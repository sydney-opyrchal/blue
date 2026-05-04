# KNOWN ISSUES

Honest list of v.1 limitations. Some are deliberate cuts (cross-referenced to `SPEC.md` §13 and `DECISIONS.md`); some are real gaps that haven't been addressed yet. This file is updated during development as new gaps surface.

## v.1 implementation status (spec → code delta)

The spec was written first and aims at a production-grade prototype. The v.1 build hit time before reaching every part of it. This section is the honest delta between what `SPEC.md` and `DECISIONS.md` describe and what is actually running in the repo. Items marked deferred are not failures — they are scope cuts to land a working end-to-end demo within budget. Each is queued for v.1.5.

### What is fully implemented

- MQTT broker (Mosquitto) with the docker-compose stack — ADR-001 ✓
- FastAPI ingest service with paho-mqtt + asyncpg in a single async process — ADR-004 ✓
- TimescaleDB hypertable for telemetry, with a tag-based row layout — ADR-003 (schema simplified, see below) ✓
- WebSocket fan-out to React clients with a typed message envelope — ADR-009 (envelope shape simplified, see below) ✓
- React dashboard with live factory-floor SVG, asset detail with live charts, alarm console with acknowledge, fleet table, and alarm history — FR-6.1 / 6.2 / 6.3 / 6.4 ✓
- Anomaly injection in the simulator producing realistic alarms end-to-end ✓
- No-auth posture documented and intentional — ADR-011 ✓
- Spec-first hand-rolled docs (SPEC, PLAN, CLAUDE, DECISIONS, KNOWN_ISSUES) — ADR-014 ✓
- Pydantic v2 wire-format contracts (SPEC §6.1, §6.2, §6.3) — ADR-002 (schema definition only; not yet on the ingest path)
- Rolling z-score and Isolation Forest detectors as standalone, unit-tested modules — ADR-006 (modules ready; not yet on the ingest path)
- Alarm lifecycle state machine with ULID identifiers — ADR-008 (wired into `evaluate_alarm`; alarms persist with ULID `alarm_id` PKs)
- Test suite (73 tests, 100% coverage on contracts / detectors / alarms; smoke tests for `/health` and the `evaluate_alarm` wire-up) — ADR-013, NFR-3
- Multi-stage Dockerfile, Mosquitto Dockerfile, and four-app Fly.io deployment topology — ADR-012, NFR-2

### What is partially implemented (simplified from spec)

- **Telemetry payload schema** (ADR-002, SPEC §6.1). Code uses `{ts, asset_id, metric, value}`. Spec specifies additionally `schema_version`, `quality`, and a `metadata` block with `unit`, `site`, `bay`, `cell`. Forward-compat fields not yet emitted. v.1.5 priority.
- **MQTT topic shape** (SPEC §6.1). Code uses `factory/{area}/{cell}/{asset_id}/{metric}` (4 levels). Spec specifies `factory/{site}/{bay}/{cell}/{device_id}/{tag}` (5 levels — `site` is missing). The multi-site case is structurally available but not exercised. v.1.5 priority.
- **Database schema** (SPEC §6.4). The `readings` hypertable carries `(ts, asset_id, metric, value)`. Spec specifies `(time, site, bay, cell, device_id, tag, value, quality, unit)`. v.1.5 priority.
- **Alarm record** (ADR-008, SPEC §6.2). ULID `alarm_id` is implemented and persisted as the alarms table PK. The full lifecycle in one row (`acknowledged_at`, `cleared_at` columns) is not — the DB only records the raise event; acknowledgements and clears mutate the in-memory `Alarm` object and broadcast over WebSocket but are not persisted. v.1.5 priority.
- **WebSocket envelope** (ADR-009, SPEC §6.3). Spec specifies `{type, timestamp, payload}` with `type` ∈ `{telemetry, alarm, machine_status, system_status}`. Code uses `{type, ...fields}` with `type` ∈ `{snapshot, reading, alarm_raised, alarm_cleared, alarm_acked}`. The typed-envelope discipline holds; the exact shape differs. v.1.5 priority.
- **Frontend stack** (ADR-010). Implemented as React + JSX + uPlot. Spec called for React + TypeScript + Recharts. uPlot was substituted for charts because the per-metric live sparkline grid is denser than Recharts handles cleanly at 2 Hz; TypeScript was deferred for build velocity. README reflects the as-built stack; ADR-010 is being updated.

