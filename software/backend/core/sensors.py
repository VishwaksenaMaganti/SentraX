"""
Sensor reading helpers shared by every telemetry path (BLE, USB serial, browser ingest).
"""

import time
from collections import deque
from typing import Any, List, Optional, Tuple

from software.backend.core.config import settings


def read_ir(raw: Any, already_corrected: bool = False) -> List[int]:
    """Returns the four IR occupancy flags (1 = vehicle present).

    Older firmware reports IR inverted, so IR_INVERTED flips it here. Firmware that already
    reads the modules correctly sends "irfix": 1 and is passed through unchanged.
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
