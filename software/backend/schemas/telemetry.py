"""
SentraX Canonical Telemetry & Device Models
Normalized data contracts for sensor observations and device health.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time


class DeviceSource(str, Enum):
    ESP32 = "ESP32"
    ESP8266 = "ESP8266"
    CAMERA = "CAMERA"
    FUSION = "FUSION"
    SIMULATED = "SIMULATED"


class ConnectionState(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    SIMULATED = "SIMULATED"


class RoadCondition(str, Enum):
    DRY = "DRY"
    WET = "WET"
    SLIPPERY = "SLIPPERY"
    HIGH_TEMP = "HIGH_TEMP"
    HUMID = "HUMID"


class TrafficLevel(str, Enum):
    LIGHT = "LIGHT"
    MODERATE = "MODERATE"
    CONGESTED = "CONGESTED"
    STANDSTILL = "STANDSTILL"


class DeviceStatus(BaseModel):
    device_id: str
    display_name: str
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    last_seen: float = Field(default_factory=time.time)
    rssi: Optional[int] = None
    firmware_version: str = "v2.4.0-sentrax"
    uptime_seconds: int = 0
    port_or_address: Optional[str] = None
    last_event: Optional[str] = "NORMAL"


class CanonicalTelemetry(BaseModel):
    device_id: str = "SENTRAX-CORE"
    timestamp: float = Field(default_factory=time.time)
    connection_state: ConnectionState = ConnectionState.DISCONNECTED

    # Speeds (km/h)
    measured_speed_kmh: float = 0.0
    recommended_speed_kmh: float = 80.0
    posted_speed_kmh: float = 80.0

    # Traffic
    traffic_count: int = 0
    traffic_level: TrafficLevel = TrafficLevel.LIGHT
    road_condition: RoadCondition = RoadCondition.DRY

    # Sensor booleans
    collision: bool = False
    wrong_way: bool = False
    stalled_vehicle: bool = False
    emergency_vehicle: bool = False

    # Environmental sensors
    temperature_c: float = 26.5
    humidity_pct: float = 55.0
    moisture_raw: int = 3100  # > 2000 is dry, < 2000 is wet

    # Raw sensor states
    ir_sensors: List[bool] = [False, False, False, False]  # IR1, IR2, IR3, IR4 (True if vehicle present)
    ultrasonic_state: Dict[str, Any] = Field(
        default_factory=lambda: {"us1_active": False, "us2_active": False, "measuring": False}
    )
    sound_active: bool = False
    rfid_active: bool = False
    night_mode: bool = False

    # Computer Vision observations
    cv_vehicle_count: int = 0
    cv_pothole_count: int = 0
    hazard_count: int = 0

    # Risk Analysis
    risk_score: int = 0  # 0 to 100
    risk_reasons: List[str] = Field(default_factory=lambda: ["System in Standby: Awaiting ESP32 & ESP8266 pairing"])

    # Metadata
    source: DeviceSource = DeviceSource.FUSION
    is_simulated: bool = False

    # Dual-Module Hardware Gate
    esp32_connected: bool = False
    esp8266_connected: bool = False
    both_modules_connected: bool = False
    hardware_standby: bool = True
