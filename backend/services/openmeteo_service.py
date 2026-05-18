"""
Open-Meteo Service — FREE Weather & Historical Data (No API Key!)
==================================================================
https://open-meteo.com/ — completely free, no registration needed.
Provides:
  - Current weather
  - 7-day forecast
  - Historical data (any date range)
  - Flood risk indicators
  
This is our PRIMARY data source for the 30-day historical buffer
since OpenWeatherMap free tier only gives current + 5-day forecast.
"""
import httpx
import logging
import math
from datetime import datetime, timedelta
from typing import List, Dict
from config.settings import settings

logger = logging.getLogger("ciro.services.openmeteo")


class OpenMeteoService:
    """
    Free weather API — no key needed.
    Provides historical + forecast + flood data.
    """

    BASE_URL = "https://api.open-meteo.com/v1"
    FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def fetch_current_and_forecast(self, zone: Dict) -> List[Dict]:
        """
        Fetch current weather + 7-day forecast for a zone.
        Returns normalized Signal dicts.
        """
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/forecast",
                params={
                    "latitude": zone["lat"],
                    "longitude": zone["lng"],
                    "current": "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,wind_direction_10m,cloud_cover,surface_pressure",
                    "hourly": "temperature_2m,precipitation,rain,relative_humidity_2m,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum,wind_speed_10m_max",
                    "timezone": "Asia/Karachi",
                    "forecast_days": 7,
                }
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_current_forecast(data, zone)

        except Exception as e:
            logger.error(f"  ✗ OpenMeteo forecast failed for {zone['name']}: {e}")
            return []

    async def fetch_historical(self, zone: Dict, days_back: int = 30) -> List[Dict]:
        """
        Fetch historical weather data for the past N days.
        This fills our 30-day buffer with REAL data — no simulation needed.
        """
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            response = await self.client.get(
                f"{self.BASE_URL}/forecast",
                params={
                    "latitude": zone["lat"],
                    "longitude": zone["lng"],
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum,wind_speed_10m_max,relative_humidity_2m_max",
                    "timezone": "Asia/Karachi",
                    "start_date": start_date,
                    "end_date": end_date,
                }
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_historical(data, zone)

        except Exception as e:
            logger.error(f"  ✗ OpenMeteo historical failed for {zone['name']}: {e}")
            return []

    async def fetch_flood_forecast(self, zone: Dict) -> List[Dict]:
        """
        Fetch river discharge flood forecast from Open-Meteo Flood API.
        Uses GloFAS (Global Flood Awareness System) data.
        """
        try:
            response = await self.client.get(
                self.FLOOD_URL,
                params={
                    "latitude": zone["lat"],
                    "longitude": zone["lng"],
                    "daily": "river_discharge,river_discharge_mean,river_discharge_max",
                    "forecast_days": 30,  # 30-day flood forecast!
                }
            )
            response.raise_for_status()
            data = response.json()
            return self._parse_flood_forecast(data, zone)

        except Exception as e:
            logger.warning(f"  ⚠ OpenMeteo flood API failed for {zone['name']}: {e}")
            return []


    async def fetch_16day_daily_forecast(self, zone: Dict) -> List[Dict]:
        """
        Fetch structured 16-day daily forecast for Agent 3.
        Returns actual meteorological predictions from ECMWF/GFS models.
        
        This is the KEY data source for accurate short-term predictions.
        Open-Meteo uses ECMWF/GFS weather models — same as national met offices.
        
        Returns:
            List of 16 dicts: [{"day": 1, "temp_max": 43.2, "rain_mm": 0, "humidity": 45, "wind_kph": 12}, ...]
        """
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/forecast",
                params={
                    "latitude": zone["lat"],
                    "longitude": zone["lng"],
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,relative_humidity_2m_max,relative_humidity_2m_min,wind_speed_10m_max",
                    "timezone": "Asia/Karachi",
                    "forecast_days": 16,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            dates = daily.get("time", [])
            
            forecast_days = []
            for i, date_str in enumerate(dates):
                temp_max = (daily.get("temperature_2m_max") or [None])[i]
                temp_min = (daily.get("temperature_2m_min") or [None])[i]
                rain = (daily.get("precipitation_sum") or [0])[i] or 0
                humidity_max = (daily.get("relative_humidity_2m_max") or [60])[i] or 60
                humidity_min = (daily.get("relative_humidity_2m_min") or [30])[i] or 30
                wind = (daily.get("wind_speed_10m_max") or [0])[i] or 0
                
                forecast_days.append({
                    "day": i + 1,
                    "date": date_str,
                    "temp_max": round(temp_max, 1) if temp_max else None,
                    "temp_min": round(temp_min, 1) if temp_min else None,
                    "rain_mm": round(rain, 2),
                    "humidity_max": round(humidity_max, 1),
                    "humidity_min": round(humidity_min, 1),
                    "humidity_avg": round((humidity_max + humidity_min) / 2, 1),
                    "wind_kph": round(wind, 1),
                })
            
            logger.info(f"  16-day forecast for {zone['name']}: {len(forecast_days)} days, temps {[d['temp_max'] for d in forecast_days[:7]]}")
            return forecast_days
            
        except Exception as e:
            logger.error(f"  Failed to fetch 16-day forecast for {zone['name']}: {e}")
            return []


    # ─── Parsers ───────────────────────────────────────────────────────────────

    def _parse_current_forecast(self, data: Dict, zone: Dict) -> List[Dict]:
        """Parse current weather + forecast into signals."""
        now = datetime.utcnow().isoformat() + "Z"
        base_id = f"ometeo_{zone['id']}_{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        signals = []

        current = data.get("current", {})
        if not current:
            return signals

        # Temperature
        temp = current.get("temperature_2m", 0)
        signals.append({
            "signal_id": f"{base_id}_temp",
            "signal_type": "temperature",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": temp,
            "severity": self._temp_severity(temp),
            "confidence": 0.93,
            "source": "open_meteo",
            "timestamp": now,
            "metadata": {"unit": "celsius"}
        })

        # Humidity
        humidity = current.get("relative_humidity_2m", 0)
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
            "source": "open_meteo",
            "timestamp": now,
            "metadata": {}
        })

        # Rainfall
        rain = current.get("rain", 0) or current.get("precipitation", 0)
        if rain > 0:
            signals.append({
                "signal_id": f"{base_id}_rain",
                "signal_type": "rainfall",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": rain,
                "severity": self._rain_severity(rain),
                "confidence": 0.90,
                "source": "open_meteo",
                "timestamp": now,
                "metadata": {"unit": "mm"}
            })

        # Wind
        wind = current.get("wind_speed_10m", 0)
        signals.append({
            "signal_id": f"{base_id}_wind",
            "signal_type": "wind",
            "zone_id": zone["id"],
            "zone_name": zone["name"],
            "lat": zone["lat"],
            "lng": zone["lng"],
            "value": wind,
            "severity": self._wind_severity(wind),
            "confidence": 0.92,
            "source": "open_meteo",
            "timestamp": now,
            "metadata": {"direction_deg": current.get("wind_direction_10m", 0)}
        })

        # 7-day forecast summary (for Agent 3's short-term prediction)
        daily = data.get("daily", {})
        if daily and daily.get("precipitation_sum"):
            forecast_rain_total = sum(daily["precipitation_sum"][:7])
            forecast_max_temp = max(daily.get("temperature_2m_max", [0])[:7])
            signals.append({
                "signal_id": f"{base_id}_forecast",
                "signal_type": "forecast_7d",
                "zone_id": zone["id"],
                "zone_name": zone["name"],
                "lat": zone["lat"],
                "lng": zone["lng"],
                "value": forecast_rain_total,
                "severity": self._rain_severity(forecast_rain_total / 7),  # avg daily
                "confidence": 0.80,
                "source": "open_meteo",
                "timestamp": now,
                "metadata": {
                    "total_rain_7d_mm": forecast_rain_total,
                    "max_temp_7d": forecast_max_temp,
                    "type": "7_day_forecast",
                }
            })

        return signals

    def _parse_historical(self, data: Dict, zone: Dict) -> List[Dict]:
        """Parse daily historical data into signal records."""
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        signals = []

        for i, date_str in enumerate(dates):
            base_id = f"hist_{zone['id']}_{date_str}"
            timestamp = f"{date_str}T12:00:00Z"

            # Daily max temp
            max_temp = (daily.get("temperature_2m_max") or [None])[i]
            if max_temp is not None:
                signals.append({
                    "signal_id": f"{base_id}_temp",
                    "signal_type": "temperature",
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "lat": zone["lat"],
                    "lng": zone["lng"],
                    "value": max_temp,
                    "severity": self._temp_severity(max_temp),
                    "confidence": 0.95,
                    "source": "open_meteo_historical",
                    "timestamp": timestamp,
                    "metadata": {
                        "min_temp": (daily.get("temperature_2m_min") or [None])[i],
                        "type": "daily_historical",
                    }
                })

            # Daily precipitation
            rain = (daily.get("precipitation_sum") or [None])[i]
            if rain is not None and rain > 0:
                signals.append({
                    "signal_id": f"{base_id}_rain",
                    "signal_type": "rainfall",
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "lat": zone["lat"],
                    "lng": zone["lng"],
                    "value": rain,
                    "severity": self._rain_severity(rain / 24),  # convert daily to hourly equiv
                    "confidence": 0.95,
                    "source": "open_meteo_historical",
                    "timestamp": timestamp,
                    "metadata": {"unit": "mm/day", "type": "daily_historical"}
                })

            # Daily humidity
            humidity = (daily.get("relative_humidity_2m_max") or [None])[i]
            if humidity is not None:
                signals.append({
                    "signal_id": f"{base_id}_humidity",
                    "signal_type": "humidity",
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "lat": zone["lat"],
                    "lng": zone["lng"],
                    "value": humidity,
                    "severity": self._humidity_severity(humidity),
                    "confidence": 0.95,
                    "source": "open_meteo_historical",
                    "timestamp": timestamp,
                    "metadata": {"type": "daily_historical"}
                })

        return signals

    def _parse_flood_forecast(self, data: Dict, zone: Dict) -> List[Dict]:
        """Parse GloFAS river discharge flood forecast."""
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        discharge = daily.get("river_discharge", [])
        discharge_mean = daily.get("river_discharge_mean", [])
        signals = []

        for i, date_str in enumerate(dates):
            current_discharge = discharge[i] if i < len(discharge) else None
            mean_discharge = discharge_mean[i] if i < len(discharge_mean) else None

            if current_discharge is None:
                continue

            # Flood risk: how much above normal is the discharge?
            if mean_discharge and mean_discharge > 0:
                ratio = current_discharge / mean_discharge
            else:
                ratio = 1.0

            # ratio > 1.5 = elevated, > 2.0 = high, > 3.0 = extreme
            severity = min(10, max(1, int((ratio - 1) * 5)))

            if ratio > 1.3:  # Only report elevated discharge
                signals.append({
                    "signal_id": f"flood_{zone['id']}_{date_str}",
                    "signal_type": "flood_discharge",
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "lat": zone["lat"],
                    "lng": zone["lng"],
                    "value": round(current_discharge, 2),
                    "severity": severity,
                    "confidence": 0.85,
                    "source": "open_meteo_flood_glofas",
                    "timestamp": f"{date_str}T00:00:00Z",
                    "metadata": {
                        "mean_discharge": round(mean_discharge, 2) if mean_discharge else None,
                        "ratio_above_normal": round(ratio, 2),
                        "forecast_day": i + 1,
                        "type": "flood_forecast_30d",
                    }
                })

        return signals

    # ─── Severity Calculators ──────────────────────────────────────────────────

    @staticmethod
    def _temp_severity(temp: float) -> int:
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
        if rain_mm_per_hour >= 60: return 10
        if rain_mm_per_hour >= 45: return 9
        if rain_mm_per_hour >= 35: return 8
        if rain_mm_per_hour >= 25: return 7
        if rain_mm_per_hour >= 15: return 6
        if rain_mm_per_hour >= 10: return 5
        if rain_mm_per_hour >= 5: return 3
        if rain_mm_per_hour >= 2: return 2
        return 1

    @staticmethod
    def _humidity_severity(humidity: float) -> int:
        if humidity >= 90: return 7
        if humidity >= 80: return 5
        if humidity >= 70: return 3
        return 1

    @staticmethod
    def _wind_severity(wind_kph: float) -> int:
        if wind_kph >= 90: return 10
        if wind_kph >= 70: return 8
        if wind_kph >= 50: return 6
        if wind_kph >= 30: return 4
        return 1
