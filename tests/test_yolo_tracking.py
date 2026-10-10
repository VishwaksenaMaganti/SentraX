"""
YOLO + ByteTrack integration tests.
The tracker must follow detector-supplied track IDs (ByteTrack) instead of nearest-centroid
matching, and the detector must not mix heuristic boxes into YOLO output. No PyTorch needed:
the AI engine is replaced with a stub.
"""

import numpy as np

from software.backend.cv.tracker import CentroidTracker
from software.backend.cv.detector import RoadObjectDetector


def _det(track_id, x, y, w=60, h=30, cls="CAR"):
    return {"class": cls, "bbox": [x, y, w, h], "confidence": 0.8, "track_id": track_id}


def test_external_ids_survive_crossing_cars():
    """Two cars pass close by; centroid matching would swap them, ByteTrack IDs must not."""
    tracker = CentroidTracker(min_movement_pixels=1.0)
    tracker.update([_det(7, 100, 100), _det(9, 200, 100)])
    # Car 7 jumps right, car 9 jumps left: each ends nearer the other's old position
    tracks = tracker.update([_det(7, 190, 100), _det(9, 110, 100)])

    by_label = {t.tracking_label: t for t in tracks}
    assert by_label["CAM-001"].bbox[0] == 190
    assert by_label["CAM-002"].bbox[0] == 110


def test_unknown_external_id_registers_new_track():
    tracker = CentroidTracker()
    tracker.update([_det(1, 100, 100)])
    tracks = tracker.update([_det(1, 102, 100), _det(2, 400, 200)])
    assert sorted(t.tracking_label for t in tracks) == ["CAM-001", "CAM-002"]


def test_expired_track_drops_external_id_mapping():
    tracker = CentroidTracker(max_disappeared=2)
    tracker.update([_det(5, 100, 100)])
    for _ in range(4):
        tracker.update([_det(6, 300, 100)])  # ID 5 missing until its track expires
    assert 5 not in tracker.external_id_map
    # ByteTrack reusing ID 5 later must create a fresh track, not revive the old one
    tracks = tracker.update([_det(5, 100, 100), _det(6, 300, 100)])
    assert "CAM-003" in {t.tracking_label for t in tracks}


def test_reset_external_ids_starts_fresh_tracks():
    tracker = CentroidTracker()
    tracker.update([_det(1, 100, 100)])
    tracker.reset_external_ids()
    tracks = tracker.update([_det(1, 100, 100)])
    assert "CAM-002" in {t.tracking_label for t in tracks}


def test_wrong_way_still_detected_with_external_ids():
    tracker = CentroidTracker(min_movement_pixels=1.0)
    tracks = []
    for step in range(12):
        tracks = tracker.update([_det(3, 300, 300 - step * 10)])  # moving up the frame
    assert tracks[0].direction == "OPPOSITE"


def test_centroid_matching_unchanged_without_ids():
    tracker = CentroidTracker()
    tracker.update([{"class": "CAR", "bbox": [100, 100, 60, 30], "confidence": 0.9}])
    tracks = tracker.update([{"class": "CAR", "bbox": [105, 100, 60, 30], "confidence": 0.9}])
    assert [t.tracking_label for t in tracks] == ["CAM-001"]
    assert tracker.external_id_map == {}


def test_set_demo_mode_switches_stall_threshold():
    tracker = CentroidTracker(demo_stall_seconds=5.0, prod_stall_seconds=15.0)
    tracker.set_demo_mode(False)
    assert tracker.stall_threshold_seconds == 15.0
    tracker.set_demo_mode(True)
    assert tracker.stall_threshold_seconds == 5.0


class _StubEngine:
    """Stands in for AIInferenceEngine with a fixed tracked output."""
    def __init__(self, dets):
        self.dets = dets
        self.can_track = True
        self.reset_called = False

    def ensure_loaded(self):
        return True

    def track(self, frame):
        return list(self.dets)

    def reset_tracking(self):
        self.reset_called = True

    def get_status(self):
        return {"model_type": "YOLO_PYTORCH"}


def _frame():
    return np.zeros((360, 640, 3), dtype=np.uint8)


def test_detector_uses_yolo_output_even_when_empty():
    det = RoadObjectDetector()
    det.ai_engine = _StubEngine([])
    frame = _frame()
    frame[150:200, 200:300] = (0, 0, 255)  # red blob the colour heuristic would report
    assert det.detect(frame) == []
    assert det.last_backend_used == "YOLO_BYTETRACK"


def test_detector_applies_roi_to_yolo_output():
    det = RoadObjectDetector()
    det.set_roi(y_min=0.2, y_max=0.8)
    det.ai_engine = _StubEngine([_det(1, 300, 150), _det(2, 300, 5)])  # second is above the ROI
    out = det.detect(_frame())
    assert [d["track_id"] for d in out] == [1]


def test_detector_heuristic_for_synthetic_frames_and_heuristic_backend():
    det = RoadObjectDetector()
    det.ai_engine = _StubEngine([_det(1, 300, 150)])
    det.detect(_frame(), use_ai=False)
    assert det.last_backend_used == "HEURISTIC"

    assert det.set_backend("heuristic")
    det.detect(_frame())
    assert det.last_backend_used == "HEURISTIC"
    assert not det.set_backend("bogus")


def test_detector_reset_tracking_reaches_engine():
    det = RoadObjectDetector()
    det.ai_engine = _StubEngine([])
    det.reset_tracking()
    assert det.ai_engine.reset_called
