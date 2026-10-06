"""
SentraX Global Configuration Settings
"""

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    PROJECT_NAME: str = "SentraX Intelligent Road Infrastructure"
    API_PREFIX: str = "/api"
    HOST: str = os.getenv("SENTRAX_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SENTRAX_PORT", 8000))
    DEBUG: bool = os.getenv("SENTRAX_DEBUG", "True").lower() == "true"

    # Hardware & Demonstration Defaults
    DEMO_OVERSPEED_LIMIT: float = 4.0   # km/h (toy car demonstration limit)
    NORMAL_RECOMMENDED_SPEED: float = 80.0
    CONGESTION_RECOMMENDED_SPEED: float = 60.0
    WET_ROAD_RECOMMENDED_SPEED: float = 40.0
    HIGH_TEMP_RECOMMENDED_SPEED: float = 35.0
    SENSOR_DISTANCE: float = 0.30       # meters between ultrasonic sensors

    # Time thresholds (seconds)
    CONGESTION_TIME_SECONDS: int = 5    # Mandatory change #1
    STALLED_TIME_SECONDS: int = 15
    WRONG_WAY_WINDOW_SECONDS: int = 15

    # Serial & BLE
    SERIAL_PORT_ESP32: str = os.getenv("SERIAL_PORT_ESP32", "COM3")
    SERIAL_PORT_ESP8266: str = os.getenv("SERIAL_PORT_ESP8266", "COM4")
    SERIAL_BAUDRATE: int = 9600

    # Google Maps Platform Key (securely loaded from .env)
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")


settings = Settings()
