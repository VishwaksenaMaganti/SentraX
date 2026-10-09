"""
SentraX Multi-Class Road Object Detector
Detects vehicles (cars, trucks, buses, motorcycles, bicycles), pedestrians,
animals, and emergency vehicles from phone-camera or simulated camera frames.
Calibrated for the physical SentraX prototype (Red Sedan + Police Car) with
Road Region of Interest (ROI) filtering, color-contour persistence, and topple-over detection.
"""

from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import time

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from ai.inference.inference_engine import AIInferenceEngine
    AI_ENGINE_AVAILABLE = True
except ImportError:
    AI_ENGINE_AVAILABLE = False


class RoadObjectDetector:
    def __init__(self):
        self.is_initialized = CV2_AVAILABLE
        self.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=25, detectShadows=True) if CV2_AVAILABLE else None
        self.ai_engine = AIInferenceEngine() if AI_ENGINE_AVAILABLE else None

        # Road Region of Interest (ROI) calibrated for physical prototype
        # Default: Central horizontal corridor (excludes surrounding breadboards, jumper wires, sensor LEDs)
        self.roi_enabled = True
        self.roi_y_min = 0.16   # 16% from top
        self.roi_y_max = 0.84   # 84% from top (excludes bottom breadboard & IR LEDs)
        self.roi_x_min = 0.03   # 3% from left
        self.roi_x_max = 0.97   # 97% from right

    def set_roi(self, y_min: float, y_max: float, x_min: float = 0.02, x_max: float = 0.98, enabled: bool = True):
        """Updates Road Region of Interest bounds (normalized 0.0 to 1.0)."""
        self.roi_enabled = bool(enabled)
        self.roi_y_min = max(0.0, min(1.0, float(y_min)))
        self.roi_y_max = max(self.roi_y_min + 0.05, min(1.0, float(y_max)))
        self.roi_x_min = max(0.0, min(1.0, float(x_min)))
        self.roi_x_max = max(self.roi_x_min + 0.05, min(1.0, float(x_max)))

    def get_roi_pixels(self, w: int, h: int) -> Tuple[int, int, int, int]:
        """Calculates pixel coordinates (x1, y1, x2, y2) for the Road ROI."""
        if not self.roi_enabled:
            return 0, 0, w, h
        x1 = max(0, int(self.roi_x_min * w))
        y1 = max(0, int(self.roi_y_min * h))
        x2 = min(w, int(self.roi_x_max * w))
        y2 = min(h, int(self.roi_y_max * h))
        return x1, y1, x2, y2

    def detect(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Executes multi-class object detection.
        Combines Road ROI spatial gating, prototype vehicle color-signature segmentation
        (Red Sedan & Police Car with blue RFID fob), MOG2 motion, and rollover/topple analysis.
        """
        if not CV2_AVAILABLE or frame_bgr is None or frame_bgr.size == 0:
            return []

        h, w = frame_bgr.shape[:2]

        # 1. Try neural inference if weights loaded
        if self.ai_engine and self.ai_engine.is_loaded:
            ai_dets = self.ai_engine.detect(frame_bgr)
            if ai_dets:
                # Filter by Road ROI if enabled
                if self.roi_enabled:
                    x1, y1, x2, y2 = self.get_roi_pixels(w, h)
                    ai_filtered = []
                    for d in ai_dets:
                        bx, by, bw, bh = d["bbox"]
                        cx = bx + bw / 2.0
                        cy = by + bh / 2.0
                        if x1 <= cx <= x2 and y1 <= cy <= y2:
                            ai_filtered.append(d)
                    return ai_filtered
                return ai_dets

        # 2. Road ROI Gating
        x1, y1, x2, y2 = self.get_roi_pixels(w, h)
        roi_frame = frame_bgr[y1:y2, x1:x2]
        if roi_frame.size == 0:
            return []

        roi_h, roi_w = roi_frame.shape[:2]
        hsv_roi = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

        detections: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # PROTOTYPE VEHICLE 1: Red Sports Car / Sedan
        # -------------------------------------------------------------
        # Red hue wraps around 0/180 in HSV
        mask_red1 = cv2.inRange(hsv_roi, np.array([0, 75, 45]), np.array([12, 255, 255]))
        mask_red2 = cv2.inRange(hsv_roi, np.array([168, 75, 45]), np.array([180, 255, 255]))
        mask_red = cv2.bitwise_or(mask_red1, mask_red2)
        mask_red = cv2.morphologyEx(mask_red, cv2.MORPH_CLOSE, kernel)
        mask_red = cv2.dilate(mask_red, kernel, iterations=1)

        contours_red, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours_red:
            area = cv2.contourArea(c)
            # Area range adjusted for prototype toy car
            if 350 <= area <= 65000:
                rx, ry, rw, rh = cv2.boundingRect(c)
                aspect_ratio = float(rw) / max(1, rh)

                # Check if toppled over / rolled onto side:
                # Normal horizontal toy car: length is along road (rw > rh, ratio ~1.6 - 3.0)
                # Toppled on its side: aspect ratio collapses to square (~0.6 - 1.25) or height > width
                is_toppled = (0.5 <= aspect_ratio <= 1.28) or (rh > rw * 1.15)

                detections.append({
                    "class": "CAR",
                    "subclass": "RED_SEDAN",
                    "bbox": [x1 + rx, y1 + ry, rw, rh],
                    "confidence": 0.95,
                    "area": area,
                    "is_toppled": is_toppled,
                    "color_tag": "RED"
                })

        # -------------------------------------------------------------
        # PROTOTYPE VEHICLE 2: Police Car (Blue RFID Fob + Lightbar)
        # -------------------------------------------------------------
        # Distinct blue roof tag / lightbar and markings
        mask_blue = cv2.inRange(hsv_roi, np.array([95, 60, 45]), np.array([135, 255, 255]))
        mask_blue = cv2.morphologyEx(mask_blue, cv2.MORPH_CLOSE, kernel)
        mask_blue = cv2.dilate(mask_blue, kernel, iterations=1)

        contours_blue, _ = cv2.findContours(mask_blue, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours_blue:
            area = cv2.contourArea(c)
            if 140 <= area <= 45000:
                rx, ry, rw, rh = cv2.boundingRect(c)
                # Expand slightly to encompass car body around the blue RFID tag
                pad_x = int(rw * 0.35)
                pad_y = int(rh * 0.25)
                adj_rx = max(0, rx - pad_x)
                adj_ry = max(0, ry - pad_y)
                adj_rw = min(roi_w - adj_rx, rw + 2 * pad_x)
                adj_rh = min(roi_h - adj_ry, rh + 2 * pad_y)

                aspect_ratio = float(adj_rw) / max(1, adj_rh)
                is_toppled = (0.5 <= aspect_ratio <= 1.28) or (adj_rh > adj_rw * 1.15)

                detections.append({
                    "class": "EMERGENCY_VEHICLE",
                    "subclass": "POLICE_CAR",
                    "bbox": [x1 + adj_rx, y1 + adj_ry, adj_rw, adj_rh],
                    "confidence": 0.96,
                    "area": area,
                    "is_toppled": is_toppled,
                    "color_tag": "BLUE"
                })

        # -------------------------------------------------------------
        # 3. MOG2 Motion & Additional Objects within Road ROI
        # -------------------------------------------------------------
        if self.bg_subtractor is not None:
            fg_mask_roi = self.bg_subtractor.apply(roi_frame)
            cleaned = cv2.morphologyEx(fg_mask_roi, cv2.MORPH_OPEN, kernel)
            dilated = cv2.dilate(cleaned, kernel, iterations=2)

            contours_fg, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours_fg:
                area = cv2.contourArea(c)
                if area < 700 or area > 75000:
                    continue

                rx, ry, rw, rh = cv2.boundingRect(c)
                bx = x1 + rx
                by = y1 + ry

                # Non-Maximum Suppression: Skip if overlapping an already detected color vehicle
                overlap = False
                for existing in detections:
                    ex, ey, ew, eh = existing["bbox"]
                    # Compute intersection over min area
                    ix1 = max(bx, ex)
                    iy1 = max(by, ey)
                    ix2 = min(bx + rw, ex + ew)
                    iy2 = min(by + rh, ey + eh)
                    if ix1 < ix2 and iy1 < iy2:
                        inter_area = (ix2 - ix1) * (iy2 - iy1)
                        if inter_area > 0.25 * min(rw * rh, ew * eh):
                            overlap = True
                            break

                if overlap:
                    continue

                aspect_ratio = float(rw) / max(1, rh)
                is_toppled = (0.5 <= aspect_ratio <= 1.28) or (rh > rw * 1.15)

                if aspect_ratio > 1.8:
                    vclass = "BUS" if area > 14000 else "TRUCK"
                    conf = 0.86
                elif 0.8 <= aspect_ratio <= 1.8:
                    vclass = "CAR"
                    conf = 0.90
                elif 0.4 <= aspect_ratio < 0.8:
                    vclass = "MOTORCYCLE" if area > 2400 else "PEDESTRIAN"
                    conf = 0.84
                else:
                    vclass = "ANIMAL"
                    conf = 0.78

                detections.append({
                    "class": vclass,
                    "bbox": [bx, by, rw, rh],
                    "confidence": conf,
                    "area": area,
                    "is_toppled": is_toppled
                })

        return detections

    def generate_synthetic_frame(
        self,
        vehicles: int = 2,
        with_pothole: bool = False,
        with_wrong_way: bool = False,
        with_wet: bool = False,
        with_collision: bool = False,
        with_stalled: bool = False,
        with_toppled: bool = False
    ) -> np.ndarray:
        """
        Synthesizes a realistic 640x360 road camera scene with lanes, vehicles,
        potholes, collisions, stalled vehicles, and toppled vehicles for offline demonstration.
        """
        # Canvas: Asphalt road surface
        frame = np.full((360, 640, 3), 45, dtype=np.uint8)

        # Draw road margins and roadside
        frame[0:360, 0:60] = [35, 75, 45]
        frame[0:360, 580:640] = [35, 75, 45]

        # Kerb borders
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

        t = time.time()

        if with_toppled:
            # Vehicle rolled over onto its side / roof
            # Squarish flipped aspect ratio with exposed chassis/side
            cv2.rectangle(frame, (190, 160), (250, 240), (30, 40, 190), -1)  # Red body on side
            cv2.rectangle(frame, (200, 175), (240, 225), (15, 15, 15), -1)   # Dark underside
            # Rollover warning indicator on roof
            cv2.putText(frame, "TOPPLED", (182, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 60, 255), 2)
            if vehicles >= 2:
                # Police car approaching or standing by
                cv2.rectangle(frame, (380, 150), (450, 245), (200, 200, 200), -1)
                cv2.rectangle(frame, (400, 185), (430, 215), (220, 70, 30), -1)   # Blue RFID fob
        elif with_collision:
            # Two vehicles in direct contact / crash interaction
            cv2.rectangle(frame, (230, 160), (300, 240), (30, 40, 200), -1)   # Red car
            cv2.rectangle(frame, (285, 170), (355, 245), (210, 210, 210), -1) # Police car
            cv2.rectangle(frame, (305, 195), (335, 225), (220, 70, 30), -1)   # Blue lightbar
            cv2.circle(frame, (290, 200), 12, (0, 140, 255), -1)              # Impact spark point
        elif with_stalled:
            # Vehicle 1 is completely stationary at fixed position
            cv2.rectangle(frame, (180, 160), (250, 260), (30, 40, 200), -1)
            cv2.rectangle(frame, (185, 180), (245, 235), (20, 20, 20), -1)
            if vehicles >= 2:
                y_pos2 = int((t * 40 + 120) % 260) + 40
                x2 = 390
                cv2.rectangle(frame, (x2, y_pos2), (x2 + 70, y_pos2 + 95), (200, 200, 200), -1)
                cv2.rectangle(frame, (x2 + 20, y_pos2 + 35), (x2 + 50, y_pos2 + 65), (220, 70, 30), -1)
        else:
            # Normal moving vehicles
            y_pos1 = int((t * 50) % 280) + 40
            # Red car
            cv2.rectangle(frame, (180, y_pos1), (250, y_pos1 + 100), (30, 40, 200), -1)
            cv2.rectangle(frame, (185, y_pos1 + 20), (245, y_pos1 + 75), (20, 20, 20), -1)

            if vehicles >= 2:
                y_pos2 = int((t * 40 + 120) % 260) + 40
                x2 = 390
                color2 = (220, 50, 40) if with_wrong_way else (200, 200, 200)
                # Police car
                cv2.rectangle(frame, (x2, y_pos2), (x2 + 70, y_pos2 + 95), color2, -1)
                cv2.rectangle(frame, (x2 + 20, y_pos2 + 35), (x2 + 50, y_pos2 + 65), (220, 70, 30), -1)

        return frame
