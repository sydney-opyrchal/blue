# SPEC

**Project:** New Glenn Factory IIoT Monitoring Platform
**Codename:** Forge
**Author:** Sydney Opyrchal
**Status:** v.1 specification, locked
**Last updated:** May 3, 2026

---

## 1. Purpose

Forge is a working prototype of an Industrial IoT (IIoT) monitoring platform for a rocket-engine manufacturing floor. It ingests telemetry from a simulated fleet of factory equipment, persists it to a time-series database, surfaces anomalies in real time, and presents a live operations dashboard for plant engineers.

The system is designed to demonstrate the architectural patterns used in real smart-factory deployments: edge devices, an MQTT message bus, a store-and-forward edge gateway, a time-series backend, and a real-time React dashboard.

This is a v.1 prototype built against a 7-hour development budget. Scope decisions throughout the document reflect that constraint and are deliberate; deferred features are documented in §15.

---

## 2. Why this project

Industrializing access to space requires industrializing engine manufacturing. Real-time visibility into factory floor operations — equipment health, throughput, anomalies, and yield — is foundational to running a manufacturing operation at the cadence reusable launch demands.

Forge is a small, honest instance of that kind of system. It is not a toy: every architectural choice mirrors how a production IIoT platform would be built, scaled down to fit the development window.

---

## 3. Glossary

Terms used throughout this document, defined to remove ambiguity during implementation and review.

- **Tag:** a named, typed signal from a device. Examples: `spindle_temp_c`, `weld_current_a`, `autoclave_pressure_psi`. Equivalent to "metric" or "signal" in other traditions.
- **Device:** a logical piece of equipment that emits one or more tags. Has a unique `device_id` within the factory namespace. Examples: `cnc-07`, `fsw-02`, `autoclave-01`.
- **Telemetry:** a single time-stamped reading of one tag from one device. The atomic unit of data flowing through the system.
- **Alarm:** a stateful event indicating a tag has gone outside its expected range. Has a lifecycle: raised → acknowledged → cleared. The system uses "alarm" as the single term for all severities.
- **Fault:** a deliberate or simulated condition causing one or more devices to emit anomalous telemetry. Distinct from "failure" — a fault is the cause, an alarm is the system response.
- **Failure:** an actual breakdown in system or equipment operation.
- **Edge:** any compute located logically or physically near the equipment. In this project, the simulated devices and the gateway.
- **Gateway:** the specific edge service that buffers and forwards messages to MQTT, providing store-and-forward resilience.
- **Broker:** the MQTT message router (Mosquitto in this project).
- **Ingest service:** the FastAPI service that subscribes to MQTT, validates payloads, runs anomaly detection, persists to the database, and pushes updates to dashboard clients.
- **OEE:** Overall Equipment Effectiveness — a composite metric (Availability × Performance × Quality) used in manufacturing to assess equipment utilization. Displayed in v.1 with seeded inputs; not computed from first principles.
- **Sparkplug B:** an Eclipse Foundation specification for MQTT topic naming and payload conventions in industrial contexts. This project uses Sparkplug-B-inspired topic naming, not the full specification.
- **Quality (of telemetry):** a per-reading classification — `good`, `uncertain`, `bad`, or `stale`. Inspired by OPC UA's quality model.

---

## 4. Users and use cases

Primary user: a plant engineer on the manufacturing floor.

Use cases in scope for v.1:

- Glance at a live factory floor map and immediately see which machines are healthy, degraded, or alarming
- Drill into any machine to see its recent sensor history, current job, and active alarms
- Watch alarms appear in real time as equipment drifts outside normal operating ranges
- Acknowledge alarms with a single click and see them move to history
- Trigger a controlled fault scenario on demand (for demonstration and operator training)

Use cases out of scope (see §15): historical replay, multi-user authentication, role-based access control, full OEE computation from first principles, multi-tenant isolation, mobile-responsive layout.

---

