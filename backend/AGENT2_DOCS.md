# Agent 2 — Data & API Collector

## Complete Technical Documentation

> **Purpose**: Collect, normalize, and store real-time and historical crisis signals from multiple data sources. Provide pre-computed feature vectors for Agent 3 (ML Predictor) and real-time signal streams for Agent 4 (Response Orchestrator) and the Flutter mobile app.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AGENT 2: Data & API Collector                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  DATA SOURCES (6)              PROCESSING             OUTPUT        │
│  ─────────────────          ─────────────          ────────────     │
│                                                                     │
│  ┌─────────────────┐                                                │
│  │ Open-Meteo      │──┐     ┌──────────────┐     ┌────────────┐   │
│  │ (FREE, no key)  │  │     │              │     │ SQLite DB  │   │
│  └─────────────────┘  │     │  Normalize   │     │ (30-day    │   │
│  ┌─────────────────┐  │     │  to unified  │────▶│  rolling   │   │
│  │ OpenWeatherMap  │──┤     │  Signal      │     │  buffer)   │   │
│  │ (free API key)  │  │     │  schema      │     └─────┬──────┘   │
│  └─────────────────┘  │     │              │           │           │
│  ┌─────────────────┐  ├────▶│              │     ┌─────▼──────┐   │
│  │ Open-Meteo Flood│  │     │  Compute     │     │ REST API   │   │
│  │ (GloFAS, FREE)  │──┤     │  severity    │     │ endpoints  │──▶ Agent 3
│  └─────────────────┘  │     │  (1-10)      │     └─────┬──────┘   │
│  ┌─────────────────┐  │     │              │           │           │
│  │ Google Maps     │──┤     │  Deduplicate │     ┌─────▼──────┐   │
│  │ (traffic)       │  │     │              │     │ WebSocket  │   │
│  └─────────────────┘  │     └──────────────┘     │ real-time  │──▶ Flutter
│  ┌─────────────────┐  │                          │ push       │   │
│  │ NDMA Pakistan   │──┤                          └─────┬──────┘   │
│  │ (alerts)        │  │                                │           │
│  └─────────────────┘  │                          ┌─────▼──────┐   │
│  ┌─────────────────┐  │                          │ Scheduler  │   │
│  │ Social Media    │──┘                          │ (15 min    │   │
│  │ (Urdu+English)  │                             │  auto)     │   │
│  └─────────────────┘                             └────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
backend/
├── main.py                          # FastAPI app entry, lifespan, WebSocket, /metrics
├── config/
│   ├── __init__.py
│   └── settings.py                  # Zone definitions, API keys, thresholds
├── agents/
│   ├── __init__.py
│   └── agent_data_collector.py      # Agent 2 router — all endpoints + helpers
├── services/
│   ├── __init__.py
│   ├── weather_service.py           # OpenWeatherMap API (+ simulation fallback)
│   ├── openmeteo_service.py         # Open-Meteo API (FREE — current, historical, flood)
│   ├── traffic_service.py           # Google Maps Directions (traffic congestion)
│   ├── social_service.py            # Simulated social media crisis keywords
│   ├── ndma_service.py              # NDMA Pakistan disaster alerts
│   ├── signal_store.py              # SQLite persistent storage with deduplication
│   ├── scheduler.py                 # APScheduler (auto-fetch every 15 min)
│   ├── websocket_manager.py         # WebSocket manager for real-time push
│   └── retry_client.py             # HTTP client with exponential backoff + circuit breaker
├── static/
│   └── index.html                   # Agent 2 Control Panel (dark-mode dashboard)
├── data/
│   └── signals.db                   # SQLite database (auto-created on first run)
├── models/                          # (Reserved for Agent 3)
├── requirements.txt
├── Dockerfile
├── .env.example
└── .gitignore
```

---

## Unified Signal Schema

**Every data point from every source is normalized to this format before storage.**

```json
{
  "signal_id": "owm_islamabad-g10_202505181430_rain",
  "signal_type": "rainfall",
  "zone_id": "islamabad-g10",
  "zone_name": "G-10, Islamabad",
  "lat": 33.6844,
  "lng": 73.0479,
  "value": 45.2,
  "severity": 9,
  "confidence": 0.88,
  "source": "openweathermap",
  "timestamp": "2025-05-18T14:30:00Z",
  "metadata": {
    "rain_1h_mm": 45.2,
    "weather_desc": "heavy intensity rain"
  }
}
```

### Field Definitions

| Field | Type | Description |
|-------|------|-------------|
| `signal_id` | string | Unique ID (prevents duplicates). Format: `{source}_{zone}_{datetime}_{type}` |
| `signal_type` | string | One of: `rainfall`, `temperature`, `humidity`, `wind`, `cloud_coverage`, `traffic`, `social`, `official_alert`, `flood_discharge`, `forecast_7d` |
| `zone_id` | string | Zone identifier (e.g., `islamabad-g10`) |
| `zone_name` | string | Human-readable zone name |
| `lat`, `lng` | float | Zone coordinates |
| `value` | float | Primary measurement value (mm for rain, °C for temp, ratio for traffic, etc.) |
| `severity` | int | 1-10 scale. Computed per signal type using Pakistan-specific thresholds |
| `confidence` | float | 0.0-1.0. Real APIs = 0.85-0.95, simulated = 0.65-0.75 |
| `source` | string | Data source identifier |
| `timestamp` | string | ISO 8601 UTC timestamp |
| `metadata` | dict | Extra source-specific data (varies by type) |

### Severity Thresholds (Pakistan-specific)

**Rainfall (mm/hour):**
| mm/hr | Severity | Label |
|-------|----------|-------|
| < 2 | 1 | Light |
| 2-5 | 2 | Light-Moderate |
| 5-10 | 3 | Moderate |
| 10-15 | 5 | Heavy |
| 15-25 | 6 | Heavy |
| 25-35 | 7 | Very Heavy |
| 35-45 | 8 | Very Heavy |
| 45-60 | 9 | Extremely Heavy |
| 60+ | 10 | Catastrophic |

**Temperature (°C):**
| °C | Severity | Risk |
|----|----------|------|
| < 35 | 1-2 | Normal |
| 35-39 | 4-6 | Elevated heatstroke risk |
| 39-43 | 6-8 | High risk |
| 43-48 | 8-9 | Very high risk |
| 48+ | 10 | Extreme danger |

**Flood Discharge (ratio above normal):**
| Ratio | Severity | Meaning |
|-------|----------|---------|
| < 1.3 | Not reported | Normal |
| 1.3-1.5 | 2-3 | Slightly elevated |
| 1.5-2.0 | 4-5 | Elevated |
| 2.0-3.0 | 6-8 | High — flood risk |
| 3.0+ | 9-10 | Critical — flooding likely |

---

## API Endpoints

### Base URL: `http://localhost:8000/api/v1/agent2`

