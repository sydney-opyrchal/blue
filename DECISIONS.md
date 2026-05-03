# DECISIONS

ADR-style log of the load-bearing calls. Each entry: what was chosen, what was rejected, and why. Anything subjective enough that a reviewer might ask "why not X?" lives here.

The decisions below align with the v.1 spec (`SPEC.md`); where this file and the spec disagree, the spec wins. The **Status:** line under each ADR title records the v.1 implementation state of that decision; cross-referenced gaps are tracked in `KNOWN_ISSUES.md`.

---

## ADR-001 — MQTT (Mosquitto) for the transport

**Status:** Implemented in v.1. Mosquitto in docker-compose; paho-mqtt clients in simulator and ingest.

**Decision:** Eclipse Mosquitto as the broker; MQTT 3.1.1 between gateway and ingest.

**Why:** MQTT is the de-facto standard for IIoT — lightweight, pub/sub, retained messages, last-will for disconnect detection. Mosquitto is the simplest broker that's still production-credible and has zero-config Docker images.

**Rejected:**
- *Kafka* — overkill at 50 msg/s; brokers are heavier to run and the client story for browsers/edge is worse. Listed in §15 as a v.2/v.3 consideration.
- *AWS IoT Core* — production answer (documented in `docs/AWS_DEPLOYMENT.md`), but locks the local-dev story to AWS credentials. Out of scope for v.1.
- *HTTP polling* — no fan-out semantics, wastes round-trips, doesn't model the real factory transport.

---

## ADR-002 — Sparkplug-B-inspired topics, JSON payloads with explicit `schema_version`

**Status:** Partial in v.1. Topic shape simplified to 4 levels (`factory/{area}/{cell}/{asset_id}/{metric}`; `{site}` segment deferred). Payload simplified to `{ts, asset_id, metric, value}`; `schema_version`, `quality`, and `metadata` block deferred. Tracked in `KNOWN_ISSUES.md`. v.1.5 priority.

**Decision:** Topic shape: `factory/{site}/{bay}/{cell}/{device_id}/{tag}` (ISA-95 / Sparkplug-B namespace shape). Payloads are JSON with a top-level `schema_version`, `quality` field (OPC UA-inspired enum), and explicit `metadata` echoing the topic hierarchy.

**Why:** The topic convention signals "this is how real IIoT systems are organized." The JSON payload keeps `mosquitto_sub` traffic readable and avoids a protobuf codegen step. The explicit `schema_version` is the cheap forward-compat hedge that costs nothing now and saves weeks later. The `quality` field is borrowed from OPC UA so reviewers familiar with that world see the right vocabulary.

**Rejected:**
- *Sparkplug-B binary protobuf payloads + birth/death certificates* — the right call for a real Ignition / AVEVA interop story. Listed in §15 / `KNOWN_ISSUES.md`.
- *No `schema_version` field* — saves 20 bytes; costs the ability to evolve the contract without breaking consumers.
- *Topic hierarchy without `site`* — earlier draft used `factory/{area}/{cell}/{asset}/{metric}`. Adding `site` and `bay` makes the multi-site / multi-building case structurally trivial later, even though v.1 has one site.

---

## ADR-003 — TimescaleDB as the historian, tag-based schema

**Status:** Partial in v.1. TimescaleDB hypertable implemented; row layout simplified to `(ts, asset_id, metric, value)`. Full SPEC §6.4 schema (`site`, `bay`, `cell`, `quality`, `unit`) deferred. Retention policy not yet scheduled. Tracked in `KNOWN_ISSUES.md`. v.1.5 priority.

**Decision:** Postgres + TimescaleDB extension. `telemetry` is a hypertable with columns `(time, site, bay, cell, device_id, tag, value, quality, unit)` — one row per reading, not one column per sensor.

**Why:** Time-series performance plus the entire SQL ecosystem. Hypertables handle the chunking; queries are just SQL. Tag-based schema means adding a new sensor is a publish, not a migration.

**Retention:** Drop telemetry older than 7 days via a scheduled job. Real factories keep years; v.1 keeps a week. Aggregations beyond 7 days deferred to v.2.

