# CLAUDE.md — agent rules for Forge

This is **Forge**, the v.1 New Glenn Factory IIoT Monitoring Platform. Built against a 7-hour development budget. The authoritative document is `SPEC.md`; this file is the rules of engagement when working in this repo.

Before you change anything: read `SPEC.md` (what is being built), then `DECISIONS.md` (why the stack looks the way it does), then `PLAN.md` (build sequence). If your change touches anything material, the answer to "why this way" should already be in `DECISIONS.md` — and if it isn't, add an ADR there before writing the code.

## Project context

- **Services** (each its own container in `docker-compose.yml`): simulator, edge gateway, Mosquitto, FastAPI ingest, TimescaleDB, React dashboard.
- **Topic shape:** `factory/{site}/{bay}/{cell}/{device_id}/{tag}` — JSON payloads, `schema_version` field, OPC UA-style `quality` enum.
- **Telemetry payload:** see SPEC §6.1. Validate strictly at the ingest boundary; reject malformed messages with a structured error.
- **Alarm contract:** ULID `alarm_id`, lifecycle `raised → acknowledged → cleared`, full schema in SPEC §6.2.
- **WebSocket envelope:** `{ type, timestamp, payload }` with `type` ∈ `telemetry | alarm | machine_status | system_status` (SPEC §6.3).
- **Anomaly detection:** rolling z-score (60s, 3σ) AND Isolation Forest — both must agree to raise (SPEC §7.5). The "AND" gate is load-bearing.
- **Persistence:** three tables — `telemetry` (Timescale hypertable), `alarms`, `machines`. Tag-based schema, not per-sensor columns. 7-day retention on `telemetry`. Full schema in `db/schema.sql`.
- **Simulator:** declarative `simulator.yaml` defines the factory, devices, tags, normal ranges, and fault scenarios. Do not hand-code the asset list in Python.
- **Edge gateway:** Python + SQLite store-and-forward. State machine: `connected` → `buffering` → `draining` → `connected`. This pattern is core to the demo — do not bypass it.

## Stack

- **Backend:** Python 3.11+, FastAPI, paho-mqtt, asyncpg, scikit-learn (`IsolationForest`), `python-ulid`. Async-first; bridge MQTT thread to asyncio with `asyncio.run_coroutine_threadsafe`.
- **Frontend:** React + TypeScript, Vite, Recharts. Function components + hooks only. No state library — `useState` / `useReducer`.
- **Hosting:** Fly.io. Local: `docker compose up`.
- **CI:** GitHub Actions on every push.

## Scope discipline

Everything in SPEC §13 is **out of scope** for v.1. Do not:

- Add auth, TLS, RBAC, or any user model.
- Build a Historical Replay view.
- Compute OEE from first principles (display seeded values from `simulator.yaml`).
- Implement OPC UA, MES integration, multi-tenant isolation, or mobile-responsive layouts.
- Switch payloads to Sparkplug-B protobuf.

If a change feels like it's reaching into one of these, stop and ask. The §15 roadmap exists so reviewers can see I know these are the next steps — not so they get half-built.

## Code style

- **No comments that restate what the code does.** Comments only for non-obvious *why*: the `run_coroutine_threadsafe` bridge, the gateway state-machine transitions, the "both must agree" detector gate.
- **No premature abstraction.** Three similar lines beats a helper.
- **No backwards-compat shims, feature flags, or "removed X" comments.** If something is gone, it's gone.
- **TypeScript:** types follow the SPEC §6 contracts. The WS envelope is the discriminated union — let TS check the cases.
- **Python:** type hints everywhere. Pydantic is fine at the boundary (MQTT-in, REST-in); not inside the hot path.
- **Logging:** structured, to stdout. Each service emits enough to debug FM-1 through FM-8 from the logs alone.

## Tests are in scope

- Unit: validators, detectors (z-score boundary cases including NaN/empty windows, IsolationForest wrapper), gateway state machine, alarm lifecycle (legal and illegal transitions).
- Integration: device → broker → ingest → DB → WS round-trip; fault injection → alarm; gateway buffer/drain across a broker restart; WS reconnect across an ingest restart.
- Acceptance: `scripts/acceptance_test.sh` walks SPEC §12 in CI.
- Smoke: 15-item checklist in `docs/SMOKE_TEST.md` after every deploy.

Coverage targets: **≥70% ingest, ≥60% overall**. Don't chase the number past these — write the tests that catch the failure modes in SPEC §10.

## Working with this repo

- The four root markdown files (README, SPEC, PLAN, DECISIONS, CLAUDE, KNOWN_ISSUES) earn their place. Do not restructure them.
- New decisions worth a paragraph go in `DECISIONS.md` as a new ADR; do not sprinkle them across files.
- New scope worth implementing goes into `SPEC.md` (and out of §13) **before** any code is written.
- README is the front door. Keep it short — link to SPEC / PLAN / DECISIONS rather than duplicating content.
- `KNOWN_ISSUES.md` is where honest limitations live. When you hit one during build, write it down.

## Things that are easy to get wrong

- **MQTT thread ≠ asyncio loop.** Anything that touches the DB or WS broadcast from inside a paho callback must go through `run_coroutine_threadsafe`.
- **TimescaleDB hypertables.** A plain `CREATE TABLE` without `create_hypertable(...)` after silently gives you a regular Postgres table. Verify in `db/schema.sql`.
- **Schema validation at the ingest boundary.** A missing `schema_version` or a malformed `timestamp` must be rejected and logged — never crash the consumer or silently coerce.
- **Two-layer detector "AND" gate.** It is *both must agree to raise*, not "either fires." Getting this wrong floods the dashboard.
- **Gateway drain order.** Buffered messages drain in chronological order (timestamp, not insert time). The store-and-forward demo only works if a reviewer can verify ordering on reconnect.
- **WebSocket envelope.** Always `{ type, timestamp, payload }`. Any code that emits a bare object skips the discriminated-union check on the client and will go silently wrong.
- **Alarm lifecycle.** Illegal transitions (`cleared → raised`, `acknowledged → raised`) must error, not silently overwrite.
