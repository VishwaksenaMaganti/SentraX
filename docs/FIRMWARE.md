# SentraX Firmware Specification & Pin Mapping

## 1. Authoritative Firmware Files
- ESP32: `firmware/esp32/SentraX_ESP32.ino` (and `firmware/esp32/ESP32_FINAL_ALL_REQUESTED_CHANGES_FIXED.ino`)
- ESP8266: `firmware/esp8266/SentraX_ESP8266.ino` (and `firmware/esp8266/ESP8266_RFID_5_BEEPS_LCD_FIXED.ino`)

## 2. ESP32 Pin Assignment
```
IR Sensors:
  IR1: GPIO 25 (INPUT, Active LOW)
  IR2: GPIO 26 (INPUT, Active LOW)
  IR3: GPIO 27 (INPUT, Active LOW)
  IR4: GPIO 33 (INPUT, Active LOW)

Environmental & Collision:
  Sound Sensor:     GPIO 32 (INPUT, Active HIGH)
  DHT11 Data:       GPIO 13 (DIGITAL)
  Moisture Sensor:  GPIO 35 (ANALOG ADC, Threshold = 2000)

Ultrasonic Speed Detection:
  US1 TRIG: GPIO 3
  US1 ECHO: GPIO 34
  US2 TRIG: GPIO 14
  US2 ECHO: GPIO 36
  Spacing:  SENSOR_DISTANCE = 0.30 m

Speed Demo Button:
  Button:   GPIO 15 (INPUT_PULLUP)

Actuators & Displays:
  WS2812B LEDs:     GPIO 2 (60 LEDs, Sole Driver)
  E-Ink CS:         GPIO 16
  E-Ink DC:         GPIO 17
  E-Ink RST:        GPIO 21
  E-Ink BUSY:       GPIO 22

UART Inter-Board Link:
  Link RX:  GPIO 4 (HardwareSerial(1))
  Link TX:  GPIO 5 (HardwareSerial(1))
  Baud:     9600, SERIAL_8N1
```

## 3. Mandatory Changes Implemented
1. **Congestion Detection Time**:
   - `CONGESTION_TIME` updated from 15,000 ms to **5,000 ms (5 seconds)**.
   - When 2 or more IR sensors remain occupied continuously for 5 seconds, congestion triggers, setting recommended advisory speed to 60 km/h.
2. **Toy-Car Low-Speed Overspeed**:
   - Configured `const float DEMO_OVERSPEED_LIMIT = 4.0;`
   - Comparison in `checkVehicleSpeed()`:
     `if (speed > DEMO_OVERSPEED_LIMIT) { triggerAlert(RASH_DRIVING); }`
   - Preserves `NORMAL_SPEED = 80.0` as highway road recommendation.
3. **Bug Verification**:
   - Verified `stalledLEDs()` does not use undefined variables; uses clean `yellow` and `red` color assignments.

## 4. ESP8266 Pin Assignment & Functions
```
GC9A01 Round TFT Display:
  CS:  D4 (GPIO 2)
  DC:  D3 (GPIO 0)
  RST: Connected to 3.3V

RFID MFRC522:
  SS:  D8 (GPIO 15)
  RST: GPIO 3 (RX)

Buzzer & Sensors:
  Buzzer:   D2 (GPIO 4)
  LDR:      A0 (Analog, NIGHT_THRESHOLD = 500, DARK_WHEN_HIGH = true)
  UART RX:  D0 (GPIO 16, SoftwareSerial)
  UART TX:  D1 (GPIO 5, SoftwareSerial)
  LED Data: Pin 1 (GPIO 1 / TX) kept in high-impedance INPUT mode
```

## 5. RFID Cadence
- Exactly **5 complete dual-beep cycles** (2200 Hz for 120ms, pause 100ms, 2200 Hz for 120ms, pause 700ms).
- At cycle 5, the buzzer stops automatically and the TFT display returns to normal/blank.
