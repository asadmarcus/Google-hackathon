# CIRO Backend — Agent 2: Data & API Collector

> **Production-grade multi-source data collection agent for the CIRO crisis prediction system.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CIRO Backend v2.0                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────────┐ │
│  │ APScheduler │───▶│ Fetch Cycle  │───▶│  SQLite Signal Store   │ │
│  │ (every 15m) │    │ (6 sources)  │    │  (30-day, deduplicated)│ │
│  └─────────────┘    └──────┬───────┘    └────────────────────────┘ │
│                            │                                        │
│                            ▼                                        │
│                   ┌─────────────────┐                               │
│                   │  WebSocket Push  │──────▶ Flutter App            │
│                   │  (real-time)     │                               │
│                   └─────────────────┘                               │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    REST API (FastAPI)                           │ │
│  │                                                                │ │
│  │  /api/v1/agent2/fetch      POST  Trigger collection           │ │
│  │  /api/v1/agent2/signals    GET   Query signals by zone        │ │
│  │  /api/v1/agent2/features   GET   ML feature vector            │ │
│  │  /api/v1/agent2/backfill   POST  30-day historical fill       │ │
│  │  /api/v1/agent2/flood-forecast GET  GloFAS 30-day forecast    │ │
│  │  /metrics                  GET   System metrics               │ │
│  │  /ws/signals               WS    Real-time stream             │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# 1. Navigate to backend
cd backend

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment (optional — works without API keys too)
copy .env.example .env
# Edit .env with your keys

# 5. Run the server
uvicorn main:app --reload --port 8000
```

**Open http://localhost:8000/docs** — full interactive API docs.

---

## Data Sources

| # | Source | API Key? | Data Provided | Update Frequency |
|---|--------|:--------:|---------------|:----------------:|
| 1 | **Open-Meteo Weather** | ❌ FREE | Current + 7-day forecast + 30-day historical | Every fetch |
| 2 | **Open-Meteo Flood (GloFAS)** | ❌ FREE | 30-day river discharge forecast | Every fetch |
| 3 | **OpenWeatherMap** | ✅ Free key | Real-time temp, rain, humidity, wind, pressure | Every fetch |
| 4 | **Google Maps Traffic** | ✅ $200/mo credit | Road congestion ratio | Every fetch |
| 5 | **NDMA Pakistan** | ❌ Simulated | Official disaster alerts (realistic) | Every fetch |
| 6 | **Social Media** | ❌ Simulated | Urdu+English crisis keywords | Every fetch |

### Getting API Keys (Optional)

- **OpenWeatherMap**: https://openweathermap.org/api → Sign up → Free key in 2 min
- **Google Maps**: https://console.cloud.google.com → Enable Directions API → $200 free credit

**The system works perfectly without any API keys** — Open-Meteo provides real data for free, and other services have intelligent simulation fallbacks.

---

## API Endpoints

### Agent 2 — Data Collection

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/agent2/fetch` | Trigger full collection cycle (all zones, all sources) |
| `POST` | `/api/v1/agent2/backfill/{zone_id}?days=30` | Fill 30-day buffer with real historical data |
| `GET` | `/api/v1/agent2/signals/{zone_id}?hours=24` | Get latest signals for a zone |
| `GET` | `/api/v1/agent2/signals/{zone_id}/history?days=30` | Full 30-day daily aggregates |
| `GET` | `/api/v1/agent2/features/{zone_id}` | Pre-computed ML feature vector (for Agent 3) |
| `GET` | `/api/v1/agent2/flood-forecast/{zone_id}` | 30-day GloFAS river discharge forecast |
| `GET` | `/api/v1/agent2/zones` | All zones with current risk summary |
| `GET` | `/api/v1/agent2/status` | Agent health & configuration |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | Health check (for load balancers) |
| `GET` | `/metrics` | Comprehensive system metrics |
| `WS` | `/ws/signals` | Real-time WebSocket signal stream |

### WebSocket Connection

```
ws://localhost:8000/ws/signals                    → All signals
ws://localhost:8000/ws/signals?zone=islamabad-g10 → One zone only
ws://localhost:8000/ws/signals?min_severity=7     → High severity only
```

**Flutter connection:**
```dart
final channel = WebSocketChannel.connect(
  Uri.parse('ws://your-server:8000/ws/signals?zone=islamabad-g10'),
);
channel.stream.listen((message) {
  final data = jsonDecode(message);
  if (data['type'] == 'signal') {
    // Update map/UI with data['data']
  }
});
```

---

## Project Structure

```
backend/
├── main.py                          # FastAPI app + lifespan + WebSocket endpoint
├── config/
│   ├── __init__.py
│   └── settings.py                  # Zones, API keys, intervals
├── agents/
│   ├── __init__.py
│   └── agent_data_collector.py      # Agent 2: router + fetch cycle + ML features
├── services/
│   ├── __init__.py
│   ├── weather_service.py           # OpenWeatherMap integration
│   ├── openmeteo_service.py         # Open-Meteo (FREE) + GloFAS flood
│   ├── traffic_service.py           # Google Maps traffic
│   ├── social_service.py            # Social media keyword monitoring
│   ├── ndma_service.py              # NDMA Pakistan disaster alerts
│   ├── signal_store.py              # SQLite persistent storage (deduplicated)
│   ├── scheduler.py                 # APScheduler (auto-fetch every 15 min)
│   ├── websocket_manager.py         # WebSocket real-time push
│   └── retry_client.py              # HTTP client with retries + circuit breaker
├── models/                          # (Agent 3 — ML models go here)
├── data/
│   └── signals.db                   # SQLite database (auto-created)
├── requirements.txt
├── Dockerfile
├── .env.example
└── .gitignore
```

