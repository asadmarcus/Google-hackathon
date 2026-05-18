"""
Traffic Service — Google Maps Traffic Integration
==================================================
Fetches traffic congestion data for monitored zones.
High congestion during heavy rain = infrastructure failure signal.
"""
import httpx
import logging
import random
from datetime import datetime
from typing import List, Dict
from config.settings import settings

logger = logging.getLogger("ciro.services.traffic")


class TrafficService:
    """Fetches traffic/congestion data from Google Maps."""

    def __init__(self):
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_for_zone(self, zone: Dict) -> List[Dict]:
        """
        Fetch traffic congestion for a zone.
        Uses Google Maps Directions API to estimate congestion.
        Falls back to simulation if no API key.
        """
        if not self.api_key:
            return self._simulate_traffic(zone)

        try:
            # Use Directions API with traffic model
            # Route from zone center to a nearby point — compare duration vs duration_in_traffic
            offset = 0.02  # ~2km offset
            response = await self.client.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params={
                    "origin": f"{zone['lat']},{zone['lng']}",
                    "destination": f"{zone['lat'] + offset},{zone['lng'] + offset}",
                    "departure_time": "now",
                    "traffic_model": "best_guess",
                    "key": self.api_key,
                }
            )
            response.raise_for_status()
            data = response.json()

            return self._parse_traffic_response(data, zone)

        except Exception as e:
            logger.warning(f"  ⚠ Traffic API failed for {zone['name']}: {e}")
            return self._simulate_traffic(zone)

    def _parse_traffic_response(self, data: Dict, zone: Dict) -> List[Dict]:
        """Parse Google Maps Directions response for congestion."""
        now = datetime.utcnow().isoformat() + "Z"
        base_id = f"traffic_{zone['id']}_{datetime.utcnow().strftime('%Y%m%d%H%M')}"

        routes = data.get("routes", [])
        if not routes:
            return self._simulate_traffic(zone)

        leg = routes[0].get("legs", [{}])[0]
        normal_duration = leg.get("duration", {}).get("value", 0)  # seconds
        traffic_duration = leg.get("duration_in_traffic", {}).get("value", 0)

        if normal_duration == 0:
            congestion_ratio = 1.0
        else:
            congestion_ratio = traffic_duration / normal_duration

        # Convert ratio to 0-10 severity
        # 1.0 = normal, 1.5 = moderate, 2.0+ = severe
        congestion_score = min(10, max(1, int((congestion_ratio - 1) * 10)))

        return [{
            "signal_id": base_id,
            "signal_type": "traffic",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": round(congestion_ratio, 2),
            "severity": congestion_score,
            "confidence": 0.85,
            "source": "google_maps",
            "timestamp": now,
            "metadata": {
                "normal_duration_s": normal_duration,
                "traffic_duration_s": traffic_duration,
                "congestion_ratio": round(congestion_ratio, 2),
            }
        }]

    def _simulate_traffic(self, zone: Dict) -> List[Dict]:
        """Simulate traffic data for demo."""
        now = datetime.utcnow()
        base_id = f"sim_traffic_{zone['id']}_{now.strftime('%Y%m%d%H%M')}"

        # Higher congestion during peak hours (8-10 AM, 5-8 PM PKT = UTC+5)
        hour_pkt = (now.hour + 5) % 24
        is_peak = hour_pkt in range(8, 10) or hour_pkt in range(17, 20)
        
        base_congestion = 1.5 if is_peak else 1.1
        congestion_ratio = base_congestion + random.uniform(0, 0.8)
        
        # Higher population density = more traffic
        density_factor = zone["population_density"] / 10000
        congestion_ratio += density_factor * 0.3
        
        congestion_score = min(10, max(1, int((congestion_ratio - 1) * 8)))

        return [{
            "signal_id": base_id,
            "signal_type": "traffic",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": round(congestion_ratio, 2),
            "severity": congestion_score,
            "confidence": 0.70,
            "source": "simulated",
            "timestamp": now.isoformat() + "Z",
            "metadata": {"simulated": True, "is_peak_hour": is_peak}
        }]
