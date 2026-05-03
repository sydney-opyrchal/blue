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
import paho.mqtt.client as mqtt

from app.assets import ASSETS, ASSET_TYPE_LABEL

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DB_URL = os.getenv(
    "DB_URL", "postgresql://factory:factory@localhost:5432/factory"
)

# ---- In-memory state ---------------------------------------------------------
latest_values: Dict[str, Dict[str, float]] = defaultdict(dict)   # asset_id -> metric -> value
latest_ts: Dict[str, int] = {}                                   # asset_id -> ms
active_alarms: Dict[str, dict] = {}                              # alarm_key -> alarm
alarm_history: deque = deque(maxlen=500)
ws_clients: Set[WebSocket] = set()
asset_lookup = {a["id"]: a for a in ASSETS}

main_loop: asyncio.AbstractEventLoop = None
db_pool: asyncpg.Pool = None


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
  id           BIGSERIAL PRIMARY KEY,
  asset_id     TEXT NOT NULL,
  metric       TEXT NOT NULL,
  severity     TEXT NOT NULL,
  message      TEXT NOT NULL,
  value        DOUBLE PRECISION,
  raised_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  cleared_at   TIMESTAMPTZ,
  acknowledged BOOLEAN NOT NULL DEFAULT FALSE
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
        alarm = {
            "key": key,
            "asset_id": asset_id,
            "asset_name": asset["name"],
            "metric": metric,
            "value": value,
            "severity": "high" if value > high else "low",
            "message": (
                f"{metric} = {value:.2f} exceeds redline {high}"
                if value > high
                else f"{metric} = {value:.2f} below redline {low}"
            ),
            "raised_at": datetime.utcnow().isoformat() + "Z",
            "acknowledged": False,
        }
        active_alarms[key] = alarm
        alarm_history.appendleft(alarm)
        broadcast({"type": "alarm_raised", "alarm": alarm})

        if main_loop and db_pool:
            asyncio.run_coroutine_threadsafe(
                _persist_alarm(alarm), main_loop
            )

    elif not breached and key in active_alarms:
        cleared = active_alarms.pop(key)
        cleared["cleared_at"] = datetime.utcnow().isoformat() + "Z"
        broadcast({"type": "alarm_cleared", "alarm": cleared})


async def _persist_alarm(alarm: dict):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO alarms (asset_id, metric, severity, message, value) "
            "VALUES ($1,$2,$3,$4,$5)",
            alarm["asset_id"], alarm["metric"], alarm["severity"],
            alarm["message"], alarm["value"],
        )


# ---- MQTT --------------------------------------------------------------------
def on_connect(client, userdata, flags, rc, props=None):
    print(f"[ingest] mqtt connected rc={rc}")
    client.subscribe("factory/+/+/+/+", qos=0)


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
    return list(active_alarms.values())


@app.get("/api/alarms/history")
def get_alarm_history(limit: int = 100):
    return list(alarm_history)[:limit]


@app.post("/api/alarms/{alarm_key}/ack")
def ack_alarm(alarm_key: str):
    if alarm_key in active_alarms:
        active_alarms[alarm_key]["acknowledged"] = True
        broadcast({"type": "alarm_acked", "key": alarm_key})
        return {"ok": True}
    return {"ok": False}


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
