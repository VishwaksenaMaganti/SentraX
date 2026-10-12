"""
SentraX Hardware Sync
Keeps the app and the ESP32 road controller showing the same alerts.

Hardware -> app: the BLE and USB serial link managers call wake() after every packet or event,
and the perception loop fuses and broadcasts straight away. The app gets one telemetry stream,
as fast as the ESP32 sends it.

App -> hardware: Test lab conditions and camera AI detections are pushed to the ESP32, so the
LED strip and E-Ink sign show them too.
  - Firmware v2 (its telemetry carries "fw") takes the whole set: "APP:<alerts>" stays until
    replaced, "CAM:<alerts>" expires 6 s after the last time it was sent.
  - Older firmware shows one dashboard alert at a time and drops it after 10 s, so it gets
    "ALERT:<most urgent>", re-sent every 8 s while it should stay up.
  - The very first firmware ran every command inside its Bluetooth task: an E-Ink redraw or the
    emergency LED sweep there stalled Bluetooth for seconds and killed the link. Until it is
    reflashed it gets one alert command at a time, at least 4 s apart, never re-sent, and no
    test-speed commands. Firmware that queues commands reports "ledr" (or "fw").
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from software.backend.core.sensors import ALERT_BITS, alert_name, by_priority

logger = logging.getLogger("sentrax.hardware_sync")

# Camera AI event types that reach the road sign, and the alert each raises on it
CAMERA_TO_ALERT = {"OVERSPEED": "OVERSPEED", "STALLED": "STALLED", "WRONG_WAY": "WRONG_WAY",
                   "EMERGENCY_VEHICLE": "EMERGENCY"}
# Alerts older firmware accepts as "ALERT:<name>" (it has no overspeed command)
LEGACY_ALERTS = {"COLLISION", "WRONG_WAY", "EMERGENCY", "STALLED", "CONGESTION", "WET_ROAD",
                 "HIGH_TEMP", "HIGH_HUMIDITY"}


class HardwareSync:
    CAM_SEEN_S = 4.0          # a camera alert stays on the sign this long after its last sighting
    CAM_REFRESH_S = 3.0       # firmware v2 drops camera alerts 6 s after the last CAM: command
    LEGACY_REFRESH_S = 8.0    # older firmware drops a dashboard alert after 10 s
    UNQUEUED_GAP_S = 4.0      # firmware running commands in its Bluetooth task: one per 4 s

    def __init__(self):
        self._send: Optional[Callable[[str], Awaitable[bool]]] = None
        self._firmware_v2: Callable[[], bool] = lambda: False
        self._commands_queued: Callable[[], bool] = lambda: False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._wake: Optional[asyncio.Event] = None
        self._events: deque = deque(maxlen=20)
        self.lab_alerts: List[str] = []
        self._lab_speed: Optional[float] = None
        self._lab_synced = True
        self._cam_seen: Dict[str, float] = {}
        self.cam_alerts: List[str] = []
        self._cam_sent: List[str] = []
        self._cam_sent_at = 0.0
        self._legacy_sent: Optional[str] = None
        self._legacy_at = 0.0
        self._sync_lock = asyncio.Lock()  # a Test lab push and the perception loop must not both send

    def bind(self, send: Callable[[str], Awaitable[bool]], firmware_v2: Callable[[], bool],
             commands_queued: Optional[Callable[[], bool]] = None):
        """Called once from the running event loop: how to write a command, and the firmware type."""
        self._send = send
        self._firmware_v2 = firmware_v2
        self._commands_queued = commands_queued or firmware_v2
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()

    # ------------------------------------------------------------------ hardware -> app
    def wake(self):
        """New telemetry or an event is waiting: run the perception loop now. Thread-safe."""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            same_loop = asyncio.get_running_loop() is self._loop
        except RuntimeError:
            same_loop = False
        if same_loop:
            self._wake.set()
        else:
            self._loop.call_soon_threadsafe(self._wake.set)

    def post_event(self, event: Any):
        """Queues an event to go out with the next broadcast. Thread-safe."""
        self._events.append(event)
        self.wake()

    def pop_event(self) -> Optional[Any]:
        try:
            return self._events.popleft()
        except IndexError:
            return None

    async def wait(self, timeout: float):
        """Sleeps until wake() or the timeout, whichever comes first."""
        if self._wake is None:
            await asyncio.sleep(timeout)
            return
        try:
            await asyncio.wait_for(self._wake.wait(), timeout)
        except asyncio.TimeoutError:
            pass
        self._wake.clear()

    def link_up(self):
        """A (re)connected ESP32 has lost anything pushed before: send it all again."""
        self._lab_synced = not self.lab_alerts and self._lab_speed is None
        self._cam_sent = []
        self._legacy_sent = None

    # ------------------------------------------------------------------ app -> hardware
    async def push_lab(self, alerts: Iterable[str], speed: Optional[float] = None) -> bool:
        """The Test lab's conditions changed: show the same alerts (and test speed) on the hardware."""
        self.lab_alerts = by_priority(alert_name(a) for a in alerts)
        if speed is not None and speed != self._lab_speed and self._commands_queued():
            self._lab_speed = float(speed)
            await self._command(f"SPEED:{self._lab_speed:.1f}")
        if not self.lab_alerts:
            self._lab_speed = None
        async with self._sync_lock:
            ok = await self._sync_lab()
            self._lab_synced = ok
        return ok

    def forget_lab(self):
        """The Test lab was reset with a clear-all command that already wiped the sign."""
        self.lab_alerts, self._lab_speed, self._lab_synced = [], None, True
        self._legacy_sent = None

    async def _sync_lab(self) -> bool:
        if self._firmware_v2():
            return await self._command("APP:" + ",".join(self.lab_alerts))
        return await self._sync_legacy(time.time())

    async def tick(self, now: float, cv_stats: Dict[str, Any], camera_live: bool, linked: bool):
        """Runs every perception cycle: camera detections and refreshes for older firmware."""
        self._update_camera(now, cv_stats if camera_live else {})
        if not linked:
            return
        async with self._sync_lock:
            if not self._lab_synced:
                self._lab_synced = await self._sync_lab()
            if self._firmware_v2():
                await self._sync_camera_v2(now)
            else:
                await self._sync_legacy(now)

    def _update_camera(self, now: float, cv_stats: Dict[str, Any]):
        for e in cv_stats.get("camera_events") or []:
            alert = CAMERA_TO_ALERT.get(str(e.get("type", "")))
            if alert:
                self._cam_seen[alert] = now
        self.cam_alerts = [a for a in ALERT_BITS if now - self._cam_seen.get(a, -1e9) < self.CAM_SEEN_S]

    async def _sync_camera_v2(self, now: float):
        if self.lab_alerts:
            return  # the Test lab owns the sign while it is on
        new = set(self.cam_alerts) - set(self._cam_sent)
        if new or (self.cam_alerts and now - self._cam_sent_at >= self.CAM_REFRESH_S):
            if await self._command("CAM:" + ",".join(self.cam_alerts)):
                self._cam_sent, self._cam_sent_at = list(self.cam_alerts), now
        elif not self.cam_alerts:
            self._cam_sent = []  # the firmware lets them expire by itself

    async def _sync_legacy(self, now: float) -> bool:
        wanted = [a for a in (self.lab_alerts or self.cam_alerts) if a in LEGACY_ALERTS]
        target = wanted[0] if wanted else None
        queued = self._commands_queued()
        if target == self._legacy_sent:
            # Re-sending restarts the alert; never the emergency LED sweep, never on unqueued firmware
            if target is None or not queued or target == "EMERGENCY" or now - self._legacy_at < self.LEGACY_REFRESH_S:
                return True
        if not queued and now - self._legacy_at < self.UNQUEUED_GAP_S:
            return False  # tick() sends the latest state once the gap has passed
        ok = await self._command(f"ALERT:{target}" if target else "ALERT:CLEAR")
        if ok:
            self._legacy_sent, self._legacy_at = target, now
        return ok

    async def _command(self, cmd: str) -> bool:
        if self._send is None:
            return False
        try:
            return bool(await self._send(cmd))
        except Exception as e:
            logger.warning("Could not send %r to the ESP32: %s", cmd, e)
            return False


hardware_sync = HardwareSync()