| Method | Endpoint | Description | Used By |
|--------|----------|-------------|---------|
| GET | `/status` | Agent health, config, API key status | Monitoring |
| POST | `/fetch` | Trigger full fetch cycle (all 6 sources, all 5 zones) | Agent 4, Scheduler, Dashboard |
| POST | `/backfill/{zone_id}?days=30` | Fill 30-day buffer with REAL historical data (free) | One-time setup |
| GET | `/signals/{zone_id}?hours=24` | Get signals for a zone in time window | Dashboard, Agent 4 |
| GET | `/signals/{zone_id}/history?days=30` | Daily aggregates for 30 days | Agent 3 |
| GET | `/features/{zone_id}` | Pre-computed ML feature vector | **Agent 3 (primary consumer)** |
| GET | `/flood-forecast/{zone_id}` | 30-day GloFAS river discharge forecast | Agent 4, Dashboard |
| GET | `/zones` | All zones with 24h risk summary | Flutter app, Dashboard |

### System Endpoints (in main.py)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI (static HTML) |
| GET | `/api` | JSON API status |
| GET | `/health` | Health check for load balancers |
| GET | `/metrics` | Signal counts, API success rates, store stats |
| WS | `/ws/signals?zone=X&min_severity=Y` | Real-time signal stream |

---

## Data Sources — Detailed

