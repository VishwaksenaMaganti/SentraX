"""
Tests for the hardware link: packet decoding (current and v2 firmware), event holds,
pushing Test lab / camera alerts to the ESP32, and BLE notification reassembly.
"""

import asyncio
import json

from software.backend.core.sensors import HardwarePacketDecoder, Hysteresis, mask_to_alerts, ALERT_BITS
from software.backend.engines.hardware_sync import HardwareSync
from software.backend.schemas.telemetry import RoadCondition, TrafficLevel


def legacy_packet(**kw):
    p = {"ir": [0, 0, 0, 0], "irfix": 1, "temp": 26.0, "hum": 55, "moist": 4095, "sound": 0,
         "sndfix": 1, "rfid": 0, "speed": 0.0, "rec_speed": 80, "alert": "NORMAL"}
    p.update(kw)
    return p


def mask(*names):
    return sum(1 << ALERT_BITS.index(n) for n in names)


# ---------------------------------------------------------------- decoding
def test_hysteresis_holds_near_the_limit():
    h = Hysteresis(30.0, 29.0)
    assert [h.update(v) for v in (29.9, 30.0, 29.5, 29.1, 28.9, 29.5)] == [False, True, True, True, False, False]
    wet = Hysteresis(2000, 2300, above=False)
    assert [wet.update(v) for v in (2100, 1900, 2200, 2400)] == [False, True, True, False]


def test_legacy_heat_does_not_flicker_at_30c():
    d = HardwarePacketDecoder()
    flags = [d.decode(legacy_packet(temp=t), now=100 + i).heat_alert for i, t in enumerate((29.9, 30.1, 29.8, 29.6, 30.0))]
    assert flags == [False, True, True, True, True]


def test_legacy_congestion_needs_15s_of_blocked_lanes():
    d = HardwarePacketDecoder()
    t0 = d.decode(legacy_packet(ir=[1, 1, 0, 0]), now=1000)
    assert t0.traffic_level == TrafficLevel.MODERATE
    t1 = d.decode(legacy_packet(ir=[1, 1, 0, 0]), now=1016)
    assert t1.traffic_level == TrafficLevel.CONGESTED and "CONGESTION" in t1.hw_alerts
    t2 = d.decode(legacy_packet(ir=[1, 0, 0, 0]), now=1017)
    assert t2.traffic_level == TrafficLevel.LIGHT


def test_missing_moisture_reading_is_not_wet():
    d = HardwarePacketDecoder()
    assert d.decode(legacy_packet(moist=0), now=5).road_condition == RoadCondition.DRY
    assert d.decode(legacy_packet(moist=1500), now=6).road_condition == RoadCondition.WET


def test_v2_masks_are_authoritative_and_advisory_matches_sign():
    d = HardwarePacketDecoder()
    p = legacy_packet(temp=35.0, moist=1000, fw="2.0", up=50, dc=1, dr=0x08, rst=1, cal=2,
                      am=mask("WET_ROAD", "STALLED"), hm=mask("WET_ROAD"), rec_speed=30)
    t = d.score(d.decode(p, now=10))
    assert t.hw_alerts == ["WET_ROAD", "STALLED"]
    assert t.pushed_alerts == ["STALLED"]
    assert t.stalled_vehicle and t.road_condition == RoadCondition.WET
    assert not t.heat_alert  # 35 °C, but the calibrated ESP32 did not call it hot
    assert t.recommended_speed_kmh == 30.0  # same table as the sign, no risk-score ceiling
    assert d.firmware == "2.0"
    assert d.diag["last_drop_reason"].startswith("radio link timeout")
    assert d.diag["calibration"] == "calibrated"


def test_event_is_held_until_telemetry_catches_up():
    d = HardwarePacketDecoder()
    t = d.score(d.decode(legacy_packet(), now=100))
    name = d.note_event("RASH", True, now=100.5)
    assert name == "OVERSPEED"
    t2 = d.refresh(t, name, True, now=100.5)
    assert t2.overspeed_alert and t2.hw_alerts == ["OVERSPEED"]
    # older firmware is still redrawing; its next packets do not mention the alert yet
    assert d.decode(legacy_packet(), now=104).overspeed_alert
    assert not d.decode(legacy_packet(), now=108).overspeed_alert
    d.note_event("WET", True, now=200)
    d.note_event("NORMAL", True, now=201)
    assert not d.decode(legacy_packet(), now=202).hw_alerts


def test_mask_helpers():
    assert mask_to_alerts(mask("COLLISION", "CONGESTION")) == ["COLLISION", "CONGESTION"]
    assert mask_to_alerts("junk") == []


# ---------------------------------------------------------------- app -> hardware
class FakeLink:
    def __init__(self, v2):
        self.sent = []
        self.v2 = v2

    async def send(self, cmd):
        self.sent.append(cmd)
        await asyncio.sleep(0)  # a real BLE write yields to the event loop
        return True


def make_sync(v2, queued=True):
    link = FakeLink(v2)
    s = HardwareSync()
    s._send = link.send
    s._firmware_v2 = lambda: link.v2
    s._commands_queued = lambda: link.v2 or queued
    return s, link


CAMERA_STALL = {"camera_events": [{"type": "STALLED"}]}


def test_legacy_lab_push_sends_most_urgent_and_refreshes():
    async def run():
        s, link = make_sync(v2=False)
        await s.push_lab(["wet", "collision"], speed=55)
        assert link.sent == ["SPEED:55.0", "ALERT:COLLISION"]
        await s.tick(s._legacy_at + 2, {}, False, True)
        assert len(link.sent) == 2
        await s.tick(s._legacy_at + 9, {}, False, True)
        assert link.sent[-1] == "ALERT:COLLISION"
        await s.push_lab([])
        assert link.sent[-1] == "ALERT:CLEAR"
    asyncio.run(run())


