# CIRO — Complete Reverse-Engineering Blueprint for Antigravity

> **Purpose**: This document lets you recreate the entire CIRO project from scratch in Antigravity's workspace, prompt by prompt. Feed sections to Antigravity in order. Each section is a self-contained build step.

---

## What CIRO Is

**CIRO (Crisis Intelligence & Response Orchestrator)** is a multi-agent AI system for predicting urban flood and heatwave crises in Pakistan. Built for the **Google Antigravity Hackathon (AI-Seekh) — Challenge 3**.

**Two components:**
1. `backend/` — Python FastAPI server with 6 AI agents, ML models, SQLite, WebSocket
2. `ciro_app/` — Flutter mobile app (Android/iOS) with 5 screens

---

## Part 1 — Project Scaffold

### Prompt 1.1 — Root structure

```
Create this folder structure at the project root:

Fuckathon/
├── backend/
│   ├── agents/
│   ├── services/
│   ├── models/
│   │   └── prophet/
│   ├── data/
│   │   └── training/
│   ├── config/
│   └── static/
├── ciro_app/
│   └── lib/
│       ├── config/
│       ├── models/
│       ├── services/
│       ├── screens/
│       └── theme/
└── docs/
```

---

## Part 2 — Backend: Config & Settings

### Prompt 2.1 — `backend/config/settings.py`

```python
"""
CIRO Configuration — 8 monitored zones, API keys, thresholds.
Uses Pydantic BaseSettings for env-var loading.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Dict, Any
import os


class ZoneConfig:
    def __init__(self, id, name, lat, lng, province, elevation_m,
                 drainage_capacity, population_density):
        self.id = id
        self.name = name
        self.lat = lat
        self.lng = lng
        self.province = province
        self.elevation_m = elevation_m
        self.drainage_capacity = drainage_capacity
        self.population_density = population_density

    def dict(self):
        return {
            "id": self.id, "name": self.name, "lat": self.lat,
            "lng": self.lng, "province": self.province,
            "elevation_m": self.elevation_m,
            "drainage_capacity": self.drainage_capacity,
            "population_density": self.population_density,
        }


ZONES_RAW = [
    ZoneConfig("islamabad-g10", "G-10, Islamabad", 33.6844, 73.0479, "Federal",    507,  0.6,  2850),
    ZoneConfig("lahore-city",   "Lahore City",      31.5204, 74.3587, "Punjab",     217,  0.4,  6300),
    ZoneConfig("karachi-south", "Karachi South",    24.8607, 67.0011, "Sindh",       10,  0.3, 14000),
    ZoneConfig("peshawar-city", "Peshawar City",    34.0151, 71.5249, "KPK",         331,  0.5,  3200),
    ZoneConfig("multan-city",   "Multan City",      30.1575, 71.5249, "Punjab",      122,  0.35, 4500),
    ZoneConfig("jacobabad-city","Jacobabad City",   28.2769, 68.4368, "Sindh",        55,  0.25, 2100),
    ZoneConfig("sukkur-city",   "Sukkur City",      27.7052, 68.8574, "Sindh",        66,  0.3,  3800),
    ZoneConfig("quetta-city",   "Quetta City",      30.1798, 66.9750, "Balochistan", 1680, 0.35, 1800),
]


class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: str = Field(default="development")

    # API Keys (all optional — system works without them)
    OPENWEATHER_API_KEY: str = Field(default="")
    GOOGLE_MAPS_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    FIREBASE_PROJECT_ID: str = Field(default="")
    FIREBASE_CREDENTIALS_PATH: str = Field(default="")

    # Scheduler
    FETCH_INTERVAL_MINUTES: int = Field(default=15)
    SIGNAL_BUFFER_DAYS: int = Field(default=30)

    # Orchestrator
    ORCHESTRATOR_INTERVAL_HOURS: int = Field(default=2)
    DEBATE_LLM_MODEL: str = Field(default="gemini-1.5-flash")

    # Thresholds
    SEVERITY_THRESHOLD: float = Field(default=0.7)
    RISK_ALERT_THRESHOLD: float = Field(default=0.30)

    # Zone list (computed)
    ZONES: list = Field(default_factory=lambda: ZONES_RAW)

    def get_zone(self, zone_id: str):
        return next((z for z in self.ZONES if z.id == zone_id), None)

    def get_zone_dict(self, zone_id: str):
        z = self.get_zone(zone_id)
        return z.dict() if z else None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
```

### Prompt 2.2 — `backend/.env.example`

```
OPENWEATHER_API_KEY=
GOOGLE_MAPS_API_KEY=
GEMINI_API_KEY=
FIREBASE_PROJECT_ID=
FIREBASE_CREDENTIALS_PATH=
ENVIRONMENT=development
```

### Prompt 2.3 — `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.9.0
pydantic-settings==2.5.2
websockets==12.0
httpx==0.27.0
xgboost==2.1.0
prophet==1.1.5
joblib==1.4.0
pandas==2.2.0
numpy==1.26.0
scikit-learn==1.5.0
apscheduler==3.10.4
earthengine-api==0.1.411
google-auth==2.29.0
python-dotenv==1.0.1
aiosqlite==0.20.0
```

---

## Part 3 — Backend: Services

### Prompt 3.1 — `backend/services/signal_store.py`

SQLite manager with async operations, deduplication, and rolling 30-day buffer.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    value REAL,
    severity INTEGER DEFAULT 0,
    confidence REAL DEFAULT 1.0,
    source TEXT,
    timestamp TEXT NOT NULL,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_zone_time ON signals(zone_id, timestamp);
```

**Key methods:**
- `async initialize()` — create tables
- `async store_signal(signal: dict)` — INSERT OR IGNORE (dedup by signal_id)
- `async get_signals(zone_id, hours=24, limit=100)` — paginated fetch
- `async prune_expired(buffer_days=30)` — delete old signals
- `async get_all_metrics()` — count per zone/type

