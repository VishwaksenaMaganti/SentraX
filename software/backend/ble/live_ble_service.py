"""
SentraX Live Bluetooth Low Energy (BLE) Client Service
Connects to physical SENTRAX-ESP32 hardware using bleak, subscribes to GATT characteristics,
and streams live physical telemetry into the SentraX platform without simulation.
"""

import asyncio
import json
import logging
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

logger = logging.getLogger("sentrax.live_ble")

try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False


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
        self._worker_task: Optional[asyncio.Task] = None
        self.latest_live_telemetry: Optional[CanonicalTelemetry] = None

    async def scan_devices(self, timeout: float = 4.0) -> list:
        """Scans for nearby Bluetooth devices advertising SentraX services or matching name."""
        if not BLEAK_AVAILABLE:
            return []
        self.is_scanning = True
        found = []
        try:
            devices = await BleakScanner.discover(return_adv=True, timeout=timeout)
            for addr, (d, adv) in devices.items():
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
            logger.warning("Bleak library not available on this platform.")
            return False

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
            logger.warning("No SENTRAX-ESP32 peripheral found during scan.")
            return False

        try:
            logger.info("Connecting to BLE device: %s", target_address)
            self.client = BleakClient(target_address, disconnected_callback=self._on_disconnected)
            await self.client.connect(timeout=10.0)

            if self.client.is_connected:
                self.is_connected = True
                self.connected_device_address = target_address
                logger.info("Successfully connected to physical ESP32 over BLE!")

                # Subscribe to Telemetry Notifications
                await self.client.start_notify(CHAR_TELEMETRY_UUID, self._on_telemetry_packet)
                # Subscribe to Events Notifications
                await self.client.start_notify(CHAR_EVENTS_UUID, self._on_event_packet)

                update_device_status("SENTRAX-ESP32", "CONNECTED", rssi=-60, last_event="BLE_CONNECTED")
                return True
        except Exception as e:
            logger.error("Failed to connect to BLE device %s: %s", target_address, e)
            self.is_connected = False
            return False

    async def disconnect(self):
        self.auto_reconnect = False
        if self.client and self.client.is_connected:
            await self.client.disconnect()
        self.is_connected = False
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
        if self.auto_reconnect:
            asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        while not self.is_connected and self.auto_reconnect:
            logger.info("Attempting auto-reconnect to BLE peripheral...")
            await asyncio.sleep(3.0)
            success = await self.connect(self.connected_device_address)
            if success:
                break

    def _on_telemetry_packet(self, sender: int, data: bytearray):
        """Processes real-time binary or JSON telemetry payload emitted by ESP32 with streaming chunk reassembly."""
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
            ir_list = parsed.get("ir", [0, 0, 0, 0])
            ir_bools = [bool(x) for x in ir_list]

            alert_str = parsed.get("alert", "NORMAL")
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
                collision=(alert_str == "COLLISION" or bool(parsed.get("sound", 0))),
                wrong_way=(alert_str == "WRONG_WAY"),
                stalled_vehicle=(alert_str == "STALLED"),
                emergency_vehicle=(alert_str == "EMERGENCY" or bool(parsed.get("rfid", 0))),
                temperature_c=float(parsed.get("temp", 26.5)),
                humidity_pct=float(parsed.get("hum", 55.0)),
                moisture_raw=int(parsed.get("moist", 3100)),
                ir_sensors=ir_bools,
                sound_active=bool(parsed.get("sound", 0)),
                rfid_active=bool(parsed.get("rfid", 0)),
                night_mode=bool(parsed.get("night", 0)),
                source=DeviceSource.ESP32,
                is_simulated=False,
                esp32_connected=True,
                esp8266_connected=esp8266_conn,
                both_modules_connected=is_armed,
                hardware_standby=not is_armed
            )

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

            if self.latest_live_telemetry and self.on_telemetry_broadcast:
                asyncio.create_task(self.on_telemetry_broadcast(self.latest_live_telemetry, evt))
        except Exception as e:
            logger.error("Error handling BLE event notification: %s", e)
