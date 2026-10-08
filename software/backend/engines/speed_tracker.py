"""
SentraX Vehicle Speed Reading Tracker
Turns the ESP32's latched speed value into a timed "speed reading".

The ESP32 telemetry `speed` field keeps the last measured (or test) speed indefinitely, so a
single 120 km/h reading would otherwise be shown, and scored as overspeed, until the next one.
A reading is shown for SPEED_READING_HOLD_SECONDS after it arrives, matching the ESP32's own
E-Ink speed display, and then measured speed returns to 0.0 (no vehicle being measured).
"""

import threading
import time
from typing import Optional

from software.backend.core.config import settings
from software.backend.schemas.telemetry import CanonicalTelemetry


class SpeedTracker:
    def __init__(self, hold_seconds: float = settings.SPEED_READING_HOLD_SECONDS):
        self.hold_seconds = hold_seconds
        self._last_raw: Optional[float] = None
        self._value = 0.0
        self._at = 0.0
        self._lock = threading.Lock()  # serial readers run on their own threads

    def reset_link(self) -> None:
        """New hardware connection: a speed already latched on the ESP32 is an old reading."""
        with self._lock:
            self._last_raw = None

    def record(self, speed: float, now: Optional[float] = None) -> None:
        """A new reading, e.g. a test vehicle speed sent from the hardware console."""
        now = time.time() if now is None else now
        with self._lock:
            # _last_raw keeps tracking the hardware: when the ESP32 applies this test speed,
            # its latched value changes and simply restarts the same reading.
            self._value = float(speed)
            self._at = now

    def clear(self) -> None:
        """Demo reset: drop the current reading. The latched raw value is kept so the
        next packet repeating it is not mistaken for a new reading."""
        with self._lock:
            self._value = 0.0
            self._at = 0.0

    def observe_packet(self, raw_speed: float, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        raw = float(raw_speed or 0.0)
        with self._lock:
            is_new = self._last_raw is not None and raw > 0 and raw != self._last_raw
            self._last_raw = raw
            if is_new:
                self._value = raw
                self._at = now

    def current(self, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        with self._lock:
            return self._value if now - self._at < self.hold_seconds else 0.0

    def apply(self, telemetry: CanonicalTelemetry) -> CanonicalTelemetry:
        telemetry.measured_speed_kmh = self.current()
        return telemetry


speed_tracker = SpeedTracker()
