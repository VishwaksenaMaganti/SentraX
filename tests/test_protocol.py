"""
Tests for SentraX Serial Protocol Adapter and BLE Packet Encoding
"""

import pytest
from software.backend.serial_comm.protocol_adapter import SentraXProtocolAdapter
from software.backend.schemas.events import EventType, EventSeverity
from software.backend.ble.adapter import BLEPacketEncoder
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel


def test_serial_speed_parsing():
    adapter = SentraXProtocolAdapter()
    res = adapter.parse_line("SPEED:4.8\n")
    assert res is not None
    assert res["type"] == "speed"
    assert res["value"] == 4.8
    assert res["source"] == "esp32"


def test_serial_limit_parsing():
    adapter = SentraXProtocolAdapter()
    res = adapter.parse_line("LIMIT:60\n")
    assert res is not None
    assert res["type"] == "recommended_speed"
    assert res["value"] == 60.0


def test_serial_congestion_event_parsing():
    adapter = SentraXProtocolAdapter()
    res = adapter.parse_line("CONGESTION\n")
    assert res is not None
    assert res["type"] == "event"
    assert res["event"] == "CONGESTION"

    canon = adapter.to_canonical_event(res)
    assert canon is not None
    assert canon.type == EventType.CONGESTION
    assert canon.severity == EventSeverity.WARNING


def test_serial_rfid_emergency_parsing():
    adapter = SentraXProtocolAdapter()
    res = adapter.parse_line("RFID\n", default_source="ESP8266")
    assert res is not None
    assert res["type"] == "event"
    assert res["event"] == "EMERGENCY"
    assert res["source"] == "esp8266"


def test_serial_state_prefix_compatibility():
    adapter = SentraXProtocolAdapter()
    res = adapter.parse_line("STATE:COLLISION\n")
    assert res is not None
    assert res["type"] == "event"
    assert res["event"] == "COLLISION"
    assert res["severity"] == "CRITICAL"


def test_ble_packet_encoder():
    data = {"device_id": "SENTRAX-ESP32", "speed": 4.5, "status": "ONLINE"}
    encoded = BLEPacketEncoder.encode_telemetry(data)
    assert isinstance(encoded, bytes)
    decoded = BLEPacketEncoder.decode_telemetry(encoded)
    assert decoded["speed"] == 4.5
    assert decoded["device_id"] == "SENTRAX-ESP32"


def test_telemetry_state_application():
    adapter = SentraXProtocolAdapter()
    base_t = CanonicalTelemetry()
    
    # Test Wet event application
    wet_msg = adapter.parse_line("WET\n")
    updated = adapter.apply_to_telemetry(wet_msg, base_t)
    assert updated.road_condition == RoadCondition.WET
    assert updated.recommended_speed_kmh == 40.0

    # Test Congestion event application
    cong_msg = adapter.parse_line("CONGESTION\n")
    updated2 = adapter.apply_to_telemetry(cong_msg, base_t)
    assert updated2.traffic_level == TrafficLevel.CONGESTED
    assert updated2.recommended_speed_kmh == 60.0