### 1. Open-Meteo (FREE — No API Key)
**File:** `services/openmeteo_service.py`

- **Current Weather + 16-day Forecast:** `api.open-meteo.com/v1/forecast`
  - Returns: temp, humidity, rain, wind, cloud cover + 16-day daily forecast
  - Produces signals: `temperature`, `humidity`, `rainfall`, `wind`, `forecast_7d`

- **30-Day Historical:** Same endpoint with `start_date` + `end_date` params
  - Used by `/backfill` endpoint to populate the buffer with real data
  - Produces signals: `temperature`, `rainfall`, `humidity` (daily records)

- **Flood Forecast (GloFAS):** `flood-api.open-meteo.com/v1/flood`
  - River discharge predictions for next 30 days
  - Compares current discharge vs mean → computes ratio
  - Only reports when ratio > 1.3 (elevated risk)
  - Produces signals: `flood_discharge`

### 2. OpenWeatherMap (Free API Key Required)
**File:** `services/weather_service.py`

- **Endpoint:** `api.openweathermap.org/data/2.5/weather`
- **Params:** lat, lon, appid, units=metric
- **Returns:** Current temp, humidity, wind, pressure, rain (if any), clouds
- **Produces signals:** `temperature`, `humidity`, `wind`, `rainfall`, `cloud_coverage`
- **Fallback:** If no API key → generates monsoon-aware simulated data

**Get a free key:** https://openweathermap.org/api (sign up, instant key, 60 calls/min)

### 3. Google Maps Traffic (API Key Required)
**File:** `services/traffic_service.py`

- **Endpoint:** `maps.googleapis.com/maps/api/directions/json`
- **Method:** Compares `duration` vs `duration_in_traffic` for a short route in the zone
- **Congestion ratio:** 1.0 = normal, 1.5 = moderate, 2.0+ = severe
- **Produces signals:** `traffic`
- **Fallback:** Simulates congestion based on time of day (PKT peak hours) + population density

### 4. NDMA Pakistan Alerts
**File:** `services/ndma_service.py`

- **Simulated** (NDMA has no clean API)
- **Alert levels:** GREEN (2), YELLOW (5), ORANGE (7), RED (9)
- **Templates:** Real NDMA bulletin language (English + province/river references)
- **Seasonal:** Higher probability during monsoon (Jun-Sep)
- **Produces signals:** `official_alert`

### 5. Social Media Keywords
**File:** `services/social_service.py`

- **Simulated** real-time social monitoring
- **Keywords monitored:**
  - Flood (English): flood, flooding, water rising, submerged, road blocked
  - Flood (Urdu): سیلاب, پانی, بارش, ڈوب, بچاؤ, راستہ بند
  - Heat (English): heatstroke, heat wave, load shedding, water shortage
  - Heat (Urdu): گرمی, لو, بجلی نہیں, پانی نہیں
- **Produces signals:** `social`
- **Confidence:** 0.60-0.65 (lower than official sources)

---

## ML Feature Vector

**Endpoint:** `GET /features/{zone_id}`

This is what **Agent 3's XGBoost model** consumes. Returns a dict of pre-computed features:

```json
{
  "cumulative_rain_7d": 180.50,
  "cumulative_rain_14d": 310.22,
  "cumulative_rain_30d": 450.80,
  "rain_intensity_24h": 45.00,
  "max_temp_24h": 42.5,
  "heat_index": 34.00,
  "consecutive_hot_days": 3,
  "avg_humidity_24h": 78.5,
  "terrain_elevation": 507,
  "drainage_capacity": 0.6,
  "population_density": 2850,
  "month": 7,
  "is_monsoon": 1,
  "month_sin": 0.866,
  "month_cos": 0.5,
  "ndwi_delta": 0.0
}
```

### Feature Definitions

