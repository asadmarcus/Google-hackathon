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
from enum import Enum
from datetime import datetime, timedelta
import logging
import math
import asyncio

from services.weather_service import WeatherService
from services.traffic_service import TrafficService
from services.social_service import SocialSignalService
from services.openmeteo_service import OpenMeteoService
from services.ndma_service import NDMAAlertService
from services.signal_store import SignalStore
from services.websocket_manager import ws_manager
from config.settings import settings

logger = logging.getLogger("ciro.agent2")
router = APIRouter()

# Initialize services
weather_service = WeatherService()
traffic_service = TrafficService()
openmeteo_service = OpenMeteoService()
ndma_service = NDMAAlertService()
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
    signals: List[Dict]
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
        "data_sources": {
            "real": [
                "open_meteo (weather + 7-day forecast — ECMWF model, no key needed)",
                "open_meteo_flood (GloFAS river discharge — 30-day forecast, no key needed)",
                "openweathermap (real-time weather — requires API key)",
                "google_maps (traffic congestion — requires API key)",
            ],
            "simulated": [
                "social_media (Urdu+English crisis keywords — no real feed connected)",
                "ndma_alerts (Pakistan disaster authority — no real API available)",
            ],
        },
    }


@router.post("/backfill/{zone_id}")
async def backfill_historical(zone_id: str, days: int = 30):
    """
    Backfill 30-day historical data from Open-Meteo (FREE).
    Call this once per zone to populate the buffer with REAL weather data.
    No API key needed — Open-Meteo is completely free.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    logger.info(f"📥 Backfilling {days}-day history for {zone['name']}...")
    
    # Fetch real historical data
    historical_signals = await openmeteo_service.fetch_historical(zone, days_back=days)
    
    # Store in buffer
    stored = await signal_store.store_signals(historical_signals)
    
    logger.info(f"📥 Backfill complete: {stored} historical signals stored for {zone['name']}")
    
    return {
        "success": True,
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "days_backfilled": days,
        "signals_stored": stored,
        "source": "open_meteo_historical (FREE, real data)",
    }


@router.get("/flood-forecast/{zone_id}")
async def get_flood_forecast(zone_id: str):
    """
    Get 30-day river discharge flood forecast from GloFAS via Open-Meteo.
    Shows days where river discharge is above normal — direct flood risk.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    flood_signals = await openmeteo_service.fetch_flood_forecast(zone)
    
    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "forecast_days": 30,
        "elevated_days": len(flood_signals),
        "source": "GloFAS via Open-Meteo (FREE)",
        "flood_signals": flood_signals,
    }


@router.post("/fetch", response_model=FetchResult)
async def fetch_all_signals(background_tasks: BackgroundTasks):
    """
    Manually trigger a full fetch cycle.
    
    Pulls data from all 6 API sources for all monitored zones, stores in SQLite,
    and broadcasts to WebSocket clients. Normally runs automatically every 15 min
    via the scheduler — use this for manual/on-demand fetching.
    
    Called by: Agent 4 (orchestrator), manual testing, Flutter app refresh button.
    """
    result = await run_fetch_cycle()

    return FetchResult(
        success=result["success"],
        zones_processed=len(settings.ZONES),
        signals_collected=result["signals_collected"],
        timestamp=datetime.utcnow().isoformat(),
        errors=result["errors"],
    )


@router.get("/signals/{zone_id}")
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

    severities = [s["severity"] for s in signals]
    
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
    
    # Inject Agent 1 satellite data (async call, can't be inside sync helper)
    features["ndwi_delta"] = await _get_ndwi_delta(zone_id)
    
    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "computed_at": datetime.utcnow().isoformat(),
        "features": features,
        "feature_names": list(features.keys()),
    }




