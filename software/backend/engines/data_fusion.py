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
        cv_data: Dict[str, Any]
    ) -> Tuple[CanonicalTelemetry, List[CanonicalEvent]]:
        """
        Executes multi-modal fusion via SensorCameraFusionEngine.
        Converts FusedEvent records to CanonicalEvent for backward compatibility.
        """
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
