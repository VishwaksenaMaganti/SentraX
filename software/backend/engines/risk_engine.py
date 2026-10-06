"""
SentraX Road Risk Score Engine
Calculates normalized 0-100 Road Risk Score based on real-time embedded sensor readings,
computer vision detections, environmental conditions, and nearby hazard zones.
NOTE: This is SentraX's prototype risk scoring model, not an official government standard.
"""

from typing import Dict, Any, List, Tuple
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel


class RoadRiskEngine:
    """
    Computes a composite risk score (0-100) from physical sensor telemetry and CV inputs.
    Weights:
      Collision:         +50
      Wrong Way:         +40
      Stalled Vehicle:   +25
      Near Collision:    +25
      Overspeed:         +20
      Hazard Proximity:  +20
      Pothole Detected:  +15
      Wet Road:          +15
      Congestion:        +10
      High Temperature:  +5
      High Humidity:     +5
    """

    @staticmethod
    def calculate_risk(telemetry: CanonicalTelemetry) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []

        # 1. Critical safety incidents
        if telemetry.collision:
            score += 50
            reasons.append("Collision detected by acoustic/impact sensor (+50)")

        if telemetry.wrong_way:
            score += 40
            reasons.append("Wrong-way vehicle detected entering section (+40)")

        if telemetry.stalled_vehicle:
            score += 25
            reasons.append("Stalled/stationary vehicle blocking traffic lane (+25)")

        # 2. Overspeeding check
        # Check against toy-car low speed demo or normal posted recommendation
        if (telemetry.measured_speed_kmh > 4.0 and telemetry.is_simulated) or \
           (telemetry.measured_speed_kmh > telemetry.recommended_speed_kmh + 5.0 and not telemetry.is_simulated):
            score += 20
            reasons.append(f"Vehicle overspeed detected: {telemetry.measured_speed_kmh:.1f} km/h (+20)")

        # 3. Environmental conditions
        if telemetry.road_condition == RoadCondition.WET:
            score += 15
            reasons.append("Wet road surface detected; reduced traction (+15)")

        if telemetry.road_condition == RoadCondition.HIGH_TEMP or telemetry.temperature_c >= 30.0:
            score += 5
            reasons.append(f"Elevated road temperature ({telemetry.temperature_c:.1f}°C) (+5)")

        if telemetry.humidity_pct >= 80.0:
            score += 5
            reasons.append(f"High atmospheric humidity ({telemetry.humidity_pct:.0f}%) (+5)")

        # 4. Traffic conditions
        if telemetry.traffic_level in (TrafficLevel.CONGESTED, TrafficLevel.STANDSTILL):
            score += 10
            reasons.append("High traffic congestion detected on IR sensors (+10)")

        # 5. Computer Vision & Hazard factors
        if telemetry.cv_pothole_count > 0:
            score += min(30, telemetry.cv_pothole_count * 15)
            reasons.append(f"{telemetry.cv_pothole_count} surface pothole(s) verified ahead (+{min(30, telemetry.cv_pothole_count * 15)})")

        if telemetry.hazard_count > 0:
            score += min(30, telemetry.hazard_count * 15)
            reasons.append(f"{telemetry.hazard_count} active hazard zone(s) in proximity (+{min(30, telemetry.hazard_count * 15)})")

        # Clamp between 0 and 100
        clamped_score = max(0, min(100, score))

        if not reasons:
            reasons.append("Road clear; normal conditions")

        return clamped_score, reasons
