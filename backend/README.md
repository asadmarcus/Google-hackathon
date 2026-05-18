# CIRO — Crisis Intelligence & Response Orchestrator

> Multi-Agent AI System for Urban Crisis Prediction & Response

[![Google Antigravity Hackathon](https://img.shields.io/badge/Google-Antigravity%20Hackathon-orange)]()
[![Challenge 3](https://img.shields.io/badge/Challenge-3%20Crisis%20Intelligence-blue)]()
[![Python](https://img.shields.io/badge/Python-3.11+-green)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)]()

---

## What is CIRO?

CIRO is a **4-agent AI system** that predicts and responds to urban crises (floods, heatwaves) in Pakistan using satellite imagery, real-time APIs, and machine learning — with a **30-day bidirectional moat** (30 days historical + 30 days predictive).

```
┌──────────────────────────────────────────────────────────┐
│              GOOGLE ANTIGRAVITY (Orchestrator)            │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Agent 1          Agent 2          Agent 3     Agent 4   │
│  Imagery &        Data & API       Predictive  Response  │
│  Geospatial       Collector        Model (ML)  Packager  │
│  (planned)        (DONE)           (next)      (planned) │
│                                                          │
│         └──────────────┼──────────────┘                  │
│                        ▼                                 │
│              ┌──────────────────┐                        │
│              │  Flutter Mobile  │                        │
│              │  App + Dashboard │                        │
│              └──────────────────┘                        │
└──────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python FastAPI |
| Mobile | Flutter (cross-platform) |
| ML | XGBoost + Prophet |
| Database | SQLite (dev) / Firebase Firestore (prod) |
| Real-time | WebSocket |
| Hosting | Google Cloud Run + Docker |
| Orchestration | Google Antigravity |

---

## Project Structure

```
Fuckathon-main/
└── backend/
    ├── main.py                    # FastAPI app + WebSocket + scheduler
    ├── config/settings.py         # Zones, API keys, thresholds
    ├── agents/
    │   └── agent_data_collector.py  # Agent 2 (active)
    ├── services/
    │   ├── weather_service.py     # OpenWeatherMap
    │   ├── openmeteo_service.py   # Open-Meteo (FREE)
    │   ├── traffic_service.py     # Google Maps
    │   ├── social_service.py      # Crisis keywords (Urdu+English)
    │   ├── ndma_service.py        # NDMA disaster alerts
    │   ├── signal_store.py        # SQLite persistent storage
    │   ├── scheduler.py           # Auto-fetch every 15 min
    │   ├── websocket_manager.py   # Real-time push to Flutter
    │   └── retry_client.py        # HTTP retry + circuit breaker
    ├── models/                    # Agent 3 ML models (next)
    ├── static/index.html          # Dashboard UI
    ├── data/signals.db            # SQLite database
    ├── AGENT2_DOCS.md             # Full Agent 2 technical docs
    ├── Dockerfile
    └── requirements.txt
```

---

## Quick Start

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
cp .env.example .env             # Optional — works without API keys
uvicorn main:app --reload --port 8000
```

**Dashboard:** http://localhost:8000
**Swagger API Docs:** http://localhost:8000/docs

---

## Agents Status

| Agent | Role | Status | Docs |
|-------|------|--------|------|
| Agent 1 | Imagery & Geospatial (GeoGemma, Earth Engine) | Planned | — |
| **Agent 2** | **Data & API Collector (6 sources, 5 zones)** | **Done** | [AGENT2_DOCS.md](./AGENT2_DOCS.md) |
| Agent 3 | Predictive Model (XGBoost, 30-day forecast) | Next | — |
| Agent 4 | Response Orchestrator (simulate actions) | Planned | — |

---

## Data Sources (Agent 2)

| Source | API Key? | What it provides |
|--------|----------|-----------------|
| Open-Meteo | No (FREE) | Current weather + 7-day forecast + 30-day historical |
| Open-Meteo Flood (GloFAS) | No (FREE) | 30-day river discharge flood forecast |
| OpenWeatherMap | Yes (free) | Real-time temp, rain, humidity, wind |
| Google Maps | Yes ($200 credit) | Traffic congestion |
| NDMA Pakistan | No | Official disaster alerts (simulated) |
| Social Media | No | Urdu+English crisis keywords (simulated) |

**Works with zero API keys** — all services fall back to realistic monsoon-aware simulation.

---

## Monitored Zones

| Zone ID | City | Province |
|---------|------|----------|
| `islamabad-g10` | G-10, Islamabad | Federal |
| `lahore-city` | Lahore City | Punjab |
| `karachi-south` | Karachi South | Sindh |
| `peshawar-city` | Peshawar City | KPK |
| `multan-city` | Multan City | Punjab |

---

## Key Features

- **30-day bidirectional moat** — historical buffer + forward prediction
- **6 real data sources** — multi-source signal fusion
- **Pakistan-specific thresholds** — rain, temp, flood discharge severity tuned for local climate
- **Urdu + English** — social monitoring in both languages
- **SQLite persistence** — data survives restarts, deduplication built-in
- **Auto-scheduling** — fetches every 15 minutes without intervention
- **WebSocket** — real-time push to Flutter app
- **Circuit breaker** — gracefully handles API failures
- **Zero-config demo** — runs immediately with no API keys

---

## Datasets (for Agent 3 training)

- [Flood Prediction Dataset](https://www.kaggle.com/datasets/naiyakhalid/flood-prediction-dataset)
- [Flood Area Segmentation](https://www.kaggle.com/datasets/faizalkarim/flood-area-segmentation)
- [Pakistan Flood Disasters 2010-2025](https://www.kaggle.com/datasets/alitaqishah/pakistan-flood-disasters-dataset-20102025)
- [Pakistan Climate Predictive Modelling](https://github.com/ahsan-javed-ds/pakistan-climate-data-analysis-and-predictive-modelling)
- [Flood Prediction Pakistan ML](https://github.com/hamza100x/final-year-project-flood-prediction-pakistan-ml)
- [FloodCast (HydroPML)](https://github.com/HydroPML/FloodCast)
- [Flood Prediction Dataset (Bangladesh+)](https://github.com/n-gauhar/Flood-prediction)

---

## Team

**Competition:** Google Antigravity Hackathon (AI-Seekh)
**Challenge:** #3 — Crisis Intelligence & Response Orchestrator
**GitHub:** https://github.com/asadmarcus/Fuckathon

---

## License

MIT
