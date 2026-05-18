"""
CIRO — Agent 2: Data & API Collector
=====================================
Fetches real-time weather, traffic, and social signals.
Normalizes into unified signal format.
Stores in 30-day rolling buffer.
Exposes endpoints for Agent 3 (predictor) to consume.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import logging
import asyncio

from services.weather_service import WeatherService
from services.traffic_service import TrafficService
from services.social_service import SocialSignalService
from services.signal_store import SignalStore
from config.settings import settings

logger = logging.getLogger("ciro.agent2")
router = APIRouter()

# Initialize services
weather_service = WeatherService()
traffic_service = TrafficService()
social_service = SocialSignalService()
signal_store = SignalStore()


# ─── Schemas ───────────────────────────────────────────────────────────────────

class Signal(BaseModel):
    """Unified signal format — every data point normalized to this."""
    signal_id: str
    signal_type: str  # rainfall, temperature, humidity, wind, traffic, social, official
    zone_id: str
    zone_name: str
    lat: float
    lng: float
    value: float  # Primary value (mm for rain, °C for temp, etc.)
    severity: int  # 1-10 scale
    confidence: float  # 0.0 - 1.0
    source: str  # openweathermap, google_maps, social, ndma
    timestamp: str
    metadata: Dict = {}


class ZoneSignalSummary(BaseModel):
    """Aggregated signals for a zone."""
    zone_id: str
    zone_name: str
    lat: float
    lng: float
    total_signals: int
    max_severity: int
    avg_severity: float
    signals: List[Signal]
    risk_indicators: Dict


class FetchResult(BaseModel):
    """Result of a fetch operation."""
    success: bool
    zones_processed: int
    signals_collected: int
    timestamp: str
    errors: List[str] = []


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def agent_status():
    """Agent 2 health and configuration."""
    return {
        "agent": "Agent 2 — Data & API Collector",
        "status": "active",
        "config": {
            "fetch_interval_min": settings.FETCH_INTERVAL_MINUTES,
            "buffer_days": settings.SIGNAL_BUFFER_DAYS,
            "monitored_zones": len(settings.ZONES),
            "weather_api": "configured" if settings.OPENWEATHER_API_KEY else "missing",
            "maps_api": "configured" if settings.GOOGLE_MAPS_API_KEY else "missing",
        },
        "zones": [z["name"] for z in settings.ZONES],
    }


@router.post("/fetch", response_model=FetchResult)
async def fetch_all_signals(background_tasks: BackgroundTasks):
    """
    Trigger a full fetch cycle — pulls data from all APIs for all zones.
    This is the main entry point Agent 4 (orchestrator) calls.
    """
    logger.info("📡 Agent 2: Starting full signal fetch cycle...")
    
    all_signals = []
    errors = []

    for zone in settings.ZONES:
        try:
            # Fetch weather data
            weather_signals = await weather_service.fetch_for_zone(zone)
            all_signals.extend(weather_signals)

            # Fetch traffic data
            traffic_signals = await traffic_service.fetch_for_zone(zone)
            all_signals.extend(traffic_signals)

            # Fetch social signals (simulated)
            social_signals = await social_service.fetch_for_zone(zone)
            all_signals.extend(social_signals)

            logger.info(f"  ✓ {zone['name']}: {len(weather_signals) + len(traffic_signals) + len(social_signals)} signals")

        except Exception as e:
            error_msg = f"Error fetching {zone['name']}: {str(e)}"
            logger.error(f"  ✗ {error_msg}")
            errors.append(error_msg)

    # Store signals in buffer
    stored_count = await signal_store.store_signals(all_signals)
    
    logger.info(f"📡 Agent 2: Fetch complete. {stored_count} signals stored across {len(settings.ZONES)} zones.")

    return FetchResult(
        success=len(errors) == 0,
        zones_processed=len(settings.ZONES),
        signals_collected=stored_count,
        timestamp=datetime.utcnow().isoformat(),
        errors=errors,
    )


@router.get("/signals/{zone_id}", response_model=ZoneSignalSummary)
async def get_zone_signals(zone_id: str, hours: int = 24):
    """
    Get latest signals for a specific zone.
    Used by Agent 3 (predictor) to build feature vectors.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    signals = await signal_store.get_signals(zone_id, hours=hours)
    
    if not signals:
        return ZoneSignalSummary(
            zone_id=zone_id, zone_name=zone["name"],
            lat=zone["lat"], lng=zone["lng"],
            total_signals=0, max_severity=0, avg_severity=0.0,
            signals=[], risk_indicators={},
        )

    severities = [s.severity for s in signals]
    
    return ZoneSignalSummary(
        zone_id=zone_id,
        zone_name=zone["name"],
        lat=zone["lat"],
        lng=zone["lng"],
        total_signals=len(signals),
        max_severity=max(severities),
        avg_severity=sum(severities) / len(severities),
        signals=signals,
        risk_indicators=_compute_risk_indicators(signals, zone),
    )


