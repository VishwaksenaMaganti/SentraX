"""
Tests for SentraX Simulation Engine & Scenario Triggers
"""

import pytest
import asyncio
from software.backend.simulation.simulator import SentraXSimulator
from software.backend.schemas.telemetry import RoadCondition, TrafficLevel


@pytest.mark.asyncio
async def test_simulation_scenario_triggers():
    sim = SentraXSimulator()

    # 1. Trigger Overspeed scenario
    t_over = await sim.trigger_scenario("OVERSPEED")
    assert t_over.measured_speed_kmh == 4.8
    assert t_over.measured_speed_kmh > 4.0  # Above demo threshold
    assert t_over.is_simulated is True
    assert t_over.risk_score > 0

    # 2. Trigger Congestion scenario
    t_cong = await sim.trigger_scenario("CONGESTION")
    assert t_cong.traffic_level == TrafficLevel.CONGESTED
    assert t_cong.recommended_speed_kmh == 60.0

    # 3. Trigger Wet Road scenario
    t_wet = await sim.trigger_scenario("WET_ROAD")
    assert t_wet.road_condition == RoadCondition.WET
    assert t_wet.recommended_speed_kmh == 40.0

    # 4. Trigger High Temp scenario
    t_temp = await sim.trigger_scenario("HIGH_TEMP")
    assert t_temp.road_condition == RoadCondition.HIGH_TEMP
    assert t_temp.recommended_speed_kmh == 35.0

    # 5. Trigger Reset to Normal
    t_norm = await sim.trigger_scenario("NORMAL")
    assert t_norm.road_condition == RoadCondition.DRY
    assert t_norm.recommended_speed_kmh == 80.0
