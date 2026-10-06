# SentraX ESP32 Firmware

## Overview
The ESP32 is the **primary road-safety and sensor controller** in the SentraX ecosystem. It interfaces with all primary physical road sensors, drives the WS2812B addressable LED warning strip, updates the Waveshare 1.54" E-Ink display, calculates vehicle speed using dual ultrasonic sensors, and communicates with the ESP8266 auxiliary unit over serial UART.

## Hardware Pinout
| Component | GPIO Pin | Mode | Description |
|---|---|---|---|
| IR Sensor 1 | GPIO 25 | INPUT (Active LOW) | First traffic detector |
| IR Sensor 2 | GPIO 26 | INPUT (Active LOW) | Second traffic detector |
| IR Sensor 3 | GPIO 27 | INPUT (Active LOW) | Third traffic detector (Wrong-way exit) |
| IR Sensor 4 | GPIO 33 | INPUT (Active LOW) | Fourth traffic detector (Wrong-way entry) |
| Sound Sensor | GPIO 32 | INPUT (Active HIGH) | Impact / collision acoustic threshold |
| DHT11 | GPIO 13 | Digital Data | Ambient temperature & relative humidity |
| Moisture Sensor | GPIO 35 | ANALOG INPUT | Road surface wetness detection (< 2000 = WET) |
| Ultrasonic 1 Trig | GPIO 3 | OUTPUT | Speed detection sensor 1 trigger |
| Ultrasonic 1 Echo | GPIO 34 | INPUT | Speed detection sensor 1 echo |
| Ultrasonic 2 Trig | GPIO 14 | OUTPUT | Speed detection sensor 2 trigger |
| Ultrasonic 2 Echo | GPIO 36 | INPUT | Speed detection sensor 2 echo |
| WS2812B LED Data | GPIO 2 | OUTPUT | 60-LED addressable road marker strip |
| Speed Measure Button | GPIO 15 | INPUT_PULLUP | Trigger vehicle speed measurement demo |
| E-Ink CS | GPIO 16 | SPI Chip Select | Waveshare 1.54" E-Ink |
| E-Ink DC | GPIO 17 | SPI Data/Command | Waveshare 1.54" E-Ink |
| E-Ink RST | GPIO 21 | Reset | Waveshare 1.54" E-Ink |
| E-Ink BUSY | GPIO 22 | Input | Waveshare 1.54" E-Ink busy status |
| Link Serial RX | GPIO 4 | HardwareSerial(1) | UART RX from ESP8266 |
| Link Serial TX | GPIO 5 | HardwareSerial(1) | UART TX to ESP8266 |

## Required Libraries
- `SPI` (ESP32 core)
- `GxEPD2_BW` (`GxEPD2_154_D67`)
- `Adafruit_GFX`
- `Adafruit_NeoPixel`
- `DHT` (Adafruit DHT sensor library)

## Key Operating Parameters & Mandatory Changes Applied
1. **Congestion Time**: `CONGESTION_TIME = 5000;` (5 seconds). When 2 or more IR sensors remain continuously blocked for 5s, Congestion alert triggers.
2. **Demo Low-Speed Overspeed Limit**:
   - `DEMO_OVERSPEED_LIMIT = 4.0;` km/h.
   - Vehicle speed measured above 4.0 km/h triggers `RASH_DRIVING` / `OVERSPEED!`.
   - Normal road speed recommendation remains `NORMAL_SPEED = 80.0;` km/h.
3. **Sensor Spacing**: `SENSOR_DISTANCE = 0.30;` meters (configurable).
4. **Stalled Vehicle Window**: 15 seconds continuous block on any IR sensor.
5. **Wrong-Way Window**: 15 seconds (IR4 triggered, then IR3 triggered within 15 seconds).
6. **Speed Recommendations**:
   - Normal: 80 km/h
   - Congestion: 60 km/h
   - Wet Road: 40 km/h
   - High Temperature (>= 30°C): 35 km/h

## BLE Integration Note
While the hardware prototype runs serial UART communication to the ESP8266 and the SentraX software bridge, a standard BLE GATT service is modeled in software and can be enabled natively using the ESP32 BLE Arduino library without disrupting existing sensor or serial logic.