@router.get("/signals/{zone_id}/history")
async def get_zone_history(zone_id: str, days: int = 30):
    """
    Get full 30-day signal history for a zone.
    Used by Agent 3 to compute rolling features (cumulative_rain_7d, etc.)
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    signals = await signal_store.get_signals(zone_id, hours=days * 24)
    
    # Aggregate by day for the ML model
    daily_aggregates = _aggregate_daily(signals, days)
    
    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "days_requested": days,
        "days_with_data": len(daily_aggregates),
        "daily_data": daily_aggregates,
        "static_features": {
            "elevation_m": zone["elevation_m"],
            "drainage_capacity": zone["drainage_capacity"],
            "population_density": zone["population_density"],
            "province": zone["province"],
        }
    }


@router.get("/features/{zone_id}")
async def get_model_features(zone_id: str):
    """
    Pre-computed feature vector for Agent 3's ML model.
    Returns the exact features XGBoost expects.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    signals = await signal_store.get_signals(zone_id, hours=30 * 24)
    
    features = _compute_ml_features(signals, zone)
    
    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "computed_at": datetime.utcnow().isoformat(),
        "features": features,
        "feature_names": list(features.keys()),
    }


@router.get("/zones")
async def list_zones():
    """List all monitored zones with their current risk summary."""
    zone_summaries = []
    for zone in settings.ZONES:
        signals = await signal_store.get_signals(zone["id"], hours=24)
        severities = [s.severity for s in signals] if signals else [0]
        zone_summaries.append({
            "zone_id": zone["id"],
            "name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "province": zone["province"],
            "signal_count_24h": len(signals),
            "max_severity_24h": max(severities),
            "avg_severity_24h": round(sum(severities) / len(severities), 2),
        })
    return {"zones": zone_summaries, "total": len(zone_summaries)}


# ─── Internal Helpers ──────────────────────────────────────────────────────────

def _compute_risk_indicators(signals: List[Signal], zone: Dict) -> Dict:
    """Compute risk indicators from current signals."""
    rain_signals = [s for s in signals if s.signal_type == "rainfall"]
    temp_signals = [s for s in signals if s.signal_type == "temperature"]
    
    total_rain = sum(s.value for s in rain_signals) if rain_signals else 0
    max_temp = max((s.value for s in temp_signals), default=0)
    
    # Simple flood risk heuristic
    flood_risk = min(1.0, (total_rain / 100) * (1 - zone["drainage_capacity"]))
    
    # Heatstroke risk heuristic
    heat_risk = min(1.0, max(0, (max_temp - 35) / 15)) if max_temp > 35 else 0
    
    return {
        "total_rainfall_mm": round(total_rain, 1),
        "max_temperature_c": round(max_temp, 1),
        "flood_risk_heuristic": round(flood_risk, 3),
        "heatstroke_risk_heuristic": round(heat_risk, 3),
        "drainage_capacity": zone["drainage_capacity"],
    }


