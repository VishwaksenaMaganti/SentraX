"""
SentraX Multi-Modal Sensor + Vision Data Fusion Engine
Fuses embedded microcontrollers (ESP32 IR, Ultrasonic, Sound, Moisture, DHT11, RFID)
with Phone-Camera Computer Vision observations using confidence weighting.
"""

from typing import Dict, Any, List, Optional, Tuple
import time
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel, DeviceSource
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.recommendation_engine import RecommendationEngine


class DataFusionEngine:
    """
    Synthesizes independent perception channels into a unified road-safety assessment.
    Weights each source:
      - Embedded Hardware (IR, Sound, Moisture, Ultrasonic): Direct physical ground-truth.
      - Computer Vision (Camera): Contextual, visual confirmation, spatial trajectory.
    """

    @staticmethod
    def fuse_telemetry_and_cv(
        hardware_telemetry: CanonicalTelemetry,
        cv_data: Dict[str, Any],
        allow_cv_speed_fallback: bool = True
    ) -> Tuple[CanonicalTelemetry, List[CanonicalEvent]]:
        """
        Takes the latest hardware telemetry and CV pipeline metrics, producing
        a fused canonical telemetry object and newly validated high-confidence events.
        """
        fused = hardware_telemetry.model_copy(deep=True)
        new_events: List[CanonicalEvent] = []
        now = time.time()

        cv_vehicles = cv_data.get("vehicle_count", 0)
        cv_potholes = cv_data.get("pothole_count", 0)
        cv_stopped_vehicles = cv_data.get("stopped_vehicle_count", 0)
        cv_opposite_dir = cv_data.get("wrong_way_count", 0)
        cv_is_wet_surface = cv_data.get("wet_surface_detected", False)
        cv_estimated_speed = cv_data.get("average_speed_kmh", None)

        fused.cv_vehicle_count = cv_vehicles
        fused.cv_pothole_count = cv_potholes
        fused.source = DeviceSource.FUSION

        # 1. Vehicle presence fusion (IR + Camera)
        ir_occupied_count = sum(1 for val in fused.ir_sensors if val)
        if ir_occupied_count > 0 and cv_vehicles > 0:
            # Both agree -> High confidence vehicle count
            fused.traffic_count = max(ir_occupied_count, cv_vehicles)
            if fused.traffic_count >= 2:
                fused.traffic_level = TrafficLevel.CONGESTED
        elif ir_occupied_count > 0:
            fused.traffic_count = ir_occupied_count
        elif cv_vehicles > 0:
            fused.traffic_count = cv_vehicles

        # 2. Collision fusion (Sound Sensor + Stopped vehicle CV)
        if fused.collision and cv_stopped_vehicles > 0:
            # Multi-modal agreement -> High confidence collision
            event = CanonicalEvent(
                source="FUSION",
                type=EventType.COLLISION,
                severity=EventSeverity.CRITICAL,
                confidence=0.98,
                title="HIGH CONFIDENCE COLLISION",
                description="Acoustic impact sensor and camera visual detection confirmed stopped incident",
                payload={"hardware_sound": True, "cv_stopped": cv_stopped_vehicles}
            )
            new_events.append(event)
        elif fused.collision:
            event = CanonicalEvent(
                source="ESP32",
                type=EventType.COLLISION,
                severity=EventSeverity.CRITICAL,
                confidence=0.85,
                title="Collision Detected (Acoustic)",
                description="Sound sensor threshold triggered",
                payload={"hardware_sound": True}
            )
            new_events.append(event)

        # 3. Wrong-way fusion (IR sequence + CV trajectory)
        if fused.wrong_way and cv_opposite_dir > 0:
            event = CanonicalEvent(
                source="FUSION",
                type=EventType.WRONG_WAY,
                severity=EventSeverity.CRITICAL,
                confidence=0.95,
                title="HIGH CONFIDENCE WRONG WAY",
                description="IR4->IR3 reverse sequence and camera motion tracking confirmed wrong-way vehicle",
                payload={"ir_reverse": True, "cv_wrong_way": cv_opposite_dir}
            )
            new_events.append(event)

        # 4. Wet surface fusion (Moisture Sensor + CV reflection/glare)
        if fused.road_condition == RoadCondition.WET and cv_is_wet_surface:
            event = CanonicalEvent(
                source="FUSION",
                type=EventType.WET_ROAD,
                severity=EventSeverity.WARNING,
                confidence=0.94,
                title="HIGH CONFIDENCE WET ROAD",
                description="Moisture sensor (< 2000) and camera surface glare verified wet roadway",
                payload={"moisture_raw": fused.moisture_raw, "cv_glare": True}
            )
            new_events.append(event)

        # 5. Speed estimation fallback if hardware is idle but CV sees vehicle
        if allow_cv_speed_fallback and fused.measured_speed_kmh == 0.0 and cv_estimated_speed is not None:
            fused.measured_speed_kmh = cv_estimated_speed

        # 6. Recompute Road Risk Score and SentraX Speed Recommendation
        risk_score, reasons = RoadRiskEngine.calculate_risk(fused)
        fused.risk_score = risk_score
        fused.risk_reasons = reasons

        rec_obj = RecommendationEngine.get_recommended_speed(fused, fused.posted_speed_kmh)
        fused.recommended_speed_kmh = rec_obj.recommended_speed_kmh

        fused.timestamp = now
        return fused, new_events
