"""
SentraX Multi-Modal Computer Vision & Sensor-Camera Fusion Test Suite
Verifies all 13 required test cases specified in Section 43:
  Test 1: Vehicle Confirmed
  Test 2: Camera Stalled (5s demo mode)
  Test 3: Stalled Confirmed
  Test 4: No Stalled Event (vehicle moves before timer expires)
  Test 5: Camera Wrong-Way
  Test 6: Wrong-Way Confirmed
  Test 7: Possible Collision (candidate)
  Test 8: Collision Confirmed
  Test 9: Sensor-Only Collision
  Test 10: Camera-Only Collision
  Test 11: Sensor-Camera Mismatch
  Test 12: Sensor-Only Wet Road (camera cannot measure moisture)
  Test 13: Camera-Only Pothole (no physical sensor)
Plus speed line calibration and temporal smoothing verification.
"""

import pytest
import time
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel, DeviceSource
from software.backend.schemas.events import EventType, EventSeverity, MatchStatus, DetectionMode
from software.backend.schemas.hazards import VehicleTrack, PotholeRecord
from software.backend.cv.tracker import CentroidTracker
from software.backend.cv.event_engine import CameraEventEngine
from software.backend.engines.fusion_engine import SensorCameraFusionEngine
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.road_health_engine import RoadHealthEngine
from software.backend.engines.recommendation_engine import RecommendationEngine


@pytest.fixture
def fusion():
    return SensorCameraFusionEngine(matching_window_seconds=3.0)


@pytest.fixture
def tracker():
    return CentroidTracker(
        line_a_y=140,
        line_b_y=260,
        line_distance_meters=0.30,
        demo_mode=True,
        min_movement_pixels=4.0,
        demo_stall_seconds=5.0
    )


@pytest.fixture
def event_engine():
    return CameraEventEngine(demo_mode=True, demo_stall_seconds=5.0)


