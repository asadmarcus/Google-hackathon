"""
CIRO Configuration & Settings
"""
from pydantic_settings import BaseSettings
from typing import List, Dict
import os


class Settings(BaseSettings):
    """Application settings — loaded from environment variables."""

    # Environment
    ENVIRONMENT: str = "development"

    # OpenWeatherMap API
    OPENWEATHER_API_KEY: str = ""  # Get from https://openweathermap.org/api
    OPENWEATHER_BASE_URL: str = "https://api.openweathermap.org/data/2.5"

    # Google Maps API
    GOOGLE_MAPS_API_KEY: str = ""  # Get from https://console.cloud.google.com

    # Firebase
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CREDENTIALS_PATH: str = ""  # Path to service account JSON

    # Agent 2 Config
    FETCH_INTERVAL_MINUTES: int = 15  # How often to poll APIs
    SIGNAL_BUFFER_DAYS: int = 30  # Rolling buffer size
    SEVERITY_THRESHOLD: float = 0.7  # Alert threshold

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
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
