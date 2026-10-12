"""
SentraX Live Bluetooth Low Energy (BLE) Client Service
Connects to physical SENTRAX-ESP32 hardware using bleak, subscribes to GATT characteristics,
and streams live physical telemetry into the SentraX platform without simulation.

Packets are decoded by the shared hardware decoder and handed to the perception loop
(hardware_sync.wake), which fuses and broadcasts them, so the app sees a single stream.
The link heals itself: a dropped or silent connection is retried until it comes back.
"""

import asyncio
import json
import logging
import sys
import time
from typing import Optional, Callable, Dict, Any, List

from software.backend.ble.adapter import (
    SENTRAX_SERVICE_UUID, CHAR_TELEMETRY_UUID, CHAR_EVENTS_UUID, CHAR_COMMANDS_UUID
)
from software.backend.schemas.telemetry import CanonicalTelemetry
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.database.models import save_telemetry, save_event, update_device_status
from software.backend.engines.emergency_tracker import emergency_tracker
from software.backend.engines.speed_tracker import speed_tracker
from software.backend.engines.hardware_sync import hardware_sync
from software.backend.core.sensors import hw_decoder, sound_filter, ALERT_BITS

logger = logging.getLogger("sentrax.live_ble")

try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

EVENT_SEVERITY = {
    "COLLISION": EventSeverity.CRITICAL, "WRONG_WAY": EventSeverity.CRITICAL, "EMERGENCY": EventSeverity.CRITICAL,
    "OVERSPEED": EventSeverity.WARNING, "CONGESTION": EventSeverity.WARNING, "STALLED": EventSeverity.WARNING,
    "WET_ROAD": EventSeverity.WARNING, "HIGH_TEMP": EventSeverity.WARNING, "HIGH_HUMIDITY": EventSeverity.WARNING,
}


def _ensure_mta_thread():
    """Undoes a single-threaded (STA) COM apartment on the current (event-loop) thread.

    bleak's WinRT backend only receives callbacks on an MTA thread; on an STA thread every scan
    fails with "Thread is configured for Windows GUI" and connects hang forever. Libraries such
    as OpenCV's DirectShow backend switch whichever thread they run on to STA.
    """
    if sys.platform != "win32":
        return
    import ctypes
    ole32 = ctypes.windll.ole32
    apt_type, qualifier = ctypes.c_int(), ctypes.c_int()
    for _ in range(8):  # CoInitialize is reference-counted; unwind a few nested calls at most
        if ole32.CoGetApartmentType(ctypes.byref(apt_type), ctypes.byref(qualifier)) != 0:
            return  # COM not initialised yet: WinRT will set it up as MTA
        if apt_type.value not in (0, 3):  # APTTYPE_STA / APTTYPE_MAINSTA
            return
        logger.warning("Event-loop thread was in a COM STA apartment; resetting it for Bluetooth")
        ole32.CoUninitialize()


