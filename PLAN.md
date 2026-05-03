# PLAN

The build sequence from current repo state to v.1 acceptance (SPEC §12). Derived from `SPEC.md`; rationale for the choices below lives in `DECISIONS.md`.

This plan is sequenced so that each phase leaves the system in a runnable, demoable state. If the budget runs out, the previous phase boundary is the natural cut point.

## Snapshot of current state

The repo has a usable but spec-non-compliant prototype:

- `backend/app/assets.py` — Python-coded asset fleet (replaces what should become `simulator.yaml`).
- `backend/app/simulator.py` — publishes telemetry, but on the old topic shape `factory/{area}/{cell}/{asset}/{metric}` and the old payload shape (no `schema_version`, no `quality`, no `metadata` block).
- `backend/app/main.py` — FastAPI ingest + WS, no schema validation, no alarm table, no `/health`, no detectors beyond static redlines.
- `frontend/src/App.jsx` — single-file JS React app using uPlot.
- `docker-compose.yml` — Mosquitto + TimescaleDB only. No gateway, no ingest, no frontend, no simulator container.
- No tests, no CI, no `db/schema.sql`, no `simulator.yaml`, no Fly config.

Almost every file gets touched. The plan below sequences the rewrite so the demo is never broken for long.

## Build sequence

### Phase 0 — Foundation docs (done)

Saved: `SPEC.md`, `DECISIONS.md`, `CLAUDE.md`, `PLAN.md` (this file), `KNOWN_ISSUES.md`. README will be refreshed at the end so it points at the final shape.

### Phase 1 — Data contract & schema (no UI yet)

The contract is the spine; everything else hangs off it. Get it right before writing the services that depend on it.

1. Author `simulator.yaml` defining at least 6 devices across CNC, FSW, autoclave, cleanroom (FR-1.1). Include normal ranges, units, and 2–3 fault scenarios per machine.
2. Author `db/schema.sql`:
   - `CREATE EXTENSION timescaledb;`
   - `telemetry` table → `create_hypertable('telemetry', 'time')`
   - `alarms` table with full lifecycle columns
   - `machines` table seeded from `simulator.yaml` at first ingest boot
   - Retention policy job (drop telemetry > 7 days)
3. Author shared Python types/Pydantic models for SPEC §6.1 telemetry and §6.2 alarms; one `validators` module imported by ingest and tests.
4. Author shared TS types for the same contracts (frontend) plus the §6.3 WS envelope as a discriminated union.

**Exit criteria:** `db/schema.sql` applies cleanly to a fresh Timescale container; `pytest tests/contract/test_schemas.py` passes against fixtures of valid + invalid payloads.

### Phase 2 — Simulator → Gateway → Broker → Ingest happy path

Wire the new data contract through every service end-to-end before adding ML, alarms, or UI polish.

5. Rewrite `backend/app/simulator.py` to read `simulator.yaml` and publish on the new topic shape `factory/{site}/{bay}/{cell}/{device_id}/{tag}` with the new payload (FR-1.2 / FR-1.3 / FR-1.4). Default 1 Hz per device.
6. New service `backend/app/gateway/` — Python + paho-mqtt + SQLite. State machine (`connected` / `buffering` / `draining`). Drain order = `ORDER BY timestamp ASC` (FR-2.1 to FR-2.5).
7. Rewrite `backend/app/main.py` ingest:
   - Subscribe to `factory/#`, validate against the Phase-1 models, reject malformed (FR-3.1, FR-3.2).
   - Insert valid rows into `telemetry`.
   - Push raw telemetry over WS in the §6.3 envelope.
   - Add `/health` returning `{ broker, db, last_message_at }`.
8. Update `docker-compose.yml`: add simulator, gateway, ingest, frontend services; ensure `depends_on` + healthchecks model the boot order.

**Exit criteria:** `docker compose up`, then `mosquitto_sub -t 'factory/#'` shows new-shape payloads; `psql` shows rows in `telemetry`; a WS client receives `telemetry` envelopes; `curl /health` returns structured JSON.

### Phase 3 — Anomaly detection & alarm lifecycle

9. Rolling z-score detector module: per-`(device_id, tag)` ring buffer, configurable window (default 60s) and threshold (default 3σ). NaN-safe, empty-window safe.
10. Isolation Forest wrapper: train per tag at boot from synthetic baseline (sampled from `normal_ranges` in `simulator.yaml`). Persist trained models in-memory; reload on restart from yaml (no model files needed for v.1).
11. "Both must agree" gate. Single sensitivity flag for layer-1-only mode (FR-5.2 mentions this is configurable).
12. Alarm lifecycle: ULID at raise, transitions `raised → acknowledged → cleared`, illegal transitions error. Persist to `alarms`. Emit `alarm` envelope over WS on every state change.
13. REST endpoints: `POST /alarms/{id}/ack`, `POST /faults/inject`, `GET /alarms?state=raised`, `GET /alarms/history?limit=200` (FR-1.5, FR-6.3).
14. `machine_status` derivation: any active alarm → `alarming`; layer-1-only fire → `degraded`; otherwise `healthy`. Push `machine_status` envelope on changes.

