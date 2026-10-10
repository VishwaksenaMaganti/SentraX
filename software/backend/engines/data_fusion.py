"""
SentraX Multi-Modal Sensor + Vision Data Fusion Engine
Interfaces with SensorCameraFusionEngine to correlate physical microcontrollers
with Camera Computer Vision observations.
"""

from typing import Dict, Any, List, Optional, Tuple
from software.backend.schemas.telemetry import CanonicalTelemetry
from software.backend.schemas.events import CanonicalEvent
from software.backend.engines.fusion_engine import fusion_engine, SensorCameraFusionEngine


class DataFusionEngine:
    @staticmethod
    def fuse_telemetry_and_cv(
        hardware_telemetry: CanonicalTelemetry,
        cv_data: Dict[str, Any],
        allow_cv_speed_fallback: bool = True
    ) -> Tuple[CanonicalTelemetry, List[CanonicalEvent]]:
        """
        Executes multi-modal fusion via SensorCameraFusionEngine.
        Converts FusedEvent records to CanonicalEvent for backward compatibility.
        """
        if not allow_cv_speed_fallback:
            # A simulated camera must not stand in for the ultrasonic speed reading
            cv_data = {**cv_data, "average_speed_kmh": 0.0}
        fused_tele, fused_events = fusion_engine.fuse(hardware_telemetry, cv_data)

        # Convert FusedEvent objects to CanonicalEvent list
        canonical_events: List[CanonicalEvent] = []
        for fe in fused_events:
            ce = CanonicalEvent(
                event_id=fe.event_id,
                timestamp=fe.timestamp,
                source=f"FUSION_{fusion_engine.detection_mode.value}",
                type=fe.event_type,
                severity=fe.severity,
                confidence=fe.final_confidence,
                title=fe.title,
                description=fe.description,
                payload={
                    "match_status": fe.match_status.value,
                    "sensor_status": fe.sensor_status,
                    "camera_status": fe.camera_status,
                    "risk_impact": fe.risk_impact,
                    "recommended_speed_kmh": fe.recommended_speed_kmh
                }
            )
            canonical_events.append(ce)

        return fused_tele, canonical_events

    @staticmethod
    def first_fresh(events: List[CanonicalEvent]) -> Optional[CanonicalEvent]:
        """The first event of this cycle that started a new episode (repeats are not re-broadcast)."""
        for ev in events:
            if ev.event_id in fusion_engine.fresh_event_ids:
                return ev
        return None
