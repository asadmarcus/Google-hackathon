"""
CIRO - Prophet Weather Forecaster
====================================
Trained on 22 YEARS of daily Pakistan climate data (2000-2021) from Google Earth Engine.
6 provinces × 2 variables (Temperature, Rainfall) = 12 Prophet models.

Architecture:
  Prophet (time series) → forecasts WHAT the weather will be (temp, rain for days 17-30)
  XGBoost (classifier)  → predicts IF that weather causes a flood/heatstroke

Why Prophet:
  - Purpose-built for time series with strong annual seasonality (weather patterns)
  - Decomposes signal into: trend (climate change) + yearly seasonality + residual
  - Provides uncertainty intervals (yhat_lower, yhat_upper) natively
  - Handles missing data gracefully (satellite data has gaps)
  - Fast training on ~8000 daily samples (~2-3 seconds per model)

Data source: Google Earth Engine (MODIS LST + CHIRPS/GPM precipitation)
  - Temperature: MODIS Land Surface Temperature (daily, 1km resolution)
  - Precipitation: CHIRPS/GPM merged satellite + gauge product (daily)
  - 6 provinces: Punjab, Sindh, Federal, KPK, Balochistan, Gilgit-Baltistan
  - Date range: Feb 2000 — Dec 2021 (~7,900 days per province)

Usage:
  forecaster = await get_weather_forecaster()
  forecast = forecaster.forecast("Punjab", recent_temps, recent_rains, start_date, days=14)
  # Returns: [{"day": 1, "date": "2026-06-04", "temp": 44.2, "rain_mm": 2.1, 
  #            "temp_lower": 40.8, "temp_upper": 47.5, "rain_upper": 8.4}, ...]
"""

import logging
import os
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from prophet import Prophet

logger = logging.getLogger(__name__)

# Province directories matching GEE training data structure
PROVINCE_DIRS = ["Punjab", "Sindh", "Federal", "Kpk", "Balochistan", "Gilgit"]


