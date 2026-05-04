"""
Ingestion + API service.

Responsibilities:
  - Subscribe to MQTT topics from the edge gateway
  - Persist readings to TimescaleDB hypertable
  - Maintain in-memory latest values + alarm state
  - Relay live updates to React clients via WebSocket
  - Serve REST endpoints for asset list, history, and alarms
"""
import asyncio
import json
import os
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Dict, List, Set

import asyncpg
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt

from app.assets import ASSETS, ASSET_TYPE_LABEL
from app.alarms import Alarm, IllegalTransition
from app.contracts import Severity

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DB_URL = os.getenv(
    "DB_URL", "postgresql://factory:factory@localhost:5432/factory"
)

# ---- In-memory state ---------------------------------------------------------
latest_values: Dict[str, Dict[str, float]] = defaultdict(dict)   # asset_id -> metric -> value
latest_ts: Dict[str, int] = {}                                   # asset_id -> ms
active_alarms: Dict[str, Alarm] = {}                             # alarm_key -> Alarm
alarm_history: deque = deque(maxlen=500)
ws_clients: Set[WebSocket] = set()
asset_lookup = {a["id"]: a for a in ASSETS}

main_loop: asyncio.AbstractEventLoop = None
db_pool: asyncpg.Pool = None
_mqtt_connected: bool = False


