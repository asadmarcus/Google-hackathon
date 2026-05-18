# Agent 3 — ML Predictor

## Complete Technical Documentation

> **Purpose**: Consume Agent 2's real-time feature vectors and output 30-day day-by-day flood and heatstroke risk forecasts for Pakistani urban zones using XGBoost.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                       AGENT 3: ML Predictor                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  INPUT                      PROCESSING              OUTPUT           │
│  ──────────────────        ──────────────          ──────────        │
│                                                                      │
│  ┌─────────────────┐                                                 │
│  │ Agent 2         │──┐    ┌──────────────┐    ┌──────────────────┐ │
│  │ /features       │  │    │ Feature      │    │ /predict/{zone}  │ │
│  │ (16 features)   │  │    │ Projector    │    │ → 30-day array   │ │
│  └─────────────────┘  ├───▶│ (day 1-30   │───▶│ [{day,flood,heat}│ │
│  ┌─────────────────┐  │    │  per day)   │    │  ...]            │ │
│  │ Agent 2         │──┘    └──────┬───────┘    └──────────────────┘ │
│  │ /flood-forecast │             │                                   │
│  │ (GloFAS 30-day) │    ┌────────▼───────┐    ┌──────────────────┐ │
│  └─────────────────┘    │  XGBoost       │    │ /model/info      │ │
│                         │  flood_model   │───▶│ → accuracy/meta  │ │
│  ┌─────────────────┐    │  heat_model    │    └──────────────────┘ │
│  │ Training Data   │───▶│  (joblib       │                          │
│  │ (CSV or synth.) │    │   bundle)      │    ┌──────────────────┐ │
│  └─────────────────┘    └────────────────┘    │ /backtest        │ │
│                                               │ → historical     │ │
│  ┌─────────────────┐                          │   accuracy       │ │
│  │ models/         │ ◀── save/load ──────────▶└──────────────────┘ │
│  │ flood_model     │                                                 │
│  │ .joblib         │                                                 │
│  └─────────────────┘                                                 │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
backend/
├── agents/
│   ├── agent_predictor.py         # Agent 3 router — all endpoints + ML logic
│   └── agent_data_collector.py    # Agent 2 (upstream data provider)
├── models/
│   └── flood_model.joblib         # Trained model bundle (auto-created on first run)
├── data/
│   ├── signals.db                 # Agent 2 SQLite store
│   └── training/                  # Drop Kaggle CSV files here
│       ├── FloodPrediction.csv    # (optional) n-gauhar/Flood-prediction on GitHub
│       ├── flood_prediction_dataset.csv  # (optional) Kaggle: naiyakhalid
│       └── pakistan_flood_disasters.csv  # (optional) Kaggle: alitaqishah
└── config/
    └── settings.py                # AGENT2_BASE_URL setting