class WeatherForecaster:
    """
    Prophet-based weather forecaster trained on 22 years of daily Pakistan data.
    
    Provides 30-day temperature and rainfall forecasts per province using
    Facebook Prophet's additive time series decomposition:
      y(t) = trend(t) + seasonality(t) + residual(t)
    
    The yearly seasonality captures Pakistan's climate cycles:
      - Winter dry cold (Dec-Feb)
      - Pre-monsoon heat buildup (Mar-May)  
      - Monsoon onset and peak (Jun-Sep)
      - Post-monsoon retreat (Oct-Nov)
    """
    
    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or str(Path(__file__).parent.parent / "data" / "training")
        self.models_dir = str(Path(__file__).parent.parent / "models" / "prophet")
        self.temp_models: Dict[str, Prophet] = {}
        self.rain_models: Dict[str, Prophet] = {}
        self._loaded = False
    
    def load_or_train(self) -> bool:
        """Load pre-trained Prophet models or train from scratch on GEE data."""
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Try loading serialized models first (fast: ~1s)
        if self._try_load_models():
            logger.info("✅ Prophet weather forecaster: loaded pre-trained models (%d provinces)", 
                       len(self.temp_models))
            self._loaded = True
            return True
        
        # Train from scratch (~15-20s for all 12 models)
        logger.info("🔧 Prophet weather forecaster: training on 22-year daily GEE data...")
        success = self._train_all_provinces()
        if success:
            self._save_models()
            self._loaded = True
            logger.info("✅ Prophet weather forecaster: all models trained and cached")
        return success
    
    def forecast(
        self,
        province: str,
        recent_temps: List[float],
        recent_rains: List[float],
        start_date: datetime,
        days: int = 14,
    ) -> List[Dict]:
        """
        Generate ML-based weather forecast for a province.
        
        Uses Prophet's trained seasonal + trend model to predict future daily
        temperature and rainfall. The recent_temps/rains are used to condition
        the forecast (Prophet uses the full training history internally, but
        we use recent data to detect if current conditions deviate from normal).
        
        Args:
            province: Province name (Punjab, Sindh, Federal, Kpk, Balochistan, Gilgit)
            recent_temps: Last 16+ days of daily max temperatures (from Open-Meteo)
            recent_rains: Last 16+ days of daily rainfall in mm (from Open-Meteo)
            start_date: First forecast day (typically day 17 of the 30-day window)
            days: Number of days to forecast (default 14, covering days 17-30)
            
        Returns:
            List of dicts with ML-predicted weather:
            [{"day": 1, "date": "2026-06-04", "temp": 44.2, "rain_mm": 2.1,
              "temp_lower": 40.8, "temp_upper": 47.5, "rain_upper": 8.4}, ...]
        """
        if not self._loaded:
            logger.warning("Prophet forecaster not loaded — returning empty forecast")
            return []
        
        if province not in self.temp_models:
            logger.warning(f"No Prophet model for '{province}' — falling back to Punjab")
            province = "Punjab"
        
        temp_model = self.temp_models[province]
        rain_model = self.rain_models[province]
        
        # Generate future dates for prediction
        future_dates = pd.DataFrame({
            'ds': [start_date + timedelta(days=d) for d in range(days)]
        })
        
        # Prophet predict (uses trained trend + seasonality decomposition)
        temp_forecast = temp_model.predict(future_dates)
        rain_forecast = rain_model.predict(future_dates)
        
        # Apply conditioning: if recent temps deviate from Prophet's expected value,
        # shift the forecast to account for current anomaly
        if recent_temps and len(recent_temps) >= 7:
            # Compare last 7 days of real data vs what Prophet would have predicted
            recent_dates = pd.DataFrame({
                'ds': [start_date - timedelta(days=d) for d in range(7, 0, -1)]
            })
            recent_pred = temp_model.predict(recent_dates)
            predicted_recent = recent_pred['yhat'].values
            actual_recent = np.array(recent_temps[-7:])
            
            # Anomaly: how much hotter/cooler is it than Prophet expected?
            anomaly = np.mean(actual_recent - predicted_recent)
            
            # Decay the anomaly over the forecast horizon (persistence decays)
            anomaly_decay = np.array([anomaly * np.exp(-0.1 * d) for d in range(days)])
            temp_forecast['yhat'] += anomaly_decay
            temp_forecast['yhat_lower'] += anomaly_decay
            temp_forecast['yhat_upper'] += anomaly_decay
        
        # Same for rainfall conditioning
        if recent_rains and len(recent_rains) >= 7:
            recent_dates = pd.DataFrame({
                'ds': [start_date - timedelta(days=d) for d in range(7, 0, -1)]
            })
            recent_pred = rain_model.predict(recent_dates)
            predicted_recent = recent_pred['yhat'].values
            actual_recent = np.array(recent_rains[-7:])
            
            rain_anomaly = np.mean(actual_recent - predicted_recent)
            rain_decay = np.array([rain_anomaly * np.exp(-0.15 * d) for d in range(days)])
            rain_forecast['yhat'] += rain_decay
            rain_forecast['yhat_upper'] += rain_decay
        
        # Build output
        forecasts = []
        for d in range(days):
            pred_temp = float(temp_forecast.iloc[d]['yhat'])
            pred_temp = np.clip(pred_temp, -12, 52)  # Physical bounds
            
            pred_rain = max(0.0, float(rain_forecast.iloc[d]['yhat']))
            
            temp_lower = float(temp_forecast.iloc[d]['yhat_lower'])
            temp_upper = float(temp_forecast.iloc[d]['yhat_upper'])
            rain_upper = max(0.0, float(rain_forecast.iloc[d]['yhat_upper']))
            
            forecasts.append({
                "day": d + 1,
                "date": (start_date + timedelta(days=d)).strftime("%Y-%m-%d"),
                "temp": round(pred_temp, 1),
                "rain_mm": round(pred_rain, 1),
                "temp_lower": round(temp_lower, 1),
                "temp_upper": round(temp_upper, 1),
                "rain_upper": round(rain_upper, 1),
            })
        
        return forecasts
    
    # ─── Training Pipeline ──────────────────────────────────────────────────────
    
    def _train_all_provinces(self) -> bool:
        """Train Prophet models for all 6 provinces on GEE daily data."""
        success_count = 0
        
        for province in PROVINCE_DIRS:
            logger.info(f"  Training Prophet for {province}...")
            df = self._load_province_data(province)
            
            if df is None or len(df) < 365:
                logger.warning(f"  ⚠ Insufficient data for {province}, skipping")
                continue
            
            try:
                # ── Temperature Model ──
                temp_df = df[['ds', 'temp']].rename(columns={'temp': 'y'}).dropna()
                
                temp_model = Prophet(
                    yearly_seasonality=True,      # Annual weather cycle (main signal)
                    weekly_seasonality=False,      # Weather doesn't care about weekday
                    daily_seasonality=False,       # We have daily granularity already
                    changepoint_prior_scale=0.05,  # Detect climate trends slowly
                    seasonality_prior_scale=10.0,  # Strong seasonality (weather is very seasonal)
                    interval_width=0.80,           # 80% prediction interval
                )
                # Add sub-annual seasonality (captures monsoon double-peak)
                temp_model.add_seasonality(name='semi_annual', period=182.625, fourier_order=5)
                
                temp_model.fit(temp_df)
                self.temp_models[province] = temp_model
                
                # ── Rainfall Model ──
                rain_df = df[['ds', 'rain']].rename(columns={'rain': 'y'}).dropna()
                
                rain_model = Prophet(
                    yearly_seasonality=True,
                    weekly_seasonality=False,
                    daily_seasonality=False,
                    changepoint_prior_scale=0.01,  # Rainfall trend changes slowly
                    seasonality_prior_scale=15.0,  # Very strong monsoon seasonality
                    interval_width=0.80,
                )
                # Monsoon sub-seasonality
                rain_model.add_seasonality(name='semi_annual', period=182.625, fourier_order=8)
                
                rain_model.fit(rain_df)
                self.rain_models[province] = rain_model
                
                # Validation: MAE on last year
                last_year = temp_df[temp_df['ds'] >= temp_df['ds'].max() - pd.Timedelta(days=365)]
                if len(last_year) > 30:
                    pred = temp_model.predict(last_year[['ds']])
                    temp_mae = np.mean(np.abs(pred['yhat'].values - last_year['y'].values))
                    
                    last_year_rain = rain_df[rain_df['ds'] >= rain_df['ds'].max() - pd.Timedelta(days=365)]
                    pred_rain = rain_model.predict(last_year_rain[['ds']])
                    rain_mae = np.mean(np.abs(pred_rain['yhat'].values - last_year_rain['y'].values))
                    
                    logger.info(f"  ✅ {province}: Temp MAE={temp_mae:.2f}°C, Rain MAE={rain_mae:.2f}mm/day "
                              f"({len(temp_df)} samples)")
                else:
                    logger.info(f"  ✅ {province}: trained ({len(temp_df)} samples)")
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"  ❌ {province} training failed: {e}")
                continue
        
        return success_count >= 4  # At least 4/6 provinces must succeed
    
    def _load_province_data(self, province: str) -> Optional[pd.DataFrame]:
        """
        Load and prepare daily climate data for a province from GEE CSVs.
        
        Combines Temp.csv + temp1.csv (MODIS LST) and Pre.csv + pre1.csv (CHIRPS)
        into a single time-indexed DataFrame.
        """
        prov_dir = os.path.join(self.data_dir, province)
        if not os.path.isdir(prov_dir):
            return None
        
        # Load temperature CSVs
        temp_dfs = []
        for fname in sorted(os.listdir(prov_dir)):
            if ('temp' in fname.lower()) and fname.endswith('.csv'):
                try:
                    df = pd.read_csv(os.path.join(prov_dir, fname))
                    if 'system:time_start' in df.columns and 'LST_Day_1km' in df.columns:
                        df['ds'] = pd.to_datetime(df['system:time_start'], format='mixed')
                        temp_dfs.append(df[['ds', 'LST_Day_1km']].rename(columns={'LST_Day_1km': 'temp'}))
                except Exception:
                    continue
        
        # Load precipitation CSVs
        rain_dfs = []
        for fname in sorted(os.listdir(prov_dir)):
            if ('pre' in fname.lower()) and fname.endswith('.csv'):
                try:
                    df = pd.read_csv(os.path.join(prov_dir, fname))
                    if 'system:time_start' in df.columns and 'precipitation' in df.columns:
                        df['ds'] = pd.to_datetime(df['system:time_start'], format='mixed')
                        rain_dfs.append(df[['ds', 'precipitation']].rename(columns={'precipitation': 'rain'}))
                except Exception:
                    continue
        
        if not temp_dfs or not rain_dfs:
            return None
        
        # Combine duplicates and merge
        temp_all = pd.concat(temp_dfs).dropna().sort_values('ds').drop_duplicates('ds').reset_index(drop=True)
        rain_all = pd.concat(rain_dfs).dropna().sort_values('ds').drop_duplicates('ds').reset_index(drop=True)
        
        df = temp_all.merge(rain_all, on='ds', how='inner').reset_index(drop=True)
        
        # GEE CHIRPS precipitation is in meters/day → convert to mm/day
        if df['rain'].max() < 5 and len(df) > 100:
            df['rain'] = df['rain'] * 1000
        
        logger.info(f"    {province}: {len(df)} daily samples "
                   f"({df['ds'].min().date()} to {df['ds'].max().date()}), "
                   f"temp {df['temp'].min():.0f}-{df['temp'].max():.0f}°C, "
                   f"rain 0-{df['rain'].max():.1f}mm/day")
        
        return df
    
    # ─── Model Persistence ──────────────────────────────────────────────────────
    
    def _save_models(self):
        """Serialize trained Prophet models to disk for fast reload."""
        for province in self.temp_models:
            temp_path = os.path.join(self.models_dir, f"{province}_temp_prophet.pkl")
            rain_path = os.path.join(self.models_dir, f"{province}_rain_prophet.pkl")
            
            with open(temp_path, 'wb') as f:
                pickle.dump(self.temp_models[province], f)
            with open(rain_path, 'wb') as f:
                pickle.dump(self.rain_models[province], f)
        
        logger.info(f"  Prophet models saved to {self.models_dir}/")
    
    def _try_load_models(self) -> bool:
        """Try to load pre-trained Prophet models from disk."""
        if not os.path.isdir(self.models_dir):
            return False
        
        loaded = 0
        for province in PROVINCE_DIRS:
            temp_path = os.path.join(self.models_dir, f"{province}_temp_prophet.pkl")
            rain_path = os.path.join(self.models_dir, f"{province}_rain_prophet.pkl")
            
            if os.path.exists(temp_path) and os.path.exists(rain_path):
                try:
                    with open(temp_path, 'rb') as f:
                        self.temp_models[province] = pickle.load(f)
                    with open(rain_path, 'rb') as f:
                        self.rain_models[province] = pickle.load(f)
                    loaded += 1
                except Exception as e:
                    logger.warning(f"Failed to load {province} Prophet models: {e}")
        
        return loaded >= 4


# ─── Module Singleton ───────────────────────────────────────────────────────────

_forecaster: Optional[WeatherForecaster] = None


async def get_weather_forecaster() -> WeatherForecaster:
    """Get or initialize the Prophet weather forecaster singleton."""
    global _forecaster
    if _forecaster is None:
        _forecaster = WeatherForecaster()
        _forecaster.load_or_train()
    return _forecaster
