# CIRO — Implementation Plan (Workplan)

> This is the phased build plan. When you run Strategy A, Antigravity will read this and emit it
> as its **Task List** artifact. When you run Strategy B (full rebuild), this is the build order.
> Phases are dependency-ordered; tasks inside a phase can often run together.

**Legend** — each task: **ID · Name · Goal · Files · Depends on · Acceptance criteria.**

---

## Phase 0 — Workspace & ground rules

**T0.1 · Workspace setup**
Goal: a clean Antigravity workspace containing the CIRO source + this kit.
Files: workspace root.
Depends on: —.
Accept: `backend/`, `ciro_app/`, `docs/`, `_kit/` present; `.claude/` and `.idea/` removed;
`backend/.env` created from `.env.example` (keys optional).

**T0.2 · Read context & emit plan**
Goal: Antigravity reads `02_ARCHITECTURE.md` + the source and produces an Implementation Plan +
Task List artifact mirroring this file.
Depends on: T0.1.
Accept: Implementation Plan + Task List artifacts exist and cover Phases 1–8.

---

## Phase 1 — Project scaffold & config

**T1.1 · Backend skeleton**
Goal: directory tree, empty `__init__.py` in `config/`, `agents/`, `services/`; `data/`,
`models/`, `models/prophet/`, `static/` dirs.
Files: `backend/**` skeleton.
Depends on: T0.2.
Accept: tree matches `02_ARCHITECTURE.md` §2.

**T1.2 · Dependencies & env**
Goal: `requirements.txt`, `.env.example`, `Dockerfile`, root `.gitignore`.
Files: `backend/requirements.txt`, `backend/.env.example`, `backend/Dockerfile`, `.gitignore`.
Depends on: T1.1.
Accept: `pip install -r requirements.txt` succeeds in a Python 3.11 venv.

**T1.3 · Settings**
Goal: `config/settings.py` — Pydantic `Settings`, 8 `ZONES`, all keys/thresholds/intervals per
`02_ARCHITECTURE.md` §4. Absolute `.env` path resolution.
Files: `backend/config/settings.py`.
Depends on: T1.2.
Accept: `from config.settings import settings; len(settings.ZONES)==8`.

---

## Phase 2 — Shared services (infrastructure)

**T2.1 · Signal store**
Goal: `signal_store.py` — async SQLite, `signals` table + 4 indexes, `store_signals` (INSERT OR
IGNORE dedup), `get_signals`, `get_signals_by_type`, `get_zone_summary`, `get_all_metrics`,
`prune_expired`, runtime metrics.
Files: `backend/services/signal_store.py`.
Depends on: T1.3.
Accept: `initialize()` creates `data/signals.db`; storing the same signal twice yields 1 row.

**T2.2 · WebSocket manager**
Goal: `websocket_manager.py` — `ClientSubscription`, connect/disconnect, `broadcast_signals`
(per-client zone/severity/type filter), `broadcast_alert`, `get_metrics`. Module singleton `ws_manager`.
Files: `backend/services/websocket_manager.py`.
Depends on: T1.3.
Accept: a client connecting receives a `{"type":"connected"}` message.

**T2.3 · Retry client + Gemini retry**
Goal: `retry_client.py` — `RetryClient` with exponential backoff (1→2→4 s), circuit breaker (5
fails → open 60 s), class-level per-source metrics. `gemini_retry.py` — decorator retrying on
HTTP 429 only.
Files: `backend/services/retry_client.py`, `backend/services/gemini_retry.py`.
Depends on: T1.3.
Accept: `RetryClient.get_all_metrics()` returns a dict; decorator re-raises non-429 errors.

**T2.4 · Scheduler**
Goal: `scheduler.py` — `CIROScheduler` (AsyncIOScheduler): 15-min fetch job, daily 03:00 prune
job, `add_orchestrator_job()` (2-h interval), `get_status()`.
Files: `backend/services/scheduler.py`.
Depends on: T1.3.
Accept: `start()` registers jobs; `get_status()` lists them with next-run times.

**T2.5 · Open-Meteo service**
Goal: `openmeteo_service.py` — `fetch_current_and_forecast`, `fetch_historical`,
`fetch_flood_forecast` (GloFAS, 30-day), `fetch_16day_daily_forecast`; severity calculators;
parsers to the Signal schema.
Files: `backend/services/openmeteo_service.py`.
Depends on: T2.1.
Accept: a live call to `api.open-meteo.com` for a zone returns ≥1 normalised signal.

