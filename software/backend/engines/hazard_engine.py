"""
SentraX Hazard Zone Management & Proximity Warning Engine
"""

import math
import time
from typing import List, Dict, Any, Optional, Tuple
from software.backend.schemas.hazards import HazardZone, HazardType, HazardSeverity
from software.backend.database.models import save_hazard_zone, get_active_hazards


class HazardEngine:
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Computes Great-Circle distance between two coordinates in meters."""
        R = 6371000.0  # Earth radius in meters
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2.0) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return R * c

    @staticmethod
    def check_vehicle_proximity(
        vehicle_lat: float,
        vehicle_lon: float,
        active_hazards: List[Dict[str, Any]],
        buffer_meters: float = 20.0
    ) -> List[Dict[str, Any]]:
        """
        Detects if a vehicle is approaching or inside any active hazard zone.
        Returns a list of proximity warnings with distance and recommended action.
        """
        warnings = []
        for h in active_hazards:
            h_lat = float(h["latitude"])
            h_lon = float(h["longitude"])
            radius = float(h.get("radius_meters", 50.0))

            dist = HazardEngine.haversine_distance(vehicle_lat, vehicle_lon, h_lat, h_lon)

            if dist <= (radius + buffer_meters):
                warnings.append({
                    "hazard_id": h["id"],
                    "type": h["type"],
                    "title": h["title"],
                    "distance_meters": round(dist, 1),
                    "is_inside": dist <= radius,
                    "severity": h.get("severity", "MEDIUM"),
                    "alert_message": f"CAUTION: {h['title']} {int(dist)}m ahead! Reduce speed."
                })
        return warnings

    @staticmethod
    def create_zone_from_event(
        event_type: str,
        lat: float = 12.9716,
        lon: float = 77.5946,
        source: str = "ESP32",
        ttl_seconds: int = 120
    ) -> HazardZone:
        """Instantiates an active hazard zone from a detected physical or CV event."""
        now = time.time()
        type_mapping = {
            "COLLISION": (HazardType.COLLISION, "Accident Zone Ahead", HazardSeverity.CRITICAL, 60.0),
            "WRONG_WAY": (HazardType.WRONG_WAY_VEHICLE, "Wrong-Way Vehicle Reported", HazardSeverity.CRITICAL, 80.0),
            "STALLED": (HazardType.STALLED_VEHICLE, "Stationary Vehicle Hazard", HazardSeverity.MEDIUM, 40.0),
            "POTHOLE": (HazardType.POTHOLE, "Severe Pothole Cluster", HazardSeverity.HIGH, 25.0),
            "ANIMAL": (HazardType.ANIMAL, "Animal Crossing Observed", HazardSeverity.MEDIUM, 40.0),
            "WET_ROAD": (HazardType.WET_ROAD, "Slippery Road Surface", HazardSeverity.LOW, 100.0),
        }

        htype, title, sev, rad = type_mapping.get(
            event_type,
            (HazardType.HIGH_RISK_ZONE, f"Hazard Alert: {event_type}", HazardSeverity.MEDIUM, 50.0)
        )

        zone = HazardZone(
            type=htype,
            title=title,
            description=f"Auto-generated hazard perimeter from {source} sensor confirmation",
            latitude=lat,
            longitude=lon,
            radius_meters=rad,
            severity=sev,
            confidence=0.92,
            created_at=now,
            expires_at=now + ttl_seconds,
            source=source,
            is_active=True,
            is_simulated=False
        )
        save_hazard_zone(zone)
        return zone