---

## Key Design Decisions

### 1. SQLite over Firestore/Redis
- **Why**: Zero configuration, file-based persistence, survives restarts, no external service needed for hackathon.
- **Indexed columns**: zone_id + timestamp (composite), signal_type, severity, source.
- **Deduplication**: `INSERT OR IGNORE` on signal_id primary key — calling `/fetch` twice won't create duplicates.

### 2. APScheduler over Celery/cron
- **Why**: Lightweight, async-native, runs in-process, no Redis/RabbitMQ needed.
- **Jobs**: Fetch every 15 min (configurable), prune daily at 3 AM UTC.
- **Coalescing**: If a job is missed (e.g., server was down), it runs once on recovery (not N times).

### 3. Circuit Breaker on API Calls
- **Pattern**: After 5 consecutive failures to a source, circuit "opens" — skips requests for 60s.
- **Recovery**: After cooldown, allows one "half-open" request. If it succeeds, circuit closes.
- **Why**: Prevents hammering a down API, allows graceful degradation.

### 4. WebSocket with Per-Client Filtering
- **Why**: Flutter app doesn't need ALL signals — only for the zone the user is viewing.
- **Filters**: zone, min_severity, signal_types — set on connect or update dynamically.

---

## Monitored Zones (Pakistan)

| Zone ID | Name | Province | Lat/Lng | Elevation |
|---------|------|----------|---------|-----------|
| `islamabad-g10` | G-10, Islamabad | Federal | 33.68, 73.05 | 507m |
| `lahore-city` | Lahore City | Punjab | 31.52, 74.36 | 217m |
| `karachi-south` | Karachi South | Sindh | 24.86, 67.00 | 10m |
| `peshawar-city` | Peshawar City | KPK | 34.02, 71.52 | 331m |
| `multan-city` | Multan City | Punjab | 30.16, 71.52 | 122m |

---

## Signal Schema

Every data point from every source is normalized to this format:

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

### Signal Types
`temperature`, `rainfall`, `humidity`, `wind`, `cloud_coverage`, `traffic`, `social`, `official_alert`, `flood_discharge`, `forecast_7d`

### Severity Scale (1-10)
| Level | Meaning | Rainfall Equiv | Temp Equiv |
|-------|---------|:--------------:|:----------:|
| 1-3 | Low/Normal | < 5 mm/hr | < 35°C |
| 4-5 | Moderate | 5-15 mm/hr | 35-39°C |
| 6-7 | High | 15-35 mm/hr | 39-43°C |
| 8-9 | Very High | 35-60 mm/hr | 43-47°C |
| 10 | Extreme/Emergency | > 60 mm/hr | > 48°C |

---

## ML Feature Vector (for Agent 3)

`GET /api/v1/agent2/features/{zone_id}` returns:

```json
{
  "cumulative_rain_7d": 142.5,
  "cumulative_rain_14d": 285.3,
  "cumulative_rain_30d": 412.1,
  "rain_intensity_24h": 45.2,
  "max_temp_24h": 38.5,
  "heat_index": 26.95,
  "consecutive_hot_days": 3,
  "avg_humidity_24h": 78.2,
  "terrain_elevation": 507,
  "drainage_capacity": 0.6,
  "population_density": 2850,
  "month": 7,
  "is_monsoon": 1,
  "month_sin": 0.866,
  "month_cos": -0.5,
  "ndwi_delta": 0.0
}
```

---

## Environment Variables

```env
# Required: None (works with Open-Meteo free data out of the box)

# Optional (enhances data quality):
OPENWEATHER_API_KEY=your_key     # https://openweathermap.org/api
GOOGLE_MAPS_API_KEY=your_key     # https://console.cloud.google.com

# Configuration:
ENVIRONMENT=development
FETCH_INTERVAL_MINUTES=15
SIGNAL_BUFFER_DAYS=30
SEVERITY_THRESHOLD=0.7
```

---

## For Team Members

### Adding a New Data Source
1. Create `services/your_service.py` with a `fetch_for_zone(zone)` method
2. Import it in `agents/agent_data_collector.py`
3. Add to `run_fetch_cycle()` function
4. Done — it auto-stores, auto-deduplicates, auto-broadcasts

### Adding a New Zone
Edit `config/settings.py` → `ZONES` list. Required fields:
```python
{"id": "slug", "name": "Display Name", "lat": 0.0, "lng": 0.0,
 "province": "X", "elevation_m": 0, "drainage_capacity": 0.5, "population_density": 0}
```

### Testing
```bash
# Start server
uvicorn main:app --reload

# Trigger fetch
curl -X POST http://localhost:8000/api/v1/agent2/fetch

# Check signals
curl http://localhost:8000/api/v1/agent2/signals/islamabad-g10

# Check metrics
curl http://localhost:8000/metrics

# WebSocket test (use wscat)
npx wscat -c ws://localhost:8000/ws/signals
```
