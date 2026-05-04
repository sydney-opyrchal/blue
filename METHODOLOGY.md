# Methodology

Forge is an AI-assisted build, intentionally and transparently. This document explains the discipline behind that — what the AI was asked to do, what the engineer did, and why the result is a credible v.1 prototype rather than a code-generation showcase.

The repo is the artifact of this process. If anything below sounds like a claim, the corresponding evidence is named so a reviewer can verify rather than take the claim on faith.

---

## The shape of the build

The implementation was generated through Claude Code sessions running against a hand-written specification, plan, and project conventions. The engineer (the author) acted as architect, decision-maker, and reviewer; the agent acted as implementation tooling. Every meaningful change was reviewed before commit. Every module has tests written alongside it.

The order was deliberate:

1. **Specify** before code. `SPEC.md`, `PLAN.md`, and `DECISIONS.md` were authored by hand before any application file existed. They define what the system is, why each load-bearing choice was made, and how the build sequences.
2. **Constrain the agent** with `CLAUDE.md`. The conventions document is read at the start of every session and bounds what the agent can do — required reading order, code style per language, anti-patterns, and ask-before triggers.
3. **Implement against the contract.** Claude Code generated the implementation against the spec, plan, and conventions. Sessions were directed; output was read; alternatives were rejected when they didn't match the conventions.
4. **Verify.** Every new module has tests. The pytest coverage gate is set at 70% on the modules under coverage; current coverage on the contracts, detectors, and alarm lifecycle modules is 100%.
5. **Track honestly.** `KNOWN_ISSUES.md` carries the delta between what the spec describes and what shipped in v.1. Hiding the gap would lose information; documenting it makes the design visible.

This is a sequence, not a workflow diagram. The artifacts are the contract; the agent is execution against the contract; the engineer is judgment about the contract.

---

## The five disciplines this repo demonstrates

### 1. Spec-first development

The contract documents — `SPEC.md`, `PLAN.md`, `DECISIONS.md`, `CLAUDE.md`, `KNOWN_ISSUES.md` — were authored before any application code was written. They are hand-written, not generated.

Why hand-written: a hand-rolled specification reads as thinking; a generated one reads as templates. For a project where the docs are part of the deliverable showing how the engineer reasons (see ADR-014), the act of writing them is part of the methodology, not a step around it.

Why before code: the spec is the contract that constrains the agent. Without a spec written first, an AI assistant has nothing to be consistent against, and its output drifts. With a spec written first, the agent's choices are bounded structurally rather than by hope. The spec is what makes the rest of the methodology credible.

Reference artifacts: `SPEC.md` (architecture, contracts, requirements, failure modes, acceptance criteria, methodology note in §16); `PLAN.md` (build sequence, deployment plan, risk register); `DECISIONS.md` (14 ADRs, each with status tagged to v.1 implementation reality).

### 2. Context engineering as the rules layer

`CLAUDE.md` is the project's rules document. It is read by the agent at the start of every session and constrains what the agent can do.

The file defines: required reading order before any work session begins, language-specific conventions (Python 3.12 with `ruff` and `mypy --strict` for the ingest service; TypeScript 5 with `strict: true`; pytest naming and structure), commit conventions (Conventional Commits with explicit scope tags), anti-patterns to avoid (premature abstraction, hidden state, silent failures, mocking what can be run), and ask-before triggers (any new dependency, any new top-level directory, any change to a SPEC requirement).

Why this matters: most engineers using AI assistants prompt opportunistically. The output reflects the prompt, not the project. CLAUDE.md is the structural answer to "how do I keep AI-generated code from drifting from the project's standards?" The agent's choices are bounded by a document the engineer wrote, not by hope.

Reference artifact: `CLAUDE.md` at the repo root, ~280 lines.

### 3. Test discipline alongside generation

Every new module in the v.1.5 module set has a corresponding test file. Coverage on those modules is 100%. The pytest configuration (`backend/pytest.ini`) enforces a 70% floor on the modules under coverage; running the suite below that threshold fails.