@router.get("/forecast/{zone_id}")
async def get_weather_forecast(zone_id: str):
    """
    Get 7-day weather forecast from Open-Meteo (REAL meteorological prediction).
    
    This is what Agent 3 uses for accurate Days 1-7 predictions.
    Open-Meteo uses ECMWF/GFS models — same quality as national weather services.
    
    Returns actual predicted temperatures, rainfall, humidity per day.
    NOT monthly averages — real weather model output.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone \'{zone_id}\' not found")

    forecast = await openmeteo_service.fetch_16day_daily_forecast(zone)
    
    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "source": "Open-Meteo ECMWF/GFS (real weather model prediction)",
        "forecast_days": len(forecast),
        "days": forecast,
    }

@router.get("/zones")
async def list_zones():
    """List all monitored zones with their current risk summary."""
    zone_summaries = []
    for zone in settings.ZONES:
        signals = await signal_store.get_signals(zone["id"], hours=24)
        severities = [s["severity"] for s in signals] if signals else [0]
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




async def _get_ndwi_delta(zone_id: str) -> float:
    """
    Get the latest ndwi_delta from Agent 1's satellite signals.
    Returns 0.0 if no satellite analysis has been run yet.
    
    This is the key integration point: Agent 1 (satellite) → Agent 2 (features) → Agent 3 (prediction)
    """
    try:
        # Get recent signals from the store, filter to satellite source
        signals = await signal_store.get_signals(zone_id, hours=168)  # 7 days
        satellite_signals = [
            s for s in signals
            if s.get("source") == "satellite_agent1" and s.get("signal_type") == "satellite_ndwi"
        ]
        if satellite_signals:
            # Return the most recent ndwi_delta value
            latest = max(satellite_signals, key=lambda s: s.get("timestamp", ""))
            return latest.get("value", 0.0)
    except Exception as e:
        logger.warning(f"Could not fetch Agent 1 ndwi_delta for {zone_id}: {e}")
    return 0.0


def _compute_risk_indicators(signals: List[Dict], zone: Dict) -> Dict:
    """Compute risk indicators from current signals."""
    rain_signals = [s for s in signals if s["signal_type"] == "rainfall"]
    temp_signals = [s for s in signals if s["signal_type"] == "temperature"]
    
    total_rain = sum(s["value"] for s in rain_signals) if rain_signals else 0
    max_temp = max((s["value"] for s in temp_signals), default=0)
    
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


def _aggregate_daily(signals: List[Dict], days: int) -> List[Dict]:
    """Aggregate signals into daily summaries for ML model."""
    daily = {}
    
    for signal in signals:
        try:
            dt = datetime.fromisoformat(signal["timestamp"].replace("Z", "+00:00"))
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
        if signal["signal_type"] == "rainfall":
            d["total_rainfall_mm"] += signal["value"]
        elif signal["signal_type"] == "temperature":
            d["max_temp_c"] = max(d["max_temp_c"], signal["value"])
            d["min_temp_c"] = min(d["min_temp_c"], signal["value"])
        elif signal["signal_type"] == "humidity":
            d["avg_humidity"].append(signal["value"])
        elif signal["signal_type"] == "wind":
            d["max_wind_kph"] = max(d["max_wind_kph"], signal["value"])
        elif signal["signal_type"] == "traffic":
            d["traffic_congestion"] = max(d["traffic_congestion"], signal["value"])
        elif signal["signal_type"] == "social":
            d["social_alert_count"] += 1
        
        d["max_severity"] = max(d["max_severity"], signal["severity"])
    
    # Finalize averages
    for d in daily.values():
        d["avg_humidity"] = round(sum(d["avg_humidity"]) / len(d["avg_humidity"]), 1) if d["avg_humidity"] else 0
        if d["max_temp_c"] == -999: d["max_temp_c"] = 0
        if d["min_temp_c"] == 999: d["min_temp_c"] = 0
    
    # Sort by date and return
    return sorted(daily.values(), key=lambda x: x["date"], reverse=True)[:days]


def _compute_ml_features(signals: List[Dict], zone: Dict) -> Dict:
    """
    Compute the exact feature vector Agent 3's XGBoost model expects.
    Matches the feature table from our project doc. Uses HOURLY deduplication
    to prevent inflated values from frequent polling (scheduler runs every 15 min).
    """
    now = datetime.utcnow()
    
    rain_signals = [s for s in signals if s["signal_type"] == "rainfall"]
    temp_signals = [s for s in signals if s["signal_type"] == "temperature"]
    humidity_signals = [s for s in signals if s["signal_type"] == "humidity"]
    
    # Time-windowed aggregates
    def rain_in_window(hours: int) -> float:
        """
        Sum rainfall in a time window with HOURLY deduplication.
        The scheduler polls every 15 min, storing the same current rainfall reading
        multiple times. We take only ONE reading per hour to avoid inflation.
        """
        cutoff = now - timedelta(hours=hours)
        window_signals = [
            s for s in rain_signals
            if datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None) > cutoff
        ]
        
        # Deduplicate: keep only ONE signal per hour (the max value in that hour)
        hourly_max = {}
        for s in window_signals:
            ts = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None)
            hour_key = ts.strftime("%Y-%m-%d-%H")
            if hour_key not in hourly_max or s["value"] > hourly_max[hour_key]:
                hourly_max[hour_key] = s["value"]
        
        return sum(hourly_max.values())
    
    def max_temp_in_window(hours):
        cutoff = now - timedelta(hours=hours)
        temps = [s["value"] for s in temp_signals
                 if datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None) > cutoff]
        return max(temps) if temps else 0
    
    def avg_humidity_in_window(hours):
        cutoff = now - timedelta(hours=hours)
        hums = [s["value"] for s in humidity_signals
                if datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None) > cutoff]
        return sum(hums) / len(hums) if hums else 0
    
    # Consecutive hot days (> 40°C)
    consecutive_hot = 0
    for day_offset in range(30):
        day_start = now - timedelta(days=day_offset + 1)
        day_end = now - timedelta(days=day_offset)
        day_temps = [s["value"] for s in temp_signals
                     if day_start < datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00")).replace(tzinfo=None) < day_end]
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
        "month_sin": round(math.sin(2 * math.pi * now.month / 12), 4),
        "month_cos": round(math.cos(2 * math.pi * now.month / 12), 4),
        
        # Placeholder for Agent 1 (imagery)
        "ndwi_delta": 0.0,  # Replaced at call site with Agent 1 data
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER-CALLABLE FETCH CYCLE
# ═══════════════════════════════════════════════════════════════════════════════

async def run_fetch_cycle() -> Dict:
    """
    Complete fetch cycle — called by APScheduler every FETCH_INTERVAL_MINUTES.
    Also called manually by POST /fetch endpoint.
    
    Flow:
      1. Fetch from all 6 data sources for each zone
      2. Store in SQLite (with deduplication)
      3. Broadcast new signals to WebSocket clients
      4. Return summary
    
    Returns:
        Dict with success status, signal counts, and any errors.
    """
    logger.info("📡 ═══ FETCH CYCLE START ═══")
    
    all_signals = []
    errors = []
    source_counts = {}

    for zone in settings.ZONES:
        try:
            # 1. OpenWeatherMap
            weather_signals = await weather_service.fetch_for_zone(zone)
            all_signals.extend(weather_signals)
            source_counts["openweathermap"] = source_counts.get("openweathermap", 0) + len(weather_signals)

            # 2. Open-Meteo (FREE — no key!)
            meteo_signals = await openmeteo_service.fetch_current_and_forecast(zone)
            all_signals.extend(meteo_signals)
            source_counts["open_meteo"] = source_counts.get("open_meteo", 0) + len(meteo_signals)

            # 3. Google Maps Traffic
            traffic_signals = await traffic_service.fetch_for_zone(zone)
            all_signals.extend(traffic_signals)
            source_counts["google_maps"] = source_counts.get("google_maps", 0) + len(traffic_signals)

            # 4. NDMA Alerts
            ndma_signals = await ndma_service.fetch_for_zone(zone)
            all_signals.extend(ndma_signals)
            source_counts["ndma"] = source_counts.get("ndma", 0) + len(ndma_signals)

            # 5. Social Media Keywords
            social_signals = await social_service.fetch_for_zone(zone)
            all_signals.extend(social_signals)
            source_counts["social"] = source_counts.get("social", 0) + len(social_signals)

            logger.info(f"  ✓ {zone['name']}: {len(weather_signals) + len(meteo_signals) + len(traffic_signals) + len(ndma_signals) + len(social_signals)} signals")

        except Exception as e:
            error_msg = f"Error fetching {zone['name']}: {str(e)}"
            logger.error(f"  ✗ {error_msg}")
            errors.append(error_msg)

    # Store in SQLite (deduplication handled by store)
    stored_count = await signal_store.store_signals(all_signals)
    
    # Broadcast to WebSocket clients
    ws_sent = await ws_manager.broadcast_signals(all_signals)

    logger.info(f"📡 ═══ FETCH CYCLE COMPLETE ═══ {stored_count} stored, {ws_sent} WS messages, {len(errors)} errors")
    logger.info(f"    Sources: {source_counts}")

    return {
        "success": len(errors) == 0,
        "signals_collected": len(all_signals),
        "signals_stored": stored_count,
        "websocket_messages": ws_sent,
        "source_counts": source_counts,
        "errors": errors,
    }