| Feature | Unit | How It's Computed |
|---------|------|-------------------|
| `cumulative_rain_7d` | mm | Sum of all rainfall signals in last 7 days |
| `cumulative_rain_14d` | mm | Sum of all rainfall signals in last 14 days |
| `cumulative_rain_30d` | mm | Sum of all rainfall signals in last 30 days |
| `rain_intensity_24h` | mm | Rainfall in last 24 hours |
| `max_temp_24h` | °C | Maximum temperature in last 24 hours |
| `heat_index` | score | max_temp × (humidity/100) — combined heat danger |
| `consecutive_hot_days` | count | Days in a row with max temp > 40°C |
| `avg_humidity_24h` | % | Average humidity last 24 hours |
| `terrain_elevation` | meters | Static zone feature (from settings.py) |
| `drainage_capacity` | 0-1 | Static zone feature (1 = excellent drainage) |
| `population_density` | people/km² | Static zone feature |
| `month` | 1-12 | Current month |
| `is_monsoon` | 0/1 | 1 if month is June-September |
| `month_sin` | -1 to 1 | Cyclical encoding of month (captures seasonality) |
| `month_cos` | -1 to 1 | Cyclical encoding of month |
| `ndwi_delta` | float | **Placeholder** — will be filled by Agent 1 (imagery) |

---

## Monitored Zones

Defined in `config/settings.py`. Each zone has:

```python
{
    "id": "islamabad-g10",       # Unique identifier (use this in API calls)
    "name": "G-10, Islamabad",   # Display name
    "lat": 33.6844,              # Latitude
    "lng": 73.0479,              # Longitude
    "province": "Federal",       # Province (for NDMA alerts)
    "elevation_m": 507,          # Meters above sea level
    "drainage_capacity": 0.6,    # 0-1 (higher = better drainage)
    "population_density": 2850,  # People per sq km
}
```

### Current Zones

| ID | City | Province | Elevation | Drainage | Population |
|----|------|----------|-----------|----------|------------|
| `islamabad-g10` | G-10, Islamabad | Federal | 507m | 0.6 | 2,850/km² |
| `lahore-city` | Lahore City | Punjab | 217m | 0.4 | 6,300/km² |
| `karachi-south` | Karachi South | Sindh | 10m | 0.3 | 14,000/km² |
| `peshawar-city` | Peshawar City | KPK | 331m | 0.5 | 3,200/km² |
| `multan-city` | Multan City | Punjab | 122m | 0.35 | 4,500/km² |

### Adding a New Zone

Edit `config/settings.py` → add to the `ZONES` list:
```python
{
    "id": "quetta-city",
    "name": "Quetta City",
    "lat": 30.1798,
    "lng": 66.9750,
    "province": "Balochistan",
    "elevation_m": 1680,
    "drainage_capacity": 0.45,
    "population_density": 1800,
}
```

No other changes needed — all services automatically iterate over zones.

---

## Storage (SQLite)

**File:** `services/signal_store.py`
**Database:** `data/signals.db` (auto-created on first run)

### Table Schema
```sql
CREATE TABLE signals (
    signal_id TEXT PRIMARY KEY,         -- Unique (prevents duplicates)
    signal_type TEXT NOT NULL,
    zone_id TEXT NOT NULL,
    zone_name TEXT,
    lat REAL,
    lng REAL,
    value REAL,
    severity INTEGER,
    confidence REAL,
    source TEXT,
    timestamp TEXT,
    metadata TEXT                        -- JSON string
);

-- Indexes for fast queries
CREATE INDEX idx_zone_time ON signals(zone_id, timestamp);
CREATE INDEX idx_type ON signals(signal_type);
```

### Key Properties
- **Deduplication:** `INSERT OR IGNORE` on `signal_id` PK — calling `/fetch` 100 times won't create duplicates
- **Auto-pruning:** Signals older than 30 days are removed daily
- **Persistence:** Survives server restarts (unlike in-memory)
- **File location:** `backend/data/signals.db`

---

## Scheduler

**File:** `services/scheduler.py`

- Uses APScheduler (AsyncIOScheduler)
- Runs `fetch_all_signals` every 15 minutes automatically
- Runs daily pruning at midnight (removes > 30 day old signals)
- Started in `main.py` lifespan event

---

## WebSocket (Real-Time Push)

**File:** `services/websocket_manager.py`
**Endpoint:** `ws://localhost:8000/ws/signals`