**T2.6 · Prophet weather forecaster**
Goal: `weather_forecaster.py` — `WeatherForecaster`: `load_or_train` (load 12 `.pkl` or train
from `data/training/{Province}/`), `forecast(province, recent_temps, recent_rains, start, days)`
with anomaly conditioning; module singleton via `get_weather_forecaster()`.
Files: `backend/services/weather_forecaster.py`.
Depends on: T1.3, T6.1 (training data present).
Accept: first call trains 12 models in ~15–20 s and writes `models/prophet/*.pkl`.

**T2.7 · Simulated & optional services**
Goal: `weather_service.py` (OpenWeatherMap + sim), `traffic_service.py` (Google Maps + sim),
`ndma_service.py` (simulated alerts, conf 0.50), `social_service.py` (Urdu+English keywords,
conf 0.50).
Files: those 4 files in `backend/services/`.
Depends on: T1.3.
Accept: each `fetch_for_zone(zone)` returns a list of valid Signal dicts with no API key.

**T2.8 · Geospatial services**
Goal: `earth_engine_service.py` (GEE Sentinel-2 + NDWI + simulation fallback),
`geogemma_service.py` (Gemini Vision + rule-based fallback), `floodhub_service.py` (Google Flood
Hub, optional). Singletons via `get_*_service()`.
Files: those 3 files in `backend/services/`.
Depends on: T2.3.
Accept: with no keys, `EarthEngineService` returns simulated change detection;
`GeoGemmaService` returns a rule-based `GeoGemmaAnalysis`.

---

## Phase 3 — Agent 2 (Data & API Collector)

**T3.1 · Agent 2 router**
Goal: `agent_data_collector.py` — `Signal`/`ZoneSignalSummary`/`FetchResult` models; 9 endpoints
(`02_ARCHITECTURE.md` §5.1); `run_fetch_cycle()`; `_compute_ml_features` with **hourly dedup**;
`_aggregate_daily`; `_compute_risk_indicators`; `_get_ndwi_delta`.
Files: `backend/agents/agent_data_collector.py`.
Depends on: T2.1, T2.5, T2.7.
Accept: `POST /api/v1/agent2/fetch` stores signals for 8 zones; `GET /features/{zone}` returns
the 16-field vector.

---

## Phase 4 — Agent 3 (ML Predictor)

**T4.1 · XGBoost flood model**
Goal: in `agent_predictor.py` — `_train_model()` loads the 6 province CSVs, trains `XGBClassifier`
(n_estimators 200, max_depth 5, lr 0.1, `scale_pos_weight`), evaluates, bundles with metadata,
saves to `models/flood_model.joblib`; `_ensure_model_loaded()` lazy + thread-safe.
Files: `backend/agents/agent_predictor.py` (part 1).
Depends on: T2.6, T6.1.
Accept: first `/predict` or `/retrain` produces `flood_model.joblib`; `GET /model/info` works.

**T4.2 · Temporal-intelligence enhancements**
Goal: the 6 enhancement functions — `compute_antecedent_moisture_index`,
`compute_discharge_momentum`, `detect_monsoon_onset`, `apply_temporal_ewma`, `sigmoid_calibrate`,
`compute_heat_risk` (UNICEF 90th-percentile engine) — plus the per-province baseline tables.
Files: `backend/agents/agent_predictor.py` (part 2).
Depends on: T4.1.
Accept: unit-sanity — `sigmoid_calibrate(0.5)≈0.5`; `compute_heat_risk` returns 0–0.99.

**T4.3 · Feature projector + 30-day pipeline + endpoints**
Goal: `FeatureProjector` (days 1–16 ECMWF, 17–30 Prophet), `RiskPredictor.predict_30_days`
(3-pass pipeline), `build_summary`; endpoints `/status`, `/predict/{zone}`, `/model/info`,
`/backtest`, `/retrain`.
Files: `backend/agents/agent_predictor.py` (part 3).
Depends on: T4.2, T3.1.
Accept: `POST /api/v1/agent3/predict/lahore-city` returns a `ZonePrediction` with 30
`predictions` and a `summary`.

---

## Phase 5 — Agents 1 & 4, Debater, Orchestrator