```

---

## Model Bundle

`flood_model.joblib` stores a single Python dict:

```python
{
    "flood": XGBClassifier,   # predicts flood probability (0-1)
    "heat":  XGBClassifier,   # predicts heatstroke probability (0-1)
    "meta": {
        "model_version": "1.0.0",
        "training_date": "2025-05-18T...",
        "training_samples": 6000,
        "training_source": "synthetic_pakistan_calibrated",
        "flood_auc": 0.94,
        "flood_accuracy": 0.89,
        "heat_auc": 0.96,
        "heat_accuracy": 0.91,
        "flood_features": [...],
        "heat_features": [...],
    }
}
```

---

## Lazy Training

The model trains **once on first use** (not at app startup) to avoid blocking uvicorn boot.

**Timeline:**
- First `POST /predict/{zone}` call → acquires async lock → trains in thread pool (~20-30s) → saves to `models/flood_model.joblib` → releases lock → all subsequent calls use cached model
- Server restart → loads `flood_model.joblib` from disk (instant)
- `POST /retrain` → deletes existing bundle, retrains in background

**Training sources (in priority order):**
1. CSVs in `backend/data/training/` (see schemas below)
2. Pakistan-calibrated synthetic data (auto-generated, always available)

---

## Feature Vectors

### Flood Model Features (11)

| Feature | Unit | Source |
|---------|------|--------|
| `cumulative_rain_7d` | mm | Agent 2 computed |
| `cumulative_rain_14d` | mm | Agent 2 computed |
| `cumulative_rain_30d` | mm | Agent 2 computed |
| `rain_intensity_24h` | mm | Agent 2 computed |
| `avg_humidity_24h` | % | Agent 2 computed |
| `terrain_elevation` | m | Zone static (settings.py) |
| `drainage_capacity` | 0-1 | Zone static (settings.py) |
| `is_monsoon` | 0/1 | Agent 2 computed |
| `month_sin` | -1 to 1 | Agent 2 computed |
| `month_cos` | -1 to 1 | Agent 2 computed |
| `ndwi_delta` | float | Agent 1 placeholder (0.0) |

### Heatstroke Model Features (8)

| Feature | Unit | Source |
|---------|------|--------|
| `max_temp_24h` | °C | Agent 2 computed |
| `heat_index` | score | Agent 2 computed (temp × humidity) |
| `consecutive_hot_days` | count | Agent 2 computed |
| `avg_humidity_24h` | % | Agent 2 computed |
| `population_density` | /km² | Zone static |
| `is_monsoon` | 0/1 | Agent 2 computed |
| `month_sin` | -1 to 1 | Agent 2 computed |
| `month_cos` | -1 to 1 | Agent 2 computed |

> **Critical:** `FLOOD_FEATURE_ORDER` and `HEAT_FEATURE_ORDER` constants in `agent_predictor.py` define the column order for both training and inference. Never reorder these — silent feature misalignment produces wrong predictions.

---

## 30-Day Forecast Method

### Why Not a Single Prediction?

The current feature vector captures "now." A 30-day forecast requires projecting what conditions will look like on each future day. Agent 3 uses a hybrid approach: **physical decay model + Pakistan monsoon calendar + GloFAS discharge data**.

### Day-by-Day Projection (`FeatureProjector`)

For each day d (1 to 30):

**Rainfall features:**
```
cumulative_rain_7d[d]  = current × exp(-d/20) + expected_daily_rain × 7
cumulative_rain_14d[d] = current × exp(-d/20) × 0.6 + expected_daily_rain × 14
cumulative_rain_30d[d] = current × 0.3 + expected_daily_rain × 30
rain_intensity_24h[d]  = expected_daily_rain[month_d] + discharge_boost[d]
```

Where `exp(-d/20)` is exponential decay with ~14-day half-life (soil drainage).

**GloFAS integration:**
- For each future day d, checks if Agent 2's `/flood-forecast` returned a discharge signal within ±1 day
- If discharge ratio > 1.3: `discharge_boost = (ratio - 1.0) × 20 mm/day`
- This captures upstream river flooding that propagates downstream

**Temperature:**
```
max_temp[d] = PAKISTAN_TEMP_CURVE[future_month] + ZONE_OFFSET[zone_id]
```

Pakistan monthly temperature curve (°C):
| Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec |
|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| 18 | 22 | 28 | 34 | 40 | 43 | 39 | 38 | 36 | 30 | 24 | 19 |

Zone offsets: Karachi +3°C, Multan +2°C, Lahore +1°C, Peshawar 0°C, Islamabad -2°C

**Humidity:**
```
humidity[d] = current × (1 - d/30) + seasonal_baseline × (d/30)
# seasonal_baseline: 72% in monsoon, 45% otherwise
```

**Consecutive hot days:**
- Continues accumulating from current value if projected temp > 40°C
- Resets to 0 if projected temp drops below threshold

### Model Inference

For each projected feature vector:
```python
flood_risk[d] = flood_model.predict_proba(flood_features_d)[1]
heat_risk[d]  = heat_model.predict_proba(heat_features_d)[1]
```

---

## API Endpoints

### Base URL: `http://localhost:8000/api/v1/agent3`