def _aggregate_daily(signals: List[Signal], days: int) -> List[Dict]:
    """Aggregate signals into daily summaries for ML model."""
    daily = {}
    
    for signal in signals:
        try:
            dt = datetime.fromisoformat(signal.timestamp.replace("Z", "+00:00"))
            day_key = dt.strftime("%Y-%m-%d")
        except:
            continue
            
        if day_key not in daily:
            daily[day_key] = {
                "date": day_key,
                "total_rainfall_mm": 0,
                "max_temp_c": -999,
                "min_temp_c": 999,
                "avg_humidity": [],
                "max_wind_kph": 0,
                "traffic_congestion": 0,
                "social_alert_count": 0,
                "max_severity": 0,
            }
        
        d = daily[day_key]
        if signal.signal_type == "rainfall":
            d["total_rainfall_mm"] += signal.value
        elif signal.signal_type == "temperature":
            d["max_temp_c"] = max(d["max_temp_c"], signal.value)
            d["min_temp_c"] = min(d["min_temp_c"], signal.value)
        elif signal.signal_type == "humidity":
            d["avg_humidity"].append(signal.value)
        elif signal.signal_type == "wind":
            d["max_wind_kph"] = max(d["max_wind_kph"], signal.value)
        elif signal.signal_type == "traffic":
            d["traffic_congestion"] = max(d["traffic_congestion"], signal.value)
        elif signal.signal_type == "social":
            d["social_alert_count"] += 1
        
        d["max_severity"] = max(d["max_severity"], signal.severity)
    
    # Finalize averages
    for d in daily.values():
        d["avg_humidity"] = round(sum(d["avg_humidity"]) / len(d["avg_humidity"]), 1) if d["avg_humidity"] else 0
        if d["max_temp_c"] == -999: d["max_temp_c"] = 0
        if d["min_temp_c"] == 999: d["min_temp_c"] = 0
    
    # Sort by date and return
    return sorted(daily.values(), key=lambda x: x["date"], reverse=True)[:days]


def _compute_ml_features(signals: List[Signal], zone: Dict) -> Dict:
    """
    Compute the exact feature vector Agent 3's XGBoost model expects.
    Matches the feature table from our project doc.
    """
    now = datetime.utcnow()
    
    rain_signals = [s for s in signals if s.signal_type == "rainfall"]
    temp_signals = [s for s in signals if s.signal_type == "temperature"]
    humidity_signals = [s for s in signals if s.signal_type == "humidity"]
    
    # Time-windowed aggregates
    def rain_in_window(hours):
        cutoff = now - timedelta(hours=hours)
        return sum(s.value for s in rain_signals
                   if datetime.fromisoformat(s.timestamp.replace("Z", "+00:00")).replace(tzinfo=None) > cutoff)
    
    def max_temp_in_window(hours):
        cutoff = now - timedelta(hours=hours)
        temps = [s.value for s in temp_signals
                 if datetime.fromisoformat(s.timestamp.replace("Z", "+00:00")).replace(tzinfo=None) > cutoff]
        return max(temps) if temps else 0
    
    def avg_humidity_in_window(hours):
        cutoff = now - timedelta(hours=hours)
        hums = [s.value for s in humidity_signals
                if datetime.fromisoformat(s.timestamp.replace("Z", "+00:00")).replace(tzinfo=None) > cutoff]
        return sum(hums) / len(hums) if hums else 0
    
    # Consecutive hot days (> 40°C)
    consecutive_hot = 0
    for day_offset in range(30):
        day_start = now - timedelta(days=day_offset + 1)
        day_end = now - timedelta(days=day_offset)
        day_temps = [s.value for s in temp_signals
                     if day_start < datetime.fromisoformat(s.timestamp.replace("Z", "+00:00")).replace(tzinfo=None) < day_end]
        if day_temps and max(day_temps) > 40:
            consecutive_hot += 1
        else:
            break
    
    max_temp = max_temp_in_window(24)
    avg_hum = avg_humidity_in_window(24)
    
    return {
        # Rainfall features
        "cumulative_rain_7d": round(rain_in_window(7 * 24), 2),
        "cumulative_rain_14d": round(rain_in_window(14 * 24), 2),
        "cumulative_rain_30d": round(rain_in_window(30 * 24), 2),
        "rain_intensity_24h": round(rain_in_window(24), 2),
        
        # Temperature features
        "max_temp_24h": round(max_temp, 1),
        "heat_index": round(max_temp * (avg_hum / 100) if max_temp > 0 else 0, 2),
        "consecutive_hot_days": consecutive_hot,
        
        # Humidity
        "avg_humidity_24h": round(avg_hum, 1),
        
        # Static/zone features
        "terrain_elevation": zone["elevation_m"],
        "drainage_capacity": zone["drainage_capacity"],
        "population_density": zone["population_density"],
        
        # Seasonal
        "month": now.month,
        "is_monsoon": 1 if now.month in [6, 7, 8, 9] else 0,
        "month_sin": round(__import__("math").sin(2 * 3.14159 * now.month / 12), 4),
        "month_cos": round(__import__("math").cos(2 * 3.14159 * now.month / 12), 4),
        
        # Placeholder for Agent 1 (imagery)
        "ndwi_delta": 0.0,  # Will be filled by Agent 1 when ready
    }
