# SentraX ESP8266 Auxiliary Firmware

## Overview
The ESP8266 serves as the **auxiliary visual alert, audio warning, and emergency vehicle detection module** in SentraX. It monitors ambient light (LDR) for automatic Night Mode, drives the GC9A01 240x240 round color TFT display, sounds the piezoelectric buzzer with specialized emergency cadence patterns, reads RFID tags for priority emergency vehicle dispatch (e.g. Ambulance/Fire), and communicates bidirectionally with the primary ESP32 controller over SoftwareSerial.

## Hardware Pinout
| Component | Pin (NodeMCU) | Mode | Description |
|---|---|---|---|
| GC9A01 TFT CS | D4 (GPIO 2) | Output | Round TFT SPI Chip Select |
| GC9A01 TFT DC | D3 (GPIO 0) | Output | Round TFT Data/Command |
| GC9A01 TFT RST | 3.3V | Hardwired | Connected to 3.3V rail |
| RC522 RFID SS | D8 (GPIO 15) | Output | SPI Slave Select |
| RC522 RFID RST | GPIO 3 (RX) | Output | Reset pin for MFRC522 |
| Buzzer Pin | D2 (GPIO 4) | Output | Piezoelectric buzzer |
| LDR Pin | A0 (ADC0) | Analog Input | Ambient light intensity |
| Link Serial RX | D0 (GPIO 16) | SoftwareSerial RX | Connected to ESP32 TX (GPIO 5) |
| Link Serial TX | D1 (GPIO 5) | SoftwareSerial TX | Connected to ESP32 RX (GPIO 4) |
| LED Data Pin | GPIO 1 (TX) | **INPUT (High-Z)** | **CRITICAL: NEVER DRIVE LED STRIP FROM ESP8266** |

## Libraries
- `SPI`
- `Adafruit_GFX`
- `Adafruit_GC9A01A`
- `MFRC522`
- `SoftwareSerial`

## Operating Characteristics
1. **RFID Emergency Sequence**:
   - Detects RFID card/tag.
   - Sends `"RFID"` to ESP32 (which starts the dual sequential red LED warning).
   - Starts dedicated buzzer mode: **exactly 5 complete dual-beep cycles** (2200 Hz for 120ms, pause 100ms, 2200 Hz for 120ms, pause 700ms).
   - After the 5th dual-beep cycle: buzzer is silenced, emergency state is cleared, and display is returned to normal / blank.
2. **Night Mode Control**:
   - Controlled by LDR on A0 (`DARK_WHEN_HIGH true`, `NIGHT_THRESHOLD = 500`).
   - When dark, sends `"NIGHT"` to ESP32 and enables round TFT visual notifications.
   - When daytime, sends `"DAY"` to ESP32 and blanks the round TFT display to save power.
3. **LED Protection**:
   - Pin GPIO 1 is explicitly maintained as high-impedance `INPUT`. ESP32 is the sole controller of the WS2812B LEDs.