| Method | Endpoint | Description | Used By |
|--------|----------|-------------|---------|
| POST | `/predict/{zone_id}` | 30-day risk forecast | Flutter, Agent 4, Dashboard |
| GET | `/model/info` | Model metadata and accuracy | Monitoring, Dashboard |
| POST | `/retrain` | Force retrain from latest data | Admin, post-CSV-upload |
| POST | `/backtest` | Evaluate against historical events | Validation, Demo |

---

### POST `/predict/{zone_id}`

**Request:** No body (zone_id in path)

**Response:**
```json
{
  "zone_id": "karachi-south",
  "zone_name": "Karachi South",
  "predicted_at": "2025-05-18T14:30:00Z",
  "horizon_days": 30,
  "current_features": {
    "cumulative_rain_7d": 180.5,
    "max_temp_24h": 41.0,
    "is_monsoon": 1,
    ...
  },
  "predictions": [
    { "day": 1, "flood_risk": 0.72, "heatstroke_risk": 0.45, "dominant_factor": "heavy_rainfall_24h" },
    { "day": 2, "flood_risk": 0.68, "heatstroke_risk": 0.46, "dominant_factor": "high_cumulative_rain_7d" },
    ...
    { "day": 30, "flood_risk": 0.31, "heatstroke_risk": 0.52, "dominant_factor": "monsoon_season" }
  ],
  "summary": {
    "peak_flood_day": 1,
    "peak_flood_risk": 0.72,
    "peak_heat_day": 30,
    "peak_heat_risk": 0.54,
    "avg_flood_risk": 0.45,
    "avg_heat_risk": 0.49,
    "high_flood_days": 8,
    "high_heat_days": 3,
    "overall_alert_level": "HIGH"
  }
}
```

**Alert levels:**
| Level | Condition |
|-------|-----------|
| `CRITICAL` | Any risk > 0.8 |
| `HIGH` | Any risk > 0.6 |
| `MODERATE` | Any risk > 0.4 |
| `LOW` | All risks ≤ 0.4 |

**Dominant factor values:**
| Value | Meaning |
|-------|---------|
| `heavy_rainfall_24h` | rain_intensity_24h > 30 mm |
| `high_cumulative_rain_7d` | cumulative_rain_7d > 80 mm |
| `poor_drainage_capacity` | drainage < 0.35 |
| `monsoon_season` | is_monsoon = 1 |
| `prolonged_heat_wave` | consecutive_hot_days > 5 |
| `extreme_heat_index` | heat_index > 38 |
| `extreme_temperature` | max_temp > 43°C |
| `elevated_flood_conditions` | moderate flood signals |
| `elevated_heat_conditions` | moderate heat signals |

---

### GET `/model/info`

```json
{
  "model_version": "1.0.0",
  "model_type": "XGBoostClassifier (dual: flood + heatstroke)",
  "training_date": "2025-05-18T14:00:00",
  "training_samples": 6000,
  "training_source": "synthetic_pakistan_calibrated",
  "flood_model_auc": 0.94,
  "heat_model_auc": 0.96,
  "flood_model_accuracy": 0.89,
  "heat_model_accuracy": 0.91,
  "flood_features": ["cumulative_rain_7d", ...],
  "heat_features": ["max_temp_24h", ...],
  "model_path": "/backend/models/flood_model.joblib",
  "is_loaded": true
}
```

---

### POST `/backtest`

**Request body (optional):**
```json
{
  "zone_ids": ["karachi-south", "lahore-city"],
  "event_types": ["flood", "heat"]
}
```

**Response:**
```json
{
  "run_at": "2025-05-18T14:30:00Z",
  "events_evaluated": 6,
  "flood_direction_accuracy": 0.9,
  "heat_direction_accuracy": 1.0,
  "overall_direction_accuracy": 0.9,
  "events": [
    {
      "event_name": "2022 Super Floods — Karachi",
      "zone_id": "karachi-south",
      "event_type": "flood",
      "event_date": "2022-08-25",
      "known_severity": 0.9,
      "model_prediction": 0.87,
      "correct_direction": true,
      "notes": "flood_pred=0.872, heat_pred=0.134"
    },
    ...
  ]
}
```

