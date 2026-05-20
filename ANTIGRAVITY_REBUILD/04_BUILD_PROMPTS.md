# CIRO — Antigravity Build Prompts

> Copy-paste prompts for the Antigravity **Agent Manager**. Each prompt is self-contained and
> credit-efficient: it does a whole phase per turn, points Antigravity at the kit specs, and asks
> it to generate the artifacts you need to submit.
>
> **Run Strategy A** (§A) — recommended, ~8–12 turns, fits the free credit budget.
> **Strategy B** (§B) is the full from-scratch rebuild — only if you specifically need that.
>
> Before you start: copy this `ANTIGRAVITY_REBUILD/` folder into the workspace as `_kit/`, and
> (Strategy A) copy your working repo in as `backend/`, `ciro_app/`, `docs/`. Set the model to
> **Gemini 3 Flash** for cheap turns; see `05_ANTIGRAVITY_PLAYBOOK.md`.

---

# §A — Strategy A prompts (RECOMMENDED)

You have the working code. Antigravity's job is to **understand, plan, verify, fix, harden,
run and document** it — all genuine work that produces genuine artifacts.

---

## Prompt A1 — Understand the codebase, emit the plan

```
You are working in a CIRO project workspace — "Crisis Intelligence & Response Orchestrator",
a multi-agent crisis-prediction system built for Challenge 3 of the Google Antigravity
Hackathon. The full working source is in backend/ (Python FastAPI) and ciro_app/ (Flutter).

Read these specs first:
  _kit/01_PRODUCT_BRIEF.md       — what CIRO is and the Challenge-3 requirements it answers
  _kit/02_ARCHITECTURE.md        — the authoritative technical architecture
  _kit/03_IMPLEMENTATION_PLAN.md — the phased build/verification plan
Then skim the source: backend/main.py, backend/config/settings.py, the 6 files in
backend/agents/, the files in backend/services/, and ciro_app/lib/.

Deliver, as Antigravity artifacts:
1. An Implementation Plan that documents CIRO's architecture: the 6 agents, the 3 data-flow
   loops (15-min fetch, on-demand prediction, 2-hour orchestration), the dual-ML design
   (XGBoost flood + Prophet weather + UNICEF heat engine), the data schemas, and the API surface.
2. A Task List mirroring Phases 1–8 of _kit/03_IMPLEMENTATION_PLAN.md, but reframed as a
   VERIFY-AND-HARDEN plan: for each phase, the task is to confirm the existing code matches the
   spec and is correct, not to rewrite it.
3. A short written summary: confirm the code matches the architecture, and list any
   discrepancies you found between _kit/02_ARCHITECTURE.md and the actual source.

Do NOT modify any code in this turn. Planning and reading only.
```

---

## Prompt A2 — Fix the known defects (real engineering work)

```
Read _kit/06_KNOWN_ISSUES_AND_FIXES.md. It lists real defects in the CIRO codebase.

Task: fix every issue in sections A, B and C of that file. Specifically:
  - Delete the stray empty files in backend/ (May, [deck.gl, functionality, like).
  - Fix the zone_context-before-assignment bug in backend/agents/agent_response.py
    (POST /respond/{zone_id}).
  - Fix the /map route file path in backend/main.py so the crisis map serves correctly.
  - Fix backend/static/index.html loadModelInfo() so it only reads fields the
    /api/v1/agent3/model/info endpoint actually returns (no heat_model_* fields).
  - Fix the hardcoded agents_active count in the /health endpoint.
  - Resolve the AlertsScreen wiring decision in ciro_app per section C (recommended: add it as
    a 4th bottom-nav tab).
  - Align any data_source label / naming inconsistencies noted in section D.

Work through them as a task list. For each fix: state the file and line, the root cause, and
the change. After all fixes, do a quick static check (python -c imports for the backend,
`flutter analyze` for the app) and report results. Produce a Walkthrough artifact summarising
what changed and why.
```

---

## Prompt A3 — Run, verify end-to-end, capture a walkthrough

```
Verify CIRO runs end-to-end and capture the evidence.

Backend:
  1. Create a Python 3.11 virtual environment in backend/ and install requirements.txt.
  2. Copy backend/.env.example to backend/.env (leave keys blank — the system runs without them).
  3. Start the server:  uvicorn main:app --host 0.0.0.0 --port 8000
  4. Run the First-Run Verification Checklist from _kit/03_IMPLEMENTATION_PLAN.md — call each
     endpoint with curl (GET /health, POST /api/v1/agent2/fetch,
     POST /api/v1/agent3/predict/lahore-city, POST /api/v1/orchestrator/run, etc.) and record
     the responses. The first /predict trains the ML models and takes ~15-20s — that is expected.
  5. Open http://localhost:8000/ (control panel) and http://localhost:8000/map (crisis map) in
     the Antigravity browser; take screenshots; click "Fetch All Signals" and "Predict 30 Days".

Flutter app:
  6. In ciro_app/, run `flutter pub get` then `flutter analyze` and report any errors.
     (A full device run is optional if no emulator is available — analyze + build is enough.)

Produce a Walkthrough artifact: the checklist results, the screenshots, and a one-paragraph
verdict on whether CIRO works end-to-end. Note anything that failed and fix it if small.
```

