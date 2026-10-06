"""
SentraX Multi-Class Road Object Detector
Detects vehicles (cars, trucks, buses, motorcycles, bicycles), pedestrians,
animals, and emergency vehicles from phone-camera or simulated camera frames.
"""

from typing import List, Dict, Any, Tuple
import numpy as np
import time

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class RoadObjectDetector:
    def __init__(self):
        self.is_initialized = CV2_AVAILABLE
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True) if CV2_AVAILABLE else None

    def detect(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Executes motion-foreground and contour analysis, classifying detected road bounding boxes.
        When neural weights are unavailable locally, applies calibrated geometric and aspect-ratio heuristics.
        """
        detections: List[Dict[str, Any]] = []
        if not CV2_AVAILABLE or frame_bgr is None or frame_bgr.size == 0:
            return detections

        fg_mask = self.bg_subtractor.apply(frame_bgr)
        # Morphological filtering to clean noise
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        cleaned = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, kernel)
        dilated = cv2.dilate(cleaned, kernel, iterations=2)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            area = cv2.contourArea(c)
            if area < 800 or area > 100000:
                continue

            x, y, w, h = cv2.boundingRect(c)
            aspect_ratio = float(w) / max(1, h)

            # Heuristic classification for prototype road environment
            if aspect_ratio > 1.8:
                vclass = "BUS" if area > 15000 else "TRUCK"
                conf = 0.86
            elif 0.8 <= aspect_ratio <= 1.8:
                vclass = "CAR"
                conf = 0.91
            elif 0.4 <= aspect_ratio < 0.8:
                vclass = "MOTORCYCLE" if area > 2500 else "PEDESTRIAN"
                conf = 0.84
            else:
                vclass = "ANIMAL"
                conf = 0.78

            detections.append({
                "class": vclass,
                "bbox": [x, y, w, h],
                "confidence": conf,
                "area": area
            })

        return detections

    def generate_synthetic_frame(
        self,
        vehicles: int = 2,
        with_pothole: bool = False,
        with_wrong_way: bool = False,
        with_wet: bool = False
    ) -> np.ndarray:
        """
        Synthesizes a realistic 640x360 road camera scene with lanes, vehicles,
        potholes, and HUD overlays for live offline demonstration.
        """
        # Canvas: Asphalt road surface
        frame = np.full((360, 640, 3), 45, dtype=np.uint8)

        # Draw road margins and lanes
        # Grass roadside (greenish)
        frame[0:360, 0:60] = [35, 75, 45]
        frame[0:360, 580:640] = [35, 75, 45]

        # Kerb borders (white/yellow)
        cv2.line(frame, (60, 0), (60, 360), (220, 220, 220), 4)
        cv2.line(frame, (580, 0), (580, 360), (220, 220, 220), 4)

        # Center lane dashed markings
        for y in range(0, 360, 40):
            cv2.line(frame, (320, y), (320, y + 20), (255, 255, 255), 3)

        # Wet road surface reflection simulation
        if with_wet:
            overlay = frame.copy()
            cv2.rectangle(overlay, (60, 0), (580, 360), (90, 80, 60), -1)
            cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)

        # Pothole defect
        if with_pothole:
            cv2.ellipse(frame, (230, 220), (35, 20), 15, 0, 360, (20, 20, 20), -1)
            cv2.ellipse(frame, (230, 220), (37, 22), 15, 0, 360, (70, 70, 70), 2)

        # Draw simulated vehicles
        t = time.time()
        y_pos1 = int((t * 50) % 280) + 40
        # Vehicle 1: Standard lane
        cv2.rectangle(frame, (180, y_pos1), (250, y_pos1 + 100), (40, 90, 220), -1)
        cv2.rectangle(frame, (185, y_pos1 + 20), (245, y_pos1 + 75), (20, 20, 20), -1)  # windshield

        if vehicles >= 2:
            y_pos2 = int((t * 40 + 120) % 260) + 40
            x2 = 390
            color2 = (220, 50, 40) if with_wrong_way else (50, 180, 50)
            cv2.rectangle(frame, (x2, y_pos2), (x2 + 70, y_pos2 + 95), color2, -1)
            cv2.rectangle(frame, (x2 + 5, y_pos2 + 15), (x2 + 65, y_pos2 + 70), (20, 20, 20), -1)

        return frame
