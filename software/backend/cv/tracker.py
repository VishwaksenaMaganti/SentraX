"""
SentraX Multi-Object Vehicle Tracker
Maintains persistent track IDs (CAM-001, CAM-002, ...), trajectory analysis,
calibrated speed estimation with virtual measurement lines (LINE_A & LINE_B),
size-based speed for detector-tracked vehicles (the car's known length sets the scale),
and temporal stationary/stalled vehicle detection.
"""

import math
import time
from typing import Dict, List, Tuple, Optional, Any, Union
from software.backend.schemas.hazards import VehicleTrack


class CentroidTracker:
    def __init__(
        self,
        max_disappeared: int = 15,
        line_a_y: int = 140,
        line_b_y: int = 260,
        line_distance_meters: float = 0.30,
        demo_mode: bool = True,
        min_movement_pixels: float = 4.0,
        demo_stall_seconds: float = 3.0,
        prod_stall_seconds: float = 15.0,
        allowed_direction: str = "FORWARD",
        ref_length_m: float = 0.075,
        ref_width_m: float = 0.035
    ):
        self.next_track_num = 1
        self.tracks: Dict[int, Dict[str, Any]] = {}
        self.max_disappeared = max_disappeared

        # Calibrated Virtual Speed Measurement Lines
        self.line_a_y = line_a_y
        self.line_b_y = line_b_y
        self.line_distance_meters = line_distance_meters  # Default 0.30m for prototype
        self.min_valid_speed_kmh = 0.2
        self.max_valid_speed_kmh = 50.0

        # Motion & Stalled thresholds
        self.min_movement_pixels = min_movement_pixels
        self.demo_mode = demo_mode
        self.demo_stall_seconds = demo_stall_seconds
        self.prod_stall_seconds = prod_stall_seconds
        self.allowed_direction = allowed_direction  # "FORWARD" or "REVERSE"

        # Real size of the tracked cars (toy cars on the demo bench). A detector-tracked car's box
        # spans this length side-on or this width head-on, which converts pixels to metres.
        self.ref_length_m = ref_length_m
        self.ref_width_m = ref_width_m
        self.max_size_speed_kmh = 30.0

        # When the detector supplies its own track IDs (YOLO + ByteTrack), they decide which
        # detection belongs to which track instead of nearest-centroid matching.
        self.external_id_map: Dict[int, int] = {}  # detector track_id -> internal track_num

    def set_demo_mode(self, enabled: bool):
        self.demo_mode = bool(enabled)

    def reset_external_ids(self):
        """Forget detector-supplied IDs. Call when the detector's own tracker restarts its numbering."""
        self.external_id_map.clear()

    def reset(self):
        """Drop every track (e.g. the camera source changed). Labels keep counting up so they stay unique."""
        self.tracks.clear()
        self.external_id_map.clear()

    def set_calibration(self, line_a_y: int, line_b_y: int, distance_meters: float):
        """Allows dynamic runtime calibration of virtual measurement lines."""
        self.line_a_y = int(line_a_y)
        self.line_b_y = int(line_b_y)
        self.line_distance_meters = float(max(0.05, distance_meters))

    def compute_line_speed(self, t_a: float, t_b: float) -> Optional[float]:
        """Calculates calibrated speed in km/h given crossing timestamps for Line A and Line B: v = d / dt * 3.6"""
        time_diff = abs(t_b - t_a)
        if 0.01 <= time_diff <= 10.0:
            mps = self.line_distance_meters / time_diff
            kmh = mps * 3.6
            if self.min_valid_speed_kmh <= kmh <= self.max_valid_speed_kmh:
                return round(kmh, 2)
        return None

    @property
    def stall_threshold_seconds(self) -> float:
        return self.demo_stall_seconds if self.demo_mode else self.prod_stall_seconds

    def update(self, detections: List[Dict[str, Any]]) -> List[VehicleTrack]:
        """
        Detections list: [{"class": str, "bbox": [x, y, w, h], "confidence": float}, ...]
        """
        now = time.time()
        active_tracks: List[VehicleTrack] = []

        if len(detections) == 0:
            for tid in list(self.tracks.keys()):
                self.tracks[tid]["disappeared"] += 1
                limit = 90 if self.tracks[tid].get("is_stationary") else self.max_disappeared
                if self.tracks[tid]["disappeared"] > limit:
                    del self.tracks[tid]
            return []

        # Convert detections to centroids
        det_centroids = []
        for d in detections:
            x, y, w, h = d["bbox"]
            cx = x + w / 2.0
            cy = y + h / 2.0
            det_centroids.append((cx, cy, d))

        if all(d.get("track_id") is not None for d in detections):
            self._associate_by_external_id(det_centroids, now)
        elif len(self.tracks) == 0:
            for cx, cy, d in det_centroids:
                self._register_track(cx, cy, d, now)
        else:
            track_ids = list(self.tracks.keys())
            track_coords = [self.tracks[tid]["centroid"] for tid in track_ids]

            used_det_indices = set()
            used_track_ids = set()

            for i, tid in enumerate(track_ids):
                tx, ty = track_coords[i]
                best_dist = 999999.0
                best_det_idx = -1

                for j, (cx, cy, d) in enumerate(det_centroids):
                    if j in used_det_indices:
                        continue
                    dist = math.hypot(cx - tx, cy - ty)
                    if dist < best_dist and dist < 150.0:  # Max matching distance
                        best_dist = dist
                        best_det_idx = j

                if best_det_idx >= 0:
                    used_track_ids.add(tid)
                    used_det_indices.add(best_det_idx)
                    cx, cy, d = det_centroids[best_det_idx]
                    self._update_track(tid, cx, cy, d, now)
                else:
                    self.tracks[tid]["disappeared"] += 1
                    limit = 90 if self.tracks[tid].get("is_stationary") else self.max_disappeared
                    if self.tracks[tid]["disappeared"] > limit:
                        del self.tracks[tid]

            # Register leftover detections as new tracks
            for j, (cx, cy, d) in enumerate(det_centroids):
                if j not in used_det_indices:
                    self._register_track(cx, cy, d, now)

        # Build output VehicleTrack objects
        for tid, tinfo in self.tracks.items():
            if tinfo["disappeared"] == 0 or (tinfo.get("is_stationary") and tinfo["disappeared"] < 90):
                stationary_time = tinfo.get("stationary_duration", 0.0)
                is_stalled = stationary_time >= self.stall_threshold_seconds
                is_wrong_way = tinfo["direction"] == "OPPOSITE"
                is_toppled = tinfo.get("is_toppled", False)

                is_hazard = is_stalled or is_wrong_way or is_toppled
                hazard_reason = None
                if is_toppled:
                    hazard_reason = "VEHICLE_TOPPLED"
                elif is_stalled:
                    hazard_reason = "STALLED_VEHICLE"
                elif is_wrong_way:
                    hazard_reason = "WRONG_WAY"

                vt = VehicleTrack(
                    track_id=tinfo["track_num"],
                    tracking_label=tinfo["label"],
                    vehicle_class=tinfo["class"],
                    confidence=round(tinfo["confidence"], 2),
                    bbox=tinfo["bbox"],
                    direction=tinfo["direction"],
                    estimated_speed_kmh=round(tinfo["speed_kmh"], 1),
                    is_calibrated_speed=tinfo["is_calibrated_speed"],
                    lane=tinfo.get("lane", 1),
                    timestamp=now,
                    is_hazard=is_hazard,
                    hazard_reason=hazard_reason,
                    is_stationary=tinfo["is_stationary"],
                    stationary_duration_seconds=round(stationary_time, 1),
                    is_toppled=is_toppled,
                    trajectory_points=[[p[0], p[1]] for p in tinfo["history"][-15:]],
                    vehicle_subtype=tinfo.get("subclass"),
                    detector_label=tinfo.get("detector_label"),
                    speed_source=tinfo.get("speed_source"),
                    frames_missing=tinfo["disappeared"]
                )
                active_tracks.append(vt)

        return active_tracks

    def _associate_by_external_id(self, det_centroids: List[Tuple[float, float, Dict[str, Any]]], now: float):
        """Matches detections to tracks using the detector's track IDs (ByteTrack)."""
        seen_track_nums = set()
        for cx, cy, d in det_centroids:
            ext_id = int(d["track_id"])
            num = self.external_id_map.get(ext_id)
            if num is None or num not in self.tracks:
                num = self._register_track(cx, cy, d, now)
                self.external_id_map[ext_id] = num
            else:
                self._update_track(num, cx, cy, d, now)
            seen_track_nums.add(num)

        for tid in list(self.tracks.keys()):
            if tid in seen_track_nums:
                continue
            self.tracks[tid]["disappeared"] += 1
            limit = 90 if self.tracks[tid].get("is_stationary") else self.max_disappeared
            if self.tracks[tid]["disappeared"] > limit:
                del self.tracks[tid]

        # Drop ID mappings whose track has expired
        for ext_id in [e for e, num in self.external_id_map.items() if num not in self.tracks]:
            del self.external_id_map[ext_id]

    def _register_track(self, cx: float, cy: float, d: Dict[str, Any], now: float) -> int:
        num = self.next_track_num
        self.next_track_num += 1
        label = f"CAM-{num:03d}"

        self.tracks[num] = {
            "track_num": num,
            "label": label,
            "centroid": (cx, cy),
            "history": [(cx, cy, now)],
            "class": d["class"],
            "subclass": d.get("subclass"),
            "detector_label": d.get("detector_label"),
            "confidence": d["confidence"],
            "bbox": d["bbox"],
            "disappeared": 0,
            "direction": "FORWARD",
            # Detector-tracked cars start at 0 until measured; heuristic tracks keep the toy-car demo default
            "speed_kmh": 0.0 if d.get("track_id") is not None else 3.8,
            "speed_source": None,
            "lines_time": 0.0,
            "is_calibrated_speed": False,
            "stationary_duration": 0.0,
            "is_stationary": False,
            "is_toppled": d.get("is_toppled", False),
            "cross_time_a": None,
            "cross_time_b": None,
            "consecutive_opposite_frames": 0,
            "lane": 1 if cx < 320 else 2
        }
        return num

    def _update_track(self, tid: int, cx: float, cy: float, d: Dict[str, Any], now: float):
        tinfo = self.tracks[tid]
        old_cx, old_cy = tinfo["centroid"]
        last_t = tinfo["history"][-1][2]
        dt = max(0.001, now - last_t)

        dx = cx - old_cx
        dy = cy - old_cy
        disp = math.hypot(dx, dy)

        # 1. Stationary vs Moving Logic (Test 4: Reset if vehicle resumes movement)
        if d.get("track_id") is not None and self.ref_length_m > 0:
            self._update_motion_from_size(tinfo, cx, cy, d, now, dt)
        elif disp < self.min_movement_pixels:
            tinfo["is_stationary"] = True
            tinfo["stationary_duration"] += dt
            tinfo["speed_kmh"] = max(0.0, tinfo["speed_kmh"] - (1.2 * dt))
            # If detection observed toppled signature while stationary
            if d.get("is_toppled"):
                tinfo["is_toppled"] = True
        else:
            # Vehicle moved again -> Immediately reset stationary timer & toppled status
            tinfo["is_stationary"] = False
            tinfo["stationary_duration"] = 0.0
            tinfo["is_toppled"] = False

            # Pixel speed calculation
            px_per_sec = disp / dt
            # Scale heuristic: ~0.02 m/pixel for typical camera view
            uncalibrated_speed = (px_per_sec * 0.02) * 3.6
            tinfo["speed_kmh"] = max(0.5, min(15.0, uncalibrated_speed))
            tinfo["speed_source"] = "PIXELS"

        # 2. Virtual Speed Lines Calibration Crossing (LINE_A and LINE_B)
        # Check if line_a or line_b was crossed in this step
        y_min = min(old_cy, cy)
        y_max = max(old_cy, cy)

        if y_min <= self.line_a_y <= y_max:
            tinfo["cross_time_a"] = now

        if y_min <= self.line_b_y <= y_max:
            tinfo["cross_time_b"] = now

        # If both lines crossed, compute calibrated speed: v = d / delta_t * 3.6
        if tinfo["cross_time_a"] is not None and tinfo["cross_time_b"] is not None:
            time_diff = abs(tinfo["cross_time_b"] - tinfo["cross_time_a"])
            if 0.05 < time_diff < 5.0:
                mps = self.line_distance_meters / time_diff
                calibrated_kmh = mps * 3.6
                if self.min_valid_speed_kmh <= calibrated_kmh <= self.max_valid_speed_kmh:
                    tinfo["speed_kmh"] = calibrated_kmh
                    tinfo["is_calibrated_speed"] = True
                    tinfo["speed_source"] = "LINES"
                    tinfo["lines_time"] = now
            # Reset crossing marks after calculation so it can measure next pass
            tinfo["cross_time_a"] = None
            tinfo["cross_time_b"] = None

        # 3. Direction Vector & Wrong-Way Analysis
        # Check trajectory over last 10 points
        if len(tinfo["history"]) >= 4:
            total_dy = cy - tinfo["history"][-4][1]
            total_dist = math.hypot(cx - tinfo["history"][-4][0], total_dy)

            if total_dist >= 12.0:  # Require minimum trajectory distance
                if total_dy < -6.0:
                    # Moving upwards (against forward traffic flow)
                    tinfo["consecutive_opposite_frames"] += 1
                elif total_dy > 6.0:
                    # Moving downwards (forward flow)
                    tinfo["consecutive_opposite_frames"] = 0
                    tinfo["direction"] = "FORWARD"

                # Require 4 consistent frames before confirming opposite direction
                if tinfo["consecutive_opposite_frames"] >= 4:
                    tinfo["direction"] = "OPPOSITE"
            else:
                if tinfo["consecutive_opposite_frames"] < 4:
                    tinfo["direction"] = "FORWARD"

        # Update metadata
        tinfo["centroid"] = (cx, cy)
        tinfo["bbox"] = d["bbox"]
        tinfo["class"] = d["class"]
        if d.get("subclass"):  # keep the last specific label (e.g. TOY_CAR) when a frame has none
            tinfo["subclass"] = d["subclass"]
            tinfo["detector_label"] = d.get("detector_label")
        elif not tinfo.get("detector_label"):
            tinfo["detector_label"] = d.get("detector_label")
        tinfo["confidence"] = d["confidence"]
        tinfo["disappeared"] = 0
        tinfo["lane"] = 1 if cx < 320 else 2
        tinfo["history"].append((cx, cy, now))
        if len(tinfo["history"]) > 40:
            tinfo["history"].pop(0)

    def _update_motion_from_size(self, tinfo: Dict[str, Any], cx: float, cy: float,
                                 d: Dict[str, Any], now: float, dt: float):
        """Moving/stationary state and speed for a detector-tracked car.
        The car's box spans a known real size (its length side-on, its width head-on or from behind),
        which converts pixels to metres without calibration. Motion is measured over the last
        ~0.6 s so box jitter does not read as movement."""
        bw, bh = d["bbox"][2], d["bbox"][3]
        long_side, short_side = max(1, bw, bh), max(1, min(bw, bh))
        ref_m = self.ref_length_m if long_side / short_side >= 1.8 else self.ref_width_m
        m_per_px = ref_m / long_side

        window = [p for p in tinfo["history"] if now - p[2] <= 0.6] or tinfo["history"][-1:]
        x0, y0, t0 = window[0]
        span = now - t0
        disp_px = math.hypot(cx - x0, cy - y0)

        if disp_px >= max(self.min_movement_pixels * 1.5, 0.04 * long_side):
            tinfo["is_stationary"] = False
            tinfo["stationary_duration"] = 0.0
            tinfo["is_toppled"] = False
            # A fresh line-calibrated reading is kept for a moment before size-based readings resume
            if span >= 0.15 and now - tinfo.get("lines_time", 0.0) > 1.5:
                kmh = min(self.max_size_speed_kmh, disp_px * m_per_px / span * 3.6)
                prev = tinfo["speed_kmh"] if tinfo.get("speed_source") == "SIZE" else kmh
                tinfo["speed_kmh"] = 0.6 * kmh + 0.4 * prev
                tinfo["speed_source"] = "SIZE"
        else:
            tinfo["is_stationary"] = True
            tinfo["stationary_duration"] += dt
            tinfo["speed_kmh"] = 0.0