**Hardcoded historical events:**
| Event | Zone | Date | Type | Known Severity |
|-------|------|------|------|----------------|
| 2022 Super Floods | karachi-south | Aug 2022 | flood | 0.90 |
| 2022 Super Floods | multan-city | Aug 2022 | flood | 0.85 |
| 2015 Karachi Heatwave | karachi-south | Jun 2015 | heat | 0.95 |
| 2023 Lahore Heatwave | lahore-city | May 2023 | heat | 0.80 |
| 2020 Peshawar Floods | peshawar-city | Jul 2020 | flood | 0.75 |
| Normal Conditions | islamabad-g10 | Jan 2023 | none | 0.05 |

> **Note:** Backtest uses synthetic feature vectors calibrated to each event's season and known conditions. True historical validation requires real sensor data from those dates.

---

## Training Data Schemas

### 1. FloodPrediction.csv (Bangladesh Weather Stations)

**Source:** https://github.com/n-gauhar/Flood-prediction  
**File:** `backend/data/training/FloodPrediction.csv`

| CSV Column | Agent 3 Feature | Mapping |
|-----------|-----------------|---------|
| `Rainfall` | `cumulative_rain_30d` | direct (monthly mm) |
| `Max_Temp` | `max_temp_24h` | direct (°C) |
| `Relative_Humidity` | `avg_humidity_24h` | direct (%) |
| `Month` | `month`, `is_monsoon`, `month_sin`, `month_cos` | derived |
| `Flood?` | `flood_label` | non-empty = 1, empty = 0 |

Terrain defaults: elevation=20m, drainage=0.35, population=8000/km²

### 2. flood_prediction_dataset.csv (Kaggle — naiyakhalid)

**Source:** https://www.kaggle.com/datasets/naiyakhalid/flood-prediction-dataset  
**File:** `backend/data/training/flood_prediction_dataset.csv`

| CSV Column | Agent 3 Feature | Mapping |
|-----------|-----------------|---------|
| `MonsoonIntensity` | `cumulative_rain_*` | × multiplier |
| `TopographyDrainage` | `drainage_capacity` | direct (0-1) |
| `FloodProbability` | `flood_label` | ≥ 0.5 = 1 |

### 3. Synthetic Data (auto-generated fallback)

Generated by `SyntheticDataGenerator` using:
- Pakistan monsoon calendar (Jun-Sep heavy rainfall)
- Zone terrain characteristics
- Pakistan temperature curves (peak May-Jun)
- Probabilistic labels based on domain rules

---

## How to Add Real Training Data

```bash
# 1. Download Kaggle datasets (requires kaggle CLI + API token)
kaggle datasets download naiyakhalid/flood-prediction-dataset -p backend/data/training/ --unzip
kaggle datasets download alitaqishah/pakistan-flood-disasters-dataset-20102025 -p backend/data/training/ --unzip

# 2. Download the GitHub CSV
curl -o backend/data/training/FloodPrediction.csv \
  https://raw.githubusercontent.com/n-gauhar/Flood-prediction/master/FloodPrediction.csv

# 3. Force retrain to pick up new data
curl -X POST http://localhost:8000/api/v1/agent3/retrain

# 4. Check training source in model/info
curl http://localhost:8000/api/v1/agent3/model/info | jq .training_source
```

---

## XGBoost Hyperparameters

Both classifiers share the same configuration:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `n_estimators` | 200 | Good coverage without overfitting on 6k samples |
| `max_depth` | 6 (flood) / 5 (heat) | Controls tree complexity |
| `learning_rate` | 0.05 | Conservative — less overfitting |
| `subsample` | 0.8 | Row sampling for variance reduction |
| `colsample_bytree` | 0.8 | Feature sampling per tree |
| `eval_metric` | logloss | Probabilistic output calibration |
| `n_jobs` | -1 | Use all CPU cores |

---

## How Agent 4 Should Consume This

