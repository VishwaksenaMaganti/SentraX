"""
SentraX Global Configuration Settings
"""

import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    PROJECT_NAME: str = "SentraX Intelligent Road Infrastructure"
    API_PREFIX: str = "/api"
    HOST: str = os.getenv("SENTRAX_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SENTRAX_PORT", 8000))
    DEBUG: bool = os.getenv("SENTRAX_DEBUG", "True").lower() == "true"

    # Hardware & Demonstration Defaults
    DEMO_OVERSPEED_LIMIT: float = 4.0   # km/h (toy car demonstration limit)
    NORMAL_RECOMMENDED_SPEED: float = 80.0
    CONGESTION_RECOMMENDED_SPEED: float = 60.0
    WET_ROAD_RECOMMENDED_SPEED: float = 40.0
    HIGH_TEMP_RECOMMENDED_SPEED: float = 35.0
    SENSOR_DISTANCE: float = 0.30       # meters between ultrasonic sensors

    # Time thresholds (seconds)
    # The ESP32 stops sending telemetry for ~9 s while it plays a blocking alert sequence
    # (e.g. the RFID emergency LED sweep + E-Ink refresh). Within this window a silent but
    # connected controller keeps its last reading instead of being treated as unplugged.
    TELEMETRY_STALL_TOLERANCE_SECONDS: float = 12.0
    # The IR modules on the testbed report the opposite of the firmware's "1 = vehicle" mapping,
    # so the dashboard flips every IR reading on arrival. Set SENTRAX_IR_INVERTED=false to undo.
    IR_INVERTED: bool = os.getenv("SENTRAX_IR_INVERTED", "true").lower() == "true"
    # How long the dashboard shows an emergency vehicle after an RFID scan is detected.
    EMERGENCY_HOLD_SECONDS: float = 8.0
    # How long a new vehicle speed reading is shown (matches the ESP32's E-Ink speed display).
    SPEED_READING_HOLD_SECONDS: float = 5.0
    CONGESTION_TIME_SECONDS: int = 5    # Mandatory change #1
    STALLED_TIME_SECONDS: int = 15
    WRONG_WAY_WINDOW_SECONDS: int = 15

    # Computer vision detector. "auto" runs YOLO + ByteTrack on live camera frames when
    # ultralytics is installed (synthetic frames always use the heuristics); "heuristic"
    # forces the colour/motion detector. Two pretrained models run together and their boxes
    # are merged: COCO yolo26m.pt (solid on ordinary car views) and the prompt-free open-vocabulary
    # yoloe-26s-seg-pf.pt (toy/model cars from any side, ambulances, police cars, fire engines).
    # Both download into ai/models/ on first use. Trained weights at
    # ai/models/sentrax_custom_run/weights/best.pt replace the COCO model. Set
    # SENTRAX_YOLO_OPEN_VOCAB_WEIGHTS="" to run the COCO model alone.
    CV_DETECTOR: str = os.getenv("SENTRAX_CV_DETECTOR", "auto")
    YOLO_WEIGHTS: str = os.getenv("SENTRAX_YOLO_WEIGHTS", "yolo26m.pt")
    YOLO_OPEN_VOCAB_WEIGHTS: str = os.getenv("SENTRAX_YOLO_OPEN_VOCAB_WEIGHTS", "yoloe-26s-seg-pf.pt")

    # Real size of the demo toy cars (1:64 die-cast). The camera turns pixels into metres using
    # the car's own size, so speeds read in real km/h without a calibration step.
    TOY_CAR_LENGTH_M: float = float(os.getenv("SENTRAX_TOY_CAR_LENGTH_M", "0.075"))
    TOY_CAR_WIDTH_M: float = float(os.getenv("SENTRAX_TOY_CAR_WIDTH_M", "0.035"))
    # Camera: seconds a vehicle must stand still before it is declared stalled (demo mode)
    CAMERA_DEMO_STALL_SECONDS: float = float(os.getenv("SENTRAX_CAMERA_STALL_SECONDS", "3.0"))

    # Serial & BLE
    SERIAL_PORT_ESP32: str = os.getenv("SERIAL_PORT_ESP32", "COM3")
    SERIAL_PORT_ESP8266: str = os.getenv("SERIAL_PORT_ESP8266", "COM4")
    SERIAL_BAUDRATE: int = 9600

    # Google Maps Platform Key (securely loaded from .env)
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")


settings = Settings()
