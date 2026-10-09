"""
SentraX Transparent Weighted Road Risk Engine
Computes normalized (0-100) Road Risk Score based on multi-source sensor and camera perception.
Implements configurable factor weights, critical event overrides, confidence-aware scaling,
and standardized risk levels (CRITICAL, HIGH, MODERATE, LOW, MINIMAL).
NOTE: SentraX prototype risk model for adaptive infrastructure, not an official government standard.
"""

from typing import Dict, Any, List, Tuple, Optional
from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition, TrafficLevel


class RoadRiskEngine:
    # Configurable Risk Factor Weights (Sum = 1.0)
    DEFAULT_WEIGHTS = {
        "traffic": 0.20,        # 20%
        "collision": 0.25,      # 25%
        "wrong_way": 0.20,       # 20%
        "road_damage": 0.15,    # 15% (Potholes)
        "wet_road": 0.10,       # 10%
        "stalled": 0.05,        # 5%
        "environment": 0.05     # 5% (High temp, high humidity)
    }

    weights = dict(DEFAULT_WEIGHTS)

    @classmethod
    def set_weights(cls, new_weights: Dict[str, float]):
        """Allows dynamic runtime reconfiguration of risk factor weights."""
        total = sum(new_weights.values())
        if total > 0:
            # Normalize to sum to 1.0
            cls.weights = {k: v / total for k, v in new_weights.items()}

    @classmethod
    def get_risk_level(cls, score: int) -> Tuple[str, str]:
        """Returns risk level and hex color code according to Section 23."""
        if score >= 80:
            return "CRITICAL", "#ef4444"   # Red
        elif score >= 60:
            return "HIGH", "#f97316"       # Orange
        elif score >= 40:
            return "MODERATE", "#eab308"   # Amber
        elif score >= 20:
            return "LOW", "#3b82f6"        # Blue
        else:
            return "MINIMAL", "#10b981"    # Green

    @classmethod
    def calculate_risk(
        cls,
        telemetry: CanonicalTelemetry,
        final_confidence: Optional[float] = None
    ) -> Tuple[int, List[str]]:
        """
        Calculates overall risk (0-100) using normalized 0-100 factors,
        applies critical overrides, and adjusts based on perception confidence.
        """
        reasons: List[str] = []

        # 1. Normalize individual risk factors (0 - 100 each)
        # Factor A: Traffic Risk (0-100)
        f_traffic = 0.0
        if telemetry.traffic_level == TrafficLevel.STANDSTILL:
            f_traffic = 100.0
            reasons.append("Standstill traffic bottleneck (Factor: 100)")
        elif telemetry.traffic_level == TrafficLevel.CONGESTED:
            f_traffic = 75.0
            reasons.append("Heavy traffic congestion (Factor: 75)")
        elif telemetry.traffic_level == TrafficLevel.MODERATE:
            f_traffic = 35.0
        elif telemetry.traffic_count >= 2:
            f_traffic = 50.0

        # Factor B: Collision Risk (0-100)
        f_collision = 100.0 if telemetry.collision else 0.0
        if telemetry.collision:
            reasons.append("Active vehicular collision detected (Factor: 100)")

        # Factor C: Wrong-Way Risk (0-100)
        f_wrong_way = 100.0 if telemetry.wrong_way else 0.0
        if telemetry.wrong_way:
            reasons.append("Wrong-way vehicle breach in progress (Factor: 100)")

        # Factor D: Road Damage / Potholes (0-100)
        f_damage = min(100.0, telemetry.cv_pothole_count * 35.0)
        if telemetry.cv_pothole_count > 0:
            reasons.append(f"{telemetry.cv_pothole_count} surface pothole(s) verified (Factor: {f_damage:.0f})")

        # Factor E: Wet Road (0-100)
        f_wet = 0.0
        if telemetry.road_condition == RoadCondition.WET or (0 < telemetry.moisture_raw < 2000):
            f_wet = 80.0
            reasons.append("Wet road surface / reduced traction (Factor: 80)")

        # Factor F: Stalled Vehicle (0-100)
        f_stalled = 100.0 if telemetry.stalled_vehicle else 0.0
        if telemetry.stalled_vehicle:
            reasons.append("Stationary/stalled vehicle blocking corridor lane (Factor: 100)")

        # Factor G: Environment (0-100)
        f_env = 0.0
        if telemetry.temperature_c >= 30.0:
            f_env += 50.0
            reasons.append(f"Elevated road temperature {telemetry.temperature_c:.1f}°C")
        if telemetry.humidity_pct >= 80.0:
            f_env += 40.0
            reasons.append(f"High relative humidity {telemetry.humidity_pct:.0f}%")
        f_env = min(100.0, f_env)

        # Factor H: Overspeed bonus
        f_overspeed = 0.0
        demo_speed_limit = 4.0
        if telemetry.measured_speed_kmh > demo_speed_limit:
            f_overspeed = min(100.0, (telemetry.measured_speed_kmh - demo_speed_limit) * 20.0)
            reasons.append(f"Vehicle overspeed detected: {telemetry.measured_speed_kmh:.1f} km/h")

        # 2. Weighted Sum Calculation
        weighted_score = (
            (cls.weights.get("traffic", 0.20) * f_traffic) +
            (cls.weights.get("collision", 0.25) * f_collision) +
            (cls.weights.get("wrong_way", 0.20) * f_wrong_way) +
            (cls.weights.get("road_damage", 0.15) * f_damage) +
            (cls.weights.get("wet_road", 0.10) * f_wet) +
            (cls.weights.get("stalled", 0.05) * f_stalled) +
            (cls.weights.get("environment", 0.05) * f_env) +
            (0.10 * f_overspeed)
        )

        score = int(round(weighted_score))

        # 3. Critical Event Overrides (Section 22)
        # Confirmed collision -> risk >= 85
        if telemetry.collision:
            score = max(score, 88)
            reasons.append("[OVERRIDE] Confirmed collision enforces critical risk >= 85")

        # Vehicle toppled over -> risk >= 90
        if getattr(telemetry, "vehicle_toppled", False):
            score = max(score, 90)
            reasons.append("[OVERRIDE] Vehicle toppled over / rollover enforces critical risk >= 90")

        # Confirmed wrong-way -> risk >= 80
        if telemetry.wrong_way:
            score = max(score, 82)
            reasons.append("[OVERRIDE] Confirmed wrong-way vehicle enforces critical risk >= 80")

        # Severe road damage -> risk >= 65
        if telemetry.cv_pothole_count >= 2:
            score = max(score, 68)
            reasons.append("[OVERRIDE] Multiple severe potholes enforce high risk >= 65")

        # Simultaneous hazard increase
        hazard_signals = sum([
            1 if telemetry.collision else 0,
            1 if telemetry.wrong_way else 0,
            1 if telemetry.stalled_vehicle else 0,
            1 if telemetry.road_condition == RoadCondition.WET else 0,
            1 if telemetry.cv_pothole_count > 0 else 0
        ])
        if hazard_signals >= 2:
            score = min(100, score + (hazard_signals * 5))
            reasons.append(f"Compound multi-hazard escalation (+{hazard_signals * 5})")

        # 4. Confidence-Aware Adjustment (Section 24)
        if final_confidence is not None and final_confidence < 0.70:
            # Lower confidence slightly attenuates unverified single-source risk
            score = max(20, int(score * max(0.65, final_confidence)))

        clamped = max(0, min(100, score))
        if not reasons:
            reasons.append("Road clear; optimal visibility and traction")

        return clamped, reasons
