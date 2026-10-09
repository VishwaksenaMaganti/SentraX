"""
SentraX Multi-Object Vehicle Tracker
Maintains persistent track IDs (CAM-001, CAM-002, ...), trajectory analysis,
calibrated speed estimation with virtual measurement lines (LINE_A & LINE_B),
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
        demo_stall_seconds: float = 5.0,
        prod_stall_seconds: float = 15.0,
        allowed_direction: str = "FORWARD"
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

        if len(self.tracks) == 0:
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
                    trajectory_points=[[p[0], p[1]] for p in tinfo["history"][-15:]]
                )
                active_tracks.append(vt)

        return active_tracks

    def _register_track(self, cx: float, cy: float, d: Dict[str, Any], now: float):
        num = self.next_track_num
        self.next_track_num += 1
        label = f"CAM-{num:03d}"

        self.tracks[num] = {
            "track_num": num,
            "label": label,
            "centroid": (cx, cy),
            "history": [(cx, cy, now)],
            "class": d["class"],
            "confidence": d["confidence"],
            "bbox": d["bbox"],
            "disappeared": 0,
            "direction": "FORWARD",
            "speed_kmh": 3.8,  # Default initial estimated speed for toy-car demo
            "is_calibrated_speed": False,
            "stationary_duration": 0.0,
            "is_stationary": False,
            "is_toppled": d.get("is_toppled", False),
            "cross_time_a": None,
            "cross_time_b": None,
            "consecutive_opposite_frames": 0,
            "lane": 1 if cx < 320 else 2
        }

    def _update_track(self, tid: int, cx: float, cy: float, d: Dict[str, Any], now: float):
        tinfo = self.tracks[tid]
        old_cx, old_cy = tinfo["centroid"]
        last_t = tinfo["history"][-1][2]
        dt = max(0.001, now - last_t)

        dx = cx - old_cx
        dy = cy - old_cy
        disp = math.hypot(dx, dy)

        # 1. Stationary vs Moving Logic (Test 4: Reset if vehicle resumes movement)
        if disp < self.min_movement_pixels:
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
        tinfo["confidence"] = d["confidence"]
        tinfo["disappeared"] = 0
        tinfo["lane"] = 1 if cx < 320 else 2
        tinfo["history"].append((cx, cy, now))
        if len(tinfo["history"]) > 40:
            tinfo["history"].pop(0)