# ---- DB ----------------------------------------------------------------------
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS readings (
  ts          TIMESTAMPTZ NOT NULL,
  asset_id    TEXT NOT NULL,
  metric      TEXT NOT NULL,
  value       DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('readings', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS readings_asset_metric_ts
  ON readings (asset_id, metric, ts DESC);

CREATE TABLE IF NOT EXISTS alarms (
  alarm_id      TEXT PRIMARY KEY,
  device_id     TEXT NOT NULL,
  tag           TEXT NOT NULL,
  severity      TEXT NOT NULL,
  current_value DOUBLE PRECISION,
  raised_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  detector      TEXT NOT NULL
);
"""


async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=8)
    async with db_pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


# ---- Alarm logic -------------------------------------------------------------
def alarm_key(asset_id: str, metric: str) -> str:
    return f"{asset_id}::{metric}"


def alarm_to_ws_payload(alarm: Alarm) -> dict:
    """Adapter from new Alarm model to the v.1 WS message shape the
    dashboard already consumes. Spec §6.3 alignment is queued."""
    return {
        "key": f"{alarm.device_id}::{alarm.tag}",
        "asset_id": alarm.device_id,
        "asset_name": asset_lookup[alarm.device_id]["name"],
        "metric": alarm.tag,
        "value": alarm.current_value,
        "severity": alarm.severity.value,
        "message": (
            f"{alarm.tag} = {alarm.current_value:.2f} exceeds redline "
            f"{alarm.expected_range[1]}"
            if alarm.current_value > alarm.expected_range[1]
            else f"{alarm.tag} = {alarm.current_value:.2f} below redline "
                 f"{alarm.expected_range[0]}"
        ),
        "raised_at": alarm.raised_at.isoformat(),
        "acknowledged": alarm.state.value == "acknowledged",
        "alarm_id": alarm.alarm_id,
    }


def evaluate_alarm(asset_id: str, metric: str, value: float):
    asset = asset_lookup.get(asset_id)
    if not asset:
        return
    cfg = asset["metrics"].get(metric)
    if not cfg:
        return

    key = alarm_key(asset_id, metric)
    high, low = cfg["redline_high"], cfg["redline_low"]
    breached = value > high or value < low

    if breached and key not in active_alarms:
        alarm = Alarm(
            device_id=asset_id,
            tag=metric,
            current_value=value,
            expected_range=(low, high),
            severity=Severity.HIGH if value > high else Severity.LOW,
            detector="redline",
        )
        active_alarms[key] = alarm
        alarm_history.appendleft(alarm)
        broadcast({"type": "alarm_raised", "alarm": alarm_to_ws_payload(alarm)})

        if main_loop and db_pool:
            asyncio.run_coroutine_threadsafe(
                _persist_alarm(alarm), main_loop
            )

    elif not breached and key in active_alarms:
        alarm = active_alarms.pop(key)
        try:
            alarm.clear()
        except IllegalTransition as e:
            print(f"[ingest] illegal alarm clear on {key}: {e}")
            return
        broadcast({"type": "alarm_cleared", "alarm": alarm_to_ws_payload(alarm)})


async def _persist_alarm(alarm: Alarm) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO alarms (alarm_id, device_id, tag, severity, "
            "current_value, raised_at, detector) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7)",
            alarm.alarm_id, alarm.device_id, alarm.tag,
            alarm.severity.value, alarm.current_value,
            alarm.raised_at, alarm.detector,
        )


# ---- MQTT --------------------------------------------------------------------
def on_connect(client, userdata, flags, rc, props=None):
    global _mqtt_connected
    _mqtt_connected = (rc == 0)
    print(f"[ingest] mqtt connected rc={rc}")
    client.subscribe("factory/+/+/+/+", qos=0)


def on_disconnect(client, userdata, rc, props=None):
    global _mqtt_connected
    _mqtt_connected = False
    print(f"[ingest] mqtt disconnected rc={rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except json.JSONDecodeError:
        return

    # status messages have an "event" field
    if "event" in payload:
        return

    asset_id = payload.get("asset_id")
    metric = payload.get("metric")
    value = payload.get("value")
    ts = payload.get("ts")
    if asset_id is None or metric is None or value is None:
        return

    latest_values[asset_id][metric] = value
    latest_ts[asset_id] = ts
    evaluate_alarm(asset_id, metric, value)
    broadcast({
        "type": "reading",
        "asset_id": asset_id,
        "metric": metric,
        "value": value,
        "ts": ts,
    })

    if main_loop and db_pool:
        asyncio.run_coroutine_threadsafe(
            _persist_reading(ts, asset_id, metric, value), main_loop
        )


async def _persist_reading(ts_ms, asset_id, metric, value):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO readings (ts, asset_id, metric, value) "
            "VALUES (to_timestamp($1::double precision / 1000), $2, $3, $4)",
            ts_ms, asset_id, metric, float(value),
        )


# ---- WebSocket broadcast -----------------------------------------------------
def broadcast(msg: dict):
    """Called from MQTT thread; schedules sends on the main asyncio loop."""
    if not ws_clients or not main_loop:
        return
    encoded = json.dumps(msg)
    for ws in list(ws_clients):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, encoded), main_loop)


async def _safe_send(ws: WebSocket, text: str):
    try:
        await ws.send_text(text)
    except Exception:
        ws_clients.discard(ws)


# ---- App lifespan ------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    await init_db()

    client = mqtt.Client(client_id="ingest-service", protocol=mqtt.MQTTv5)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT, 60)
    client.loop_start()
    print("[ingest] ready")

    yield

    client.loop_stop()
    client.disconnect()
    await db_pool.close()


app = FastAPI(title="New Glenn IIoT Platform", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ---- REST endpoints ----------------------------------------------------------
@app.get("/health")
async def health():
    """SPEC NFR-5 — structured dependency status.

    Returns 'healthy' iff MQTT is connected and DB is reachable. Returns
    'degraded' if either is impaired. Status code is 200 on healthy/degraded
    and 503 on unhealthy so platform-level health checks behave correctly.
    """
    deps = {"mqtt": "unknown", "database": "unknown"}

    # DB check: cheap SELECT 1 on the pool.
    if db_pool is not None:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            deps["database"] = "healthy"
        except Exception:
            deps["database"] = "unhealthy"
    else:
        deps["database"] = "unhealthy"

    # MQTT check: paho exposes is_connected() on the client. We currently
    # don't hold a module-level reference to the client — track it.
    deps["mqtt"] = "healthy" if _mqtt_connected else "unhealthy"

    overall = (
        "healthy" if all(v == "healthy" for v in deps.values())
        else "degraded" if any(v == "healthy" for v in deps.values())
        else "unhealthy"
    )
    status_code = 503 if overall == "unhealthy" else 200
    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": "ingest",
            "version": "1.0.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "dependencies": deps,
        },
    )


@app.get("/api/assets")
def list_assets():
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "area": a["area"],
            "cell": a["cell"],
            "type": a["type"],
            "type_label": ASSET_TYPE_LABEL.get(a["type"], a["type"]),
            "x": a["x"], "y": a["y"],
            "metrics": [
                {
                    "name": m,
                    "redline_high": cfg["redline_high"],
                    "redline_low": cfg["redline_low"],
                    "nominal": cfg["nominal"],
                }
                for m, cfg in a["metrics"].items()
            ],
            "latest": latest_values.get(a["id"], {}),
            "latest_ts": latest_ts.get(a["id"]),
            "has_alarm": any(
                k.startswith(f"{a['id']}::") for k in active_alarms
            ),
        }
        for a in ASSETS
    ]


@app.get("/api/assets/{asset_id}/history")
async def asset_history(
    asset_id: str,
    metric: str = Query(...),
    minutes: int = Query(5, ge=1, le=240),
):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT ts, value FROM readings "
            "WHERE asset_id=$1 AND metric=$2 AND ts > NOW() - $3::interval "
            "ORDER BY ts ASC",
            asset_id, metric, timedelta(minutes=minutes),
        )
    return [
        {"ts": int(r["ts"].timestamp() * 1000), "value": r["value"]}
        for r in rows
    ]


@app.get("/api/alarms/active")
def get_active_alarms():
    return [alarm_to_ws_payload(a) for a in active_alarms.values()]


@app.get("/api/alarms/history")
def get_alarm_history(limit: int = 100):
    return [alarm_to_ws_payload(a) for a in list(alarm_history)[:limit]]


@app.post("/api/alarms/{alarm_key}/ack")
def ack_alarm(alarm_key: str):
    if alarm_key not in active_alarms:
        return {"ok": False}
    alarm = active_alarms[alarm_key]
    try:
        alarm.acknowledge(by="dashboard")
    except IllegalTransition as e:
        print(f"[ingest] illegal alarm ack on {alarm_key}: {e}")
        return {"ok": False}
    broadcast({"type": "alarm_acked", "key": alarm_key})
    return {"ok": True}


@app.get("/api/oee")
def oee_summary():
    """Quick OEE-ish KPI for the fleet overview."""
    total = len(ASSETS)
    alarming = len({k.split("::")[0] for k in active_alarms})
    online = sum(1 for a in ASSETS if a["id"] in latest_ts)
    return {
        "total_assets": total,
        "online": online,
        "alarming": alarming,
        "availability": round((online - alarming) / total, 3) if total else 0,
        "active_alarms": len(active_alarms),
    }


# ---- WebSocket ---------------------------------------------------------------
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    # Send current snapshot on connect
    await ws.send_text(json.dumps({
        "type": "snapshot",
        "latest": latest_values,
        "active_alarms": list(active_alarms.values()),
    }))
    try:
        while True:
            await ws.receive_text()  # keepalive
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)


# ---- Static SPA --------------------------------------------------------------
# Mounted last so /api/* and /ws win the route match. In local dev STATIC_DIR
# does not exist; Vite serves the SPA on :5173 and proxies /api + /ws to us.
STATIC_DIR = os.getenv("STATIC_DIR", "/app/static")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="spa")
