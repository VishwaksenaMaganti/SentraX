"""
SentraX Dataset Frame Collector & Exporter
Captures video frames from Phone Webcam, RTSP stream, or local video file,
allowing researchers to collect and prepare training datasets for YOLO fine-tuning.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import cv2
except ImportError:
    cv2 = None


def collect_frames_from_source(
    source: str = "0",
    output_dir: str = "ai/datasets/images/raw",
    frame_interval_sec: float = 0.5,
    max_frames: int = 100
):
    """
    Captures frames periodically from the camera or video stream and saves them as JPEGs.
    """
    if cv2 is None:
        print("[ERROR] OpenCV (cv2) is not installed. Please install opencv-python.")
        return

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    src = int(source) if source.isdigit() else source
    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        print(f"[ERROR] Could not open video source: {source}")
        return

    print(f"[SentraX Collector] Capturing up to {max_frames} frames from '{source}' into '{out_path}'...")
    print(f"[SentraX Collector] Capture interval: {frame_interval_sec}s. Press 'q' in preview to stop.")

    captured_count = 0
    last_capture_time = 0.0

    try:
        while captured_count < max_frames:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[SentraX Collector] End of stream or frame read failure.")
                break

            now = time.time()
            if now - last_capture_time >= frame_interval_sec:
                filename = out_path / f"frame_{int(now * 1000)}_{captured_count:04d}.jpg"
                cv2.imwrite(str(filename), frame)
                captured_count += 1
                last_capture_time = now
                print(f"  [+] Saved ({captured_count}/{max_frames}): {filename.name}")

            time.sleep(0.01)

    finally:
        cap.release()
        print(f"[SentraX Collector] Completed. Saved {captured_count} frames to {out_path}.")


if __name__ == "__main__":
    src_arg = sys.argv[1] if len(sys.argv) > 1 else "0"
    max_arg = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    collect_frames_from_source(source=src_arg, max_frames=max_arg)
