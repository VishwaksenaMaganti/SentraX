"""
SentraX RoadSegment and Route Health Data Models
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time
import uuid


class RoadSegment(BaseModel):
    id: str = Field(default_factory=lambda: f"seg_{uuid.uuid4().hex[:6]}")
    name: str = "Sector Road Segment"
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    length_meters: float = 250.0
    health_score: int = 88  # 0 to 100
    risk_score: int = 15    # 0 to 100
    health_band: str = "GOOD"  # GOOD, MODERATE, POOR, CRITICAL
    color_hex: str = "#22c55e" # Green, Yellow, Orange, Red
    recommended_speed_kmh: float = 80.0
    posted_speed_kmh: float = 80.0
    pothole_count: int = 0
    collision_count: int = 0
    wet: bool = False
    traffic_density: str = "NORMAL"
    active_hazards: List[str] = Field(default_factory=list)
    timestamp: float = Field(default_factory=time.time)


class RouteHealthRequest(BaseModel):
    origin: str = "Woxsen North Roundabout"
    destination: str = "Woxsen Hostels & Blue Embers"
    origin_lat: Optional[float] = 17.6638
    origin_lng: Optional[float] = 77.9272
    dest_lat: Optional[float] = 17.6596
    dest_lng: Optional[float] = 77.9248
    prefer_safest: bool = True


class RouteHealthResponse(BaseModel):
    session_id: str = Field(default_factory=lambda: f"rt_{uuid.uuid4().hex[:8]}")
    origin_name: str
    destination_name: str
    origin_coords: List[float] = Field(default_factory=lambda: [17.6638, 77.9272])
    dest_coords: List[float] = Field(default_factory=lambda: [17.6596, 77.9248])
    total_distance_km: float
    estimated_duration_mins: float
    overall_health_score: int  # 0 to 100
    overall_health_band: str   # GOOD, MODERATE, POOR, CRITICAL
    overall_risk_score: int
    recommended_speed_kmh: float
    posted_speed_kmh: float = 80.0
    measured_speed_kmh: float = 0.0
    road_anatomy_text: str = "Surface: Asphalt | Lanes: 2 | Shoulder: Concrete"
    road_surface_status: str = "Dry Asphalt"
    sensor_situation_summary: str = "Corridor Clear | Normal Operations"
    weather_temp_c: float = 26.0
    weather_aqi: int = 72
    google_maps_configured: bool = False
    pothole_count: int
    collision_zones_count: int
    wet_sections_count: int
    segments: List[RoadSegment] = Field(default_factory=list)
    route_polyline_points: List[List[float]] = Field(default_factory=list) # [[lat, lng], ...]
    vehicle_type_recommendation: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    is_mock_provider: bool = False
