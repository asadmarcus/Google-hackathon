# CIRO Backend

> FastAPI server powering the CIRO crisis prediction system.

---

## Quick Start

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Dashboard: http://localhost:8000

---

## Requirements

- Python 3.11+
- ~500MB disk for Prophet models (auto-generated on first prediction call)
- No API keys required (Open-Meteo is free). Optional: OpenWeatherMap, Google Maps.

---

## Key Endpoints

### Agent 2 — Data Collection
```
POST /api/v1/agent2/fetch                    # Trigger data fetch (all zones)
POST /api/v1/agent2/backfill/{zone_id}?days=30  # Fill 30-day buffer
GET  /api/v1/agent2/forecast/{zone_id}       # 16-day ECMWF forecast
GET  /api/v1/agent2/flood-forecast/{zone_id} # 30-day GloFAS discharge
GET  /api/v1/agent2/features/{zone_id}       # ML feature vector
GET  /api/v1/agent2/signals/{zone_id}        # Raw signals
GET  /api/v1/agent2/zones                    # All zones + status
```

### Agent 3 — ML Prediction
```
POST /api/v1/agent3/predict/{zone_id}        # 30-day prediction (main endpoint)
GET  /api/v1/agent3/status                   # Model health
GET  /api/v1/agent3/model/info               # Training metadata
POST /api/v1/agent3/backtest                  # Validate on historical floods
```

### WebSocket
```
ws://localhost:8000/ws/signals?zone={zone_id}&min_severity={1-10}
```

---

## ML Pipeline Summary

```
┌─────────────────┐     ┌─────────────────┐     ┌───────────────┐
│  Open-Meteo     │     │  Prophet         │     │  XGBoost      │
│  ECMWF/GFS     │     │  (22yr daily)    │     │  Flood Model  │
│  Days 1-16     │     │  Days 17-30      │     │  (1572 samples│
│  (REAL weather) │     │  (ML forecast)   │     │  60 floods)   │
└────────┬────────┘     └────────┬─────────┘     └───────┬───────┘
         │                       │                        │
         └───────────┬───────────┘                        │
                     │                                    │
                     ▼                                    │
         ┌───────────────────────┐                       │
         │  Cumulative Rain      │                       │
         │  (antecedent moisture)│───────────────────────▶│
         └───────────────────────┘                       │
                                                         ▼
         ┌───────────────────────┐              ┌────────────────┐
         │  GloFAS Discharge     │──────────────│  Daily Flood   │
         │  (30-day hydrology)   │  modulation  │  Probability   │
         └───────────────────────┘              └────────────────┘
```

---

## Environment Variables (.env)

```env
# Optional — system works WITHOUT any keys
OPENWEATHER_API_KEY=           # openweathermap.org (optional)
GOOGLE_MAPS_API_KEY=           # console.cloud.google.com (optional)
FIREBASE_PROJECT_ID=           # For production Firestore (optional)
FIREBASE_CREDENTIALS_PATH=     # Path to service account JSON (optional)
```

---

## First Run Notes

1. **Prophet training**: First `POST /predict/{zone_id}` takes ~15-20s (trains 12 models). Subsequent calls are instant.
2. **Signal database**: `data/signals.db` is auto-created on first fetch.
3. **Backfill recommended**: Run `POST /api/v1/agent2/backfill/{zone_id}?days=30` for each zone after first start.
4. **Docker**: `docker build -t ciro . && docker run -p 8000:8000 ciro`

---

## Documentation

- **[AGENT2_DOCS.md](AGENT2_DOCS.md)** — Agent 2 data collection: signal schema, all endpoints, severity thresholds, how to add zones
- **[AGENT3_DOCS.md](AGENT3_DOCS.md)** — Agent 3 ML prediction: Prophet + XGBoost architecture, training data, prediction pipeline, output schemas
- **[../README.md](../README.md)** — Project overview, architecture, all zones, tech stack