```python
import httpx

async def get_zone_risk(zone_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"http://localhost:8000/api/v1/agent3/predict/{zone_id}")
        data = resp.json()
        
        summary = data["summary"]
        predictions = data["predictions"]
        
        if summary["overall_alert_level"] in ["CRITICAL", "HIGH"]:
            # Trigger response protocols
            peak_day = summary["peak_flood_day"]
            peak_risk = summary["peak_flood_risk"]
            ...
        
        # Day 1 risk for immediate action decisions
        day_1 = predictions[0]
        flood_now = day_1["flood_risk"]
        heat_now = day_1["heatstroke_risk"]
```

**Recommended thresholds:**
| Risk | Action |
|------|--------|
| > 0.8 | CRITICAL — evacuate/alert NDMA |
| 0.6-0.8 | HIGH — standby response teams, public advisory |
| 0.4-0.6 | MODERATE — enhanced monitoring |
| < 0.4 | LOW — normal operations |

---

## How Flutter App Should Consume This

```dart
Future<void> fetchZonePredictions(String zoneId) async {
  final response = await http.post(
    Uri.parse('$baseUrl/api/v1/agent3/predict/$zoneId'),
  );
  final data = jsonDecode(response.body);
  
  final summary = data['summary'];
  final alertLevel = summary['overall_alert_level'];   // "LOW"|"MODERATE"|"HIGH"|"CRITICAL"
  final peakFloodRisk = summary['peak_flood_risk'];    // 0.0-1.0
  
  // 30-day chart data
  final predictions = (data['predictions'] as List)
    .map((p) => DayRisk(
      day: p['day'],
      flood: p['flood_risk'],
      heat: p['heatstroke_risk'],
    )).toList();
}
```

---

## Environment Variables

No new environment variables are required for Agent 3. Optional config:

```env
# Override where Agent 3 calls Agent 2 (useful for containerized deployment)
AGENT2_BASE_URL=http://agent2-service:8000
```

Default: `http://localhost:8000` (same-process, works with standard uvicorn setup)

---

## How to Run

Agent 3 is part of the same FastAPI app — no separate process needed.

```bash
cd backend
venv\Scripts\activate          # Windows
uvicorn main:app --reload --port 8000

# Test prediction (first call triggers training — ~30s):
curl -X POST http://localhost:8000/api/v1/agent3/predict/karachi-south

# Check model info:
curl http://localhost:8000/api/v1/agent3/model/info

# Run backtest:
curl -X POST http://localhost:8000/api/v1/agent3/backtest -H "Content-Type: application/json" -d '{}'
```

**Swagger UI:** http://localhost:8000/docs → Agent 3 — ML Predictor section

---

## What's Done vs What's Left

| Component | Status | Notes |
|-----------|--------|-------|
| XGBoost flood model | ✅ Done | Trains on CSV or synthetic data |
| XGBoost heatstroke model | ✅ Done | Pakistan temp curve + heat index |
| Lazy model training | ✅ Done | First /predict call triggers training |
| Model persistence | ✅ Done | joblib bundle, reloaded on restart |
| 30-day feature projection | ✅ Done | Decay + monsoon calendar + GloFAS |
| GloFAS discharge integration | ✅ Done | Boosts flood signal per day |
| POST /predict/{zone_id} | ✅ Done | Full 30-day day-by-day output |
| GET /model/info | ✅ Done | Accuracy + training metadata |
| POST /retrain | ✅ Done | Background retrain after new data |
| POST /backtest | ✅ Done | 6 historical Pakistan events |
| CSV dataset loader | ✅ Done | 2 schemas detected automatically |
| Synthetic data generator | ✅ Done | Pakistan-calibrated fallback |
| Agent 4 integration | ❌ Planned | Consume /predict for response triggers |
| SHAP explainability | ❌ Planned | Per-prediction feature importance |
| Agent 1 NDWI feature | ❌ Planned | Currently 0.0 placeholder |
| Time-series model (LSTM) | ❌ Future | Replace projection heuristics |
