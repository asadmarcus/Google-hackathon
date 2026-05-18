# Agent 3 — ML Predictor

## Complete Technical Documentation

> **Purpose**: Predict 30-day flood and heatstroke risk for Pakistani urban zones using a dual-model ML architecture: Prophet (weather forecasting) + XGBoost (flood classification).

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                       AGENT 3: ML Predictor                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUTS (from Agent 2)          ML PIPELINE              OUTPUT          │
│  ─────────────────────         ────────────             ──────────       │
│                                                                          │
│  /forecast/{zone}     ──→  ┌─────────────────┐                          │
│  (16-day ECMWF/GFS)        │  Days 1-16:     │                          │
│                             │  Real Forecast  │──┐                       │
│  /flood-forecast/{zone}     │  (Open-Meteo)   │  │                       │
│  (30-day GloFAS)            └─────────────────┘  │                       │
│                                                  ├──→ XGBoost ──→ Flood  │
│  /features/{zone}     ──→  ┌─────────────────┐  │    Classifier   Risk  │
│  (current conditions)       │  Days 17-30:    │  │                       │
│                             │  Prophet ML     │──┘    PMD Heat ──→ Heat  │
│  Training Data (GEE)  ──→  │  (22yr trained) │       Engine       Risk  │
│  8000 days/province         └─────────────────┘                          │
│                                                                          │
│  OUTPUT: POST /api/v1/agent3/predict/{zone_id}                          │
│  → 30 DayPrediction objects + PredictionSummary                         │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## ML Models

### Model 1: Prophet Weather Forecaster

**Purpose**: Predict daily temperature and rainfall for days 17-30 (beyond ECMWF forecast horizon).

| Property | Value |
|----------|-------|
| Library | Facebook Prophet 1.1.5 |
| Type | Additive time series decomposition |
| Training data | Google Earth Engine daily data (MODIS LST + CHIRPS/GPM) |
| Training samples | ~7,900 days per province (Feb 2000 — Dec 2021) |
| Models | 12 total (6 provinces × 2 variables: temp + rain) |
| Seasonality | Yearly (Fourier) + semi-annual (captures monsoon double-peak) |
| Outputs | Predicted value + 80% confidence interval (upper/lower bounds) |
| Conditioning | Last 7 days of real ECMWF forecast used to detect current anomaly |
| Caching | Trained once, serialized to `.pkl` files in `models/prophet/` |
| Training time | ~15-20s first call, then instant from cache |

**How it works:**
1. Loads daily Temp.csv + Pre.csv from each province's GEE directory
2. Converts GEE precipitation from meters/day → mm/day
3. Fits Prophet with yearly + semi-annual seasonality
4. At prediction time: generates future dates → predict → apply anomaly conditioning
5. Anomaly conditioning: compares last 7 real days vs Prophet's expectation, applies decaying offset

**File**: `services/weather_forecaster.py`

---

### Model 2: XGBoost Flood Classifier

**Purpose**: Given weather conditions (temp, rain, NDSI, NDVI, month, province), predict flood probability.

| Property | Value |
|----------|-------|
| Library | XGBoost 2.1.0 (XGBClassifier) |
| Training data | 6 province CSVs from GEE (1,572 rows, 60 real flood events) |
| Features | Month, Temp, Rain(mm), Ice (NDSI), Veg (NDVI), Province_enc |
| Flood rate | 3.8% (realistic for Pakistan — floods are rare events) |
| Output | `predict_proba()[0][1]` → flood probability 0.0-1.0 |
| Saved to | `models/flood_model.joblib` |

**CRITICAL — Rain_mm input**:
The model was trained on **monthly rainfall totals** (e.g., Punjab July = 97mm → flood).
At inference, we feed **cumulative rainfall to date** (antecedent moisture), NOT daily×30:

```python
# Day 1:  cumulative = 0mm → XGBoost sees dry conditions → ~2% flood
# Day 15: cumulative = 5mm → still dry → ~3% flood  
# Day 25: cumulative = 60mm → saturated soil → ~30% flood
# Day 30: cumulative = 90mm → monsoon month → ~55% flood
```

This models the physics: floods happen **after sustained rain accumulates**, not because it drizzled 1mm today.

**Per-day modulation** (on top of base XGBoost probability):
- GloFAS discharge > 2.0× normal → +50% boost
- GloFAS discharge > 1.5× normal → +20% boost
- GloFAS discharge < 0.8× normal → -50% reduction
- Daily rain > 50mm → +30% acute event bonus
- Daily rain > 30mm → +15% acute event bonus

---

### Model 3: PMD Heat Risk Engine (Rule-Based)

