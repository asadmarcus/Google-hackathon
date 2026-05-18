# CIRO — Crisis Intelligence & Response Orchestrator

> Multi-Agent AI System for Urban Crisis Prediction & Response in Pakistan

[![Google Antigravity Hackathon](https://img.shields.io/badge/Google-Antigravity%20Hackathon-orange)]()
[![Challenge 3](https://img.shields.io/badge/Challenge-3%20Crisis%20Intelligence-blue)]()
[![Python](https://img.shields.io/badge/Python-3.11+-green)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)]()
[![XGBoost](https://img.shields.io/badge/XGBoost-2.1-blue)]()
[![Prophet](https://img.shields.io/badge/Prophet-1.1.5-purple)]()

---

## What is CIRO?

CIRO is a **4-agent AI system** that predicts and responds to urban crises (floods and heatwaves) in Pakistan. It uses **two ML models working together**:

- **Prophet** (time series) — forecasts future weather conditions using 22 years of daily satellite data
- **XGBoost** (classification) — predicts whether those conditions cause floods, using real Pakistan flood event data

Combined with real-time meteorological forecasts (ECMWF/GFS via Open-Meteo) and river discharge data (GloFAS), CIRO provides a **30-day forward-looking crisis risk assessment** for 8 Pakistani cities across 5 provinces.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    CIRO — 30-Day Prediction Pipeline                      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Days 1-7         Days 8-16         Days 17-30                           │
│  ─────────        ──────────        ──────────                           │
│  ECMWF/GFS        ECMWF Extended    Prophet ML                           │
│  Real Forecast    Forecast          (22yr trained)                        │
│  ↓                ↓                 ↓                                    │
│  confidence:      confidence:       confidence:                           │
│  HIGH             MODERATE          LOW                                   │
│                                                                          │
│           ALL → XGBoost Flood Classifier + PMD Heat Engine               │
│                         ↓                                                │
│              30-day risk timeline + alerts                                │
│                         ↓                                                │
│              Flutter App + WebSocket + Dashboard                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | Python FastAPI | REST API + WebSocket |
| ML (Flood) | XGBoost Classifier | Flood probability from weather features |
| ML (Weather) | Facebook Prophet | Temperature & rainfall forecasting (days 17-30) |
| Data | Open-Meteo (ECMWF/GFS) | Real 16-day weather forecast (free, no API key) |
| Hydrology | GloFAS (via Open-Meteo) | 30-day river discharge forecast |
| Database | SQLite | Signal storage with deduplication |
| Real-time | WebSocket | Push signals to Flutter app |
| Mobile | Flutter | Cross-platform mobile app |
| Hosting | Google Cloud Run + Docker | Containerized deployment |

---

## Agent Architecture

### Agent 2 — Data & API Collector ✅ DONE
Fetches real-time data from 6 sources, stores in SQLite, pushes via WebSocket.
- Open-Meteo (weather + 16-day forecast + GloFAS flood)
- OpenWeatherMap, Google Maps traffic, NDMA alerts, social signals
- Auto-polls every 15 minutes via APScheduler
- **Docs:** [`backend/AGENT2_DOCS.md`](backend/AGENT2_DOCS.md)

### Agent 3 — ML Predictor ✅ DONE
Dual-model prediction engine for 30-day crisis forecasting.
- Prophet trained on 22 years of GEE daily data (temp + rain, 6 provinces)
- XGBoost trained on real Pakistan flood events (1572 samples, 60 floods)
- PMD-calibrated heat risk engine (rule-based, matches official thresholds)
- **Docs:** [`backend/AGENT3_DOCS.md`](backend/AGENT3_DOCS.md)

### Agent 1 — Imagery & Geospatial 🔲 PLANNED
GeoGemma + Google Earth Engine for satellite change detection.

### Agent 4 — Response Orchestrator 🔲 PLANNED
Alert dispatch, evacuation routing, resource coordination.

---

## Monitored Zones (8 cities, 5 provinces)

| Zone ID | City | Province | Lat/Lng | Why it matters |
|---------|------|----------|---------|----------------|
| `islamabad-g10` | G-10, Islamabad | Federal | 33.68, 73.05 | Capital, moderate flood risk |
| `lahore-city` | Lahore City | Punjab | 31.52, 74.36 | Dense urban, active heatwave zone |
| `karachi-south` | Karachi South | Sindh | 24.86, 67.00 | Coastal megacity, flash flood risk |
| `peshawar-city` | Peshawar City | KPK | 34.02, 71.52 | Mountain runoff floods |
| `multan-city` | Multan City | Punjab | 30.16, 71.52 | Extreme heat zone (47°C+) |
| `jacobabad-city` | Jacobabad City | Sindh | 28.28, 68.44 | **Hottest city in Pakistan** (52°C recorded) |
| `sukkur-city` | Sukkur City | Sindh | 27.71, 68.86 | **2022 flood epicenter** (Indus river) |
| `quetta-city` | Quetta City | Balochistan | 30.18, 66.98 | Flash floods from surrounding hills |

---

## Quick Start

```bash
cd backend

# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Set API keys in .env — system works WITHOUT them
cp .env.example .env

# 3. Run the server
uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Open dashboard
# http://localhost:8000
```

### First run behavior:
- **Agent 2**: Immediately begins fetching data. Run `POST /api/v1/agent2/fetch` to trigger manually.
- **Agent 3**: First prediction call trains Prophet models (~15-20s). Subsequent calls use cached models.
- **Backfill**: Run `POST /api/v1/agent2/backfill/{zone_id}?days=30` to fill historical buffer.

---

## Docker

```bash
docker build -t ciro-backend ./backend
docker run -p 8000:8000 ciro-backend
```

---

## Project Structure

```
Fuckathon-main/
├── README.md                          ← You are here
└── backend/
    ├── main.py                        # FastAPI app + WebSocket + scheduler
    ├── config/
    │   └── settings.py                # 8 zones, API keys, thresholds
    ├── agents/
    │   ├── agent_data_collector.py    # Agent 2: data fetching + endpoints
    │   └── agent_predictor.py         # Agent 3: ML prediction + endpoints
    ├── services/
    │   ├── openmeteo_service.py       # Open-Meteo: 16-day forecast + GloFAS 30-day
    │   ├── weather_forecaster.py      # Prophet: trained on 22yr daily Pakistan data
    │   ├── weather_service.py         # OpenWeatherMap (optional, needs API key)
    │   ├── traffic_service.py         # Google Maps traffic
    │   ├── social_service.py          # Crisis keyword simulation (confidence=0.50)
    │   ├── ndma_service.py            # NDMA alert simulation (confidence=0.50)
    │   ├── signal_store.py            # SQLite with INSERT OR IGNORE dedup
    │   ├── scheduler.py               # APScheduler (15-min auto-fetch)
    │   ├── websocket_manager.py       # Real-time push to Flutter
    │   └── retry_client.py            # HTTP retry + circuit breaker
    ├── models/
    │   ├── flood_model.joblib         # Trained XGBoost flood classifier
    │   └── prophet/                   # Trained Prophet models (auto-generated)
    │       ├── Punjab_temp_prophet.pkl
    │       ├── Punjab_rain_prophet.pkl
    │       └── ... (12 models: 6 provinces × 2 variables)
    ├── data/
    │   ├── signals.db                 # SQLite signal database (auto-created)
    │   └── training/                  # 22 years of daily Pakistan climate data
    │       ├── Punjab_training.csv    # Monthly aggregates for XGBoost
    │       ├── Punjab/                # Daily data for Prophet (Temp.csv, Pre.csv)
    │       ├── Sindh_training.csv
    │       ├── Sindh/
    │       ├── Federal_training.csv
    │       ├── Federal/
    │       ├── Kpk_training.csv
    │       ├── Kpk/
    │       ├── Balochistan_training.csv
    │       ├── Balochistan/
    │       ├── Gilgit_training.csv
    │       ├── Gilgit/
    │       ├── Rainfall_1901_2016_PAK.csv    # 116 years national rainfall
    │       └── Tempreture_1901_2016_Pakistan.csv  # 116 years national temp
    ├── static/
    │   └── index.html                 # Dark-mode control panel dashboard
    ├── AGENT2_DOCS.md                 # Agent 2 technical reference
    ├── AGENT3_DOCS.md                 # Agent 3 technical reference
    ├── requirements.txt
    ├── Dockerfile
    └── .env.example
```

---

## Training Data

All ML models are trained on **REAL Pakistan data**:

| Dataset | Source | Rows | Coverage |
|---------|--------|------|----------|
| Province training CSVs | Google Earth Engine (MODIS + CHIRPS) | 1,572 | 2000-2021, monthly, 6 provinces |
| Province daily CSVs | GEE (Temp.csv, Pre.csv per province) | ~8,000/province | 2000-2021, daily |
| National rainfall | Pakistan Meteorological Dept | 1,392 | 1901-2016, monthly |
| National temperature | Pakistan Meteorological Dept | 1,392 | 1901-2016, monthly |
| Flood events | NDMA Pakistan records | 60 events | Labeled in training CSVs |

---

## API Endpoints Summary

### Agent 2 (Data Collection)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/agent2/status` | Health + config |
| POST | `/api/v1/agent2/fetch` | Trigger full fetch cycle |
| POST | `/api/v1/agent2/backfill/{zone_id}?days=30` | Fill historical buffer |
| GET | `/api/v1/agent2/signals/{zone_id}?hours=24` | Recent signals |
| GET | `/api/v1/agent2/features/{zone_id}` | Pre-computed ML features |
| GET | `/api/v1/agent2/forecast/{zone_id}` | 16-day ECMWF forecast |
| GET | `/api/v1/agent2/flood-forecast/{zone_id}` | 30-day GloFAS discharge |
| GET | `/api/v1/agent2/zones` | All zones + risk summary |

### Agent 3 (ML Prediction)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/agent3/status` | Model health + loaded status |
| POST | `/api/v1/agent3/predict/{zone_id}` | **30-day flood + heat prediction** |
| GET | `/api/v1/agent3/model/info` | Model metadata + accuracy |
| POST | `/api/v1/agent3/backtest` | Validate against historical floods |

### General
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard (static/index.html) |
| WS | `/ws/signals?zone=X&min_severity=Y` | Real-time signal stream |

---

## Key Design Decisions

1. **Two-model architecture**: Prophet forecasts weather, XGBoost predicts floods. Each model does what it's best at.
2. **Cumulative rain for flood model**: XGBoost receives cumulative rainfall *to date* (antecedent moisture) — not daily×30. Floods happen after sustained rain, not because of drizzle.
3. **GloFAS per-day modulation**: Base flood risk comes from XGBoost; daily variation from real river discharge data.
4. **Honest confidence labels**: Days 1-7 = HIGH (real ECMWF), 8-16 = MODERATE (extended), 17-30 = LOW (ML forecast).
5. **Simulated sources labeled**: NDMA + Social services marked confidence=0.50 to show they're simulated.
6. **Hourly deduplication**: Feature computation deduplicates rain signals per hour to prevent inflation from 15-min polling.

---

## Team

Built for the **Google Antigravity Hackathon (AI-Seekh)** — Challenge 3: Crisis Intelligence & Response Orchestrator.
