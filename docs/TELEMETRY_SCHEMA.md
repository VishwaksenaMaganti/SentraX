# SentraX Canonical Telemetry & Event Schema

## 1. Canonical Telemetry Data Model
Every incoming reading from physical hardware, BLE packets, or the multi-modal fusion engine is normalized into this structure:

```json
{
  "device_id": "SENTRAX-CORE",
  "timestamp": 1791224559.5,
  "connection_state": "CONNECTED",
  "measured_speed_kmh": 4.5,
  "recommended_speed_kmh": 60.0,
  "posted_speed_kmh": 80.0,
  "traffic_count": 2,
  "traffic_level": "CONGESTED",
  "road_condition": "DRY",
  "collision": false,
  "wrong_way": false,
  "stalled_vehicle": false,
  "emergency_vehicle": false,
  "temperature_c": 27.2,
  "humidity_pct": 54.0,
  "moisture_raw": 3150,
  "ir_sensors": [true, true, false, false],
  "ultrasonic_state": {
    "us1_active": false,
    "us2_active": false,
    "measuring": false
  },
  "sound_active": false,
  "rfid_active": false,
  "night_mode": false,
  "cv_vehicle_count": 2,
  "hazard_count": 0,
  "risk_score": 30,
  "risk_reasons": [
    "High traffic congestion detected on IR sensors (+10)",
    "Vehicle overspeed detected: 4.5 km/h (+20)"
  ],
  "source": "FUSION",
  "is_simulated": false
}
```

## 2. Canonical Event Model
```json
{
  "event_id": "evt_a9b1c2d3",
  "timestamp": 1791224560.1,
  "source": "ESP32",
  "type": "CONGESTION",
  "severity": "WARNING",
  "confidence": 0.95,
  "title": "Corridor Congestion Alert",
  "description": "Two or more IR sensors occupied continuously >= 5 seconds",
  "payload": {
    "occupied_sensors": 2,
    "duration_seconds": 5.0
  },
  "is_simulated": false
}
```
