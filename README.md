# SentraX: Intelligent & Adaptive Road Safety Platform

> **INTELLIGENT AND ADAPTIVE ROAD SAFETY & SMART INFRASTRUCTURE SYSTEM**  
> *Transforming conventional passive roadways into a self-sensing, risk-aware, communicative infrastructure platform.*

---

## 1. Project Overview

Conventional road infrastructure consists of passive markers, static signs, and delayed manual incident reporting. **SentraX** enables the roadway itself to:

$$\text{SENSE} \longrightarrow \text{UNDERSTAND} \longrightarrow \text{DECIDE} \longrightarrow \text{RESPOND} \longrightarrow \text{MONITOR}$$

The physical prototype uses dual microcontrollers (**ESP32** and **ESP8266**) driving optical, ultrasonic, acoustic, environmental, and radio-frequency sensors. This software platform extends that foundation into an integrated ecosystem featuring:
- **Real-Time BLE & Serial Gateway**
- **Live Command Center Web UI** (12 operational views)
- **Multi-Modal Data Fusion** (Sensors + Camera Vision)
- **Computer Vision Vehicle Tracking, Speed Snapshots & Emergency Vehicle Recognition**
- **Road Risk (0–100) & Road Health (0–100) Scoring Engines**
- **Dynamic Speed Recommendations** (Advisory, not legal limits)
- **Google Maps-Style Navigation with Route Health Segmentation**
- **Automated 8-Step Expo Demo Mode** (100% offline runnable)

---

## 2. System Architecture

```
                 ┌────────────────────────────────┐
                 │       ESP32 Primary Node       │
                 │  Sensors + E-Ink + 60 LEDs     │
                 └───────────────┬────────────────┘
                                 │ UART / BLE
                 ┌───────────────▼────────────────┐
                 │     ESP8266 Auxiliary Node     │
                 │  RFID, LDR, Round TFT, Buzzer  │
                 └───────────────┬────────────────┘
                                 │
                   BLE / Serial Gateway Bridge
                                 │
                 ┌───────────────▼────────────────┐
                 │    SentraX Software Platform   │
                 │  - Canonical Telemetry & Events│
                 │  - Data Fusion Engine          │
                 │  - Road Risk & Health Engines  │
                 │  - Computer Vision Subsystem   │
                 │  - Map Route Segmentation      │
                 │  - SQLite Database Logger      │
                 └───────────────┬────────────────┘
                                 │ REST & WebSocket
                 ┌───────────────▼────────────────┐
                 │ Presentation Command Center UI │
                 │ - 12 Interactive Dashboard Views│
                 │ - Live Speed & Risk Streams    │
                 │ - Real-Time MJPEG Vision Feed  │
                 │ - Automated 8-Step Expo Demo   │
                 └────────────────────────────────┘
```

---

## 3. Directory Structure

```
SentraX/
│
├── firmware/
│   ├── esp32/
│   │   ├── SentraX_ESP32.ino                         # Authoritative ESP32 firmware
│   │   ├── ESP32_FINAL_ALL_REQUESTED_CHANGES_FIXED.ino
│   │   └── README.md                                 # ESP32 pinout & hardware docs
│   │
│   └── esp8266/
│       ├── SentraX_ESP8266.ino                       # Authoritative ESP8266 firmware
│       ├── ESP8266_RFID_5_BEEPS_LCD_FIXED.ino
│       └── README.md                                 # ESP8266 pinout & buzzer docs
│
├── software/
│   ├── backend/
│   │   ├── main.py                                   # FastAPI entrypoint & WebSockets
│   │   ├── api/
│   │   │   ├── routes.py                             # REST API router
│   │   │   └── websocket.py                          # Live WebSocket broadcasting
│   │   ├── core/
│   │   │   ├── config.py                             # Configuration & thresholds
│   │   │   └── logging.py                            # Structured logger
│   │   ├── database/
│   │   │   ├── connection.py                         # SQLite connection & auto-init
│   │   │   └── models.py                             # Query repository & helpers
│   │   ├── ble/
│   │   │   ├── adapter.py                            # Standard GATT profile & UUIDs
│   │   │   ├── bleak_transport.py                    # Windows Bluetooth client
│   │   │   └── mock_transport.py                     # High-fidelity mock BLE client
│   │   ├── serial_comm/
│   │   │   └── protocol_adapter.py                   # Microcontroller UART translator
│   │   ├── engines/
│   │   │   ├── risk_engine.py                        # Road Risk Score (0-100)
│   │   │   ├── road_health_engine.py                 # Road Health Score (0-100)
│   │   │   ├── hazard_engine.py                      # Proximity warning engine
│   │   │   ├── recommendation_engine.py              # Adaptive advisory speed & transit
│   │   │   └── data_fusion.py                        # Multi-modal sensor + CV fusion
│   │   ├── cv/
│   │   │   ├── detector.py                           # Road object detector
│   │   │   ├── tracker.py                            # Multi-object centroid tracking
│   │   │   └── cv_pipeline.py                        # Frame processor & MJPEG streamer
│   │   ├── maps/
│   │   │   └── route_service.py                      # Google Maps & mock route provider
│   │   ├── schemas/                                  # Canonical Pydantic contracts
│   │   │   ├── telemetry.py
│   │   │   ├── events.py
│   │   │   ├── hazards.py
│   │   │   ├── routes.py
│   │   │   └── recommendations.py
│   │   └── simulation/
│   │       └── simulator.py                          # 8-step expo demo & scenario engine
│   │
│   └── frontend/
│       ├── static/
│       │   ├── css/styles.css                        # Modern dark/light stylesheet
│       │   └── js/app.js                             # WebSockets, Leaflet & Chart.js
│       └── templates/
│           └── index.html                            # 12-page presentation dashboard
│
├── data/
│   └── sentrax.db                                    # Persistent SQLite database
├── tests/
│   ├── test_acceptance_criteria.py                  # All 15 project acceptance tests
│   ├── test_api.py                                  # REST endpoints verification
│   ├── test_engines.py                              # Physics, speed rules & risk tests
│   ├── test_protocol.py                             # Serial & BLE encoding tests
│   └── test_simulation.py                           # Scenario trigger tests
├── docs/                                             # Full documentation suite
│   ├── ARCHITECTURE.md
│   ├── FIRMWARE.md
│   ├── BLE_PROTOCOL.md
│   ├── TELEMETRY_SCHEMA.md
│   ├── API.md
│   ├── CV.md
│   ├── ROAD_HEALTH.md
│   ├── MAPS.md
│   ├── DEMO.md
│   └── IMPLEMENTED_VS_FUTURE.md
├── config/
│   └── sentrax_config.json
├── scripts/
│   ├── run_backend.py                               # Start FastAPI & Web Dashboard
│   ├── run_demo.py                                  # CLI walkthrough of demo scenarios
│   └── patch_firmware.py
├── .env.example
├── .env
├── requirements.txt
└── README.md
```