**Deduplication rule:** `signal_id` is `f"{zone_id}_{signal_type}_{source}_{hour_bucket}"` where `hour_bucket` truncates timestamp to the hour. This prevents inflation from 15-min polling.

### Prompt 3.2 — `backend/services/websocket_manager.py`

Real-time push manager for Flutter WebSocket clients.

**WebSocketClient dataclass:**
```python
@dataclass
class WebSocketClient:
    websocket: WebSocket
    client_id: str
    zone_filter: Optional[str] = None
    min_severity: int = 0
    connected_at: datetime = field(default_factory=datetime.utcnow)
```

**Key methods:**
- `async connect(websocket, zone_filter, min_severity)` → returns client, sends `{"type": "connected", "filters": {...}}`
- `async disconnect(client)` — remove from pool
- `async broadcast_signal(signal_data: dict)` — send to matching clients
- `async send_alert(zone_id, alert_data)` — high-priority push
- `get_metrics()` — active_connections, zones_subscribed

**Message format:**
```json
{"type": "signal",  "data": { ...signal fields... }}
{"type": "alert",   "priority": "critical", "data": { ... }}
{"type": "connected", "filters": {"zone": null, "min_severity": 0}}
```

### Prompt 3.3 — `backend/services/retry_client.py`

HTTP client with exponential backoff and circuit breaker.

**Features:**
- Uses `httpx.AsyncClient`
- Max retries: 3, backoff: 1s → 2s → 4s
- Circuit breaker: opens after 5 consecutive failures, resets after 60s
- Metrics tracking: total_calls, successes, failures, circuit_opens
- Class-level registry: `RetryClient._instances` dict keyed by name
- `RetryClient.get_all_metrics()` — static method returning all instance metrics

### Prompt 3.4 — `backend/services/openmeteo_service.py`

Free weather API (no API key needed). Uses Open-Meteo and GloFAS endpoints.

**Base URLs:**
- Weather: `https://api.open-meteo.com/v1/forecast`
- GloFAS: `https://flood-api.open-meteo.com/v1/flood`

**Key methods:**
```python
async def fetch_forecast(lat, lng, days=16) -> dict:
    # Returns: temperature_2m, precipitation, windspeed_10m (hourly)
    # Params: hourly=temperature_2m,precipitation,windspeed_10m&forecast_days=16

async def fetch_flood_forecast(lat, lng, days=30) -> dict:
    # Returns: river_discharge (daily, GloFAS ensemble)
    # Params: daily=river_discharge&forecast_days=30

async def fetch_historical(lat, lng, start_date, end_date) -> dict:
    # Returns: historical temp + precip for backfill
    # Params: start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

### Prompt 3.5 — `backend/services/scheduler.py`

APScheduler wrapper for periodic data collection.

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

class CIROScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler()
        self._is_running = False

    async def start(self, fetch_callback, prune_callback):
        # Add fetch job: every FETCH_INTERVAL_MINUTES
        # Add prune job: every 6 hours
        self._scheduler.start()
        self._is_running = True

    def add_orchestrator_job(self, orchestrator_callback):
        # Add orchestrator job: every ORCHESTRATOR_INTERVAL_HOURS

    async def shutdown(self):
        self._scheduler.shutdown(wait=False)
        self._is_running = False

    def get_status(self) -> dict:
        # Returns jobs list with next_run_time
```

### Prompt 3.6 — `backend/services/weather_forecaster.py`

Prophet time-series forecaster trained on 22 years of Pakistan climate data.

**Model files:** `backend/models/prophet/{Province}_{variable}_prophet.pkl`
- 6 provinces: Punjab, Sindh, Federal, Kpk, Balochistan, Gilgit
- 2 variables per province: temp, rain
- Total: 12 .pkl files

**Province → CSV folder mapping:**
```python
PROVINCE_MAP = {
    "Punjab": "Punjab", "Sindh": "Sindh", "Federal": "Federal",
    "KPK": "Kpk", "Balochistan": "Balochistan", "Gilgit": "Gilgit"
}
```

**Training data columns** (from `data/training/{Province}/Temp.csv` and `Pre.csv`):
- `ds` (datetime), `y` (value)

**Key methods:**
```python
def load_or_train_model(province: str, variable: str) -> Prophet:
    # Checks models/prophet/ for saved .pkl
    # If missing: loads CSV, trains Prophet(yearly_seasonality=True), saves

def forecast_temperature(province: str, days: int = 30) -> list[dict]:
    # Returns [{ds, yhat, yhat_lower, yhat_upper}, ...]

def forecast_rainfall(province: str, days: int = 30) -> list[dict]:
    # Returns [{ds, yhat, yhat_lower, yhat_upper}, ...]

def forecast_with_conditioning(province, variable, days, anomaly_offset=0.0):
    # Adds anomaly_offset to yhat (for conditioning on real recent data)
```

**Caching:** Use `joblib.Memory` or a dict cache so Prophet is only trained once per session.

### Prompt 3.7 — Simulated services (3 files)

#### `backend/services/weather_service.py`
OpenWeatherMap integration (optional, requires API key).
- `async fetch_current(lat, lng)` → temperature, humidity, description
- Returns `None` gracefully if no API key
- confidence: 0.85

#### `backend/services/ndma_service.py`
NDMA Pakistan alert simulation (no real API exists).
- `async get_alerts(zone_id)` → simulated alert list based on zone + season
- confidence: 0.50 (labeled as simulated)
- Signal type: `ndma_alert`

#### `backend/services/social_service.py`
Social media crisis keyword simulation.
- `async get_signals(zone_id)` → simulated urgency signals
- Keywords: flood, barish, sayl, heatwave, garmi (Urdu + English)
- confidence: 0.50 (labeled as simulated)
- Signal type: `social_signal`

