"""
SentraX Multi-Object Vehicle Tracker
Maintains persistent track IDs, direction estimation, speed estimation (marked ESTIMATED),
and stopped/stalled vehicle detection across consecutive camera frames.
"""

import math
import time
from typing import Dict, List, Tuple, Optional
from software.backend.schemas.hazards import VehicleTrack


class CentroidTracker:
    def __init__(self, max_disappeared: int = 15, pixel_to_kmh_scale: float = 0.08):
        self.next_track_id = 1
        self.tracks: Dict[int, Dict] = {}  # track_id -> info
        self.max_disappeared = max_disappeared
        self.pixel_to_kmh_scale = pixel_to_kmh_scale  # Calibrated for toy-car demonstration distance

    def update(self, detections: List[Dict]) -> List[VehicleTrack]:
        """
        Detections list of dict: {"class": str, "bbox": [x, y, w, h], "confidence": float}
        """
        now = time.time()
        active_tracks: List[VehicleTrack] = []

        if len(detections) == 0:
            # Mark all existing tracks as disappeared
            for tid in list(self.tracks.keys()):
                self.tracks[tid]["disappeared"] += 1
                if self.tracks[tid]["disappeared"] > self.max_disappeared:
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
            # Match existing tracks to nearest detected centroids
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
                    if dist < best_dist and dist < 120.0:  # Distance threshold
                        best_dist = dist
                        best_det_idx = j

                if best_det_idx >= 0:
                    used_track_ids.add(tid)
                    used_det_indices.add(best_det_idx)
                    cx, cy, d = det_centroids[best_det_idx]
                    self._update_track(tid, cx, cy, d, now)
                else:
                    self.tracks[tid]["disappeared"] += 1
                    if self.tracks[tid]["disappeared"] > self.max_disappeared:
                        del self.tracks[tid]

            # Register leftover detections as new tracks
            for j, (cx, cy, d) in enumerate(det_centroids):
                if j not in used_det_indices:
                    self._register_track(cx, cy, d, now)

        # Build output objects
        for tid, tinfo in self.tracks.items():
            if tinfo["disappeared"] == 0:
                # Determine stalled condition (low motion over 3+ seconds)
                time_stationary = tinfo.get("stationary_duration", 0.0)
                is_stalled = time_stationary >= 3.0

                vt = VehicleTrack(
                    track_id=tid,
                    vehicle_class=tinfo["class"],
                    confidence=tinfo["confidence"],
                    bbox=tinfo["bbox"],
                    direction=tinfo["direction"],
                    estimated_speed_kmh=round(tinfo["estimated_speed_kmh"], 1),
                    is_calibrated_speed=False,  # Uncalibrated phone CV: marked ESTIMATED
                    lane=tinfo.get("lane", 1),
                    timestamp=now,
                    is_hazard=is_stalled or (tinfo["direction"] == "OPPOSITE"),
                    hazard_reason="STALLED_VEHICLE" if is_stalled else ("WRONG_WAY" if tinfo["direction"] == "OPPOSITE" else None)
                )
                active_tracks.append(vt)

        return active_tracks

    def _register_track(self, cx: float, cy: float, d: Dict, now: float):
        tid = self.next_track_id
        self.next_track_id += 1
        self.tracks[tid] = {
            "centroid": (cx, cy),
            "history": [(cx, cy, now)],
            "class": d["class"],
            "confidence": d["confidence"],
            "bbox": d["bbox"],
            "disappeared": 0,
            "direction": "NORTH",
            "estimated_speed_kmh": 4.5,
            "stationary_duration": 0.0,
            "lane": 1 if cx < 320 else 2
        }

    def _update_track(self, tid: int, cx: float, cy: float, d: Dict, now: float):
        tinfo = self.tracks[tid]
        old_cx, old_cy = tinfo["centroid"]
        dt = max(0.01, now - tinfo["history"][-1][2])

        # Direction calculation
        dx = cx - old_cx
        dy = cy - old_cy
        dist = math.hypot(dx, dy)

        if dist < 4.0:
            tinfo["stationary_duration"] += dt
            tinfo["estimated_speed_kmh"] = max(0.0, tinfo["estimated_speed_kmh"] - 0.5)
        else:
            tinfo["stationary_duration"] = 0.0
            # Pixel velocity to km/h estimation
            pixel_speed = dist / dt
            tinfo["estimated_speed_kmh"] = min(15.0, pixel_speed * self.pixel_to_kmh_scale)

        if dy > 5.0:
            tinfo["direction"] = "OPPOSITE"  # Towards camera / south (wrong-way on standard lane)
        elif dy < -5.0:
            tinfo["direction"] = "NORTH"     # Away from camera (standard flow)

        tinfo["centroid"] = (cx, cy)
        tinfo["bbox"] = d["bbox"]
        tinfo["class"] = d["class"]
        tinfo["confidence"] = d["confidence"]
        tinfo["disappeared"] = 0
        tinfo["history"].append((cx, cy, now))
        if len(tinfo["history"]) > 30:
            tinfo["history"].pop(0)
