# SentraX Implemented vs. Experimental vs. Future Scope Matrix

To preserve scientific rigor and intellectual honesty, this document distinguishes between what is physically built and validated, what is experimental, what the software platform provides, and what is reserved for future commercial deployment.

| Feature / Subsystem | Category | Current Implementation State | Notes & Verification |
|---|---|---|---|
| **ESP32 Core Microcontroller** | Implemented Hardware | Fully working on physical hardware | Pins 25, 26, 27, 33, 32, 13, 35, 3, 34, 14, 36, 2, 15, 16, 17, 21, 22, 4, 5 |
| **ESP8266 Auxiliary Node** | Implemented Hardware | Fully working on physical hardware | D4, D3, D8, GPIO3, D2, A0, D0, D1; GPIO1 kept high-Z |
| **IR Traffic Sensors (1 to 4)** | Implemented Hardware | Physical sensors wired & active | Congestion (5s), Stalled (15s), Wrong-way (IR4 &rarr; IR3 15s) |
| **Dual Ultrasonic Sensors** | Implemented Hardware | Physical sensors wired & active | Spacing: 0.30 m, Speed = Distance / Time * 3.6 |
| **Sound / Acoustic Sensor** | Implemented Hardware | Physical sensor active HIGH | Impact & crash detection |
| **Moisture Sensor** | Implemented Hardware | Analog reading on GPIO 35 | Threshold 2000 (below = WET) |
| **DHT11 Environmental Sensor** | Implemented Hardware | Digital reading on GPIO 13 | High Temp (&ge; 30°C), Humidity (&ge; 80%) |
| **RC522 RFID Tag Reader** | Implemented Hardware | Physical SPI on ESP8266 | Detects emergency ambulance tags |
| **WS2812B Addressable LED Strip** | Implemented Hardware | 60 LEDs driven solely by ESP32 | Normal amber, red collision, flash white wet, sequential emergency |
| **Waveshare 1.54" E-Ink** | Implemented Hardware | SPI screen driven by ESP32 | Crisp daylight event and speed rendering |
| **GC9A01 240x240 Round TFT** | Implemented Hardware | SPI screen on ESP8266 | Displays alert graphics during Night Mode only |
| **Piezo Buzzer (RFID Cadence)** | Implemented Hardware | Connected to ESP8266 D2 | Exactly 5 complete dual-beep cycles |
| **UART Serial Link** | Implemented Hardware | 9600 baud 8N1 serial link | Bi-directional inter-board message passing |
| **Piezoelectric Rumble Strip** | Experimental Hardware | Bench concept (10x 27mm discs) | **Experimental**: Software does not depend on raw output |
| **BLE Communication Architecture** | Software Platform | Standard GATT profile + Bleak/Mock | Auto-discovers physical BLE or runs mock transport |
| **Live Command Center Dashboard** | Software Platform | Complete responsive Web UI | 12 views, dark/light theme, live WebSockets |
| **SQLite Event & Data Logging** | Software Platform | Persistent thread-safe DB | 11 relational tables storing telemetry and events |
| **Road Risk Scoring (0-100)** | Software Platform | Real-time weighted algorithm | Clamped 0-100 score with explicit reasons list |
| **Road Health Scoring (0-100)** | Software Platform | Corridor evaluation model | Bands: GOOD, MODERATE, POOR, CRITICAL |
| **Phone-Camera Computer Vision** | Software Platform | OpenCV tracking pipeline | Vehicle detection, trajectory, pothole detection, estimated speed |
| **Sensor + Vision Data Fusion** | Software Platform | Weighted confidence engine | Multi-modal incident validation |
| **Google Maps Navigation** | Software Platform | Routes API + Mock Provider | Color-coded segmented route health |
| **Adaptive Speed Recommendations**| Software Platform | Priority safety engine | Advisory speed recommendations (NOT legal limits) |
| **One-Click Expo Demo Engine** | Software Platform | 9-step automated walkthrough | Offline simulation for exhibitions & demos |
| **Edge mmWave Radar Sensors** | Future Scope | Not in current prototype | Intended for all-weather velocity tracking |
| **Dedicated V2X (DSRC / C-V2X)** | Future Scope | Not in current prototype | Direct vehicle-to-infrastructure messaging |
| **On-Vehicle Safety HUD Unit** | Future Scope | Not in current prototype | In-car dash receiver for advisory alerts |
| **Cellular GSM/4G Telematics** | Future Scope | Not in current prototype | Regional highway cloud telemetry uplink |
| **Trained Deep Learning Weights** | Future Scope | Pluggable architecture ready | Heuristic / contour CV used; ML weights pluggable |
