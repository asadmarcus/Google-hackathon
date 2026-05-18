"""
Weather Service — OpenWeatherMap Integration
=============================================
Fetches current weather + short-term forecast for monitored zones.
Falls back to simulated data if API key is not configured.
"""
import httpx
import logging
from datetime import datetime
from typing import List, Dict
from config.settings import settings

logger = logging.getLogger("ciro.services.weather")


class WeatherService:
    """Fetches weather data from OpenWeatherMap API."""

    def __init__(self):
        self.api_key = settings.OPENWEATHER_API_KEY
        self.base_url = settings.OPENWEATHER_BASE_URL
        self.client = httpx.AsyncClient(timeout=10.0)

    async def fetch_for_zone(self, zone: Dict) -> List[Dict]:
        """
        Fetch current weather for a zone.
        Returns list of normalized Signal dicts.
        """
        if not self.api_key:
            logger.info(f"  ⏭ No OpenWeather API key — skipping (Open-Meteo covers this)")
            return []  # Don't inject fake data. Open-Meteo provides real weather without a key.

        try:
            # Current weather
            response = await self.client.get(
                f"{self.base_url}/weather",
                params={
                    "lat": zone["lat"],
                    "lon": zone["lng"],
                    "appid": self.api_key,
                    "units": "metric",
                }
            )
            response.raise_for_status()
            data = response.json()

            signals = self._parse_weather_response(data, zone)
            return signals

        except httpx.HTTPStatusError as e:
            logger.error(f"  ✗ Weather API error for {zone['name']}: {e.response.status_code}")
            return []  # Don't inject fake data on API failure
        except Exception as e:
            logger.error(f"  ✗ Weather fetch failed for {zone['name']}: {e}")
            return []  # Don't inject fake data on failure

    def _parse_weather_response(self, data: Dict, zone: Dict) -> List[Dict]:
        """Parse OpenWeatherMap response into Signal format."""
        now = datetime.utcnow().isoformat() + "Z"
        base_id = f"owm_{zone['id']}_{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        
        signals = []

        # Temperature
        temp = data.get("main", {}).get("temp", 0)
        signals.append({
            "signal_id": f"{base_id}_temp",
            "signal_type": "temperature",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": temp,
            "severity": self._temp_severity(temp),
            "confidence": 0.95,
            "source": "openweathermap",
            "timestamp": now,
            "metadata": {
                "feels_like": data.get("main", {}).get("feels_like", 0),
                "temp_min": data.get("main", {}).get("temp_min", 0),
                "temp_max": data.get("main", {}).get("temp_max", 0),
            }
        })

        # Humidity
        humidity = data.get("main", {}).get("humidity", 0)
        signals.append({
            "signal_id": f"{base_id}_humidity",
            "signal_type": "humidity",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": humidity,
            "severity": self._humidity_severity(humidity),
            "confidence": 0.93,
            "source": "openweathermap",
            "timestamp": now,
            "metadata": {"pressure_hpa": data.get("main", {}).get("pressure", 0)}
        })

        # Wind
        wind_speed = data.get("wind", {}).get("speed", 0) * 3.6  # m/s to km/h
        signals.append({
            "signal_id": f"{base_id}_wind",
            "signal_type": "wind",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": round(wind_speed, 1),
            "severity": self._wind_severity(wind_speed),
            "confidence": 0.90,
            "source": "openweathermap",
            "timestamp": now,
            "metadata": {"direction_deg": data.get("wind", {}).get("deg", 0)}
        })

        # Rainfall (if present)
        rain_1h = data.get("rain", {}).get("1h", 0)
        rain_3h = data.get("rain", {}).get("3h", 0)
        rain_value = rain_1h or (rain_3h / 3 if rain_3h else 0)
        
        if rain_value > 0:
            signals.append({
                "signal_id": f"{base_id}_rain",
                "signal_type": "rainfall",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": round(rain_value, 2),
                "severity": self._rain_severity(rain_value),
                "confidence": 0.88,
                "source": "openweathermap",
                "timestamp": now,
                "metadata": {
                    "rain_1h_mm": rain_1h,
                    "rain_3h_mm": rain_3h,
                    "weather_main": data.get("weather", [{}])[0].get("main", ""),
                    "weather_desc": data.get("weather", [{}])[0].get("description", ""),
                }
            })
        
        # Cloud coverage
        clouds = data.get("clouds", {}).get("all", 0)
        signals.append({
            "signal_id": f"{base_id}_clouds",
            "signal_type": "cloud_coverage",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": clouds,
            "severity": 1,  # Clouds alone are low severity
            "confidence": 0.92,
            "source": "openweathermap",
            "timestamp": now,
            "metadata": {"visibility_m": data.get("visibility", 10000)}
        })

        return signals

    def _simulate_weather(self, zone: Dict) -> List[Dict]:
        """
        Generate realistic simulated weather data for demo/testing.
        Based on Pakistan monsoon patterns (July-August peak).
        """
        import random
        now = datetime.utcnow()
        month = now.month
        base_id = f"sim_{zone['id']}_{now.strftime('%Y%m%d%H%M')}"
        timestamp = now.isoformat() + "Z"
        
        # Monsoon-aware simulation
        is_monsoon = month in [6, 7, 8, 9]
        
        # Temperature: 25-48°C depending on season and zone
        base_temp = 35 if is_monsoon else 20
        temp = base_temp + random.uniform(-5, 13) - (zone["elevation_m"] / 200)
        
        # Rainfall: much higher during monsoon
        rain_prob = 0.7 if is_monsoon else 0.15
        rain_value = random.uniform(5, 85) if random.random() < rain_prob else 0
        
        # Humidity: higher during monsoon
        humidity = random.uniform(60, 95) if is_monsoon else random.uniform(30, 60)
        
        # Wind
        wind = random.uniform(5, 45)
        
        signals = [
            {
                "signal_id": f"{base_id}_temp",
                "signal_type": "temperature",
                "zone_id": zone["id"], "zone_name": zone["name"],
                "lat": zone["lat"], "lng": zone["lng"],
                "value": round(temp, 1),
                "severity": self._temp_severity(temp),
                "confidence": 0.75,  # Lower confidence for simulated
                "source": "simulated",
                "timestamp": timestamp,
                "metadata": {"simulated": True}
            },
            {
                "signal_id": f"{base_id}_humidity",
                "signal_type": "humidity",
                "zone_id": zone["id"], "zone_name": zone["name"],
                "lat": zone["lat"], "lng": zone["lng"],
                "value": round(humidity, 1),
                "severity": self._humidity_severity(humidity),
                "confidence": 0.75,
                "source": "simulated",
                "timestamp": timestamp,
                "metadata": {"simulated": True}
            },
            {
                "signal_id": f"{base_id}_wind",
                "signal_type": "wind",
                "zone_id": zone["id"], "zone_name": zone["name"],
                "lat": zone["lat"], "lng": zone["lng"],
                "value": round(wind, 1),
                "severity": self._wind_severity(wind),
                "confidence": 0.75,
                "source": "simulated",
                "timestamp": timestamp,
                "metadata": {"simulated": True}
            },
        ]
        
        if rain_value > 0:
            signals.append({
                "signal_id": f"{base_id}_rain",
                "signal_type": "rainfall",
                "zone_id": zone["id"], "zone_name": zone["name"],
                "lat": zone["lat"], "lng": zone["lng"],
                "value": round(rain_value, 2),
                "severity": self._rain_severity(rain_value),
                "confidence": 0.75,
                "source": "simulated",
                "timestamp": timestamp,
                "metadata": {"simulated": True}
            })
        
        return signals

    # ─── Severity Calculators ──────────────────────────────────────────────────

    @staticmethod
    def _temp_severity(temp: float) -> int:
        """Temperature severity: danger starts at 40°C for heatstroke."""
        if temp >= 48: return 10
        if temp >= 45: return 9
        if temp >= 43: return 8
        if temp >= 41: return 7
        if temp >= 39: return 6
        if temp >= 37: return 5
        if temp >= 35: return 4
        if temp >= 30: return 2
        return 1

    @staticmethod
    def _rain_severity(rain_mm_per_hour: float) -> int:
        """Rainfall severity per hour (Pakistan flood thresholds)."""
        if rain_mm_per_hour >= 60: return 10  # Extremely heavy
        if rain_mm_per_hour >= 45: return 9
        if rain_mm_per_hour >= 35: return 8   # Very heavy
        if rain_mm_per_hour >= 25: return 7
        if rain_mm_per_hour >= 15: return 6   # Heavy
        if rain_mm_per_hour >= 10: return 5
        if rain_mm_per_hour >= 5: return 3    # Moderate
        if rain_mm_per_hour >= 2: return 2
        return 1

    @staticmethod
    def _humidity_severity(humidity: float) -> int:
        """High humidity amplifies heatstroke risk."""
        if humidity >= 90: return 7
        if humidity >= 80: return 5
        if humidity >= 70: return 3
        return 1

    @staticmethod
    def _wind_severity(wind_kph: float) -> int:
        """Wind speed severity."""
        if wind_kph >= 90: return 10
        if wind_kph >= 70: return 8
        if wind_kph >= 50: return 6
        if wind_kph >= 30: return 4
        return 1
