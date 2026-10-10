"""
SentraX Live Bluetooth Low Energy (BLE) Client Service
Connects to physical SENTRAX-ESP32 hardware using bleak, subscribes to GATT characteristics,
and streams live physical telemetry into the SentraX platform without simulation.
"""

import asyncio
import json
import logging
import sys
import time
from typing import Optional, Callable, Dict, Any

from software.backend.ble.adapter import (
    SENTRAX_SERVICE_UUID, CHAR_TELEMETRY_UUID, CHAR_EVENTS_UUID, CHAR_COMMANDS_UUID
)
from software.backend.schemas.telemetry import (
    CanonicalTelemetry, ConnectionState, RoadCondition, TrafficLevel, DeviceSource
)
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.database.models import save_telemetry, save_event, update_device_status
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.recommendation_engine import RecommendationEngine
from software.backend.engines.emergency_tracker import emergency_tracker
from software.backend.engines.speed_tracker import speed_tracker
from software.backend.core.sensors import read_ir, sound_filter

logger = logging.getLogger("sentrax.live_ble")

try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False


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
        self.on_telemetry_broadcast = on_telemetry_broadcast
        self.client: Optional[Any] = None
        self.connected_device_address: Optional[str] = None
        self.connected_device_name: Optional[str] = None
        self.is_connected = False
        self.is_esp8266_connected = False
        self.last_esp8266_heartbeat = 0.0
        self.is_scanning = False
        self.auto_reconnect = True
        self._rx_buffer = ""
        self._reconnect_task: Optional[asyncio.Task] = None
        self.latest_live_telemetry: Optional[CanonicalTelemetry] = None
        self._discovered_ble_devices: Dict[str, Any] = {}
        self.last_error: str = ""
        # Serialises connect attempts: a dashboard click and the auto-reconnect loop must never
        # drive two BleakClients at the same ESP32 at once (that deadlocks the Windows stack).
        self._connect_lock = asyncio.Lock()

    CONNECT_TIMEOUT_S = 15.0
    NOTIFY_TIMEOUT_S = 6.0
    DISCONNECT_TIMEOUT_S = 5.0

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
            self._rx_buffer = ""
            emergency_tracker.reset_link()
            speed_tracker.reset_link()
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
            else:
                self.last_error = f"BLE connection error: {err_msg}"
            logger.error("Failed to connect to BLE device %s: %s", target_address, err_msg)
            self.is_connected = False
            await self._close_client()
            return False

    async def disconnect(self):
        self.auto_reconnect = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None
        self.is_connected = False
        await self._close_client()
        self.is_esp8266_connected = False
        self._rx_buffer = ""
        self.latest_live_telemetry = None
        update_device_status("SENTRAX-ESP32", "DISCONNECTED", last_event="BLE_DISCONNECTED")

    async def send_command(self, cmd: str) -> bool:
        """Sends command string to ESP32 over BLE commands characteristic."""
        if not self.is_connected or not self.client:
            return False
        try:
            payload = cmd.strip().encode("utf-8") + b"\n"
            await self.client.write_gatt_char(CHAR_COMMANDS_UUID, payload, response=False)
            logger.info("Sent BLE command to ESP32: %s", cmd)
            return True
        except Exception as e:
            logger.error("Failed to write BLE command: %s", e)
            return False

    def _on_disconnected(self, client):
        if client is not self.client or not self.is_connected:
            # A client we closed on purpose, or a failure mid-handshake that connect() is already handling
            return
        logger.warning("Physical ESP32 BLE peripheral disconnected!")
        self.is_connected = False
        self.is_esp8266_connected = False
        self._rx_buffer = ""
        self.latest_live_telemetry = None
        update_device_status("SENTRAX-ESP32", "DISCONNECTED", last_event="DISCONNECTED")
        if self.on_telemetry_broadcast:
            standby_tele = CanonicalTelemetry(
                device_id="SENTRAX-STANDBY",
                timestamp=time.time(),
                connection_state=ConnectionState.DISCONNECTED,
                measured_speed_kmh=0.0,
                recommended_speed_kmh=0.0,
                posted_speed_kmh=80.0,
                traffic_count=0,
                traffic_level=TrafficLevel.LIGHT,
                road_condition=RoadCondition.DRY,
                collision=False,
                wrong_way=False,
                stalled_vehicle=False,
                emergency_vehicle=False,
                temperature_c=0.0,
                humidity_pct=0.0,
                moisture_raw=0,
                ir_sensors=[False, False, False, False],
                sound_active=False,
                rfid_active=False,
                night_mode=False,
                risk_score=0,
                risk_reasons=["HARDWARE STANDBY: ESP32 BLE disconnected."],
                source=DeviceSource.FUSION,
                is_simulated=False,
                esp32_connected=False,
                esp8266_connected=False,
                both_modules_connected=False,
                hardware_standby=True
            )
            asyncio.create_task(self.on_telemetry_broadcast(standby_tele, None))
        if self.auto_reconnect and (self._reconnect_task is None or self._reconnect_task.done()):
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        retries = 0
        max_retries = 3
        while not self.is_connected and self.auto_reconnect and retries < max_retries:
            retries += 1
            logger.info("Attempting auto-reconnect to BLE peripheral (%d/%d)...", retries, max_retries)
            await asyncio.sleep(4.0)
            if self.is_connected or not self.auto_reconnect:
                break
            async with self._connect_lock:
                if self.is_connected or not self.auto_reconnect:
                    break
                success = await self._connect_locked(self.connected_device_address)
            if success:
                break
        if not self.is_connected:
            logger.info("Auto-reconnect attempts finished. Awaiting manual user connection.")

    def _on_telemetry_packet(self, sender: int, data: bytearray):
        """Processes real-time binary or JSON telemetry payload emitted by ESP32 with streaming chunk reassembly."""
        if not self.is_connected:
            return  # still handshaking; connect() resets the buffer once the link is live
        try:
            chunk = data.decode("utf-8", errors="ignore")
            self._rx_buffer += chunk

            start_idx = self._rx_buffer.find("{")
            end_idx = self._rx_buffer.find("}", start_idx) if start_idx != -1 else -1

            while start_idx != -1 and end_idx != -1:
                json_str = self._rx_buffer[start_idx:end_idx + 1]
                self._rx_buffer = self._rx_buffer[end_idx + 1:]

                try:
                    parsed = json.loads(json_str)
                    self._handle_parsed_telemetry(parsed)
                except json.JSONDecodeError as je:
                    logger.warning("BLE packet JSON decode error on chunk: %s", je)

                start_idx = self._rx_buffer.find("{")
                end_idx = self._rx_buffer.find("}", start_idx) if start_idx != -1 else -1

            if len(self._rx_buffer) > 2048:
                self._rx_buffer = ""
        except Exception as e:
            logger.error("Error decoding live BLE packet: %s", e)

    def _handle_parsed_telemetry(self, parsed: dict):
        try:
            now = time.time()
            ir_list = read_ir(parsed.get("ir"), bool(parsed.get("irfix", 0)))
            ir_bools = [bool(x) for x in ir_list]

            alert_str = parsed.get("alert", "NORMAL")
            sound_on, collision_on = sound_filter.observe(
                parsed.get("sound", 0), alert_str, bool(parsed.get("sndfix", 0)), now)
            cond = RoadCondition.WET if (alert_str == "WET_ROAD" or parsed.get("moist", 3000) < 2000) else RoadCondition.DRY
            traf = TrafficLevel.CONGESTED if (alert_str == "CONGESTION" or sum(ir_list) >= 2) else TrafficLevel.LIGHT

            from software.backend.api.routes import live_serial_instance

            esp8266_flag = bool(parsed.get("esp8266", 0))
            if esp8266_flag:
                self.is_esp8266_connected = True
                self.last_esp8266_heartbeat = now
                update_device_status("SENTRAX-ESP8266", "CONNECTED", last_event="UART_LINK_ACTIVE")
            else:
                if (now - self.last_esp8266_heartbeat) > 4.0:
                    self.is_esp8266_connected = False

            serial_esp8266 = bool(live_serial_instance and (live_serial_instance.is_esp8266_connected or live_serial_instance.is_esp8266_direct_connected))
            esp8266_conn = self.is_esp8266_connected or serial_esp8266
            is_armed = bool(self.is_connected)

            t = CanonicalTelemetry(
                device_id="SENTRAX-ESP32",
                timestamp=now,
                connection_state=ConnectionState.CONNECTED if is_armed else ConnectionState.DISCONNECTED,
                measured_speed_kmh=float(parsed.get("speed", parsed.get("spd", 0.0))),
                recommended_speed_kmh=float(parsed.get("rec_speed", parsed.get("rec", 80.0))),
                posted_speed_kmh=80.0,
                traffic_count=sum(ir_list),
                traffic_level=traf,
                road_condition=cond,
                collision=collision_on,
                wrong_way=(alert_str == "WRONG_WAY"),
                stalled_vehicle=(alert_str == "STALLED"),
                emergency_vehicle=(alert_str == "EMERGENCY" or bool(parsed.get("rfid", 0))),
                temperature_c=float(parsed.get("temp", 26.5)),
                humidity_pct=float(parsed.get("hum", 55.0)),
                moisture_raw=int(parsed.get("moist", 3100)),
                ir_sensors=ir_bools,
                sound_active=sound_on,
                rfid_active=bool(parsed.get("rfid", 0)),
                night_mode=bool(parsed.get("night", 0)),
                source=DeviceSource.ESP32,
                is_simulated=False,
                esp32_connected=True,
                esp8266_connected=esp8266_conn,
                both_modules_connected=is_armed,
                hardware_standby=not is_armed
            )

            # The firmware's rfid flag stays latched after a scan; read it as an edge, not a level
            emergency_tracker.observe_packet(bool(parsed.get("rfid", 0)), alert_str, now)
            emergency_tracker.apply(t)
            # The firmware's speed also stays latched; show each new reading for a few seconds
            speed_tracker.observe_packet(t.measured_speed_kmh, now)
            speed_tracker.apply(t)

            if is_armed:
                score, reasons = RoadRiskEngine.calculate_risk(t)
                t.risk_score = score
                t.risk_reasons = reasons
                rec = RecommendationEngine.get_recommended_speed(t, t.posted_speed_kmh)
                t.recommended_speed_kmh = rec.recommended_speed_kmh
                self.latest_live_telemetry = t
                save_telemetry(t)
                update_device_status("SENTRAX-ESP32", "CONNECTED", last_event=alert_str)
                if self.on_telemetry_broadcast:
                    asyncio.create_task(self.on_telemetry_broadcast(t, None))
            else:
                self.latest_live_telemetry = None
                standby_tele = CanonicalTelemetry(
                    device_id="SENTRAX-STANDBY",
                    timestamp=time.time(),
                    connection_state=ConnectionState.DISCONNECTED,
                    measured_speed_kmh=0.0,
                    recommended_speed_kmh=0.0,
                    posted_speed_kmh=80.0,
                    traffic_count=0,
                    traffic_level=TrafficLevel.LIGHT,
                    road_condition=RoadCondition.DRY,
                    collision=False,
                    wrong_way=False,
                    stalled_vehicle=False,
                    emergency_vehicle=False,
                    temperature_c=0.0,
                    humidity_pct=0.0,
                    moisture_raw=0,
                    ir_sensors=[False, False, False, False],
                    sound_active=False,
                    rfid_active=False,
                    night_mode=False,
                    risk_score=0,
                    risk_reasons=["HARDWARE STANDBY: ESP32 BLE disconnected."],
                    source=DeviceSource.FUSION,
                    is_simulated=False,
                    esp32_connected=False,
                    esp8266_connected=esp8266_conn,
                    both_modules_connected=False,
                    hardware_standby=True
                )
                if self.on_telemetry_broadcast:
                    asyncio.create_task(self.on_telemetry_broadcast(standby_tele, None))

        except Exception as e:
            logger.error("Error processing telemetry packet: %s", e)

    def _on_event_packet(self, sender: int, data: bytearray):
        """Processes instantaneous alert events emitted by ESP32."""
        try:
            event_name = data.decode("utf-8").strip()
            logger.info("Received live hardware event over BLE: %s", event_name)

            if event_name == "COLLISION" and not sound_filter.collision_allowed():
                logger.info("Ignoring COLLISION event from mic noise (no sustained sound)")
                return

            sev = EventSeverity.INFO
            if event_name in ("COLLISION", "WRONG_WAY"):
                sev = EventSeverity.CRITICAL
            elif event_name in ("OVERSPEED", "CONGESTION", "STALLED", "WET_ROAD"):
                sev = EventSeverity.WARNING

            evt = CanonicalEvent(
                source="ESP32",
                type=EventType(event_name) if event_name in EventType.__members__ else EventType.NORMAL,
                severity=sev,
                confidence=1.0,
                title=f"Hardware Event: {event_name}",
                description="Instantaneous interrupt notification from physical ESP32 controller",
                payload={"transport": "BLE"},
                is_simulated=False
            )
            save_event(evt)

            # Sent on every tag scan, while the ESP32 is still busy with its alert sequence
            # (telemetry pauses for ~9 s), so this is the earliest emergency signal.
            if event_name == "EMERGENCY":
                emergency_tracker.trigger()

            if self.latest_live_telemetry and self.on_telemetry_broadcast:
                t = emergency_tracker.apply(self.latest_live_telemetry.model_copy(deep=True))
                speed_tracker.apply(t)
                score, reasons = RoadRiskEngine.calculate_risk(t)
                t.risk_score = score
                t.risk_reasons = reasons
                asyncio.create_task(self.on_telemetry_broadcast(t, evt))
        except Exception as e:
            logger.error("Error handling BLE event notification: %s", e)
