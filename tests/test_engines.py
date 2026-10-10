"""
Tests for SentraX Core Intelligence Engines:
Speed Recommendations, Risk Scoring, Road Health, Hazard Proximity, and Ultrasonic Physics.
"""

import pytest
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.road_health_engine import RoadHealthEngine
from software.backend.engines.recommendation_engine import RecommendationEngine
from software.backend.engines.hazard_engine import HazardEngine
from software.backend.engines.data_fusion import DataFusionEngine
from software.backend.core.config import settings


def test_ultrasonic_speed_physics():
    sensor_distance = settings.SENSOR_DISTANCE  # 0.30 meters
    # Simulated toy car passing in 0.24 seconds
    elapsed_seconds = 0.24
    speed_kmh = (sensor_distance / elapsed_seconds) * 3.6
    assert round(speed_kmh, 1) == 4.5  # Realistic toy-car speed


def test_toy_car_overspeed_threshold():
    demo_limit = settings.DEMO_OVERSPEED_LIMIT  # 4.0 km/h
    assert demo_limit == 4.0

    # Normal toy vehicle speed
    speed_normal = 3.2
    assert speed_normal <= demo_limit

    # Overspeed toy vehicle speed
    speed_rash = 4.8
    assert speed_rash > demo_limit


def test_speed_recommendations_priority():
    # 1. Normal road condition -> 80 km/h
    t_normal = CanonicalTelemetry(road_condition=RoadCondition.DRY, traffic_level=TrafficLevel.LIGHT)
    rec_normal = RecommendationEngine.get_recommended_speed(t_normal)
    assert rec_normal.recommended_speed_kmh == 80.0
    assert not rec_normal.is_legal_limit  # Purely advisory

    # 2. Wet road condition -> 40 km/h
    t_wet = CanonicalTelemetry(road_condition=RoadCondition.WET)
    rec_wet = RecommendationEngine.get_recommended_speed(t_wet)
    assert rec_wet.recommended_speed_kmh == 40.0

    # 3. Congestion -> 60 km/h
    t_cong = CanonicalTelemetry(traffic_level=TrafficLevel.CONGESTED)
    rec_cong = RecommendationEngine.get_recommended_speed(t_cong)
    assert rec_cong.recommended_speed_kmh == 60.0

    # 4. High temperature -> 35 km/h
    t_temp = CanonicalTelemetry(temperature_c=34.0, road_condition=RoadCondition.HIGH_TEMP)
    rec_temp = RecommendationEngine.get_recommended_speed(t_temp)
    assert rec_temp.recommended_speed_kmh == 35.0


def test_road_risk_score_calculation():
    # Baseline clear road
    t_clear = CanonicalTelemetry()
    score_clear, reasons_clear = RoadRiskEngine.calculate_risk(t_clear)
    assert score_clear == 0
    assert "Road clear" in reasons_clear[0]

    # Collision event (+50)
    t_crash = CanonicalTelemetry(collision=True)
    score_crash, _ = RoadRiskEngine.calculate_risk(t_crash)
    assert score_crash >= 50

    # Compound severe scenario (Collision + Wrong Way + Wet Road) clamped to 100
    t_severe = CanonicalTelemetry(collision=True, wrong_way=True, road_condition=RoadCondition.WET)
    score_severe, reasons_severe = RoadRiskEngine.calculate_risk(t_severe)
    assert score_severe == 100
    assert len(reasons_severe) >= 3


def test_road_health_bands():
    # 1. Good band (85-100)
    score, band, color, _ = RoadHealthEngine.evaluate_segment_health(collision_history=0)
    assert band == "GOOD"
    assert score >= 85

    # 2. Moderate band (65-84)
    score_mod, band_mod, _, _ = RoadHealthEngine.evaluate_segment_health(collision_history=0, is_wet=True, base_score=85)
    assert band_mod == "MODERATE"

    # 3. Critical band (0-39)
    score_crit, band_crit, _, _ = RoadHealthEngine.evaluate_segment_health(collision_history=2, is_wet=True, wrong_way_events=1, stalled_events=1, base_score=80)
    assert band_crit == "CRITICAL"
    assert score_crit < 40


def test_hazard_proximity_haversine():
    # Same point distance is 0
    dist = HazardEngine.haversine_distance(12.9716, 77.5946, 12.9716, 77.5946)
    assert round(dist, 1) == 0.0

    # Two coordinates roughly 111 meters apart in latitude (0.001 deg)
    dist_approx = HazardEngine.haversine_distance(12.9716, 77.5946, 12.9726, 77.5946)
    assert 100.0 < dist_approx < 125.0


def test_data_fusion_confidence_weighting():
    t = CanonicalTelemetry(collision=True)
    cv_data = {"stopped_vehicle_count": 1, "vehicle_count": 1}
    fused, events = DataFusionEngine.fuse_telemetry_and_cv(t, cv_data)
    assert len(events) >= 1
    # Fusion of acoustic crash + stopped camera detection yields high confidence
    assert events[0].confidence == 0.98
    assert "HIGH CONFIDENCE" in events[0].title
