"""
SentraX Speed & Vehicle Type Recommendation Schemas
"""

from typing import List, Optional
from pydantic import BaseModel, Field
import time


class SpeedRecommendation(BaseModel):
    recommended_speed_kmh: float = 80.0
    posted_speed_kmh: float = 80.0
    advisory_label: str = "SentraX Recommended Speed"
    is_legal_limit: bool = False  # NEVER call it a legal speed limit!
    reasons: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class VehicleTypeRecommendation(BaseModel):
    recommended_type: str = "CAR"  # CAR, MOTORCYCLE, BICYCLE, PUBLIC_TRANSIT, WALK
    alternative_types: List[str] = Field(default_factory=list)
    trip_distance_km: float = 5.0
    traffic_level: str = "MODERATE"
    road_condition: str = "DRY"
    rationale: str = "Standard transit recommended"
    timestamp: float = Field(default_factory=time.time)
