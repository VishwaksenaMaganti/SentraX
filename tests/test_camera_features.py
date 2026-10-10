"""
Camera feature tests: merging boxes from two detectors, size-based speed, 3 s stall,
visual emergency-vehicle recognition, and the vehicle log with snapshots.
No PyTorch needed.
"""

import numpy as np
import pytest

import software.backend.cv.tracker as tracker_module
from ai.inference.inference_engine import merge_detections
from software.backend.cv.tracker import CentroidTracker
from software.backend.cv.event_engine import CameraEventEngine
from software.backend.cv.emergency_detector import EmergencyLightDetector, is_flashing
from software.backend.cv.vehicle_log import VehicleLog, colour_name
from software.backend.schemas.hazards import VehicleTrack
from software.backend.schemas.events import EventType


class _Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def time(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(tracker_module, "time", c)
    return c


def _raw(xyxy, conf, cls, sub=None, label="car"):
    return {"xyxy": xyxy, "conf": conf, "class": cls, "subclass": sub, "label": label}


# --- merging two models' boxes ------------------------------------------------

def test_merge_keeps_one_box_and_the_specific_label():
    merged = merge_detections([
        _raw([100, 100, 300, 180], 0.9, "CAR", None, "car"),             # COCO
        _raw([105, 102, 298, 182], 0.5, "CAR", "TOY_CAR", "toy car"),    # open vocabulary
    ])
    assert len(merged) == 1
    assert merged[0]["conf"] == 0.9 and merged[0]["subclass"] == "TOY_CAR"


def test_merge_emergency_label_wins():
    merged = merge_detections([
        _raw([100, 100, 300, 180], 0.9, "CAR"),
        _raw([102, 101, 301, 181], 0.4, "EMERGENCY_VEHICLE", "POLICE", "police car"),
    ])
    assert merged[0]["class"] == "EMERGENCY_VEHICLE" and merged[0]["subclass"] == "POLICE"


def test_merge_keeps_separate_vehicles():
    merged = merge_detections([_raw([0, 0, 100, 50], 0.8, "CAR"), _raw([300, 0, 400, 50], 0.7, "CAR")])
    assert len(merged) == 2


# --- speed from the car's own size ------------------------------------------

def _det(x, y=100, w=300, h=120, tid=1):
    return {"class": "CAR", "bbox": [x, y, w, h], "confidence": 0.9, "track_id": tid}


def test_size_based_speed_side_view(clock):
    # Side-on box (300 x 120 px, aspect 2.5) spans the 7.5 cm car: 0.25 mm per pixel.
    tracker = CentroidTracker(ref_length_m=0.075, ref_width_m=0.035)
    tracks = []
    for step in range(11):  # 60 px every 0.1 s = 600 px/s = 0.15 m/s = 0.54 km/h
        clock.t = 1000.0 + step * 0.1
        tracks = tracker.update([_det(100 + step * 60)])
    assert tracks[0].speed_source == "SIZE"
    assert 0.45 <= tracks[0].estimated_speed_kmh <= 0.6
    assert not tracks[0].is_stationary


def test_size_based_speed_head_on_uses_width(clock):
    # Head-on box (140 x 120 px, aspect < 1.8) spans the 3.5 cm width: 0.25 mm per pixel too.
    tracker = CentroidTracker(ref_length_m=0.075, ref_width_m=0.035)
    tracks = []
    for step in range(11):
        clock.t = 1000.0 + step * 0.1
        tracks = tracker.update([_det(100 + step * 28, w=140)])  # 280 px/s * 0.25 mm = 0.07 m/s
    assert 0.2 <= tracks[0].estimated_speed_kmh <= 0.3


def test_still_car_is_stalled_after_three_seconds(clock):
    tracker = CentroidTracker()  # default demo stall = 3 s
    tracks = []
    for step in range(36):
        clock.t = 1000.0 + step * 0.1
        tracks = tracker.update([_det(200 + (step % 2))])  # 1 px jitter only
    assert tracks[0].is_stationary
    assert tracks[0].estimated_speed_kmh == 0.0
    assert tracks[0].hazard_reason == "STALLED_VEHICLE"


def test_default_stall_thresholds_are_three_seconds():
    assert CentroidTracker().stall_threshold_seconds == 3.0
    assert CameraEventEngine().stall_threshold_seconds == 3.0


# --- emergency vehicles by appearance ----------------------------------------

def _scene(body_bgr, lamp_bgr=None, lamp2_bgr=None):
    frame = np.full((240, 320, 3), 40, dtype=np.uint8)
    frame[100:180, 80:240] = body_bgr                  # vehicle body
    if lamp_bgr is not None:
        frame[104:118, 120:150] = lamp_bgr             # roof lamp, top of the box
    if lamp2_bgr is not None:
        frame[104:118, 170:200] = lamp2_bgr
    return frame


def _trk(sub=None):
    return VehicleTrack(track_id=1, tracking_label="CAM-001", bbox=[80, 100, 160, 80], vehicle_subtype=sub)


BLUE, RED, OFF = (255, 60, 0), (0, 0, 255), (60, 60, 60)
GREY, WHITE = (120, 120, 120), (235, 235, 235)


def test_flashing_blue_lights_mean_police():
    det = EmergencyLightDetector()
    out = {}
    for i in range(10):
        out = det.update(_scene(GREY, BLUE if i % 2 == 0 else OFF), [_trk()], 1000.0 + i * 0.1)
    assert out["CAM-001"]["type"] == "POLICE"
    assert out["CAM-001"]["flashing"]


def test_flashing_red_on_white_body_means_ambulance():
    det = EmergencyLightDetector()
    out = {}
    for i in range(10):
        out = det.update(_scene(WHITE, RED if i % 2 == 0 else OFF), [_trk()], 1000.0 + i * 0.1)
    assert out["CAM-001"]["type"] == "AMBULANCE"


def test_steady_red_and_blue_light_bar_means_police():
    det = EmergencyLightDetector()
    out = {}
    for i in range(6):
        out = det.update(_scene(GREY, RED, BLUE), [_trk()], 1000.0 + i * 0.1)
    assert out["CAM-001"]["type"] == "POLICE"
    assert "light bar" in out["CAM-001"]["reason"]


def test_plain_red_car_is_not_an_emergency_vehicle():
    det = EmergencyLightDetector()
    out = {}
    for i in range(10):
        out = det.update(_scene((0, 0, 220)), [_trk()], 1000.0 + i * 0.1)
    assert out == {}


def test_painted_blue_rims_and_flickering_red_details_are_not_lamps():
    # Regression: a yellow toy car with blue rims (not emissive) and small red details whose
    # share wobbles between frames was flagged as a police car.
    det = EmergencyLightDetector()
    out = {}
    for i in range(12):
        frame = _scene((0, 210, 230), (200, 90, 20))           # dim blue patch, brightness ~200
        if i % 2 == 0:
            frame[106:111, 160:167] = (0, 0, 255)               # red detail, ~0.45% of the box top, flickering
        out = det.update(frame, [_trk()], 1000.0 + i * 0.1)
    assert out == {}


def test_parked_track_not_detected_this_frame_is_ignored():
    # Regression: a stale parked box that another (flashing) car drove through was flagged.
    det = EmergencyLightDetector()
    out = {}
    for i in range(10):
        trk = _trk()
        trk.frames_missing = 5
        out = det.update(_scene(GREY, BLUE if i % 2 == 0 else OFF), [trk], 1000.0 + i * 0.1)
    assert out == {}


def test_detector_label_is_enough():
    det = EmergencyLightDetector()
    det.update(_scene(GREY), [_trk("AMBULANCE")], 1000.0)
    out = det.update(_scene(GREY), [_trk("AMBULANCE")], 1000.1)
    assert out["CAM-001"]["type"] == "AMBULANCE"


def test_is_flashing_needs_on_off_cycles():
    assert is_flashing([0.0, 0.02, 0.0, 0.02, 0.0, 0.02])
    assert not is_flashing([0.02] * 8)


def test_emergency_track_raises_camera_event():
    trk = _trk()
    trk.emergency_type, trk.emergency_reason = "POLICE", "Flashing blue lights"
    events = CameraEventEngine().evaluate_tracks_and_hazards([trk])
    ev = next(e for e in events if e.type == EventType.EMERGENCY_VEHICLE)
    assert "Police" in ev.title


# --- vehicle log with snapshots ----------------------------------------------

def test_vehicle_log_snapshot_speed_and_alerts():
    log = VehicleLog()
    frame = _scene((0, 220, 240))  # yellow car
    trk = _trk("TOY_CAR")
    trk.estimated_speed_kmh = 2.0
    log.update(frame, [trk], speed_limit_kmh=4.0, now=1000.0)
    trk2 = trk.model_copy()
    trk2.estimated_speed_kmh = 5.0
    log.update(frame, [trk2], speed_limit_kmh=4.0, now=1000.5)

    data = log.get()
    rec = data["vehicles"][0]
    assert rec["type_label"] == "Toy car"
    assert rec["colour"] == "Yellow"
    assert rec["speed_max"] == 5.0 and rec["speed_avg"] == 3.5
    assert "Overspeed" in rec["alerts"]
    assert rec["snapshot_version"] >= 1
    assert log.snapshot("CAM-001")[:2] == b"\xff\xd8"  # JPEG
    assert data["summary"]["vehicles_seen"] == 1 and data["summary"]["overspeed_count"] == 1

    log.update(frame, [], speed_limit_kmh=4.0, now=1001.0)
    assert log.get()["vehicles"][0]["in_view"] is False
    log.clear()
    assert log.get()["vehicles"] == []


def test_colour_names():
    assert colour_name(np.full((40, 80, 3), (235, 235, 235), dtype=np.uint8)) == "White"
    assert colour_name(np.full((40, 80, 3), (200, 60, 0), dtype=np.uint8)) == "Blue"
