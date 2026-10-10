"""
SentraX AI Inference Engine
Provides a unified abstraction for running object detection via:
1. Custom trained PyTorch / YOLOv8 / YOLO11 weights (.pt)
2. High-performance ONNX Runtime (.onnx) for low-latency CPU/Edge inference
3. Calibrated OpenCV contour & motion foreground detection (zero-dependency fallback)

Weights load lazily on first use, so the backend starts without importing PyTorch.
Two pretrained models run on every frame and their boxes are merged before tracking:
  - COCO yolo26m.pt: reliable on ordinary car, truck, bus and bike views
  - open-vocabulary yoloe-26s-seg-pf.pt: knows "toy car", "model car", "ambulance",
    "police car", "fire truck" and more, so it catches toy cars seen head-on or from
    behind and recognises emergency vehicles by their look
Both download into /ai/models/ on first load. Custom trained weights replace the COCO model.
One ByteTrack instance gives every merged box a stable track ID.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

AI_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = AI_ROOT / "models"

DEFAULT_PRETRAINED_WEIGHTS = "yolo26m.pt"
DEFAULT_OPEN_VOCAB_WEIGHTS = "yoloe-26s-seg-pf.pt"

# COCO classes the pretrained detector keeps; every other COCO class is ignored
COCO_CLASS_MAP = {"car": "CAR", "truck": "TRUCK", "bus": "BUS", "motorcycle": "MOTORCYCLE", "bicycle": "BICYCLE"}

# Open-vocabulary labels -> (SentraX class, subtype). Every other label is ignored.
OPEN_VOCAB_CLASS_MAP: Dict[str, Tuple[str, Optional[str]]] = {
    # Emergency vehicles, recognised by livery, light bars and shape
    "ambulance": ("EMERGENCY_VEHICLE", "AMBULANCE"),
    "police car": ("EMERGENCY_VEHICLE", "POLICE"),
    "police van": ("EMERGENCY_VEHICLE", "POLICE"),
    "fire truck": ("EMERGENCY_VEHICLE", "FIRE_TRUCK"),
    "emergency vehicle": ("EMERGENCY_VEHICLE", "EMERGENCY"),
    # Toy and model cars (the bench demo). On the bench every toy is a car.
    "toy car": ("CAR", "TOY_CAR"), "model car": ("CAR", "TOY_CAR"), "toy": ("CAR", "TOY_CAR"),
    # Ordinary cars
    "car": ("CAR", None), "sports car": ("CAR", None), "race car": ("CAR", None), "muscle car": ("CAR", None),
    "concept car": ("CAR", None), "family car": ("CAR", None), "sedan": ("CAR", None), "coupe": ("CAR", None),
    "convertible": ("CAR", None), "suv": ("CAR", None), "jeep": ("CAR", None), "taxi": ("CAR", "TAXI"),
    "minivan": ("CAR", None), "van": ("CAR", None), "vehicle": ("CAR", None), "motor vehicle": ("CAR", None),
    "land vehicle": ("CAR", None),
    # Trucks, buses, two-wheelers, autos
    "truck": ("TRUCK", None), "lorry": ("TRUCK", None), "tow truck": ("TRUCK", None),
    "trailer truck": ("TRUCK", None), "garbage truck": ("TRUCK", None), "monster truck": ("TRUCK", None),
    "food truck": ("TRUCK", None),
    "bus": ("BUS", None), "city bus": ("BUS", None), "school bus": ("BUS", None), "tour bus": ("BUS", None),
    "decker bus": ("BUS", None),
    "motorcycle": ("MOTORCYCLE", None), "motorbike": ("MOTORCYCLE", None), "scooter": ("MOTORCYCLE", None),
    "dirt bike": ("MOTORCYCLE", None),
    "bicycle": ("BICYCLE", None), "mountain bike": ("BICYCLE", None),
    "rickshaw": ("AUTO_RICKSHAW", None),
}

# Detections down to this score go to ByteTrack, which uses the weak ones only to keep existing tracks alive
DETECTION_CONF = 0.08
# ByteTrack thresholds, lowered from the 0.25 defaults so views the models score lower
# (a toy car head-on or from behind) still start and keep a track
BYTETRACK_ARGS = dict(track_high_thresh=0.20, track_low_thresh=0.08, new_track_thresh=0.20,
                      track_buffer=30, match_thresh=0.8, fuse_score=True)
# Boxes from the two models that overlap this much are the same vehicle
MERGE_IOU = 0.45


class _Detector:
    def __init__(self, model, path: Path, class_map: Dict[int, Tuple[str, Optional[str], str]]):
        self.model = model
        self.path = path
        self.class_map = class_map  # model class id -> (SentraX class, subtype, raw label)
        self.class_ids = sorted(class_map)


def _overlap(a: List[float], b: List[float]) -> float:
    """IoU of two xyxy boxes; a box sitting almost entirely inside the other counts as a full match."""
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    iou = inter / (area_a + area_b - inter)
    inside = inter / max(1e-6, min(area_a, area_b))
    return 1.0 if inside >= 0.85 else iou


def merge_detections(dets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Joins overlapping boxes from several models into one per vehicle (highest score wins the box).
    An emergency label from either model wins over a plain one; otherwise the more specific label stays."""
    kept: List[Dict[str, Any]] = []
    for d in sorted(dets, key=lambda d: -d["conf"]):
        match = next((k for k in kept if _overlap(k["xyxy"], d["xyxy"]) >= MERGE_IOU), None)
        if match is None:
            kept.append(dict(d))
            continue
        if d["class"] == "EMERGENCY_VEHICLE" and match["class"] != "EMERGENCY_VEHICLE" and d["conf"] >= 0.25:
            match.update({"class": d["class"], "subclass": d["subclass"], "label": d["label"]})
        elif match["subclass"] is None and d["subclass"] and d["class"] == match["class"]:
            match.update({"subclass": d["subclass"], "label": d["label"]})
    return kept