**Exit criteria:** Curl `POST /faults/inject` for a machine with an out-of-range value; within 5s see an `alarm` envelope on WS, a row in `alarms`, and a `machine_status` change envelope. Acknowledge moves the alarm to `acknowledged`; the value normalizing for one window clears it.

### Phase 4 — Frontend rewrite (TS + Recharts)

15. New Vite + React + TypeScript scaffold under `frontend/`. Replace single-file `App.jsx` with a small file tree: `App.tsx`, `routes/FloorMap.tsx`, `routes/MachineDetail.tsx`, `components/AlarmConsole.tsx`, `components/SystemStatus.tsx`, `lib/ws.ts`, `lib/types.ts`.
16. WebSocket client (`lib/ws.ts`): connect, auto-reconnect with backoff (5s → 30s max, FR-3 / FM-6), discriminated union router on the §6.3 envelope.
17. Floor map (FR-6.1): SVG laid out from `floor_position` (x/y/w/h) per machine; status color mapping `healthy → green | degraded → yellow | alarming → red`; click to drill in; URL-routed so the back button works.
18. Machine detail (FR-6.2): live Recharts line charts (last 5 minutes streaming) per tag; current job display; per-machine active alarms; OEE strip seeded from `simulator.yaml`.
19. Alarm console (FR-6.3): live alarms list with severity badges, ack button, "history" tab.
20. Fleet overview header (FR-6.4): online count, active alarm count, last-hour throughput.
21. Fault injection control (FR-6.5): dropdown of scenarios from a `GET /faults/scenarios` endpoint; trigger button POSTs to `/faults/inject`.
22. System status footer widget (FR-7 / NFR-7): subscribes to `system_status` envelope and surfaces broker / db / ingest health.

**Exit criteria:** Click through the §12 acceptance criteria 1–7 manually in the browser. Everything except deployment passes.

### Phase 5 — Tests & CI

23. Unit tests: schema validators, z-score (boundaries, NaN, empty window), IsolationForest wrapper, gateway state machine transitions + drain order, alarm lifecycle (legal + illegal).
24. Integration tests: round-trip publish → DB → WS; fault inject → alarm; gateway buffer/drain across broker restart; WS reconnect across ingest restart.
25. Acceptance script `scripts/acceptance_test.sh`: boots compose, waits for `/health` to be green on every service, then walks SPEC §12 and exits non-zero on failure.
26. GitHub Actions workflow: install, lint, type-check, run unit + integration + acceptance on every push.

**Exit criteria:** Coverage ≥70% on ingest, ≥60% overall. CI green on `main`.

### Phase 6 — Deploy & documentation

27. `fly.toml` per service (broker, ingest, frontend, gateway, simulator) plus a single shared volume for the gateway SQLite buffer. Postgres can run on Fly's managed Postgres or as a containerized Timescale with a Fly volume.
28. `docs/AWS_DEPLOYMENT.md`: production topology — IoT Core, ECS Fargate, RDS / Timestream, CloudFront + S3, ALB for WS — with the §5 architecture mapped service by service.
29. `docs/SMOKE_TEST.md`: 15-item manual checklist (~30s each) covering the reviewer-likely click path.
30. Refresh `README.md` to point at the deployed URL, the four root docs, and a 4-line quickstart.
31. Update `KNOWN_ISSUES.md` with anything discovered during build.

**Exit criteria:** Public Fly.io URL serves the dashboard. Cold start under 90s (criterion #10). All NFR-4 docs present. CI green.

## Acceptance script outline (Phase 5)

`scripts/acceptance_test.sh` is small but load-bearing — it's how a reviewer answers "does it actually work?" without clicking around. Pseudocode:

```
docker compose up -d
wait_for "GET /health on ingest" → all deps green, timeout 60s
assert "GET /machines returns ≥6"
open WS to /ws
assert "first telemetry envelope received within 5s"
POST /faults/inject {device_id: cnc-07, scenario: spindle_overheat}
assert "alarm envelope for cnc-07 within 5s"
assert "machine_status envelope alarming for cnc-07 within 5s"
POST /alarms/{id}/ack
assert "alarm row state=acknowledged"
docker compose stop mosquitto
sleep 15
docker compose start mosquitto
assert "telemetry resumes; gateway logs show drain"
echo "PASS"
```

This is what gets called from CI and what a reviewer can run locally.

## What this plan does not promise

- Hitting all six phases inside the 7-hour budget. The realistic cut-line is somewhere in Phase 4 or Phase 5; Phase 6 might collapse to "Fly deploy works, AWS doc is a stub." Whatever lands, `KNOWN_ISSUES.md` will be honest about it.
- That every spec FR is fully tested. The test plan covers the highest-leverage paths; the rest is documented honestly per SPEC §11.6.
- That the architecture survives v.2. It is intentionally sized for v.1 demands; §15 names the v.2 / v.3 reshape candidates.