**Rejected:**
- *Per-sensor columns* — tempting for query simplicity, fatal for schema evolution. New sensor = new migration = no.
- *InfluxDB* — strong product, but a separate query language and ops story. Postgres lets the team stay in SQL.
- *Amazon Timestream* — production answer (see `docs/AWS_DEPLOYMENT.md`), wrong for local-first dev.
- *Plain Postgres* — fine at this scale, but doesn't tell the time-series story I want to tell, and chunking has to be hand-rolled.

---

## ADR-004 — FastAPI + paho-mqtt + asyncpg in one ingest process

**Status:** Implemented in v.1. Single uvicorn process runs the MQTT subscriber, asyncpg pool, REST endpoints, and WebSocket fan-out. The `asyncio.run_coroutine_threadsafe` bridge described in the note is the live mechanism in `backend/app/main.py`.

**Decision:** Single Python process subscribes to MQTT (paho), validates and writes to Timescale (asyncpg), and fans out to the browser over WebSockets (FastAPI).

**Why:** FastAPI's async story makes the WS fan-out trivial. paho-mqtt is the canonical Python MQTT client; asyncpg is the fastest Postgres driver. One process keeps the demo deployable from a single `uvicorn` command and stays inside the 7-hour budget.

**Note:** paho-mqtt runs its loop on a thread, FastAPI runs on asyncio. Bridge with `asyncio.run_coroutine_threadsafe(...)` from MQTT callbacks. This is the one piece of glue worth understanding before changing.

**Rejected:** Splitting ingest and API into separate services. Right call eventually; wrong call inside the v.1 budget.

---

## ADR-005 — Dedicated edge gateway with SQLite store-and-forward

**Status:** Specified, not yet implemented in v.1. The simulator publishes directly to Mosquitto. The dedicated gateway service, the SQLite buffer, and the `connected → buffering → draining` state machine are queued for v.1.5. This is the highest-priority architectural item on the v.1.5 list — the spec describes it because it is the right pattern; the demo runs without it for now. Tracked in `KNOWN_ISSUES.md`.

**Decision:** A separate Python service sits between simulated devices and Mosquitto. While the broker is reachable it forwards with negligible latency; while it isn't, it buffers to a local SQLite file and drains in chronological order on reconnect. State machine: `connected` → `buffering` → `draining` → `connected`.

**Why:** This is the single most credible IIoT pattern in the project. Real factories lose network constantly; production code that assumes a healthy broker is a junior smell. Standing up a real store-and-forward gateway — even a small one — is the difference between "demo" and "I understand the failure modes."

**SQLite specifically:** durable across restart, no external dependency, ordered drains by primary key.

**Rejected:**
- *Buffering inside the simulator process* — same code path as production devices won't have, defeats the point.
- *Buffering inside the ingest service* — wrong side of the broker. Doesn't help when the broker itself is down.
- *In-memory buffer only* — lost on gateway restart. Broker outages and gateway restarts both happen; one buffer should survive both.

---

## ADR-006 — Two-layer anomaly detection: rolling z-score + Isolation Forest, both must agree

**Status:** Specified, not yet implemented in v.1. v.1 alarms run on static redline thresholds only (`redline_high` / `redline_low` per metric in `backend/app/assets.py`). The rolling z-score and `IsolationForest` layers are queued for v.1.5. Static thresholds are kept regardless as the source of `expected_range` on alarm payloads. Tracked in `KNOWN_ISSUES.md`. High v.1.5 priority.

**Decision:** Two detectors run on every incoming reading.
1. Layer 1: rolling z-score per `(device_id, tag)` over the last 60 seconds; trips at |z| > 3.
2. Layer 2: scikit-learn `IsolationForest`, trained on synthetic baseline data per tag; trips on `predict() == -1`.

An alarm raises only when both layers agree. Layer 1 alone is configurable for higher sensitivity.

**Why:** Single-detector systems are noisy. The "both must agree" gate cuts false positives sharply with almost no engineering cost. Isolation Forest is a defensible ML choice — small, fast, no GPU, and recognizable to anyone who has shipped an anomaly system before. Two layers also gives a specific story for FM-7 (false positives) in the spec.

