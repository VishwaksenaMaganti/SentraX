"""
SentraX Canonical Event Model
Standardized event contracts for detections, incidents, and warnings.
"""

from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import time
import uuid


class EventType(str, Enum):
    NORMAL = "NORMAL"
    COLLISION = "COLLISION"
    WRONG_WAY = "WRONG_WAY"
    OVERSPEED = "OVERSPEED"
    CONGESTION = "CONGESTION"
    STALLED = "STALLED"
    WET_ROAD = "WET_ROAD"
    HIGH_TEMP = "HIGH_TEMP"
    HIGH_HUMIDITY = "HIGH_HUMIDITY"
    EMERGENCY = "EMERGENCY"
    POTHOLE = "POTHOLE"
    ANIMAL = "ANIMAL"
    PEDESTRIAN = "PEDESTRIAN"
    NEAR_COLLISION = "NEAR_COLLISION"
    TRAFFIC_JAM = "TRAFFIC_JAM"


class EventSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class CanonicalEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:8]}")
    timestamp: float = Field(default_factory=time.time)
    source: str = "ESP32"  # ESP32, ESP8266, CAMERA, FUSION, SIMULATION
    type: EventType = EventType.NORMAL
    severity: EventSeverity = EventSeverity.INFO
    confidence: float = 1.0  # 0.0 to 1.0
    title: str = "System Event"
    description: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    is_simulated: bool = False
