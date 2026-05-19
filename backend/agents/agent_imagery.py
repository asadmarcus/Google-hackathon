"""
CIRO — Agent 1: Imagery & Geospatial
=======================================
Satellite-based flood detection using Google Earth Engine + GeoGemma.

Pipeline:
  1. Fetch latest Sentinel-2 imagery from GEE for each zone
  2. Compute NDWI (water index) and compare with 30-day baseline
  3. Feed imagery + metrics to GeoGemma (Gemini Vision) for AI interpretation
  4. Output: ndwi_delta signal → Agent 2 store → Agent 3 XGBoost feature
  5. Push satellite analysis results to Flutter via WebSocket

Integration:
  - Fills Agent 2's `ndwi_delta` feature (was 0.0 placeholder)
  - Provides visual evidence for Agent 3's predictions
  - Serves before/after imagery to Flutter app

Schedule:
  - Runs daily (Sentinel-2 revisit is ~5 days)
  - On-demand via POST /api/v1/agent1/analyze/{zone_id}
  - Full sweep via POST /api/v1/agent1/analyze-all
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from config.settings import settings
from services.earth_engine_service import get_earth_engine_service
from services.geogemma_service import get_geogemma_service
from services.signal_store import SignalStore
from services.websocket_manager import ws_manager

logger = logging.getLogger("ciro.agent1")
router = APIRouter()

# Services
signal_store = SignalStore()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SatelliteAnalysisResult(BaseModel):
    """Complete satellite analysis for a zone."""
    zone_id: str
    zone_name: str
    province: str
    analysis_timestamp: str

    # Earth Engine metrics
    ndwi_current: float
    ndwi_baseline: float
    ndwi_delta: float
    water_expansion_detected: bool
    flood_signal_strength: float

    # GeoGemma AI interpretation
    ai_flood_detected: bool
    ai_severity: int
    ai_confidence: float
    ai_description: str
    ai_risk_factors: List[str]
    ai_recommendations: List[str]
    ai_estimated_extent_km2: float

    # Imagery URLs (None if GEE not authenticated)
    current_image_url: Optional[str] = None
    baseline_image_url: Optional[str] = None
    ndwi_map_url: Optional[str] = None

    # Metadata
    data_source: str
    satellite: str
    resolution_m: int = 10
    gee_authenticated: bool


class AnalyzeAllResult(BaseModel):
    """Result of analyzing all zones."""
    success: bool
    zones_analyzed: int
    zones_with_flood_signal: int
    highest_severity_zone: str
    highest_severity: int
    timestamp: str
    results: List[SatelliteAnalysisResult]


class Agent1Status(BaseModel):
    """Agent 1 health and configuration."""
    agent: str
    status: str
    gee_authenticated: bool
    gemini_available: bool
    zones_monitored: int
    last_analysis: Optional[str] = None
    capabilities: List[str]


# ─── State ────────────────────────────────────────────────────────────────────

_last_analysis_time: Optional[datetime] = None
_analysis_cache: Dict[str, SatelliteAnalysisResult] = {}
_analysis_lock = asyncio.Lock()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/status", response_model=Agent1Status)
async def agent_status():
    """Agent 1 health, auth status, and capabilities."""
    ee_service = get_earth_engine_service()
    gemma_service = get_geogemma_service()

    return Agent1Status(
        agent="Agent 1 — Imagery & Geospatial",
        status="active",
        gee_authenticated=ee_service.is_available(),
        gemini_available=gemma_service.is_available,
        zones_monitored=len(settings.ZONES),
        last_analysis=_last_analysis_time.isoformat() if _last_analysis_time else None,
        capabilities=[
            "Sentinel-2 imagery retrieval (10m resolution)",
            "NDWI water index computation",
            "NDVI vegetation index computation",
            "30-day change detection (baseline vs current)",
            "GeoGemma AI flood interpretation",
            "Flood extent mapping",
            "Signal integration with Agent 2/3 pipeline",
        ]
    )


@router.post("/initialize")
async def initialize_services():
    """
    Initialize Earth Engine authentication.
    Call once on startup or when GEE credentials are configured.
    """
    ee_service = get_earth_engine_service()
    success = await ee_service.initialize()

    return {
        "success": success,
        "gee_authenticated": ee_service.is_available(),
        "gemini_available": get_geogemma_service().is_available,
        "message": "Earth Engine initialized" if success else "GEE auth failed — running in simulation mode",
    }


@router.post("/analyze/{zone_id}", response_model=SatelliteAnalysisResult)
async def analyze_zone(zone_id: str, force_refresh: bool = False):
    """
    Run full satellite analysis for a single zone.
    
    Pipeline:
      1. Fetch/compute Sentinel-2 NDWI via Earth Engine
      2. Compare with 30-day baseline (change detection)
      3. Send to GeoGemma for AI interpretation
      4. Store ndwi_delta signal in Agent 2's buffer
      5. Broadcast result via WebSocket
    
    Results are cached for 6 hours (Sentinel-2 revisit ~5 days).
    Pass force_refresh=true to bypass cache.
    """
    # Check cache
    if not force_refresh and zone_id in _analysis_cache:
        cached = _analysis_cache[zone_id]
        cache_age = datetime.utcnow() - datetime.fromisoformat(cached.analysis_timestamp)
        if cache_age < timedelta(hours=6):
            return cached

    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    result = await _run_analysis(zone)
    return result


@router.post("/analyze-all", response_model=AnalyzeAllResult)
async def analyze_all_zones(background: bool = False):
    """
    Run satellite analysis for ALL monitored zones.
    
    Set background=true to run asynchronously (returns immediately).
    Otherwise blocks until all zones are analyzed (~30-60s depending on GEE).
    """
    if background:
        asyncio.create_task(_analyze_all_background())
        return AnalyzeAllResult(
            success=True,
            zones_analyzed=0,
            zones_with_flood_signal=0,
            highest_severity_zone="",
            highest_severity=0,
            timestamp=datetime.utcnow().isoformat(),
            results=[],
        )

    results = await _analyze_all_zones()

    flood_zones = [r for r in results if r.water_expansion_detected]
    highest = max(results, key=lambda r: r.ai_severity) if results else None

    return AnalyzeAllResult(
        success=True,
        zones_analyzed=len(results),
        zones_with_flood_signal=len(flood_zones),
        highest_severity_zone=highest.zone_id if highest else "",
        highest_severity=highest.ai_severity if highest else 0,
        timestamp=datetime.utcnow().isoformat(),
        results=results,
    )


@router.get("/latest/{zone_id}", response_model=Optional[SatelliteAnalysisResult])
async def get_latest_analysis(zone_id: str):
    """
    Get the most recent satellite analysis for a zone.
    Returns cached result or None if never analyzed.
    """
    if zone_id not in _analysis_cache:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis available for '{zone_id}'. Run POST /analyze/{zone_id} first."
        )
    return _analysis_cache[zone_id]


@router.get("/imagery/{zone_id}")
async def get_zone_imagery(zone_id: str):
    """
    Get satellite image URLs for a zone (before/after/NDWI map).
    Used by Flutter app to display satellite views.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    ee_service = get_earth_engine_service()
    
    # Get current imagery
    imagery = await ee_service.get_sentinel2_imagery(zone)
    
    if imagery is None:
        return {
            "zone_id": zone_id,
            "available": False,
            "message": "No clear imagery available (cloud cover too high or GEE not authenticated)",
        }

    return {
        "zone_id": zone_id,
        "available": True,
        "image_date": imagery.get("image_date"),
        "cloud_cover": imagery.get("cloud_cover"),
        "rgb_url": imagery.get("rgb_thumbnail_url"),
        "ndwi_url": imagery.get("ndwi_thumbnail_url"),
        "ndwi_mean": imagery.get("ndwi_mean"),
        "ndvi_mean": imagery.get("ndvi_mean"),
        "satellite": imagery.get("satellite"),
        "resolution_m": imagery.get("resolution_m"),
    }