def test_v2_lab_push_sends_the_whole_set():
    async def run():
        s, link = make_sync(v2=True)
        await s.push_lab(["HIGH_TEMP", "WET_ROAD"])
        assert link.sent == ["APP:WET_ROAD,HIGH_TEMP"]
        s.link_up()  # ESP32 reconnected: it lost the set
        await s.tick(10.0, {}, False, True)
        assert link.sent[-1] == "APP:WET_ROAD,HIGH_TEMP"
    asyncio.run(run())


def test_camera_alerts_reach_v2_firmware_only_from_a_live_camera():
    async def run():
        s, link = make_sync(v2=True)
        await s.tick(1.0, CAMERA_STALL, False, True)   # synthetic scene
        assert link.sent == []
        await s.tick(2.0, CAMERA_STALL, True, True)
        assert link.sent == ["CAM:STALLED"]
        await s.tick(3.0, CAMERA_STALL, True, True)    # unchanged, not yet due
        assert len(link.sent) == 1
        await s.tick(5.5, {}, True, True)               # still within 4 s of the sighting: refresh
        assert link.sent[-1] == "CAM:STALLED"
        await s.push_lab(["COLLISION"])
        await s.tick(6.0, {"camera_events": [{"type": "EMERGENCY_VEHICLE"}]}, True, True)
        assert link.sent[-1] == "APP:COLLISION"         # the Test lab owns the sign
    asyncio.run(run())


def test_unqueued_firmware_gets_one_command_at_a_time():
    async def run():
        s, link = make_sync(v2=False, queued=False)
        await s.push_lab(["WRONG_WAY"], speed=50)
        assert link.sent == ["ALERT:WRONG_WAY"]          # no SPEED: its E-Ink redraw stalls Bluetooth
        t0 = s._legacy_at
        await s.push_lab(["EMERGENCY"], speed=45)
        assert link.sent == ["ALERT:WRONG_WAY"]          # too soon: held back
        await s.tick(t0 + 4.5, {}, False, True)
        assert link.sent == ["ALERT:WRONG_WAY", "ALERT:EMERGENCY"]
        await s.tick(t0 + 30, {}, False, True)
        assert len(link.sent) == 2                         # never re-sent
    asyncio.run(run())


def test_camera_alert_on_legacy_firmware_clears_when_unseen():
    async def run():
        s, link = make_sync(v2=False)
        await s.tick(1.0, {"camera_events": [{"type": "WRONG_WAY"}, {"type": "OVERSPEED"}]}, True, True)
        assert link.sent == ["ALERT:WRONG_WAY"]
        await s.tick(6.0, {}, True, True)
        assert link.sent[-1] == "ALERT:CLEAR"
    asyncio.run(run())


# ---------------------------------------------------------------- BLE reassembly
def make_ble(monkeypatch):
    import software.backend.ble.live_ble_service as ble
    for fn in ("save_telemetry", "save_event", "update_device_status"):
        monkeypatch.setattr(ble, fn, lambda *a, **k: None)
    monkeypatch.setattr(ble, "hw_decoder", HardwarePacketDecoder())
    m = ble.LiveBLEManager()
    m.is_connected = True
    return m


def test_ble_reassembles_chunked_telemetry(monkeypatch):
    m = make_ble(monkeypatch)
    raw = (json.dumps(legacy_packet(alert="WRONG_WAY", ir=[0, 0, 1, 0])) + "\n").encode()
    for i in range(0, len(raw), 20):
        m._on_telemetry_packet(0, bytearray(raw[i:i + 20]))
    t = m.latest_live_telemetry
    assert t is not None and t.wrong_way and t.ir_sensors == [False, False, True, False]
    assert m._rx_buffer == ""


def test_ble_events_from_both_firmware_generations(monkeypatch):
    m = make_ble(monkeypatch)
    m._on_telemetry_packet(0, bytearray((json.dumps(legacy_packet()) + "\n").encode()))
    m._on_event_packet(0, bytearray(b"WET"))                          # older firmware
    assert m.latest_live_telemetry.road_condition == RoadCondition.WET
    line = (json.dumps({"ev": "HIGH_TEMP", "on": 1, "src": "cam"}) + "\n").encode()
    m._on_event_packet(0, bytearray(line[:15]))                       # v2, split across chunks
    m._on_event_packet(0, bytearray(line[15:]))
    t = m.latest_live_telemetry
    assert t.heat_alert and "HIGH_TEMP" in t.pushed_alerts


def test_flashed_firmware_ir_is_not_flipped_and_led_alignment_is_read():
    d = HardwarePacketDecoder()
    t = d.decode(legacy_packet(ir=[1, 0, 0, 0], irfix=1, ledr=18, ledw=0), now=1)
    assert t.ir_sensors == [True, False, False, False]
    assert d.led_right == 18 and d.led_swap is False
    empty = HardwarePacketDecoder().decode({"ir": [0, 0, 0, 0], "alert": "NORMAL"}, now=1)
    assert empty.traffic_count == 0  # older packets without irfix pass through too


def test_push_and_loop_tick_do_not_send_twice():
    async def run():
        s, link = make_sync(v2=False, queued=False)
        await asyncio.gather(s.push_lab(["WET_ROAD"]), s.tick(100.0, {}, False, True))
        assert link.sent == ["ALERT:WET_ROAD"]
    asyncio.run(run())
