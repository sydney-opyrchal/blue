# SPEC — New Glenn Factory IIoT Monitoring Platform

## Problem

Rocket factories run a heterogeneous fleet of high-value assets (welders, autoclaves, mills, clean rooms, cranes). Operators need a single live view of fleet state and alarms; engineers need historical data for incident review. This project is a vertical-slice prototype of that view, modeled on the New Glenn manufacturing floor at Exploration Park.

Inputs are simulated. The goal is to demonstrate the system-design patterns — not to ship to production.

## Users

- **Operator** — watches the floor map, acknowledges alarms, drills into an asset when something goes red.
- **Engineer** — reviews historical tag data and alarm history after an event.
- **Maintenance** — (future) gets a mobile alarm feed.

Only the operator and engineer flows are in scope.

## Acceptance criteria

A reviewer should be able to:

1. `docker compose up -d`, start backend, start simulator, start frontend — and see live data within ~30 seconds.
2. See all 10 simulated assets on a floor map with status (nominal / alarm / offline).
3. Click any asset and see live multi-channel time-series with redline annotations.
4. See an alarm fire when a simulated metric crosses a redline, ack it, and watch it move to history.
5. Pull up the last 200 alarm events for incident review.
6. See header KPIs: fleet availability, online/offline counts, active alarm count.

## Functional features

- **Factory floor map** — top-down SVG layout, real-time per-asset status indicators.
- **Asset drilldown** — live multi-channel charts, redline annotations.
- **Alarm console** — live feed, ack workflow, persisted to Postgres.
- **Fleet overview** — table of all assets with status and tag counts.
- **Alarm history** — last 200 events.
- **Header KPIs** — availability, online/offline, active alarms.

## Architecture

```
┌─────────────────┐    MQTT     ┌──────────────────┐    SQL    ┌─────────────────┐
│  Edge Gateway   │  (1883)     │  FastAPI         │           │  TimescaleDB    │
│  (simulator.py) │ ──────────► │  Ingest Service  │ ────────► │  (hypertable)   │
│                 │             │                  │           └─────────────────┘
│  10 simulated   │             │  - Subscribes    │
│  assets @ 2 Hz  │             │  - Validates     │           ┌─────────────────┐
│  Sparkplug-ish  │             │  - Alarm logic   │ ──WS────► │  React Client   │
│  topic naming   │             │  - WS broadcast  │           │  (Vite)         │
└─────────────────┘             └──────────────────┘           └─────────────────┘
        │                                ▲
        ▼                                │
┌─────────────────┐  pub/sub     ┌──────────────────┐
│  Mosquitto      │ ◄──────────► │  Future: OPC UA  │
│  Broker         │              │  client, MES,    │
│  (Docker)       │              │  historian, ...  │
└─────────────────┘              └──────────────────┘
```

Topic convention: `factory/{area}/{cell}/{asset}/{metric}` — ISA-95 hierarchy, Sparkplug-B namespace shape, JSON payloads (see DECISIONS.md).

## Simulated fleet

| Asset | Type | Area | Real-world basis |
|---|---|---|---|
| FSW-01/02 | Friction Stir Welder | Tank Fab | New Glenn cryogenic tank barrels are FSW'd on the Ingersoll Mongoose. |
| AFP-01/02 | Automated Fiber Placement | Composites | Used for payload fairings and adapters. |
| AUTO-01 | Autoclave | Composites | Cures composite layups under temperature + pressure. |
| CNC-01/02 | 5-Axis Mill | Chem Proc | General-purpose precision machining. |
| CR-2CAT | Clean Room | 2CAT | Second Stage Cleaning and Testing — environmental control. |
| HIF-CRANE | Bridge Crane | HIF | Hardware Integration Facility — final assembly. |

Each asset publishes 2–4 metrics at 2 Hz with realistic nominals, drift, and noise. Anomalies are randomly injected to exercise alarm logic.

## Vocabulary

- **Tag** — a single named data point on an asset (e.g. `spindle_rpm`).
- **OPC UA** — standard protocol for talking to PLCs (Rockwell, Siemens). In production, an edge gateway speaks OPC UA to the PLC and republishes to MQTT.
- **Sparkplug B** — MQTT payload + topic spec for IIoT. Defines a unified namespace, birth/death certificates, and a binary payload format.
- **Unified Namespace (UNS)** — one MQTT broker as the central nervous system for the plant; every system reads from and writes to it.
- **Historian** — long-term store for tag data (PI, Ignition; TimescaleDB plays this role here).
- **MES** — Manufacturing Execution System; tracks work orders, routings, traceability. One layer above this dashboard in the ISA-95 stack.
- **OEE** — Overall Equipment Effectiveness = Availability × Performance × Quality.
- **Redline** — operating limit beyond which an alarm fires.

## Out of scope (deferred to roadmap)

These are intentionally not built in the time window:

1. Real OPC UA client (the simulator stands in).
2. Sparkplug-B binary protobuf payloads + birth/death certificates.
3. Edge buffering / store-and-forward.
4. Auth, mTLS, RBAC.
5. Anomaly detection beyond static redlines.
6. TimescaleDB continuous aggregates / compression policies.
7. Kafka in front of the historian.
8. MES integration / work-order overlay.
9. Mobile companion app.
10. Digital thread (per-serial traceability).

## Scaling notes

Current load: 10 assets × ~4 tags × 2 Hz ≈ 80 msg/s — fits a laptop. Real-plant scale (thousands of tags at 10–100 Hz) would hit:

- **DB writes** — switch single-row inserts to batched `COPY`; enable Timescale compression on chunks older than a day.
- **WebSocket fan-out** — current implementation re-encodes per client; at >50 operators, switch to one encoded buffer per tick or Redis pub/sub between API replicas.
- **MQTT** — Mosquitto handles tens of thousands of msg/s on one node; for HA, EMQX or HiveMQ in cluster mode.
