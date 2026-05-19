"""
CIRO Configuration & Settings
"""
from pydantic_settings import BaseSettings
from typing import List, Dict
import os

# Absolute path to backend/.env — works regardless of where uvicorn is launched from
_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


class Settings(BaseSettings):
    """Application settings — loaded from environment variables."""

    # Environment
    ENVIRONMENT: str = "development"

    # OpenWeatherMap API
    OPENWEATHER_API_KEY: str = ""  # Get from https://openweathermap.org/api
    OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5"

    # Google Maps API
    GOOGLE_MAPS_API_KEY: str = ""  # Get from https://console.cloud.google.com

    # Google Gemini (GeoGemma) API
    GOOGLE_API_KEY: str = ""  # Gemini API key for satellite image analysis
    GEMINI_API_KEY: str = ""  # Alias used in .env

    # Google Flood Hub API
    GOOGLE_FLOODHUB_API_KEY: str = ""  # Apply: https://developers.google.com/flood-forecasting

    # Google Earth Engine
    GEE_PROJECT_ID: str = ""  # GEE project ID
    GEE_SERVICE_ACCOUNT: str = ""  # Service account email
    GEE_CREDENTIALS_PATH: str = ""  # Path to service account JSON key

    # Firebase
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_PATH: str = ""  # Path to service account JSON

    # Agent 2 ↔ Agent 3 internal API URL
    AGENT2_BASE_URL: str = "http://localhost:8000"

    # Agent 2 Config
    FETCH_INTERVAL_MINUTES: int = 15  # How often to poll APIs
    SIGNAL_BUFFER_DAYS: int = 30  # Rolling buffer size
    SEVERITY_THRESHOLD: float = 0.7  # Alert threshold
    RISK_ALERT_THRESHOLD: float = 0.30
    DEMO_MODE: bool = False
    DEMO_FETCH_INTERVAL_SECONDS: int = 300

    # Orchestrator + Debater Config
    ORCHESTRATOR_INTERVAL_HOURS: int = 2
    DEBATE_LLM_MODEL: str = "gemini-2.5-flash-lite"
    DEBATE_TEMPERATURE: float = 0.3

    # Monitored Zones (Pakistan-focused for hackathon)
    ZONES: List[Dict] = [
        {
            "id": "islamabad-g10",
            "name": "G-10, Islamabad",
            "lat": 33.6844,
            "lng": 73.0479,
            "province": "Federal",
            "elevation_m": 507,
            "drainage_capacity": 0.6,
            "population_density": 2850,
        },
        {
            "id": "lahore-city",
            "name": "Lahore City",
            "lat": 31.5204,
            "lng": 74.3587,
            "province": "Punjab",
            "elevation_m": 217,
            "drainage_capacity": 0.4,
            "population_density": 6300,
        },
        {
            "id": "karachi-south",
            "name": "Karachi South",
            "lat": 24.8607,
            "lng": 67.0011,
            "province": "Sindh",
            "elevation_m": 10,
            "drainage_capacity": 0.3,
            "population_density": 14000,
        },
        {
            "id": "peshawar-city",
            "name": "Peshawar City",
            "lat": 34.0151,
            "lng": 71.5249,
            "province": "KPK",
            "elevation_m": 331,
            "drainage_capacity": 0.5,
            "population_density": 3200,
        },
        {
            "id": "multan-city",
            "name": "Multan City",
            "lat": 30.1575,
            "lng": 71.5249,
            "province": "Punjab",
            "elevation_m": 122,
            "drainage_capacity": 0.35,
            "population_density": 4500,
        },
        {
            "id": "jacobabad-city",
            "name": "Jacobabad City",
            "lat": 28.2810,
            "lng": 68.4376,
            "province": "Sindh",
            "elevation_m": 55,
            "drainage_capacity": 0.25,
            "population_density": 2100,
        },
        {
            "id": "sukkur-city",
            "name": "Sukkur City",
            "lat": 27.7052,
            "lng": 68.8574,
            "province": "Sindh",
            "elevation_m": 66,
            "drainage_capacity": 0.3,
            "population_density": 3800,
        },
        {
            "id": "quetta-city",
            "name": "Quetta City",
            "lat": 30.1798,
            "lng": 66.9750,
            "province": "Balochistan",
            "elevation_m": 1680,
            "drainage_capacity": 0.35,
            "population_density": 1800,
        },
    ]

    class Config:
        env_file = _ENV_FILE
        env_file_encoding = "utf-8"


settings = Settings()
