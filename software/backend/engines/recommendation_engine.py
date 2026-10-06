"""
SentraX Intelligent Speed & Transit Recommendation Engine
Generates dynamic advisory recommendations based on multi-sensor telemetry,
hazard conditions, trip distance, and road health scores.
CRITICAL: Advisory recommendations are NOT legal speed limits.
"""

from typing import List, Tuple
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel
from software.backend.schemas.recommendations import SpeedRecommendation, VehicleTypeRecommendation


class RecommendationEngine:
    @staticmethod
    def get_recommended_speed(
        telemetry: CanonicalTelemetry,
        posted_limit: float = 80.0
    ) -> SpeedRecommendation:
        """
        Determines the adaptive SentraX Recommended Speed based on priority safety conditions:
          Priority 1: Wet Road -> 40 km/h
          Priority 2: High Temp -> 35 km/h
          Priority 3: Congestion -> 60 km/h
          Priority 4: Severe Hazard/Potholes/Stalled -> 30-50 km/h
          Priority 5: Normal -> 80 km/h (or posted limit)
        """
        reasons = []
        rec_speed = posted_limit

        # 1. Collision / Wrong-Way / Stalled in corridor
        if telemetry.collision:
            rec_speed = min(rec_speed, 20.0)
            reasons.append("Collision reported ahead - proceed at crawling speed")
        elif telemetry.wrong_way:
            rec_speed = min(rec_speed, 25.0)
            reasons.append("Wrong-way vehicle approaching - exercise extreme caution")
        elif telemetry.stalled_vehicle:
            rec_speed = min(rec_speed, 30.0)
            reasons.append("Stationary obstacle on road - slow down")

        # 2. Moisture / Wet Road (ESP32: 40 km/h)
        if telemetry.road_condition == RoadCondition.WET:
            rec_speed = min(rec_speed, 40.0)
            reasons.append("Wet road surface detected - wet traction recommendation 40 km/h")

        # 3. High Temperature (ESP32: 35 km/h)
        if telemetry.road_condition == RoadCondition.HIGH_TEMP or telemetry.temperature_c >= 30.0:
            rec_speed = min(rec_speed, 35.0)
            reasons.append("Elevated surface temperature - tire blowout mitigation 35 km/h")

        # 4. Congestion (ESP32: 60 km/h)
        if telemetry.traffic_level in (TrafficLevel.CONGESTED, TrafficLevel.STANDSTILL):
            rec_speed = min(rec_speed, 60.0)
            reasons.append("High traffic congestion - advisory speed 60 km/h")

        # 5. Potholes ahead
        if telemetry.cv_pothole_count > 0:
            pothole_speed = max(30.0, 50.0 - (telemetry.cv_pothole_count * 10))
            rec_speed = min(rec_speed, pothole_speed)
            reasons.append(f"Road surface potholes detected ({telemetry.cv_pothole_count}) - reduce speed")

        if not reasons:
            reasons.append("Clear roadway and optimal weather - normal advisory 80 km/h")

        return SpeedRecommendation(
            recommended_speed_kmh=round(rec_speed, 1),
            posted_speed_kmh=posted_limit,
            advisory_label="SentraX Recommended Speed",
            is_legal_limit=False,
            reasons=reasons
        )

    @staticmethod
    def get_vehicle_recommendation(
        trip_distance_km: float,
        traffic_level: TrafficLevel,
        road_condition: RoadCondition,
        potholes_count: int = 0
    ) -> VehicleTypeRecommendation:
        """
        Suggests optimal multimodal transit mode based on trip length, weather, and congestion.
        Configurable suggestion - does NOT restrict vehicle type.
        """
        # Rainy / Wet condition -> enclosed transit
        if road_condition == RoadCondition.WET:
            if trip_distance_km > 3.0:
                return VehicleTypeRecommendation(
                    recommended_type="CAR",
                    alternative_types=["PUBLIC_TRANSIT"],
                    trip_distance_km=trip_distance_km,
                    traffic_level=traffic_level.value,
                    road_condition=road_condition.value,
                    rationale="Wet road conditions prioritize enclosed vehicles for weather protection and safety."
                )
            else:
                return VehicleTypeRecommendation(
                    recommended_type="PUBLIC_TRANSIT",
                    alternative_types=["CAR"],
                    trip_distance_km=trip_distance_km,
                    traffic_level=traffic_level.value,
                    road_condition=road_condition.value,
                    rationale="Short wet trip; covered public transit or car recommended to avoid exposed cycling."
                )

        # Heavily congested traffic
        if traffic_level in (TrafficLevel.CONGESTED, TrafficLevel.STANDSTILL):
            if trip_distance_km <= 5.0:
                return VehicleTypeRecommendation(
                    recommended_type="BICYCLE",
                    alternative_types=["MOTORCYCLE", "PUBLIC_TRANSIT"],
                    trip_distance_km=trip_distance_km,
                    traffic_level=traffic_level.value,
                    road_condition=road_condition.value,
                    rationale="Heavy corridor congestion on short trip. Bicycle or light two-wheeler bypasses traffic gridlock."
                )
            else:
                return VehicleTypeRecommendation(
                    recommended_type="PUBLIC_TRANSIT",
                    alternative_types=["MOTORCYCLE", "CAR"],
                    trip_distance_km=trip_distance_km,
                    traffic_level=traffic_level.value,
                    road_condition=road_condition.value,
                    rationale="Corridor heavily congested. Rail / rapid public transit will offer significantly lower commute time."
                )

        # Default normal conditions
        if trip_distance_km <= 2.0:
            return VehicleTypeRecommendation(
                recommended_type="BICYCLE",
                alternative_types=["WALK", "CAR"],
                trip_distance_km=trip_distance_km,
                traffic_level=traffic_level.value,
                road_condition=road_condition.value,
                rationale="Short distance trip with clear road. Active mobility recommended."
            )
        else:
            return VehicleTypeRecommendation(
                recommended_type="CAR",
                alternative_types=["MOTORCYCLE", "PUBLIC_TRANSIT"],
                trip_distance_km=trip_distance_km,
                traffic_level=traffic_level.value,
                road_condition=road_condition.value,
                rationale="Moderate-to-long distance with clear traffic flow. Private car or personal transport recommended."
            )