## 5. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      SIMULATED FACTORY                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │  CNC-07  │  │  FSW-02  │  │ Autoclave│  │ Cleanroom    │    │
│  │  spindle │  │  weld    │  │ pressure │  │ env sensors  │    │
│  │  vib     │  │  current │  │ temp     │  │ humidity     │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
└───────┼─────────────┼─────────────┼───────────────┼────────────┘
        │             │             │               │
        ▼             ▼             ▼               ▼
   ┌────────────────────────────────────────────────────┐
   │   EDGE GATEWAY  (store-and-forward, SQLite buffer) │
   └─────────────────────────┬──────────────────────────┘
                             │ MQTT
                             ▼
                    ┌────────────────┐
                    │  Mosquitto     │
                    │  (MQTT broker) │
                    └───────┬────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │  FastAPI Ingest     │
                 │  - validates        │
                 │  - tags             │
                 │  - anomaly check    │
                 │  - WebSocket relay  │
                 └──────┬──────────┬───┘
                        │          │
                        ▼          ▼
              ┌───────────────┐  ┌──────────────────┐
              │ TimescaleDB   │  │ React Dashboard  │
              │ (time-series) │  │ (browser, live)  │
              └───────────────┘  └──────────────────┘
```

Each block is a discrete service in `docker-compose`. Communication boundaries are explicit. The architecture is intentionally portable: replacing Mosquitto with AWS IoT Core, FastAPI with ECS Fargate, and TimescaleDB with RDS or Timestream produces the production AWS topology documented in `docs/AWS_DEPLOYMENT.md`.

---

## 6. Data contract

This section defines the shape of data flowing through the system. Implementation must conform to these schemas; tests in `tests/contract/` verify compliance.

### 6.1 Telemetry payload (MQTT publish)

Published by edge devices (or the simulator) to MQTT topic `factory/{site}/{bay}/{cell}/{device_id}/{tag}`.

```json
{
  "schema_version": "1.0",
  "timestamp": "2026-05-03T16:42:13.500Z",
  "device_id": "cnc-07",
  "tag": "spindle_temp_c",
  "value": 187.4,
  "quality": "good",
  "metadata": {
    "unit": "celsius",
    "site": "merritt-island",
    "bay": "bay-3",
    "cell": "machining-2"
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Currently `"1.0"`. Reserved for future evolution. |
| `timestamp` | ISO 8601 string, UTC | yes | Source-of-truth time. Producers must include. |
| `device_id` | string | yes | Lowercase, hyphenated. Unique within site. |
| `tag` | string | yes | Lowercase snake_case. Unit suffix encouraged (`_c`, `_psi`, `_a`). |
| `value` | number \| boolean | yes | Numeric for analog, boolean for digital. |
| `quality` | enum | yes | `good` \| `uncertain` \| `bad` \| `stale` |
| `metadata.unit` | string | yes | Free-form unit label. |
| `metadata.site`, `bay`, `cell` | string | yes | Mirror the topic hierarchy. |

### 6.2 Alarm event

Emitted by the ingest service on alarm state change. Persisted to the `alarms` table and pushed over WebSocket.

```json
{
  "alarm_id": "alm_01HQX2T9R7K8YJWX5MVZP3D4QF",
  "device_id": "cnc-07",
  "tag": "spindle_temp_c",
  "current_value": 247.8,
  "expected_range": [60.0, 200.0],
  "severity": "high",
  "state": "raised",
  "raised_at": "2026-05-03T16:42:14.012Z",
  "acknowledged_at": null,
  "acknowledged_by": null,
  "cleared_at": null,
  "detector": "z_score_and_isolation_forest"
}
```

| Field | Type | Notes |
|---|---|---|
| `alarm_id` | ULID string | Stable identifier across state transitions. |
| `severity` | enum | `low` \| `medium` \| `high` \| `critical` |
| `state` | enum | `raised` \| `acknowledged` \| `cleared` |
| `detector` | string | Which rule(s) fired. |

### 6.3 WebSocket envelope (server → dashboard)

All server-to-client real-time messages share an envelope:

```json
{
  "type": "telemetry",
  "timestamp": "2026-05-03T16:42:13.500Z",
  "payload": { /* type-specific */ }
}
```

`type` is one of: `telemetry`, `alarm`, `machine_status`, `system_status`.

- `telemetry` payload: a single telemetry record (§6.1).
- `alarm` payload: a single alarm event (§6.2).
- `machine_status` payload: `{ device_id, status: "healthy" | "degraded" | "alarming", reason }`.
- `system_status` payload: dependency health summary (mirrors `/health` endpoint).

### 6.4 Database schema (logical)

Three primary tables. Full DDL in `db/schema.sql`.

- **`telemetry`** (TimescaleDB hypertable, partitioned by time)
  `time`, `site`, `bay`, `cell`, `device_id`, `tag`, `value`, `quality`, `unit`
- **`alarms`** (regular Postgres table)
  `alarm_id` (PK), `device_id`, `tag`, `current_value`, `lower_bound`, `upper_bound`, `severity`, `state`, `raised_at`, `acknowledged_at`, `acknowledged_by`, `cleared_at`, `detector`
- **`machines`** (regular Postgres table)
  `device_id` (PK), `site`, `bay`, `cell`, `type`, `display_name`, `normal_ranges` (JSONB), `floor_position` (JSONB: `x`, `y`, `w`, `h`)

Retention: `telemetry` rows older than 7 days are dropped by a scheduled job. `alarms` and `machines` are not auto-pruned.

---

## 7. Functional requirements

### 7.1 Edge simulation layer

- **FR-1.1** — The system SHALL include simulated edge devices representing at least four equipment types: CNC machine, friction stir welder, autoclave, and cleanroom environmental sensor.
- **FR-1.2** — Each simulated device SHALL publish telemetry to MQTT at a configurable interval (default: 1 second).
- **FR-1.3** — Telemetry topics SHALL follow a Sparkplug-B-inspired hierarchical naming convention: `factory/{site}/{bay}/{cell}/{device_id}/{tag}`.
- **FR-1.4** — The simulator SHALL be driven by a declarative YAML configuration (`simulator.yaml`) defining the factory layout, devices, sensor tags, normal operating ranges, and fault injection scenarios.
- **FR-1.5** — The system SHALL expose a fault injection endpoint that, when triggered, causes a specified device to emit telemetry outside its normal range, demonstrating end-to-end alarm propagation.

### 7.2 Edge gateway

- **FR-2.1** — A dedicated edge gateway service SHALL sit between simulated devices and the MQTT broker.
- **FR-2.2** — When the broker connection is healthy, the gateway SHALL forward messages with negligible added latency (<100ms p95).
- **FR-2.3** — When the broker connection is lost, the gateway SHALL buffer incoming messages to a local SQLite store.
- **FR-2.4** — On reconnection, the gateway SHALL drain the buffer in chronological order while continuing to accept new messages.
- **FR-2.5** — The gateway SHALL emit observable status (`connected`, `buffering`, `draining`) for verification.

### 7.3 Ingest service

- **FR-3.1** — The ingest service SHALL subscribe to all `factory/#` topics on the MQTT broker.
- **FR-3.2** — The ingest service SHALL validate each message against the §6.1 schema and reject malformed payloads with a logged structured error.
- **FR-3.3** — Valid telemetry SHALL be persisted to the `telemetry` hypertable.
- **FR-3.4** — The ingest service SHALL run anomaly detection on each incoming message (see §7.5) and emit alarm events when triggered.
- **FR-3.5** — The ingest service SHALL push real-time updates (telemetry deltas, alarms, machine status changes) to connected dashboard clients via WebSocket using the §6.3 envelope.

### 7.4 Persistence

- **FR-4.1** — Telemetry SHALL be stored in a TimescaleDB hypertable partitioned by time.
- **FR-4.2** — The schema SHALL use a tag-based data model (§6.4) rather than per-sensor columns.
- **FR-4.3** — Alarms SHALL be stored in a separate table with full lifecycle state and timestamps for each transition.
- **FR-4.4** — A retention policy SHALL drop raw telemetry older than 7 days; aggregations beyond that window are out of scope for v.1.

### 7.5 Anomaly detection

- **FR-5.1** — The system SHALL implement two-layer anomaly detection:
  - Layer 1: Rolling z-score on each tag with a configurable window (default: 60 seconds) and threshold (default: 3σ).
  - Layer 2: Isolation Forest classifier (scikit-learn) trained on synthetic baseline data, used as a second-opinion signal.
- **FR-5.2** — An alarm SHALL be raised only when both layers agree, reducing false positives. (Layer 1 alone is configurable for higher sensitivity.)
- **FR-5.3** — Each alarm SHALL conform to the §6.2 schema.

### 7.6 Dashboard

- **FR-6.1** — Factory Floor Map: top-down SVG layout showing all bays, cells, and machines with live status indicators (green = healthy, yellow = degraded, red = alarming). Clicking a machine drills into its detail view.
- **FR-6.2** — Machine Detail View: live charts for the selected device's sensor tags (last 5 minutes streaming), current job display, active alarms list, and a displayed OEE strip (Availability, Performance, Quality — values seeded from simulator config; not computed from first principles).
- **FR-6.3** — Alarm Console: a live feed of all current alarms with severity badges, an "acknowledge" action, and a history view of recently cleared alarms.
- **FR-6.4** — Fleet Overview header strip: three KPIs visible on every page — total machines online, active alarm count, last-hour throughput.
- **FR-6.5** — Fault Injection control: a discrete UI element allowing the user to trigger one of the predefined fault scenarios from `simulator.yaml`.
- **FR-6.6** — All real-time updates SHALL arrive over WebSocket; the dashboard SHALL NOT poll.

---

## 8. Non-functional requirements

- **NFR-1** — Deployment: the entire stack SHALL be runnable locally with `docker compose up` and shall require no manual configuration beyond an optional `.env` file.
- **NFR-2** — Hosting: v.1 SHALL be deployed to a public URL on Fly.io.
- **NFR-3** — Code quality: every service SHALL have a test suite. Test coverage targets: ≥70% for the ingest service, ≥60% overall. Tests SHALL run in CI on every push.
- **NFR-4** — Documentation: the repository SHALL contain at minimum: `README.md`, `SPEC.md` (this file), `PLAN.md`, `DECISIONS.md`, `CLAUDE.md`, `KNOWN_ISSUES.md`, `docs/AWS_DEPLOYMENT.md`, and `docs/SMOKE_TEST.md`.
- **NFR-5** — Observability: every service SHALL log structured events to stdout. The ingest service SHALL expose a `/health` endpoint returning structured JSON dependency status.
- **NFR-6** — Performance (v.1 target, not a guarantee): the system SHALL handle 50 messages/second sustained across the simulator fleet without dropped telemetry or dashboard lag visible to a human observer.
- **NFR-7** — Status visibility: the dashboard SHALL display current system health (broker, database, ingest) such that a degraded state is never invisible to the user.

---

## 9. Tech stack

| Component | Choice | Reason |
|---|---|---|
| MQTT broker | Mosquitto | Industry standard, reference implementation |
| Topic naming | Sparkplug-B-inspired | Domain credibility, structured hierarchy |
| Edge simulation | Python | Speed of development, library ecosystem |
| Edge gateway | Python + SQLite | Simple, durable, easy to defend |
| Ingest service | FastAPI (Python, async) | Named in target role; team's stack |
| Real-time push | WebSocket via FastAPI | Standard modern pattern |
| Time-series DB | TimescaleDB | Postgres-native; team stays in SQL |
| ML anomaly | scikit-learn IsolationForest | Lightweight, defensible, resume tie-in |
| Frontend | React + TypeScript | Named in target role; primary stack |
| Charts | Recharts | Familiar, sufficient for v.1 |
| Packaging | docker-compose | Single-command spin-up |
| Hosting | Fly.io | Multi-service Docker, long-lived connections |
| CI | GitHub Actions | Zero-config for public repos |

---

## 10. Failure modes and recovery

This section describes how the system behaves when things go wrong. Each scenario is verified by an integration test or manual smoke test step.

- **FM-1 — MQTT broker crashes or restarts.** Edge gateway detects disconnection within 10 seconds and begins buffering to local SQLite. On reconnect, the gateway drains the buffer in chronological order while continuing to accept new messages. Ingest service reconnects automatically with exponential backoff. Dashboard displays a "broker reconnecting" indicator until restored. No telemetry is lost for buffer durations under one hour at default rates.
- **FM-2 — TimescaleDB crashes or becomes unreachable.** Ingest service catches connection errors and queues writes in a bounded in-memory buffer (~10,000 messages). On database return, the queue drains. If the queue exceeds its bound, oldest messages are dropped with a logged warning. The dashboard displays "history unavailable" on detail charts; the live stream continues.
- **FM-3 — Ingest service crashes.** Mosquitto retains messages on durable subscriptions. On ingest restart, the service resubscribes and resumes processing. Dashboard WebSocket clients auto-reconnect with exponential backoff (5s → 30s max). Acknowledged-but-not-cleared alarms remain in the database and reload on dashboard reconnect.
- **FM-4 — Edge gateway crashes.** Devices continue publishing; messages are lost during gateway downtime. On gateway restart, normal forwarding resumes. This is a known v.1 limitation: simulated devices have no buffering of their own. Real OPC UA / Sparkplug B devices in production would buffer at the device level. Documented in `KNOWN_ISSUES.md`.
- **FM-5 — Malformed telemetry payload.** Ingest validation rejects the payload and logs a structured error including the schema mismatch detail and the offending `device_id`. The bad payload does not crash the service or block valid messages from other devices. Repeated failures from the same device increment a counter visible in the system status.
- **FM-6 — Dashboard browser tab loses network.** WebSocket close event fires. Dashboard reconnect logic retries every 5 seconds, with exponential backoff to a 30-second maximum. On reconnect, the dashboard fetches recent state via a REST endpoint to fill the gap. The user sees a transient "reconnecting" indicator.
- **FM-7 — Anomaly detector emits a false positive.** Operator acknowledges in the console; alarm moves to history. The two-layer detector design (z-score AND isolation forest) reduces but does not eliminate false positives. Per-device sensitivity tuning is deferred to v.2.
- **FM-8 — Disk fills (TimescaleDB volume).** Retention policy drops telemetry older than 7 days, scheduled hourly. In v.1, there is no automated alerting on volume usage; this is documented in `KNOWN_ISSUES.md`. A production deployment would use cloud-managed storage with autoscaling and CloudWatch (or equivalent) alarms on volume thresholds.

---

## 11. Testing strategy

The system uses a layered verification strategy. The goal is not 100% coverage; it is high confidence on the paths a reviewer will exercise, with explicit honesty about what isn't tested.

### 11.1 Unit tests

Targeted at components most likely to break silently:

- Telemetry and alarm schema validators
- Rolling z-score detector (boundary cases, NaN handling, empty windows)
- Isolation Forest wrapper (model loading, prediction shape)
- Gateway store-and-forward state machine (transition matrix, buffer drain order)
- Alarm lifecycle transitions (legal and illegal)

Coverage target: ≥70% on the ingest service, ≥60% overall.

### 11.2 Integration tests

Covering critical end-to-end paths:

- Message round-trip: device publishes → broker → ingest → DB → WebSocket → asserts receipt
- Alarm round-trip: fault injection → detection → DB write → WebSocket emit
- Gateway recovery: kill broker, verify buffering, restart broker, verify drain order
- WebSocket reconnect: kill ingest, verify dashboard handles gracefully on restart

### 11.3 Acceptance script

A single executable script (`scripts/acceptance_test.sh`) that boots the docker-compose stack, waits for services to become healthy, and runs through the §12 acceptance criteria programmatically. Exits non-zero on any failure. Runs in CI on every push to main. Doubles as a reviewer-readable artifact: a concrete answer to "how do you know the system works?"

### 11.4 Manual smoke test

Documented in `docs/SMOKE_TEST.md`. Approximately 15 items, each ~30 seconds. Covers visual rendering, browser-specific concerns, and the reviewer-likely interaction sequence. Run after every deployment.

### 11.5 Health and status visibility

Each service exposes `/health` returning structured JSON with dependency status. The dashboard footer displays a system status widget reflecting the ingest service `/health`. A degraded system shows what is degraded — never a blank screen or silent failure.

### 11.6 Out of scope for v.1 testing

- Load testing beyond the NFR-6 target of 50 msg/s
- Cross-browser testing (Chrome only)
- Long-duration soak testing (>24-hour runs not verified)
- Security testing (no authentication surface to test)
- Mobile / responsive testing

These are listed in `KNOWN_ISSUES.md` alongside any other limitations discovered during development.

---

## 12. Acceptance criteria

The v.1 build is considered complete when all of the following are demonstrably true at the deployed URL:

1. The factory floor map renders with at least 6 distinct simulated machines.
2. All machines emit live telemetry visible as updating sparklines in the detail view.
3. An operator can drill from the floor map into any machine and back, with no full page reload.
4. Triggering the Fault Injection control causes:
   a. The targeted machine's status indicator to change color within 5 seconds
   b. A new alarm to appear in the Alarm Console within 5 seconds
   c. The relevant sensor's chart to show the anomalous reading
5. Acknowledging an alarm in the console moves it from the active list to history.
6. Killing and restarting the Mosquitto container demonstrates the edge gateway's store-and-forward behavior: no telemetry lost, buffered messages drain on reconnect.
7. The Fleet Overview KPIs update in real time as conditions change.
8. The repository contains all documents listed in NFR-4.
9. CI is green on the main branch.
10. Total cold start (`fly deploy` to first telemetry visible) is under 90 seconds.

---

## 13. Out of scope (deliberate)

The following are explicitly NOT in v.1. Each is a real feature of a production IIoT platform; each was cut for time-budget reasons documented in `DECISIONS.md`.

- Authentication, authorization, or any user model
- Multi-tenant or multi-site isolation
- Historical Replay view (time-window scrubbing)
- Full OEE computation from production schedule and cycle-time data
- MTBF, MTTR, or any reliability metric requiring incident history
- OPC UA protocol implementation (mentioned in §14 as the real-world upstream)
- AWS-native deployment (architecture documented; deployment deferred)
- Mobile-responsive layout
- Internationalization

---

## 14. Real-world context

In a production deployment, the data flow upstream of MQTT typically looks different from the simulated edge devices in this prototype. Real CNC machines, PLCs, and process equipment most often speak OPC UA, with an edge gateway translating OPC UA reads into MQTT publishes. The architecture in §5 is compatible with this pattern: a real OPC UA → MQTT bridge would replace the simulator scripts without changes to anything downstream.

Similarly, in production:

- The MQTT broker would be AWS IoT Core or a hardened Mosquitto cluster
- The ingest service would scale horizontally on ECS Fargate
- TimescaleDB would be a managed RDS instance or replaced by Amazon Timestream
- The React app would be served from CloudFront with S3 origin
- WebSocket connections would terminate at an Application Load Balancer

This mapping is documented in detail in `docs/AWS_DEPLOYMENT.md`.

---

## 15. Roadmap (v.2 and beyond)

Documented here so the v.1 cuts are visible as deliberate, not accidental.

**v.2 candidates:**

- Historical Replay view with variable-speed playback
- OEE computed from production schedule + cycle time + quality data
- Real OPC UA bridge alongside the MQTT path
- AWS-native deployment with IoT Core, ECS, and Timestream
- Operator authentication with role-based views
- Mobile-responsive layout for tablet use on the floor

**v.3 candidates:**

- Predictive maintenance using time-series anomaly models trained on historical data
- Multi-site federation with regional aggregation
- Integration with MES (Manufacturing Execution System) for job traceability
- Digital twin synchronization

---

## 16. Methodology note

This specification was authored before any application code was written. It serves as the contract that constrains the AI-assisted implementation phase. The development workflow follows a spec-driven approach:

1. **Specify** (this document)
2. **Plan** (`PLAN.md` — architectural decisions, data models, API contracts, build sequence, acceptance script content)
3. **Implement** (Claude Code, in VS Code, against the spec and plan)
4. **Verify** (test suite + acceptance script + manual smoke test)

The `CLAUDE.md` file in the repository root provides project-level rules and conventions to the coding agent. `DECISIONS.md` logs material architectural choices and their tradeoffs in ADR-style entries.

This methodology is itself part of what the project demonstrates: working with AI coding agents at a senior level is a discipline of context engineering, not just prompting.

### What a v.1.5 spec would add

A production-grade specification at the next level of rigor would also include: a formal AsyncAPI document for the WebSocket protocol, an OpenAPI spec for any REST endpoints, an FMEA covering systematic failure analysis (this v.1 covers the most important scenarios in §10 but does not exhaust the failure space), defined SLOs and error budgets, a full security threat model with mitigations, a data lifecycle and PII posture statement, a dependency version pinning policy, a verification matrix mapping each FR to its test, and an explicit assumptions section. These are deferred for the v.1 prototype but are the natural next layer of rigor and would be added before production deployment.
