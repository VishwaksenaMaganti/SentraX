"""
SentraX Vehicle Log
One record per vehicle the camera has seen. When a vehicle enters the frame a snapshot is taken
(and replaced while a clearer or larger view comes along), then its speed is followed while it is
in view: current, average and top speed. The record also keeps colour, heading, time in view and
the alerts it raised. Feeds the Camera AI panel of the mobile app.
"""

import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from software.backend.schemas.hazards import VehicleTrack

MAX_RECORDS = 12
SNAPSHOT_HEIGHT = 120
SNAPSHOT_MAX_WIDTH = 220
SNAPSHOT_REFRESH_SECONDS = 0.5
MOVING_KMH = 0.2  # speeds below this do not count towards the average

TYPE_NAMES = {
    "AMBULANCE": "Ambulance", "POLICE": "Police car", "FIRE_TRUCK": "Fire engine", "EMERGENCY": "Emergency vehicle",
    "TOY_CAR": "Toy car", "TAXI": "Taxi",
    "CAR": "Car", "TRUCK": "Truck", "BUS": "Bus", "MOTORCYCLE": "Motorcycle", "BICYCLE": "Bicycle",
    "AUTO_RICKSHAW": "Auto rickshaw", "EMERGENCY_VEHICLE": "Emergency vehicle",
}


