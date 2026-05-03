# CLAUDE.md — agent rules for this repo

This is a 10-hour vertical-slice IIoT demo. Read SPEC.md for what's being built and DECISIONS.md for why the stack looks the way it does. This file is the rules of engagement when working in this repo.

## Project context

- Stack: Mosquitto, FastAPI (paho-mqtt + asyncpg), TimescaleDB, React + Vite + uPlot.
- One backend process: ingest + API + WS fan-out share an asyncio loop. paho-mqtt's thread bridges to the loop via `asyncio.run_coroutine_threadsafe`.
- One frontend file: `frontend/src/App.jsx`.
- Topic shape: `factory/{area}/{cell}/{asset}/{metric}`. JSON payloads.
- All asset data is simulated (`backend/app/simulator.py`).

## Scope discipline

Everything in SPEC.md "Out of scope" is **out of scope**. Do not:

- Add auth, TLS, or RBAC.
- Switch payloads to Sparkplug-B protobuf.
- Replace the simulator with a real OPC UA client.
- Introduce Kafka, Redis, or a second backend service.
- Add anomaly detection beyond the static redlines already in the asset definitions.
- Add Timescale continuous aggregates or compression policies.

If a change feels like it's reaching into one of these, stop and ask. The roadmap exists so the reviewer can see I know these are the next steps — not so they get half-built.

## Code style

- Backend: Python 3.11+, async-first. Use type hints. Don't add Pydantic models for things that are already validated by the topic-and-schema contract.
- Frontend: function components, hooks, no class components. No state library — `useState` / `useReducer` only. No CSS framework — inline styles or one CSS file.
- No comments that restate what the code does. Comments only for non-obvious *why* (the `run_coroutine_threadsafe` bridge is one).
- No premature abstraction. Three similar lines beats a helper.
- No backwards-compat shims, feature flags, or "removed X" comments. If something is gone, it's gone.

## Testing

- No test suite is in scope for the 10-hour build. If a test would catch a real bug under active development, write it; otherwise skip.
- "Did the UI actually work?" is verified by running the dev server and clicking through. Type-checks and lints don't substitute for that.

## Working with this repo

- Don't restructure the four root markdown files (README, SPEC, DECISIONS, CLAUDE). They earn their place.
- New decisions worth a paragraph go in DECISIONS.md as a new ADR; don't sprinkle them across files.
- New scope worth implementing goes in SPEC.md "Functional features" — and out of "Out of scope" — before any code is written.
- README is the front door. Keep it short — link to SPEC/DECISIONS rather than duplicating content.

## Things that are easy to get wrong

- The MQTT thread is not the asyncio loop. Anything that touches the DB or WS broadcast from inside a paho callback must go through `run_coroutine_threadsafe`.
- uPlot wants raw typed-array-ish data and re-renders are expensive — append, don't replace, on tick.
- TimescaleDB hypertables: don't `CREATE TABLE` without `create_hypertable(...)` after; you'll get a regular Postgres table and silently lose the time-series benefits.
