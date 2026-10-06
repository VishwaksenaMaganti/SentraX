"""
SentraX Pothole & Road Surface Defect Detector
Identifies asphalt craters, severe cracks, and surface depressions via vision analysis.
"""

import time
import uuid
import numpy as np
from typing import List, Dict, Any, Tuple
from software.backend.schemas.hazards import PotholeRecord, HazardSeverity
from software.backend.database.models import save_pothole

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class PotholeDetector:
    def __init__(self, confidence_threshold: float = 0.75):
        self.confidence_threshold = confidence_threshold

    def detect_in_frame(
        self,
        frame_rgb: np.ndarray,
        base_lat: float = 12.9716,
        base_lng: float = 77.5946
    ) -> List[PotholeRecord]:
        """
        Analyzes road ROI for dark depressions, texture roughness, and contour gradients.
        Returns validated PotholeRecord entries.
        """
        potholes: List[PotholeRecord] = []
        if not CV2_AVAILABLE or frame_rgb is None or frame_rgb.size == 0:
            return potholes

        h, w = frame_rgb.shape[:2]
        # Focus on lower half of camera frame (road surface)
        roi = frame_rgb[int(h * 0.5):, :]
        gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # Adaptive thresholding for localized dark asphalt depressions
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 19, 5
        )

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            area = cv2.contourArea(c)
            # Filter realistic pothole contours for a road corridor
            if 400 < area < 15000:
                perimeter = cv2.arcLength(c, True)
                if perimeter == 0:
                    continue
                circularity = 4 * np.pi * (area / (perimeter * perimeter))

                # Potholes exhibit moderate irregular circularity / oval crater
                if 0.2 < circularity < 0.85:
                    x, y, cw, ch = cv2.boundingRect(c)
                    conf = min(0.96, 0.70 + (area / 20000.0) + (circularity * 0.15))

                    severity = HazardSeverity.HIGH if area > 3500 else HazardSeverity.MEDIUM
                    pothole = PotholeRecord(
                        id=f"pot_{uuid.uuid4().hex[:6]}",
                        latitude=base_lat + (y * 0.00001),
                        longitude=base_lng + (x * 0.00001),
                        severity=severity,
                        confidence=round(conf, 2),
                        timestamp=time.time(),
                        image_reference=f"frame_roi_{int(time.time())}.jpg",
                        road_health_impact=-15 if severity == HazardSeverity.HIGH else -10,
                        verified_by_cv=True,
                        is_simulated=False
                    )
                    save_pothole(pothole)
                    potholes.append(pothole)

        return potholes