def test_case_1_vehicle_confirmed(fusion):
    """TEST 1: Camera detects moving vehicle + Sensor detects vehicle -> VEHICLE CONFIRMED"""
    tele = CanonicalTelemetry(ir_sensors=[True, False, False, False], measured_speed_kmh=4.2)
    cv_stats = {
        "vehicle_count": 1,
        "average_speed_kmh": 4.4,
        "stopped_vehicle_count": 0,
        "wrong_way_count": 0,
        "camera_events": [{"type": EventType.VEHICLE_DETECTED.value, "timestamp": time.time(), "speed": 4.4}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    table = fusion.get_dashboard_fusion_table(fused_tele, cv_stats)

    speed_row = next(r for r in table if r["event"] == "Vehicle Speed")
    assert "CONFIRMED" in speed_row["final"]
    assert fused_tele.traffic_count >= 1


def test_case_2_camera_stalled_demo(tracker, event_engine, fusion):
    """TEST 2: Camera vehicle stationary for 5 seconds in DEMO mode -> CAMERA STALLED"""
    # Create track stationary for 5.2s
    vt = VehicleTrack(
        track_id=1,
        tracking_label="CAM-001",
        is_stationary=True,
        stationary_duration_seconds=5.2,
        estimated_speed_kmh=0.0
    )
    cam_events = event_engine.evaluate_tracks_and_hazards([vt], [])
    stalled_ev = next((e for e in cam_events if e.type == EventType.STALLED), None)

    assert stalled_ev is not None
    assert stalled_ev.tracking_id == "CAM-001"

    # Feed into fusion with sensor normal
    tele = CanonicalTelemetry(stalled_vehicle=False)
    cv_stats = {
        "vehicle_count": 1,
        "stopped_vehicle_count": 1,
        "camera_events": [stalled_ev.model_dump()]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    stalled_fe = next((e for e in events if e.event_type == EventType.STALLED), None)

    assert stalled_fe is not None
    assert stalled_fe.match_status == MatchStatus.CAMERA_ONLY
    assert "CAMERA-ONLY" in stalled_fe.title


def test_case_3_stalled_confirmed(fusion):
    """TEST 3: Sensor stalled event + camera stalled event -> STALLED CONFIRMED"""
    tele = CanonicalTelemetry(stalled_vehicle=True)
    cv_stats = {
        "vehicle_count": 1,
        "stopped_vehicle_count": 1,
        "camera_events": [{"type": EventType.STALLED.value, "timestamp": time.time(), "speed": 0.0}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.STALLED), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.CONFIRMED
    assert fe.final_confidence >= 0.95
    assert "CONFIRMED" in fe.title


def test_case_4_no_stalled_event_vehicle_moves(tracker):
    """TEST 4: Camera vehicle moves again before timer expires -> no stalled event"""
    # Step 1: Detect vehicle at (200, 200)
    det1 = [{"class": "CAR", "bbox": [180, 180, 40, 40], "confidence": 0.90}]
    tracks1 = tracker.update(det1)
    assert len(tracks1) == 1
    assert not tracks1[0].is_stationary

    # Step 2: Tiny displacement (< 4.0 px) -> stationary timer begins
    det2 = [{"class": "CAR", "bbox": [181, 181, 40, 40], "confidence": 0.90}]
    tracks2 = tracker.update(det2)
    assert tracks2[0].is_stationary

    # Step 3: Vehicle moves (> 4.0 px displacement) -> timer resets immediately!
    det3 = [{"class": "CAR", "bbox": [195, 220, 40, 40], "confidence": 0.90}]
    tracks3 = tracker.update(det3)
    assert not tracks3[0].is_stationary
    assert tracks3[0].stationary_duration_seconds == 0.0
    assert not tracks3[0].is_hazard


def test_case_5_camera_wrong_way(fusion):
    """TEST 5: Camera detects wrong-way -> CAMERA WRONG-WAY"""
    fusion.set_detection_mode(DetectionMode.CAMERA)
    tele = CanonicalTelemetry(wrong_way=False)
    cv_stats = {
        "vehicle_count": 1,
        "wrong_way_count": 1,
        "camera_events": [{"type": EventType.WRONG_WAY.value, "timestamp": time.time(), "speed": 4.0}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    assert fused_tele.wrong_way is True


def test_case_6_wrong_way_confirmed(fusion):
    """TEST 6: Sensor wrong-way + camera wrong-way -> WRONG-WAY CONFIRMED"""
    fusion.set_detection_mode(DetectionMode.FUSION)
    tele = CanonicalTelemetry(wrong_way=True)
    cv_stats = {
        "vehicle_count": 1,
        "wrong_way_count": 1,
        "camera_events": [{"type": EventType.WRONG_WAY.value, "timestamp": time.time(), "speed": 4.0}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.WRONG_WAY), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.CONFIRMED
    assert fe.final_confidence >= 0.95
    assert fused_tele.wrong_way is True


def test_case_7_possible_collision_candidate(event_engine, fusion):
    """TEST 7: Camera detects collision candidate -> POSSIBLE COLLISION"""
    # Two vehicles in extreme proximity
    t1 = VehicleTrack(track_id=1, tracking_label="CAM-001", bbox=[200, 200, 50, 50], estimated_speed_kmh=4.0)
    t2 = VehicleTrack(track_id=2, tracking_label="CAM-002", bbox=[210, 205, 50, 50], estimated_speed_kmh=4.0)

    events = event_engine.evaluate_tracks_and_hazards([t1, t2], [])
    cand = next((e for e in events if e.type == EventType.POSSIBLE_COLLISION), None)

    assert cand is not None
    assert cand.is_candidate is True
    assert "POSSIBLE" in cand.title


def test_case_8_collision_confirmed(fusion):
    """TEST 8: Camera collision + physical sound sensor collision -> COLLISION CONFIRMED"""
    tele = CanonicalTelemetry(collision=True, sound_active=True)
    cv_stats = {
        "vehicle_count": 2,
        "stopped_vehicle_count": 2,
        "camera_events": [{"type": EventType.COLLISION.value, "timestamp": time.time(), "speed": 0.0}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.COLLISION), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.CONFIRMED
    assert fe.final_confidence >= 0.98
    assert fused_tele.risk_score >= 85


def test_case_9_sensor_only_collision(fusion):
    """TEST 9: Sensor collision only -> SENSOR-ONLY COLLISION"""
    tele = CanonicalTelemetry(collision=True, sound_active=True)
    cv_stats = {"vehicle_count": 1, "stopped_vehicle_count": 0, "camera_events": []}

    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.COLLISION), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.SENSOR_ONLY
    assert "SENSOR-ONLY" in fe.title


def test_case_10_camera_only_collision(fusion):
    """TEST 10: Camera collision only -> CAMERA-ONLY COLLISION"""
    tele = CanonicalTelemetry(collision=False, sound_active=False)
    cv_stats = {
        "vehicle_count": 2,
        "stopped_vehicle_count": 2,
        "camera_events": [{"type": EventType.COLLISION.value, "timestamp": time.time(), "speed": 0.0}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.COLLISION), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.CAMERA_ONLY
    assert "CAMERA-ONLY" in fe.title


def test_case_11_sensor_camera_mismatch(fusion):
    """TEST 11: Sensor says normal, Camera says wrong-way -> MISMATCH"""
    tele = CanonicalTelemetry(wrong_way=False)
    cv_stats = {
        "vehicle_count": 1,
        "wrong_way_count": 1,
        "camera_events": [{"type": EventType.WRONG_WAY.value, "timestamp": time.time(), "speed": 4.2}]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.WRONG_WAY), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.MISMATCH
    assert "MISMATCH" in fe.title


def test_case_12_sensor_only_wet_road(fusion):
    """TEST 12: Wet-road sensor detects moisture, Camera cannot measure moisture -> SENSOR-ONLY WET ROAD"""
    tele = CanonicalTelemetry(road_condition=RoadCondition.WET, moisture_raw=1450)
    cv_stats = {"vehicle_count": 1, "camera_events": []}

    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.WET_ROAD), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.SENSOR_ONLY
    assert "Camera cannot measure moisture" in fe.description


def test_case_13_camera_only_pothole(fusion):
    """TEST 13: Camera detects pothole, No physical sensor -> CAMERA-ONLY POTHOLE"""
    tele = CanonicalTelemetry()
    cv_stats = {"vehicle_count": 1, "pothole_count": 2, "camera_events": []}

    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.POTHOLE), None)

    assert fe is not None
    assert fe.match_status == MatchStatus.CAMERA_ONLY
    assert "No physical road sensor" in fe.description


def test_calibrated_speed_virtual_lines():
    """Verifies virtual lines LINE_A and LINE_B compute calibrated speed: v = d / delta_t * 3.6"""
    tracker = CentroidTracker(line_a_y=100, line_b_y=200, line_distance_meters=0.30)
    now = time.time()

    # Section 9 exact example: 0.30m / 0.22s = 1.363 m/s * 3.6 = 4.91 km/h
    speed = tracker.compute_line_speed(t_a=now, t_b=now + 0.22)
    assert speed is not None
    assert 4.85 <= speed <= 4.95


def test_road_health_temporal_smoothing():
    """Verifies exponential moving average prevents one frame from spiking road health."""
    RoadHealthEngine.set_smoothed_score(82.0)

    # One observation with pothole penalty
    score, band, color, reasons = RoadHealthEngine.evaluate_segment_health(
        potholes=2,
        apply_smoothing=True
    )

    # Raw score with 2 potholes is 100 - 30 = 70
    # Smoothed score from 82 towards 70 should be around 80, NOT collapsing to 20!
    assert 76 <= score <= 82
    assert band in ("GOOD", "MODERATE", "EXCELLENT")


def test_risk_engine_critical_override():
    """Verifies confirmed collision enforces risk >= 85 and wrong-way >= 80."""
    tele_col = CanonicalTelemetry(collision=True)
    score_col, _ = RoadRiskEngine.calculate_risk(tele_col)
    assert score_col >= 85

    tele_ww = CanonicalTelemetry(wrong_way=True)
    score_ww, _ = RoadRiskEngine.calculate_risk(tele_ww)
    assert score_ww >= 80


def test_explainability_forensic_audit(fusion):
    """Section 58: Verifies 8-question forensic decision audit is generated for fused events."""
    tele = CanonicalTelemetry(collision=True)
    cv_stats = {"camera_events": [{"type": "COLLISION", "confidence": 0.98}], "vehicle_count": 2}
    _, events = fusion.fuse(tele, cv_stats)
    assert len(events) > 0

    explanation = fusion.explain_event(events[0].event_id)
    assert "audit" in explanation
    audit = explanation["audit"]

    # Verify all 8 questions are answered
    assert "1_sensor_detection" in audit and len(audit["1_sensor_detection"]) > 10
    assert "2_camera_detection" in audit and len(audit["2_camera_detection"]) > 10
    assert "3_did_they_agree" in audit and "CONFIRMED" in audit["3_did_they_agree"]
    assert "4_confidence_score" in audit and "Dual Independent" in audit["4_confidence_score"]
    assert "5_confirmation_reason" in audit
    assert "6_risk_score_impact" in audit and "85" in audit["6_risk_score_impact"]
    assert "7_road_health_impact" in audit
    assert "8_recommended_speed_rationale" in audit and "20" in audit["8_recommended_speed_rationale"]


def test_ai_inference_engine_structure():
    """Sections 40 & 41: Verifies AI classes, dataset schema, and fallback engine."""
    import json
    from pathlib import Path
    from ai.inference.inference_engine import AIInferenceEngine

    classes_file = Path("ai/models/classes.json")
    assert classes_file.exists()
    with open(classes_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data["classes"]) == 12

    dataset_yaml = Path("ai/datasets/dataset.yaml")
    assert dataset_yaml.exists()

    engine = AIInferenceEngine()
    status = engine.get_status()
    assert "model_type" in status
    assert status["model_type"] in ("CALIBRATED_MOTION_HEURISTIC", "YOLO_PYTORCH", "ONNX_DNN")


def test_case_14_vehicle_toppled_confirmed(fusion):
    """TEST 14: Camera vehicle toppled / rolled over -> VEHICLE TOPPLED OVER alert"""
    tele = CanonicalTelemetry()
    cv_stats = {
        "vehicle_count": 1,
        "stopped_vehicle_count": 1,
        "toppled_vehicle_count": 1,
        "camera_events": [{
            "type": EventType.VEHICLE_TOPPLED.value,
            "timestamp": time.time(),
            "confidence": 0.96,
            "tracking_id": "CAM-001",
            "speed": 0.0
        }]
    }
    fused_tele, events = fusion.fuse(tele, cv_stats)
    fe = next((e for e in events if e.event_type == EventType.VEHICLE_TOPPLED), None)

    assert fe is not None
    assert fe.severity == EventSeverity.CRITICAL
    assert fe.match_status == MatchStatus.CAMERA_ONLY
    assert "TOPPLED" in fe.title
    assert fused_tele.vehicle_toppled is True
    assert fused_tele.risk_score >= 85
    assert fused_tele.recommended_speed_kmh <= 25.0


def test_road_roi_filtering():
    """Verifies that Road ROI properly rejects detections outside calibrated corridor."""
    from software.backend.cv.detector import RoadObjectDetector
    det = RoadObjectDetector()
    det.set_roi(y_min=0.20, y_max=0.80, x_min=0.05, x_max=0.95, enabled=True)
    x1, y1, x2, y2 = det.get_roi_pixels(640, 360)
    assert y1 == int(0.20 * 360)
    assert y2 == int(0.80 * 360)
    assert x1 == int(0.05 * 640)
    assert x2 == int(0.95 * 640)