@router.get("/history/{zone_id}")
async def get_zone_analysis_history(zone_id: str, days: int = 30):
    """
    Get historical NDWI trend for a zone.
    Shows water index changes over time for trend analysis.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    # Get stored satellite signals from Agent 2's buffer
    signals = await signal_store.get_signals(zone_id, hours=days * 24)
    
    # Filter to satellite-type signals
    sat_signals = [s for s in signals if s.get("source") == "satellite_agent1"]

    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "days_requested": days,
        "data_points": len(sat_signals),
        "history": sat_signals,
    }


@router.get("/flood-map/{zone_id}")
async def get_flood_extent_map(zone_id: str):
    """
    Get classified flood extent map (water pixels > NDWI threshold).
    Returns image URL showing flooded vs dry areas.
    """
    zone = next((z for z in settings.ZONES if z["id"] == zone_id), None)
    if not zone:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found")

    ee_service = get_earth_engine_service()
    result = await ee_service.get_flood_extent_map(zone)

    if result is None:
        return {
            "zone_id": zone_id,
            "available": False,
            "message": "Flood extent map unavailable (GEE not authenticated or no imagery)",
        }

    return {
        "zone_id": zone_id,
        "available": True,
        **result,
    }


# ─── Core Analysis Logic ─────────────────────────────────────────────────────

async def _run_analysis(zone: Dict) -> SatelliteAnalysisResult:
    """
    Full analysis pipeline for one zone.
    
    Steps:
      1. Earth Engine: Get NDWI change detection
      2. GeoGemma: AI interpretation of satellite data
      3. Store signal: Push ndwi_delta to Agent 2's buffer
      4. WebSocket: Broadcast to Flutter clients
      5. Cache: Store result for subsequent requests
    """
    global _last_analysis_time

    ee_service = get_earth_engine_service()
    gemma_service = get_geogemma_service()

    logger.info(f"🛰️  Analyzing {zone['name']} ({zone['id']})...")

    # Step 1: Earth Engine change detection
    change_data = await ee_service.compute_change_detection(zone)

    # Step 2: GeoGemma AI interpretation
    ai_analysis = await gemma_service.analyze_satellite_imagery(
        zone=zone,
        current_image_url=change_data.get("current_image_url"),
        baseline_image_url=change_data.get("baseline_image_url"),
        ndwi_data=change_data,
        change_data=change_data,
    )

    # Build result
    result = SatelliteAnalysisResult(
        zone_id=zone["id"],
        zone_name=zone["name"],
        province=zone.get("province", "Unknown"),
        analysis_timestamp=datetime.utcnow().isoformat(),
        # EE metrics
        ndwi_current=change_data.get("current_ndwi", 0.0),
        ndwi_baseline=change_data.get("baseline_ndwi", 0.0),
        ndwi_delta=change_data.get("ndwi_delta", 0.0),
        water_expansion_detected=change_data.get("water_expansion_detected", False),
        flood_signal_strength=change_data.get("flood_signal_strength", 0.0),
        # GeoGemma AI
        ai_flood_detected=ai_analysis.flood_detected,
        ai_severity=ai_analysis.severity,
        ai_confidence=ai_analysis.confidence,
        ai_description=ai_analysis.affected_area_description,
        ai_risk_factors=ai_analysis.risk_factors,
        ai_recommendations=ai_analysis.recommendations,
        ai_estimated_extent_km2=ai_analysis.estimated_flood_extent_km2,
        # Imagery
        current_image_url=change_data.get("current_image_url"),
        baseline_image_url=change_data.get("baseline_image_url"),
        ndwi_map_url=change_data.get("ndwi_thumbnail_url"),
        # Meta
        data_source=change_data.get("data_source", "unknown"),
        satellite="Sentinel-2 L2A",
        resolution_m=10,
        gee_authenticated=ee_service.is_available(),
    )

    # Step 3: Store signal in Agent 2's buffer
    await _store_satellite_signal(zone, change_data, ai_analysis)

    # Step 4: Broadcast via WebSocket
    await _broadcast_analysis(result)

    # Step 5: Cache
    _analysis_cache[zone["id"]] = result
    _last_analysis_time = datetime.utcnow()

    logger.info(
        f"🛰️  {zone['name']}: ndwi_delta={change_data.get('ndwi_delta', 0):.4f}, "
        f"AI_severity={ai_analysis.severity}, flood={'YES' if ai_analysis.flood_detected else 'no'}"
    )

    return result


async def _analyze_all_zones() -> List[SatelliteAnalysisResult]:
    """Analyze all zones sequentially (to avoid GEE rate limits)."""
    results = []
    for zone in settings.ZONES:
        try:
            result = await _run_analysis(zone)
            results.append(result)
        except Exception as e:
            logger.error(f"Analysis failed for {zone['id']}: {e}")
    return results


async def _analyze_all_background():
    """Background task for full zone sweep."""
    logger.info("🛰️  Starting background analysis of all zones...")
    results = await _analyze_all_zones()
    logger.info(f"🛰️  Background analysis complete: {len(results)} zones processed")


async def _store_satellite_signal(
    zone: Dict, change_data: Dict, ai_analysis: Any
) -> None:
    """
    Store satellite-derived signal in Agent 2's signal store.
    This fills the ndwi_delta feature that Agent 3 uses for flood prediction.
    """
    signal = {
        "signal_id": f"sat_{zone['id']}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}",
        "signal_type": "satellite_ndwi",
        "zone_id": zone["id"],
        "zone_name": zone["name"],
        "lat": zone["lat"],
        "lng": zone["lng"],
        "value": change_data.get("ndwi_delta", 0.0),
        "severity": ai_analysis.severity,
        "confidence": change_data.get("confidence", 0.5),
        "source": "satellite_agent1",
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": {
            "ndwi_current": change_data.get("current_ndwi", 0.0),
            "ndwi_baseline": change_data.get("baseline_ndwi", 0.0),
            "flood_signal_strength": change_data.get("flood_signal_strength", 0.0),
            "ai_flood_detected": ai_analysis.flood_detected,
            "ai_confidence": ai_analysis.confidence,
            "water_expansion_detected": change_data.get("water_expansion_detected", False),
        }
    }

    try:
        await signal_store.store_signals([signal])
    except Exception as e:
        logger.error(f"Failed to store satellite signal for {zone['id']}: {e}")


async def _broadcast_analysis(result: SatelliteAnalysisResult) -> None:
    """Broadcast analysis result to WebSocket clients."""
    try:
        message = {
            "type": "satellite_analysis",
            "zone_id": result.zone_id,
            "zone_name": result.zone_name,
            "ndwi_delta": result.ndwi_delta,
            "flood_detected": result.ai_flood_detected,
            "severity": result.ai_severity,
            "confidence": result.ai_confidence,
            "description": result.ai_description,
            "timestamp": result.analysis_timestamp,
        }
        await ws_manager.broadcast(message)
    except Exception as e:
        logger.debug(f"WebSocket broadcast failed (no clients?): {e}")


# ─── Scheduled Task Entry Point ──────────────────────────────────────────────

async def run_satellite_analysis_cycle():
    """
    Entry point for scheduled satellite analysis.
    Called by APScheduler (daily) or manually via /analyze-all.
    """
    logger.info("🛰️  Scheduled satellite analysis cycle starting...")
    results = await _analyze_all_zones()
    
    flood_zones = [r for r in results if r.ai_flood_detected]
    if flood_zones:
        logger.warning(
            f"⚠️  FLOOD DETECTED in {len(flood_zones)} zones: "
            f"{', '.join(r.zone_id for r in flood_zones)}"
        )
    
    logger.info(f"🛰️  Cycle complete: {len(results)} zones, {len(flood_zones)} with flood signal")
    return {
        "zones_analyzed": len(results),
        "flood_detected_zones": len(flood_zones),
    }
