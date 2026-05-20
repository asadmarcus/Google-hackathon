# CIRO — System Architecture

> The authoritative technical spec. Antigravity should treat this as ground truth alongside the
> reference source. This file also doubles as the **architecture section of your README**.

---

## 1. System overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                  CIRO SYSTEM                                  │
│                                                                                │
│   Flutter mobile app  ◀── REST ──▶  FastAPI backend (uvicorn, :8000)           │
│   (ciro_app/)         ◀─ WebSocket ─▶                                          │
│                                                                                │
│   BACKEND AGENTS                                                               │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌────────────┐  ┌─────┐ │
│   │ Agent 1 │  │ Agent 2 │  │ Agent 3 │  │ Debater  │  │Orchestrator│  │Ag. 4│ │
│   │ Imagery │  │  Data   │  │   ML    │  │ 3-persona│  │  2h cycle  │  │Resp.│ │
│   │ GEE +   │  │Collector│  │Predictor│  │  Gemini  │  │ coordinate │  │Gemini│ │
│   │GeoGemma │  │6 sources│  │XGB+Proph│  │  debate  │  │  + log     │  │ plan │ │
│   └────┬────┘  └────┬────┘  └────┬────┘  └────┬─────┘  └─────┬──────┘  └──┬──┘ │
│        │            │            │            │              │           │    │
│        └────────────┴─── shared services ──────┴──────────────┴───────────┘    │
│   SQLite signal store · APScheduler · WebSocket manager · Retry/circuit-breaker │
└────────────────────────────────────────────────────────────────────────────────┘
```

**Two deployables:**
- `backend/` — Python 3.11 FastAPI server: 6 agents, ML models, SQLite, WebSocket, 2 web dashboards.
- `ciro_app/` — Flutter app (Android primary; iOS/web/desktop scaffolded).

---

## 2. Repository layout

```
ciro/                              (workspace root — name it anything)
├── backend/
│   ├── main.py                    FastAPI app: lifespan, routers, /health, /metrics, WebSocket
│   ├── config/
│   │   └── settings.py            Pydantic settings: 8 ZONES, API keys, thresholds, intervals
│   ├── agents/
│   │   ├── agent_data_collector.py   Agent 2  — router /api/v1/agent2
│   │   ├── agent_predictor.py        Agent 3  — router /api/v1/agent3   (largest file, ~1.5k LOC)
│   │   ├── agent_imagery.py          Agent 1  — router /api/v1/agent1
│   │   ├── agent_debater.py          Debater  — router /api/v1/debater
│   │   ├── agent_orchestrator.py     Orchestr.— router /api/v1/orchestrator
│   │   └── agent_response.py         Agent 4  — router /api/v1/agent4
│   ├── services/
│   │   ├── signal_store.py        SQLite persistent store + dedup + prune
│   │   ├── websocket_manager.py   Real-time push, per-client filters
│   │   ├── retry_client.py        HTTP retry + circuit breaker + metrics
│   │   ├── gemini_retry.py        Decorator: exponential backoff on Gemini 429
│   │   ├── scheduler.py           APScheduler wrapper (15-min fetch, 2-h orchestrator, prune)
│   │   ├── openmeteo_service.py   Open-Meteo weather + 16-day forecast + GloFAS flood
│   │   ├── weather_forecaster.py  Prophet weather forecaster (12 models, days 17-30)
│   │   ├── weather_service.py     OpenWeatherMap (optional key)
│   │   ├── traffic_service.py     Google Maps traffic (optional key) + simulation
│   │   ├── ndma_service.py        NDMA alerts (simulated, conf 0.50)
│   │   ├── social_service.py      Social keywords Urdu+English (simulated, conf 0.50)
│   │   ├── earth_engine_service.py  Google Earth Engine Sentinel-2 + NDWI (+ simulation)
│   │   ├── geogemma_service.py    Gemini Vision satellite interpretation (+ rule-based fallback)
│   │   └── floodhub_service.py    Google Flood Hub integration (optional)
│   ├── models/
│   │   ├── flood_model.joblib     Trained XGBoost bundle (auto-generated)
│   │   └── prophet/               12 Prophet .pkl models (auto-generated)
│   ├── data/
│   │   ├── signals.db             SQLite (auto-created)
│   │   └── training/              Real Pakistan climate CSVs (GEE + PMD)
│   ├── static/
│   │   ├── index.html             Control-panel dashboard  → served at GET /
│   │   └── crisis_map.html        Interactive crisis map    → served at GET /map
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── ciro_app/                      Flutter app (see §10)
└── docs/                          design notes
```

---

## 3. Tech stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend framework | FastAPI + Uvicorn | 0.115 / 0.30 |
| Validation | Pydantic + pydantic-settings | 2.9 / 2.5 |
| HTTP client | httpx (async) | 0.27 |
| Database | SQLite via aiosqlite | 0.20 |
| Scheduler | APScheduler (AsyncIOScheduler) | 3.10 |
| Realtime | WebSockets (FastAPI native) | 12.0 |
| ML — flood | XGBoost (XGBClassifier) | 2.1 |
| ML — weather | Prophet (time series) | 1.1.5 |
| ML — utils | scikit-learn, pandas, numpy, joblib | 1.5 / 2.2 / 1.26 / 1.4 |
| Geospatial | earthengine-api, google-auth | 0.1.411 / 2.29 |
| LLM | Google Gemini via REST (`generativelanguage.googleapis.com/v1beta`) | model = `gemini-2.5-flash-lite` |
| Mobile | Flutter (Dart ≥3.0) | provider, dio, web_socket_channel, fl_chart, flutter_local_notifications, url_launcher, intl, shimmer |
| Deploy | Docker → Google Cloud Run | python:3.11-slim |

`requirements.txt` (exact): fastapi==0.115.0, uvicorn[standard]==0.30.0, pydantic==2.9.0,
pydantic-settings==2.5.0, websockets==12.0, httpx==0.27.0, aiosqlite==0.20.0, apscheduler==3.10.4,
scikit-learn==1.5.0, xgboost==2.1.0, prophet==1.1.5, joblib==1.4.0, pandas==2.2.0, numpy==1.26.0,
python-dotenv==1.0.1, python-multipart==0.0.9, earthengine-api==0.1.411, google-auth==2.29.0.

---

## 4. Configuration (`config/settings.py`)

Pydantic `Settings` (BaseSettings), env file resolved by **absolute path** to `backend/.env` so it
works regardless of the uvicorn launch directory.

Key fields: `ENVIRONMENT`, `OPENWEATHER_API_KEY`, `OPENWEATHER_BASE_URL`, `GOOGLE_MAPS_API_KEY`,
`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_FLOODHUB_API_KEY`, `GEE_PROJECT_ID`,
`GEE_SERVICE_ACCOUNT`, `GEE_CREDENTIALS_PATH`, `FIREBASE_*`, `AGENT2_BASE_URL` (default
`http://localhost:8000`), `FETCH_INTERVAL_MINUTES=15`, `SIGNAL_BUFFER_DAYS=30`,
`SEVERITY_THRESHOLD=0.7`, `RISK_ALERT_THRESHOLD=0.30`, `ORCHESTRATOR_INTERVAL_HOURS=2`,
`DEBATE_LLM_MODEL="gemini-2.5-flash-lite"`, `DEBATE_TEMPERATURE=0.3`, and the `ZONES` list.

