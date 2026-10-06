# SentraX Bluetooth Low Energy (BLE) & Serial Protocol Specification

## 1. Architectural Strategy
To ensure resilience in noisy outdoor environments without Wi-Fi dependency, SentraX supports a standardized BLE GATT profile alongside its physical 9600-baud UART link.

When physical BLE hardware is paired, the Python `bleak` transport or browser Web Bluetooth API connects directly. When running offline or in demo mode, the software switches automatically to the Mock BLE Transport without interface changes.

## 2. Standard GATT Profile
**Service UUID**: `73656e74-7261-7800-0001-000000000000`

### Characteristics
| Name | UUID | Permissions | Description |
|---|---|---|---|
| **Device Status** | `73656e74-7261-7800-0002-000000000001` | READ, NOTIFY | Node health, uptime, RSSI, firmware version |
| **Telemetry** | `73656e74-7261-7800-0002-000000000002` | NOTIFY | Live sensor values (JSON/Binary packet) |
| **Events** | `73656e74-7261-7800-0002-000000000003` | NOTIFY, INDICATE | Alert incidents (Overspeed, Congestion, Wet) |
| **Commands** | `73656e74-7261-7800-0002-000000000004` | WRITE | Commands (`START_SPEED`, `RESET_ALERT`) |
| **Heartbeat** | `73656e74-7261-7800-0002-000000000005` | READ, NOTIFY | Liveness pulse emitted every 2-3s |

## 3. Serial Protocol (UART 9600 Baud 8N1)
The physical microcontrollers exchange newline-terminated ASCII tokens across the inter-board serial bus:

| Raw Message | Source | Description | Converted Software Model |
|---|---|---|---|
| `SPEED:<value>` | ESP32 | Measured vehicle speed in km/h | `{"type": "speed", "value": <float>, "source": "esp32"}` |
| `LIMIT:<value>` | ESP32 | Active speed recommendation | `{"type": "recommended_speed", "value": <int>}` |
| `SPEED_MODE` | ESP32 | Speed measuring countdown initiated | `{"type": "mode", "mode": "CALCULATING_SPEED"}` |
| `CONGESTION` | ESP32 | 2+ IR blocked for 5s | `{"type": "event", "event": "CONGESTION"}` |
| `STALLED` | ESP32 | Any IR blocked for 15s | `{"type": "event", "event": "STALLED"}` |
| `WRONG` | ESP32 | IR4 &rarr; IR3 reverse trigger | `{"type": "event", "event": "WRONG_WAY"}` |
| `COLLISION` | ESP32 | Acoustic impact sensor trigger | `{"type": "event", "event": "COLLISION"}` |
| `WET` | ESP32 | Moisture sensor &lt; 2000 | `{"type": "event", "event": "WET_ROAD"}` |
| `NORMAL` | ESP32 | Reset alert; clear roadway | `{"type": "event", "event": "NORMAL"}` |
| `RFID` | ESP8266 | Emergency ambulance detected | `{"type": "event", "event": "EMERGENCY", "source": "esp8266"}` |
| `NIGHT` | ESP8266 | LDR dark condition (A0 &gt; 500) | `{"type": "environment", "night_mode": true}` |
| `DAY` | ESP8266 | LDR bright condition | `{"type": "environment", "night_mode": false}` |
| `ESP8266_HEARTBEAT` | ESP8266 | Auxiliary pulse (every 3s) | `{"type": "heartbeat", "device": "SENTRAX-ESP8266"}` |
| `STATE:<state>` | ESP32 | Generalized state dispatch | Normalized to `<state>` |
