"""
SentraX Real-Time Camera Service
Handles Webcam / Phone-as-Webcam / RTSP / Video-File capture,
computes FPS, resolution, latency, overlays tracking HUD and virtual speed lines,
and serves low-latency MJPEG video streaming for the SentraX Command Center.
"""

import time
import os
import subprocess
import threading
from typing import Dict, Any, List, Optional, Tuple, Generator
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from software.backend.cv.detector import RoadObjectDetector
from software.backend.cv.tracker import CentroidTracker
from software.backend.cv.pothole_detector import PotholeDetector
from software.backend.cv.event_engine import CameraEventEngine
from software.backend.schemas.events import CameraEvent, EventType
from software.backend.schemas.hazards import VehicleTrack, PotholeRecord


class CameraService:
    def __init__(self, camera_source: Any = None):
        self.camera_source_str = str(camera_source if camera_source is not None else os.environ.get("CAMERA_SOURCE", "0"))
        self.detector = RoadObjectDetector()
        self.tracker = CentroidTracker()
        self.pothole_detector = PotholeDetector()
        self.event_engine = CameraEventEngine()

        self.cap: Optional[Any] = None
        self.is_connected = False
        self.is_running = False

        # Live Metrics
        self.fps = 0.0
        self.resolution = (640, 360)
        self.latency_ms = 0.0
        self.device_name = "Phone Camera / Webcam"
        self.detection_status = "ACTIVE"
        self.tracking_status = "STANDBY"

        # Frame and output cache
        self.last_frame_raw: Optional[np.ndarray] = None
        self.last_frame_annotated: Optional[np.ndarray] = None
        self.last_jpeg_bytes: Optional[bytes] = None
        self.current_tracks: List[VehicleTrack] = []
        self.current_potholes: List[PotholeRecord] = []
        self.current_camera_events: List[CameraEvent] = []

        # Threading
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Simulation triggers if camera offline
        self.sim_vehicles = 2
        self.sim_pothole = False
        self.sim_wrong_way = False
        self.sim_stalled = False
        self.sim_wet = False
        self.sim_collision = False
        self.sim_toppled = False

    _dshow_cache: Dict[int, str] = {}
    _dshow_cache_time: float = 0.0

    @classmethod
    def get_dshow_devices(cls, force_refresh: bool = False) -> Dict[int, str]:
        """Queries DirectShow device names on Windows via PowerShell COM helper."""
        now = time.time()
        if not force_refresh and cls._dshow_cache and (now - cls._dshow_cache_time < 12.0):
            return cls._dshow_cache

        device_map: Dict[int, str] = {}
        if os.name != 'nt':
            return device_map

        try:
            ps_script = os.path.join(os.path.dirname(__file__), "probe_dshow.ps1")
            if os.path.exists(ps_script):
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_script],
                    capture_output=True, text=True, timeout=3.0
                )
                if res.returncode == 0:
                    for line in res.stdout.strip().splitlines():
                        if "::" in line:
                            parts = line.split("::", 2)
                            if len(parts) >= 2 and parts[0].strip().isdigit():
                                device_map[int(parts[0].strip())] = parts[1].strip()
        except Exception:
            pass

        if device_map:
            cls._dshow_cache = device_map
            cls._dshow_cache_time = now

        return device_map or cls._dshow_cache

    @classmethod
    def list_available_cameras(cls, max_tested: int = 8, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Probes local system for accessible video capture devices with friendly names."""
        available: List[Dict[str, Any]] = []
        if not CV2_AVAILABLE:
            return available

        device_names = cls.get_dshow_devices(force_refresh=force_refresh)
        indices_to_test = sorted(list(set(list(device_names.keys()) + list(range(max_tested)))))

        for idx in indices_to_test:
            try:
                temp_cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                is_open = temp_cap.isOpened()
                if is_open:
                    ret, _ = temp_cap.read()
                    w = int(temp_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(temp_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    temp_cap.release()

                    raw_name = device_names.get(idx, f"Camera Device #{idx}")
                    is_phone = any(k in raw_name.lower() for k in ("iriun", "droidcam", "phone", "s24", "galaxy", "virtual camera"))
                    badge = "[Phone] " if is_phone else "[Camera] "
                    display_name = f"{badge}{raw_name} (Device #{idx})"

                    available.append({
                        "index": idx,
                        "source": str(idx),
                        "name": display_name,
                        "raw_name": raw_name,
                        "resolution": f"{w}x{h}" if w > 0 and h > 0 else "Ready",
                        "active": bool(ret),
                        "is_phone": is_phone
                    })
                elif idx in device_names:
                    # Device registered in Windows (e.g. phone driver ready/standby)
                    raw_name = device_names[idx]
                    is_phone = any(k in raw_name.lower() for k in ("iriun", "droidcam", "phone", "s24", "galaxy", "virtual camera"))
                    badge = "[Phone] " if is_phone else "[Camera] "
                    display_name = f"{badge}{raw_name} (Device #{idx} - Standby)"

                    available.append({
                        "index": idx,
                        "source": str(idx),
                        "name": display_name,
                        "raw_name": raw_name,
                        "resolution": "Standby",
                        "active": False,
                        "is_phone": is_phone
                    })
            except Exception:
                pass

        # Sort so phone cameras (like Iriun) are prioritized at the top
        available.sort(key=lambda x: (not x.get("is_phone", False), not x.get("active", False), x.get("index", 0)))
        return available

    def set_source(self, source_str: str) -> bool:
        """Dynamically reconfigures camera device (index, IP stream URL, or file)."""
        with self._lock:
            self.camera_source_str = str(source_str).strip()
            if self.cap:
                self.cap.release()
                self.cap = None
            self.is_connected = False
            return self._open_capture()

    def set_calibration(self, line_a_y: int, line_b_y: int, distance_meters: float):
        """Updates virtual speed calibration lines."""
        self.tracker.set_calibration(line_a_y, line_b_y, distance_meters)

    def set_demo_mode(self, enabled: bool):
        """Toggles 5s demo vs 15s production thresholds."""
        self.tracker.set_demo_mode(enabled)
        self.event_engine.set_demo_mode(enabled)

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._open_capture()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        with self._lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.is_connected = False

    def _open_capture(self) -> bool:
        if not CV2_AVAILABLE:
            return False

        src_val = str(self.camera_source_str).strip()
        src_lower = src_val.lower()

        devs = self.get_dshow_devices()
        resolved_idx: Optional[int] = None

        if src_lower in ("iriun", "iriun webcam", "iriun_webcam", "phone"):
            for idx, name in devs.items():
                if "iriun" in name.lower():
                    resolved_idx = idx
                    break
            if resolved_idx is None:
                resolved_idx = 4
        elif src_lower in ("s24", "galaxy"):
            for idx, name in devs.items():
                if "s24" in name.lower():
                    resolved_idx = idx
                    break
            if resolved_idx is None:
                resolved_idx = 2
        elif src_lower in ("tab", "tablet"):
            for idx, name in devs.items():
                if "tab" in name.lower():
                    resolved_idx = idx
                    break
            if resolved_idx is None:
                resolved_idx = 1
        elif src_lower in ("droidcam",):
            for idx, name in devs.items():
                if "droidcam" in name.lower():
                    resolved_idx = idx
                    break
            if resolved_idx is None:
                resolved_idx = 5
        elif src_lower in ("webcam", "default", "usb", "integrated"):
            resolved_idx = 0
        elif src_val.isdigit():
            resolved_idx = int(src_val)

        try:
            if resolved_idx is not None:
                if os.name == 'nt':
                    self.cap = cv2.VideoCapture(resolved_idx, cv2.CAP_DSHOW)
                else:
                    self.cap = cv2.VideoCapture(resolved_idx)

                friendly = devs.get(resolved_idx, f"Camera Device #{resolved_idx}")
                self.device_name = f"{friendly} (#{resolved_idx})"
            else:
                self.cap = cv2.VideoCapture(src_val)
                self.device_name = f"Stream ({src_val})"

            if self.cap and self.cap.isOpened():
                self.is_connected = True
                w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if w > 0 and h > 0:
                    self.resolution = (w, h)
                return True
        except Exception as e:
            print(f"[CameraService] Error opening capture '{self.camera_source_str}': {e}")

        self.is_connected = False
        return False

    def _capture_loop(self):
        prev_time = time.time()
        fps_smoothing = 0.9

        while not self._stop_event.is_set():
            t_start = time.time()
            frame = None

            # 1. Grab frame from hardware camera
            if self.cap and self.cap.isOpened():
                try:
                    ret, raw_frame = self.cap.read()
                    if ret and raw_frame is not None and raw_frame.size > 0:
                        frame = raw_frame
                        self.is_connected = True
                    else:
                        self.is_connected = False
                except Exception:
                    self.is_connected = False

            # 2. Fall back to high-fidelity synthetic road scene if hardware camera offline
            if frame is None:
                self.is_connected = False
                frame = self.detector.generate_synthetic_frame(
                    vehicles=self.sim_vehicles,
                    with_pothole=self.sim_pothole,
                    with_wrong_way=self.sim_wrong_way,
                    with_wet=self.sim_wet,
                    with_collision=self.sim_collision,
                    with_stalled=self.sim_stalled,
                    with_toppled=self.sim_toppled
                )

            # 3. Vision Detection & Tracking
            h, w = frame.shape[:2]
            self.resolution = (w, h)
            self.last_frame_raw = frame.copy()

            detections = self.detector.detect(frame)
            tracks = self.tracker.update(detections)

            # 4. Potholes
            potholes = []
            if self.sim_pothole or self.is_connected:
                potholes = self.pothole_detector.detect_in_frame(frame)

            # 5. Temporal Camera Event Generation
            camera_events = self.event_engine.evaluate_tracks_and_hazards(
                tracks=tracks,
                potholes=potholes,
                obstruction_detected=False
            )

            # 6. Annotate HUD and overlay on frame
            annotated = self._draw_hud(frame, tracks, potholes, camera_events)
            self.last_frame_annotated = annotated

            # 7. JPEG compression
            _, jpeg_buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            jpeg_bytes = jpeg_buf.tobytes()

            t_end = time.time()
            cycle_dt = max(0.001, t_end - t_start)
            frame_dt = max(0.001, t_end - prev_time)
            prev_time = t_end

            cur_fps = 1.0 / frame_dt
            self.fps = (self.fps * fps_smoothing) + (cur_fps * (1.0 - fps_smoothing))
            self.latency_ms = cycle_dt * 1000.0

            with self._lock:
                self.last_jpeg_bytes = jpeg_bytes
                self.current_tracks = tracks
                self.current_potholes = potholes
                self.current_camera_events = camera_events
                self.tracking_status = f"{len(tracks)} OBJECTS TRACKED" if tracks else "SEARCHING"

            # Frame rate throttle ~25-30 FPS
            time.sleep(max(0.01, 0.033 - cycle_dt))

    def _draw_hud(
        self,
        frame: np.ndarray,
        tracks: List[VehicleTrack],
        potholes: List[PotholeRecord],
        events: List[CameraEvent]
    ) -> np.ndarray:
        out = frame.copy()
        h, w = out.shape[:2]

        # Draw Calibrated Road Region of Interest (ROI) Guide
        if getattr(self.detector, "roi_enabled", False):
            rx1, ry1, rx2, ry2 = self.detector.get_roi_pixels(w, h)
            cv2.rectangle(out, (rx1, ry1), (rx2, ry2), (0, 180, 255), 1)
            cv2.putText(out, "ROAD ROI (ACTIVE)", (rx1 + 6, max(14, ry1 + 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 180, 255), 1)

        # Draw Calibrated Speed Virtual Measurement Lines (LINE A & LINE B)
        # Line A
        cv2.line(out, (0, self.tracker.line_a_y), (w, self.tracker.line_a_y), (0, 255, 128), 2)
        cv2.putText(out, f"LINE A [CALIBRATION START]", (15, max(20, self.tracker.line_a_y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 128), 1)

        # Line B
        cv2.line(out, (0, self.tracker.line_b_y), (w, self.tracker.line_b_y), (255, 200, 0), 2)
        cv2.putText(out, f"LINE B [CALIBRATION END: {self.tracker.line_distance_meters:.2f}m]",
                    (15, max(20, self.tracker.line_b_y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 200, 0), 1)

        # Draw Vehicle Bounding Boxes & Tracking Details
        for trk in tracks:
            x, y, bw, bh = trk.bbox
            color = (0, 220, 0)  # Default green
            status_text = f"{trk.tracking_label} | {trk.vehicle_class}"

            if getattr(trk, "is_toppled", False) or trk.hazard_reason == "VEHICLE_TOPPLED":
                color = (0, 0, 255)  # Red alert
                status_text = f"{trk.tracking_label} [TOPPLED OVER]"
            elif trk.hazard_reason == "STALLED_VEHICLE" or (trk.is_stationary and trk.stationary_duration_seconds >= self.tracker.stall_threshold_seconds):
                color = (0, 0, 255)  # Red alert
                status_text = f"{trk.tracking_label} [STALLED: {trk.stationary_duration_seconds:.1f}s]"
            elif trk.direction == "OPPOSITE":
                color = (0, 60, 255)  # Orange/Red alert
                status_text = f"{trk.tracking_label} [WRONG-WAY]"
            elif trk.is_stationary:
                color = (0, 200, 255)  # Amber stationary
                status_text = f"{trk.tracking_label} [STATIONARY {trk.stationary_duration_seconds:.1f}s]"

            # Bounding box
            cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)

            # Badge background
            badge_h = 28
            cv2.rectangle(out, (x, max(0, y - badge_h)), (x + max(140, bw), max(0, y)), (20, 20, 20), -1)
            cv2.putText(out, status_text, (x + 4, max(12, y - 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1)

            # Speed label (Calibrated vs Estimated)
            cal_tag = "CALIBRATED" if trk.is_calibrated_speed else "EST"
            speed_str = f"{trk.estimated_speed_kmh:.1f} km/h ({cal_tag}) | {trk.direction}"
            cv2.putText(out, speed_str, (x + 4, max(22, y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1)

            # Trajectory history trail
            pts = trk.trajectory_points
            for k in range(1, len(pts)):
                p1 = (int(pts[k - 1][0]), int(pts[k - 1][1]))
                p2 = (int(pts[k][0]), int(pts[k][1]))
                cv2.line(out, p1, p2, color, 1)

        # Draw Potholes
        for pot in potholes:
            cv2.putText(out, "POTHOLE AHEAD", (180, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 2)

        # Draw Top HUD Banner
        cv2.rectangle(out, (0, 0), (w, 24), (15, 15, 15), -1)
        src_tag = "PHONE WEBCAM" if self.is_connected else "SYNTHETIC SCENE (OFFLINE)"
        mode_tag = "DEMO (5s STALL)" if self.tracker.demo_mode else "PROD (15s STALL)"
        hud_str = f"FPS: {self.fps:.1f} | LATENCY: {self.latency_ms:.0f}ms | SOURCE: {src_tag} | {mode_tag}"
        cv2.putText(out, hud_str, (10, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 200), 1)

        # Active Alerts Overlay if any critical camera event
        active_crf = [e for e in events if e.severity.value in ("CRITICAL", "HIGH")]
        if active_crf:
            top_evt = active_crf[0]
            alert_bar_y = h - 26
            cv2.rectangle(out, (0, alert_bar_y), (w, h), (0, 0, 180), -1)
            cv2.putText(out, f"CAMERA ALERT: {top_evt.title} - {top_evt.description}", (15, h - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        return out

    def get_summary_stats(self) -> Dict[str, Any]:
        with self._lock:
            tracks_copy = list(self.current_tracks)
            potholes_copy = list(self.current_potholes)
            events_copy = list(self.current_camera_events)
            is_conn = self.is_connected
            fps_val = round(self.fps, 1)
            lat_val = round(self.latency_ms, 1)
            res_val = self.resolution

        stopped = sum(1 for t in tracks_copy if t.is_stationary or t.estimated_speed_kmh < 0.5)
        wrong = sum(1 for t in tracks_copy if t.direction == "OPPOSITE")
        toppled = sum(1 for t in tracks_copy if getattr(t, "is_toppled", False))
        speeds = [t.estimated_speed_kmh for t in tracks_copy if t.estimated_speed_kmh > 0]
        avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 0.0

        return {
            "camera_connected": is_conn,
            "camera_fps": fps_val,
            "camera_resolution": f"{res_val[0]}x{res_val[1]}",
            "camera_latency_ms": lat_val,
            "camera_source": self.camera_source_str,
            "device_name": self.device_name,
            "detection_status": "ACTIVE",
            "tracking_status": f"{len(tracks_copy)} ACTIVE OBJECTS" if tracks_copy else "NO VEHICLES",
            "vehicle_count": len(tracks_copy),
            "pothole_count": len(potholes_copy),
            "stopped_vehicle_count": stopped,
            "wrong_way_count": wrong,
            "toppled_vehicle_count": toppled,
            "average_speed_kmh": avg_speed,
            "demo_mode": self.tracker.demo_mode,
            "stall_threshold_seconds": self.tracker.stall_threshold_seconds,
            "road_roi": {
                "y_min": getattr(self.detector, "roi_y_min", 0.16),
                "y_max": getattr(self.detector, "roi_y_max", 0.84),
                "x_min": getattr(self.detector, "roi_x_min", 0.03),
                "x_max": getattr(self.detector, "roi_x_max", 0.97),
                "enabled": getattr(self.detector, "roi_enabled", True)
            },
            "speed_calibration": {
                "line_a_y": self.tracker.line_a_y,
                "line_b_y": self.tracker.line_b_y,
                "distance_meters": self.tracker.line_distance_meters
            },
            "tracks": [t.model_dump() for t in tracks_copy],
            "potholes": [p.model_dump() for p in potholes_copy],
            "camera_events": [e.model_dump() for e in events_copy]
        }

    def generate_mjpeg_stream(self) -> Generator[bytes, None, None]:
        """Yields continuous multipart JPEG stream for browser consumption."""
        while True:
            frame_bytes = None
            with self._lock:
                frame_bytes = self.last_jpeg_bytes

            if frame_bytes:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.035)