### v.1 ingest path: simpler than the modules describe

Two of the new modules — `app/contracts.py` and the pair under `app/detectors/` — are implemented and unit-tested but not yet wired into the running ingest service. The third module, `app/alarms/lifecycle.py`, is wired (see "What is fully implemented" above).

Specifically, in the running v.1 demo:
- The MQTT subscriber parses incoming messages as raw JSON dicts rather than validating against the `Telemetry` Pydantic model.
- Alarms are raised on simple redline thresholds (`redline_high` / `redline_low` in `assets.py`) rather than the two-layer z-score + Isolation Forest gate described in ADR-006.

The remaining wire-up is the next chunk of v.1.5 work. Doing it correctly under the v.1 budget — and shipping a working demo — meant landing the modules with high test coverage first, then wiring them in incrementally. The contracts and detectors wire-up is mechanical; the modules are designed to drop in the same way the lifecycle module did.

### What is specified but not yet implemented in v.1

These are the real gaps. Each is named in the spec and each is genuinely on the v.1.5 list — not retired, not dropped. The v.1 build runs without them; production would not.

- **Dedicated edge gateway with SQLite store-and-forward** (ADR-005, FR-2). The single most credible IIoT pattern in the spec. v.1's simulator publishes directly to Mosquitto; there is no separate gateway service, no SQLite buffer, and no `connected → buffering → draining` state machine. The spec describes this in detail because it is the right architecture; the implementation will follow in v.1.5. **High v.1.5 priority.**
- **Two-layer anomaly detection: rolling z-score + Isolation Forest** (ADR-006, FR-5). v.1 alarms use static redline thresholds only (`redline_high` / `redline_low` per metric, defined in `backend/app/assets.py`). The two-layer ML detector specified in ADR-006 — z-score plus scikit-learn `IsolationForest`, both must agree — is not yet wired in. The redline approach is honest about what it is (a baseline) and produces real alarms, but it is not the detector specified. **High v.1.5 priority.**
- **Declarative `simulator.yaml`** (ADR-007). The asset fleet is defined in `backend/app/assets.py` as a Python list. The YAML conversion is a near-mechanical transformation and is queued.
- **`/faults/inject` endpoint** (FR-1.5). The simulator triggers anomalies on its own internal random schedule; there is no externally-triggered fault. Adding the HTTP endpoint is small (~30 lines) and is queued.
- **Acceptance script** (`scripts/acceptance_test.sh`, SPEC §11.3, §12). Not yet written.
- **CI workflow** (`.github/workflows/`, NFR-3, SPEC §12 criterion 9). Not yet present.
- **Live Fly.io deployment** (ADR-012, NFR-2). Live at https://forge-apis.fly.dev
  (FastAPI + bundled SPA, public). Internal-only services: forge-broker,
  forge-dbs, forge-sim. CI / GitHub Actions integration with the deploy is
  queued for v.1.5.
- **`docs/AWS_DEPLOYMENT.md`** (SPEC §14, referenced from README and several ADRs). Not yet written. The mapping is well-understood (Mosquitto → AWS IoT Core, FastAPI → ECS Fargate, Timescale → RDS or Timestream, React → CloudFront/S3, WebSocket → ALB) but is not yet captured in the doc.
- **`docs/SMOKE_TEST.md`** (SPEC §11.4). Not yet written.

The principle behind keeping all of these visible in `SPEC.md` and `DECISIONS.md` rather than retroactively trimming the spec to match the code: **the spec is the design, not the changelog.** A reviewer reading the spec sees what the system is meant to be; reading this file sees what shipped in v.1 and what is queued. Hiding the gap by editing the spec down to match the code would lose information, not gain credibility.

