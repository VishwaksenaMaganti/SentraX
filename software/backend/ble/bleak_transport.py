"""
SentraX Bleak BLE Transport with Automatic Hardware / Mock Fallback
"""

import asyncio
import logging
from typing import Optional, Callable, Dict, Any
from software.backend.ble.mock_transport import MockBLEManager
from software.backend.ble.adapter import (
    SENTRAX_SERVICE_UUID, CHAR_TELEMETRY_UUID, CHAR_EVENTS_UUID,
    CHAR_HEARTBEAT_UUID, CHAR_COMMANDS_UUID
)

logger = logging.getLogger("sentrax.ble")

try:
    from bleak import BleakScanner, BleakClient
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False


class SentraXBLEGateway:
    """
    Manages physical Bluetooth Low Energy connections using Bleak when available,
    seamlessly falling back to the simulated GATT transport when running in demo mode
    or on platforms without active Bluetooth radio hardware.
    """

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock or not BLEAK_AVAILABLE
        self.mock_manager = MockBLEManager()
        self.physical_clients: Dict[str, Any] = {}
        self.is_scanning = False

    async def initialize(self, telemetry_callback: Optional[Callable] = None):
        if self.use_mock:
            logger.info("Initializing SentraX BLE Gateway in MOCK / SIMULATION mode")
            self.mock_manager.start(telemetry_callback)
            return

        try:
            logger.info("Scanning for physical SentraX BLE hardware...")
            devices = await BleakScanner.discover(timeout=3.0)
            found_physical = False
            for d in devices:
                if d.name and ("SENTRAX" in d.name.upper() or "ESP32" in d.name.upper()):
                    logger.info("Discovered SentraX BLE peripheral: %s (%s)", d.name, d.address)
                    found_physical = True

            if not found_physical:
                logger.info("No physical SentraX BLE peripheral found. Activating Mock BLE Transport.")
                self.use_mock = True
                self.mock_manager.start(telemetry_callback)
        except Exception as e:
            logger.warning("BLE scanner encountered exception: %s. Falling back to Mock Transport.", e)
            self.use_mock = True
            self.mock_manager.start(telemetry_callback)

    async def send_command(self, device_id: str, command: str) -> bool:
        if self.use_mock:
            return self.mock_manager.write_command(device_id, command)
        # Physical implementation
        client = self.physical_clients.get(device_id)
        if client and client.is_connected:
            await client.write_gatt_char(CHAR_COMMANDS_UUID, command.encode("utf-8"))
            return True
        return False
