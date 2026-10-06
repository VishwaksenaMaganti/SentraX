"""
SentraX Mock BLE Transport
Emulates standard BLE GATT server / peripheral connections for SENTRAX-ESP32 and SENTRAX-ESP8266.
Provides identical callback interfaces to bleak so the software remains runnable without hardware.
"""

import asyncio
import time
import random
from typing import Dict, Any, Callable, List, Optional
from software.backend.ble.adapter import (
    SENTRAX_SERVICE_UUID, CHAR_DEVICE_STATUS_UUID, CHAR_TELEMETRY_UUID,
    CHAR_EVENTS_UUID, CHAR_COMMANDS_UUID, CHAR_HEARTBEAT_UUID
)
from software.backend.schemas.telemetry import ConnectionState


class MockBLEDevice:
    def __init__(self, device_id: str, name: str):
        self.device_id = device_id
        self.name = name
        self.state = ConnectionState.CONNECTED
        self.rssi = -64
        self.uptime = 0
        self.last_seen = time.time()
        self.subscribers: Dict[str, List[Callable[[bytes], None]]] = {
            CHAR_DEVICE_STATUS_UUID: [],
            CHAR_TELEMETRY_UUID: [],
            CHAR_EVENTS_UUID: [],
            CHAR_HEARTBEAT_UUID: []
        }

    def subscribe(self, char_uuid: str, callback: Callable[[bytes], None]):
        if char_uuid in self.subscribers:
            self.subscribers[char_uuid].append(callback)

    def notify(self, char_uuid: str, data: bytes):
        for cb in self.subscribers.get(char_uuid, []):
            try:
                cb(data)
            except Exception as e:
                pass


class MockBLEManager:
    """Simulates BLE scanning, connection, and GATT characteristic streaming."""

    def __init__(self):
        self.devices = {
            "SENTRAX-ESP32": MockBLEDevice("SENTRAX-ESP32", "SentraX Road Node ESP32"),
            "SENTRAX-ESP8266": MockBLEDevice("SENTRAX-ESP8266", "SentraX Aux Node ESP8266")
        }
        self.is_running = False
        self._task = None

    def start(self, on_telemetry_cb: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.is_running = True
        self.on_telemetry_cb = on_telemetry_cb
        self._task = asyncio.create_task(self._simulation_loop())

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()

    async def _simulation_loop(self):
        while self.is_running:
            await asyncio.sleep(2.0)
            now = time.time()
            for dev_id, dev in self.devices.items():
                dev.uptime += 2
                dev.last_seen = now
                dev.rssi = -60 + random.randint(-8, 5)

                heartbeat_data = f"HB:{dev_id}:{int(now)}".encode("utf-8")
                dev.notify(CHAR_HEARTBEAT_UUID, heartbeat_data)

    def write_command(self, device_id: str, cmd: str) -> bool:
        if device_id in self.devices:
            # Emulate receipt of command
            return True
        return False