def colour_name(crop_bgr: np.ndarray) -> Optional[str]:
    """Dominant body colour of a vehicle crop, judged on its central area to skip background."""
    if not CV2_AVAILABLE or crop_bgr is None or crop_bgr.size == 0:
        return None
    ch, cw = crop_bgr.shape[:2]
    core = crop_bgr[int(ch * 0.2):max(int(ch * 0.2) + 1, int(ch * 0.8)), int(cw * 0.2):max(int(cw * 0.2) + 1, int(cw * 0.8))]
    hsv = cv2.cvtColor(core, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    vivid = (s >= 70) & (v >= 60)
    if vivid.mean() < 0.15:
        mean_v = float(v.mean())
        return "White" if mean_v >= 170 else ("Black" if mean_v < 70 else "Silver")
    hist = np.bincount(h[vivid].ravel(), minlength=180)
    hue = int(hist.argmax())
    for limit, name in ((8, "Red"), (20, "Orange"), (34, "Yellow"), (85, "Green"), (100, "Teal"),
                        (130, "Blue"), (150, "Purple"), (170, "Pink"), (180, "Red")):
        if hue < limit:
            return name
    return None


def heading(points: List[List[float]]) -> Optional[str]:
    """Direction of travel across the frame from the recent trajectory."""
    if len(points) < 3:
        return None
    dx = points[-1][0] - points[0][0]
    dy = points[-1][1] - points[0][1]
    if max(abs(dx), abs(dy)) < 15:
        return None
    if abs(dx) >= abs(dy):
        return "Right" if dx > 0 else "Left"
    return "Down" if dy > 0 else "Up"


def track_status(trk: VehicleTrack) -> str:
    if trk.is_toppled:
        return "Toppled"
    if trk.hazard_reason == "STALLED_VEHICLE":
        return "Stalled"
    if trk.direction == "OPPOSITE":
        return "Wrong way"
    if trk.is_stationary:
        return "Stopped"
    return "Moving"


class VehicleLog:
    def __init__(self, max_records: int = MAX_RECORDS):
        self.max_records = max_records
        self._lock = threading.Lock()
        self._records: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._jpeg: Dict[str, bytes] = {}
        self._reset_totals()

    def _reset_totals(self):
        self.session_started = time.time()
        self.vehicles_seen = 0
        self.flagged: Dict[str, set] = {"overspeed": set(), "stalled": set(), "wrong_way": set(), "emergency": set()}
        self.top_speed = 0.0

    def clear(self):
        with self._lock:
            self._records.clear()
            self._jpeg.clear()
            self._reset_totals()

    def snapshot(self, label: str) -> Optional[bytes]:
        with self._lock:
            return self._jpeg.get(label)

    def update(self, frame_bgr: np.ndarray, tracks: List[VehicleTrack], speed_limit_kmh: float, now: Optional[float] = None):
        now = now or time.time()
        with self._lock:
            in_view = set()
            for trk in tracks:
                label = trk.tracking_label
                in_view.add(label)
                rec = self._records.get(label)
                if rec is None:
                    rec = self._new_record(trk, now)
                    self._records[label] = rec
                    self.vehicles_seen += 1
                self._maybe_snapshot(rec, trk, frame_bgr, now)
                self._update_record(rec, trk, speed_limit_kmh, now)

            for label, rec in self._records.items():
                rec["in_view"] = label in in_view

            # Keep the newest records; vehicles still in view are never dropped
            while len(self._records) > self.max_records:
                old = next((k for k, r in self._records.items() if not r["in_view"]), None)
                if old is None:
                    break
                del self._records[old]
                self._jpeg.pop(old, None)

    @staticmethod
    def _new_record(trk: VehicleTrack, now: float) -> Dict[str, Any]:
        return {
            "label": trk.tracking_label, "first_seen": now, "last_seen": now, "in_view": True,
            "vehicle_class": trk.vehicle_class, "type_label": None, "detector_label": None, "colour": None,
            "emergency_type": None, "emergency_reason": None,
            "speed_now": 0.0, "speed_max": 0.0, "speed_avg": 0.0, "speed_source": None,
            "heading": None, "status": "Moving", "alerts": [], "confidence": 0.0,
            "snapshot_version": 0, "_snap_t": 0.0, "_snap_conf": 0.0, "_snap_area": 0, "_speed_sum": 0.0, "_speed_n": 0,
        }

    def _maybe_snapshot(self, rec: Dict[str, Any], trk: VehicleTrack, frame_bgr: np.ndarray, now: float):
        if not CV2_AVAILABLE or frame_bgr is None or trk.frames_missing:
            return  # no fresh box this frame, so the old one may not show this vehicle any more
        x, y, w, h = trk.bbox
        area = w * h
        first = rec["snapshot_version"] == 0
        better = trk.confidence >= rec["_snap_conf"] + 0.05 or area >= rec["_snap_area"] * 1.2
        if not first and (now - rec["_snap_t"] < SNAPSHOT_REFRESH_SECONDS or not better):
            return
        fh, fw = frame_bgr.shape[:2]
        pad_x, pad_y = int(w * 0.1), int(h * 0.1)
        x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
        x2, y2 = min(fw, x + w + pad_x), min(fh, y + h + pad_y)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return
        crop = frame_bgr[y1:y2, x1:x2]
        scale = min(SNAPSHOT_HEIGHT / crop.shape[0], SNAPSHOT_MAX_WIDTH / crop.shape[1])
        thumb = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), max(1, int(crop.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", thumb, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if not ok:
            return
        self._jpeg[rec["label"]] = buf.tobytes()
        rec["snapshot_version"] += 1
        rec["_snap_t"], rec["_snap_conf"], rec["_snap_area"] = now, trk.confidence, area
        rec["colour"] = colour_name(frame_bgr[max(0, y):y + h, max(0, x):x + w]) or rec["colour"]

    def _update_record(self, rec: Dict[str, Any], trk: VehicleTrack, speed_limit_kmh: float, now: float):
        label = rec["label"]
        speed = float(trk.estimated_speed_kmh)
        rec["last_seen"] = now
        rec["vehicle_class"] = trk.vehicle_class
        rec["detector_label"] = trk.detector_label or rec["detector_label"]
        # Current verdict while in view; after it leaves the record keeps the last one
        rec["emergency_type"] = trk.emergency_type
        rec["emergency_reason"] = trk.emergency_reason
        rec["type_label"] = TYPE_NAMES.get(rec["emergency_type"] or trk.vehicle_subtype or trk.vehicle_class,
                                           str(trk.vehicle_class).replace("_", " ").title())
        rec["confidence"] = max(rec["confidence"], float(trk.confidence))
        rec["speed_now"] = round(speed, 1)
        rec["speed_source"] = trk.speed_source
        if speed >= MOVING_KMH:
            rec["_speed_sum"] += speed
            rec["_speed_n"] += 1
            rec["speed_avg"] = round(rec["_speed_sum"] / rec["_speed_n"], 1)
        rec["speed_max"] = round(max(rec["speed_max"], speed), 1)
        self.top_speed = max(self.top_speed, rec["speed_max"])
        rec["heading"] = heading(trk.trajectory_points) or rec["heading"]
        rec["status"] = track_status(trk)

        alerts = []
        if rec["speed_max"] > speed_limit_kmh:
            alerts.append("Overspeed")
            self.flagged["overspeed"].add(label)
        if rec["status"] == "Stalled" or "Stalled" in rec["alerts"]:
            alerts.append("Stalled")
            self.flagged["stalled"].add(label)
        if rec["status"] == "Wrong way" or "Wrong way" in rec["alerts"]:
            alerts.append("Wrong way")
            self.flagged["wrong_way"].add(label)
        if rec["emergency_type"]:
            alerts.append("Emergency")
            self.flagged["emergency"].add(label)
        rec["alerts"] = alerts

    def get(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            vehicles = []
            for rec in sorted(self._records.values(), key=lambda r: (not r["in_view"], -r["last_seen"])):
                pub = {k: v for k, v in rec.items() if not k.startswith("_")}
                pub["seconds_in_view"] = round(rec["last_seen"] - rec["first_seen"], 1)
                pub["seconds_since_seen"] = round(now - rec["last_seen"], 1)
                vehicles.append(pub)
            avgs = [r["speed_avg"] for r in self._records.values() if r["speed_avg"] > 0]
            summary = {
                "vehicles_seen": self.vehicles_seen,
                "in_view": sum(1 for r in self._records.values() if r["in_view"]),
                "average_speed_kmh": round(sum(avgs) / len(avgs), 1) if avgs else 0.0,
                "top_speed_kmh": round(self.top_speed, 1),
                "overspeed_count": len(self.flagged["overspeed"]),
                "stalled_count": len(self.flagged["stalled"]),
                "wrong_way_count": len(self.flagged["wrong_way"]),
                "emergency_count": len(self.flagged["emergency"]),
                "session_minutes": round((now - self.session_started) / 60.0, 1),
            }
        return {"vehicles": vehicles, "summary": summary}