`ZONES` — list of 8 dicts, each: `id, name, lat, lng, province, elevation_m, drainage_capacity,
population_density`. Exact values:

```
islamabad-g10  G-10, Islamabad  33.6844 73.0479 Federal      507  0.60  2850
lahore-city    Lahore City      31.5204 74.3587 Punjab       217  0.40  6300
karachi-south  Karachi South    24.8607 67.0011 Sindh         10  0.30 14000
peshawar-city  Peshawar City    34.0151 71.5249 KPK          331  0.50  3200
multan-city    Multan City      30.1575 71.5249 Punjab       122  0.35  4500
jacobabad-city Jacobabad City   28.2810 68.4376 Sindh         55  0.25  2100
sukkur-city    Sukkur City      27.7052 68.8574 Sindh         66  0.30  3800
quetta-city    Quetta City      30.1798 66.9750 Balochistan 1680  0.35  1800
```

The system needs **zero API keys** to run — Open-Meteo is free; everything else degrades to
simulation. Keys only enhance fidelity.

---

## 5. The six agents — detailed spec

Each agent is a FastAPI `APIRouter` mounted under a prefix. Agents talk to each other **over HTTP
to `localhost:8000`** (loose coupling) — never via direct imports for data flow.

### 5.1 Agent 2 — Data & API Collector  (`agents/agent_data_collector.py`, prefix `/api/v1/agent2`)

