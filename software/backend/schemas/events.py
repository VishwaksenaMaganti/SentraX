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
    VEHICLE_DETECTED = "VEHICLE_DETECTED"
    SPEED = "SPEED"
    OVERSPEED = "OVERSPEED"
    CONGESTION = "CONGESTION"
    STALLED = "STALLED"
    WRONG_WAY = "WRONG_WAY"
    COLLISION = "COLLISION"
    POSSIBLE_COLLISION = "POSSIBLE_COLLISION"
    WET_ROAD = "WET_ROAD"
    HIGH_TEMP = "HIGH_TEMP"
    HIGH_HUMIDITY = "HIGH_HUMIDITY"
    EMERGENCY = "EMERGENCY"
    EMERGENCY_VEHICLE = "EMERGENCY_VEHICLE"
    OBSTRUCTION = "OBSTRUCTION"
    ROAD_OBSTRUCTION = "ROAD_OBSTRUCTION"
    TEMPERATURE = "TEMPERATURE"
    HUMIDITY = "HUMIDITY"
    SENSOR_CAMERA_MATCH = "SENSOR_CAMERA_MATCH"
    SENSOR_CAMERA_MISMATCH = "SENSOR_CAMERA_MISMATCH"
    ANIMAL = "ANIMAL"
    PEDESTRIAN = "PEDESTRIAN"
    NEAR_COLLISION = "NEAR_COLLISION"
    TRAFFIC_JAM = "TRAFFIC_JAM"
    VEHICLE_TOPPLED = "VEHICLE_TOPPLED"
    TOPPLED = "TOPPLED"


class EventSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MatchStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    SENSOR_ONLY = "SENSOR_ONLY"
    CAMERA_ONLY = "CAMERA_ONLY"
    MISMATCH = "MISMATCH"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class DetectionMode(str, Enum):
    FUSION = "FUSION"
    SENSOR = "SENSOR"
    CAMERA = "CAMERA"


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


class CameraEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"camevt_{uuid.uuid4().hex[:8]}")
    source: str = "camera"
    type: EventType = EventType.VEHICLE_DETECTED
    tracking_id: str = "CAM-001"
    timestamp: float = Field(default_factory=time.time)
    confidence: float = 0.90
    speed: float = 0.0
    direction: str = "FORWARD"
    position: Dict[str, int] = Field(default_factory=lambda: {"x": 0, "y": 0, "w": 0, "h": 0})
    severity: EventSeverity = EventSeverity.INFO
    title: str = "Camera Observation"
    description: str = ""
    is_hazard: bool = False
    is_candidate: bool = False
    candidate_age_seconds: float = 0.0


class SensorEvent(BaseModel):
    id: str = Field(default_factory=lambda: f"snrevt_{uuid.uuid4().hex[:8]}")
    source: str = "sensor"  # ESP32 / ESP8266
    type: EventType = EventType.NORMAL
    timestamp: float = Field(default_factory=time.time)
    confidence: float = 0.95
    speed: Optional[float] = None
    severity: EventSeverity = EventSeverity.INFO
    title: str = "Physical Sensor Observation"
    description: str = ""
    raw_data: Dict[str, Any] = Field(default_factory=dict)


class FusedEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: f"fuse_{uuid.uuid4().hex[:8]}")
    event_type: EventType = EventType.NORMAL
    timestamp: float = Field(default_factory=time.time)
    location: Optional[str] = "Main Corridor / Woxsen Sector 1"
    latitude: Optional[float] = 17.6638
    longitude: Optional[float] = 77.9272
    road_segment_id: Optional[str] = "seg-wxn-01"

    # Perception channels
    sensor_status: str = "NORMAL"
    camera_status: str = "NORMAL"
    match_status: MatchStatus = MatchStatus.CONFIRMED

    # Confidence scores
    sensor_confidence: float = 0.0
    camera_confidence: float = 0.0
    final_confidence: float = 0.0

    # Safety outputs
    severity: EventSeverity = EventSeverity.INFO
    risk_impact: int = 0
    recommended_speed_kmh: float = 80.0
    recommended_action: str = "NORMAL ADVISORY"
    final_action: str = "INFORMATIONAL"
    title: str = "Fused Multi-Modal Observation"
    description: str = ""
    is_simulated: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)
