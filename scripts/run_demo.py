"""
CLI Demo Runner for SentraX Simulation Scenarios
"""

import sys
import asyncio
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from software.backend.simulation.simulator import SentraXSimulator
from software.backend.database.connection import init_db


async def main():
    init_db()
    sim = SentraXSimulator()
    print("=" * 60)
    print("SENTRAX EXPO DEMONSTRATION RUNNER (SYNTHETIC / SIMULATED)")
    print("=" * 60)

    scenarios = [
        ("NORMAL ROAD", "NORMAL", 80.0),
        ("TOY CAR DETECTED (OVERSPEED > 4.0 km/h)", "OVERSPEED", 4.8),
        ("TWO IR OCCUPIED 5s (CONGESTION)", "CONGESTION", 60.0),
        ("WET ROAD (MOISTURE < 2000)", "WET_ROAD", 40.0),
        ("ACOUSTIC IMPACT COLLISION", "COLLISION", 20.0),
        ("RFID EMERGENCY AMBULANCE", "EMERGENCY", 80.0),
        ("CV POTHOLE CLUSTER VERIFIED", "POTHOLE", 35.0)
    ]

    for label, sc, target in scenarios:
        print(f"\n---> TRIGGERING: {label} [Scenario: {sc}]")
        t = await sim.trigger_scenario(sc)
        print(f"     Speed: {t.measured_speed_kmh} km/h | Rec Limit: {t.recommended_speed_kmh} km/h")
        print(f"     Risk Score: {t.risk_score}/100 | Reasons: {', '.join(t.risk_reasons)}")
        time.sleep(1)

    print("\n" + "=" * 60)
    print("EXPO DEMONSTRATION COMPLETED SUCCESSFULLY.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
