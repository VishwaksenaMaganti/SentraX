"""
SentraX Object Detector Training Pipeline
Fine-tunes a pretrained YOLO-family architecture on the custom SentraX Road Perception Dataset,
evaluates held-out test accuracy, and exports optimized weights for real-time deployment.
"""

import sys
import os
from pathlib import Path

# Paths
AI_ROOT = Path(__file__).resolve().parent.parent
DATASET_CONFIG = AI_ROOT / "datasets" / "dataset.yaml"
OUTPUT_MODELS_DIR = AI_ROOT / "models"


def check_environment():
    """Verifies PyTorch and Ultralytics environment."""
    print("=" * 65)
    print("SENTRAX AI MODEL TRAINING & OPTIMIZATION PIPELINE")
    print("=" * 65)

    try:
        import torch
        print(f"[OK] PyTorch Version: {torch.__version__}")
        print(f"[OK] CUDA Available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            print(f"     Device: {torch.cuda.get_device_name(0)}")
        else:
            print("     Device: CPU (Training will proceed using CPU)")
    except ImportError:
        print("[!] PyTorch is not currently installed. Run: pip install torch torchvision")

    try:
        import ultralytics
        print(f"[OK] Ultralytics YOLO Version: {ultralytics.__version__}")
        return True
    except ImportError:
        print("[!] Ultralytics is not installed. Run: pip install ultralytics")
        return False


def train_sentrax_model(
    base_model: str = "yolov8n.pt",
    epochs: int = 50,
    batch_size: int = 16,
    img_size: int = 640,
    export_onnx: bool = True
):
    """
    Executes fine-tuning with transfer learning on the 11 SentraX target classes.
    """
    if not check_environment():
        print("\n[INFO] Ultralytics package is required to execute automated training.")
        print("To install all training dependencies, run:")
        print("    pip install ultralytics torch torchvision")
        return False

    from ultralytics import YOLO

    print(f"\n[1/4] Initializing base pretrained model: {base_model}...")
    model = YOLO(base_model)

    if not DATASET_CONFIG.exists():
        print(f"[ERROR] Dataset configuration not found at: {DATASET_CONFIG}")
        return False

    print(f"[2/4] Starting transfer learning on {DATASET_CONFIG}...")
    print(f"      Epochs: {epochs} | Batch Size: {batch_size} | Image Size: {img_size}")

    results = model.train(
        data=str(DATASET_CONFIG),
        epochs=epochs,
        batch=batch_size,
        imgsz=img_size,
        patience=15,
        project=str(OUTPUT_MODELS_DIR),
        name="sentrax_custom_run",
        exist_ok=True,
        verbose=True
    )

    print("\n[3/4] Evaluating model on held-out validation set...")
    val_results = model.val()
    print("Held-out evaluation metrics:")
    if hasattr(val_results, 'box'):
        print(f"  mAP@50:    {val_results.box.map50:.4f}")
        print(f"  mAP@50-95: {val_results.box.map:.4f}")
        print(f"  Precision: {val_results.box.mp:.4f}")
        print(f"  Recall:    {val_results.box.mr:.4f}")

    if export_onnx:
        print("\n[4/4] Exporting model to ONNX for real-time edge deployment...")
        onnx_path = model.export(format="onnx", imgsz=img_size, dynamic=True)
        print(f"  [+] ONNX Model saved: {onnx_path}")

    print("\n[SUCCESS] SentraX model training & export completed successfully.")
    return True


if __name__ == "__main__":
    epochs_val = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    train_sentrax_model(epochs=epochs_val)
