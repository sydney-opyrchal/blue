# New Glenn Factory — IIoT Monitoring Platform

A vertical-slice Industrial IoT monitoring platform inspired by the manufacturing floor at Blue Origin's Exploration Park rocket factory in Merritt Island, FL. Simulates a fleet of factory floor assets (friction stir welders, automated fiber placement machines, autoclaves, 5-axis mills, clean rooms, bridge cranes) and provides real-time visibility, alarm management, and historical analytics.

> All asset data is simulated. Personal project, not affiliated with Blue Origin.

## Live demo

`https://forge-apis.fly.dev` — public FastAPI + React SPA. The simulator and
broker run on internal-only Fly apps (`forge-sim`, `forge-broker`,
`forge-dbs`). Telemetry flows continuously; the simulator's internal anomaly
schedule produces real alarms every few minutes.

Open the URL, click any machine on the floor map for live charts, and watch
the Active Alarms rail for the next anomaly.

## Where to read what

- **[SPEC.md](./SPEC.md)** — what this is, who it's for, acceptance criteria, architecture, simulated fleet, vocabulary, what's out of scope.
- **[PLAN.md](./PLAN.md)** — implementation plan: repo layout, build sequence, deployment plan, acceptance script structure.
- **[DECISIONS.md](./DECISIONS.md)** — ADR-style log of the load-bearing calls (why MQTT, why Timescale, why JSON over protobuf, etc.) and what was rejected. Each ADR carries a v.1 implementation status.
- **[KNOWN_ISSUES.md](./KNOWN_ISSUES.md)** — honest accounting of v.1 implementation status, deliberate cuts, real gaps, and operational limits.
- **[CLAUDE.md](./CLAUDE.md)** — rules of engagement for the agent working in this repo.

If you're reviewing this in under 10 minutes, read SPEC.md and KNOWN_ISSUES.md.

## Stack

Mosquitto (MQTT) → FastAPI (paho-mqtt + asyncpg) → TimescaleDB, with a React + Vite + uPlot client over WebSockets. Topic shape follows ISA-95 / Sparkplug-B; payloads are JSON. Rationale in DECISIONS.md.

## Running it

Prereqs: Docker + Docker Compose, Python 3.11+, Node 18+.

```bash
# 1. Broker + database
docker compose up -d

# 2. Ingest service
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 3. Simulator (separate terminal)
cd backend && source .venv/bin/activate
python -m app.simulator

# 4. Frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Project structure

```
newglenn-iiot/
├── README.md                  # front door (this file)
├── SPEC.md                    # what + why + acceptance criteria
├── PLAN.md                    # implementation plan + build sequence
├── DECISIONS.md               # ADR log (each ADR carries v.1 status)
├── KNOWN_ISSUES.md            # spec → code delta + deliberate cuts
├── CLAUDE.md                  # agent rules
├── docker-compose.yml         # Mosquitto + TimescaleDB (local)
├── Dockerfile.backend         # multi-stage: Vite build + FastAPI runtime
├── Dockerfile.broker          # Mosquitto with baked-in config
├── fly.api.toml               # Fly app: forge-apis (ingest + bundled SPA)
├── fly.broker.toml            # Fly app: forge-broker (Mosquitto)
├── fly.db.toml                # Fly app: forge-dbs (TimescaleDB + volume)
├── fly.sim.toml               # Fly app: forge-sim (simulator)
├── mosquitto/config/          # Broker config
├── backend/
│   ├── requirements.txt
│   ├── pytest.ini             # coverage scoped to spec-aligned modules
│   ├── app/
│   │   ├── assets.py          # Asset fleet (Python list; YAML in v.1.5)
│   │   ├── simulator.py       # Edge gateway simulator
│   │   ├── main.py            # FastAPI ingest + WS + REST
│   │   ├── contracts.py       # Pydantic v2 wire-format models (SPEC §6)
│   │   ├── detectors/         # z-score + IsolationForest (SPEC §7.5)
│   │   │   ├── zscore.py
│   │   │   └── isoforest.py
│   │   └── alarms/            # Alarm lifecycle state machine (SPEC §6.2)
│   │       └── lifecycle.py
│   └── tests/                 # 69 unit tests, 100% on contracts/detectors/alarms
│       ├── test_contracts.py
│       ├── test_zscore.py
│       ├── test_isoforest.py
│       └── test_alarm_lifecycle.py
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        └── App.jsx            # Single-file React UI (uPlot)
```
