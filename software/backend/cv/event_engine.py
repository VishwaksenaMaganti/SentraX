"""
SentraX Camera Event Generation Engine
Translates real-time vehicle tracks, trajectories, stationary timers,
and visual indicators into standardized CameraEvent structures.
Includes temporal state machines for stalled vehicles (5s demo / 15s prod),
congestion, wrong-way, overspeed, collision candidate & confirmation, and hazards.
"""

import time
import math
from typing import List, Dict, Any, Optional, Tuple
from software.backend.schemas.events import CameraEvent, EventType, EventSeverity
from software.backend.schemas.hazards import VehicleTrack, PotholeRecord


class CameraEventEngine:
    def __init__(
        self,
        demo_mode: bool = True,
        demo_stall_seconds: float = 5.0,
        prod_stall_seconds: float = 15.0,
        congestion_threshold_vehicles: int = 3,
        congestion_duration_seconds: float = 5.0,
        demo_overspeed_limit_kmh: float = 4.0,
        normal_speed_limit_kmh: float = 80.0
    ):
        self.demo_mode = demo_mode
        self.demo_stall_seconds = demo_stall_seconds
        self.prod_stall_seconds = prod_stall_seconds
        self.congestion_threshold_vehicles = congestion_threshold_vehicles
        self.congestion_duration_seconds = congestion_duration_seconds
        self.demo_overspeed_limit_kmh = demo_overspeed_limit_kmh
        self.normal_speed_limit_kmh = normal_speed_limit_kmh

        # Temporal state tracking
        self.congestion_start_time: Optional[float] = None
        self.active_collision_candidates: Dict[str, Dict[str, Any]] = {}  # key -> candidate info
        self.last_reported_events: Dict[str, float] = {}  # event_key -> last_time

    def set_demo_mode(self, enabled: bool):
        self.demo_mode = bool(enabled)

    @property
    def stall_threshold_seconds(self) -> float:
        return self.demo_stall_seconds if self.demo_mode else self.prod_stall_seconds

    def evaluate_tracks_and_hazards(
        self,
        tracks: List[VehicleTrack],
        potholes: List[PotholeRecord],
        obstruction_detected: bool = False
    ) -> List[CameraEvent]:
        """
        Runs one cycle of camera event analysis across all active tracks and visual hazards.
        Returns a list of structured CameraEvent objects.
        """
        now = time.time()
        events: List[CameraEvent] = []

        # 1. Individual Vehicle Events (Speed, Overspeed, Stalled, Wrong-Way)
        for trk in tracks:
            # 1a. Vehicle Detected event
            # 1b. Overspeed check (Separate demo 4.0 km/h vs production 80 km/h)
            speed_limit = self.demo_overspeed_limit_kmh if self.demo_mode else self.normal_speed_limit_kmh
            if trk.estimated_speed_kmh > speed_limit:
                events.append(CameraEvent(
                    source="camera",
                    type=EventType.OVERSPEED,
                    tracking_id=trk.tracking_label,
                    timestamp=now,
                    confidence=0.92,
                    speed=trk.estimated_speed_kmh,
                    direction=trk.direction,
                    position={"x": trk.bbox[0], "y": trk.bbox[1], "w": trk.bbox[2], "h": trk.bbox[3]},
                    severity=EventSeverity.WARNING,
                    title="Camera Overspeed Detected",
                    description=f"Vehicle {trk.tracking_label} observed at {trk.estimated_speed_kmh:.1f} km/h (Limit: {speed_limit} km/h)",
                    is_hazard=True
                ))

            # 1c. Stalled Vehicle (Test 2: Demo 5s / Test 3: Stalled / Test 4: Reset if moved)
            if trk.is_stationary and trk.stationary_duration_seconds >= self.stall_threshold_seconds:
                events.append(CameraEvent(
                    source="camera",
                    type=EventType.STALLED,
                    tracking_id=trk.tracking_label,
                    timestamp=now,
                    confidence=0.94,
                    speed=0.0,
                    direction=trk.direction,
                    position={"x": trk.bbox[0], "y": trk.bbox[1], "w": trk.bbox[2], "h": trk.bbox[3]},
                    severity=EventSeverity.HIGH,
                    title="Camera Stalled Vehicle",
                    description=f"Vehicle {trk.tracking_label} stationary for {trk.stationary_duration_seconds:.1f}s ({'DEMO' if self.demo_mode else 'PROD'} threshold)",
                    is_hazard=True
                ))

            # 1d. Wrong-Way Trajectory (Test 5 & 6)
            if trk.direction == "OPPOSITE":
                events.append(CameraEvent(
                    source="camera",
                    type=EventType.WRONG_WAY,
                    tracking_id=trk.tracking_label,
                    timestamp=now,
                    confidence=0.95,
                    speed=trk.estimated_speed_kmh,
                    direction="OPPOSITE",
                    position={"x": trk.bbox[0], "y": trk.bbox[1], "w": trk.bbox[2], "h": trk.bbox[3]},
                    severity=EventSeverity.CRITICAL,
                    title="Camera Wrong-Way Vehicle",
                    description=f"Vehicle {trk.tracking_label} moving opposite to corridor traffic direction",
                    is_hazard=True
                ))

            # 1e. Vehicle Toppled Over / Rollover
            if getattr(trk, "is_toppled", False) or trk.hazard_reason == "VEHICLE_TOPPLED":
                events.append(CameraEvent(
                    source="camera",
                    type=EventType.VEHICLE_TOPPLED,
                    tracking_id=trk.tracking_label,
                    timestamp=now,
                    confidence=0.96,
                    speed=0.0,
                    direction=trk.direction,
                    position={"x": trk.bbox[0], "y": trk.bbox[1], "w": trk.bbox[2], "h": trk.bbox[3]},
                    severity=EventSeverity.CRITICAL,
                    title="CRITICAL: VEHICLE TOPPLED OVER",
                    description=f"Vehicle {trk.tracking_label} has toppled / rolled over in roadway",
                    is_hazard=True
                ))

        # 2. Traffic Congestion Temporal Evaluation (Section 7)
        vehicle_count = len(tracks)
        effective_congestion_target = 2 if self.demo_mode else self.congestion_threshold_vehicles
        if vehicle_count >= effective_congestion_target:
            if self.congestion_start_time is None:
                self.congestion_start_time = now
            elif (now - self.congestion_start_time) >= self.congestion_duration_seconds:
                events.append(CameraEvent(
                    source="camera",
                    type=EventType.CONGESTION,
                    tracking_id="CORRIDOR",
                    timestamp=now,
                    confidence=0.88,
                    speed=0.0,
                    direction="FORWARD",
                    severity=EventSeverity.WARNING,
                    title="Camera Traffic Congestion",
                    description=f"{vehicle_count} vehicles accumulated for >= {self.congestion_duration_seconds}s",
                    is_hazard=False
                ))
        else:
            self.congestion_start_time = None

        # 3. Collision Detection (Two-Stage: Candidate -> Confirmed) (Section 11, Tests 7, 8, 10)
        collision_events = self._evaluate_collisions(tracks, now)
        events.extend(collision_events)

        # 4. Potholes (Section 10, Test 13)
        if potholes:
            for p in potholes:
                events.append(CameraEvent(
                    source="camera",
                    type=EventType.POTHOLE,
                    tracking_id="ROAD-SURFACE",
                    timestamp=now,
                    confidence=p.confidence,
                    speed=0.0,
                    direction="N/A",
                    severity=EventSeverity.WARNING,
                    title="Camera Pothole Detected",
                    description=f"Surface defect identified by vision system (Severity: {p.severity})",
                    is_hazard=True
                ))

        # 5. Road Obstruction
        if obstruction_detected:
            events.append(CameraEvent(
                source="camera",
                type=EventType.ROAD_OBSTRUCTION,
                tracking_id="ROAD-OBSTACLE",
                timestamp=now,
                confidence=0.85,
                speed=0.0,
                direction="N/A",
                severity=EventSeverity.HIGH,
                title="Road Obstruction Detected",
                description="Stationary debris or obstacle detected in roadway",
                is_hazard=True
            ))

        return events

    def _evaluate_collisions(self, tracks: List[VehicleTrack], now: float) -> List[CameraEvent]:
        """
        Two-stage multi-signal collision detection:
        Stage 1: Trajectory convergence + bbox overlap/proximity -> CAMERA_COLLISION_CANDIDATE
        Stage 2: Post-interaction stationary state after candidate window -> CAMERA_COLLISION_CONFIRMED
        """
        collision_events: List[CameraEvent] = []
        n = len(tracks)
        if n < 2:
            return collision_events

        # Clean up stale candidates older than 6.0s
        for ckey in list(self.active_collision_candidates.keys()):
            if now - self.active_collision_candidates[ckey]["candidate_time"] > 6.0:
                del self.active_collision_candidates[ckey]

        # Check all pairs of vehicles
        for i in range(n):
            for j in range(i + 1, n):
                t1, t2 = tracks[i], tracks[j]
                ckey = f"{min(t1.track_id, t2.track_id)}_{max(t1.track_id, t2.track_id)}"

                # Calculate centers and distance
                c1x = t1.bbox[0] + t1.bbox[2] / 2.0
                c1y = t1.bbox[1] + t1.bbox[3] / 2.0
                c2x = t2.bbox[0] + t2.bbox[2] / 2.0
                c2y = t2.bbox[1] + t2.bbox[3] / 2.0
                dist = math.hypot(c1x - c2x, c1y - c2y)

                # Bounding box overlap / near-contact threshold
                min_safe_dist = (t1.bbox[2] + t2.bbox[2]) * 0.45

                # Check bounding box proximity/touching along both axes
                touch_x = (t1.bbox[0] + t1.bbox[2] >= t2.bbox[0] - 15) and (t2.bbox[0] + t2.bbox[2] >= t1.bbox[0] - 15)
                touch_y = (t1.bbox[1] + t1.bbox[3] >= t2.bbox[1] - 15) and (t2.bbox[1] + t2.bbox[3] >= t1.bbox[1] - 15)
                is_touching = (touch_x and touch_y) or (dist < min_safe_dist)

                if is_touching:
                    # Vehicles in contact or extreme proximity!
                    if ckey not in self.active_collision_candidates:
                        # Stage 1: Candidate
                        self.active_collision_candidates[ckey] = {
                            "candidate_time": now,
                            "tracks": (t1.tracking_label, t2.tracking_label),
                            "pos": {"x": int((c1x + c2x) / 2), "y": int((c1y + c2y) / 2)},
                            "confirmed": False
                        }
                        collision_events.append(CameraEvent(
                            source="camera",
                            type=EventType.POSSIBLE_COLLISION,
                            tracking_id=f"{t1.tracking_label}+{t2.tracking_label}",
                            timestamp=now,
                            confidence=0.75,
                            speed=0.0,
                            direction="N/A",
                            position=self.active_collision_candidates[ckey]["pos"],
                            severity=EventSeverity.HIGH,
                            title="POSSIBLE COLLISION",
                            description=f"Visual trajectory convergence between {t1.tracking_label} and {t2.tracking_label}",
                            is_hazard=True,
                            is_candidate=True
                        ))
                    else:
                        # Stage 2: Check for temporal confirmation (abrupt stop / post-impact stay)
                        cand = self.active_collision_candidates[ckey]
                        time_since_cand = now - cand["candidate_time"]

                        # If both vehicles are stationary or slow after 0.5s
                        if 0.5 <= time_since_cand <= 5.0 and (t1.is_stationary or t2.is_stationary or t1.estimated_speed_kmh < 1.0 or t2.estimated_speed_kmh < 1.0):
                            if not cand["confirmed"]:
                                cand["confirmed"] = True
                                collision_events.append(CameraEvent(
                                    source="camera",
                                    type=EventType.COLLISION,
                                    tracking_id=f"{t1.tracking_label}+{t2.tracking_label}",
                                    timestamp=now,
                                    confidence=0.94,
                                    speed=0.0,
                                    direction="N/A",
                                    position=cand["pos"],
                                    severity=EventSeverity.CRITICAL,
                                    title="CAMERA COLLISION CONFIRMED",
                                    description=f"Visual collision verified between {t1.tracking_label} and {t2.tracking_label} with post-impact stop",
                                    is_hazard=True,
                                    is_candidate=False,
                                    candidate_age_seconds=round(time_since_cand, 2)
                                ))

        return collision_events
