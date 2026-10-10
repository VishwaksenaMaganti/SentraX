# SentraX AI Architecture & Model Training Pipeline

## 1. Overview
The SentraX Computer Vision subsystem utilizes a hybrid architecture:
1. **Pretrained & Custom YOLO Detector**: Detects multi-class road participants and infrastructure hazards.
2. **Persistent Centroid & Trajectory Tracker (`CAM-001` format)**: Maintains object state across temporal frames.
3. **Calibrated Fallback Detector**: Guarantees zero-downtime offline execution using morphological contour and motion subtraction when neural weights are not yet downloaded.

---

## 2. Target Perception Classes

| ID | Class | Priority | Category | Status in Baseline |
|:---|:---|:---|:---|:---|
| 0 | `car` | PRIMARY | Vehicle | Pretrained (COCO Class 2) |
| 1 | `motorcycle` | PRIMARY | Vehicle | Pretrained (COCO Class 3) |
| 2 | `bus` | PRIMARY | Vehicle | Pretrained (COCO Class 5) |
| 3 | `truck` | PRIMARY | Vehicle | Pretrained (COCO Class 7) |
| 4 | `bicycle` | PRIMARY | Vehicle | Pretrained (COCO Class 1) |
| 5 | `auto_rickshaw` | PRIMARY | Vehicle | **Requires Custom Training** |
| 6 | `pedestrian` | PRIMARY | Vulnerable User | Pretrained (COCO Class 0) |
| 7 | `animal` | SECONDARY | Vulnerable User | Pretrained (COCO Class 15-21) |
| 8 | `emergency_vehicle`| PRIMARY | Priority Fleet | **Requires Custom Training** |
| 9 | `crashed_vehicle` | PRIMARY | Collision Hazard | **Requires Custom Training** |
| 10| `road_obstruction`| SECONDARY | Road Hazard | **Requires Custom Training** |

> **Priority Rule**: Vehicle detection and tracking are the primary development focus. Road hazard detection is a secondary enhancement.

---

## 3. End-to-End Workflow

### Step 1: Image Collection
Collect diverse road video footage under varied lighting (day, dusk, overcast) using a smartphone camera, roadside webcam, or miniature track setup:
```bash
python ai/datasets/data_collector.py 0 200
```
- `0`: Camera device index (or URL: `http://192.168.1.100:8080/video`)
- `200`: Maximum frames to capture at 0.5s intervals.
- Frames are saved into `ai/datasets/images/raw/`.

### Step 2: Annotation
1. Organize images into standard train/val folders:
   - `ai/datasets/images/train/` (80% of data)
   - `ai/datasets/images/val/` (20% of data)
2. Label bounding boxes using [CVAT](https://cvat.ai/) or [LabelImg](https://github.com/HumanSignal/labelImg) in **YOLO format**:
   - Each image `frame_001.jpg` must have a corresponding `frame_001.txt`.
   - Format per line: `<class_id> <x_center> <y_center> <width> <height>` (normalized 0.0 to 1.0).

### Step 3: Model Fine-Tuning
Execute transfer learning using YOLOv8 or YOLO11:
```bash
python ai/training/train_detector.py 50
```
- Base architecture: `yolov8n.pt` (Nano for high-speed 30+ FPS edge execution).
- Hyperparameters:
  - Input resolution: 640x640
  - Batch size: 16
  - Optimizer: AdamW / SGD
  - Early stopping patience: 15 epochs

### Step 4: Held-Out Validation & Scientific Integrity
> **Scientific Integrity Standard**: Never claim model accuracy without evaluating against an independent held-out test split.

The training script automatically computes and logs:
- **mAP@50**: Mean Average Precision at IoU 0.50
- **mAP@50-95**: Rigorous multi-threshold metric
- **Precision & Recall** curves per class
- **Confusion Matrix** identifying misclassification rates between vehicles and road artifacts.

### Step 5: Edge Export & Deployment
The training script exports optimized runtime weights:
```
ai/models/sentrax_custom_run/weights/best.onnx
```
Place `best.pt` or `best.onnx` into `ai/models/`. The SentraX backend automatically detects and initializes the weights on startup.