**T5.1 · Agent 1 (Imagery)**
Goal: `agent_imagery.py` — 8 endpoints; `_run_analysis` pipeline (GEE change detection →
GeoGemma → store `satellite_ndwi` signal → WebSocket broadcast → cache); `SatelliteAnalysisResult`.
Files: `backend/agents/agent_imagery.py`.
Depends on: T2.8, T3.1.
Accept: `POST /api/v1/agent1/analyze/{zone}` returns a result (simulated mode OK).

**T5.2 · Debater**
Goal: `agent_debater.py` — `_classify_trigger`, `_PERSONA_FOCUSES` library, `ZoneDebater`
(4 Gemini calls), `DebateResult`/`PersonaVerdict`/`DebateConsensus`; endpoints `/debate/{zone}`,
`/last-results`. Structured fallback when Gemini unavailable.
Files: `backend/agents/agent_debater.py`.
Depends on: T2.3, T4.3.
Accept: `POST /api/v1/debater/debate/{zone}` returns a `DebateResult` (fallback OK without a key).

**T5.3 · Agent 4 (Response Commander)**
Goal: `agent_response.py` — `ResponsePlanner` (Gemini planning + `_fallback_plan`); zone
population/shelter/hospital tables; schemas; endpoints `/respond/{zone}`,
`/respond-from-debate`, `/last-response/{zone}`, `/trace/{zone}`, `/status`.
Files: `backend/agents/agent_response.py`.
Depends on: T5.2.
Accept: `POST /api/v1/agent4/respond/{zone}` returns a `ResponsePlan` with actions + simulation.
**Fix the `zone_context` ordering bug** — see `06_KNOWN_ISSUES_AND_FIXES.md` §B1.

**T5.4 · Orchestrator**
Goal: `agent_orchestrator.py` — `OrchestrationLog`, `CIROOrchestrator.run_cycle()` (predict all →
threshold-gate → debate → Agent 4 → log); endpoints `/status`, `/run`, `/logs`, `/logs/{run_id}`.
Files: `backend/agents/agent_orchestrator.py`.
Depends on: T5.2, T5.3.
Accept: `POST /api/v1/orchestrator/run` returns a run result with a `trace`; `/logs` lists it.

---

## Phase 6 — Data, models, main app, dashboards

**T6.1 · Training data**
Goal: place real Pakistan climate CSVs under `data/training/` — 6 `{Province}_training.csv`
(monthly, for XGBoost) + 6 `{Province}/` folders with daily `Temp*.csv` / `Pre*.csv` (for
Prophet) + national rainfall/temperature CSVs.
Files: `backend/data/training/**`.
Depends on: T1.1.
Accept: `_train_model` finds ≥4 province CSVs; Prophet finds ≥4 province folders.
*(These files already exist in your repo — just carry them over.)*

**T6.2 · Main application**
Goal: `main.py` — logging, `lifespan` (init signal store → init Earth Engine → start scheduler →
register orchestrator job), CORS, mount all 6 routers, `/`, `/map`, `/api`, `/health`,
`/metrics`, WebSocket `/ws/signals`.
Files: `backend/main.py`.
Depends on: T3.1, T4.3, T5.1–T5.4.
Accept: `uvicorn main:app` starts cleanly; `/health` returns `{"status":"healthy"}`; `/docs` lists
all routers. **Fix the `/map` path bug** — `06_KNOWN_ISSUES_AND_FIXES.md` §B2.

**T6.3 · Web dashboards**
Goal: `static/index.html` (control panel) + `static/crisis_map.html` (interactive map).
Files: `backend/static/index.html`, `backend/static/crisis_map.html`.
Depends on: T6.2.
Accept: `/` renders the dashboard; buttons call the API. **Fix the `model/info` field bug** —
`06_KNOWN_ISSUES_AND_FIXES.md` §B3.

---

## Phase 7 — Flutter mobile app

**T7.1 · Flutter scaffold + config + theme + models**
Goal: `pubspec.yaml` (deps per `02_ARCHITECTURE.md` §10), `api_config.dart`, `ciro_theme.dart`,
`models/zone.dart` (8 zones — must match `settings.py`), `models/prediction.dart`.
Files: `ciro_app/pubspec.yaml`, `ciro_app/lib/config/`, `lib/theme/`, `lib/models/`.
Depends on: —.
Accept: `flutter pub get` succeeds.

