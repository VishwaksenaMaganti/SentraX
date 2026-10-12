"""
Sensor reading helpers shared by every telemetry path (BLE, USB serial, browser ingest).
"""

import logging
import threading
import time
from collections import deque
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from software.backend.core.config import settings
from software.backend.schemas.telemetry import (
    CanonicalTelemetry, ConnectionState, RoadCondition, TrafficLevel, DeviceSource
)
from software.backend.engines.emergency_tracker import emergency_tracker
from software.backend.engines.speed_tracker import speed_tracker

logger = logging.getLogger("sentrax.sensors")

# Alert order shared with ESP32 firmware v2 (its AlertType enum): bit i of the "am"/"hm" masks
ALERT_BITS = ("NORMAL", "COLLISION", "WRONG_WAY", "EMERGENCY", "OVERSPEED", "WET_ROAD",
              "HIGH_TEMP", "HIGH_HUMIDITY", "STALLED", "CONGESTION")
TRANSIENT_ALERTS = {"COLLISION", "WRONG_WAY", "OVERSPEED", "EMERGENCY"}
# Names older firmware uses in its event notifications and dashboard commands
ALERT_ALIASES = {"RASH": "OVERSPEED", "RASH_DRIVING": "OVERSPEED", "WET": "WET_ROAD", "TEMP": "HIGH_TEMP",
                 "HUMIDITY": "HIGH_HUMIDITY", "WRONG": "WRONG_WAY", "RFID": "EMERGENCY", "CLEAR": "NORMAL"}


def alert_name(raw: Any) -> str:
    name = str(raw or "NORMAL").strip().upper()
    return ALERT_ALIASES.get(name, name)


def mask_to_alerts(mask: Any) -> List[str]:
    try:
        bits = int(mask)
    except (TypeError, ValueError):
        return []
    return [name for i, name in enumerate(ALERT_BITS) if i and bits >> i & 1]


def by_priority(alerts: Iterable[str]) -> List[str]:
    return sorted(set(alerts) & set(ALERT_BITS[1:]), key=ALERT_BITS.index)


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_ir(raw: Any, already_corrected: bool = False) -> List[int]:
    """Returns the four IR occupancy flags (1 = vehicle present).

    Firmware reporting IR inverted can be flipped here with IR_INVERTED (off by default: the
    flashed firmware reports correctly). Packets with "irfix": 1 are never flipped.
    """
    if not isinstance(raw, list):
        return [0, 0, 0, 0]  # no IR data in the packet: report clear, not inverted
    flags = [1 if v else 0 for v in raw]
    if settings.IR_INVERTED and not already_corrected:
        flags = [1 - f for f in flags]
    return flags


class SoundFilter:
    """Turns the ESP32 sound flag into a collision signal that ignores mic noise.

    Firmware with the on-board filter sends "sndfix": 1 and its "sound" flag is trusted as-is.
    Older firmware sends the raw mic pin, which flickers on room noise and also raises a COLLISION
    alert on every flicker; for those packets a collision needs the flag set in most recent packets
    (a phone speaker held to the mic), or a collision triggered from the dashboard.
    """

    WINDOW = 5           # recent packets considered (~2 s at the ESP32's 400 ms rate)
    NEEDED = 4           # packets in the window that must report sound
    HOLD_S = 3.0         # keep a confirmed sound visible this long
    MANUAL_GRACE_S = 12.0
    # Old firmware reads the mic with the wrong polarity on some boards, so the flag sits at 1 in
    # a quiet room. A phone-speaker test lasts a few seconds; a flag stuck on longer is the sensor.
    STUCK_S = 10.0

    def __init__(self):
        self._recent = deque(maxlen=self.WINDOW)
        self._confirmed_until = 0.0
        self._manual_until = 0.0
        self._raw_on_since: Optional[float] = None
        self.firmware_filtered = False

    def manual_collision(self, now: Optional[float] = None):
        """A collision was requested from the dashboard: let the hardware's echo of it through."""
        self._manual_until = (now or time.time()) + self.MANUAL_GRACE_S

    def observe(self, raw_sound: Any, alert: str, already_filtered: bool,
                now: Optional[float] = None) -> Tuple[bool, bool]:
        """Returns (sound_active, collision) for one telemetry packet."""
        now = now or time.time()
        self.firmware_filtered = already_filtered
        if already_filtered:
            sound = bool(raw_sound)
            return sound, (alert == "COLLISION" or sound)

        raw = bool(raw_sound)
        if not raw:
            self._raw_on_since = None
        elif self._raw_on_since is None:
            self._raw_on_since = now
        if self._raw_on_since is not None and now - self._raw_on_since > self.STUCK_S:
            self._recent.clear()
            self._confirmed_until = 0.0
            return False, alert == "COLLISION" and now < self._manual_until

        self._recent.append(raw)
        if sum(self._recent) >= self.NEEDED:
            self._confirmed_until = now + self.HOLD_S
        sound = now < self._confirmed_until
        return sound, sound or (alert == "COLLISION" and self.collision_allowed(now))

    def collision_allowed(self, now: Optional[float] = None) -> bool:
        """Whether a COLLISION alert/event from the hardware should be believed right now."""
        now = now or time.time()
        return self.firmware_filtered or now < self._confirmed_until or now < self._manual_until