---

## Prompt A4 — Robustness demonstration (required by the rubric)

```
The hackathon requires "robustness evidence" — at least one failure / edge case / fallback
demonstrated. With the backend running, demonstrate and capture three scenarios:

  1. Missing-key fallback: confirm Agent 1 (POST /api/v1/agent1/analyze/lahore-city) and the
     Debater (POST /api/v1/debater/debate/lahore-city) both return valid structured results with
     NO Gemini/GEE keys configured — i.e. the simulation / rule-based / structured-fallback
     paths. Show the response and the log line proving the fallback fired.
  2. Retry / circuit breaker: explain (and if possible exercise) services/retry_client.py and
     services/gemini_retry.py — show the exponential-backoff retry and the circuit-breaker
     opening after repeated failures.
  3. False-signal handling: call the Debater on a heat-dominant zone (e.g. jacobabad-city) and
     show that trigger_type is classified HEAT, so the consensus reports a heat probability and
     does NOT invent a flood probability — the conflicting-signal safeguard.

Capture each as a screenshot or log excerpt in a Walkthrough artifact titled
"CIRO robustness evidence".
```

---

## Prompt A5 — Generate the README and the Antigravity section

```
Write/refresh README.md at the repo root so it satisfies the hackathon's README checklist.
Base the architecture content on _kit/02_ARCHITECTURE.md and the product framing on
_kit/01_PRODUCT_BRIEF.md. Include these sections:

  - What CIRO is + the Challenge-3 problem it solves
  - System architecture (the 6 agents, 3 data-flow loops, dual-ML design) with the diagram
  - Data stream schemas (Signal, ZonePrediction, DebateResult, ResponsePlan, OrchestrationLog)
  - Tools / APIs used (Open-Meteo, GloFAS, OpenWeatherMap, Google Maps, Gemini, Earth Engine,
    Google Flood Hub) and which need keys
  - "How Antigravity is used" — use the exact two-layer framing from _kit/02_ARCHITECTURE.md
    §13: Antigravity is the development-time agentic platform (it planned, verified, hardened,
    ran and documented CIRO and produced the Implementation Plan / Task List / Walkthrough
    artifacts); CIRO's own 6-agent pipeline is the runtime crisis-response system. Keep both
    descriptions accurate.
  - Setup steps (backend venv + uvicorn; Flutter pub get + run)
  - Assumptions & limitations (NDMA + social sources are simulated at confidence 0.50; days
    17-30 forecasts are low-confidence; heat engine is rule-based)
  - Privacy & safety note (no real personal data; simulated/mock crisis data)
  - Cost & latency (Open-Meteo free; ~latency per /predict; Gemini calls per orchestration cycle)
  - Scalability (10x / 100x: stateless agents, SQLite → Postgres, Cloud Run autoscaling)
  - Baseline comparison: agentic CIRO vs a non-agentic flat heuristic — explain why the
    multi-agent + temporal-intelligence pipeline detects crises a simple threshold rule misses.

Then produce a final Walkthrough artifact summarising the whole rebuild session.
```

> After A5, export your artifacts — see `05_ANTIGRAVITY_PLAYBOOK.md` §5.

---

# §B — Strategy B prompts (full rebuild — fallback only)

Use these only if you need Antigravity's history to show a from-scratch build. Far more credits.
Keep your working repo available as `_reference/` so each prompt can be checked against it.
Run one prompt per turn; review the artifacts; comment to correct before moving on.

### Prompt B0 — Setup & plan
```
We are building CIRO (Crisis Intelligence & Response Orchestrator) for Challenge 3 of the
Google Antigravity Hackathon — a multi-agent crisis-prediction system: a Python FastAPI backend
with 6 agents + a Flutter mobile app. The full spec is in _kit/02_ARCHITECTURE.md and the build
plan in _kit/03_IMPLEMENTATION_PLAN.md. A known-good reference implementation is in _reference/.

Read all of _kit/, then produce an Implementation Plan and a Task List covering Phases 1-8 of
_kit/03_IMPLEMENTATION_PLAN.md. Do not write code yet. Confirm the plan back to me.
```

### Prompt B1 — Phase 1: scaffold, deps, settings
```
Execute Phase 1 of _kit/03_IMPLEMENTATION_PLAN.md (tasks T1.1–T1.3): create the backend/
directory tree, requirements.txt, .env.example, Dockerfile, root .gitignore, and
config/settings.py with the 8 ZONES and all settings exactly as in _kit/02_ARCHITECTURE.md §4.
Match _reference/ for exact values. Verify: `pip install -r requirements.txt` succeeds and
`from config.settings import settings` loads 8 zones.
```

### Prompt B2 — Phase 2: shared services
```
Execute Phase 2 of _kit/03_IMPLEMENTATION_PLAN.md (T2.1–T2.8): build all of backend/services/ —
signal_store, websocket_manager, retry_client, gemini_retry, scheduler, openmeteo_service,
weather_forecaster, weather_service, traffic_service, ndma_service, social_service,
earth_engine_service, geogemma_service, floodhub_service. Follow _kit/02_ARCHITECTURE.md §5
and §8–9 for behaviour and schemas; match _reference/services/ for exact logic. Every external
service must degrade gracefully (simulation/fallback) with no API key. Verify each acceptance
criterion in the plan.
```