## Deliberate v.1 cuts

These are out of scope by design. Each is named in `SPEC.md` §13 and / or `§15` (roadmap).

- **No authentication or authorization.** Broker is anonymous; ingest API and WebSocket are unauthenticated and plaintext. ADR-011.
- **No multi-tenant or multi-site isolation.** Schema supports `site` for forward compatibility; runtime is single-site.
- **No Historical Replay view.** Only live data and the alarm history list (last 200) are exposed in v.1.
- **OEE is displayed, not computed.** Availability / Performance / Quality values are seeded from `simulator.yaml`. Real OEE requires production schedule and cycle-time data the simulator doesn't model.
- **No MTBF / MTTR / reliability metrics.** Requires multi-incident history; deferred to v.2.
- **No OPC UA upstream.** The simulator stands in. A real OPC UA → MQTT bridge is a v.2 candidate (SPEC §14, §15).
- **No AWS-native deployment.** Documented in `docs/AWS_DEPLOYMENT.md` as the production topology; v.1 deploys to Fly.io.
- **No mobile / responsive layout.** Chrome desktop only. Verified at common laptop resolutions.
- **No internationalization.** English only.
- **Sparkplug-B-inspired, not compliant.** Topic naming follows the spec; payload is JSON with `schema_version`, not the binary protobuf format with birth/death certificates. ADR-002.

## Real v.1 gaps (non-deliberate, accepted within budget)

These are limitations of the implementation rather than scope choices. Each maps to an FM in SPEC §10 where applicable.

- **FM-4: edge gateway crash drops in-flight messages.** Simulated devices have no buffering of their own; messages published while the gateway is down are lost. Real OPC UA / Sparkplug-B devices buffer at the device level; the simulator does not. Mitigation: the gateway restart is fast and the simulator runs at low rates.
- **FM-8: no automated alerting on TimescaleDB volume usage.** Retention drops telemetry > 7 days, but if write rates spike or retention fails, the disk fill goes silent until the smoke test catches it. A production deployment would alert on volume thresholds via CloudWatch or equivalent.
- **No per-device anomaly-detector tuning.** The two-layer detector uses one z-score window (60s) and one Isolation Forest contamination parameter for every tag. Per-tag tuning is a v.2 candidate (FM-7).
- **WebSocket fan-out re-encodes per client.** Acceptable at the v.1 client count (a handful of operators); not acceptable above ~50 concurrent clients. Mitigation listed in SPEC §10 scaling notes.
- **Bounded in-memory buffer in ingest under DB outage.** ~10,000 messages; oldest dropped on overflow with a logged warning (FM-2). Acceptable for short outages, lossy for long ones.
- **No persisted alarm state transitions.** The alarms table records the raise event only (`alarm_id`, `device_id`, `tag`, `severity`, `current_value`, `raised_at`, `detector`). Acknowledgements and clears mutate the in-memory `Alarm` object and broadcast over WebSocket but are not written back to the DB. Restarting the ingest service loses ack state on currently-active alarms. v.1.5: persist `acknowledged_at` / `cleared_at` per ADR-008.

## Testing gaps (v.1)

Per SPEC §11.6:

- **Load testing only verified up to NFR-6 (50 msg/s).** Behavior above this is undefined.
- **Cross-browser testing not performed.** Chrome only.
- **Long-duration soak testing not performed.** Runs over ~24 hours not verified; potential memory growth in the WS fan-out or detector ring buffers is unknown.
- **No security testing.** No authentication surface to test in v.1.
- **No mobile / responsive testing.**

## Operational gaps

- **No backup / restore for TimescaleDB.** Docker volume only; if the volume is lost, history is lost. Production answer is managed Postgres with point-in-time recovery.
- **No structured log aggregation.** Logs go to stdout per service; viewing across services means `docker compose logs` or Fly's log stream. No central aggregator.
- **No metrics or tracing.** `/health` is the only observability surface. A production deployment would add Prometheus metrics and OpenTelemetry traces.