**Rejected:**
- *Static redlines only* — works, but doesn't earn the "anomaly detection" label honestly. Static thresholds are kept in `simulator.yaml` as the source of `expected_range` displayed on alarm payloads.
- *Heavyweight models (LSTM, Prophet, etc.)* — overkill for v.1, training infra alone would eat the budget.
- *Single detector* — cheaper but noisier. The "both must agree" pattern is the cheapest credible upgrade.

---

## ADR-007 — Declarative `simulator.yaml` over Python-coded asset list

**Status:** Specified, not yet implemented in v.1. The asset fleet currently lives in `backend/app/assets.py` as a Python list. The YAML conversion is a near-mechanical transform queued for v.1.5. The decision still stands; the conversion is overdue.

**Decision:** Factory layout, devices, sensor tags, normal ranges, and fault scenarios live in `simulator.yaml`, not in Python. The simulator and the `machines` table both load from this file at boot.

**Why:** A reviewer reading `simulator.yaml` sees the whole factory in one screen. A reviewer reading `assets.py` sees a Python data structure that could be anything. Declarative config is also what real IIoT systems do (Ignition tag exports, OPC UA address spaces).

**Rejected:** Keeping the Python module. Faster to edit during dev but harder to reason about and not portable to other languages or tools.

---

## ADR-008 — ULID alarm IDs, full lifecycle in one row

**Status:** Partial in v.1. The single-row lifecycle (`raised_at`, `cleared_at`, `acknowledged`) is implemented. ULID `alarm_id` is not — current PK is `BIGSERIAL`. Switching the PK is a small migration queued for v.1.5.

**Decision:** Alarms get a ULID `alarm_id` at raise time. The same row carries `state` (`raised` / `acknowledged` / `cleared`) and the corresponding timestamps (`raised_at`, `acknowledged_at`, `cleared_at`). No separate `alarm_events` audit table in v.1.

**Why:** ULIDs are sortable by time, URL-safe, and stable across state transitions — better than UUIDs for this use case. Single-row lifecycle is enough to satisfy §6.2 and §7.4 within budget; an event-sourced version is a v.2 candidate.

**Rejected:** UUIDv4 (not time-sortable), auto-incrementing integers (leak ordering and count to clients), separate `alarm_events` table (the right answer for audit trails, the wrong answer for v.1 budget).

---

## ADR-009 — WebSocket fan-out from the ingest process, typed envelope

**Status:** Partial in v.1. WebSocket fan-out is implemented; the typed-envelope discipline is in place. The exact envelope shape and the type vocabulary differ from SPEC §6.3 — code uses `{type, ...fields}` with `type` ∈ `{snapshot, reading, alarm_raised, alarm_cleared, alarm_acked}` rather than the spec's `{type, timestamp, payload}` with `type` ∈ `{telemetry, alarm, machine_status, system_status}`. Aligning to spec is queued for v.1.5.

**Decision:** Browser clients open one WS to the ingest service. Every server→client message uses the envelope `{ type, timestamp, payload }` with `type` ∈ {`telemetry`, `alarm`, `machine_status`, `system_status`}.

**Why:** Pushes live data without polling. The typed envelope is the cheapest move that makes the client side router obvious and lets us add new event types without a protocol change.

**Limit:** Re-encodes JSON per client. Fine for a handful of operators; mitigation listed in `SPEC.md` §10 / scaling notes.

**Rejected:** Server-Sent Events (one-way only; no acknowledge round-trip), untyped messages (every new event becomes an ad-hoc spec).

---

## ADR-010 — React + TypeScript, Recharts for charts

**Status:** Partial in v.1. Implemented as React + JSX (TypeScript deferred for build velocity) and uPlot for charts (substituted for Recharts because the dense per-metric live sparkline grid renders more cleanly under uPlot at 2 Hz). README reflects the as-built stack. TypeScript migration is queued for v.1.5; chart library will likely stay on uPlot based on v.1 experience.

**Decision:** React + TypeScript with Vite. Recharts for time-series charts.

**Why:** TypeScript catches the WS envelope / payload mismatch bugs at edit time, which is exactly the class of bug this app is most exposed to. Recharts is a familiar, sufficient charting library at v.1 scale (~6 machines × ~3 tags × 1 Hz on the detail view) and matches the spec.