class AIInferenceEngine:
    def __init__(self, model_filename: Optional[str] = None,
                 pretrained_weights: str = DEFAULT_PRETRAINED_WEIGHTS,
                 open_vocab_weights: Optional[str] = DEFAULT_OPEN_VOCAB_WEIGHTS):
        self.model_filename = model_filename
        self.pretrained_weights = pretrained_weights
        self.open_vocab_weights = open_vocab_weights or None
        self.model = None  # legacy single-model handle (ONNX path)
        self.detectors: List[_Detector] = []
        self.model_type = "CALIBRATED_MOTION_HEURISTIC"
        self.weights_path: Optional[Path] = None
        self.device = "cpu"
        self.is_loaded = False
        self.load_error: Optional[str] = None
        self._load_attempted = False
        self._reset_tracker = False
        self._tracker = None
        self._class_ids: Dict[str, int] = {}

    @property
    def can_track(self) -> bool:
        return self.is_loaded and self.model_type == "YOLO_PYTORCH"

    def _candidate_weights(self) -> List[Path]:
        candidates = []
        if self.model_filename:
            candidates.append(MODELS_DIR / self.model_filename)
        candidates.extend([
            MODELS_DIR / "sentrax_custom_run" / "weights" / "best.pt",
            MODELS_DIR / "sentrax_yolo.onnx",
            MODELS_DIR / self.pretrained_weights,
        ])
        return candidates

    def _load_detector(self, path: Path) -> _Detector:
        from ultralytics import YOLO  # downloads official pretrained weights if missing
        model = YOLO(str(path))
        names = model.names
        if len(names) > 1000:  # open-vocabulary model: keep the vehicle labels we know
            class_map = {i: (*OPEN_VOCAB_CLASS_MAP[n], n) for i, n in names.items() if n in OPEN_VOCAB_CLASS_MAP}
        elif len(names) == 80 and "person" in names.values():  # COCO
            class_map = {i: (COCO_CLASS_MAP[n], None, n) for i, n in names.items() if n in COCO_CLASS_MAP}
        else:  # custom trained weights keep every class
            class_map = {i: (n.upper(), None, n) for i, n in names.items()}
        # Warm-up pass so the first live frame does not stall on CUDA initialisation
        model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=self.device, verbose=False)
        return _Detector(model, path, class_map)

    def ensure_loaded(self) -> bool:
        """Loads the weights on the first call. Later calls return the cached result."""
        if self._load_attempted:
            return self.is_loaded
        self._load_attempted = True

        primary: Optional[_Detector] = None
        for path in self._candidate_weights():
            if not path.exists() and path.name != self.pretrained_weights:
                continue
            try:
                if path.suffix == ".pt":
                    import torch
                    self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
                    primary = self._load_detector(path)
                    break
                elif path.suffix == ".onnx":
                    import cv2
                    self.model = cv2.dnn.readNetFromONNX(str(path))
                    self.model_type = "ONNX_DNN"
                    self.weights_path = path
                    self.is_loaded = True
                    print(f"[SentraX AI] Successfully loaded ONNX model: {path}")
                    return True
            except Exception as e:
                self.load_error = f"{path.name}: {e}"
                print(f"[SentraX AI] Could not load weights from {path}: {e}")

        if primary is None:
            # No usable weights: callers fall back to the calibrated motion heuristic
            self.model_type = "CALIBRATED_MOTION_HEURISTIC"
            self.is_loaded = False
            return False

        self.detectors = [primary]
        if self.open_vocab_weights:
            try:
                self.detectors.append(self._load_detector(MODELS_DIR / self.open_vocab_weights))
            except Exception as e:
                # The COCO model still works alone
                self.load_error = f"{self.open_vocab_weights}: {e}"
                print(f"[SentraX AI] Open-vocabulary model unavailable: {e}")

        self.model_type = "YOLO_PYTORCH"
        self.weights_path = primary.path
        self.is_loaded = True
        self._new_tracker()
        print(f"[SentraX AI] Loaded {' + '.join(d.path.name for d in self.detectors)} on {self.device}")
        return True

    def _new_tracker(self):
        from ultralytics.trackers.byte_tracker import BYTETracker
        self._tracker = BYTETracker(SimpleNamespace(**BYTETRACK_ARGS))

    def reset_tracking(self):
        """Restarts ByteTrack on the next frame (new IDs). Use after the camera source changes."""
        self._reset_tracker = True

    def _detect_merged(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        raw: List[Dict[str, Any]] = []
        for det in self.detectors:
            r = det.model.predict(frame_bgr, conf=DETECTION_CONF, classes=det.class_ids, device=self.device,
                                  half=self.device.startswith("cuda"), verbose=False)[0]
            if r.boxes is None or len(r.boxes) == 0:
                continue
            for xyxy, cid, conf in zip(r.boxes.xyxy.tolist(), r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                mapped = det.class_map.get(cid)
                if mapped:
                    cls, sub, label = mapped
                    raw.append({"xyxy": xyxy, "conf": float(conf), "class": cls, "subclass": sub, "label": label})
        return merge_detections(raw)

    @staticmethod
    def _as_detection(d: Dict[str, Any]) -> Dict[str, Any]:
        x1, y1, x2, y2 = d["xyxy"]
        x, y, w, h = int(x1), int(y1), int(x2 - x1), int(y2 - y1)
        return {
            "class": d["class"],
            "subclass": d["subclass"],
            "detector_label": d["label"],
            "bbox": [x, y, w, h],
            "confidence": round(d["conf"], 2),
            "area": w * h
        }

    def detect(self, frame_bgr: np.ndarray, conf_threshold: float = 0.40) -> List[Dict[str, Any]]:
        """
        Runs object detection and returns normalized bounding boxes with class labels.
        Output format:
            [{"class": str, "subclass": str|None, "detector_label": str, "bbox": [x, y, w, h],
              "confidence": float, "area": int}]
        """
        if frame_bgr is None or frame_bgr.size == 0 or not self.can_track:
            return []
        try:
            return [self._as_detection(d) for d in self._detect_merged(frame_bgr) if d["conf"] >= conf_threshold]
        except Exception as e:
            print(f"[SentraX AI] YOLO inference exception: {e}")
            return []

    def track(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detects with every loaded model, merges the boxes and tracks them with ByteTrack.
        Same output as detect(), plus a stable integer "track_id". Boxes ByteTrack has not
        confirmed yet are left out.
        """
        if frame_bgr is None or frame_bgr.size == 0 or not self.can_track:
            return []
        try:
            from ultralytics.engine.results import Boxes
            merged = self._detect_merged(frame_bgr)
            if self._reset_tracker:
                self._reset_tracker = False
                self._new_tracker()
            rows = [[*d["xyxy"], d["conf"], self._class_ids.setdefault(d["class"], len(self._class_ids))] for d in merged]
            data = np.array(rows, dtype=np.float32) if rows else np.zeros((0, 6), dtype=np.float32)
            tracks = self._tracker.update(Boxes(data, frame_bgr.shape[:2]), frame_bgr)
            out = []
            for row in tracks:
                det = self._as_detection(merged[int(row[7])])  # the detection box, not the Kalman estimate
                det["track_id"] = int(row[4])
                out.append(det)
            return out
        except Exception as e:
            print(f"[SentraX AI] YOLO tracking exception: {e}")
            return []

    def get_status(self) -> Dict[str, Any]:
        return {
            "model_type": self.model_type,
            "is_weights_loaded": self.is_loaded,
            "weights": " + ".join(d.path.name for d in self.detectors) if self.detectors else (self.weights_path.name if self.weights_path else None),
            "models": [d.path.stem for d in self.detectors],
            "device": self.device if self.is_loaded else None,
            "tracker": "bytetrack" if self.can_track else None,
            "load_error": self.load_error,
            "models_dir": str(MODELS_DIR)
        }
