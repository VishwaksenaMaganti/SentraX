# SentraX Demo & Presentation Guide

## 1. Zero-Hardware Exhibition Mode
SentraX is designed to be demonstrated anywhere without requiring active Wi-Fi, external cloud access, physical microcontroller hardware, or camera peripherals.

All synthetic telemetry and vision feeds are clearly tagged **SIMULATED / SYNTHETIC**.

## 2. One-Click 8-Step Automated Expo Demo
Clicking **START 8-STEP EXPO DEMO** executes the complete sequence:

1. **STEP 1: Normal Road (80 km/h)**
   - Road clear, all sensors normal, posted limit 80 km/h.
2. **STEP 2: Toy Car Detected**
   - Measured speed 4.5 km/h displayed.
3. **STEP 3: Overspeed Threshold Exceeded**
   - Speed 4.5 km/h &gt; demo limit 4.0 km/h triggers `OVERSPEED!` / `RASH DRIVING`.
4. **STEP 4: Two IR Sensors Blocked for 5s (Congestion)**
   - Congestion detected, advisory speed drops to 60 km/h.
5. **STEP 5: Wet Road (Moisture &lt; 2000)**
   - Road surface wet alert, advisory speed drops to 40 km/h.
6. **STEP 6: Collision Impact**
   - Acoustic collision triggered, hazard zone generated.
7. **STEP 7: RFID Emergency Vehicle**
   - Priority ambulance tag detected, 5 dual-beep cadence active.
8. **STEP 8: Road Risk Score Increases**
   - Composite risk score increases to 88/100, displaying comprehensive breakdown.

## 3. Instant Manual Scenario Triggers
From the **Demo Simulation** tab or REST API, any individual scenario can be triggered instantly:
- `NORMAL`
- `OVERSPEED`
- `CONGESTION`
- `WRONG_WAY`
- `STALLED_VEHICLE`
- `COLLISION`
- `WET_ROAD`
- `EMERGENCY`
- `HIGH_TEMP`
- `HIGH_HUMIDITY`
- `ANIMAL_HAZARD`
