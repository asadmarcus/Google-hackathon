"""
Social Signal Service — Simulated Crisis Keyword Monitoring
============================================================
In production: would monitor Twitter/X, Facebook, local news for crisis keywords.
For hackathon: generates realistic simulated social signals based on
Urdu + English flood/heat keywords from Pakistani social media patterns.
"""
import random
import logging
from datetime import datetime
from typing import List, Dict
from config.settings import settings

logger = logging.getLogger("ciro.services.social")


# Crisis keywords we'd monitor in production
FLOOD_KEYWORDS_EN = ["flood", "flooding", "water rising", "submerged", "road blocked",
                     "heavy rain", "rescue needed", "evacuate", "stranded"]
FLOOD_KEYWORDS_UR = ["سیلاب", "پانی", "بارش", "ڈوب", "بچاؤ", "راستہ بند",
                     "طغیانی", "تباہی"]
HEAT_KEYWORDS_EN = ["heatstroke", "heat wave", "too hot", "no electricity",
                    "load shedding", "water shortage", "sunstroke"]
HEAT_KEYWORDS_UR = ["گرمی", "لو", "بجلی نہیں", "پانی نہیں", "ہیٹ ویو",
                    "لوڈشیڈنگ"]

# Simulated post templates
POST_TEMPLATES_FLOOD = [
    "Heavy rain in {zone} for 3 hours straight, streets flooding #flood",
    "Road completely submerged near {zone}, can't get to work",
    "{zone} main nallah overflowing, water entering houses",
    "بارش رکنے کا نام نہیں لے رہی {zone} میں - سڑکیں ڈوب گئیں",
    "Rescue needed in {zone} - family stuck on rooftop",
    "{zone} drainage system completely failed again",
    "پانی گھروں میں آ گیا ہے {zone} میں مدد چاہیے",
]

POST_TEMPLATES_HEAT = [
    "45°C in {zone} today, impossible to go outside #heatwave",
    "{zone} میں بجلی 12 گھنٹے سے بند ہے - گرمی برداشت نہیں ہو رہی",
    "3 people hospitalized with heatstroke in {zone}",
    "No water supply in {zone} for 2 days in this heat",
    "Load shedding + heat wave = disaster in {zone}",
    "{zone} کے لوگ بیمار ہو رہے ہیں گرمی سے",
]


class SocialSignalService:
    """Simulates social media crisis monitoring."""

    async def fetch_for_zone(self, zone: Dict) -> List[Dict]:
        """
        Generate simulated social signals for a zone.
        Probability varies by season (monsoon = more flood posts).
        """
        now = datetime.utcnow()
        month = now.month
        is_monsoon = month in [6, 7, 8, 9]
        is_hot_season = month in [4, 5, 6, 7]

        signals = []

        # Flood-related social signals (higher during monsoon)
        flood_prob = 0.6 if is_monsoon else 0.1
        if random.random() < flood_prob:
            post = random.choice(POST_TEMPLATES_FLOOD).format(zone=zone["name"])
            keyword = random.choice(FLOOD_KEYWORDS_EN + FLOOD_KEYWORDS_UR)
            severity = random.randint(5, 9) if is_monsoon else random.randint(2, 5)

            signals.append({
                "signal_id": f"social_flood_{zone['id']}_{now.strftime('%Y%m%d%H%M%S')}",
                "signal_type": "social",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": severity,  # Severity as value for social signals
                "severity": severity,
                "confidence": 0.50,  # Simulated source — lower confidence  # Social signals have lower confidence
                "source": "simulated_social",
                "timestamp": now.isoformat() + "Z",
                "metadata": {
                    "post_text": post,
                    "keyword_matched": keyword,
                    "crisis_type": "flood",
                    "platform": random.choice(["twitter", "facebook", "whatsapp"]),
                    "simulated": True,
                }
            })

        # Heat-related social signals (higher in hot season)
        heat_prob = 0.5 if is_hot_season else 0.05
        if random.random() < heat_prob:
            post = random.choice(POST_TEMPLATES_HEAT).format(zone=zone["name"])
            keyword = random.choice(HEAT_KEYWORDS_EN + HEAT_KEYWORDS_UR)
            severity = random.randint(4, 8) if is_hot_season else random.randint(1, 3)

            signals.append({
                "signal_id": f"social_heat_{zone['id']}_{now.strftime('%Y%m%d%H%M%S')}",
                "signal_type": "social",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": severity,
                "severity": severity,
                "confidence": 0.50,  # Simulated source — lower confidence
                "source": "simulated_social",
                "timestamp": now.isoformat() + "Z",
                "metadata": {
                    "post_text": post,
                    "keyword_matched": keyword,
                    "crisis_type": "heatstroke",
                    "platform": random.choice(["twitter", "facebook", "whatsapp"]),
                    "simulated": True,
                }
            })

        return signals