sound_filter = SoundFilter()


class Hysteresis:
    """A threshold that switches on at `on` and only switches off once past `off`, so a reading
    hovering at the limit (29.9 / 30.0 °C) cannot flip an alert on every packet."""

    def __init__(self, on: float, off: float, above: bool = True):
        self.on, self.off, self.above = on, off, above
        self.state = False

    def update(self, value: Optional[float]) -> bool:
        if value is None:
            return self.state
        if self.above:
            self.state = value > self.off if self.state else value >= self.on
        else:
            self.state = value < self.off if self.state else value < self.on
        return self.state

    def reset(self):
        self.state = False


# HCI disconnect reasons (Bluetooth Core spec, Vol 1 Part F) reported by firmware v2 as "dr"
DISCONNECT_REASONS = {
    0x05: "pairing/authentication failed",
    0x06: "pairing key missing (stale Windows pairing)",
    0x08: "radio link timeout (out of range or interference)",
    0x13: "PC closed the link",
    0x16: "ESP32 closed the link",
    0x22: "link-layer response timeout",
    0x3B: "connection parameters rejected",
    0x3D: "encryption check failed",
    0x3E: "connection failed to establish",
}
# esp_reset_reason() codes reported by firmware v2 as "rst"
RESET_REASONS = {1: "power-on", 2: "reset button", 3: "software restart", 4: "crash (panic)",
                 5: "interrupt watchdog", 6: "task watchdog", 7: "watchdog", 8: "deep sleep",
                 9: "brownout (power dip)", 10: "SDIO reset"}
CALIBRATION_STATES = {0: "factory", 1: "running", 2: "calibrated"}