The signal-fusion layer. Polls 6 sources for all 8 zones, normalises to one **Signal** schema,
stores in SQLite with dedup, broadcasts via WebSocket.

**`run_fetch_cycle()`** (called by scheduler every 15 min and by `POST /fetch`): for each zone,
fetch from `weather_service`, `openmeteo_service`, `traffic_service`, `ndma_service`,
`social_service`; collect all signals; `signal_store.store_signals()`; `ws_manager.broadcast_signals()`.

**Endpoints:**
| Method | Path | Description |
|--------|------|-------------|
| GET | `/status` | Health, config, data-source inventory |
| POST | `/fetch` | Trigger a full fetch cycle → `FetchResult` |
| POST | `/backfill/{zone_id}?days=30` | Fill buffer with real Open-Meteo history |
| GET | `/signals/{zone_id}?hours=24` | Recent signals → `ZoneSignalSummary` |
| GET | `/signals/{zone_id}/history?days=30` | Daily aggregates |
| GET | `/features/{zone_id}` | **Pre-computed ML feature vector** (Agent 3's primary input) |
| GET | `/forecast/{zone_id}` | 16-day ECMWF/GFS daily forecast |
| GET | `/flood-forecast/{zone_id}` | 30-day GloFAS river-discharge forecast |
| GET | `/zones` | All zones + 24-h risk summary |

**Feature computation** (`_compute_ml_features`): cumulative rain 7/14/30 d, rain intensity 24 h,
max temp 24 h, heat index, consecutive hot days (>40 °C), avg humidity 24 h, terrain elevation,
drainage capacity, population density, month, is_monsoon, month_sin/cos, ndwi_delta.
**Critical detail — hourly dedup:** the 15-min scheduler stores the same rainfall reading 4×/hour;
`rain_in_window()` keeps only the **max value per hour** to prevent inflated cumulative totals.

**Severity** is computed per signal type with Pakistan-specific thresholds (rainfall mm/h,
temperature °C, discharge ratio) → integer 1–10.

### 5.2 Agent 3 — ML Predictor  (`agents/agent_predictor.py`, prefix `/api/v1/agent3`)

The forecasting brain. Produces a **30-day day-by-day** flood + heatstroke prediction per zone.
Largest, most important file (~1,560 LOC).

**Two ML models + one rule engine:**
- **XGBoost flood classifier** — trained on 6 province CSVs (1,572 monthly rows, 60 flood events,
  3.8% positive rate). Features `["Month","Temp","Rain_mm","Ice","veg","Province_enc"]`.
  `scale_pos_weight` handles class imbalance. Saved as a bundle to `models/flood_model.joblib`
  with metadata. Lazy-trained on first prediction, then cached.
- **Prophet weather forecaster** (`services/weather_forecaster.py`) — 12 models (6 provinces ×
  {temp, rain}) trained on ~7,900 daily GEE rows each (2000–2021). Forecasts days 17–30. Cached
  as 12 `.pkl` files. Anomaly-conditioned on the last 7 real days.
- **UNICEF heatwave engine** (`compute_heat_risk`) — rule-based, calibrated to the local 90th-
  percentile temperature (1960–1990 baseline) per province/month; "heatwave" = 3+ consecutive
  days above threshold; zone + seasonal multipliers.

**30-day pipeline** (`RiskPredictor.predict_30_days`):
1. Days 1–16 use the **real Open-Meteo ECMWF/GFS** forecast; days 17–30 use the **Prophet** ML
   forecast (seasonal-climatology fallback if Prophet unavailable).
2. **Pass 1** — collect 30 days of projected daily rain + temp.
3. Detect **monsoon onset** (first 3 consecutive >10 mm days after May 15).
4. **Pass 2** — per day: project features; compute the rain signal fed to XGBoost as
   `0.5·AMI + 0.3·cumulative + 0.2·monthly_pace` (AMI = exponentially-weighted antecedent
   moisture, decay 0.85); run `predict_proba`; modulate by GloFAS discharge ratio + discharge
   **momentum** (rising rivers are more dangerous); add daily-intensity and monsoon-onset bonuses;
   add Agent-1 NDWI boost.
5. **Pass 3** — apply **LSTM-inspired EWMA** smoothing (α 0.3) across the 30 days; apply
   **sigmoid calibration**; compute heat risk via the UNICEF engine; assign `dominant_factor`,
   `alert_level`, `confidence` tier per day.

**The 6 "temporal intelligence" enhancements** (model v3.0): UNICEF heatwave detection,
Antecedent Moisture Index, discharge momentum, monsoon-onset detection, EWMA temporal weighting,
sigmoid calibration. These are what make CIRO "agentic detection" rather than a flat classifier.

**Endpoints:** `GET /status`, `POST /predict/{zone_id}` (main → `ZonePrediction`),
`GET /model/info` (→ `ModelInfo`), `POST /backtest` (validates against 11 known historical events),
`POST /retrain` (deletes + retrains).

**Zone→province map:** islamabad-g10→Federal, lahore-city→Punjab, karachi-south→Sindh,
peshawar-city→Kpk, multan-city→Punjab, jacobabad-city→Sindh, sukkur-city→Sindh, quetta-city→Balochistan.
**Province encoding:** Punjab 0, Sindh 1, Federal 2, Kpk 3, Balochistan 4, Gilgit 5.

### 5.3 Agent 1 — Imagery & Geospatial  (`agents/agent_imagery.py`, prefix `/api/v1/agent1`)

Satellite ground-truth. Pulls Sentinel-2 L2A from Earth Engine, computes **NDWI = (B3−B8)/(B3+B8)**,
does 30-day change detection, sends imagery/metrics to **GeoGemma** (Gemini Vision) for structured
flood interpretation, stores an `ndwi_delta` signal that Agent 2/3 consume.

Three modes: **Full** (GEE + Gemini authenticated), **Simulation** (no GEE — realistic NDWI from
zone characteristics + season), **Fallback** (no Gemini — rule-based analysis). Always works.

**Endpoints:** `GET /status`, `POST /initialize`, `POST /analyze/{zone_id}`, `POST /analyze-all`,
`GET /latest/{zone_id}`, `GET /imagery/{zone_id}`, `GET /history/{zone_id}`, `GET /flood-map/{zone_id}`.

### 5.4 Debater — Multi-Persona LLM Debate  (`agents/agent_debater.py`, prefix `/api/v1/debater`)

For a high-risk zone, runs **4 Gemini calls**: three expert personas (**Hydrologist**,
**Meteorologist**, **Urban_Planner**) each return a `PersonaVerdict`, then a **consensus
synthesiser** produces a `DebateConsensus`. The `trigger_type` (FLOOD / HEAT / BOTH) is classified
**before** the debate and drives the persona focuses and the consensus schema — so a heat-only
event never reports a flood probability. `flood_probability` / `heat_probability` come straight
from the ML model; Gemini only decides verdict text, urgency, action window, rationale.

Gemini is called via raw REST with `responseMimeType: application/json`; wrapped in
`@gemini_retry` (5 retries, exponential backoff on HTTP 429). On any failure → structured fallback.

**Endpoints:** `POST /debate/{zone_id}`, `GET /last-results`.

### 5.5 Orchestrator — Pipeline Coordinator  (`agents/agent_orchestrator.py`, prefix `/api/v1/orchestrator`)

Runs every `ORCHESTRATOR_INTERVAL_HOURS` (2 h) and on demand. `run_cycle()`:
1. In parallel, fetch a 30-day prediction (Agent 3) + features (Agent 2) for all 8 zones.
2. Threshold-gate: keep zones with `peak_flood_risk` OR `peak_heat_risk ≥ RISK_ALERT_THRESHOLD` (0.30).
3. Run the Debater on each high-risk zone.
4. For zones where consensus urgency ∈ {ACT_NOW, PREPARE} (`agent4_ready`), call Agent 4.
5. Write a full **`OrchestrationLog`** — timestamped steps, debate results, Agent-4 responses,
   summary, timing. Keeps the last 20 runs in memory.

**Endpoints:** `GET /status`, `POST /run`, `GET /logs`, `GET /logs/{run_id}`.
This log **is** the traceable agentic-workflow evidence the rubric rewards.

### 5.6 Agent 4 — Response Commander  (`agents/agent_response.py`, prefix `/api/v1/agent4`)

The action layer. Given the debate consensus, **Gemini plans 4–8 response actions** plus a
`reasoning_trace` (4–6 steps) and a `simulation` with before/after state. Actions name real
Pakistan agencies (NDMA, PDMA, Rescue 1122, Pakistan Army/Navy) and roads (GT Road, M2, NH-55).
Per-zone static data: `ZONE_POPULATION`, `ZONE_SHELTERS`, `ZONE_HOSPITALS`. Rule-based
`_fallback_plan` if Gemini fails.

**Endpoints:** `POST /respond/{zone_id}`, `POST /respond-from-debate`, `GET /last-response/{zone_id}`,
`GET /trace/{zone_id}`, `GET /status`.

---

## 6. Data flow — the three loops

**Loop 1 — Signal fetch (every 15 min):** scheduler → `run_fetch_cycle()` → 6 sources × 8 zones →
normalise → SQLite (dedup) → WebSocket broadcast.

**Loop 2 — Prediction (on demand):** `POST /agent3/predict/{zone}` → fetch Agent-2 features +
16-day forecast + GloFAS → run XGBoost + Prophet + UNICEF engine over 30 days → `ZonePrediction`.

**Loop 3 — Orchestration (every 2 h):** `run_cycle()` → predict all 8 → threshold-gate → debate →
Agent 4 → `OrchestrationLog`. The Flutter "AI Agents" screen triggers this via `POST /orchestrator/run`.

---

## 7. Core data schemas

**Signal** (the universal record — every source normalises to this):
`signal_id` (PK, dedup key), `signal_type`, `zone_id`, `zone_name`, `lat`, `lng`, `value`,
`severity` (int 1–10), `confidence` (0–1), `source`, `timestamp` (ISO-8601 UTC), `metadata` (dict).

**DayPrediction:** `day` (1–30), `date`, `flood_risk` (0–1), `heatstroke_risk` (0–1),
`dominant_factor`, `expected_temp_c`, `expected_rain_mm`, `expected_humidity`, `alert_level`
(NONE/LOW/MODERATE/HIGH/CRITICAL), `confidence` (high/moderate/low), `data_source`.

**ZonePrediction:** `zone_id`, `zone_name`, `province`, `predicted_at`, `horizon_days`,
`current_features`, `predictions` (30× DayPrediction), `summary` (PredictionSummary:
peak flood/heat day+risk, avg flood/heat, high flood/heat days, overall_alert_level, dominant_factor).

**DebateResult:** `zone_id`, `zone_name`, `debate_timestamp`, `trigger`, `trigger_type`,
`ml_risk_input`, `zone_context`, `personas` (3× PersonaVerdict: persona, assessment, risk_vote,
key_factor, urgency), `consensus` (DebateConsensus: trigger_type, flood/heat/primary probability,
verdict, urgency, recommended_action_window_days, unanimous, rationale), `agent4_ready`.

**ResponsePlan:** `zone_id`, `zone_name`, `timestamp`, `trigger_type`, `alert_level`, `urgency`,
`debate_verdict`, `flood_probability`, `heat_probability`, `action_window_days`, `reasoning_trace`
(ReasoningStep[]), `actions` (ResponseAction[]: category, description, priority, target_population,
resources_required, estimated_time_hours, responsible_agency), `simulation` (before/after
SimulationState + effectiveness_score), `narrative`, `gemini_model`.

**OrchestrationLog:** `run_id`, `started_at`, `completed_at`, `duration_seconds`, `cycle_number`,
zone counts, `threshold`, `steps[]` (timestamped action/detail/zone/status), `debate_results[]`,
`agent4_responses[]`, `summary`.

---

## 8. Storage — SQLite (`services/signal_store.py`)

One table `signals` (signal_id PK, signal_type, zone_id, zone_name, lat, lng, value, severity,
confidence, source, timestamp, metadata JSON, created_at). Indexes on (zone_id,timestamp),
signal_type, source, severity. **Dedup** via `INSERT OR IGNORE` on the PK — fetching 100× creates
no duplicates. **Auto-prune** signals older than `SIGNAL_BUFFER_DAYS` (30) daily at 03:00 UTC.
Async via `aiosqlite`. DB path is `backend/data/signals.db`.

---

## 9. Realtime — WebSocket (`services/websocket_manager.py`, endpoint `/ws/signals`)

`WebSocketManager` keeps a client list; per-client filters `zone`, `min_severity`, `signal_types`.
On connect → `{"type":"connected", filters, active_clients}`. `broadcast_signals()` sends each
matching signal as `{"type":"signal","data":{...}}`; `broadcast_alert()` ignores filters for
critical pushes. Dead clients are pruned on send failure. Query params:
`ws://host/ws/signals?zone=<id>&min_severity=<n>`.

---

## 10. Flutter app (`ciro_app/`)

`pubspec.yaml` deps: provider ^6.1, dio ^5.4, web_socket_channel ^2.4, fl_chart ^0.66,
flutter_local_notifications ^17, url_launcher ^6.2, intl ^0.19, shimmer ^3.

```
lib/
├── main.dart                 ChangeNotifierProvider<WebSocketService>; AppShell with 3-tab
│                              BottomNav (Home, AI Agents, Live Map); WS + notification wiring
├── config/api_config.dart    baseUrl (10.0.2.2:8000 emulator), wsUrl, endpoint helpers
├── models/
│   ├── zone.dart             CiroZone + const allZones (8 zones, must match settings.py)
│   └── prediction.dart       DayPrediction / PredictionSummary / ZonePrediction + fromJson
├── services/
│   ├── api_service.dart      Dio singleton — predict, fetch, satellite, debate, response,
│   │                          orchestrator endpoints
│   ├── websocket_service.dart ChangeNotifier — connect, auto-reconnect (5s), onAlert (sev≥7)
│   └── notification_service.dart  flutter_local_notifications; tap → open zone forecast
├── theme/ciro_theme.dart     Dark theme; bg #0F1419, surface #1A2332, accent #F97316;
│                              alertColor() / severityColor() / markerColor() helpers
└── screens/
    ├── home_screen.dart       8 zone cards sorted by risk; flood/heat bars; 30-day sparkline;
    │                          next-danger-day; quick stats; live/offline badge
    ├── prediction_screen.dart 30-day detail: AI risk summary, current conditions, Agent-1
    │                          satellite status, summary cards, 30-day bar chart, day detail,
    │                          confidence-tier info
    ├── agents_screen.dart     "Run Full Pipeline" → orchestrator; shows summary, Agent-4
    │                          responses, action queue, debate transcripts, run logs + trace
    ├── live_map_screen.dart   Launches the web crisis map (/map) in browser
    └── alerts_screen.dart     WebSocket alert timeline (sev≥7) — see Known Issues §C
```

App theme intentionally mirrors the web dashboards (same colour tokens).

---

## 11. Web dashboards (`backend/static/`)

- `index.html` → served at `GET /` — dark control panel: zone grid, Agent-2 fetch/backfill,
  Agent-1 satellite analysis, Agent-3 30-day prediction chart + day table, activity log. Single
  file, no framework, calls the API via `fetch`.
- `crisis_map.html` → served at `GET /map` — full-screen interactive crisis map: heatmap of 8
  zones, 30-day timeline slider, zone cards strip, detail panel. Single file.

---

## 12. Deployment

`Dockerfile`: `python:3.11-slim`, install `requirements.txt`, copy app, `mkdir /app/data`,
`EXPOSE 8000`, `HEALTHCHECK` on `/health`, `CMD uvicorn main:app --host 0.0.0.0 --port 8000`.
Target: **Google Cloud Run**. First `/predict` call trains Prophet (~15–20 s); subsequent calls
load from `.pkl`. Run `POST /agent2/backfill/{zone}?days=30` per zone after first start to
populate real history.

---

## 13. How Antigravity fits — wording for the README

The README's mandatory **"How Antigravity is used"** section should describe **two distinct
agent layers** — keep them separate so the story is clear and true:

- **Development-time agent — Google Antigravity.** Antigravity is the agentic development
  platform used to (re)build, plan, verify and harden CIRO. It generated the **Implementation
  Plan** and **Task List** artifacts, executed the build across the backend and Flutter app,
  installed dependencies, fixed defects, ran the backend and the app in its browser to verify
  end-to-end behaviour, and produced **Walkthrough** artifacts. Its agent traces (workplan,
  reasoning, tool calls, action execution, error recovery) are submitted as the Antigravity
  trace/logs deliverable.
- **Runtime agent system — CIRO's 6 agents.** Inside the product, CIRO runs its own multi-agent
  pipeline (Agents 1–4, Debater, Orchestrator) to fuse signals, predict crises, debate severity
  and plan responses. The Orchestrator's `OrchestrationLog` is the runtime decision trace.

Both are genuine. Antigravity orchestrates the *engineering*; CIRO's agents orchestrate the
*crisis response*. Do not conflate them and do not overstate either.