The tests were written alongside the modules during the same Claude Code sessions that produced them. They are not retrofitted. They cover boundary conditions explicitly: NaN handling in the z-score detector, empty windows, zero-variance windows, prior-window semantics (a regression-protecting test that ensures an anomaly doesn't pollute its own mean), illegal alarm-lifecycle transitions, schema rejection of malformed device IDs and tags, ULID format validation, time-ordered ULID semantics.

Why this matters: AI-generated code without test discipline is exactly the failure mode reviewers worry about — fast generation, opaque correctness. AI-generated code with rigorous testing alongside is faster than hand-rolled code at equivalent quality. The discipline is in the harness, not in the generation.

Reference artifacts: `backend/tests/test_zscore.py`, `test_isoforest.py`, `test_alarm_lifecycle.py`, `test_contracts.py`. Run `cd backend && pytest` to verify.

### 4. Honest scope management

The spec describes the intended architecture at v.1.5 production grade. The code ships v.1. The delta between the two is documented explicitly in `KNOWN_ISSUES.md` under the section "v.1 implementation status (spec → code delta)."

The principle: **the spec is the design, not the changelog**. Trimming the spec retroactively to match what shipped would lose information about the intended architecture. Documenting the gap preserves both — design and as-built — and lets a reviewer see the trajectory.

Examples of deliberate scope cuts visible in `KNOWN_ISSUES.md`:

- The Pydantic contracts module (`app/contracts.py`), the rolling z-score and Isolation Forest detector modules (`app/detectors/`), and the alarm lifecycle module (`app/alarms/lifecycle.py`) are implemented and unit-tested. They are **not yet wired into the running ingest service**. The integration is mechanical and queued for v.1.5.
- The dedicated edge gateway with SQLite store-and-forward (ADR-005) is specified in detail but not built; the simulator publishes directly to Mosquitto in v.1.
- The MQTT topic shape and telemetry payload in the running code are simpler than `SPEC.md` §6.1 specifies; the full schema is implemented in `contracts.py` but not yet used by `main.py`.

These gaps are not failures. They are what a focused v.1 build looks like when the engineer chose to land high-coverage modules and a working demo rather than rush an integration without the test discipline.

Why this matters in a regulated-industry context: software whose origin and review path are documented honestly is a credibility asset. Software that overclaims is a liability. ITAR, AS9100, and CMMC environments penalize hidden over-claim much more than they penalize honest under-delivery.

Reference artifact: `KNOWN_ISSUES.md`, especially the "v.1 implementation status" section and the "v.1 ingest path: simpler than the modules describe" subsection.

### 5. Transparency about AI involvement

The methodology is documented at the repo root in this file and in `CLAUDE.md`. The essay accompanying this submission names Claude Code by name. The repo's `DECISIONS.md` ADR-014 names the spec-first methodology as a deliberate choice. Nothing about AI involvement is obscured.

This matters because the alternative — AI-assisted code without disclosure — is a credibility hit when discovered. Reviewers can spot AI patterns; the cost of pretending the work was hand-written exceeds the cost of being explicit about how it was made.

The transparency is also the point. The repo is meant to demonstrate not just what the system does, but how the engineer works. AI-assisted development at production quality is a methodology distinct from "vibe coding" with an AI assistant. This document and `CLAUDE.md` are the evidence that the methodology was the former.

---

## What this methodology does NOT claim

To prevent the document from being read as a tool flex, here is what it explicitly does not assert:

- It does **not** claim AI assistance produces senior-engineer judgment automatically. The judgment about what to build, what to defer, how to label telemetry honestly, and what to surface in `KNOWN_ISSUES.md` is the engineer's. The agent's role was implementation against decisions the engineer had already made.
- It does **not** claim the result is equivalent to a system built over weeks by a team with operational scale experience. The architectural choices are research-and-judgment based; many of them are first-principles rather than lived production experience. `SPEC.md` §16 is explicit about the next layer of rigor a v.1.5 spec would add (formal AsyncAPI/OpenAPI documents, FMEA, SLOs, threat model, data lifecycle, dependency-pinning policy, verification matrix).
- It does **not** claim the spec was unaffected by the agent. Discussion of alternatives during the spec phase happened in conversation with Claude. The decisions are the engineer's; some of the comparative reasoning was informed by AI-generated analysis. This is the same dynamic as discussing alternatives with a colleague or reading a comparison blog post — the source of analysis matters less than the engineer's final ownership of the decision.
- It does **not** claim novelty. The patterns documented here — spec-first methodology, context engineering, ADR-style decisions, hand-rolled vs tool-generated docs, honest scope tracking — are documented across the industry as best practices for AI-assisted development. The methodology is recognized current practice applied with discipline, not invented.

---

## What this methodology does claim

- That the repo's quality is the result of process and discipline, not just AI tooling.
- That the documentation set, the test coverage, and the honest gap accounting in `KNOWN_ISSUES.md` are evidence that this process was followed.
- That AI-assisted development under spec-first methodology with rigorous testing produces meaningfully more work in less time at credible quality, when the engineer brings the judgment about what to build, what to defer, and what to be honest about.
- That for a regulated-industry engineering team — Smart Factory at Blue Origin sits inside ITAR, AS9100, and CMMC — having software whose origin and review path are documented is a feature, not a flaw.

---

## How to verify the methodology actually held

A reviewer who wants to confirm the claims above can do the following in 10–15 minutes:

1. Read `SPEC.md` — note that the document is structured (numbered sections, requirements with FR/NFR identifiers, explicit failure modes, acceptance criteria, a `§16 Methodology note` section). Hand-rolled specs read as thinking; check the prose voice.
2. Read `DECISIONS.md` — note the ADR format with explicit "Rejected" alternatives in each entry. Each ADR has a `**Status:**` tag added during the v.1 polish pass that records implementation reality.
3. Read `CLAUDE.md` — note the section structure (working agreement, required reading order, language conventions, ask-before triggers). This is the rules document the agent reads at the start of every session.
4. Read `KNOWN_ISSUES.md`, specifically the "v.1 implementation status" section. Note how the gap between spec and code is documented explicitly rather than papered over.
5. Run the test suite: `cd backend && pip install -r requirements.txt && pytest`. Confirm 69 tests pass and coverage on `app.contracts`, `app.detectors`, and `app.alarms` is 100%.
6. Spot-check the git history: `git log --oneline`. Conventional Commits format, scope tags, sequenced commits per logical change.
7. Read one detector test file (`backend/tests/test_zscore.py` is the densest). Note that the tests cover NaN handling, empty windows, zero-variance windows, eviction behavior, and the prior-window-semantics regression. These are tests written by an engineer who knew what to break.

If any of those seven steps doesn't hold up to inspection, the methodology claims in this document are weaker than they appear. They were intended to hold up.

---

## Closing note

This methodology was applied to a v.1 prototype on a focused-window deadline. It is not a process for every project, every team, or every scale. It is the process that makes AI-assisted development credible for the kind of work this repo demonstrates: architectural prototypes, vertical slices, documented designs intended to evolve.

For a long-running production system, the methodology expands — formal API specifications generated and validated, runbooks under `docs/`, CI tied to deployment gates, security review, on-call rotations, change management. `SPEC.md` §16 names what a v.1.5 spec would add and `AWS_DEPLOYMENT.md` names what a production deployment looks like. The methodology here is the right one for the layer this project is at; the next layer of rigor is named and queued.
