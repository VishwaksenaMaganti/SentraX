# SentraX Ecosystem Architecture

## 1. System Vision
SentraX transforms conventional passive road infrastructure into an **intelligent, adaptive, and communicative road safety platform**. Traditional roadways rely on static road signs, passive cat's eyes, dumb rumble strips, and delayed police responses. SentraX introduces an end-to-end loop:

```
SENSE  ──►  UNDERSTAND  ──►  DECIDE  ──►  RESPOND  ──►  MONITOR
```

## 2. High-Level Multi-Tier Architecture

```
                 ┌────────────────────────────────┐
                 │       ESP32 Primary Node       │
                 │  IR1-4, Sound, DHT11, Moisture │
                 │  US1/US2 Speed, 60 WS2812B LED │
                 │  Waveshare 1.54" E-Ink Screen  │
                 └───────────────┬────────────────┘
                                 │ UART (9600 8N1)
                                 │ & BLE GATT
                 ┌───────────────▼────────────────┐
                 │     ESP8266 Auxiliary Node     │
                 │  RC522 RFID, LDR Night Sensor  │
                 │  GC9A01 Round TFT, Buzzer (5x) │
                 └───────────────┬────────────────┘
                                 │
                   BLE / Serial Gateway Bridge
                                 │
                 ┌───────────────▼────────────────┐
                 │    SentraX Software Platform   │
                 │                                │
                 │  ┌──────────────────────────┐  │
                 │  │ Canonical Telemetry &    │  │
                 │  │ Event Normalization Hub  │  │
                 │  └────────────┬─────────────┘  │
                 │               │                │
                 │  ┌────────────▼─────────────┐  │
                 │  │ Multi-Modal Data Fusion  │  │
                 │  │ (Sensors + Phone CV)     │  │
                 │  └────────────┬─────────────┘  │
                 │               │                │
                 │  ┌────────────▼─────────────┐  │
                 │  │ Core Intelligence        │  │
                 │  │ - Road Risk (0-100)      │  │
                 │  │ - Road Health (0-100)    │  │
                 │  │ - Speed Recommendation   │  │
                 │  │ - Multimodal Transit Rec │  │
                 │  │ - Hazard Perimeters      │  │
                 │  └────────────┬─────────────┘  │
                 │               │                │
                 │  ┌────────────▼─────────────┐  │
                 │  │ SQLite Database & Log    │  │
                 │  └────────────┬─────────────┘  │
                 └───────────────┼────────────────┘
                                 │ REST & WebSocket
                 ┌───────────────▼────────────────┐
                 │ Presentation Command Center UI │
                 │ - 12 Interactive Panels        │
                 │ - Color-Coded Route Health     │
                 │ - Live Vision MJPEG Stream     │
                 │ - Automated 9-Step Expo Demo   │
                 └────────────────────────────────┘
```

## 3. Physical & Software Boundary Separation
- **Embedded Hardware**: Microcontroller algorithms execute real-time safety critical tasks directly in deterministic C++ code (e.g., stopping countdowns, pulsing WS2812B LEDs, drawing E-Ink alerts, sounding piezo buzzers).
- **Software Platform**: Executes higher-level computation, state aggregation, computer vision trajectory tracking, geospatial hazard calculation, route segmentation, and persistent analytics.