class LiveBLEManager:
    def __init__(self, on_telemetry_broadcast: Optional[Callable] = None):
        self.on_telemetry_broadcast = on_telemetry_broadcast  # kept for callers; the perception loop broadcasts
        self.client: Optional[Any] = None
        self.connected_device_address: Optional[str] = None
        self.connected_device_name: Optional[str] = None
        self.is_connected = False
        self.is_esp8266_connected = False
        self.last_esp8266_heartbeat = 0.0
        self.is_scanning = False
        self.auto_reconnect = True
        self._rx_buffer = ""
        self._event_buffer = ""
        self._reconnect_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self.latest_live_telemetry: Optional[CanonicalTelemetry] = None
        self._discovered_ble_devices: Dict[str, Any] = {}
        self.last_error: str = ""
        self.radio_off = False  # last scan found the PC's Bluetooth switched off
        self.connected_at = 0.0
        self.last_packet_at = 0.0
        self.link_drops: List[Dict[str, Any]] = []   # this session: when each link dropped and why
        self.reconnecting = False
        self._last_event_saved: Dict[str, float] = {}
        # Serialises connect attempts: a dashboard click and the auto-reconnect loop must never
        # drive two BleakClients at the same ESP32 at once (that deadlocks the Windows stack).
        self._connect_lock = asyncio.Lock()

    CONNECT_TIMEOUT_S = 15.0
    NOTIFY_TIMEOUT_S = 6.0
    DISCONNECT_TIMEOUT_S = 5.0
    SILENT_LINK_S = 20.0       # no packet this long = dead link (older firmware goes quiet ~9 s per alert)
    RECONNECT_MAX_DELAY_S = 10.0
    EVENT_LOG_GAP_S = 3.0      # the same hardware event is logged at most this often

    async def _close_client(self):
        """Disconnects and forgets the current client without triggering auto-reconnect."""
        old, self.client = self.client, None  # _on_disconnected ignores clients that aren't current
        if old is None:
            return
        try:
            await asyncio.wait_for(old.disconnect(), self.DISCONNECT_TIMEOUT_S)
        except Exception as e:
            logger.debug("Ignoring error while closing old BLE client: %s", e)

    async def scan_devices(self, timeout: float = 4.0) -> list:
        """Scans for nearby Bluetooth devices advertising SentraX services or matching name."""
        if not BLEAK_AVAILABLE:
            return []
        self.is_scanning = True
        self.radio_off = False
        found = []
        _ensure_mta_thread()
        try:
            devices = await BleakScanner.discover(return_adv=True, timeout=timeout)
            for addr, (d, adv) in devices.items():
                self._discovered_ble_devices[addr] = d
                name = adv.local_name or d.name or "Unknown Device"
                uuids = [str(u).lower() for u in (adv.service_uuids or [])]
                is_sentrax = ("SENTRAX" in name.upper() or
                              "ESP32" in name.upper() or
                              SENTRAX_SERVICE_UUID.lower() in uuids)
                found.append({
                    "name": name,
                    "address": addr,
                    "rssi": adv.rssi,
                    "is_sentrax": is_sentrax
                })
        except Exception as e:
            logger.error("BLE scan error: %s", e)
            if "not powered on" in str(e).lower() or "powered_off" in str(e).lower():
                self.radio_off = True
                self.last_error = "Bluetooth is turned off on this PC. Turn it on in Windows Settings > Bluetooth & devices, then connect again."
            else:
                self.last_error = f"Bluetooth scan failed: {e}"
        finally:
            self.is_scanning = False
        return found

    async def connect(self, address_or_name: Optional[str] = None) -> bool:
        """Connects to a specific BLE address or automatically discovers SENTRAX-ESP32."""
        if not BLEAK_AVAILABLE:
            self.last_error = "Bleak library not available on this platform."
            logger.warning(self.last_error)
            return False

        # A manual connect cancels any pending auto-reconnect (but the reconnect loop must not cancel itself)
        if (self._reconnect_task and not self._reconnect_task.done()
                and self._reconnect_task is not asyncio.current_task()):
            self._reconnect_task.cancel()
            self._reconnect_task = None
            self.reconnecting = False
        self.auto_reconnect = True
        _ensure_mta_thread()

        async with self._connect_lock:
            if self.is_connected and self.client and self.client.is_connected and (
                    not address_or_name or address_or_name == self.connected_device_address):
                return True  # another caller already connected while we waited
            return await self._connect_locked(address_or_name)

    async def _connect_locked(self, address_or_name: Optional[str]) -> bool:
        target_address = address_or_name

        if not target_address:
            # Auto-discover SENTRAX-ESP32
            logger.info("Auto-scanning for SENTRAX-ESP32 BLE peripheral...")
            devices = await self.scan_devices(timeout=4.0)
            for d in devices:
                if "SENTRAX" in d["name"].upper() or d["is_sentrax"]:
                    target_address = d["address"]
                    self.connected_device_name = d["name"]
                    break

        if not target_address and self.radio_off:
            return False  # scan_devices already explained that Bluetooth is off

        if not target_address:
            # Check if we have previously known or paired address
            if self.connected_device_address:
                target_address = self.connected_device_address
            else:
                self.last_error = "No SENTRAX-ESP32 found in scan. Ensure ESP32 is powered on."
                logger.warning(self.last_error)
                return False

        try:
            logger.info("Connecting to BLE device: %s", target_address)
            # On Windows, BleakClient(str) invokes find_device_by_address which fails if device is connected to OS.
            # Passing BLEDevice directly connects via Windows BluetoothAddress immediately!
            device_target = self._discovered_ble_devices.get(target_address)
            if not device_target:
                from bleak.backends.device import BLEDevice
                device_target = BLEDevice(
                    address=target_address,
                    name=self.connected_device_name or "SENTRAX-ESP32",
                    details=None
                )

            # Drop any previous client first. Its disconnect callback is ignored, so this can no
            # longer spawn an auto-reconnect that races the connect below.
            self.is_connected = False
            await self._close_client()

            last_exc: Optional[BaseException] = None
            for attempt in range(1, 3):
                client = BleakClient(
                    device_target,
                    disconnected_callback=self._on_disconnected,
                    winrt={"use_cached_services": False}
                )
                self.client = client
                try:
                    # Hard ceiling: some WinRT calls inside connect() have no timeout of their own
                    await asyncio.wait_for(client.connect(timeout=10.0), self.CONNECT_TIMEOUT_S)
                    if not client.is_connected:
                        raise ConnectionError("link dropped during service discovery")

                    # Subscribe before declaring the link live; a stuck CCCD write must not hang us
                    await asyncio.wait_for(
                        client.start_notify(CHAR_TELEMETRY_UUID, self._on_telemetry_packet),
                        self.NOTIFY_TIMEOUT_S)
                    try:
                        await asyncio.wait_for(
                            client.start_notify(CHAR_EVENTS_UUID, self._on_event_packet),
                            self.NOTIFY_TIMEOUT_S)
                    except Exception as ne:
                        logger.warning("Events notify subscribe failed (telemetry still live): %s", ne)
                    break
                except Exception as ce:
                    last_exc = ce
                    logger.warning("BLE connect attempt %d failed: %r", attempt, ce)
                    await self._close_client()
                    if attempt == 1:
                        await asyncio.sleep(1.5)

            if self.client is None or not self.client.is_connected:
                raise last_exc or ConnectionError("connection failed")

            self.is_connected = True
            self.connected_device_address = target_address
            self.connected_at = self.last_packet_at = time.time()
            self._rx_buffer = ""
            self._event_buffer = ""
            emergency_tracker.reset_link()
            speed_tracker.reset_link()
            hw_decoder.reset_link()
            hardware_sync.link_up()
            self._start_watchdog(self.client)
            logger.info("Successfully connected to physical ESP32 over BLE!")
            update_device_status("SENTRAX-ESP32", "CONNECTED", rssi=-60, last_event="BLE_CONNECTED")
            self.last_error = ""
            return True
        except Exception as e:
            err_msg = str(e) or type(e).__name__
            if isinstance(e, asyncio.TimeoutError):
                self.last_error = ("BLE connection timed out. Power-cycle the ESP32 (press EN/RST), "
                                   "close any other app/browser tab connected to it, then retry.")
            elif "AccessDenied" in err_msg or "Access is denied" in err_msg:
                self.last_error = "Windows AccessDenied: Please remove SENTRAX-ESP32 from Windows Bluetooth Settings (Devices), then connect via Web Bluetooth or COM Port."
            elif "not found" in err_msg.lower():
                self.last_error = (f"Device {target_address} not found. Ensure ESP32 power LED is on and advertising "
                                   "(it stops advertising while another app or browser tab is connected).")
                self._discovered_ble_devices.pop(target_address, None)  # rescan next time
            else:
                self.last_error = f"BLE connection error: {err_msg}"
            logger.error("Failed to connect to BLE device %s: %s", target_address, err_msg)
            self.is_connected = False
            await self._close_client()
            return False

    async def disconnect(self):
        self.auto_reconnect = False
        for task in (self._reconnect_task, self._watchdog_task):
            if task and not task.done() and task is not asyncio.current_task():
                task.cancel()
        self._reconnect_task = self._watchdog_task = None
        self.reconnecting = False
        self.is_connected = False
        await self._close_client()
        self.is_esp8266_connected = False
        self._rx_buffer = ""
        self.latest_live_telemetry = None
        update_device_status("SENTRAX-ESP32", "DISCONNECTED", last_event="BLE_DISCONNECTED")
        hardware_sync.wake()

    async def send_command(self, cmd: str) -> bool:
        """Sends command string to ESP32 over BLE commands characteristic."""
        if not self.is_connected or not self.client:
            return False
        try:
            payload = cmd.strip().encode("utf-8") + b"\n"
            await asyncio.wait_for(
                self.client.write_gatt_char(CHAR_COMMANDS_UUID, payload, response=False), 3.0)
            logger.info("Sent BLE command to ESP32: %s", cmd)
            return True
        except Exception as e:
            logger.error("Failed to write BLE command: %s", e)
            return False

    # ------------------------------------------------------------------ link health
    def _on_disconnected(self, client):
        if client is not self.client or not self.is_connected:
            # A client we closed on purpose, or a failure mid-handshake that connect() is already handling
            return
        self._link_lost("Windows reported the Bluetooth link closed")

    def _link_lost(self, why: str):
        """The live link is gone: show standby and keep trying to reconnect."""
        lasted = time.time() - self.connected_at if self.connected_at else 0.0
        logger.warning("Physical ESP32 BLE link lost after %.0f s: %s", lasted, why)
        self.link_drops = (self.link_drops + [{"at": time.time(), "after_s": round(lasted), "why": why}])[-10:]
        self.is_connected = False
        self.is_esp8266_connected = False
        self._rx_buffer = ""
        self.latest_live_telemetry = None
        update_device_status("SENTRAX-ESP32", "DISCONNECTED", last_event="DISCONNECTED")
        hardware_sync.wake()  # the perception loop broadcasts standby
        if self.auto_reconnect and (self._reconnect_task is None or self._reconnect_task.done()):
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    def _start_watchdog(self, client):
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
        self._watchdog_task = asyncio.create_task(self._watchdog(client))

    async def _watchdog(self, client):
        """Restarts a link that Windows still calls connected but that has stopped delivering data."""
        while self.client is client and self.is_connected:
            await asyncio.sleep(2.0)
            silent = time.time() - self.last_packet_at
            if self.client is client and self.is_connected and silent > self.SILENT_LINK_S:
                self._link_lost(f"no data for {silent:.0f} s")
                await self._close_client()
                return

    async def _reconnect_loop(self):
        """Retries until the ESP32 is back, backing off to one attempt every 10 s."""
        self.reconnecting = True
        delay, attempt = 2.0, 0
        try:
            while not self.is_connected and self.auto_reconnect:
                attempt += 1
                await asyncio.sleep(delay)
                if self.is_connected or not self.auto_reconnect:
                    break
                logger.info("Attempting auto-reconnect to BLE peripheral (attempt %d)...", attempt)
                async with self._connect_lock:
                    if self.is_connected or not self.auto_reconnect:
                        break
                    if await self._connect_locked(self.connected_device_address):
                        break
                delay = self.RECONNECT_MAX_DELAY_S if self.radio_off else min(delay * 1.6, self.RECONNECT_MAX_DELAY_S)
        finally:
            self.reconnecting = False

    def link_status(self) -> Dict[str, Any]:
        """Connection health for the dashboard: this session's drops plus what the ESP32 reports."""
        now = time.time()
        return {
            "connected_for_s": round(now - self.connected_at) if self.is_connected else 0,
            "reconnecting": self.reconnecting,
            "drops_this_session": len(self.link_drops),
            "last_drop": self.link_drops[-1] if self.link_drops else None,
            "esp32": hw_decoder.diag or None,
        }

    # ------------------------------------------------------------------ incoming data
    def _on_telemetry_packet(self, sender: int, data: bytearray):
        """Reassembles newline-framed JSON telemetry from MTU-sized notification chunks."""
        if not self.is_connected:
            return  # still handshaking; connect() resets the buffer once the link is live
        self.last_packet_at = time.time()
        self._rx_buffer += data.decode("utf-8", errors="ignore")
        if len(self._rx_buffer) > 4096:
            self._rx_buffer = self._rx_buffer[self._rx_buffer.rfind("\n") + 1:]
        *lines, self._rx_buffer = self._rx_buffer.split("\n")
        for line in lines:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as je:
                logger.warning("BLE telemetry JSON decode error: %s", je)
                continue
            if "ev" in parsed:
                self._handle_event(parsed)
            else:
                self._handle_parsed_telemetry(parsed)

    def _handle_parsed_telemetry(self, parsed: dict):
        try:
            now = time.time()
            if parsed.get("esp8266", 0):
                self.is_esp8266_connected = True
                self.last_esp8266_heartbeat = now
                update_device_status("SENTRAX-ESP8266", "CONNECTED", last_event="UART_LINK_ACTIVE")
            elif now - self.last_esp8266_heartbeat > 4.0:
                self.is_esp8266_connected = False

            from software.backend.api.routes import live_serial_instance
            serial_esp8266 = bool(live_serial_instance and (live_serial_instance.is_esp8266_connected or live_serial_instance.is_esp8266_direct_connected))

            t = hw_decoder.decode(parsed, now)
            t.esp8266_connected = self.is_esp8266_connected or serial_esp8266
            self.latest_live_telemetry = hw_decoder.score(t)
            save_telemetry(t)
            update_device_status("SENTRAX-ESP32", "CONNECTED", last_event=t.hw_alerts[0] if t.hw_alerts else "NORMAL")
            hardware_sync.wake()
        except Exception as e:
            logger.error("Error processing telemetry packet: %s", e)

    def _on_event_packet(self, sender: int, data: bytearray):
        """Instant alert events: plain names from older firmware, JSON lines from firmware v2."""
        self.last_packet_at = time.time()
        chunk = data.decode("utf-8", errors="ignore")
        if not self._event_buffer and not chunk.lstrip().startswith("{"):
            name = chunk.strip()
            if name:
                self._handle_event({"ev": name, "on": 1, "src": "hw"})
            return
        self._event_buffer += chunk
        *lines, self._event_buffer = self._event_buffer.split("\n")
        if len(self._event_buffer) > 512:
            self._event_buffer = ""
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                self._handle_event(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Bad BLE event line: %r", line[:60])

    def _handle_event(self, msg: dict):
        try:
            now = time.time()
            raw = str(msg.get("ev", "")).strip()
            on = bool(msg.get("on", 1))
            src = str(msg.get("src", "hw")).lower()
            if raw.upper() == "CAL":
                logger.info("ESP32 calibration %s", "started" if on else ("finished" if msg.get("ok", 1) else "failed"))
                hardware_sync.wake()
                return
            if raw.upper() == "COLLISION" and on and src == "hw" and not sound_filter.collision_allowed(now):
                logger.info("Ignoring COLLISION event from mic noise (no sustained sound)")
                return
            name = hw_decoder.note_event(raw, on, now)
            logger.info("Hardware event over BLE: %s %s (%s)", name, "on" if on else "off", src)
            if name == "EMERGENCY" and on:
                # Older firmware sends this on every tag scan, seconds before telemetry resumes
                emergency_tracker.trigger(now)

            evt = None
            fresh = now - self._last_event_saved.get(name, 0.0) >= self.EVENT_LOG_GAP_S
            if on and src == "hw" and fresh:
                self._last_event_saved[name] = now
                event_type = EventType.SPEED if name == "SPEED_CHECK" else (
                    EventType(name) if name in EventType.__members__ else EventType.NORMAL)
                evt = CanonicalEvent(
                    source="ESP32",
                    type=event_type,
                    severity=EVENT_SEVERITY.get(name, EventSeverity.INFO),
                    confidence=1.0,
                    title=f"Hardware Event: {name}",
                    description="Instantaneous interrupt notification from physical ESP32 controller",
                    payload={"transport": "BLE"},
                    is_simulated=False
                )
                save_event(evt)

            if self.latest_live_telemetry and (name in ALERT_BITS):
                self.latest_live_telemetry = hw_decoder.refresh(
                    self.latest_live_telemetry, name, on, pushed=(src != "hw"), now=now)
            if evt:
                hardware_sync.post_event(evt)
            else:
                hardware_sync.wake()
        except Exception as e:
            logger.error("Error handling BLE event notification: %s", e)