---

## Part 4 — Backend: Agents

### Prompt 4.1 — `backend/agents/agent_data_collector.py`

**Agent 2 — Data & API Collector**

FastAPI router prefix: `/api/v1/agent2`

**Endpoints:**
```
GET  /status                     → health + config
POST /fetch                      → trigger run_fetch_cycle()
POST /backfill/{zone_id}         → ?days=30, fetch historical
GET  /signals/{zone_id}          → ?hours=24, paginated recent signals
GET  /features/{zone_id}         → pre-computed ML features for Agent 3
GET  /forecast/{zone_id}         → 16-day ECMWF weather
GET  /flood-forecast/{zone_id}   → 30-day GloFAS discharge
GET  /zones                      → all 8 zones + risk summary
```

**`run_fetch_cycle()` logic:**
```
For each of 8 zones:
  1. fetch Open-Meteo current + forecast
  2. fetch GloFAS flood discharge
  3. fetch OpenWeatherMap (if key set)
  4. fetch NDMA simulated alerts
  5. fetch Social simulated signals
  6. store each in SQLite via signal_store.store_signal()
  7. broadcast to WebSocket via ws_manager.broadcast_signal()
```

**Signal dict schema:**
```python
{
    "signal_id": str,       # unique dedup key
    "zone_id": str,
    "signal_type": str,     # "temperature" | "precipitation" | "river_discharge" | ...
    "value": float,
    "severity": int,        # 0-10
    "confidence": float,    # 0.0-1.0
    "source": str,          # "open-meteo" | "openweathermap" | "ndma" | "social"
    "timestamp": str,       # ISO 8601 UTC
    "metadata": dict,       # extra fields
}
```

**Severity calculation:**
- Temperature > 45°C → severity 8
- Precipitation > 50mm → severity 7
- River discharge > 5000 m³/s → severity 9
- Linear scale otherwise

### Prompt 4.2 — `backend/agents/agent_predictor.py`

**Agent 3 — ML Predictor (30-day flood + heat)**

FastAPI router prefix: `/api/v1/agent3`

**Endpoints:**
```
GET  /status          → model health, loaded status, accuracy metrics
POST /predict/{zone_id} → 30-day flood + heat prediction (main endpoint)
GET  /model/info      → model metadata, training data summary
POST /backtest        → validate against historical flood events
```

**`POST /predict/{zone_id}` response schema:**
```json
{
  "zone_id": "lahore-city",
  "generated_at": "2024-01-15T10:30:00Z",
  "peak_flood_risk": 0.72,
  "peak_heat_risk": 0.65,
  "prediction_horizon_days": 30,
  "day_predictions": [
    {
      "date": "2024-01-16",
      "day_number": 1,
      "temperature_c": 32.5,
      "rainfall_mm": 12.3,
      "flood_risk": 0.45,
      "heat_risk": 0.30,
      "confidence": "HIGH",
      "data_source": "ECMWF",
      "river_discharge_m3s": 1250.0,
      "cumulative_rain_mm": 12.3,
      "ndwi": 0.15,
      "ndvi": 0.42,
      "alerts": []
    }
    // ... 30 days total
  ],
  "summary": {
    "high_flood_days": 3,
    "high_heat_days": 8,
    "max_flood_risk_date": "2024-01-22",
    "max_heat_risk_date": "2024-01-19"
  }
}
```

**30-day prediction pipeline:**

```
Days 1-7:   Use Open-Meteo ECMWF real forecast (confidence=HIGH, 0.95)
Days 8-16:  Use Open-Meteo extended forecast (confidence=MODERATE, 0.70)
Days 17-30: Use Prophet ML forecast conditioned on real recent data (confidence=LOW, 0.40)

For each day:
  features = {
    "month": date.month,
    "temperature": temp_c,
    "rainfall_mm": daily_rain,
    "ndsi": zone_ndsi,          # satellite ice/snow index
    "ndvi": zone_ndvi,          # vegetation index
    "province_enc": province_int  # label-encoded
  }
  cumulative_rain += daily_rain  # antecedent moisture
  features["cumulative_rain"] = cumulative_rain

  flood_prob = xgboost_model.predict_proba([features])[1]

  # GloFAS modulation: daily river variation
  if glofas_discharge available:
    baseline_discharge = mean(glofas_30_day)
    daily_ratio = glofas_day / baseline_discharge
    flood_prob = min(1.0, flood_prob * daily_ratio)

  # Heat risk (PMD rule-based thresholds)
  heat_risk = pmd_heat_engine(temp_c, province)
```

**PMD heat engine thresholds:**
```python
def pmd_heat_engine(temp_c: float, province: str) -> float:
    # Jacobabad / Sindh extreme: > 48°C → 1.0, > 44°C → 0.8
    # Punjab (Multan, Lahore): > 45°C → 0.9, > 42°C → 0.7
    # Federal / KPK: > 43°C → 0.8, > 40°C → 0.6
    # Balochistan / Gilgit: > 40°C → 0.7, > 37°C → 0.5
    # All: linear interpolation below thresholds
```

**XGBoost model** (`models/flood_model.joblib`):
- Features: `["Month", "Temp", "Precip_mm", "NDSI", "NDVI", "Province_enc"]`
- Trained on 1,572 monthly samples, 60 labeled flood events
- Province encoding: Punjab=0, Sindh=1, KPK=2, Balochistan=3, Federal=4, Gilgit=5
- Load with: `joblib.load("models/flood_model.joblib")`

### Prompt 4.3 — `backend/agents/agent_debater.py`

**Debater — Multi-Persona LLM Risk Debate**

FastAPI router prefix: `/api/v1/debater`

**Endpoint:**
```
POST /debate/{zone_id}   → run 3-persona LLM debate, return consensus
```

