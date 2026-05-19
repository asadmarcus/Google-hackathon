"""
CIRO — Google Flood Hub Integration
=====================================
Uses Google's Flood Forecasting API as a data source.
Google's AI predicts riverine floods 7 days ahead — we consume their
predictions as one of our signals, alongside Open-Meteo, GloFAS, etc.

This makes CIRO a meta-system that COMBINES multiple AI forecasts
(Google's + ours) for more robust predictions.

API: https://developers.google.com/flood-forecasting
Access: Requires API key (waitlist → approval → enable in Cloud project)
Coverage: Pakistan rivers included (Indus, Chenab, Jhelum, Kabul, Ravi)
License: CC BY 4.0 (free)

If API key not available, falls back to GloFAS data (already integrated).
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("ciro.floodhub")

# Google Flood Forecasting API base
FLOODHUB_API = "https://floodforecasting.googleapis.com/v1"

# Pakistan gauge stations near our monitored zones
# These are approximate gauge IDs for rivers near each zone
# Real IDs would come from the API's ListGauges endpoint
ZONE_GAUGES: Dict[str, List[str]] = {
    "islamabad-g10": ["PK-INDUS-TARBELA", "PK-SOAN-ISB"],
    "lahore-city": ["PK-RAVI-LAHORE", "PK-CHENAB-MARALA"],
    "karachi-south": ["PK-INDUS-KOTRI", "PK-INDUS-SUKKUR"],
    "peshawar-city": ["PK-KABUL-NOWSHERA", "PK-KABUL-WARSAK"],
    "multan-city": ["PK-CHENAB-PANJNAD", "PK-INDUS-TAUNSA"],
    "jacobabad-city": ["PK-INDUS-SUKKUR", "PK-INDUS-GUDDU"],
    "sukkur-city": ["PK-INDUS-SUKKUR", "PK-INDUS-GUDDU"],
    "quetta-city": ["PK-BOLAN-QUETTA"],
}


class FloodHubService:
    """
    Integrates Google's Flood Forecasting API as a signal source.
    
    What it provides:
      - 7-day flood forecasts from Google's AI (LSTM-based)
      - Gauge-level river discharge predictions
      - Flood status (no_flooding, watch, warning, danger)
      - Inundation polygon data (if available)
    
    How CIRO uses it:
      - Agent 2 fetches FloodHub data alongside Open-Meteo/GloFAS
      - Stored as signals with source="google_floodhub"
      - Agent 3 uses Google's flood probability as a weighted input
      - Confidence: HIGH (Google's model is state-of-the-art)
    """

    def __init__(self):
        self._api_key = os.getenv("GOOGLE_FLOODHUB_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None
        self._available = False

    @property
    def is_available(self) -> bool:
        """Check if FloodHub API key is configured."""
        return bool(self._api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def initialize(self) -> bool:
        """Test API connectivity."""
        if not self._api_key:
            logger.info("Google FloodHub: No API key configured (GOOGLE_FLOODHUB_API_KEY)")
            logger.info("  → Apply at: https://developers.google.com/flood-forecasting")
            logger.info("  → Falling back to GloFAS data")
            return False

        try:
            client = await self._get_client()
            resp = await client.get(
                f"{FLOODHUB_API}/gauges",
                params={"key": self._api_key, "regionCode": "PK"},
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                self._available = True
                logger.info("✅ Google FloodHub connected — Pakistan gauges available")
                return True
            else:
                logger.warning(f"FloodHub API returned {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            logger.warning(f"FloodHub connection failed: {e}")
            return False

    async def get_flood_forecast(self, zone_id: str) -> Optional[Dict[str, Any]]:
        """
        Get Google's flood forecast for gauges near a zone.
        
        Returns:
            Dict with flood_status, forecast_days, discharge_forecast, etc.
            None if unavailable.
        """
        if not self._available:
            return None

        gauges = ZONE_GAUGES.get(zone_id, [])
        if not gauges:
            return None

        try:
            client = await self._get_client()
            results = []

            for gauge_id in gauges:
                resp = await client.get(
                    f"{FLOODHUB_API}/gauges/{gauge_id}/forecasts",
                    params={
                        "key": self._api_key,
                        "forecastStartTime": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "forecastEndTime": (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results.append({
                        "gauge_id": gauge_id,
                        "forecasts": data.get("forecasts", []),
                        "flood_status": data.get("floodStatus", "unknown"),
                    })

            if not results:
                return None

            # Aggregate: take the worst flood status from all nearby gauges
            statuses = [r["flood_status"] for r in results]
            severity_order = ["no_flooding", "watch", "warning", "danger"]
            worst_status = max(statuses, key=lambda s: severity_order.index(s) if s in severity_order else 0)

            # Convert to our signal format
            flood_prob = {
                "danger": 0.9,
                "warning": 0.7,
                "watch": 0.4,
                "no_flooding": 0.1,
                "unknown": 0.0,
            }.get(worst_status, 0.0)

            return {
                "zone_id": zone_id,
                "source": "google_floodhub",
                "flood_status": worst_status,
                "flood_probability": flood_prob,
                "forecast_days": 7,
                "gauges_checked": len(results),
                "gauge_data": results,
                "confidence": 0.92,  # Google's model is very accurate
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"FloodHub forecast error for {zone_id}: {e}")
            return None

    async def get_flood_status_all_zones(self) -> Dict[str, Dict]:
        """Get flood status for all monitored zones."""
        results = {}
        for zone_id in ZONE_GAUGES:
            forecast = await self.get_flood_forecast(zone_id)
            if forecast:
                results[zone_id] = forecast
        return results

    def to_signal(self, forecast: Dict) -> Dict:
        """Convert FloodHub forecast to CIRO signal format."""
        status = forecast.get("flood_status", "unknown")
        severity_map = {"danger": 10, "warning": 8, "watch": 5, "no_flooding": 1, "unknown": 0}

        return {
            "signal_id": f"floodhub_{forecast['zone_id']}_{datetime.utcnow().strftime('%Y%m%d_%H%M')}",
            "signal_type": "flood_forecast",
            "zone_id": forecast["zone_id"],
            "zone_name": "",  # Filled by caller
            "lat": 0.0,  # Filled by caller
            "lng": 0.0,
            "value": forecast.get("flood_probability", 0.0),
            "severity": severity_map.get(status, 0),
            "confidence": forecast.get("confidence", 0.92),
            "source": "google_floodhub",
            "timestamp": forecast.get("timestamp", datetime.utcnow().isoformat()),
            "metadata": {
                "flood_status": status,
                "gauges_checked": forecast.get("gauges_checked", 0),
                "forecast_days": 7,
                "model": "Google Flood Forecasting AI (LSTM)",
            },
        }

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton
_floodhub: Optional[FloodHubService] = None

def get_floodhub_service() -> FloodHubService:
    global _floodhub
    if _floodhub is None:
        _floodhub = FloodHubService()
    return _floodhub