class HardwarePacketDecoder:
    """Turns one ESP32 telemetry packet into CanonicalTelemetry (shared by BLE and USB serial).

    Firmware v2 reports its own alert decisions as bit masks: "am" is everything the road sign is
    showing, "hm" what its sensors raised (the rest was pushed by the app or camera). Older
    firmware only reports the single alert on the sign, so the rest is derived here, with
    hysteresis so readings near a limit cannot flicker.

    Event notifications arrive before the next telemetry packet (older firmware stalls for
    seconds while it redraws the E-Ink), so note_event() holds an alert until telemetry catches up.
    """

    CONGESTION_S = 15.0       # older firmware: 2+ lanes blocked this long (its CONGESTION_TIME)
    TRANSIENT_HOLD_S = 7.0    # firmware ALERT_TIME
    CONDITION_HOLD_S = 4.0

    def __init__(self):
        self.heat = Hysteresis(30.0, 29.0)
        self.humid = Hysteresis(80.0, 76.0)
        self.wet = Hysteresis(2000, 2300, above=False)
        self._busy_since: Optional[float] = None
        self._holds: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.firmware: Optional[str] = None   # set by firmware v2 packets ("fw")
        self.diag: Dict[str, Any] = {}
        self.led_right: Optional[int] = None   # right-strip alignment rule the ESP32 reports ("ledr")
        self.led_swap = False                  # ...and whether its strip sides are swapped ("ledw")

    def reset_link(self):
        """New hardware connection: forget holds and state learnt from the previous link."""
        with self._lock:
            self._holds.clear()
        self._busy_since = None
        for h in (self.heat, self.humid, self.wet):
            h.reset()
        self.firmware = None
        self.diag = {}
        self.led_right = None

    # ------------------------------------------------------------------ events
    def note_event(self, raw_name: Any, on: bool = True, now: Optional[float] = None) -> str:
        """Records a hardware event notification and returns its canonical alert name."""
        name = alert_name(raw_name)
        now = time.time() if now is None else now
        with self._lock:
            if name == "NORMAL":
                self._holds.clear()
            elif name in ALERT_BITS:
                if on:
                    hold = self.TRANSIENT_HOLD_S if name in TRANSIENT_ALERTS else self.CONDITION_HOLD_S
                    self._holds[name] = now + hold
                else:
                    self._holds.pop(name, None)
        return name

    def held(self, now: Optional[float] = None) -> Set[str]:
        now = time.time() if now is None else now
        with self._lock:
            return {n for n, until in self._holds.items() if until > now}

    def refresh(self, t: CanonicalTelemetry, name: str, on: bool, pushed: bool = False,
                now: Optional[float] = None) -> CanonicalTelemetry:
        """The latest telemetry with a just-received event applied, for an immediate broadcast."""
        now = time.time() if now is None else now
        out = t.model_copy(deep=True)
        active = set(out.hw_alerts)
        pushed_set = set(out.pushed_alerts)
        if name == "NORMAL":
            active.clear()
            pushed_set.clear()
        elif on:
            active.add(name)
            if pushed:
                pushed_set.add(name)
        else:
            active.discard(name)
            pushed_set.discard(name)
        active |= self.held(now)
        self._set_alert_flags(out, active, active - pushed_set)
        out.timestamp = now
        return self.score(out)

    # ------------------------------------------------------------------ packets
    def decode(self, d: Dict[str, Any], now: Optional[float] = None) -> CanonicalTelemetry:
        now = time.time() if now is None else now
        ir_list = read_ir(d.get("ir"), bool(d.get("irfix", 0)))
        alert_str = alert_name(d.get("alert", "NORMAL"))
        sound_on, collision_on = sound_filter.observe(
            d.get("sound", 0), alert_str, bool(d.get("sndfix", 0)), now)
        temp = _num(d.get("temp"), 26.5)
        hum = _num(d.get("hum"), 55.0)
        moist = int(_num(d.get("moist"), 3100))

        if "am" in d:  # firmware v2: the ESP32 decided, using its calibrated thresholds
            active = set(mask_to_alerts(d.get("am")))
            hw = set(mask_to_alerts(d.get("hm"))) & active
        else:
            active = {alert_str} - {"NORMAL"}
            if self.heat.update(temp):
                active.add("HIGH_TEMP")
            if self.humid.update(hum):
                active.add("HIGH_HUMIDITY")
            if moist > 0 and self.wet.update(moist):
                active.add("WET_ROAD")
            if collision_on:
                active.add("COLLISION")
            if sum(ir_list) >= 2:
                if self._busy_since is None:
                    self._busy_since = now
                if now - self._busy_since >= self.CONGESTION_S:
                    active.add("CONGESTION")
            else:
                self._busy_since = None
            hw = set(active)
        # A held event alert came from the sensors, unless telemetry already says it was pushed
        held = self.held(now) - active
        active |= held
        hw |= held

        t = CanonicalTelemetry(
            device_id="SENTRAX-ESP32",
            timestamp=now,
            connection_state=ConnectionState.CONNECTED,
            measured_speed_kmh=_num(d.get("speed", d.get("spd")), 0.0),
            recommended_speed_kmh=_num(d.get("rec_speed", d.get("rec")), 80.0),
            posted_speed_kmh=80.0,
            traffic_count=sum(ir_list),
            temperature_c=temp,
            humidity_pct=hum,
            moisture_raw=moist,
            ir_sensors=[bool(x) for x in ir_list],
            sound_active=sound_on,
            rfid_active=bool(d.get("rfid", 0)),
            night_mode=bool(d.get("night", 0)),
            source=DeviceSource.ESP32,
            is_simulated=False,
            esp32_connected=True,
            both_modules_connected=True,
            hardware_standby=False,
        )
        self._set_alert_flags(t, active, hw)
        # Older firmware latches rfid after a scan; the tracker reads it as an edge
        emergency_tracker.observe_packet(
            t.rfid_active, "EMERGENCY" if "EMERGENCY" in active else alert_str, now)
        emergency_tracker.apply(t)
        # The firmware's speed also stays latched; show each new reading for a few seconds
        speed_tracker.observe_packet(t.measured_speed_kmh, now)
        speed_tracker.apply(t)
        if "ledr" in d:
            self.led_right = int(_num(d.get("ledr"), 18))
            self.led_swap = bool(d.get("ledw", 0))
        self._note_diag(d)
        return t

    @staticmethod
    def _set_alert_flags(t: CanonicalTelemetry, active: Set[str], hw: Set[str]):
        t.alerts_decided = True
        t.collision = "COLLISION" in active
        t.wrong_way = "WRONG_WAY" in active
        t.stalled_vehicle = "STALLED" in active
        t.road_condition = RoadCondition.WET if "WET_ROAD" in active else RoadCondition.DRY
        if "CONGESTION" in active:
            t.traffic_level = TrafficLevel.CONGESTED
        else:
            t.traffic_level = TrafficLevel.MODERATE if t.traffic_count >= 2 else TrafficLevel.LIGHT
        t.heat_alert = "HIGH_TEMP" in active
        t.humid_alert = "HIGH_HUMIDITY" in active
        t.overspeed_alert = "OVERSPEED" in active
        if "EMERGENCY" in active:
            emergency_tracker.trigger()
            emergency_tracker.apply(t)
        t.hw_alerts = by_priority(active)
        t.pushed_alerts = by_priority(active - hw)

    @staticmethod
    def score(t: CanonicalTelemetry) -> CanonicalTelemetry:
        from software.backend.engines.risk_engine import RoadRiskEngine
        from software.backend.engines.recommendation_engine import RecommendationEngine
        t.risk_score, t.risk_reasons = RoadRiskEngine.calculate_risk(t)
        t.recommended_speed_kmh = RecommendationEngine.get_recommended_speed(
            t, t.posted_speed_kmh).recommended_speed_kmh
        return t

    def _note_diag(self, d: Dict[str, Any]):
        """Link and controller health from firmware v2, to explain a dropped connection."""
        if "fw" not in d:
            return
        prev_up = self.diag.get("uptime_s")
        drops = int(_num(d.get("dc"), 0))
        reason = int(_num(d.get("dr"), 0))
        diag = {
            "firmware": str(d.get("fw")),
            "uptime_s": int(_num(d.get("up"), 0)),
            "link_drops_since_boot": drops,
            "last_drop_reason": (DISCONNECT_REASONS.get(reason, f"code 0x{reason:02X}") if drops else None),
            "last_reset": RESET_REASONS.get(int(_num(d.get("rst"), 0)), "unknown"),
            "calibration": CALIBRATION_STATES.get(int(_num(d.get("cal"), 0)), "factory"),
            "free_heap_kb": int(_num(d.get("heap"), 0)),
        }
        if self.firmware is None:
            logger.info("ESP32 firmware %s, up %d s, %d Bluetooth drops since boot%s, last reset: %s",
                        diag["firmware"], diag["uptime_s"], drops,
                        f" (last: {diag['last_drop_reason']})" if drops else "", diag["last_reset"])
        elif prev_up is not None and diag["uptime_s"] + 5 < prev_up:
            logger.warning("ESP32 restarted (reset reason: %s)", diag["last_reset"])
        self.firmware = diag["firmware"]
        self.diag = diag


hw_decoder = HardwarePacketDecoder()
