"""
SentraX Road Health Score Engine
Evaluates long-term structural and operational condition of road corridors (0 to 100).
Implements exponential moving average (EMA) temporal smoothing so a single frame
does not wildly disrupt health ratings.
Bands:
  85 - 100: EXCELLENT
  65 - 84:  GOOD
  40 - 64:  MODERATE
  20 - 39:  POOR
  0 - 19:   CRITICAL
NOTE: SentraX prototype metrics for adaptive infrastructure, not official government standards.
"""

from typing import Dict, Any, List, Tuple, Optional


class RoadHealthEngine:
    # State tracking for exponential moving average (EMA)
    _smoothed_health_score: float = 84.0
    _smoothing_alpha: float = 0.15  # Gradual historical adaptation factor

    @classmethod
    def get_band_and_color(cls, score: float) -> Tuple[str, str]:
        if score >= 85:
            return "GOOD", "#10b981"        # Green (Excellent/Good)
        elif score >= 65:
            return "MODERATE", "#eab308"    # Amber
        elif score >= 40:
            return "POOR", "#f97316"        # Orange
        else:
            return "CRITICAL", "#ef4444"    # Red

    @classmethod
    def evaluate_segment_health(
        cls,
        collision_history: int = 0,
        is_wet: bool = False,
        traffic_congestion: bool = False,
        stalled_events: int = 0,
        wrong_way_events: int = 0,
        base_score: int = 100,
        apply_smoothing: bool = False
    ) -> Tuple[int, str, str, List[str]]:
        raw_score = base_score
        penalties: List[str] = []

        # 2. Collision history (-20 per recorded crash, capped at -30)
        if collision_history > 0:
            c_deduct = min(30, collision_history * 20)
            raw_score -= c_deduct
            penalties.append(f"{collision_history} incident(s) in sector history (-{c_deduct})")

        # 3. Wet road surface
        if is_wet:
            raw_score -= 10
            penalties.append("Wet road surface / reduced friction index (-10)")

        # 4. Recurring congestion
        if traffic_congestion:
            raw_score -= 10
            penalties.append("Recurring traffic bottleneck (-10)")

        # 5. Stalled vehicles
        if stalled_events > 0:
            s_deduct = min(15, stalled_events * 10)
            raw_score -= s_deduct
            penalties.append(f"Obstruction/stalled incident (-{s_deduct})")

        # 6. Wrong way events
        if wrong_way_events > 0:
            raw_score -= 20
            penalties.append("Wrong-way vehicular breach recorded (-20)")

        raw_score = max(0, min(100, raw_score))

        # Temporal Smoothing: Exponential Moving Average (EMA) (Section 26)
        if apply_smoothing:
            cls._smoothed_health_score = (
                (1.0 - cls._smoothing_alpha) * cls._smoothed_health_score +
                (cls._smoothing_alpha * float(raw_score))
            )
            final_score = int(round(cls._smoothed_health_score))
        else:
            final_score = raw_score

        band, color = cls.get_band_and_color(final_score)

        if not penalties:
            penalties.append("Pristine asphalt; no degradation factors detected")

        return final_score, band, color, penalties

    @classmethod
    def set_smoothed_score(cls, val: float):
        cls._smoothed_health_score = float(max(0.0, min(100.0, val)))