### Connection
```javascript
// Flutter or browser client
const ws = new WebSocket("ws://localhost:8000/ws/signals?zone=islamabad-g10&min_severity=5");
ws.onmessage = (event) => {
    const signal = JSON.parse(event.data);
    // signal = { signal_id, signal_type, value, severity, ... }
};
```

### Query Params (optional filters)
- `zone` — only receive signals for this zone
- `min_severity` — only receive signals with severity >= this value

### Broadcast
After every `/fetch` cycle, all new signals are broadcast to connected WebSocket clients (filtered by their preferences).

---

## Retry & Circuit Breaker

**File:** `services/retry_client.py`

- Wraps `httpx.AsyncClient`
- **Retry:** On timeout or 5xx error → retries 3 times with exponential backoff (1s → 2s → 4s)
- **Circuit Breaker:** After 5 consecutive failures → skips that source for 60 seconds
- All services use this client for external API calls

---

## How Agent 3 Should Consume This

Agent 3 (ML Predictor) should:

1. **Call** `GET /api/v1/agent2/features/{zone_id}` to get the feature vector
2. **Feed** the features dict directly into the trained XGBoost model
3. **Output** flood_risk (0-1) and heatstroke_risk (0-1) for next 30 days

Example integration:
```python
import httpx
import joblib

model = joblib.load("models/flood_model.joblib")

async def predict_for_zone(zone_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8000/api/v1/agent2/features/{zone_id}")
        data = response.json()
        features = data["features"]
        
        # Convert to model input format
        X = [list(features.values())]
        flood_probability = model.predict_proba(X)[0][1]
        
        return {"zone_id": zone_id, "flood_risk": flood_probability}
```

---

## How Agent 4 Should Consume This

Agent 4 (Response Orchestrator) should:

1. **Monitor** via WebSocket — get real-time signals as they arrive
2. **Check** `GET /api/v1/agent2/zones` for current risk summary across all zones
3. **Get predictions** from Agent 3 (which itself gets features from Agent 2)
4. **Trigger actions** when severity/risk crosses thresholds

---

## How to Run

```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # Add API keys (optional — works without them)
uvicorn main:app --reload --port 8000
```

**Dashboard:** http://localhost:8000
**API Docs (Swagger):** http://localhost:8000/docs
**Health Check:** http://localhost:8000/health

---

## Environment Variables (.env)

```
# Required: None (works with simulation)
# Recommended: OpenWeatherMap (real weather data)
OPENWEATHER_API_KEY=your_key_here

# Optional: Google Maps (traffic data)
GOOGLE_MAPS_API_KEY=your_key_here

# Optional: Firebase (production storage)
FIREBASE_PROJECT_ID=
FIREBASE_CREDENTIALS_PATH=
```

---

## What's Done vs What's Left

| Component | Status | Notes |
|-----------|--------|-------|
| Weather data collection | ✅ Done | OpenWeatherMap + Open-Meteo (real data) |
| Historical backfill | ✅ Done | 30-day real data via Open-Meteo (free) |
| Flood forecast (GloFAS) | ✅ Done | 30-day river discharge prediction |
| Traffic monitoring | ✅ Done | Google Maps + simulation |
| Social signal monitoring | ✅ Done | Simulated Urdu+English keywords |
| NDMA official alerts | ✅ Done | Simulated with real NDMA language |
| SQLite persistent storage | ✅ Done | Deduplication, indexed, auto-prune |
| Auto-scheduling (15 min) | ✅ Done | APScheduler |
| WebSocket real-time push | ✅ Done | Filtered streams to Flutter |
| ML feature computation | ✅ Done | 16-feature vector for XGBoost |
| Retry + circuit breaker | ✅ Done | Exponential backoff |
| Dashboard UI | ✅ Done | Dark-mode control panel |
| Agent 3 (ML Predictor) | ❌ Next | Train XGBoost on Kaggle datasets |
| Agent 4 (Orchestrator) | ❌ Planned | Response simulation |
| Agent 1 (Imagery) | ❌ Planned | GeoGemma + Earth Engine |
| Flutter mobile app | ❌ Planned | Map + alerts + WebSocket |
