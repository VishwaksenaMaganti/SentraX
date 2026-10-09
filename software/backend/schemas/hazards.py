"""
SentraX Hazard Zones, Pothole Records, and CV Track Models
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import time
import uuid


class HazardType(str, Enum):
    COLLISION = "COLLISION"
    POTHOLE = "POTHOLE"
    ANIMAL = "ANIMAL"
    PEDESTRIAN = "PEDESTRIAN"
    STALLED_VEHICLE = "STALLED_VEHICLE"
    WRONG_WAY_VEHICLE = "WRONG_WAY_VEHICLE"
    EMERGENCY_VEHICLE = "EMERGENCY_VEHICLE"
    WET_ROAD = "WET_ROAD"
    ROAD_OBSTRUCTION = "ROAD_OBSTRUCTION"
    VEHICLE_TOPPLED = "VEHICLE_TOPPLED"
    HIGH_RISK_ZONE = "HIGH_RISK_ZONE"


class HazardSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class HazardZone(BaseModel):
    id: str = Field(default_factory=lambda: f"hz_{uuid.uuid4().hex[:6]}")
    type: HazardType = HazardType.HIGH_RISK_ZONE
    title: str = "Active Hazard Zone"
    description: str = ""
    latitude: float = 12.9716  # Default prototype demo coords (Bengaluru Tech Corridor)
    longitude: float = 77.5946
    radius_meters: float = 50.0
    severity: HazardSeverity = HazardSeverity.MEDIUM
    confidence: float = 0.90
    created_at: float = Field(default_factory=time.time)
    expires_at: Optional[float] = None
    source: str = "FUSION"  # ESP32, ESP8266, CAMERA, FUSION, SIMULATED
    is_active: bool = True
    is_simulated: bool = False


class PotholeRecord(BaseModel):
    id: str = Field(default_factory=lambda: f"pot_{uuid.uuid4().hex[:6]}")
    latitude: float = 12.9720
    longitude: float = 77.5950
    severity: HazardSeverity = HazardSeverity.HIGH
    confidence: float = 0.88
    timestamp: float = Field(default_factory=time.time)
    image_reference: Optional[str] = None
    road_health_impact: int = -15  # Health penalty
    verified_by_cv: bool = True
    is_simulated: bool = False


from typing import Optional, Dict, Any, List, Union

class VehicleTrack(BaseModel):
    track_id: Union[int, str]
    tracking_label: str = "CAM-001"
    vehicle_class: str = "CAR"  # CAR, MOTORCYCLE, TRUCK, BUS, PEDESTRIAN, ANIMAL, EMERGENCY_VEHICLE
    confidence: float = 0.85
    bbox: List[int] = Field(default_factory=lambda: [0, 0, 0, 0])  # x, y, w, h
    direction: str = "FORWARD"  # FORWARD, OPPOSITE (WRONG-WAY), NORTH, SOUTH
    estimated_speed_kmh: float = 4.2  # Toy-car / uncalibrated CV speed
    is_calibrated_speed: bool = False  # Marked ESTIMATED unless calibrated
    lane: int = 1
    timestamp: float = Field(default_factory=time.time)
    is_hazard: bool = False
    hazard_reason: Optional[str] = None
    is_stationary: bool = False
    stationary_duration_seconds: float = 0.0
    is_toppled: bool = False
    trajectory_points: List[List[float]] = Field(default_factory=list)
