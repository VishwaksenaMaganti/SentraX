"""
SentraX Comprehensive Simulation & Demo Engine
Controls automated expo walkthrough scenarios, individual incident injections,
and high-fidelity synthetic sensor telemetry streams.
All generated data is explicitly stamped: is_simulated=True and source="SIMULATED".
"""

import asyncio
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from software.backend.schemas.telemetry import (
    CanonicalTelemetry, ConnectionState, RoadCondition, TrafficLevel, DeviceSource
)
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.recommendation_engine import RecommendationEngine
from software.backend.database.models import save_telemetry, save_event, update_device_status


class SentraXSimulator:
    def __init__(self, broadcast_callback: Optional[Callable] = None):
        self.broadcast_callback = broadcast_callback
        self.is_active = True
        self.current_scenario = "NORMAL"
        self.active_step = 1
        self.total_steps = 9
        self.auto_demo_running = False
        self._demo_task: Optional[asyncio.Task] = None

        # Base telemetry baseline in Standby mode
        self.telemetry = CanonicalTelemetry(
            device_id="SENTRAX-STANDBY",
            timestamp=time.time(),
            connection_state=ConnectionState.DISCONNECTED,
            measured_speed_kmh=0.0,
            recommended_speed_kmh=0.0,
            posted_speed_kmh=80.0,
            traffic_count=0,
            traffic_level=TrafficLevel.LIGHT,
            road_condition=RoadCondition.DRY,
            temperature_c=0.0,
            humidity_pct=0.0,
            moisture_raw=0,
            risk_score=0,
            risk_reasons=["Awaiting hardware connection of ESP32 Core Controller"],
            source=DeviceSource.FUSION,
            is_simulated=False,
            esp32_connected=False,
            esp8266_connected=False,
            both_modules_connected=False,
            hardware_standby=True
        )

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_active": self.is_active,
            "scenario": self.current_scenario,
            "auto_demo_running": self.auto_demo_running,
            "active_step": self.active_step,
            "total_steps": self.total_steps,
            "telemetry": self.telemetry.model_dump()
        }

    async def trigger_scenario(self, scenario_name: str) -> CanonicalTelemetry:
        """Immediately loads an individual predefined test scenario."""
        self.current_scenario = scenario_name.upper()
        t = self.telemetry.model_copy(deep=True)
        t.timestamp = time.time()
        t.is_simulated = True
        t.source = DeviceSource.SIMULATED

        # Reset base states
        t.collision = False
        t.wrong_way = False
        t.stalled_vehicle = False
        t.emergency_vehicle = False
        t.road_condition = RoadCondition.DRY
        t.traffic_level = TrafficLevel.LIGHT
        t.recommended_speed_kmh = 80.0
        t.sound_active = False
        t.rfid_active = False
        t.ir_sensors = [False, False, False, False]

        event_to_save: Optional[CanonicalEvent] = None

        if self.current_scenario == "NORMAL":
            t.measured_speed_kmh = 3.2
            t.recommended_speed_kmh = 80.0
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.NORMAL, severity=EventSeverity.INFO,
                title="Normal Road Clear", description="Baseline normal operations restored",
                is_simulated=True
            )

        elif self.current_scenario == "OVERSPEED":
            t.measured_speed_kmh = 4.8  # Exceeds toy-car 4.0 km/h limit!
            t.recommended_speed_kmh = 80.0
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.OVERSPEED, severity=EventSeverity.WARNING,
                title="OVERSPEED! RASH DRIVING",
                description="Toy-car speed 4.8 km/h exceeded demo threshold 4.0 km/h",
                payload={"measured_speed": 4.8, "limit": 4.0}, is_simulated=True
            )

        elif self.current_scenario == "CONGESTION":
            t.ir_sensors = [True, True, False, False]  # Two IR sensors blocked
            t.traffic_level = TrafficLevel.CONGESTED
            t.traffic_count = 3
            t.recommended_speed_kmh = 60.0
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.CONGESTION, severity=EventSeverity.WARNING,
                title="CONGESTION ALERT",
                description="2 IR sensors occupied >= 5 seconds. Advisory speed set to 60 km/h",
                is_simulated=True
            )

        elif self.current_scenario == "WRONG_WAY":
            t.wrong_way = True
            t.ir_sensors = [False, False, True, True]  # IR4 -> IR3 sequence
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.WRONG_WAY, severity=EventSeverity.CRITICAL,
                title="WRONG WAY VEHICLE DETECTED",
                description="Reverse transit detected on corridor sensor zone",
                is_simulated=True
            )

        elif self.current_scenario == "STALLED_VEHICLE":
            t.stalled_vehicle = True
            t.ir_sensors = [False, True, False, False]
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.STALLED, severity=EventSeverity.WARNING,
                title="STALLED VEHICLE ON CORRIDOR",
                description="Vehicle continuously occupying IR2 for 15+ seconds",
                is_simulated=True
            )

        elif self.current_scenario == "COLLISION":
            t.collision = True
            t.sound_active = True
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.COLLISION, severity=EventSeverity.CRITICAL,
                title="COLLISION DETECTED",
                description="Acoustic sensor registered severe impact deceleration",
                is_simulated=True
            )

        elif self.current_scenario == "WET_ROAD":
            t.road_condition = RoadCondition.WET
            t.moisture_raw = 850  # < 2000
            t.recommended_speed_kmh = 40.0
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.WET_ROAD, severity=EventSeverity.WARNING,
                title="ROAD WET - SLOW DOWN",
                description="Moisture sensor triggered; advisory speed updated to 40 km/h",
                is_simulated=True
            )

        elif self.current_scenario == "EMERGENCY":
            t.emergency_vehicle = True
            t.rfid_active = True
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.EMERGENCY, severity=EventSeverity.CRITICAL,
                title="EMERGENCY VEHICLE APPROACHING",
                description="RFID detected Priority Ambulance tag (5 dual-beep cadence active)",
                is_simulated=True
            )

        elif self.current_scenario == "HIGH_TEMP":
            t.temperature_c = 34.5
            t.road_condition = RoadCondition.HIGH_TEMP
            t.recommended_speed_kmh = 35.0
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.HIGH_TEMP, severity=EventSeverity.INFO,
                title="HIGH TEMPERATURE ALERT",
                description="Ambient road temp 34.5 deg C exceeded 30 deg C limit",
                is_simulated=True
            )

        elif self.current_scenario == "HIGH_HUMIDITY":
            t.humidity_pct = 88.0
            t.road_condition = RoadCondition.HUMID
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.HIGH_HUMIDITY, severity=EventSeverity.INFO,
                title="HIGH HUMIDITY WARNING",
                description="Atmospheric moisture level at 88% - reduced visibility",
                is_simulated=True
            )

        elif self.current_scenario == "POTHOLE":
            t.cv_pothole_count = 2
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.POTHOLE, severity=EventSeverity.WARNING,
                title="POTHOLE AHEAD - SLOW DOWN",
                description="Phone CV confirmed 2 asphalt craters in lane 1",
                is_simulated=True
            )

        elif self.current_scenario == "ANIMAL_HAZARD":
            t.hazard_count = 1
            event_to_save = CanonicalEvent(
                source="SIMULATED", type=EventType.ANIMAL, severity=EventSeverity.WARNING,
                title="ANIMAL CROSSING ROADWAY",
                description="Computer vision identified stray cattle/dog crossing corridor",
                is_simulated=True
            )

        # Recompute risk score & reasons
        r_score, reasons = RoadRiskEngine.calculate_risk(t)
        t.risk_score = r_score
        t.risk_reasons = reasons

        self.telemetry = t
        save_telemetry(t)
        if event_to_save:
            save_event(event_to_save)

        update_device_status("SENTRAX-ESP32", "SIMULATED", rssi=-62, last_event=self.current_scenario)
        update_device_status("SENTRAX-ESP8266", "SIMULATED", rssi=-69, last_event=self.current_scenario)

        if self.broadcast_callback:
            await self.broadcast_callback(t, event_to_save)

        return t

    async def start_one_click_demo(self):
        """
        Runs the mandatory 9-step demonstration script:
          STEP 1: Normal road (80 km/h)
          STEP 2: Toy car detected (4.5 km/h)
          STEP 3: Overspeed threshold exceeded (Show: OVERSPEED / RASH DRIVING)
          STEP 4: Two IR sensors occupied -> wait 5s -> CONGESTION -> Recommended: 60 km/h
          STEP 5: Wet road -> ROAD WET -> Recommended: 40 km/h
          STEP 6: Collision -> COLLISION
          STEP 7: RFID -> EMERGENCY
          STEP 8: Pothole -> POTHOLE AHEAD
          STEP 9: Road-risk score increases
        """
        if self.auto_demo_running:
            return
        self.auto_demo_running = True
        self._demo_task = asyncio.create_task(self._run_demo_sequence())

    async def stop_one_click_demo(self):
        self.auto_demo_running = False
        if self._demo_task:
            self._demo_task.cancel()
        await self.trigger_scenario("NORMAL")

    async def _run_demo_sequence(self):
        try:
            # STEP 1: Normal Road
            self.active_step = 1
            await self.trigger_scenario("NORMAL")
            await asyncio.sleep(4.0)

            # STEP 2: Toy Car Detected (Speed: 4.5 km/h)
            self.active_step = 2
            t = self.telemetry.copy(deep=True)
            t.measured_speed_kmh = 4.5
            t.ultrasonic_state = {"us1_active": True, "us2_active": True, "measuring": True}
            self.telemetry = t
            if self.broadcast_callback:
                await self.broadcast_callback(t, None)
            await asyncio.sleep(3.0)

            # STEP 3: Overspeed Threshold Exceeded (> 4.0 km/h)
            self.active_step = 3
            await self.trigger_scenario("OVERSPEED")
            await asyncio.sleep(4.0)

            # STEP 4: Two IR sensors occupied for 5 seconds -> CONGESTION (60 km/h)
            self.active_step = 4
            await self.trigger_scenario("CONGESTION")
            await asyncio.sleep(5.0)

            # STEP 5: Wet Road (40 km/h)
            self.active_step = 5
            await self.trigger_scenario("WET_ROAD")
            await asyncio.sleep(4.0)

            # STEP 6: Collision
            self.active_step = 6
            await self.trigger_scenario("COLLISION")
            await asyncio.sleep(4.0)

            # STEP 7: RFID Emergency
            self.active_step = 7
            await self.trigger_scenario("EMERGENCY")
            await asyncio.sleep(4.0)

            # STEP 8: Pothole
            self.active_step = 8
            await self.trigger_scenario("POTHOLE")
            await asyncio.sleep(3.0)

            # STEP 9: Composite High Road-Risk
            self.active_step = 9
            t = self.telemetry.copy(deep=True)
            t.risk_score = 88
            t.risk_reasons = [
                "Wet road surface active (+15)",
                "Severe pothole cluster verified (+30)",
                "Accident hazard perimeter (+25)",
                "High corridor congestion (+10)"
            ]
            self.telemetry = t
            save_telemetry(t)
            if self.broadcast_callback:
                await self.broadcast_callback(t, None)
            await asyncio.sleep(5.0)

        except asyncio.CancelledError:
            pass
        finally:
            self.auto_demo_running = False
