"""
SentraX Real-Time Computer Vision Pipeline
Wraps and interfaces CameraService, Detector, Tracker, and EventEngine
to provide live CV telemetry, tracking metrics, and streaming to SentraX backend.
"""

from typing import Dict, Any, List, Optional
from software.backend.cv.camera_service import CameraService
from software.backend.schemas.hazards import VehicleTrack
from software.backend.schemas.events import CameraEvent


class CVPipeline:
    def __init__(self, camera_index: Any = None, use_simulation: bool = False):
        self.camera_service = CameraService(camera_source=camera_index)

    @property
    def is_running(self) -> bool:
        return self.camera_service.is_running

    @property
    def last_frame_jpeg(self) -> Optional[bytes]:
        return self.camera_service.last_jpeg_bytes

    @property
    def current_tracks(self) -> List[VehicleTrack]:
        return self.camera_service.current_tracks

    @property
    def current_camera_events(self) -> List[CameraEvent]:
        return self.camera_service.current_camera_events

    def start(self):
        self.camera_service.start()

    def stop(self):
        self.camera_service.stop()

    def process_step(self) -> Dict[str, Any]:
        """Returns the latest vision telemetry snapshot."""
        return self.camera_service.get_summary_stats()

    def get_summary_stats(self) -> Dict[str, Any]:
        return self.camera_service.get_summary_stats()

    def set_source(self, source_str: str) -> bool:
        return self.camera_service.set_source(source_str)

    def set_calibration(self, line_a_y: int, line_b_y: int, distance_meters: float):
        self.camera_service.set_calibration(line_a_y, line_b_y, distance_meters)

    def set_demo_mode(self, enabled: bool):
        self.camera_service.set_demo_mode(enabled)

    def set_detector_backend(self, backend: str) -> bool:
        return self.camera_service.set_detector_backend(backend)

    def get_vehicle_log(self) -> Dict[str, Any]:
        return self.camera_service.get_vehicle_log()

    def get_vehicle_snapshot(self, label: str) -> Optional[bytes]:
        return self.camera_service.vehicle_log.snapshot(label)

    def generate_mjpeg_stream(self):
        return self.camera_service.generate_mjpeg_stream()
