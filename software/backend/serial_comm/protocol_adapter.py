"""
SentraX Serial Protocol Adapter
Translates raw UART serial streams from ESP32 and ESP8266 into Canonical Telemetry and Events.
"""

from typing import Dict, Any, Optional, Tuple
import time
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel, DeviceSource


class SentraXProtocolAdapter:
    """
    Parses ASCII line messages exchanged across the ESP32 <-> ESP8266 UART link
    and converts them to structured event records and telemetry state updates.
    """

    def __init__(self):
        self.last_parsed_time = time.time()

    def parse_line(self, line: str, default_source: str = "ESP32") -> Optional[Dict[str, Any]]:
        raw = line.strip()
        if not raw:
            return None

        # 1. Speed reading (e.g., "SPEED:4.8")
        if raw.startswith("SPEED:"):
            try:
                val = float(raw.split(":", 1)[1])
                return {
                    "type": "speed",
                    "value": val,
                    "source": default_source.lower(),
                    "raw": raw,
                    "timestamp": time.time()
                }
            except ValueError:
                return None

        # 2. Recommended speed / limit update (e.g., "LIMIT:60")
        if raw.startswith("LIMIT:"):
            try:
                val = float(raw.split(":", 1)[1])
                return {
                    "type": "recommended_speed",
                    "value": val,
                    "source": default_source.lower(),
                    "raw": raw,
                    "timestamp": time.time()
                }
            except ValueError:
                return None

        # 3. Mode changes (e.g., "SPEED_MODE")
        if raw == "SPEED_MODE":
            return {
                "type": "mode",
                "mode": "CALCULATING_SPEED",
                "source": default_source.lower(),
                "raw": raw,
                "timestamp": time.time()
            }

        # 4. RFID Emergency from ESP8266
        if raw == "RFID":
            return {
                "type": "event",
                "event": "EMERGENCY",
                "source": "esp8266",
                "raw": raw,
                "timestamp": time.time()
            }

        # 5. Heartbeat / Handshake
        if raw == "ESP8266_HEARTBEAT":
            return {
                "type": "heartbeat",
                "device": "SENTRAX-ESP8266",
                "source": "esp8266",
                "raw": raw,
                "timestamp": time.time()
            }

        if raw in ("ESP32_READY", "ESP8266_READY"):
            return {
                "type": "handshake",
                "ready": True,
                "device": "SENTRAX-" + raw.split("_")[0],
                "source": raw.split("_")[0].lower(),
                "raw": raw,
                "timestamp": time.time()
            }

        # 6. Environmental / Day-Night
        if raw == "NIGHT":
            return {
                "type": "environment",
                "night_mode": True,
                "source": "esp8266",
                "raw": raw,
                "timestamp": time.time()
            }

        if raw == "DAY":
            return {
                "type": "environment",
                "night_mode": False,
                "source": "esp8266",
                "raw": raw,
                "timestamp": time.time()
            }

        # 7. Safety Alert Events
        event_map = {
            "COLLISION": ("COLLISION", EventSeverity.CRITICAL, "Acoustic impact sensor detected collision"),
            "WRONG": ("WRONG_WAY", EventSeverity.CRITICAL, "Reverse IR sequence (IR4 -> IR3) detected wrong-way vehicle"),
            "RASH": ("OVERSPEED", EventSeverity.WARNING, "Ultrasonic detector recorded overspeed driving"),
            "CONGESTION": ("CONGESTION", EventSeverity.WARNING, "Two or more IR sensors occupied continuously >= 5s"),
            "STALLED": ("STALLED", EventSeverity.WARNING, "Vehicle stopped on IR sensor continuously >= 15s"),
            "WET": ("WET_ROAD", EventSeverity.WARNING, "Moisture sensor detected wet road surface (< 2000)"),
            "TEMP": ("HIGH_TEMP", EventSeverity.INFO, "DHT11 ambient temperature exceeded 30 deg C"),
            "HUMIDITY": ("HIGH_HUMIDITY", EventSeverity.INFO, "DHT11 relative humidity exceeded 80%"),
            "NORMAL": ("NORMAL", EventSeverity.INFO, "Road conditions restored to clear")
        }

        # Also support "STATE:<event>" format
        event_key = raw[6:] if raw.startswith("STATE:") else raw

        if event_key in event_map:
            etype, sev, desc = event_map[event_key]
            return {
                "type": "event",
                "event": etype,
                "severity": sev.value,
                "description": desc,
                "source": default_source.lower(),
                "raw": raw,
                "timestamp": time.time()
            }

        # Unrecognized message
        return {
            "type": "unknown",
            "raw": raw,
            "source": default_source.lower(),
            "timestamp": time.time()
        }

    def to_canonical_event(self, parsed: Dict[str, Any]) -> Optional[CanonicalEvent]:
        if parsed.get("type") != "event":
            return None

        event_type_str = parsed.get("event", "NORMAL")
        try:
            etype = EventType(event_type_str)
        except ValueError:
            etype = EventType.NORMAL

        sev_str = parsed.get("severity", "INFO")
        try:
            sev = EventSeverity(sev_str)
        except ValueError:
            sev = EventSeverity.INFO

        source_upper = parsed.get("source", "ESP32").upper()

        return CanonicalEvent(
            source=source_upper,
            type=etype,
            severity=sev,
            confidence=0.95,
            title=f"SentraX Alert: {etype.value}",
            description=parsed.get("description", f"Event generated from {source_upper}"),
            payload={"raw_serial": parsed.get("raw")},
            is_simulated=False
        )

    def apply_to_telemetry(self, parsed: Dict[str, Any], current_telemetry: CanonicalTelemetry) -> CanonicalTelemetry:
        t = current_telemetry.model_copy(deep=True)
        ptype = parsed.get("type")

        if ptype == "speed":
            t.measured_speed_kmh = float(parsed["value"])
            t.source = DeviceSource.ESP32
        elif ptype == "recommended_speed":
            t.recommended_speed_kmh = float(parsed["value"])
        elif ptype == "environment":
            if "night_mode" in parsed:
                t.night_mode = parsed["night_mode"]
        elif ptype == "event":
            evt = parsed.get("event")
            if evt == "COLLISION":
                t.collision = True
            elif evt == "WRONG_WAY":
                t.wrong_way = True
            elif evt == "CONGESTION":
                t.traffic_level = TrafficLevel.CONGESTED
                t.recommended_speed_kmh = 60.0
            elif evt == "STALLED":
                t.stalled_vehicle = True
            elif evt == "WET_ROAD":
                t.road_condition = RoadCondition.WET
                t.recommended_speed_kmh = 40.0
            elif evt == "HIGH_TEMP":
                t.road_condition = RoadCondition.HIGH_TEMP
                t.recommended_speed_kmh = 35.0
            elif evt == "HIGH_HUMIDITY":
                t.road_condition = RoadCondition.HUMID
            elif evt == "EMERGENCY":
                t.emergency_vehicle = True
            elif evt == "NORMAL":
                t.collision = False
                t.wrong_way = False
                t.stalled_vehicle = False
                t.emergency_vehicle = False
                t.road_condition = RoadCondition.DRY
                t.traffic_level = TrafficLevel.LIGHT
                t.recommended_speed_kmh = 80.0

        t.timestamp = time.time()
        return t
