# New Glenn Factory — IIoT Monitoring Platform

A vertical-slice Industrial IoT monitoring platform inspired by the manufacturing floor at Blue Origin's Exploration Park rocket factory in Merritt Island, FL. Simulates a fleet of factory floor assets (friction stir welders, automated fiber placement machines, autoclaves, 5-axis mills, clean rooms, bridge cranes) and provides real-time visibility, alarm management, and historical analytics.

> All asset data is simulated. Personal project, not affiliated with Blue Origin.

## Where to read what

- **[SPEC.md](./SPEC.md)** — what this is, who it's for, acceptance criteria, architecture, simulated fleet, vocabulary, what's out of scope.
- **[DECISIONS.md](./DECISIONS.md)** — ADR-style log of the load-bearing calls (why MQTT, why Timescale, why JSON over protobuf, etc.) and what was rejected.
- **[CLAUDE.md](./CLAUDE.md)** — rules of engagement for the agent working in this repo.

If you're reviewing this in under 10 minutes, read SPEC.md and DECISIONS.md.

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
├── DECISIONS.md               # ADR log
├── CLAUDE.md                  # agent rules
├── docker-compose.yml         # Mosquitto + TimescaleDB
├── mosquitto/config/          # Broker config
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── assets.py          # Asset fleet definitions
│       ├── simulator.py       # Edge gateway simulator
│       └── main.py            # FastAPI ingest + WS + REST
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        └── App.jsx            # Single-file React UI
```