**T7.2 · Flutter services**
Goal: `api_service.dart` (Dio singleton), `websocket_service.dart` (ChangeNotifier + 5-s
auto-reconnect + `onAlert` for severity ≥7), `notification_service.dart`.
Files: `ciro_app/lib/services/`.
Depends on: T7.1.
Accept: app compiles; `ApiService` covers all agent endpoints used by the screens.

**T7.3 · Flutter screens + shell**
Goal: `main.dart` (Provider + 3-tab shell), `home_screen.dart`, `prediction_screen.dart`,
`agents_screen.dart`, `live_map_screen.dart`, `alerts_screen.dart`.
Files: `ciro_app/lib/main.dart`, `ciro_app/lib/screens/`.
Depends on: T7.2.
Accept: `flutter run` launches; Home shows 8 zone cards; tapping a zone opens the 30-day chart.
Decide whether to wire `alerts_screen.dart` into the nav — `06_KNOWN_ISSUES_AND_FIXES.md` §C.

---

## Phase 8 — Integration, verification, hardening, docs

**T8.1 · End-to-end run & verify**
Goal: start the backend, run the first-run checklist, exercise the full agent pipeline.
Depends on: T6.2, T7.3.
Accept: checklist below all green.

**T8.2 · Fix known issues**
Goal: apply every fix in `06_KNOWN_ISSUES_AND_FIXES.md`.
Depends on: T8.1.
Accept: stray empty files gone; `/map` works; `/respond` works; `model/info` UI shows no
`undefined`; `/health` reports the real agent count.

**T8.3 · Robustness pass**
Goal: demonstrate ≥1 failure/edge case (per the FAQ "robustness evidence" rule) — kill an API
key and show graceful fallback; force a Gemini 429 and show retry; show the Debater `trigger_type`
preventing a false flood reading on a heat-only zone.
Depends on: T8.2.
Accept: each scenario logged/screenshotted.

**T8.4 · README & docs**
Goal: README with architecture (`02_ARCHITECTURE.md`), data schemas, tools/APIs, **"How
Antigravity is used"** (`02_ARCHITECTURE.md` §13), setup, assumptions, privacy note, cost/latency,
scalability (10×/100×), baseline comparison (agentic vs. a flat heuristic), limitations.
Depends on: T8.3.
Accept: README covers every bullet in the FAQ "README/documentation" checklist.

**T8.5 · Antigravity artifact export**
Goal: collect the Implementation Plan, Task List, agent traces and Walkthrough artifacts for
submission (`05_ANTIGRAVITY_PLAYBOOK.md` §5).
Depends on: T8.4.
Accept: artifacts exported to a `submission/antigravity-artifacts/` folder.

---

## First-run verification checklist (T8.1)

```
[ ] python venv + pip install -r requirements.txt  → no errors
[ ] uvicorn main:app --host 0.0.0.0 --port 8000     → starts clean
[ ] GET  /health                                    → {"status":"healthy"}
[ ] GET  /docs                                       → all 6 agent routers listed
[ ] POST /api/v1/agent2/fetch                         → signals_collected > 0
[ ] POST /api/v1/agent2/backfill/lahore-city?days=30 → signals_stored > 0
[ ] GET  /api/v1/agent2/features/lahore-city          → 16-field feature vector
[ ] POST /api/v1/agent3/predict/lahore-city           → 30 predictions + summary (first run ~20s)
[ ] GET  /api/v1/agent3/model/info                    → XGBoost metadata
[ ] POST /api/v1/agent3/backtest                       → accuracy reported
[ ] POST /api/v1/agent1/analyze/lahore-city           → satellite result (simulated OK)
[ ] POST /api/v1/debater/debate/lahore-city            → DebateResult (fallback OK w/o key)
[ ] POST /api/v1/orchestrator/run                      → run_id + trace
[ ] GET  /api/v1/orchestrator/logs                     → the run is listed
[ ] WS   /ws/signals                                   → receives "connected" + signals
[ ] GET  /            → control-panel dashboard renders
[ ] GET  /map         → crisis map renders
[ ] flutter pub get && flutter run  → Home shows 8 zones; tap → 30-day chart; AI Agents → pipeline
```

## Build order summary

```
Phase 0 → 1 → 2 → (3 ∥ 6.1) → 4 → 5 → 6 → 7 → 8
```
Phase 7 (Flutter) has no dependency on the backend build and may run in parallel with Phases 2–6.
In Strategy A you do not rebuild — you verify each phase against the existing code, then jump
to Phase 8.
