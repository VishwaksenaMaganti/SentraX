"""
SentraX AI Inference Engine
Provides a unified abstraction for running object detection via:
1. Custom trained PyTorch / YOLOv8 / YOLO11 weights (.pt)
2. High-performance ONNX Runtime (.onnx) for low-latency CPU/Edge inference
3. Calibrated OpenCV contour & motion foreground detection (zero-dependency fallback)
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

AI_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = AI_ROOT / "models"


class AIInferenceEngine:
    def __init__(self, model_filename: Optional[str] = None):
        self.model_filename = model_filename
        self.model = None
        self.model_type = "FALLBACK_OPENCV"
        self.is_loaded = False
        self._init_model()

    def _init_model(self):
        """Attempts to load custom trained weights if present in /ai/models/."""
        # Check for user-specified or default weights
        candidates = []
        if self.model_filename:
            candidates.append(MODELS_DIR / self.model_filename)
        candidates.extend([
            MODELS_DIR / "sentrax_custom_run" / "weights" / "best.pt",
            MODELS_DIR / "sentrax_yolo.onnx",
            MODELS_DIR / "yolov8n.pt"
        ])

        for path in candidates:
            if path.exists():
                try:
                    if path.suffix == ".pt":
                        from ultralytics import YOLO
                        self.model = YOLO(str(path))
                        self.model_type = f"YOLO_PYTORCH ({path.name})"
                        self.is_loaded = True
                        print(f"[SentraX AI] Successfully loaded model weights: {path}")
                        return
                    elif path.suffix == ".onnx":
                        import cv2
                        self.model = cv2.dnn.readNetFromONNX(str(path))
                        self.model_type = f"ONNX_DNN ({path.name})"
                        self.is_loaded = True
                        print(f"[SentraX AI] Successfully loaded ONNX model: {path}")
                        return
                except Exception as e:
                    print(f"[SentraX AI] Could not load weights from {path}: {e}")

        # If no custom weights found, use fallback
        self.model_type = "CALIBRATED_MOTION_HEURISTIC"
        self.is_loaded = False

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.40) -> List[Dict[str, Any]]:
        """
        Runs object detection and returns normalized bounding boxes with class labels.
        Output format:
            [{"class": str, "bbox": [x, y, w, h], "confidence": float, "area": int}]
        """
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        if self.is_loaded and "YOLO" in self.model_type:
            try:
                results = self.model.predict(frame_bgr, conf=conf_threshold, verbose=False)
                detections = []
                for r in results:
                    boxes = r.boxes
                    for box in boxes:
                        cls_id = int(box.cls[0].item())
                        cls_name = r.names.get(cls_id, f"class_{cls_id}").upper()
                        conf = float(box.conf[0].item())
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        w = int(x2 - x1)
                        h = int(y2 - y1)
                        x = int(x1)
                        y = int(y1)
                        detections.append({
                            "class": cls_name,
                            "bbox": [x, y, w, h],
                            "confidence": round(conf, 2),
                            "area": w * h
                        })
                return detections
            except Exception as e:
                print(f"[SentraX AI] YOLO inference exception: {e}")

        # Fallback to empty list so calling module falls back to its local contour analysis
        return []

    def get_status(self) -> Dict[str, Any]:
        return {
            "model_type": self.model_type,
            "is_weights_loaded": self.is_loaded,
            "models_dir": str(MODELS_DIR)
        }