**Purpose**: Estimate heatstroke risk based on Pakistan Meteorological Department advisory thresholds.

This is **NOT ML** — it's explicitly a rule-based engine calibrated to official PMD criteria. Labeled honestly.

| Temp Range | PMD Level | Base Risk |
|-----------|-----------|-----------|
| < 35°C | Normal | 0% |
| 35-38°C | Warm | 3-10% |
| 38-40°C | Hot | 10-20% |
| 40-42°C | Very Hot | 20-40% |
| 42-44°C | PMD Advisory | 40-80% |
| 44-46°C | Danger | 80-90% |
| 46°C+ | Extreme | 90-95% |

**Zone multipliers** (geographic reality):
| Zone | Multiplier | Reason |
|------|-----------|--------|
| jacobabad-city | 1.0 | Hottest city in Pakistan (52°C recorded) |
| multan-city | 0.95 | Interior Punjab extreme heat zone |
| sukkur-city | 0.85 | Upper Sindh heat corridor |
| lahore-city | 0.75 | Punjab interior, active heatwave zone |
| peshawar-city | 0.55 | Warm but drier |
| islamabad-g10 | 0.4 | Higher elevation (507m), cooler |
| karachi-south | 0.35 | Coastal, ocean-moderated |
| quetta-city | 0.3 | High altitude (1680m), much cooler |

**Seasonal multiplier**: Only May-June = full risk (1.0). July = 0.6 (monsoon cooling). Oct-Mar = 0.05.

---

## Prediction Pipeline (Step by Step)

When `POST /api/v1/agent3/predict/{zone_id}` is called:

### Step 1: Load/Train Models (lazy, cached)
```
flood_model.joblib exists? → load it
Prophet models exist? → load them
Otherwise → train from training data (one-time cost)
```

### Step 2: Fetch Real Data from Agent 2
```
GET /api/v1/agent2/features/{zone_id}     → current conditions
GET /api/v1/agent2/forecast/{zone_id}     → 16-day ECMWF forecast
GET /api/v1/agent2/flood-forecast/{zone_id} → 30-day GloFAS discharge
```

### Step 3: Generate Prophet Forecast (days 17-30)
```
Prophet.forecast(province, last_16_days_temps, last_16_days_rains, start=day17, days=14)
→ Returns temp + rain + confidence intervals for each day
```

### Step 4: Compute Cumulative Rain Array
```python
total_daily_rains = []
for day 1-16:  use real ECMWF forecast rain
for day 17-30: use Prophet predicted rain (or seasonal fallback)

# This gives us the rainfall trajectory for the whole month
```

### Step 5: Per-Day Prediction Loop (×30)
```python
for day in 1..30:
    # A) Project weather features
    if day <= 16:
        temp, rain = ECMWF real forecast
    else:
        temp, rain = Prophet ML forecast
    
    # B) XGBoost flood prediction
    cumulative_rain = sum(total_daily_rains[:day])
    monthly_pace = cumulative_rain * (30 / day)
    rain_for_model = 0.7 * cumulative_rain + 0.3 * monthly_pace
    flood_prob = xgboost.predict_proba([Month, Temp, rain_for_model, Ice, Veg, Province])
    
    # C) GloFAS discharge modulation (per-day from real hydrology model)
    discharge = get_glofas_for_day(day)
    flood_prob *= discharge_multiplier
    
    # D) Daily intensity bonus (acute storm events)
    if daily_rain > 50mm: flood_prob += 0.30
    
    # E) PMD heat risk
    heat_prob = compute_heat_risk(temp, month, zone_id)
    
    # F) Build DayPrediction
    → {day, date, flood_risk, heatstroke_risk, alert_level, confidence, data_source}
```

---

## DayPrediction Output Schema

```python
class DayPrediction(BaseModel):
    day: int                     # 1-30
    date: str                    # "2026-05-19"
    flood_risk: float            # 0.0 - 1.0
    heatstroke_risk: float       # 0.0 - 1.0
    dominant_factor: str         # "heavy_monsoon_rain" / "extreme_heat" / etc.
    expected_temp_c: float       # Projected temperature
    expected_rain_mm: float      # Projected daily rainfall
    expected_humidity: float     # Projected humidity
    alert_level: str             # NONE / LOW / MODERATE / HIGH / CRITICAL
    confidence: str              # "high" / "moderate" / "low"
    data_source: str             # "ecmwf_forecast" / "ecmwf_extended" / "xgboost_forecast" / "prophet_forecast"
```

**Alert level thresholds:**
| Max Risk | Alert |
|----------|-------|
| ≥ 75% | CRITICAL |
| ≥ 50% | HIGH |
| ≥ 25% | MODERATE |
| ≥ 10% | LOW |
| < 10% | NONE |

