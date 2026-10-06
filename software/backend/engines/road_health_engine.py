"""
SentraX Road Health Score Engine
Evaluates structural and operational health of road corridors (0 to 100).
Prototype Bands:
  85 - 100: GOOD
  65 - 84:  MODERATE
  40 - 64:  POOR
  0 - 39:   CRITICAL
NOTE: SentraX prototype metrics for adaptive infrastructure, not official government standards.
"""

from typing import Dict, Any, List, Tuple
from software.backend.schemas.routes import RoadSegment


class RoadHealthEngine:
    @staticmethod
    def get_band_and_color(score: int) -> Tuple[str, str]:
        if score >= 85:
            return "GOOD", "#22c55e"       # Vibrant green
        elif score >= 65:
            return "MODERATE", "#eab308"   # Warning amber
        elif score >= 40:
            return "POOR", "#f97316"       # Orange
        else:
            return "CRITICAL", "#ef4444"   # Red

    @staticmethod
    def evaluate_segment_health(
        potholes: int = 0,
        collision_history: int = 0,
        is_wet: bool = False,
        traffic_congestion: bool = False,
        stalled_events: int = 0,
        wrong_way_events: int = 0,
        base_score: int = 100
    ) -> Tuple[int, str, str, List[str]]:
        score = base_score
        penalties: List[str] = []

        # Potholes impact (-15 per major pothole, capped at -45)
        if potholes > 0:
            p_deduct = min(45, potholes * 15)
            score -= p_deduct
            penalties.append(f"{potholes} pothole(s) detected (-{p_deduct})")

        # Collision history
        if collision_history > 0:
            c_deduct = min(30, collision_history * 20)
            score -= c_deduct
            penalties.append(f"{collision_history} collision incident(s) (-{c_deduct})")

        # Wet road surface
        if is_wet:
            score -= 10
            penalties.append("Wet road surface / reduced grip (-10)")

        # Recurring congestion
        if traffic_congestion:
            score -= 10
            penalties.append("Recurring traffic bottleneck (-10)")

        # Stalled vehicles
        if stalled_events > 0:
            s_deduct = min(15, stalled_events * 10)
            score -= s_deduct
            penalties.append(f"Obstruction/stalled vehicle incident (-{s_deduct})")

        # Wrong way events
        if wrong_way_events > 0:
            score -= 20
            penalties.append("Wrong-way vehicular breach recorded (-20)")

        final_score = max(0, min(100, score))
        band, color = RoadHealthEngine.get_band_and_color(final_score)

        if not penalties:
            penalties.append("Surface integrity optimal; no degradation factors")

        return final_score, band, color, penalties
