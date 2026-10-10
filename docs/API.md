# SentraX REST API & WebSocket Reference

The SentraX backend is built on **FastAPI** and provides high-performance, asynchronous REST and WebSocket communication.

## 1. Base URL & Interactive Docs
- Base API: `http://localhost:8000/api`
- Interactive Swagger UI: `http://localhost:8000/docs`
- Interactive ReDoc: `http://localhost:8000/redoc`

## 2. Endpoints Overview

### System & Devices
- `GET /api/health`: System health status and active operating mode.
- `GET /api/devices`: List all registered nodes (`SENTRAX-ESP32`, `SENTRAX-ESP8266`).
- `GET /api/devices/{id}`: Detailed status for a specific node (RSSI, uptime, port).

### Live Telemetry & Events
- `GET /api/telemetry/latest`: Returns the most recent canonical telemetry record.
- `GET /api/telemetry/history?limit=50`: Returns historical telemetry samples.
- `GET /api/events?limit=50&type=...`: List persistent incident and event logs.
- `POST /api/events`: Inject or log an external event.

### Road Health & Hazards
- `GET /api/road-health`: Overall corridor road health score (0-100) and deterioration factors.
- `GET /api/hazards`: List active geographic hazard perimeters.
- `POST /api/hazards`: Register a new hazard zone.

### Navigation & Routing
- `GET /api/route-health`: Default corridor route segmented with color-coded safety bands.
- `POST /api/route-health`: Calculate road health and hazards along a custom origin & destination.

### Analytics & Recommendations
- `GET /api/analytics`: Aggregate statistics (counts by event type, speed averages, incident trends).
- `GET /api/recommendations`: Active dynamic advisory speed and multimodal transit suggestions.

### Simulation Controls
- `POST /api/simulation/start`: Launch the automated 8-step expo walkthrough.
- `POST /api/simulation/stop`: Stop demo sequence and reset baseline state.
- `POST /api/simulation/scenario`: Trigger an individual scenario (`OVERSPEED`, `CONGESTION`, `WET_ROAD`, `COLLISION`, `EMERGENCY`).
- `GET /api/simulation/status`: Current simulation mode and progress.

### Live Computer Vision Stream
- `GET /api/cv/feed`: Real-time MJPEG video stream with bounding boxes and HUD overlay.
- `GET /api/cv/stats`: Summary metrics for vehicles and speeds currently in frame.
- `GET /api/cv/vehicles`: Vehicles seen by the live camera with snapshot URL, speed now/avg/top, colour, heading, alerts, and session totals.
- `GET /api/cv/vehicles/{label}/snapshot.jpg`: Snapshot taken when the vehicle entered the frame.
- `POST /api/cv/vehicles/clear`: Clear the vehicle log.

## 3. Real-Time WebSocket
- Endpoint: `ws://localhost:8000/ws/telemetry`
- Packets: Emits `telemetry_update` messages whenever sensor values change or simulation ticks.
