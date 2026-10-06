"""
SentraX Real-Time Computer Vision Pipeline
Streams frames from webcam/phone camera or generates synthetic scene feeds,
runs detection, tracking, pothole recognition, and exports fused CV telemetry metrics.
"""

import asyncio
import time
import base64
from typing import Dict, Any, List, Optional
import numpy as np

from software.backend.cv.detector import RoadObjectDetector
from software.backend.cv.tracker import CentroidTracker
from software.backend.cv.pothole_detector import PotholeDetector
from software.backend.schemas.hazards import VehicleTrack, PotholeRecord

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class CVPipeline:
    def __init__(self, camera_index: int = -1, use_simulation: bool = True):
        self.use_simulation = use_simulation
        self.camera_index = camera_index
        self.detector = RoadObjectDetector()
        self.tracker = CentroidTracker()
        self.pothole_detector = PotholeDetector()
        self.cap = None

        self.last_frame_jpeg: Optional[bytes] = None
        self.current_tracks: List[VehicleTrack] = []
        self.current_potholes: List[PotholeRecord] = []
        self.is_running = False

        # Simulation scene triggers
        self.sim_vehicles = 2
        self.sim_pothole = False
        self.sim_wrong_way = False
        self.sim_wet = False

    def start(self):
        self.is_running = True
        if not self.use_simulation and CV2_AVAILABLE and self.camera_index >= 0:
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                self.use_simulation = True

    def stop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None

    def process_step(self) -> Dict[str, Any]:
        """Runs one vision cycle and returns telemetry metadata."""
        if not self.is_running:
            return self.get_summary_stats()

        frame = None
        if not self.use_simulation and self.cap:
            ret, frame = self.cap.read()
            if not ret:
                frame = None

        if frame is None:
            # Fall back to synthetic road scene
            frame = self.detector.generate_synthetic_frame(
                vehicles=self.sim_vehicles,
                with_pothole=self.sim_pothole,
                with_wrong_way=self.sim_wrong_way,
                with_wet=self.sim_wet
            )

        # 1. Object detection & tracking
        detections = self.detector.detect(frame)
        self.current_tracks = self.tracker.update(detections)

        # 2. Pothole detection
        if self.sim_pothole or not self.use_simulation:
            potholes = self.pothole_detector.detect_in_frame(frame)
            if potholes:
                self.current_potholes = potholes

        # 3. Annotate frame for dashboard display
        annotated = frame.copy()
        for trk in self.current_tracks:
            x, y, w, h = trk.bbox
            color = (0, 0, 255) if trk.is_hazard else (0, 255, 0)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 2)
            label = f"#{trk.track_id} {trk.vehicle_class} {trk.estimated_speed_kmh}km/h (EST)"
            cv2.putText(annotated, label, (x, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # Annotate potholes
        for pot in self.current_potholes:
            cv2.putText(annotated, "POTHOLE AHEAD", (180, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)

        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
        self.last_frame_jpeg = buffer.tobytes()

        return self.get_summary_stats()

    def get_summary_stats(self) -> Dict[str, Any]:
        stopped = sum(1 for t in self.current_tracks if t.estimated_speed_kmh < 0.5)
        wrong = sum(1 for t in self.current_tracks if t.direction == "OPPOSITE")
        speeds = [t.estimated_speed_kmh for t in self.current_tracks if t.estimated_speed_kmh > 0]
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

        return {
            "vehicle_count": len(self.current_tracks),
            "pothole_count": len(self.current_potholes),
            "stopped_vehicle_count": stopped,
            "wrong_way_count": wrong,
            "wet_surface_detected": self.sim_wet,
            "average_speed_kmh": avg_speed,
            "tracks": [t.dict() for t in self.current_tracks],
            "potholes": [p.dict() for p in self.current_potholes]
        }