**Rejected:**
- *uPlot* — faster at high frequency / many series, but the v.1 detail view shows one machine at a time. Recharts wins on developer ergonomics inside the budget.
- *Plain JavaScript* — TypeScript pays for itself the first time the WS envelope changes.
- *Component library (Radix / shadcn / MUI)* — would dwarf the actual app code at this size.

---

## ADR-011 — No auth in v.1

**Status:** Implemented (intentional absence) in v.1. Broker, REST, and WebSocket are all unauthenticated as specified. Listed in `SPEC.md` §13 and `KNOWN_ISSUES.md`. v.2 candidate.

**Decision:** Broker is anonymous, ingest API is unauthenticated, WS is plaintext.

**Why:** Auth is a rabbit hole — mTLS on the broker, OIDC on the API, role mapping in the UI — that doesn't differentiate the demo. Listed as out of scope in §13 and as v.2 in §15.

**How to apply:** If a reviewer asks "where's auth?" — point at this entry, §13, and §15. Don't half-build it.

---

## ADR-012 — Fly.io for hosting

**Status:** Specified, not yet implemented in v.1. Repo is public on GitHub; live deployment to Fly.io is queued. No `fly.toml` or per-service Dockerfiles for the application yet. Tracked in `KNOWN_ISSUES.md`. High v.1.5 priority — the README claims a deployable stack and the deployment is needed to back that claim.

**Decision:** Deploy v.1 to Fly.io.

**Why:** Multi-service Docker deploys, long-lived WebSocket connections, public URL with HTTPS, and free-tier-friendly. Cold-start under 90s is achievable (acceptance criterion #10).

**Rejected:**
- *AWS-native (ECS Fargate + ALB + IoT Core + RDS)* — the production answer (`docs/AWS_DEPLOYMENT.md`). Wrong shape for v.1 because each service needs separate IAM, networking, and deploy pipelines.
- *Render / Railway* — fine, but Fly's WS story and multi-container support is closer to what a real deployment looks like.
- *Self-hosted on a VPS* — adds an ops chore that doesn't serve the demo.

---

## ADR-013 — Tests in scope: layered, with explicit honesty about gaps

**Status:** Specified, not yet implemented in v.1. The repo contains no automated tests, no `scripts/acceptance_test.sh`, no CI workflow, and no `docs/SMOKE_TEST.md`. Coverage targets in `SPEC.md` NFR-3 are aspirational for v.1. Test scaffolding is queued for v.1.5; the spec described shape is the right one and stands. High v.1.5 priority — credibility of the implementation under change depends on this layer.

**Decision:** Unit tests on validators / detectors / lifecycle transitions; integration tests on round-trips and gateway recovery; one acceptance script (`scripts/acceptance_test.sh`) that walks the §12 criteria; a 15-item manual smoke test in `docs/SMOKE_TEST.md`. Coverage targets: ≥70% ingest, ≥60% overall.

**Why:** Tests are what makes this a credible v.1 instead of a vibe-coded demo. The four-layer split (unit / integration / acceptance / smoke) maps the test surface to the highest-leverage failures rather than chasing a coverage number.

**Rejected:** Skipping tests entirely (the obvious time-budget temptation, the obvious credibility cost).

---

## ADR-014 — Hand-rolled spec docs, spec-first methodology

**Status:** Implemented in v.1. SPEC, PLAN, CLAUDE, DECISIONS, and KNOWN_ISSUES are all present at the repo root and were authored before application code. The methodology described in SPEC §16 is the methodology in use.

**Decision:** `README` + `SPEC` + `PLAN` + `DECISIONS` + `CLAUDE` + `KNOWN_ISSUES` at the root, `docs/AWS_DEPLOYMENT.md` and `docs/SMOKE_TEST.md` underneath. Spec authored before code; plan derived from spec; code follows.

**Why:** For a 7-hour single-purpose project, the docs *are* the deliverable showing how I think. Hand-written artifacts read as thinking; tool-generated ones don't. The spec-first sequence is the methodology being demonstrated, not just the order of operations (see SPEC §16).

**Rejected:** Spec Kit (`/speckit.specify`, `/speckit.plan`, etc.) — defensible for a longer project; wrong shape for this one.