---

## Data Sources & Confidence Tiers

| Days | Weather Source | Data Source Label | Confidence |
|------|--------------|-------------------|------------|
| 1-7 | Open-Meteo ECMWF/GFS | `ecmwf_forecast` | HIGH |
| 8-16 | Open-Meteo extended (16-day) | `ecmwf_extended` | MODERATE |
| 17-30 | Prophet ML (22yr trained) | `prophet_forecast` or `xgboost_forecast` | LOW |

**For flood risk specifically:**
| Signal | Source | Type |
|--------|--------|------|
| Base probability | XGBoost (trained on real floods) | ML classification |
| Weather input (days 1-16) | ECMWF/GFS via Open-Meteo | Real meteorological model |
| Weather input (days 17-30) | Prophet (22yr daily GEE data) | ML time series |
| Per-day discharge | GloFAS via Open-Meteo flood API | Real hydrological model |
| Daily intensity | Forecast rain values | Direct input |

---

## Zone → Province Mapping

Agent 3 maps each zone to a province for the XGBoost model:

```python
ZONE_TO_PROVINCE = {
    "islamabad-g10": "Federal",
    "lahore-city": "Punjab",
    "karachi-south": "Sindh",
    "peshawar-city": "Kpk",
    "multan-city": "Punjab",
    "jacobabad-city": "Sindh",
    "sukkur-city": "Sindh",
    "quetta-city": "Balochistan",
}
```

Province encoding for XGBoost: Punjab=0, Sindh=1, Federal=2, Kpk=3, Balochistan=4, Gilgit=5

---

## Training Data Details

### For XGBoost (monthly data)
Located in `data/training/{Province}_training.csv`:
```
Month, Year, Temp, Ice, veg, Flood, Rain(mm)
3,     2000, 30.6, -0.17, 3660, False, 7.56
7,     2010, 35.3, -0.05, 2563, True,  96.9   ← real flood event
```
- 6 files, ~262 rows each (22 years × 12 months, with gaps)
- Flood column: True/False from NDMA Pakistan records
- 60 total flood events across all provinces (3.8% positive rate)

### For Prophet (daily data)
Located in `data/training/{Province}/`:
- `Temp.csv` + `temp1.csv`: MODIS Land Surface Temperature (daily)
- `Pre.csv` + `pre1.csv`: CHIRPS/GPM precipitation (daily)
- ~8,000 days per province (Feb 2000 — Dec 2021)
- `Flood.csv`: Monthly flood labels
- `Ndsi.csv`, `Veg.csv`: Supplementary indices

---

## Known Limitations & Honest Labels

1. **Days 17-30 confidence is "low"**: No weather model can predict specific daily conditions at 3-4 weeks. Prophet gives seasonally-aware estimates with uncertainty intervals.
2. **Heat model is rule-based**: Labeled as such. No ML training data for heatstroke events in Pakistan.
3. **Social/NDMA services are simulated**: Marked with confidence=0.50 in signal store.
4. **Karachi may show 0% heat**: Coastal temperatures (~33°C in May) fall below the 35°C heat threshold with the 0.35 zone multiplier. This is correct — Karachi's heat risk is humidity-amplified, which this model doesn't yet capture.
5. **Monthly → daily translation**: XGBoost was trained on monthly data. We use cumulative-to-date as the best proxy. Not perfect, but physically motivated (antecedent moisture).

---

## Files

| File | Purpose |
|------|---------|
| `agents/agent_predictor.py` | Main Agent 3 module: models, projector, endpoints |
| `services/weather_forecaster.py` | Prophet weather forecaster (22yr daily data) |
| `models/flood_model.joblib` | Trained XGBoost classifier (auto-generated) |
| `models/prophet/` | Trained Prophet models (auto-generated on first call) |
| `data/training/*.csv` | Monthly aggregates for XGBoost |
| `data/training/{Province}/` | Daily data for Prophet |

---

## How to Modify

### Add a new zone:
1. Add to `config/settings.py` ZONES list (id, name, lat, lng, province, elevation, drainage, population)
2. Add to `ZONE_TO_PROVINCE` in `agent_predictor.py`
3. Add to `ZONE_HEAT_MULTIPLIER` in `agent_predictor.py`
4. Add to `static/index.html` (zones array, zoneNames, zoneProvinces)

### Retrain flood model:
Delete `models/flood_model.joblib` → next API call will retrain from CSVs.

### Retrain Prophet models:
Delete `models/prophet/` directory → next prediction call will retrain (~15-20s).

### Adjust heat thresholds:
Edit `compute_heat_risk()` in `agent_predictor.py`. Thresholds are calibrated to PMD advisories.
