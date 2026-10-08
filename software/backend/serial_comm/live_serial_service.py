"""
SentraX Dual Microcontroller Serial Communication Service
Manages direct USB and Bluetooth Virtual COM Port links for:
1. ESP32 Core Road Controller Gateway (115200 baud)
2. ESP8266 Auxiliary Node (9600 baud direct or via ESP32 Hardware UART Bridge)
"""

import asyncio
import json
import logging
import threading
import time
from typing import Optional, Callable, List, Dict, Any

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

from software.backend.schemas.telemetry import (
    CanonicalTelemetry, ConnectionState, RoadCondition, TrafficLevel, DeviceSource
)
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.serial_comm.protocol_adapter import SentraXProtocolAdapter
from software.backend.database.models import save_telemetry, save_event, update_device_status
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.recommendation_engine import RecommendationEngine
from software.backend.engines.emergency_tracker import emergency_tracker
from software.backend.engines.speed_tracker import speed_tracker
from software.backend.core.config import settings

logger = logging.getLogger("sentrax.live_serial")


class LiveSerialManager:
    def __init__(self, on_telemetry_broadcast: Optional[Callable] = None):
        self.on_telemetry_broadcast = on_telemetry_broadcast
        self.adapter = SentraXProtocolAdapter()

        # ESP32 Core Gateway connection state
        self.esp32_port: Optional[str] = None
        self.esp32_baudrate: int = 115200
        self.esp32_conn: Optional[Any] = None
        self._is_esp32_connected_flag = False
        self.last_esp32_packet_time = 0.0
        self._esp32_thread: Optional[threading.Thread] = None
        self._esp32_stop_event = threading.Event()

        # ESP8266 Auxiliary Node direct connection state
        self.esp8266_port: Optional[str] = None
        self.esp8266_baudrate: int = 9600
        self.esp8266_conn: Optional[Any] = None
        self.is_esp8266_direct_connected = False
        self._esp8266_thread: Optional[threading.Thread] = None
        self._esp8266_stop_event = threading.Event()

        # ESP8266 via ESP32 Hardware UART link bridge
        self.esp8266_uart_bridge_active = False
        self.last_esp8266_heartbeat = 0.0

        # Canonical live telemetry buffer (starts in clean unpopulated standby state)
        self.latest_live_telemetry: Optional[CanonicalTelemetry] = None

    @property
    def is_esp32_connected(self) -> bool:
        """True if ESP32 serial port is active and has received a packet recently."""
        if not self._is_esp32_connected_flag:
            return False
        if self.last_esp32_packet_time > 0 and (time.time() - self.last_esp32_packet_time > settings.TELEMETRY_STALL_TOLERANCE_SECONDS):
            return False
        return True

    @is_esp32_connected.setter
    def is_esp32_connected(self, value: bool):
        self._is_esp32_connected_flag = bool(value)

    @property
    def is_connected(self) -> bool:
        """Backward-compatible alias for ESP32 connection state."""
        return self.is_esp32_connected

    @property
    def is_esp8266_connected(self) -> bool:
        """True if ESP8266 is connected directly via USB OR actively sending heartbeats over UART to ESP32."""
        now = time.time()
        if self.is_esp8266_direct_connected:
            if self.last_esp8266_heartbeat > 0 and (now - self.last_esp8266_heartbeat > 3.0):
                return False
            return True
        if self.esp8266_uart_bridge_active and (now - self.last_esp8266_heartbeat < 3.5):
            return True
        return False

    @property
    def both_modules_connected(self) -> bool:
        return bool(self.is_esp32_connected)

    @staticmethod
    def list_available_ports() -> List[Dict[str, str]]:
        if not SERIAL_AVAILABLE:
            return []
        ports = serial.tools.list_ports.comports()
        return [{"port": p.device, "description": p.description} for p in ports]

    # =========================================================================
    # ESP32 CONNECTION MANAGEMENT
    # =========================================================================
    def connect_esp32(self, port: str, baudrate: int = 115200) -> bool:
        if not SERIAL_AVAILABLE:
            return False
        self.disconnect_esp32()
        try:
            self.esp32_port = port
            self.esp32_baudrate = baudrate
            self.esp32_conn = serial.Serial(port, baudrate=baudrate, timeout=1.0)
            self._is_esp32_connected_flag = True
            self.last_esp32_packet_time = time.time()
            emergency_tracker.reset_link()
            speed_tracker.reset_link()
            self._esp32_stop_event.clear()
            self._esp32_thread = threading.Thread(target=self._read_esp32_loop, daemon=True)
            self._esp32_thread.start()
            logger.info("Connected to ESP32 serial port %s at %d baud", port, baudrate)
            update_device_status("SENTRAX-ESP32", "CONNECTED", port_or_address=port, last_event="SERIAL_CONNECTED")
            self._update_and_broadcast_standby_state()
            return True
        except Exception as e:
            logger.error("Failed to connect to ESP32 serial port %s: %s", port, e)
            self._is_esp32_connected_flag = False
            return False

    def disconnect_esp32(self):
        self._esp32_stop_event.set()
        if self.esp32_conn:
            try:
                self.esp32_conn.close()
            except Exception:
                pass
            self.esp32_conn = None
        self._is_esp32_connected_flag = False
        self.last_esp32_packet_time = 0.0
        self.latest_live_telemetry = None
        update_device_status("SENTRAX-ESP32", "DISCONNECTED", last_event="SERIAL_DISCONNECTED")
        self._update_and_broadcast_standby_state()

    # Backward compatibility aliases
    def connect(self, port: str, baudrate: int = 115200) -> bool:
        return self.connect_esp32(port, baudrate)

    def disconnect(self):
        self.disconnect_esp32()

    def send_command(self, cmd: str) -> bool:
        """Sends command string to ESP32 over physical USB / Bluetooth COM port."""
        if not self.is_esp32_connected or not self.esp32_conn:
            return False
        try:
            payload = cmd.strip().encode("utf-8") + b"\n"
            self.esp32_conn.write(payload)
            self.esp32_conn.flush()
            logger.info("Sent Serial command to ESP32: %s", cmd)
            return True
        except Exception as e:
            logger.error("Failed to write Serial command: %s", e)
            return False

    # =========================================================================
    # ESP8266 CONNECTION MANAGEMENT (DIRECT USB / SERIAL)
    # =========================================================================
    def connect_esp8266(self, port: str, baudrate: int = 9600) -> bool:
        if not SERIAL_AVAILABLE:
            return False
        self.disconnect_esp8266()
        try:
            self.esp8266_port = port
            self.esp8266_baudrate = baudrate
            self.esp8266_conn = serial.Serial(port, baudrate=baudrate, timeout=1.0)
            self.is_esp8266_direct_connected = True
            self.last_esp8266_heartbeat = time.time()
            self._esp8266_stop_event.clear()
            self._esp8266_thread = threading.Thread(target=self._read_esp8266_loop, daemon=True)
            self._esp8266_thread.start()
            logger.info("Connected to ESP8266 direct serial port %s at %d baud", port, baudrate)
            update_device_status("SENTRAX-ESP8266", "CONNECTED", port_or_address=port, last_event="DIRECT_SERIAL_CONNECTED")
            self._update_and_broadcast_standby_state()
            return True
        except Exception as e:
            logger.error("Failed to connect to ESP8266 serial port %s: %s", port, e)
            self.is_esp8266_direct_connected = False
            return False

    def disconnect_esp8266(self):
        self._esp8266_stop_event.set()
        if self.esp8266_conn:
            try:
                self.esp8266_conn.close()
            except Exception:
                pass
            self.esp8266_conn = None
        self.is_esp8266_direct_connected = False
        self.latest_live_telemetry = None
        if not self.esp8266_uart_bridge_active:
            update_device_status("SENTRAX-ESP8266", "DISCONNECTED", last_event="DIRECT_SERIAL_DISCONNECTED")
        self._update_and_broadcast_standby_state()

    def set_esp8266_uart_status(self, active: bool):
        """Called when ESP32 telemetry indicates ESP8266 UART link activity."""
        self.esp8266_uart_bridge_active = active
        if active:
            self.last_esp8266_heartbeat = time.time()
            update_device_status("SENTRAX-ESP8266", "CONNECTED", last_event="UART_LINK_ACTIVE")
        else:
            if not self.is_esp8266_direct_connected:
                update_device_status("SENTRAX-ESP8266", "DISCONNECTED", last_event="UART_LINK_OFFLINE")
        self._update_and_broadcast_standby_state()

    def _update_and_broadcast_standby_state(self):
        esp32_c = self.is_esp32_connected
        esp8266_c = self.is_esp8266_connected
        both_c = bool(esp32_c)

        if not both_c:
            self.latest_live_telemetry = None
            standby_msg = "HARDWARE STANDBY: ESP32 Gateway not connected."

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
                risk_reasons=[standby_msg],
                source=DeviceSource.FUSION,
                is_simulated=False,
                esp32_connected=esp32_c,
                esp8266_connected=esp8266_c,
                both_modules_connected=False,
                hardware_standby=True
            )
            if self.on_telemetry_broadcast:
                self._dispatch_async_broadcast(standby_tele, None)

    # =========================================================================
    # ESP32 READING LOOP
    # =========================================================================
    def _read_esp32_loop(self):
        while not self._esp32_stop_event.is_set() and self.esp32_conn and self.esp32_conn.is_open:
            try:
                raw_bytes = self.esp32_conn.readline()
                if not raw_bytes:
                    continue
                line = raw_bytes.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                self.last_esp32_packet_time = time.time()
                self._process_incoming_esp32_line(line)
            except Exception as e:
                logger.warning("ESP32 serial connection lost/unplugged: %s", e)
                self.disconnect_esp32()
                break

    def _process_incoming_esp32_line(self, line: str):
        now = time.time()
        # 1. Check if line is formatted JSON
        if line.startswith("{") and line.endswith("}"):
            try:
                d = json.loads(line)
                ir_list = d.get("ir", [0, 0, 0, 0])
                ir_bools = [bool(x) for x in ir_list]

                # Check ESP8266 bridge flag in ESP32 payload
                esp8266_flag = bool(d.get("esp8266", 0))
                if esp8266_flag:
                    self.esp8266_uart_bridge_active = True
                    self.last_esp8266_heartbeat = now
                    update_device_status("SENTRAX-ESP8266", "CONNECTED", last_event="UART_LINK_ACTIVE")
                else:
                    if (now - self.last_esp8266_heartbeat > 3.5) and not self.is_esp8266_direct_connected:
                        self.esp8266_uart_bridge_active = False
                        update_device_status("SENTRAX-ESP8266", "DISCONNECTED", last_event="UART_LINK_OFFLINE")

                esp8266_conn = self.is_esp8266_connected
                both_conn = bool(self.is_esp32_connected)

                alert_str = d.get("alert", "NORMAL")
                cond = RoadCondition.WET if (alert_str == "WET_ROAD" or d.get("moist", 3000) < 2000) else RoadCondition.DRY
                traf = TrafficLevel.CONGESTED if (alert_str == "CONGESTION" or sum(ir_list) >= 2) else TrafficLevel.LIGHT

                t = CanonicalTelemetry(
                    device_id="SENTRAX-ESP32",
                    timestamp=now,
                    connection_state=ConnectionState.CONNECTED if both_conn else ConnectionState.DISCONNECTED,
                    measured_speed_kmh=float(d.get("speed", d.get("spd", 0.0))),
                    recommended_speed_kmh=float(d.get("rec_speed", d.get("rec", 80.0))),
                    posted_speed_kmh=80.0,
                    traffic_count=sum(ir_list),
                    traffic_level=traf,
                    road_condition=cond,
                    collision=(alert_str == "COLLISION" or bool(d.get("sound", 0))),
                    wrong_way=(alert_str == "WRONG_WAY"),
                    stalled_vehicle=(alert_str == "STALLED"),
                    emergency_vehicle=(alert_str == "EMERGENCY" or bool(d.get("rfid", 0))),
                    temperature_c=float(d.get("temp", 26.5)),
                    humidity_pct=float(d.get("hum", 55.0)),
                    moisture_raw=int(d.get("moist", 3100)),
                    ir_sensors=ir_bools,
                    sound_active=bool(d.get("sound", 0)),
                    rfid_active=bool(d.get("rfid", 0)),
                    night_mode=bool(d.get("night", 0)),
                    source=DeviceSource.ESP32,
                    is_simulated=False,
                    esp32_connected=True,
                    esp8266_connected=esp8266_conn,
                    both_modules_connected=both_conn,
                    hardware_standby=not both_conn
                )

                # The firmware's rfid flag stays latched after a scan; read it as an edge, not a level
                emergency_tracker.observe_packet(bool(d.get("rfid", 0)), alert_str, now)
                emergency_tracker.apply(t)
                # The firmware's speed also stays latched; show each new reading for a few seconds
                speed_tracker.observe_packet(t.measured_speed_kmh, now)
                speed_tracker.apply(t)

                if both_conn:
                    score, reasons = RoadRiskEngine.calculate_risk(t)
                    t.risk_score = score
                    t.risk_reasons = reasons
                    rec = RecommendationEngine.get_recommended_speed(t, t.posted_speed_kmh)
                    t.recommended_speed_kmh = rec.recommended_speed_kmh
                    self.latest_live_telemetry = t
                    save_telemetry(t)
                    update_device_status("SENTRAX-ESP32", "CONNECTED", last_event=alert_str)
                    if self.on_telemetry_broadcast:
                        self._dispatch_async_broadcast(t, None)
                else:
                    self.latest_live_telemetry = None
                    self._update_and_broadcast_standby_state()
                return
            except Exception as ex:
                logger.error("Error processing ESP32 JSON payload: %s", ex)

        # 2. Check ASCII Protocol Token (SPEED:4.8, CONGESTION, WET, RFID, etc.)
        parsed = self.adapter.parse_line(line)
        if parsed:
            updated_tele = self.adapter.apply_to_telemetry(parsed, self.latest_live_telemetry)
            updated_tele.is_simulated = False
            updated_tele.source = DeviceSource.ESP32
            updated_tele.esp32_connected = True
            updated_tele.esp8266_connected = self.is_esp8266_connected
            updated_tele.both_modules_connected = self.both_modules_connected
            updated_tele.hardware_standby = not self.both_modules_connected
            self.latest_live_telemetry = updated_tele

            canon_event = self.adapter.to_canonical_event(parsed)
            if canon_event:
                canon_event.is_simulated = False
                save_event(canon_event)

            save_telemetry(updated_tele)
            if self.on_telemetry_broadcast:
                self._dispatch_async_broadcast(updated_tele, canon_event)

    # =========================================================================
    # ESP8266 READING LOOP (FOR DIRECT SERIAL CONNECTION)
    # =========================================================================
    def _read_esp8266_loop(self):
        while not self._esp8266_stop_event.is_set() and self.esp8266_conn and self.esp8266_conn.is_open:
            try:
                raw_bytes = self.esp8266_conn.readline()
                if not raw_bytes:
                    continue
                line = raw_bytes.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                self.last_esp8266_heartbeat = time.time()
                self._process_incoming_esp8266_line(line)
            except Exception as e:
                logger.warning("ESP8266 direct serial connection lost/unplugged: %s", e)
                self.disconnect_esp8266()
                break

    def _process_incoming_esp8266_line(self, line: str):
        now = time.time()
        logger.info("ESP8266 Direct Serial: %s", line)
        self.last_esp8266_heartbeat = now
        update_device_status("SENTRAX-ESP8266", "CONNECTED", last_event=line[:20])

        if line == "RFID":
            # Emergency RFID card swipe detected!
            evt = CanonicalEvent(
                source="ESP8266",
                type=EventType.EMERGENCY,
                severity=EventSeverity.CRITICAL,
                title="RFID EMERGENCY VEHICLE PRIORITY",
                description="Emergency vehicle RFID card authenticated. Priority route clearance requested.",
                payload={"node": "ESP8266", "action": "EMERGENCY_CLEARANCE"},
                is_simulated=False
            )
            save_event(evt)
            emergency_tracker.trigger()
            if self.latest_live_telemetry:
                emergency_tracker.apply(self.latest_live_telemetry)
                if self.on_telemetry_broadcast:
                    self._dispatch_async_broadcast(self.latest_live_telemetry, evt)

        elif line in ("NIGHT", "DAY"):
            if self.latest_live_telemetry:
                self.latest_live_telemetry.night_mode = (line == "NIGHT")
                if self.on_telemetry_broadcast:
                    self._dispatch_async_broadcast(self.latest_live_telemetry, None)

    def _dispatch_async_broadcast(self, t, evt):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.on_telemetry_broadcast(t, evt), loop)
        except Exception:
            pass