**3 personas:**
1. **Hydrologist** — focuses on river discharge, soil saturation, GloFAS data
2. **Meteorologist** — focuses on rainfall patterns, ECMWF forecasts, historical precedents
3. **Urban_Planner** — focuses on drainage capacity, population density, infrastructure resilience

**Debate flow (4 Gemini API calls per zone):**
```
Call 1: Hydrologist persona → assess flood risk
Call 2: Meteorologist persona → assess flood + heat risk
Call 3: Urban_Planner persona → assess response urgency
Call 4: Consensus synthesizer → weigh 3 opinions, output final risk level
```

**Request payload to each persona:**
```python
{
    "zone": zone_config,
    "prediction": agent3_prediction,  # 30-day forecast
    "signals": recent_signals,         # last 24h signals
    "persona": "Hydrologist"
}
```

**Response schema:**
```json
{
  "zone_id": "lahore-city",
  "debate_timestamp": "...",
  "personas": {
    "Hydrologist":    {"risk_vote": "HIGH",   "urgency": "immediate", "reasoning": "..."},
    "Meteorologist":  {"risk_vote": "MEDIUM", "urgency": "monitor",   "reasoning": "..."},
    "Urban_Planner":  {"risk_vote": "HIGH",   "urgency": "prepare",   "reasoning": "..."}
  },
  "consensus": {
    "final_risk": "HIGH",
    "urgency": "immediate",
    "recommended_actions": ["Activate flood barriers", "Pre-position rescue teams"],
    "confidence": 0.78
  }
}
```

**Gemini integration:** Use `google-generativeai` SDK. Model: `gemini-1.5-flash`. Wrap calls in `gemini_retry.py` (max 3 retries, exponential backoff).

### Prompt 4.4 — `backend/agents/agent_orchestrator.py`

**Orchestrator — AI Pipeline Coordinator**

FastAPI router prefix: `/api/v1/orchestrator`

**Endpoints:**
```
GET  /status   → orchestrator health, last run time, zones processed
POST /run      → manually trigger one orchestration cycle
```

**`CIROOrchestrator.run_cycle()` logic:**
```
1. For each of 8 zones:
   a. Call Agent 3: POST /api/v1/agent3/predict/{zone_id}
   b. If peak_flood_risk > RISK_ALERT_THRESHOLD (0.30):
      → Call Debater: POST /api/v1/debater/debate/{zone_id}
   c. Log results + update orchestrator state

2. After all zones:
   a. Broadcast high-risk zone summary via WebSocket
   b. Update last_run_time
```

**State tracking:**
```python
@dataclass
class OrchestratorState:
    last_run: Optional[datetime]
    zones_processed: int
    high_risk_zones: list[str]
    debate_triggered: list[str]
    errors: list[str]
    is_running: bool = False
```

### Prompt 4.5 — `backend/agents/agent_imagery.py`

**Agent 1 — Satellite Imagery & Geospatial**

FastAPI router prefix: `/api/v1/agent1`

**Endpoints:**
```
GET  /latest/{zone_id}   → latest satellite analysis from cache
POST /analyze/{zone_id}  → trigger new GEE NDWI analysis
```

**NDWI (Normalized Difference Water Index):**
```python
# NDWI = (Green - NIR) / (Green + NIR)
# Positive NDWI → water body present
# High NDWI change → flood inundation detected
```

**Dependencies:** `earthengine-api`, `google-auth`

**Earth Engine auth:** Service account or application-default credentials. Fails gracefully if not configured — returns `{"status": "unavailable", "reason": "not_configured"}`.

**GeoGemma integration:** Use Gemini Vision API to analyze satellite image thumbnails for flood extent estimation.

### Prompt 4.6 — `backend/agents/agent_response.py`

**Agent 4 — Response Commander**

FastAPI router prefix: `/api/v1/agent4`

**Endpoints:**
```
GET  /status                 → agent health
POST /dispatch/{zone_id}     → create response plan
GET  /plans/{zone_id}        → active response plans
POST /evacuate/{zone_id}     → trigger evacuation routing
```

**Response plan schema:**
```json
{
  "zone_id": "karachi-south",
  "risk_level": "HIGH",
  "plan_id": "uuid",
  "created_at": "...",
  "actions": [
    {"type": "alert", "priority": 1, "description": "Notify NDMA"},
    {"type": "resource", "priority": 2, "description": "Pre-position 3 rescue boats"},
    {"type": "evacuate", "priority": 3, "description": "Prepare Sector 4 evacuation routes"}
  ],
  "estimated_affected_population": 45000
}
```

---

## Part 5 — Backend: Main Application

### Prompt 5.1 — `backend/main.py`

Full FastAPI application entry point.

**Lifespan startup sequence:**
1. `await signal_store.initialize()` — create SQLite schema
2. `await ee_service.initialize()` — authenticate Earth Engine (graceful fail)
3. `await scheduler.start(run_fetch_cycle, signal_store.prune_expired)`
4. `scheduler.add_orchestrator_job(orchestrator.run_cycle)`

**Router mounts:**
```python
app.include_router(data_collector_router, prefix="/api/v1/agent2")
app.include_router(predictor_router,      prefix="/api/v1/agent3")
app.include_router(imagery_router,        prefix="/api/v1/agent1")
app.include_router(debater_router,        prefix="/api/v1/debater")
app.include_router(orchestrator_router,   prefix="/api/v1/orchestrator")
app.include_router(response_router,       prefix="/api/v1/agent4")
```

**CORS:** `allow_origins=["*"]` (development), restrict in production.

**System endpoints:**
- `GET /` → serve `static/index.html` dashboard
- `GET /health` → `{status, agents_active, scheduler_running, websocket_clients, database}`
- `GET /metrics` → `{signal_store, api_clients, scheduler, websocket}`
- `GET /api` → API status JSON
- `WS /ws/signals?zone=X&min_severity=Y` → real-time signal stream

