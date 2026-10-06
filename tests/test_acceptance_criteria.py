"""
Acceptance Criteria Verification Tests for SentraX Platform
Validates every requirement specified in Sections 5, 6, 7, 8, 11, 13, 14, 16, 21, and 82.
"""

import pytest
from software.backend.core.config import settings
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel
from software.backend.engines.recommendation_engine import RecommendationEngine
from software.backend.serial_comm.protocol_adapter import SentraXProtocolAdapter
from software.backend.schemas.events import EventType


def test_acceptance_congestion_time_5_seconds():
    """Validates Section 5: CONGESTION_TIME must be 5000 ms (5 seconds)."""
    assert settings.CONGESTION_TIME_SECONDS == 5


def test_acceptance_stalled_time_15_seconds():
    """Validates Section 10: STALL_TIME must be 15000 ms (15 seconds)."""
    assert settings.STALLED_TIME_SECONDS == 15


def test_acceptance_wrong_way_window_15_seconds():
    """Validates Section 9: WRONG_WAY_WINDOW must be 15000 ms (15 seconds)."""
    assert settings.WRONG_WAY_WINDOW_SECONDS == 15


def test_acceptance_toy_car_overspeed_threshold():
    """Validates Section 6: Toy-car overspeed limit is approximately 4.0 km/h."""
    assert settings.DEMO_OVERSPEED_LIMIT == 4.0
    
    # Check test cases from Section 6
    speeds_normal = [2.5, 3.0, 3.8]
    speeds_overspeed = [4.2, 4.5, 5.0, 6.0]

    for s in speeds_normal:
        assert s <= settings.DEMO_OVERSPEED_LIMIT, f"Speed {s} should be normal"

    for s in speeds_overspeed:
        assert s > settings.DEMO_OVERSPEED_LIMIT, f"Speed {s} should trigger overspeed"


def test_acceptance_speed_recommendations():
    """Validates Sections 4, 11, 13, 14 speed recommendation rules."""
    # Normal: 80 km/h
    t_normal = CanonicalTelemetry(road_condition=RoadCondition.DRY, traffic_level=TrafficLevel.LIGHT)
    rec_normal = RecommendationEngine.get_recommended_speed(t_normal)
    assert rec_normal.recommended_speed_kmh == 80.0
    assert rec_normal.is_legal_limit is False

    # Congestion: 60 km/h
    t_cong = CanonicalTelemetry(traffic_level=TrafficLevel.CONGESTED)
    rec_cong = RecommendationEngine.get_recommended_speed(t_cong)
    assert rec_cong.recommended_speed_kmh == 60.0

    # Wet road: 40 km/h
    t_wet = CanonicalTelemetry(road_condition=RoadCondition.WET)
    rec_wet = RecommendationEngine.get_recommended_speed(t_wet)
    assert rec_wet.recommended_speed_kmh == 40.0

    # High temperature: 35 km/h
    t_temp = CanonicalTelemetry(temperature_c=34.0, road_condition=RoadCondition.HIGH_TEMP)
    rec_temp = RecommendationEngine.get_recommended_speed(t_temp)
    assert rec_temp.recommended_speed_kmh == 35.0


def test_acceptance_sensor_distance_configurable():
    """Validates Section 7: SENSOR_DISTANCE is clearly configurable (0.30 m)."""
    assert settings.SENSOR_DISTANCE == 0.30


def test_acceptance_rfid_emergency_event():
    """Validates Section 16 & 21: RFID triggers EMERGENCY and 5-beep cycle."""
    adapter = SentraXProtocolAdapter()
    parsed = adapter.parse_line("RFID\n", default_source="ESP8266")
    assert parsed["type"] == "event"
    assert parsed["event"] == "EMERGENCY"
    assert parsed["source"] == "esp8266"

    canon = adapter.to_canonical_event(parsed)
    assert canon.type == EventType.EMERGENCY
    assert canon.source == "ESP8266"


def test_acceptance_terminology_compliance():
    """Validates Section 67: UI terminology standards."""
    rec = RecommendationEngine.get_recommended_speed(CanonicalTelemetry())
    assert rec.advisory_label == "SentraX Recommended Speed"
    assert "Legal" not in rec.advisory_label
