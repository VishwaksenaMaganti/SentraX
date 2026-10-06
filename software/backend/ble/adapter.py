"""
SentraX Standard GATT Profile and BLE Service Definition
"""

from typing import Dict, Any, Callable, List
import uuid

# SentraX Standard 128-bit Base UUID: 0000xxxx-7365-6e74-7261-782073616665
SENTRAX_SERVICE_UUID = "73656e74-7261-7800-0001-000000000000"

# GATT Characteristics
CHAR_DEVICE_STATUS_UUID  = "73656e74-7261-7800-0002-000000000001"  # Read / Notify: Device health, uptime, state
CHAR_TELEMETRY_UUID      = "73656e74-7261-7800-0002-000000000002"  # Notify: Periodic sensor telemetry packet
CHAR_EVENTS_UUID         = "73656e74-7261-7800-0002-000000000003"  # Notify / Indicate: Instantaneous alert events
CHAR_COMMANDS_UUID       = "73656e74-7261-7800-0002-000000000004"  # Write: Control commands
CHAR_HEARTBEAT_UUID      = "73656e74-7261-7800-0002-000000000005"  # Read / Notify: Liveness pulse

DEVICE_NAMES = ["SENTRAX-ESP32", "SENTRAX-ESP8266"]


class BLEPacketEncoder:
    """Encodes and decodes binary/JSON GATT characteristic payloads."""

    @staticmethod
    def encode_telemetry(data: Dict[str, Any]) -> bytes:
        import json
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def decode_telemetry(payload: bytes) -> Dict[str, Any]:
        import json
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def encode_command(command_str: str) -> bytes:
        return command_str.encode("utf-8")

    @staticmethod
    def decode_command(payload: bytes) -> str:
        return payload.decode("utf-8").strip()
