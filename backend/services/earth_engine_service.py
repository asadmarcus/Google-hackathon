"""
CIRO — Earth Engine Service
==============================
Handles Google Earth Engine authentication, Sentinel-2 imagery retrieval,
and NDWI/NDVI computation for flood change detection.

Sentinel-2 L2A (10m resolution):
  - Band B3 (Green) + B8 (NIR) → NDWI = (Green - NIR) / (Green + NIR)
  - Band B4 (Red) + B8 (NIR) → NDVI = (NIR - Red) / (NIR + Red)
  - Revisit time: ~5 days per zone

Uses Earth Engine REST API (no local ee library needed for thumbnails).
Falls back to ee Python API if available.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import numpy as np

logger = logging.getLogger("ciro.earth_engine")

# Try importing Earth Engine
try:
    import ee
    EE_AVAILABLE = True
except ImportError:
    EE_AVAILABLE = False
    logger.warning("Earth Engine Python API not installed. Using REST fallback.")


class EarthEngineService:
    """
    Google Earth Engine service for satellite imagery and change detection.
    
    Provides:
      - Sentinel-2 L2A image retrieval for monitored zones
      - NDWI (Normalized Difference Water Index) computation
      - NDVI (Normalized Difference Vegetation Index) computation
      - Change detection between baseline and current imagery
      - Thumbnail/image URL generation for GeoGemma analysis
    """

    def __init__(self):
        self._initialized = False
        self._project_id = os.getenv("GEE_PROJECT_ID", "")
        self._service_account = os.getenv("GEE_SERVICE_ACCOUNT", "")
        self._credentials_path = os.getenv("GEE_CREDENTIALS_PATH", "")
        
        # Cache for computed results (zone_id -> result)
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(hours=6)  # Sentinel-2 revisit is ~5 days

    async def initialize(self) -> bool:
        """
        Initialize Earth Engine authentication.
        Returns True if successful, False otherwise.
        """
        if self._initialized:
            return True

        if not EE_AVAILABLE:
            logger.warning("Earth Engine not available — using simulation mode")
            return False

        try:
            # Try service account auth first
            if self._credentials_path and Path(self._credentials_path).exists():
                credentials = ee.ServiceAccountCredentials(
                    self._service_account,
                    self._credentials_path
                )
                ee.Initialize(credentials, project=self._project_id)
            else:
                # Try default credentials (works in Cloud Run / local gcloud auth)
                ee.Initialize(project=self._project_id if self._project_id else None)

            self._initialized = True
            logger.info("✅ Earth Engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Earth Engine initialization failed: {e}")
            logger.info("Falling back to simulation mode for demo")
            return False

    def is_available(self) -> bool:
        """Check if GEE is authenticated and ready."""
        return self._initialized

    async def get_sentinel2_imagery(
        self,
        zone: Dict,
        days_back: int = 10,
        cloud_cover_max: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch most recent Sentinel-2 L2A image for a zone.
        
        Returns:
            Dict with image metadata, bands, and thumbnail URLs
            or None if no clear image available.
        """
        if not self._initialized:
            return await self._simulate_imagery(zone)

        try:
            result = await asyncio.to_thread(
                self._fetch_sentinel2_sync, zone, days_back, cloud_cover_max
            )
            return result
        except Exception as e:
            logger.error(f"Sentinel-2 fetch failed for {zone['id']}: {e}")
            return await self._simulate_imagery(zone)

    def _fetch_sentinel2_sync(
        self, zone: Dict, days_back: int, cloud_cover_max: int
    ) -> Optional[Dict]:
        """Synchronous GEE fetch (run in thread)."""
        lat, lng = zone["lat"], zone["lng"]
        
        # Define area of interest (5km buffer around zone center)
        point = ee.Geometry.Point([lng, lat])
        aoi = point.buffer(5000)  # 5km radius

        # Date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)

        # Query Sentinel-2 L2A (Surface Reflectance)
        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_cover_max))
            .sort("CLOUDY_PIXEL_PERCENTAGE")
        )

        count = collection.size().getInfo()
        if count == 0:
            logger.warning(f"No clear Sentinel-2 images for {zone['id']} in last {days_back} days")
            return None

        # Get the clearest image
        image = collection.first()
        info = image.getInfo()
        
        # Compute NDWI: (B3 - B8) / (B3 + B8)
        ndwi = image.normalizedDifference(["B3", "B8"]).rename("NDWI")
        
        # Compute NDVI: (B8 - B4) / (B8 + B4)
        ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")

        # Get mean values over the AOI
        ndwi_stats = ndwi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=10,
            maxPixels=1e8
        ).getInfo()

        ndvi_stats = ndvi.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=10,
            maxPixels=1e8
        ).getInfo()

        # Generate thumbnail URLs
        rgb_url = image.select(["B4", "B3", "B2"]).getThumbURL({
            "region": aoi,
            "dimensions": 512,
            "min": 0,
            "max": 3000,
            "format": "png"
        })

        ndwi_url = ndwi.getThumbURL({
            "region": aoi,
            "dimensions": 512,
            "min": -1,
            "max": 1,
            "palette": ["red", "yellow", "green", "cyan", "blue"],
            "format": "png"
        })

        return {
            "zone_id": zone["id"],
            "image_date": info["properties"]["system:time_start"],
            "cloud_cover": info["properties"].get("CLOUDY_PIXEL_PERCENTAGE", 0),
            "ndwi_mean": ndwi_stats.get("NDWI", 0.0),
            "ndvi_mean": ndvi_stats.get("NDVI", 0.0),
            "rgb_thumbnail_url": rgb_url,
            "ndwi_thumbnail_url": ndwi_url,
            "satellite": "Sentinel-2 L2A",
            "resolution_m": 10,
            "aoi_radius_m": 5000,
        }

    async def compute_change_detection(
        self,
        zone: Dict,
        baseline_days_back: int = 30,
        current_days_back: int = 10
    ) -> Dict[str, Any]:
        """
        Compare current imagery with baseline to detect water expansion.
        
        Returns:
            Dict with ndwi_delta, flood indicators, and image URLs
        """
        if not self._initialized:
            return await self._simulate_change_detection(zone)

        try:
            result = await asyncio.to_thread(
                self._compute_change_sync, zone, baseline_days_back, current_days_back
            )
            return result
        except Exception as e:
            logger.error(f"Change detection failed for {zone['id']}: {e}")
            return await self._simulate_change_detection(zone)

    def _compute_change_sync(
        self, zone: Dict, baseline_days_back: int, current_days_back: int
    ) -> Dict:
        """Synchronous change detection (run in thread)."""
        lat, lng = zone["lat"], zone["lng"]
        point = ee.Geometry.Point([lng, lat])
        aoi = point.buffer(5000)

        now = datetime.utcnow()

        # Baseline period (e.g., 30-60 days ago)
        baseline_end = now - timedelta(days=baseline_days_back)
        baseline_start = baseline_end - timedelta(days=30)

        # Current period (most recent)
        current_end = now
        current_start = now - timedelta(days=current_days_back)

        def get_median_ndwi(start, end):
            col = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi)
                .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
            )
            if col.size().getInfo() == 0:
                return None, None
            
            median = col.median()
            ndwi = median.normalizedDifference(["B3", "B8"])
            
            stats = ndwi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=aoi,
                scale=10,
                maxPixels=1e8
            ).getInfo()
            
            url = ndwi.getThumbURL({
                "region": aoi,
                "dimensions": 512,
                "min": -1, "max": 1,
                "palette": ["red", "yellow", "green", "cyan", "blue"],
                "format": "png"
            })
            
            return stats.get("nd", 0.0), url

        baseline_ndwi, baseline_url = get_median_ndwi(baseline_start, baseline_end)
        current_ndwi, current_url = get_median_ndwi(current_start, current_end)

        if baseline_ndwi is None or current_ndwi is None:
            return self._simulate_change_detection_sync(zone)

        ndwi_delta = (current_ndwi or 0.0) - (baseline_ndwi or 0.0)

        # Positive delta = more water = potential flooding
        flood_signal = max(0.0, ndwi_delta * 5.0)  # Scale to 0-1 range
        flood_signal = min(1.0, flood_signal)

        return {
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "baseline_ndwi": round(baseline_ndwi or 0.0, 4),
            "current_ndwi": round(current_ndwi or 0.0, 4),
            "ndwi_delta": round(ndwi_delta, 4),
            "flood_signal_strength": round(flood_signal, 3),
            "water_expansion_detected": ndwi_delta > 0.05,
            "baseline_image_url": baseline_url,
            "current_image_url": current_url,
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "data_source": "sentinel2_gee",
            "confidence": 0.85 if abs(ndwi_delta) > 0.02 else 0.60,
        }

    # ─── Simulation Mode (for demo without GEE auth) ──────────────────────

    async def _simulate_imagery(self, zone: Dict) -> Dict:
        """Generate realistic simulated satellite data for demo."""
        import random
        
        # Simulate based on zone characteristics
        base_ndwi = -0.1  # Typical urban area
        if zone["id"] in ("sukkur-city", "jacobabad-city"):
            base_ndwi = 0.05  # Near rivers
        elif zone["id"] == "karachi-south":
            base_ndwi = 0.15  # Coastal

        # Add seasonal variation (May = pre-monsoon, drier)
        month = datetime.utcnow().month
        if month in (7, 8, 9):  # Monsoon
            base_ndwi += random.uniform(0.05, 0.20)
        
        ndwi = base_ndwi + random.uniform(-0.03, 0.03)
        ndvi = random.uniform(0.15, 0.45)

        return {
            "zone_id": zone["id"],
            "image_date": int((datetime.utcnow() - timedelta(days=random.randint(1, 5))).timestamp() * 1000),
            "cloud_cover": random.uniform(5, 25),
            "ndwi_mean": round(ndwi, 4),
            "ndvi_mean": round(ndvi, 4),
            "rgb_thumbnail_url": None,  # No real image in simulation
            "ndwi_thumbnail_url": None,
            "satellite": "Sentinel-2 L2A (SIMULATED)",
            "resolution_m": 10,
            "aoi_radius_m": 5000,
            "simulated": True,
        }

    async def _simulate_change_detection(self, zone: Dict) -> Dict:
        """Simulate change detection for demo."""
        return await asyncio.to_thread(self._simulate_change_detection_sync, zone)

    def _simulate_change_detection_sync(self, zone: Dict) -> Dict:
        """Synchronous simulation."""
        import random

        month = datetime.utcnow().month
        
        # Higher flood signal during monsoon months for flood-prone zones
        flood_prone = zone["id"] in ("sukkur-city", "jacobabad-city", "karachi-south", "peshawar-city")
        is_monsoon = month in (7, 8, 9)
        
        if flood_prone and is_monsoon:
            ndwi_delta = random.uniform(0.05, 0.25)
        elif is_monsoon:
            ndwi_delta = random.uniform(0.0, 0.12)
        else:
            ndwi_delta = random.uniform(-0.05, 0.05)

        baseline_ndwi = random.uniform(-0.15, 0.05)
        current_ndwi = baseline_ndwi + ndwi_delta

        flood_signal = max(0.0, min(1.0, ndwi_delta * 5.0))

        return {
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "baseline_ndwi": round(baseline_ndwi, 4),
            "current_ndwi": round(current_ndwi, 4),
            "ndwi_delta": round(ndwi_delta, 4),
            "flood_signal_strength": round(flood_signal, 3),
            "water_expansion_detected": ndwi_delta > 0.05,
            "baseline_image_url": None,
            "current_image_url": None,
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "data_source": "sentinel2_simulated",
            "confidence": 0.50,  # Lower confidence for simulated
            "simulated": True,
        }

    async def get_flood_extent_map(self, zone: Dict) -> Optional[Dict]:
        """
        Generate a flood extent map showing water pixels > threshold.
        Used as input for GeoGemma visual analysis.
        """
        if not self._initialized:
            return None

        try:
            result = await asyncio.to_thread(self._flood_extent_sync, zone)
            return result
        except Exception as e:
            logger.error(f"Flood extent map failed for {zone['id']}: {e}")
            return None

    def _flood_extent_sync(self, zone: Dict) -> Dict:
        """Generate flood extent classification map."""
        lat, lng = zone["lat"], zone["lng"]
        point = ee.Geometry.Point([lng, lat])
        aoi = point.buffer(5000)

        now = datetime.utcnow()
        start = now - timedelta(days=10)

        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(aoi)
            .filterDate(start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
        )

        if col.size().getInfo() == 0:
            return None

        image = col.median()
        ndwi = image.normalizedDifference(["B3", "B8"])
        
        # Classify: water where NDWI > 0.3
        water_mask = ndwi.gt(0.3)
        
        # Get water pixel percentage
        water_stats = water_mask.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=10,
            maxPixels=1e8
        ).getInfo()

        # Generate classified map URL
        classified_url = water_mask.getThumbURL({
            "region": aoi,
            "dimensions": 512,
            "min": 0, "max": 1,
            "palette": ["land:brown", "water:blue"],
            "format": "png"
        })

        water_fraction = water_stats.get("nd", 0.0) or 0.0
        aoi_area_km2 = 3.14159 * (5.0 ** 2)  # π * r²
        water_area_km2 = water_fraction * aoi_area_km2

        return {
            "zone_id": zone["id"],
            "water_fraction": round(water_fraction, 4),
            "water_area_km2": round(water_area_km2, 2),
            "total_area_km2": round(aoi_area_km2, 2),
            "flood_extent_url": classified_url,
            "threshold_ndwi": 0.3,
            "timestamp": datetime.utcnow().isoformat(),
        }


# Singleton
_earth_engine_service: Optional[EarthEngineService] = None


def get_earth_engine_service() -> EarthEngineService:
    """Get or create the Earth Engine service singleton."""
    global _earth_engine_service
    if _earth_engine_service is None:
        _earth_engine_service = EarthEngineService()
    return _earth_engine_service