### Prompt B3 — Phase 3: Agent 2
```
Execute Phase 3 (T3.1): build backend/agents/agent_data_collector.py — Agent 2, the data
collector. 9 endpoints, run_fetch_cycle(), and _compute_ml_features with the critical HOURLY
DEDUPLICATION (the 15-min scheduler stores the same rainfall reading 4x/hour; keep only the max
per hour). Spec: _kit/02_ARCHITECTURE.md §5.1; reference: _reference/agents/agent_data_collector.py.
Verify POST /api/v1/agent2/fetch and GET /features/{zone}.
```

### Prompt B4 — Phase 4: Agent 3 (ML predictor)
```
Execute Phase 4 (T4.1–T4.3): build backend/agents/agent_predictor.py — Agent 3. This is the
largest, most important file. Implement: the XGBoost flood model (train/load/bundle), the 6
temporal-intelligence enhancements (antecedent moisture index, discharge momentum, monsoon-onset
detection, EWMA temporal weighting, sigmoid calibration, UNICEF heatwave engine), the per-province
baseline tables, the FeatureProjector (days 1-16 ECMWF / 17-30 Prophet), the 3-pass
predict_30_days pipeline, and endpoints /status /predict /model/info /backtest /retrain.
Spec: _kit/02_ARCHITECTURE.md §5.2; reference: _reference/agents/agent_predictor.py — match its
logic closely, it is tuned. Verify POST /api/v1/agent3/predict/lahore-city returns 30 predictions.
```

### Prompt B5 — Phase 5: Agents 1 & 4, Debater, Orchestrator
```
Execute Phase 5 (T5.1–T5.4): build backend/agents/agent_imagery.py (Agent 1),
agent_debater.py (Debater — 4 Gemini calls, 3 personas + consensus, trigger_type classification),
agent_response.py (Agent 4 — Gemini response planning + before/after simulation), and
agent_orchestrator.py (Orchestrator — 2-hour cycle, threshold gate, OrchestrationLog).
Spec: _kit/02_ARCHITECTURE.md §5.3–5.6; reference: _reference/agents/. Apply the fixes in
_kit/06_KNOWN_ISSUES_AND_FIXES.md as you go (do NOT reproduce the zone_context bug). All Gemini
calls must have structured fallbacks. Verify each endpoint.
```

### Prompt B6 — Phase 6: main app, data, dashboards
```
Execute Phase 6 (T6.1–T6.3): copy the training CSVs from _reference/data/training/ into
backend/data/training/; build backend/main.py (lifespan, CORS, mount all 6 routers, /, /map,
/api, /health, /metrics, /ws/signals); and the two dashboards static/index.html +
static/crisis_map.html. Spec: _kit/02_ARCHITECTURE.md §11–12. Apply the /map path fix and the
model/info field fix from _kit/06_KNOWN_ISSUES_AND_FIXES.md. Verify uvicorn starts and /health
is healthy.
```

### Prompt B7 — Phase 7: Flutter app
```
Execute Phase 7 (T7.1–T7.3): build the ciro_app/ Flutter app — pubspec.yaml, config/api_config,
theme/ciro_theme, models/{zone,prediction}, services/{api_service,websocket_service,
notification_service}, main.dart, and screens/{home,prediction,agents,live_map,alerts}.
Spec: _kit/02_ARCHITECTURE.md §10; reference: _reference/ciro_app/lib/. The 8 zones in zone.dart
MUST match settings.py exactly. Verify `flutter pub get` and `flutter analyze`.
```

### Prompt B8 — Phase 8: integrate, verify, harden, document
```
Execute Phase 8 (T8.1–T8.5): run the First-Run Verification Checklist in
_kit/03_IMPLEMENTATION_PLAN.md; apply any remaining fixes from _kit/06_KNOWN_ISSUES_AND_FIXES.md;
demonstrate the 3 robustness scenarios from Prompt A4; write the README per Prompt A5; and
collect the Antigravity artifacts for submission. Produce a final Walkthrough artifact.
```

---

# Prompt-writing tips (if you need to deviate)

- **One phase per turn.** Each turn ≈ one Antigravity request. With ~20 free requests/day,
  Strategy A (≈5 turns) is comfortable; Strategy B (≈9 turns) is one day's budget — no room for
  re-runs, so review artifacts carefully before approving.
- **Always say "produce an Implementation Plan / Task List / Walkthrough artifact"** — those are
  the deliverables; make Antigravity emit them explicitly.
- **Point at the kit + reference, don't paste code.** Antigravity reads files cheaply; pasting
  15k lines into prompts is wasteful and error-prone.
- **Correct via artifact comments, not new chats.** Highlight a line in the plan and comment —
  it steers the live run without burning a fresh turn.
- **End every prompt with a concrete verification step** so the agent self-checks instead of you
  spending a turn finding out it failed.
