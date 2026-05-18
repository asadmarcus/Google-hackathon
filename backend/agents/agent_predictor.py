"""
CIRO — Agent 3: ML Predictor
=============================
XGBoost flood and heatstroke risk prediction for Pakistani urban zones.
Consumes Agent 2 feature vectors, outputs 30-day day-by-day risk forecasts.

Model bundle: backend/models/flood_model.joblib
  Saved as: {"flood": XGBClassifier, "heat": XGBClassifier, "meta": Dict}

Training (lazy — first /predict call triggers training if bundle is absent):
  1. Scan backend/data/training/*.csv for known dataset schemas (Kaggle/GitHub)
  2. Fall back to Pakistan-calibrated synthetic data if no CSVs are found
  3. Train XGBoost classifiers, evaluate on holdout, save bundle, cache in memory

30-day forecast method:
  1. Fetch current feature vector  → GET /api/v1/agent2/features/{zone_id}
  2. Fetch GloFAS discharge data   → GET /api/v1/agent2/flood-forecast/{zone_id}
  3. Project features day-by-day   → rain decay + monsoon calendar + discharge signals
  4. Apply both classifiers        → flood_risk (0-1) and heatstroke_risk (0-1) per day
  5. Return [{day, flood_risk, heatstroke_risk}, ...] for days 1-30

Datasets (place CSV files in backend/data/training/ to use real data):
  - FloodPrediction.csv              (n-gauhar/Flood-prediction on GitHub)
  - flood_prediction_dataset.csv     (naiyakhalid/flood-prediction-dataset on Kaggle)
  - pakistan_flood_disasters.csv     (alitaqishah/pakistan-flood-disasters-dataset on Kaggle)

If no CSVs are present, Pakistan-calibrated synthetic data is auto-generated.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import joblib
import numpy as np
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from config.settings import settings

logger = logging.getLogger("ciro.agent3")
router = APIRouter()

# ─── Paths ─────────────────────────────────────────────────────────────────────

_BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_PATH = _BASE_DIR / "models" / "flood_model.joblib"
TRAINING_DATA_DIR = _BASE_DIR / "data" / "training"
MODEL_VERSION = "1.0.0"

# ─── Feature Definitions ───────────────────────────────────────────────────────

# Column order MUST match for both training and inference — never reorder.
FLOOD_FEATURE_ORDER: List[str] = [
    "cumulative_rain_7d",
    "cumulative_rain_14d",
    "cumulative_rain_30d",
    "rain_intensity_24h",
    "avg_humidity_24h",
    "terrain_elevation",
    "drainage_capacity",
    "is_monsoon",
    "month_sin",
    "month_cos",
    "ndwi_delta",
]

HEAT_FEATURE_ORDER: List[str] = [
    "max_temp_24h",
    "heat_index",
    "consecutive_hot_days",
    "avg_humidity_24h",
    "population_density",
    "is_monsoon",
    "month_sin",
    "month_cos",
]

# Pakistan monthly temperature curve (°C peak daytime, zone-neutral baseline)
_PAKISTAN_TEMP_CURVE: Dict[int, float] = {
    1: 18.0, 2: 22.0, 3: 28.0, 4: 34.0, 5: 40.0, 6: 43.0,
    7: 39.0, 8: 38.0, 9: 36.0, 10: 30.0, 11: 24.0, 12: 19.0,
}

# Zone-specific temperature offsets relative to baseline
_ZONE_TEMP_OFFSET: Dict[str, float] = {
    "karachi-south": 3.0,
    "multan-city": 2.0,
    "lahore-city": 1.0,
    "peshawar-city": 0.0,
    "islamabad-g10": -2.0,
}

# Expected daily rainfall (mm) per month for Pakistan monsoon zones
_MONSOON_RAIN_MM_PER_DAY: Dict[int, float] = {
    1: 1.5, 2: 2.0, 3: 3.0, 4: 4.0, 5: 5.0, 6: 8.0,
    7: 16.0, 8: 19.0, 9: 11.0, 10: 3.5, 11: 2.0, 12: 1.5,
}

# ─── Schemas ───────────────────────────────────────────────────────────────────


class DayPrediction(BaseModel):
    """Single-day risk output in the 30-day forecast."""
    day: int
    flood_risk: float           # 0.0 - 1.0
    heatstroke_risk: float      # 0.0 - 1.0
    dominant_factor: str        # human-readable main driver


class PredictionSummary(BaseModel):
    """Aggregate stats over the 30-day window."""
    peak_flood_day: int
    peak_flood_risk: float
    peak_heat_day: int
    peak_heat_risk: float
    avg_flood_risk: float
    avg_heat_risk: float
    high_flood_days: int        # days with flood_risk > 0.6
    high_heat_days: int         # days with heatstroke_risk > 0.6
    overall_alert_level: str    # LOW / MODERATE / HIGH / CRITICAL


class ZonePrediction(BaseModel):
    """Full 30-day prediction response for a zone."""
    zone_id: str
    zone_name: str
    predicted_at: str
    horizon_days: int
    current_features: Dict[str, Any]
    predictions: List[DayPrediction]
    summary: PredictionSummary


class ModelInfo(BaseModel):
    """Model metadata and training statistics."""
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    model_type: str
    training_date: str
    training_samples: int
    training_source: str
    flood_model_auc: float
    heat_model_auc: float
    flood_model_accuracy: float
    heat_model_accuracy: float
    flood_features: List[str]
    heat_features: List[str]
    model_path: str
    is_loaded: bool


class BacktestRequest(BaseModel):
    """Optional filter for backtest — defaults to all zones and events."""
    zone_ids: Optional[List[str]] = None
    event_types: Optional[List[str]] = None  # "flood", "heat", or both


class BacktestEventResult(BaseModel):
    """Model evaluation against one known historical event."""
    model_config = ConfigDict(protected_namespaces=())

    event_name: str
    zone_id: str
    event_type: str
    event_date: str
    known_severity: float
    model_prediction: float
    correct_direction: bool     # did the model predict high risk for a real event?
    notes: str


class BacktestResponse(BaseModel):
    """Aggregate backtest results."""
    run_at: str
    events_evaluated: int
    flood_direction_accuracy: float
    heat_direction_accuracy: float
    overall_direction_accuracy: float
    events: List[BacktestEventResult]


# ─── Module-Level Model State ──────────────────────────────────────────────────

_model_bundle: Optional[Dict[str, Any]] = None   # loaded once, reused
_training_lock = asyncio.Lock()


async def _ensure_models_loaded() -> Dict[str, Any]:
    """Load or train model bundle. Thread-safe via asyncio lock."""
    global _model_bundle
    if _model_bundle is not None:
        return _model_bundle

    async with _training_lock:
        if _model_bundle is not None:  # double-check after acquiring lock
            return _model_bundle

        if MODEL_PATH.exists():
            logger.info("🤖 Loading model bundle from %s", MODEL_PATH)
            _model_bundle = joblib.load(MODEL_PATH)
            logger.info("🤖 Model bundle loaded (trained %s)", _model_bundle["meta"]["training_date"])
        else:
            logger.info("🤖 No model file found — training now...")
            _model_bundle = await asyncio.to_thread(_train_and_save)
            logger.info("🤖 Training complete — models cached in memory")

    return _model_bundle


# ─── Dataset Loader ────────────────────────────────────────────────────────────


class DatasetLoader:
    """
    Scans backend/data/training/ for known CSV schemas and normalizes them
    into (X_flood, y_flood, X_heat, y_heat) DataFrames.

    Supported schemas (detected by column names):
      - FloodPrediction.csv  (Bangladesh weather stations, n-gauhar/Flood-prediction)
      - flood_prediction_dataset.csv  (Kaggle naiyakhalid)
      - Any CSV with at least: rainfall, temperature, humidity, month, flood_label columns
    """

    _SCHEMA_DETECTORS = {
        "bangladesh_stations": {
            "required": {"Rainfall", "Max_Temp", "Relative_Humidity", "Month"},
            "flood_col": "Flood?",
        },
        "kaggle_flood": {
            "required": {"MonsoonIntensity", "TopographyDrainage", "RiverManagement"},
            "flood_col": "FloodProbability",
        },
    }

    def load(self) -> Optional[Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]]:
        """
        Return (X_flood, y_flood, X_heat, y_heat) or None if no usable files.
        """
        csv_files = list(TRAINING_DATA_DIR.glob("*.csv"))
        if not csv_files:
            return None

        flood_frames, heat_frames = [], []

        for csv_path in csv_files:
            try:
                df = pd.read_csv(csv_path)
                schema = self._detect_schema(df)
                if schema == "bangladesh_stations":
                    f_df, h_df = self._parse_bangladesh(df)
                    flood_frames.append(f_df)
                    heat_frames.append(h_df)
                    logger.info("  📂 Loaded %s (%d rows, schema: %s)", csv_path.name, len(df), schema)
                elif schema == "kaggle_flood":
                    f_df = self._parse_kaggle_flood(df)
                    flood_frames.append(f_df)
                    logger.info("  📂 Loaded %s (%d rows, schema: %s)", csv_path.name, len(df), schema)
                else:
                    logger.warning("  ⚠ Unrecognised schema in %s — skipping", csv_path.name)
            except Exception as exc:
                logger.warning("  ⚠ Failed to load %s: %s", csv_path.name, exc)

        if not flood_frames:
            return None

        flood_data = pd.concat(flood_frames, ignore_index=True).dropna()

        X_flood = flood_data[FLOOD_FEATURE_ORDER]
        y_flood = flood_data["flood_label"].astype(int)

        if heat_frames:
            heat_data = pd.concat(heat_frames, ignore_index=True).dropna()
            X_heat = heat_data[HEAT_FEATURE_ORDER]
            y_heat = heat_data["heat_label"].astype(int)
        else:
            # No heat-capable CSVs (e.g. only kaggle_flood) — synthesize heat data
            logger.info("  ℹ No heat training data in CSVs — synthesising heat samples")
            _, _, X_heat, y_heat = SyntheticDataGenerator().generate(n_samples=len(X_flood))

        logger.info("  📊 Dataset: %d flood samples, %d heat samples", len(X_flood), len(X_heat))
        return X_flood, y_flood, X_heat, y_heat

    def _detect_schema(self, df: pd.DataFrame) -> str:
        cols = set(df.columns)
        for schema_name, spec in self._SCHEMA_DETECTORS.items():
            if spec["required"].issubset(cols):
                return schema_name
        return "unknown"

    def _parse_bangladesh(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Map Bangladesh weather station schema to CIRO feature vectors."""
        df = df.copy()
        df["Month"] = pd.to_numeric(df["Month"], errors="coerce")
        df["Rainfall"] = pd.to_numeric(df["Rainfall"], errors="coerce").fillna(0)
        df["Max_Temp"] = pd.to_numeric(df["Max_Temp"], errors="coerce").fillna(30)
        df["Relative_Humidity"] = pd.to_numeric(df["Relative_Humidity"], errors="coerce").fillna(60)
        df["flood_label"] = df["Flood?"].notna() & (df["Flood?"].astype(str).str.strip() != "")
        df["flood_label"] = df["flood_label"].astype(int)

        # Approximate cumulative windows from monthly rainfall
        df["cumulative_rain_7d"] = df["Rainfall"] * (7 / 30)
        df["cumulative_rain_14d"] = df["Rainfall"] * (14 / 30)
        df["cumulative_rain_30d"] = df["Rainfall"]
        df["rain_intensity_24h"] = df["Rainfall"] / 30
        df["avg_humidity_24h"] = df["Relative_Humidity"]
        df["terrain_elevation"] = 20.0      # Bangladesh avg
        df["drainage_capacity"] = 0.35      # poor drainage (flood-prone)
        df["population_density"] = 8000.0
        df["is_monsoon"] = df["Month"].isin([6, 7, 8, 9]).astype(int)
        df["month_sin"] = np.sin(2 * np.pi * df["Month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["Month"] / 12)
        df["ndwi_delta"] = 0.0

        df["max_temp_24h"] = df["Max_Temp"]
        df["heat_index"] = df["Max_Temp"] * (df["Relative_Humidity"] / 100)
        df["consecutive_hot_days"] = (df["Max_Temp"] > 38).astype(int) * 3  # rough proxy
        df["heat_label"] = (df["Max_Temp"] > 38).astype(int)

        return df[FLOOD_FEATURE_ORDER + ["flood_label"]], df[HEAT_FEATURE_ORDER + ["heat_label"]]

    def _parse_kaggle_flood(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map Kaggle flood prediction schema to CIRO flood features."""
        df = df.copy()
        df["flood_label"] = (df["FloodProbability"] >= 0.5).astype(int)

        # Kaggle dataset has direct probability features — map to our schema
        df["cumulative_rain_7d"] = df.get("MonsoonIntensity", 5) * 14
        df["cumulative_rain_14d"] = df.get("MonsoonIntensity", 5) * 28
        df["cumulative_rain_30d"] = df.get("MonsoonIntensity", 5) * 60
        df["rain_intensity_24h"] = df.get("MonsoonIntensity", 5) * 2
        df["avg_humidity_24h"] = 70.0
        df["terrain_elevation"] = (1 - df.get("TopographyDrainage", 0.5)) * 500
        df["drainage_capacity"] = df.get("TopographyDrainage", 0.5)
        df["is_monsoon"] = 1
        df["month_sin"] = np.sin(2 * np.pi * 7 / 12)   # July — peak monsoon
        df["month_cos"] = np.cos(2 * np.pi * 7 / 12)
        df["ndwi_delta"] = 0.0

        return df[FLOOD_FEATURE_ORDER + ["flood_label"]]


# ─── Synthetic Data Generator ──────────────────────────────────────────────────


class SyntheticDataGenerator:
    """
    Generates Pakistan-calibrated synthetic training data when no CSV files exist.

    Flood model rules (domain-derived):
      - flood=1 when cumulative_rain_7d > 75 AND drainage_capacity < 0.5 AND is_monsoon
      - flood=1 when cumulative_rain_30d > 180 AND elevation < 250
      - flood=1 when rain_intensity_24h > 40
      - Probabilistic noise added for realistic decision boundary

    Heat model rules:
      - heat=1 when max_temp_24h > 40 AND heat_index > 30
      - heat=1 when consecutive_hot_days > 5 AND max_temp_24h > 38
      - heat=1 in peak summer (month 5-6) with temp > 37
    """

    def generate(self, n_samples: int = 6000) -> Tuple[
        pd.DataFrame, pd.Series, pd.DataFrame, pd.Series
    ]:
        rng = np.random.default_rng(42)
        months = rng.integers(1, 13, size=n_samples)
        is_monsoon = np.isin(months, [6, 7, 8, 9]).astype(int)
        month_sin = np.sin(2 * np.pi * months / 12)
        month_cos = np.cos(2 * np.pi * months / 12)

        # Monsoon months get heavier rainfall
        monsoon_multiplier = np.where(is_monsoon, rng.uniform(3, 8, n_samples), rng.uniform(0.1, 1.5, n_samples))
        daily_rain = monsoon_multiplier * rng.gamma(2, 3, n_samples)

        cumulative_rain_7d = daily_rain * 7 * rng.uniform(0.7, 1.3, n_samples)
        cumulative_rain_14d = daily_rain * 14 * rng.uniform(0.7, 1.3, n_samples)
        cumulative_rain_30d = daily_rain * 30 * rng.uniform(0.7, 1.3, n_samples)
        rain_intensity_24h = daily_rain * rng.uniform(0.5, 2.5, n_samples)

        # Temperature follows Pakistan seasonal curve
        base_temps = np.array([_PAKISTAN_TEMP_CURVE[m] for m in months])
        max_temp = base_temps + rng.normal(0, 3, n_samples)
        humidity = np.where(is_monsoon, rng.uniform(60, 90, n_samples), rng.uniform(30, 65, n_samples))
        heat_index = max_temp * (humidity / 100)

        # consecutive_hot_days: more likely in hot months
        hot_base = np.where(np.isin(months, [4, 5, 6, 9, 10]), rng.integers(0, 15, n_samples), rng.integers(0, 3, n_samples))
        consecutive_hot_days = hot_base.astype(float)

        elevation = rng.uniform(10, 600, n_samples)
        drainage = rng.uniform(0.2, 0.8, n_samples)
        population = rng.uniform(1500, 15000, n_samples)
        ndwi = rng.uniform(-0.05, 0.15, n_samples)

        # ── Flood labels ──────────────────────────────────────────────────────
        flood_score = (
            np.clip(cumulative_rain_7d / 80, 0, 1) * 0.35
            + np.clip(rain_intensity_24h / 40, 0, 1) * 0.25
            + is_monsoon * 0.15
            + (1 - drainage) * 0.15
            + np.clip((200 - elevation) / 200, 0, 1) * 0.10
        )
        flood_label = (flood_score + rng.normal(0, 0.08, n_samples) > 0.52).astype(int)

        # ── Heat labels ───────────────────────────────────────────────────────
        heat_score = (
            np.clip((max_temp - 35) / 15, 0, 1) * 0.45
            + np.clip(heat_index / 40, 0, 1) * 0.25
            + np.clip(consecutive_hot_days / 10, 0, 1) * 0.20
            + np.isin(months, [4, 5, 6]).astype(float) * 0.10
        )
        heat_label = (heat_score + rng.normal(0, 0.08, n_samples) > 0.52).astype(int)

        flood_df = pd.DataFrame({
            "cumulative_rain_7d": cumulative_rain_7d,
            "cumulative_rain_14d": cumulative_rain_14d,
            "cumulative_rain_30d": cumulative_rain_30d,
            "rain_intensity_24h": rain_intensity_24h,
            "avg_humidity_24h": humidity,
            "terrain_elevation": elevation,
            "drainage_capacity": drainage,
            "is_monsoon": is_monsoon,
            "month_sin": month_sin,
            "month_cos": month_cos,
            "ndwi_delta": ndwi,
        })

        heat_df = pd.DataFrame({
            "max_temp_24h": max_temp,
            "heat_index": heat_index,
            "consecutive_hot_days": consecutive_hot_days,
            "avg_humidity_24h": humidity,
            "population_density": population,
            "is_monsoon": is_monsoon,
            "month_sin": month_sin,
            "month_cos": month_cos,
        })

        logger.info("  🔧 Synthetic data: %d samples (flood pos=%.1f%%, heat pos=%.1f%%)",
                    n_samples, flood_label.mean() * 100, heat_label.mean() * 100)

        return flood_df, pd.Series(flood_label), heat_df, pd.Series(heat_label)


# ─── Model Trainer ─────────────────────────────────────────────────────────────


def _train_and_save() -> Dict[str, Any]:
    """
    Synchronous training function (runs in thread pool via run_in_executor).
    Returns the model bundle dict and saves it to MODEL_PATH.
    """
    logger.info("🤖 ═══ TRAINING START ═══")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    loader = DatasetLoader()
    real_data = loader.load()
    training_source = "csv_files"

    if real_data is not None:
        X_flood, y_flood, X_heat, y_heat = real_data
        logger.info("  ✓ Using real CSV training data (%d flood / %d heat samples)",
                    len(X_flood), len(X_heat))
    else:
        gen = SyntheticDataGenerator()
        X_flood, y_flood, X_heat, y_heat = gen.generate(n_samples=6000)
        training_source = "synthetic_pakistan_calibrated"
        logger.info("  ✓ No CSVs found — using synthetic training data")

    # ── Train flood model ─────────────────────────────────────────────────────
    Xf_train, Xf_test, yf_train, yf_test = train_test_split(
        X_flood, y_flood, test_size=0.2, random_state=42, stratify=y_flood
    )
    flood_model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    flood_model.fit(Xf_train, yf_train, eval_set=[(Xf_test, yf_test)], verbose=False)
    flood_proba = flood_model.predict_proba(Xf_test)[:, 1]
    flood_auc = float(roc_auc_score(yf_test, flood_proba))
    flood_acc = float(accuracy_score(yf_test, flood_model.predict(Xf_test)))
    logger.info("  ✓ Flood model: AUC=%.3f  Accuracy=%.3f", flood_auc, flood_acc)

    # ── Train heatstroke model ────────────────────────────────────────────────
    Xh_train, Xh_test, yh_train, yh_test = train_test_split(
        X_heat, y_heat, test_size=0.2, random_state=42, stratify=y_heat
    )
    heat_model = XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    heat_model.fit(Xh_train, yh_train, eval_set=[(Xh_test, yh_test)], verbose=False)
    heat_proba = heat_model.predict_proba(Xh_test)[:, 1]
    heat_auc = float(roc_auc_score(yh_test, heat_proba))
    heat_acc = float(accuracy_score(yh_test, heat_model.predict(Xh_test)))
    logger.info("  ✓ Heat model:  AUC=%.3f  Accuracy=%.3f", heat_auc, heat_acc)

    # ── Save bundle ───────────────────────────────────────────────────────────
    bundle: Dict[str, Any] = {
        "flood": flood_model,
        "heat": heat_model,
        "meta": {
            "model_version": MODEL_VERSION,
            "training_date": datetime.utcnow().isoformat(),
            "training_samples": len(X_flood),
            "training_source": training_source,
            "flood_auc": flood_auc,
            "flood_accuracy": flood_acc,
            "heat_auc": heat_auc,
            "heat_accuracy": heat_acc,
            "flood_features": FLOOD_FEATURE_ORDER,
            "heat_features": HEAT_FEATURE_ORDER,
        },
    }
    joblib.dump(bundle, MODEL_PATH)
    logger.info("🤖 ═══ TRAINING COMPLETE ═══ Saved to %s", MODEL_PATH)
    return bundle


# ─── Feature Projector ─────────────────────────────────────────────────────────


class FeatureProjector:
    """
    Projects a current Agent 2 feature vector forward day-by-day.

    Flood projection:
      - Cumulative rain decays exponentially as water drains (τ ≈ 20 days)
      - Expected daily rain from Pakistan monsoon calendar is added
      - GloFAS discharge ratio (from /flood-forecast) boosts rain signal on matching days

    Heat projection:
      - Temperature follows _PAKISTAN_TEMP_CURVE + zone offset
      - Consecutive hot days accumulates while projected temp > 40°C, resets otherwise
      - humidity follows monsoon curve (higher in Jun-Sep)
    """

    def project(
        self,
        current: Dict[str, Any],
        zone: Dict[str, Any],
        flood_signals: List[Dict],
        day: int,
    ) -> Dict[str, Any]:
        """Return a projected feature dict for `day` days from today."""
        future_date = datetime.utcnow() + timedelta(days=day)
        fm = future_date.month

        # Rainfall decay: half-life ~14 days
        decay = math.exp(-day / 20.0)
        expected_daily = _MONSOON_RAIN_MM_PER_DAY.get(fm, 2.0)

        # Check GloFAS discharge for this future day (boosts flood signal)
        discharge_ratio = self._discharge_for_day(flood_signals, future_date)
        rain_boost = max(0.0, (discharge_ratio - 1.0) * 20) if discharge_ratio > 1.3 else 0.0

        proj: Dict[str, Any] = {}

        # Rainfall features
        proj["cumulative_rain_7d"] = (
            current["cumulative_rain_7d"] * decay + expected_daily * 7 + rain_boost * 7
        )
        proj["cumulative_rain_14d"] = (
            current["cumulative_rain_14d"] * decay * 0.6 + expected_daily * 14 + rain_boost * 14
        )
        proj["cumulative_rain_30d"] = (
            current["cumulative_rain_30d"] * 0.3 + expected_daily * 30
        )
        proj["rain_intensity_24h"] = expected_daily + rain_boost

        # Temperature
        base_temp = _PAKISTAN_TEMP_CURVE[fm] + _ZONE_TEMP_OFFSET.get(zone["id"], 0.0)
        proj["max_temp_24h"] = base_temp

        # Humidity — higher in monsoon
        base_humidity = current["avg_humidity_24h"]
        monsoon_humidity = 72.0 if fm in [6, 7, 8, 9] else 45.0
        # Blend current toward seasonal mean over 30 days
        blend = min(1.0, day / 30.0)
        proj["avg_humidity_24h"] = base_humidity * (1 - blend) + monsoon_humidity * blend

        proj["heat_index"] = proj["max_temp_24h"] * (proj["avg_humidity_24h"] / 100)

        # Consecutive hot days
        if base_temp > 40.0:
            proj["consecutive_hot_days"] = (
                current.get("consecutive_hot_days", 0) + day
                if day <= 7
                else float(day)
            )
        else:
            proj["consecutive_hot_days"] = 0.0

        # Static zone features (unchanged)
        proj["terrain_elevation"] = zone.get("elevation_m", current.get("terrain_elevation", 300))
        proj["drainage_capacity"] = zone.get("drainage_capacity", current.get("drainage_capacity", 0.5))
        proj["population_density"] = zone.get("population_density", current.get("population_density", 3000))

        # Seasonal
        proj["month"] = fm
        proj["is_monsoon"] = 1 if fm in [6, 7, 8, 9] else 0
        proj["month_sin"] = math.sin(2 * math.pi * fm / 12)
        proj["month_cos"] = math.cos(2 * math.pi * fm / 12)
        proj["ndwi_delta"] = current.get("ndwi_delta", 0.0)

        return proj

    @staticmethod
    def _discharge_for_day(flood_signals: List[Dict], target_date: datetime) -> float:
        """Return the GloFAS discharge ratio for the target date, or 1.0 if none."""
        target_day = target_date.date()
        for sig in flood_signals:
            try:
                ts = sig.get("timestamp", "")
                sig_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                if abs((sig_date - target_day).days) <= 1:
                    return float(sig.get("value", 1.0))
            except (ValueError, KeyError):
                continue
        return 1.0


# ─── Risk Predictor ────────────────────────────────────────────────────────────


class RiskPredictor:
    """Orchestrates feature projection → model inference → response assembly."""

    def __init__(self, bundle: Dict[str, Any]) -> None:
        self.flood_model: XGBClassifier = bundle["flood"]
        self.heat_model: XGBClassifier = bundle["heat"]
        self.meta: Dict[str, Any] = bundle["meta"]
        self.projector = FeatureProjector()

    def predict_30_days(
        self,
        current_features: Dict[str, Any],
        zone: Dict[str, Any],
        flood_signals: List[Dict],
    ) -> List[DayPrediction]:
        """
        Generate day-by-day predictions for days 1-30.

        Args:
            current_features: Feature dict from Agent 2 /features/{zone_id}
            zone: Zone config dict from settings.ZONES
            flood_signals: GloFAS signals from Agent 2 /flood-forecast/{zone_id}

        Returns:
            List of 30 DayPrediction objects.
        """
        days: List[DayPrediction] = []

        for day in range(1, 31):
            projected = self.projector.project(current_features, zone, flood_signals, day)

            # Build feature arrays in correct column order
            flood_vec = np.array([[projected[f] for f in FLOOD_FEATURE_ORDER]])
            heat_vec = np.array([[projected[f] for f in HEAT_FEATURE_ORDER]])

            flood_risk = float(self.flood_model.predict_proba(flood_vec)[0][1])
            heat_risk = float(self.heat_model.predict_proba(heat_vec)[0][1])

            days.append(DayPrediction(
                day=day,
                flood_risk=round(flood_risk, 4),
                heatstroke_risk=round(heat_risk, 4),
                dominant_factor=_dominant_factor(projected, flood_risk, heat_risk),
            ))

        return days

    @staticmethod
    def build_summary(predictions: List[DayPrediction]) -> PredictionSummary:
        """Aggregate 30-day predictions into a summary object."""
        flood_risks = [p.flood_risk for p in predictions]
        heat_risks = [p.heatstroke_risk for p in predictions]

        peak_flood_idx = int(np.argmax(flood_risks))
        peak_heat_idx = int(np.argmax(heat_risks))

        avg_flood = float(np.mean(flood_risks))
        avg_heat = float(np.mean(heat_risks))
        max_risk = max(max(flood_risks), max(heat_risks))

        if max_risk >= 0.8:
            alert_level = "CRITICAL"
        elif max_risk >= 0.6:
            alert_level = "HIGH"
        elif max_risk >= 0.4:
            alert_level = "MODERATE"
        else:
            alert_level = "LOW"

        return PredictionSummary(
            peak_flood_day=predictions[peak_flood_idx].day,
            peak_flood_risk=round(flood_risks[peak_flood_idx], 4),
            peak_heat_day=predictions[peak_heat_idx].day,
            peak_heat_risk=round(heat_risks[peak_heat_idx], 4),
            avg_flood_risk=round(avg_flood, 4),
            avg_heat_risk=round(avg_heat, 4),
            high_flood_days=sum(r > 0.6 for r in flood_risks),
            high_heat_days=sum(r > 0.6 for r in heat_risks),
            overall_alert_level=alert_level,
        )


# ─── Helpers ───────────────────────────────────────────────────────────────────


def _dominant_factor(features: Dict[str, Any], flood_risk: float, heat_risk: float) -> str:
    """Rule-based dominant risk factor label (no SHAP overhead)."""
    if flood_risk >= heat_risk:
        if features.get("rain_intensity_24h", 0) > 30:
            return "heavy_rainfall_24h"
        if features.get("cumulative_rain_7d", 0) > 80:
            return "high_cumulative_rain_7d"
        if features.get("drainage_capacity", 1) < 0.35:
            return "poor_drainage_capacity"
        if features.get("is_monsoon", 0):
            return "monsoon_season"
        return "elevated_flood_conditions"
    else:
        if features.get("consecutive_hot_days", 0) > 5:
            return "prolonged_heat_wave"
        if features.get("heat_index", 0) > 38:
            return "extreme_heat_index"
        if features.get("max_temp_24h", 0) > 43:
            return "extreme_temperature"
        return "elevated_heat_conditions"


async def _fetch_agent2(path: str) -> Dict:
    """Call Agent 2's API. Raises HTTPException on failure."""
    base_url = getattr(settings, "AGENT2_BASE_URL", "http://localhost:8000")
    url = f"{base_url}/api/v1/agent2{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent 2 returned {exc.response.status_code} for {path}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cannot reach Agent 2 at {url}: {exc}",
        ) from exc


def _zone_by_id(zone_id: str) -> Dict:
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")
    return zone


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/predict/{zone_id}", response_model=ZonePrediction)
async def predict_zone(zone_id: str):
    """
    30-day flood and heatstroke risk forecast for a zone.

    Flow:
      1. Ensure XGBoost models are loaded (trains if missing — ~30s first call)
      2. Fetch current feature vector from Agent 2
      3. Fetch GloFAS 30-day discharge forecast from Agent 2
      4. Project features day-by-day and run both models
      5. Return [{day, flood_risk, heatstroke_risk}, ...] for days 1-30

    Response includes:
      - Full 30-day predictions array
      - Summary with peak days, averages, alert level
      - The feature vector used for day-1 prediction
    """
    zone = _zone_by_id(zone_id)

    # Ensure models are loaded (lazy train on first call)
    bundle = await _ensure_models_loaded()
    predictor = RiskPredictor(bundle)

    # Fetch Agent 2 data in parallel
    features_data, flood_data = await asyncio.gather(
        _fetch_agent2(f"/features/{zone_id}"),
        _fetch_agent2(f"/flood-forecast/{zone_id}"),
        return_exceptions=True,
    )

    # Handle partial failures gracefully
    if isinstance(features_data, Exception):
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch features from Agent 2: {features_data}",
        )

    current_features: Dict = features_data["features"]
    flood_signals: List[Dict] = (
        flood_data.get("flood_signals", []) if not isinstance(flood_data, Exception) else []
    )
    if isinstance(flood_data, Exception):
        logger.warning("⚠ Could not fetch flood forecast — continuing without GloFAS: %s", flood_data)

    # Generate predictions
    predictions = predictor.predict_30_days(current_features, zone, flood_signals)
    summary = RiskPredictor.build_summary(predictions)

    logger.info(
        "🔮 %s → flood_peak=%.2f (day %d) | heat_peak=%.2f (day %d) | alert=%s",
        zone_id,
        summary.peak_flood_risk, summary.peak_flood_day,
        summary.peak_heat_risk, summary.peak_heat_day,
        summary.overall_alert_level,
    )

    return ZonePrediction(
        zone_id=zone_id,
        zone_name=zone["name"],
        predicted_at=datetime.utcnow().isoformat() + "Z",
        horizon_days=30,
        current_features=current_features,
        predictions=predictions,
        summary=summary,
    )


@router.get("/model/info", response_model=ModelInfo)
async def model_info():
    """
    XGBoost model metadata — training date, accuracy, features used.

    Returns model statistics from the last training run.
    If no model exists yet, triggers lazy training.
    """
    bundle = await _ensure_models_loaded()
    meta = bundle["meta"]

    return ModelInfo(
        model_version=meta["model_version"],
        model_type="XGBoostClassifier (dual: flood + heatstroke)",
        training_date=meta["training_date"],
        training_samples=meta["training_samples"],
        training_source=meta["training_source"],
        flood_model_auc=meta["flood_auc"],
        heat_model_auc=meta["heat_auc"],
        flood_model_accuracy=meta["flood_accuracy"],
        heat_model_accuracy=meta["heat_accuracy"],
        flood_features=meta["flood_features"],
        heat_features=meta["heat_features"],
        model_path=str(MODEL_PATH),
        is_loaded=True,
    )


@router.post("/retrain")
async def retrain_model(background_tasks: BackgroundTasks):
    """
    Force a full model retrain (deletes existing bundle, retrains from scratch).

    Runs in the background — returns immediately. Check /model/info after
    ~30 seconds to see the new training date and metrics.

    Use this after dropping new CSV files into backend/data/training/.
    """
    global _model_bundle

    def _retrain():
        global _model_bundle
        MODEL_PATH.unlink(missing_ok=True)
        _model_bundle = None  # clear cache
        _model_bundle = _train_and_save()

    background_tasks.add_task(_retrain)
    return {
        "status": "retraining_started",
        "message": "Model retrain running in background. Check /model/info in ~30s.",
        "training_data_dir": str(TRAINING_DATA_DIR),
    }


@router.post("/backtest", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest):
    """
    Evaluate model accuracy against known Pakistan historical crisis events.

    Method:
      - Generates synthetic feature vectors for each historical event using
        season-appropriate values (monsoon conditions for 2022 floods, etc.)
      - Runs both models on these feature vectors
      - Scores whether the model predicts HIGH risk during real crisis events
        and LOW risk during normal periods (directional accuracy)

    Known events hardcoded:
      - 2022 Pakistan super-floods (Aug-Sep, Sindh/Punjab)
      - 2015 Karachi heatwave (June)
      - 2023 Lahore heatwave (May)
      - 2020 Peshawar monsoon floods (July-Aug)
      - 2010 Khyber Pakhtunkhwa floods (July)
    """
    bundle = await _ensure_models_loaded()
    predictor = RiskPredictor(bundle)

    historical_events = [
        {
            "name": "2022 Super Floods — Karachi",
            "zone_id": "karachi-south",
            "event_type": "flood",
            "event_date": "2022-08-25",
            "known_severity": 0.90,
            "features": {"cumulative_rain_7d": 210, "cumulative_rain_14d": 380, "cumulative_rain_30d": 580,
                         "rain_intensity_24h": 65, "avg_humidity_24h": 88, "terrain_elevation": 10,
                         "drainage_capacity": 0.3, "is_monsoon": 1, "month_sin": 0.866, "month_cos": -0.5,
                         "ndwi_delta": 0.12, "max_temp_24h": 34, "heat_index": 29.9,
                         "consecutive_hot_days": 0, "population_density": 14000},
        },
        {
            "name": "2022 Super Floods — Multan",
            "zone_id": "multan-city",
            "event_type": "flood",
            "event_date": "2022-08-28",
            "known_severity": 0.85,
            "features": {"cumulative_rain_7d": 180, "cumulative_rain_14d": 310, "cumulative_rain_30d": 490,
                         "rain_intensity_24h": 55, "avg_humidity_24h": 82, "terrain_elevation": 122,
                         "drainage_capacity": 0.35, "is_monsoon": 1, "month_sin": 0.866, "month_cos": -0.5,
                         "ndwi_delta": 0.10, "max_temp_24h": 36, "heat_index": 29.5,
                         "consecutive_hot_days": 0, "population_density": 4500},
        },
        {
            "name": "2015 Karachi Heatwave",
            "zone_id": "karachi-south",
            "event_type": "heat",
            "event_date": "2015-06-22",
            "known_severity": 0.95,
            "features": {"cumulative_rain_7d": 2, "cumulative_rain_14d": 4, "cumulative_rain_30d": 8,
                         "rain_intensity_24h": 0, "avg_humidity_24h": 55, "terrain_elevation": 10,
                         "drainage_capacity": 0.3, "is_monsoon": 1, "month_sin": 1.0, "month_cos": 0.0,
                         "ndwi_delta": 0.0, "max_temp_24h": 47, "heat_index": 25.85,
                         "consecutive_hot_days": 9, "population_density": 14000},
        },
        {
            "name": "2023 Lahore Heatwave",
            "zone_id": "lahore-city",
            "event_type": "heat",
            "event_date": "2023-05-22",
            "known_severity": 0.80,
            "features": {"cumulative_rain_7d": 5, "cumulative_rain_14d": 9, "cumulative_rain_30d": 20,
                         "rain_intensity_24h": 1, "avg_humidity_24h": 42, "terrain_elevation": 217,
                         "drainage_capacity": 0.4, "is_monsoon": 0, "month_sin": 0.866, "month_cos": 0.5,
                         "ndwi_delta": 0.0, "max_temp_24h": 45, "heat_index": 18.9,
                         "consecutive_hot_days": 7, "population_density": 6300},
        },
        {
            "name": "2020 Peshawar Monsoon Floods",
            "zone_id": "peshawar-city",
            "event_type": "flood",
            "event_date": "2020-07-15",
            "known_severity": 0.75,
            "features": {"cumulative_rain_7d": 140, "cumulative_rain_14d": 250, "cumulative_rain_30d": 400,
                         "rain_intensity_24h": 48, "avg_humidity_24h": 78, "terrain_elevation": 331,
                         "drainage_capacity": 0.5, "is_monsoon": 1, "month_sin": 0.5, "month_cos": -0.866,
                         "ndwi_delta": 0.08, "max_temp_24h": 38, "heat_index": 29.6,
                         "consecutive_hot_days": 2, "population_density": 3200},
        },
        {
            "name": "Normal Conditions — Islamabad (Jan)",
            "zone_id": "islamabad-g10",
            "event_type": "none",
            "event_date": "2023-01-15",
            "known_severity": 0.05,
            "features": {"cumulative_rain_7d": 8, "cumulative_rain_14d": 15, "cumulative_rain_30d": 30,
                         "rain_intensity_24h": 2, "avg_humidity_24h": 45, "terrain_elevation": 507,
                         "drainage_capacity": 0.6, "is_monsoon": 0, "month_sin": 0.5, "month_cos": 0.866,
                         "ndwi_delta": 0.0, "max_temp_24h": 19, "heat_index": 8.55,
                         "consecutive_hot_days": 0, "population_density": 2850},
        },
    ]

    # Filter by request
    if request.zone_ids:
        historical_events = [e for e in historical_events if e["zone_id"] in request.zone_ids]
    if request.event_types:
        historical_events = [e for e in historical_events if e["event_type"] in request.event_types]

    results: List[BacktestEventResult] = []

    for event in historical_events:
        features = event["features"]
        event_type = event["event_type"]

        flood_vec = np.array([[features[f] for f in FLOOD_FEATURE_ORDER]])
        heat_vec = np.array([[features[f] for f in HEAT_FEATURE_ORDER]])

        flood_pred = float(bundle["flood"].predict_proba(flood_vec)[0][1])
        heat_pred = float(bundle["heat"].predict_proba(heat_vec)[0][1])

        if event_type == "flood":
            model_pred = flood_pred
            # Correct direction: model predicts high risk during known flood event
            correct = (model_pred > 0.5) == (event["known_severity"] > 0.5)
        elif event_type == "heat":
            model_pred = heat_pred
            correct = (model_pred > 0.5) == (event["known_severity"] > 0.5)
        else:
            # Normal period — model should predict LOW risk
            model_pred = max(flood_pred, heat_pred)
            correct = model_pred < 0.4

        results.append(BacktestEventResult(
            event_name=event["name"],
            zone_id=event["zone_id"],
            event_type=event_type,
            event_date=event["event_date"],
            known_severity=event["known_severity"],
            model_prediction=round(model_pred, 4),
            correct_direction=correct,
            notes=f"flood_pred={flood_pred:.3f}, heat_pred={heat_pred:.3f}",
        ))

    flood_events = [r for r in results if r.event_type == "flood"]
    heat_events = [r for r in results if r.event_type == "heat"]
    all_events = [r for r in results if r.event_type != "none"] + [r for r in results if r.event_type == "none"]

    def _dir_acc(evts: List[BacktestEventResult]) -> float:
        return round(sum(e.correct_direction for e in evts) / len(evts), 4) if evts else 0.0

    logger.info("📊 Backtest: %d events | overall=%.1f%%",
                len(results), _dir_acc(results) * 100)

    return BacktestResponse(
        run_at=datetime.utcnow().isoformat() + "Z",
        events_evaluated=len(results),
        flood_direction_accuracy=_dir_acc(flood_events),
        heat_direction_accuracy=_dir_acc(heat_events),
        overall_direction_accuracy=_dir_acc(results),
        events=results,
    )
