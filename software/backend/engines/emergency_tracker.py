"""
SentraX Emergency Vehicle Tracker
Turns the ESP32's RFID signals into a timed "emergency vehicle present" state.

The ESP32 telemetry `rfid` flag is latched: after the first tag scan it stays 1 until the
controller is reset from the dashboard, so it cannot be read as "a vehicle is here now".
Instead, emergency is shown for EMERGENCY_HOLD_SECONDS after each detection, where a
detection is any of:
  - the BLE "EMERGENCY" event notification (sent on every tag scan),
  - the telemetry `rfid` flag changing 0 -> 1,
  - telemetry reporting alert == "EMERGENCY" (e.g. a manual dashboard trigger),
  - a manual EMERGENCY trigger from the hardware command console,
  - an "RFID" line from a directly connected ESP8266.
"""

import threading
import time
from typing import Optional

from software.backend.core.config import settings
from software.backend.schemas.telemetry import CanonicalTelemetry


class EmergencyTracker:
    def __init__(self, hold_seconds: float = settings.EMERGENCY_HOLD_SECONDS):
        self.hold_seconds = hold_seconds
        self._until = 0.0
        self._last_rfid: Optional[bool] = None
        self._lock = threading.Lock()  # serial readers run on their own threads

    def trigger(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._until = max(self._until, now + self.hold_seconds)

    def clear(self) -> None:
        with self._lock:
            self._until = 0.0

    def reset_link(self) -> None:
        """New hardware connection: the first packet's rfid level is not a fresh scan."""
        with self._lock:
            self._last_rfid = None

    def observe_packet(self, rfid_flag: bool, alert: str, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        rising_edge = False
        with self._lock:
            if rfid_flag and self._last_rfid is False:
                rising_edge = True
            self._last_rfid = bool(rfid_flag)
        if alert == "EMERGENCY":
            # Reported while the ESP32's alert is live (e.g. a manual trigger held on the board)
            self.trigger(now)
        elif rising_edge and not self.is_active(now):
            # Over BLE the scan's event notification usually arrives first; the flag change
            # after the ESP32's silent alert sequence belongs to the same scan, so don't extend.
            self.trigger(now)

    def is_active(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            return now < self._until

    def apply(self, telemetry: CanonicalTelemetry) -> CanonicalTelemetry:
        active = self.is_active()
        telemetry.rfid_active = active
        telemetry.emergency_vehicle = active
        return telemetry


emergency_tracker = EmergencyTracker()
