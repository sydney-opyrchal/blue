# DECISIONS

Short ADR-style log of the load-bearing calls. Each entry: what was chosen, what was rejected, and why. Anything subjective enough that a reviewer might ask "why not X?" should live here.

---

## ADR-001 — MQTT (Mosquitto) for the transport

**Decision:** Eclipse Mosquitto as the broker; MQTT 3.1.1 between simulator and ingest.

**Why:** MQTT is the de-facto standard for IIoT — lightweight, pub/sub, retained messages, last-will for disconnect detection. Mosquitto is the simplest broker that's still production-credible.

**Rejected:**
- *Kafka* — overkill at 80 msg/s; brokers are heavier to run and the client story for browsers/edge is worse. Would revisit at thousands of tags or when replayability matters.
- *HTTP polling* — no fan-out semantics, wastes round-trips, doesn't model the real factory transport.

---

## ADR-002 — Sparkplug-B-style topics, JSON payloads (not protobuf)

**Decision:** Topic shape follows Sparkplug-B / ISA-95: `factory/{area}/{cell}/{asset}/{metric}`. Payloads are JSON.

**Why:** The topic convention is the part that signals "this is how real IIoT systems are organized." The protobuf payload is the part that makes traffic unreadable in `mosquitto_sub` and adds a codegen step. For a demo, readability wins.

**Rejected:** Full Sparkplug-B compliance (binary payload, birth/death certificates). Listed in roadmap; would matter for interop with Ignition or AVEVA.

---

## ADR-003 — TimescaleDB as the historian

**Decision:** Postgres + TimescaleDB extension, hypertable per metric stream.

**Why:** Time-series performance plus the entire SQL ecosystem. Hypertables handle the chunking; queries are just SQL. Easier to operate than InfluxDB on a small project.

**Rejected:**
- *InfluxDB* — strong product but a separate query language, separate ops story, and the v2/v3 transition is still messy.
- *Plain Postgres* — fine at this scale but doesn't tell the time-series story I want to tell.
- *Parquet on disk* — great for batch analytics, wrong shape for live dashboards.

---

## ADR-004 — FastAPI + paho-mqtt + asyncpg

**Decision:** Single Python process subscribes to MQTT (paho), validates and writes to Timescale (asyncpg), and fans out to the browser over WebSockets (FastAPI).

**Why:** FastAPI's async story makes the WS fan-out trivial. paho-mqtt is the canonical Python MQTT client; asyncpg is the fastest Postgres driver. One process keeps the demo deployable from a single `uvicorn` command.

**Note:** paho-mqtt runs its loop on a thread, FastAPI runs on asyncio. Bridge with `asyncio.run_coroutine_threadsafe(...)` from the MQTT callback. This is the one piece of glue that's worth understanding before changing.

**Rejected:** Splitting ingest and API into separate services. Right call eventually (independent scaling, isolation), wrong call for a 10-hour build.

---

## ADR-005 — WebSocket fan-out from a single API process

**Decision:** Browser clients open a WS to the API; the API broadcasts every tick.

**Why:** Pushes live data without polling. Fits the single-process architecture in ADR-004.

**Limit:** Re-encodes JSON per client. Fine for a handful of operators, breaks above ~50 concurrent. Mitigation listed in SPEC.md scaling notes (encode once per tick, or Redis pub/sub between replicas).

**Rejected:** SSE — simpler but one-way; we want ack-alarm round-trips on the same channel.

---

## ADR-006 — uPlot for the time-series charts

**Decision:** uPlot on the asset-drilldown view.

**Why:** Recharts and Chart.js choke on multi-channel high-frequency updates. uPlot was built for this exact use case.

**Rejected:** Recharts (DX is nicer, perf is not), Chart.js (similar), D3-from-scratch (too much code for one weekend).

---

## ADR-007 — No auth, no TLS in scope

**Decision:** Broker is anonymous, API is unauthenticated, WS is plaintext.

**Why:** Auth is a rabbit hole — mTLS on the broker, OIDC on the API, role mapping in the UI — that doesn't differentiate the demo. Listed in roadmap.

**How to apply:** If a reviewer asks "where's auth?" — point at this entry and the roadmap. Don't half-build it.

---

## ADR-008 — Single-file React UI

**Decision:** `App.jsx` holds the whole frontend; Vite builds it.

**Why:** Component splitting is premature at this size. One file means one place to read the whole UI. Will split if/when a second view appears that genuinely shares state.

**Rejected:** Next.js (no SSR need, extra build complexity), full component library (Radix/shadcn would dwarf the actual app code).

---

## ADR-009 — Hand-rolled spec docs over Spec Kit

**Decision:** README + SPEC + DECISIONS + CLAUDE, written by hand.

**Why:** For a 10-hour single-purpose project, the docs *are* the deliverable showing how I think. Spec Kit's slash commands and generated artifacts add ceremony without proving thinking. Reviewer should be able to read SPEC and DECISIONS in 10 minutes and know exactly what was built and what was traded off.

**Rejected:** Spec Kit (`/speckit.specify`, `/speckit.plan`, etc.) — defensible for a longer project; wrong shape here.
