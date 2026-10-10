"""
SentraX Visual Emergency Vehicle Detector
Recognises ambulances, police cars and fire engines from the camera alone (no siren audio):
  1. Detector label: the open-vocabulary model calls the vehicle "ambulance", "police car", ...
  2. Flashing beacons: bright red or blue light inside the vehicle box that blinks on and off
  3. Light bar: bright red and bright blue lights on the vehicle at the same time
The body colour then separates an ambulance (mostly white) from a police car.
A recognised vehicle stays flagged for a few seconds so a blinking light does not flicker the result.
"""

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from software.backend.schemas.hazards import VehicleTrack

HISTORY_SECONDS = 2.0       # window used to judge flashing
HOLD_SECONDS = 3.0          # keep a vehicle flagged this long after the last evidence
LAMP_MIN_BRIGHTNESS = 220   # lit lamps are emissive; painted parts and wheel rims stay well below this
LIGHT_MIN_RATIO = 0.004     # share of the box top that must be lit red/blue to count as a lamp
FLASH_MIN_PEAK = 0.008      # a flashing lamp must light at least this share when on...
FLASH_MIN_SWING = 0.006     # ...and drop by at least this much when off
WHITE_BODY_RATIO = 0.45     # share of the car's centre that is white for an ambulance-style body
EMERGENCY_SUBTYPES = ("AMBULANCE", "POLICE", "FIRE_TRUCK", "EMERGENCY")


def light_ratios(crop_bgr: np.ndarray) -> Tuple[float, float, float]:
    """Shares of a vehicle crop that are lit red lamp, lit blue lamp, and white body.
    Lamps are looked for in the top 60% of the box, where roof beacons and light bars sit.
    The body colour is judged on the centre of the box so background around the car does not count."""
    if not CV2_AVAILABLE or crop_bgr is None or crop_bgr.size == 0:
        return 0.0, 0.0, 0.0
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    top = slice(0, max(1, int(hsv.shape[0] * 0.6)))
    ht, st, vt = h[top], s[top], v[top]
    red = ((ht <= 10) | (ht >= 170)) & (st >= 110) & (vt >= LAMP_MIN_BRIGHTNESS)
    blue = (ht >= 95) & (ht <= 130) & (st >= 110) & (vt >= LAMP_MIN_BRIGHTNESS)
    ch, cw = hsv.shape[:2]
    core = (slice(ch // 4, max(ch // 4 + 1, ch * 3 // 4)), slice(cw // 4, max(cw // 4 + 1, cw * 3 // 4)))
    white = (s[core] <= 35) & (v[core] >= 190)
    return float(red.mean()), float(blue.mean()), float(white.mean())


def is_flashing(values: List[float]) -> bool:
    """True if a lamp signal goes clearly on and off repeatedly (at least 3 crossings of its midpoint)."""
    if len(values) < 6:
        return False
    hi, lo = max(values), min(values)
    if hi < FLASH_MIN_PEAK or (hi - lo) < FLASH_MIN_SWING or lo > 0.4 * hi:
        return False
    mid = (hi + lo) / 2.0
    states = [x > mid for x in values]
    return sum(1 for a, b in zip(states, states[1:]) if a != b) >= 3


class EmergencyLightDetector:
    def __init__(self):
        self.history: Dict[str, Deque[Tuple[float, float, float, float, Optional[str]]]] = {}
        self.flagged: Dict[str, Dict] = {}  # label -> {"type", "reason", "flashing", "until"}

    def reset(self):
        self.history.clear()
        self.flagged.clear()

    def update(self, frame_bgr: np.ndarray, tracks: List[VehicleTrack], now: float) -> Dict[str, Dict]:
        """Analyses each tracked vehicle and returns {tracking_label: {"type", "reason", "flashing"}}
        for the ones recognised as emergency vehicles."""
        h, w = frame_bgr.shape[:2] if frame_bgr is not None else (0, 0)
        seen = set()
        for trk in tracks:
            label = trk.tracking_label
            seen.add(label)
            if trk.frames_missing:
                continue  # parked track not detected this frame: its old box may hold another vehicle now
            x, y, bw, bh = trk.bbox
            x1, y1 = max(0, int(x)), max(0, int(y))
            x2, y2 = min(w, int(x + bw)), min(h, int(y + bh))
            red, blue, white = light_ratios(frame_bgr[y1:y2, x1:x2]) if x2 > x1 and y2 > y1 else (0.0, 0.0, 0.0)
            sub = trk.vehicle_subtype if trk.vehicle_subtype in EMERGENCY_SUBTYPES else None

            hist = self.history.setdefault(label, deque())
            hist.append((now, red, blue, white, sub))
            while hist and now - hist[0][0] > HISTORY_SECONDS:
                hist.popleft()

            verdict = self._judge(hist, now)
            if verdict:
                verdict["until"] = now + HOLD_SECONDS
                self.flagged[label] = verdict

        # Forget vehicles that left the frame and flags that have expired
        for label in [k for k in self.history if k not in seen]:
            del self.history[label]
        for label in [k for k, v in self.flagged.items() if k not in seen or v["until"] < now]:
            del self.flagged[label]
        return {k: {"type": v["type"], "reason": v["reason"], "flashing": v["flashing"]} for k, v in self.flagged.items()}

    @staticmethod
    def _judge(hist, now: float) -> Optional[Dict]:
        reds = [e[1] for e in hist]
        blues = [e[2] for e in hist]
        white = float(np.median([e[3] for e in hist]))
        recent = [e for e in hist if now - e[0] <= 1.0]

        # 1. The detector itself recognised the vehicle type in at least 2 of the last frames
        subs = [e[4] for e in recent if e[4]]
        if len(subs) >= 2:
            sub = max(set(subs), key=subs.count)
            names = {"AMBULANCE": "an ambulance", "POLICE": "a police car", "FIRE_TRUCK": "a fire engine"}
            return {"type": sub, "reason": f"Looks like {names.get(sub, 'an emergency vehicle')}", "flashing": False}

        # 2. Flashing beacons
        red_flash, blue_flash = is_flashing(reds), is_flashing(blues)
        if red_flash or blue_flash:
            colours = " and ".join(c for c, f in (("red", red_flash), ("blue", blue_flash)) if f)
            if white >= WHITE_BODY_RATIO:
                kind = "AMBULANCE"
            elif blue_flash:
                kind = "POLICE"
            else:
                kind = "EMERGENCY"
            return {"type": kind, "reason": f"Flashing {colours} lights", "flashing": True}

        # 3. Red and blue light bar lit together in most recent frames
        both = [e for e in recent if e[1] >= LIGHT_MIN_RATIO and e[2] >= LIGHT_MIN_RATIO]
        if len(recent) >= 3 and len(both) >= 0.6 * len(recent):
            kind = "AMBULANCE" if white >= WHITE_BODY_RATIO else "POLICE"
            return {"type": kind, "reason": "Red and blue light bar", "flashing": False}
        return None
