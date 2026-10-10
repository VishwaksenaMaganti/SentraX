# SentraX Road Health & Risk Scoring Model

## 1. Prototype Road Health Score (0 - 100)
SentraX calculates a continuous composite health metric representing physical corridor integrity and operational safety.

*Disclaimer: This is SentraX's prototype scoring model developed for adaptive infrastructure demonstration and is not an official governmental road index.*

### Prototype Health Bands
| Band | Score Range | Visual Color | Interpretation |
|---|---|---|---|
| **GOOD** | 85 – 100 | `#22c55e` (Green) | Smooth asphalt, no surface defects, clear visibility |
| **MODERATE** | 65 – 84 | `#eab308` (Yellow) | Minor surface wear, occasional traffic slowdowns |
| **POOR** | 40 – 64 | `#f97316` (Orange) | Recurring incidents, waterlogging, rough surface |
| **CRITICAL** | 0 – 39 | `#ef4444` (Red) | Severe damage, frequent collisions, major safety risk |

### Degradation Factors
- **Collision History**: -20 points per recorded impact blackspot (capped at -30).
- **Wet Surface**: -10 points during standing water or precipitation.
- **Persistent Congestion**: -10 points when traffic density remains high.
- **Stalled Vehicles**: -10 points per lane obstruction incident.
- **Wrong-Way Breaches**: -20 points per reported incident.

---

## 2. Road Risk Score (0 - 100)
Measures instantaneous navigational hazard level facing drivers on the corridor:

- **Collision**: +50
- **Wrong Way Vehicle**: +40
- **Stalled Vehicle**: +25
- **Near-Collision Trajectory**: +25
- **Overspeed Violation**: +20
- **Hazard Proximity**: +20
- **Wet Road Surface**: +15
- **Corridor Congestion**: +10
- **Elevated Temperature (&ge; 30°C)**: +5
- **High Humidity (&ge; 80%)**: +5
- **Clamping**: Clamped strictly between `0` and `100`.