**WebSocket handler:** Accept zone/severity query params, forward to `ws_manager.connect()`, loop `receive_text()` for dynamic filter updates, handle `WebSocketDisconnect`.

### Prompt 5.2 — `backend/static/index.html`

Dark-mode HTML/CSS/JS control panel dashboard. Single-file, no framework dependencies.

**Sections:**
- Header: CIRO logo + live status indicator
- Zone cards grid (8 zones): risk badge, last signal, fetch time
- Fetch controls: "Run Fetch Cycle" + "Backfill Zone" buttons
- Signal log: live WebSocket feed (scrollable, color-coded by severity)
- Orchestrator panel: last run, zones processed, high-risk list
- API quick-links: /docs, /metrics, /health

**Color scheme:** Dark background (#0d1117), accent blue (#1e88e5), risk colors: green/yellow/orange/red.

### Prompt 5.3 — `backend/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Part 6 — Flutter Mobile App

### Prompt 6.1 — `ciro_app/pubspec.yaml`

```yaml
name: ciro_app
description: CIRO — Crisis Intelligence Mobile App
version: 2.0.0+1

environment:
  sdk: ">=3.0.0 <4.0.0"

dependencies:
  flutter:
    sdk: flutter
  provider: ^6.1.1
  dio: ^5.4.0
  web_socket_channel: ^2.4.0
  fl_chart: ^0.66.0
  flutter_local_notifications: ^17.0.0
  url_launcher: ^6.2.1
  intl: ^0.19.0
  shimmer: ^3.0.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^3.0.0

flutter:
  uses-material-design: true
```

### Prompt 6.2 — `ciro_app/lib/config/api_config.dart`

```dart
class ApiConfig {
  // Android emulator → host machine localhost
  static const String baseUrl = 'http://10.0.2.2:8000';
  static const String wsUrl   = 'ws://10.0.2.2:8000/ws/signals';

  // Agent endpoints
  static String agent2Status()          => '$baseUrl/api/v1/agent2/status';
  static String agent2Fetch()           => '$baseUrl/api/v1/agent2/fetch';
  static String agent2Signals(String z) => '$baseUrl/api/v1/agent2/signals/$z';
  static String agent2Zones()           => '$baseUrl/api/v1/agent2/zones';
  static String agent3Predict(String z) => '$baseUrl/api/v1/agent3/predict/$z';
  static String agent3Status()          => '$baseUrl/api/v1/agent3/status';
  static String agent1Latest(String z)  => '$baseUrl/api/v1/agent1/latest/$z';
  static String agent1Analyze(String z) => '$baseUrl/api/v1/agent1/analyze/$z';
  static String orchestratorStatus()    => '$baseUrl/api/v1/orchestrator/status';
  static String debaterDebate(String z) => '$baseUrl/api/v1/debater/debate/$z';
  static String health()                => '$baseUrl/health';
}
```

### Prompt 6.3 — `ciro_app/lib/models/zone.dart`

```dart
class CiroZone {
  final String id;
  final String name;
  final double lat;
  final double lng;
  final String province;
  final double elevationM;
  final double drainageCapacity;
  final double populationDensity;

  const CiroZone({
    required this.id, required this.name,
    required this.lat, required this.lng,
    required this.province, required this.elevationM,
    required this.drainageCapacity, required this.populationDensity,
  });

  static const List<CiroZone> allZones = [
    CiroZone(id: 'islamabad-g10', name: 'G-10, Islamabad', lat: 33.6844, lng: 73.0479, province: 'Federal',     elevationM: 507,  drainageCapacity: 0.6,  populationDensity: 2850),
    CiroZone(id: 'lahore-city',   name: 'Lahore City',      lat: 31.5204, lng: 74.3587, province: 'Punjab',      elevationM: 217,  drainageCapacity: 0.4,  populationDensity: 6300),
    CiroZone(id: 'karachi-south', name: 'Karachi South',    lat: 24.8607, lng: 67.0011, province: 'Sindh',       elevationM: 10,   drainageCapacity: 0.3,  populationDensity: 14000),
    CiroZone(id: 'peshawar-city', name: 'Peshawar City',    lat: 34.0151, lng: 71.5249, province: 'KPK',         elevationM: 331,  drainageCapacity: 0.5,  populationDensity: 3200),
    CiroZone(id: 'multan-city',   name: 'Multan City',      lat: 30.1575, lng: 71.5249, province: 'Punjab',      elevationM: 122,  drainageCapacity: 0.35, populationDensity: 4500),
    CiroZone(id: 'jacobabad-city',name: 'Jacobabad City',   lat: 28.2769, lng: 68.4368, province: 'Sindh',       elevationM: 55,   drainageCapacity: 0.25, populationDensity: 2100),
    CiroZone(id: 'sukkur-city',   name: 'Sukkur City',      lat: 27.7052, lng: 68.8574, province: 'Sindh',       elevationM: 66,   drainageCapacity: 0.3,  populationDensity: 3800),
    CiroZone(id: 'quetta-city',   name: 'Quetta City',      lat: 30.1798, lng: 66.9750, province: 'Balochistan', elevationM: 1680, drainageCapacity: 0.35, populationDensity: 1800),
  ];
}
```

### Prompt 6.4 — `ciro_app/lib/models/prediction.dart`

```dart
class DayPrediction {
  final String date;
  final int dayNumber;
  final double temperatureC;
  final double rainfallMm;
  final double floodRisk;       // 0.0 - 1.0
  final double heatRisk;        // 0.0 - 1.0
  final String confidence;      // "HIGH" | "MODERATE" | "LOW"
  final String dataSource;      // "ECMWF" | "ECMWF_Extended" | "Prophet_ML"
  final double? riverDischarge;
  final List<String> alerts;

  factory DayPrediction.fromJson(Map<String, dynamic> json) { ... }
}

class ZonePrediction {
  final String zoneId;
  final String generatedAt;
  final double peakFloodRisk;
  final double peakHeatRisk;
  final List<DayPrediction> dayPredictions;
  final Map<String, dynamic> summary;

  factory ZonePrediction.fromJson(Map<String, dynamic> json) { ... }
}
```

### Prompt 6.5 — `ciro_app/lib/services/api_service.dart`

```dart
class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  final Dio _dio = Dio(BaseOptions(
    connectTimeout: Duration(seconds: 10),
    receiveTimeout: Duration(seconds: 30),
  ));

  Future<ZonePrediction> getPrediction(String zoneId) async {
    final resp = await _dio.post(ApiConfig.agent3Predict(zoneId));
    return ZonePrediction.fromJson(resp.data);
  }

  Future<void> triggerFetch() async {
    await _dio.post(ApiConfig.agent2Fetch());
  }

  Future<Map<String, dynamic>> getSatelliteAnalysis(String zoneId) async {
    final resp = await _dio.get(ApiConfig.agent1Latest(zoneId));
    return resp.data;
  }

  Future<Map<String, dynamic>> analyzeSatellite(String zoneId) async {
    final resp = await _dio.post(ApiConfig.agent1Analyze(zoneId));
    return resp.data;
  }

  Future<bool> isHealthy() async {
    try {
      final resp = await _dio.get(ApiConfig.health());
      return resp.data['status'] == 'healthy';
    } catch (_) { return false; }
  }
}
```

### Prompt 6.6 — `ciro_app/lib/services/websocket_service.dart`

```dart
class WebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  bool _connected = false;
  List<Map<String, dynamic>> _recentAlerts = [];

  bool get connected => _connected;
  List<Map<String, dynamic>> get recentAlerts => _recentAlerts;

  void connect({String? zoneFilter, int minSeverity = 0}) {
    final uri = Uri.parse(
      minSeverity > 0
        ? '${ApiConfig.wsUrl}?min_severity=$minSeverity'
        : ApiConfig.wsUrl,
    );
    _channel = WebSocketChannel.connect(uri);
    _connected = true;

    _channel!.stream.listen(
      (data) {
        final msg = jsonDecode(data);
        if (msg['type'] == 'alert' || msg['type'] == 'signal') {
          _recentAlerts.insert(0, msg['data']);
          if (_recentAlerts.length > 100) _recentAlerts.removeLast();
          notifyListeners();
        }
      },
      onDone: () { _connected = false; notifyListeners(); },
      onError: (_) { _connected = false; notifyListeners(); },
    );
    notifyListeners();
  }

  void disconnect() {
    _channel?.sink.close();
    _connected = false;
    notifyListeners();
  }
}
```

### Prompt 6.7 — `ciro_app/lib/services/notification_service.dart`

```dart
class NotificationService {
  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();

  static Future<void> initialize() async {
    const initAndroid = AndroidInitializationSettings('@mipmap/ic_launcher');
    await _plugin.initialize(
      const InitializationSettings(android: initAndroid),
      onDidReceiveNotificationResponse: _onTap,
    );
  }

  static Future<void> showAlert({
    required String title,
    required String body,
    String? payload,
  }) async {
    await _plugin.show(
      DateTime.now().millisecondsSinceEpoch.remainder(100000),
      title, body,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'ciro_alerts', 'CIRO Alerts',
          importance: Importance.high,
          priority: Priority.high,
        ),
      ),
      payload: payload,
    );
  }

  static void _onTap(NotificationResponse details) {
    // Navigate to alerts screen
  }
}
```

### Prompt 6.8 — `ciro_app/lib/theme/ciro_theme.dart`

```dart
import 'package:flutter/material.dart';

class CiroTheme {
  static const Color background  = Color(0xFF0D1117);
  static const Color surface     = Color(0xFF161B22);
  static const Color accent      = Color(0xFF1E88E5);
  static const Color textPrimary = Color(0xFFE6EDF3);
  static const Color textMuted   = Color(0xFF8B949E);
  static const Color riskLow     = Color(0xFF238636);
  static const Color riskMedium  = Color(0xFFD29922);
  static const Color riskHigh    = Color(0xFFDA3633);
  static const Color riskCrit    = Color(0xFFFF7B72);

  static ThemeData get theme => ThemeData(
    brightness: Brightness.dark,
    scaffoldBackgroundColor: background,
    colorScheme: const ColorScheme.dark(
      primary: accent,
      surface: surface,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: surface,
      elevation: 0,
      titleTextStyle: TextStyle(
        color: textPrimary, fontSize: 18, fontWeight: FontWeight.w600,
      ),
    ),
    cardTheme: CardTheme(
      color: surface,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
    textTheme: const TextTheme(
      bodyMedium: TextStyle(color: textPrimary),
      bodySmall:  TextStyle(color: textMuted),
    ),
  );

  static Color riskColor(double risk) {
    if (risk >= 0.75) return riskCrit;
    if (risk >= 0.5)  return riskHigh;
    if (risk >= 0.25) return riskMedium;
    return riskLow;
  }
}
```

### Prompt 6.9 — `ciro_app/lib/screens/home_screen.dart`

Main screen showing all 8 zones with risk badges.

**UI structure:**
```
AppBar: "CIRO" + connection status dot (green/red)
Body: ListView of ZoneCard widgets (one per zone)

ZoneCard:
  - Zone name + province chip
  - Flood risk badge (color from CiroTheme.riskColor)
  - Heat risk badge
  - Elevation + population density (small text)
  - Tap → navigate to PredictionScreen(zone: zone)

FloatingActionButton: "Fetch Now" → ApiService().triggerFetch()
```

**State:** Uses `WebSocketService` via `Provider.of<WebSocketService>` for live updates. On mount, calls `ApiService().isHealthy()` to show connection banner.

### Prompt 6.10 — `ciro_app/lib/screens/prediction_screen.dart`

30-day forecast detail for a single zone.

**UI structure:**
```
AppBar: zone.name
TabBar: "Flood Risk" | "Heat Risk" | "Daily Detail"

Tab 1 — Flood Risk:
  LineChart (fl_chart): 30-day flood probability
  X-axis: dates, Y-axis: 0-100%
  Color bands: green (0-25), yellow (25-50), orange (50-75), red (75-100)
  Confidence region: shaded area (yhat_lower to yhat_upper)

Tab 2 — Heat Risk:
  Same chart structure for heat_risk
  
Tab 3 — Daily Detail:
  ListView of DayCard for each of 30 days:
    - Date + day number
    - Temperature + rainfall
    - Flood % + Heat %
    - Confidence label chip
    - Data source chip (ECMWF / Prophet ML)
    - Alert chips if any

Bottom panel:
  Summary stats: peak flood day, peak heat day, total high-risk days
```

**State:** `FutureBuilder` on `ApiService().getPrediction(zone.id)`. Shimmer loading skeleton while fetching.

### Prompt 6.11 — `ciro_app/lib/screens/alerts_screen.dart`

Alert history with filtering.

**UI structure:**
```
AppBar: "Live Alerts"
FilterBar: All | Critical | High | Medium chips
Body: ListView.builder on WebSocketService.recentAlerts
  AlertCard:
    - Signal type icon
    - Zone name + timestamp
    - Severity badge (color-coded)
    - Value + source
    - Confidence pill

Empty state: "No alerts — all zones nominal"
```

### Prompt 6.12 — `ciro_app/lib/screens/live_map_screen.dart`

Interactive map visualization of 8 zones.

**UI structure:**
```
AppBar: "Crisis Map"
Body: Stack
  - Base map: simple Pakistan SVG outline or CustomPaint
  - Zone markers: positioned Dots at lat/lng (scaled to screen)
    - Dot color: CiroTheme.riskColor(zone.floodRisk)
    - Dot size: proportional to population density
    - Tap → show ZonePopup (name, risk values, province)
  - Legend: risk color scale
```

Note: No Google Maps dependency needed — use a simple custom painted map or an SVG outline. This avoids API key requirements.

### Prompt 6.13 — `ciro_app/lib/screens/agents_screen.dart`

Agent status dashboard with controls.

**UI structure:**
```
AppBar: "Agent Status"
Body: Column
  AgentStatusCard for each of 6 agents:
    - Agent name + icon
    - Status indicator (online / offline / running)
    - Last activity timestamp
    - Action button if applicable

  Divider

  ControlPanel:
    [Trigger Fetch]    → ApiService().triggerFetch()
    [Run Orchestrator] → POST /api/v1/orchestrator/run
    [Analyze Imagery]  → ApiService().analyzeSatellite(selectedZone)

  ZoneSelector dropdown (for satellite analysis)
```

**Polling:** `Timer.periodic(Duration(seconds: 30))` to refresh agent statuses.

### Prompt 6.14 — `ciro_app/lib/main.dart`

App entry point with Provider setup and bottom navigation.

```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await NotificationService.initialize();
  runApp(const CiroApp());
}

class CiroApp extends StatelessWidget {
  Widget build(BuildContext context) => MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => WebSocketService()..connect()),
    ],
    child: MaterialApp(
      title: 'CIRO',
      theme: CiroTheme.theme,
      home: const AppShell(),
    ),
  );
}

class AppShell extends StatefulWidget { ... }
class _AppShellState extends State<AppShell> {
  int _index = 0;
  final _screens = [HomeScreen(), AlertsScreen(), LiveMapScreen(), AgentsScreen()];

  Widget build(BuildContext context) => Scaffold(
    body: _screens[_index],
    bottomNavigationBar: BottomNavigationBar(
      currentIndex: _index,
      onTap: (i) => setState(() => _index = i),
      items: [
        BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
        BottomNavigationBarItem(icon: Icon(Icons.notifications), label: 'Alerts'),
        BottomNavigationBarItem(icon: Icon(Icons.map), label: 'Map'),
        BottomNavigationBarItem(icon: Icon(Icons.smart_toy), label: 'Agents'),
      ],
    ),
  );
}
```

---

## Part 7 — Data & ML Models

### Prompt 7.1 — Training data structure

The `backend/data/training/` directory must contain:

**Monthly aggregates (for XGBoost training):**
- `Punjab_training.csv`, `Sindh_training.csv`, `Federal_training.csv`
- `Kpk_training.csv`, `Balochistan_training.csv`, `Gilgit_training.csv`
- Columns: `Month,Temp,Precip_mm,NDSI,NDVI,Province,Flood_label`
- 1,572 total rows, 60 rows where `Flood_label=1`

**Daily data (for Prophet training), per province folder:**
- `Punjab/Temp.csv`, `Punjab/Pre.csv` — columns: `ds,y` (date + value)
- Same structure for: Sindh, Federal, Kpk, Balochistan, Gilgit
- ~8,000 rows per CSV, covering 2000-2021

**National historical:**
- `Rainfall_1901_2016_PAK.csv`, `Tempreture_1901_2016_Pakistan.csv`
- Columns: monthly aggregates, 1,392 rows each

### Prompt 7.2 — XGBoost model training script

Create `backend/train_xgboost.py`:

```python
"""Run this once to train and save the XGBoost flood classifier."""
import pandas as pd
import numpy as np
from xgboost import XGBClassifier
import joblib
from pathlib import Path

PROVINCES = ["Punjab", "Sindh", "Federal", "Kpk", "Balochistan", "Gilgit"]
PROVINCE_ENC = {p: i for i, p in enumerate(PROVINCES)}

def load_all_training_data():
    dfs = []
    for province in PROVINCES:
        path = f"data/training/{province}_training.csv"
        df = pd.read_csv(path)
        df["Province_enc"] = PROVINCE_ENC[province]
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

df = load_all_training_data()
X = df[["Month", "Temp", "Precip_mm", "NDSI", "NDVI", "Province_enc"]]
y = df["Flood_label"]

model = XGBClassifier(
    n_estimators=100, max_depth=5, learning_rate=0.1,
    use_label_encoder=False, eval_metric="logloss", random_state=42
)
model.fit(X, y)

Path("models").mkdir(exist_ok=True)
joblib.dump(model, "models/flood_model.joblib")
print(f"Saved. Accuracy: {model.score(X, y):.3f}")
```

### Prompt 7.3 — Prophet model training (auto on first call)

Prophet models are trained lazily in `services/weather_forecaster.py`. On first call:
1. Load `data/training/{Province}/Temp.csv` → fit Prophet → save `models/prophet/{Province}_temp_prophet.pkl`
2. Load `data/training/{Province}/Pre.csv` → fit Prophet → save `models/prophet/{Province}_rain_prophet.pkl`

This takes ~15-20 seconds per model on first call. Subsequent calls load from .pkl (instant).

---

## Part 8 — Integration & Testing

### Prompt 8.1 — Run order

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
python train_xgboost.py          # one-time: train + save XGBoost
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Verify:
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/agent2/fetch
curl -X POST http://localhost:8000/api/v1/agent3/predict/lahore-city
```

```bash
# Terminal 2: Flutter app
cd ciro_app
flutter pub get
flutter run                       # Android emulator or device
```

### Prompt 8.2 — First-run checklist

- [ ] Backend starts without error on port 8000
- [ ] `/health` returns `{"status": "healthy"}`
- [ ] `POST /api/v1/agent2/fetch` triggers data collection for all 8 zones
- [ ] `POST /api/v1/agent3/predict/lahore-city` returns 30 `day_predictions`
- [ ] Flutter app connects to `ws://10.0.2.2:8000/ws/signals`
- [ ] Zone cards show on Home screen
- [ ] Prediction chart renders on tap of any zone
- [ ] Alerts tab shows signals as they arrive

### Prompt 8.3 — Environment variables for production

```bash
GEMINI_API_KEY=<your key>          # Required for Debater agent
OPENWEATHER_API_KEY=<optional>     # Enhances real-time weather
GOOGLE_MAPS_API_KEY=<optional>     # Traffic congestion data
ENVIRONMENT=production
```

---

## Architecture Summary (for Antigravity context)

```
┌─────────────────────────────────────────────────────────┐
│                    CIRO Architecture                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Flutter App  ←──WebSocket──→  FastAPI Backend           │
│  (5 screens)  ←──REST API──→   (port 8000)               │
│                                                          │
│  Backend agents:                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Agent 1  │ │ Agent 2  │ │ Agent 3  │ │ Agent 4  │   │
│  │Satellite │ │  Data    │ │   ML     │ │Response  │   │
│  │ GEE+     │ │Collector │ │Predictor │ │Commander │   │
│  │GeoGemma  │ │6 sources │ │XGBoost + │ │Dispatch  │   │
│  └──────────┘ └──────────┘ │ Prophet  │ └──────────┘   │
│                             └──────────┘                 │
│  ┌──────────────────┐ ┌──────────────────┐              │
│  │   Orchestrator   │ │     Debater      │              │
│  │  2-hr AI cycle   │ │ 3-persona Gemini │              │
│  │  coordinates all │ │ Hydrologist +    │              │
│  │  agents          │ │ Meteorologist +  │              │
│  └──────────────────┘ │ Urban Planner    │              │
│                        └──────────────────┘              │
│  Services:                                               │
│  SQLite (signals.db) → 30-day rolling buffer             │
│  APScheduler → 15-min fetch + 2-hr orchestration        │
│  WebSocket Manager → real-time push to Flutter           │
│  RetryClient → HTTP with circuit breaker                 │
└─────────────────────────────────────────────────────────┘
```

---

## Prompt-by-Prompt Session Guide

Use this order when feeding prompts to Antigravity:

| Step | What to ask Antigravity to build |
|------|----------------------------------|
| 1    | Project folder scaffold (Part 1) |
| 2    | `backend/config/settings.py` + `.env.example` + `requirements.txt` (Part 2) |
| 3    | `signal_store.py` + `websocket_manager.py` + `retry_client.py` (Part 3.1-3.3) |
| 4    | `openmeteo_service.py` + `scheduler.py` + `weather_forecaster.py` (Part 3.4-3.6) |
| 5    | Three simulated services: weather, NDMA, social (Part 3.7) |
| 6    | `agent_data_collector.py` — Agent 2 (Part 4.1) |
| 7    | `agent_predictor.py` — Agent 3 with full ML pipeline (Part 4.2) |
| 8    | `agent_debater.py` — Gemini debate (Part 4.3) |
| 9    | `agent_orchestrator.py` — coordinator (Part 4.4) |
| 10   | `agent_imagery.py` + `agent_response.py` (Parts 4.5-4.6) |
| 11   | `main.py` + `static/index.html` + `Dockerfile` (Part 5) |
| 12   | Flutter: `pubspec.yaml` + config + models (Parts 6.1-6.4) |
| 13   | Flutter: services layer — ApiService, WebSocketService, NotificationService (Parts 6.5-6.7) |
| 14   | Flutter: theme + all 5 screens (Parts 6.8-6.14) |
| 15   | Data + ML training scripts (Part 7) |
| 16   | Integration test checklist (Part 8) |

At each step, share the relevant section from this document to Antigravity and ask it to implement exactly that component.