---

## 4. Hardware Firmware & Applied Modifications

### ESP32 Primary Controller
- **Congestion Time**: `CONGESTION_TIME = 5000;` (5 seconds). When 2 or more IR sensors remain occupied for 5s, Congestion alert triggers and advisory speed drops to 60 km/h.
- **Toy-Car Low-Speed Overspeed**: `DEMO_OVERSPEED_LIMIT = 4.0;` km/h. Speeds measured above 4.0 km/h trigger overspeed alerts during demonstration, while maintaining highway recommendation `NORMAL_SPEED = 80.0;`.
- **Sensor Distance**: Configurable constant `SENSOR_DISTANCE = 0.30;` meters.
- **LED Driving**: Sole controller for the 60 WS2812B LEDs on GPIO 2. Fixed `stalledLEDs()` color references.

### ESP8266 Auxiliary Controller
- **RFID Emergency Ambulance**: Triggers dedicated buzzer sequence with **exactly 5 complete dual-beep cycles**, then automatically stops buzzer and restores normal display.
- **Night Mode**: LDR on A0 controls the GC9A01 round TFT display (active only in night mode; blank in daytime).
- **LED Protection**: GPIO 1 kept in high-impedance `INPUT` mode (never drives LEDs).

---

## 5. Getting Started & Running the Platform

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Start Backend Server & Dashboard
```bash
python scripts/run_backend.py
```
Open your browser at:
- **Command Center Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Interactive REST API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Step 3: Run the CLI Demo Sequence
In a separate terminal:
```bash
python scripts/run_demo.py
```

### Step 4: Run the Automated Test Suite
```bash
pytest tests/
```
All **30 tests** covering acceptance criteria, physics, speed rules, risk calculation, serial parsing, and REST endpoints pass with 100% success.

---

## 6. Live Dashboard Overview (12 Operational Views)

1. **Command Center**: Large key metrics (Current Speed, Recommended Speed, Road Risk, Traffic, Condition), live speed trend chart, and real-time incident timeline.
2. **Live Telemetry**: Real-time readings for all 15 physical sensors (IR1-4 occupancy grid, dual ultrasonic beams, acoustic crash sensor, DHT11 temp/humidity, moisture level, RFID tag status, night mode).
3. **Event History**: Searchable, filterable persistent incident log.
4. **Road Risk Analysis**: Live 0-100 risk score breakdown with factor explanations.
5. **Analytics & Trends**: Aggregate metrics, average speed, incident distribution charts.
6. **Computer Vision**: Live 640x360 camera feed with bounding box annotations, vehicle tracking, per-vehicle snapshots with speed, and visual emergency vehicle recognition.
7. **Road Health Monitor**: 0-100 road health gauge with prototype bands (GOOD, MODERATE, POOR, CRITICAL).
8. **Map / Navigation**: Interactive map with color-coded corridor road health segments (Green, Yellow, Orange, Red) and active hazard markers.
9. **Hazard Zones**: Active perimeter geofences with distance countdowns.
10. **Device Nodes**: Status cards for ESP32 and ESP8266 (RSSI, uptime, connection state).
11. **Demo Simulation**: One-click 8-step automated expo demo and instant scenario injection pills.
12. **Settings**: Configuration thresholds and calibration parameters.

---

## 7. Product USP & Academic Integrity

> *"SentraX is not just a traffic monitoring system. It is an intelligent road infrastructure platform that allows the road to sense changing conditions, understand risk, communicate warnings, and continuously provide safety intelligence."*

- **Embedded Firmware**: Rule-based embedded C++ logic executing on physical microcontrollers.
- **Software Analytics**: Software-layer AI/analytics and multi-modal data fusion engine.
- **Speed Guidance**: Always termed **SentraX Recommended Speed** or **Advisory Speed**, never dynamic legal limits.
- **Camera Speeds**: Clearly marked **ESTIMATED (Uncalibrated)**.
- **Simulation**: All simulated readings and demo runs are transparently labeled **SIMULATED / SYNTHETIC**.
