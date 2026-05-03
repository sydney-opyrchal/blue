# KNOWN ISSUES

Honest list of v.1 limitations. Some are deliberate cuts (cross-referenced to `SPEC.md` §13 and `DECISIONS.md`); some are real gaps that haven't been addressed yet. This file is updated during development as new gaps surface.

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
- **No event-sourced alarm audit trail.** Alarms carry their full lifecycle in one row (ADR-008). Reconstruction of historical state changes beyond `raised_at` / `acknowledged_at` / `cleared_at` is not possible.

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

## To be filled during build

This section is a placeholder for issues discovered while implementing the spec. Every item here is something that surprised the build and is worth recording so a reviewer doesn't have to guess what's known vs. unknown.

- _(none yet)_
