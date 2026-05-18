"""
NDMA Alert Service — Pakistan National Disaster Management Authority
=====================================================================
Fetches official disaster alerts from NDMA Pakistan.
In production: scrapes NDMA website / RSS feed.
For hackathon: simulates realistic alerts based on current conditions.

NDMA official site: https://www.ndma.gov.pk/
"""
import httpx
import logging
import random
from datetime import datetime
from typing import List, Dict
from config.settings import settings

logger = logging.getLogger("ciro.services.ndma")


# Real NDMA alert categories
NDMA_ALERT_LEVELS = {
    "GREEN": {"severity": 2, "description": "Normal conditions"},
    "YELLOW": {"severity": 5, "description": "Watch — potential risk developing"},
    "ORANGE": {"severity": 7, "description": "Warning — significant risk"},
    "RED": {"severity": 9, "description": "Emergency — immediate action required"},
}

# Simulated NDMA-style bulletins (based on real NDMA language)
NDMA_BULLETINS_FLOOD = [
    "PMD has predicted heavy to very heavy rainfall in {province} during next 48-72 hours.",
    "NDMA Advisory: All relevant departments to remain on high alert in {province} due to expected monsoon spell.",
    "Flash flooding expected in nullahs and streams of {province}. District administrations directed to take precautionary measures.",
    "River {river} at {zone} showing rising trend. Current level: HIGH. Expected: VERY HIGH in 24 hours.",
    "Urban flooding likely in low-lying areas of {zone} due to continued rainfall and choked drainage.",
]

NDMA_BULLETINS_HEAT = [
    "Severe heatwave expected in {province}. Temperature likely to reach 47-49°C. Public advisory issued.",
    "NDMA urges citizens in {zone} to avoid sun exposure between 11AM-4PM. Heatstroke risk VERY HIGH.",
    "Multiple heatstroke cases reported in {province}. Hospitals on alert status.",
    "Water shortage reported in {zone} during heatwave. NDMA coordinating emergency water supply.",
]

RIVERS_BY_PROVINCE = {
    "Punjab": ["Chenab", "Ravi", "Jhelum", "Sutlej"],
    "Sindh": ["Indus", "Hub"],
    "KPK": ["Kabul", "Swat", "Indus"],
    "Federal": ["Nullah Lai", "Korang"],
}


class NDMAAlertService:
    """
    Fetches/simulates NDMA Pakistan disaster alerts.
    """

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_for_zone(self, zone: Dict) -> List[Dict]:
        """
        Get current NDMA alerts for a zone.
        Tries real RSS/API first, falls back to simulation.
        """
        # Try fetching real NDMA data
        real_alerts = await self._fetch_real_alerts(zone)
        if real_alerts:
            return real_alerts

        # Fallback: generate realistic simulated alerts
        return self._simulate_alerts(zone)

    async def _fetch_real_alerts(self, zone: Dict) -> List[Dict]:
        """
        Attempt to fetch from NDMA RSS or alerts page.
        Returns empty list if unavailable (triggering simulation).
        """
        try:
            # NDMA doesn't have a clean API, but we can try their alerts page
            response = await self.client.get(
                "https://www.ndma.gov.pk/",
                timeout=5.0,
            )
            # If we get a response, we could parse it — for hackathon, we skip
            # and use simulation. In production, add proper scraping here.
            return []
        except:
            return []

    def _simulate_alerts(self, zone: Dict) -> List[Dict]:
        """
        Generate realistic NDMA-style alerts based on season and zone.
        """
        now = datetime.utcnow()
        month = now.month
        is_monsoon = month in [6, 7, 8, 9]
        is_hot = month in [4, 5, 6, 7]
        province = zone.get("province", "Federal")
        signals = []

        # Flood alerts (higher probability during monsoon)
        flood_prob = 0.5 if is_monsoon else 0.05
        if random.random() < flood_prob:
            alert_level = random.choice(["YELLOW", "ORANGE", "RED"]) if is_monsoon else "YELLOW"
            alert_info = NDMA_ALERT_LEVELS[alert_level]
            
            # Pick a relevant river
            rivers = RIVERS_BY_PROVINCE.get(province, ["Indus"])
            river = random.choice(rivers)
            
            bulletin = random.choice(NDMA_BULLETINS_FLOOD).format(
                province=province, zone=zone["name"], river=river
            )

            signals.append({
                "signal_id": f"ndma_flood_{zone['id']}_{now.strftime('%Y%m%d%H%M')}",
                "signal_type": "official_alert",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": alert_info["severity"],
                "severity": alert_info["severity"],
                "confidence": 0.50,  # Simulated — no real NDMA API connected  # Official alerts are high confidence
                "source": "simulated_ndma",
                "timestamp": now.isoformat() + "Z",
                "metadata": {
                    "alert_level": alert_level,
                    "description": alert_info["description"],
                    "bulletin": bulletin,
                    "crisis_type": "flood",
                    "authority": "NDMA Pakistan",
                    "province": province,
                    "simulated": True,
                }
            })

        # Heatwave alerts
        heat_prob = 0.4 if is_hot else 0.02
        if random.random() < heat_prob:
            alert_level = random.choice(["YELLOW", "ORANGE"]) if is_hot else "YELLOW"
            alert_info = NDMA_ALERT_LEVELS[alert_level]
            
            bulletin = random.choice(NDMA_BULLETINS_HEAT).format(
                province=province, zone=zone["name"]
            )

            signals.append({
                "signal_id": f"ndma_heat_{zone['id']}_{now.strftime('%Y%m%d%H%M')}",
                "signal_type": "official_alert",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": alert_info["severity"],
                "severity": alert_info["severity"],
                "confidence": 0.50,  # Simulated — no real NDMA API connected
                "source": "simulated_ndma",
                "timestamp": now.isoformat() + "Z",
                "metadata": {
                    "alert_level": alert_level,
                    "description": alert_info["description"],
                    "bulletin": bulletin,
                    "crisis_type": "heatwave",
                    "authority": "NDMA Pakistan",
                    "province": province,
                    "simulated": True,
                }
            })

        return signals
