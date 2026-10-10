# SentraX Phone-Camera Computer Vision Subsystem

## 1. Overview
The Computer Vision subsystem serves as an independent perception channel that complements embedded microcontrollers. A roadside camera or smartphone camera mounted overlooking the road track tracks physical vehicular traffic, measures speed, recognises emergency vehicles by their lights and look, and flags safety anomalies.

## 2. Capabilities
- **Object Detection**: Identifies Cars, Trucks, Buses, Motorcycles, Bicycles, Pedestrians, and Animals.
- **Centroid & Trajectory Tracking**: Assigns persistent `track_id` values, tracking vehicle movement across frames.
- **Direction Estimation**: Flags wrong-way traffic moving opposite to designated corridor flow.
- **Speed Estimation**: Approximates toy vehicle speed from pixel displacement.
  * *Important Note*: All camera-derived speeds are explicitly labeled **ESTIMATED (Uncalibrated)** to maintain rigorous scientific integrity.
- **Emergency Vehicle Recognition**: Flashing red/blue beacons, red-and-blue light bars, and the open-vocabulary detector's ambulance / police car labels. No audio needed.
- **Vehicle Snapshots & Speed**: A snapshot is taken when a vehicle enters the frame; its speed is measured from the toy car's known size (7.5 cm) and shown in the mobile app's Camera AI panel.
- **Stationary Vehicle Flagging**: Identifies stalled vehicles that remain immobile for &gt; 3 seconds.

## 3. Sensor + Vision Data Fusion
Vision observations are merged with microcontroller readings via weighted confidence scoring:

| Hardware Reading | Camera CV Observation | Fused Incident Determination | Confidence |
|---|---|---|---|
| IR sensors occupied | Camera identifies vehicle | High-Confidence Vehicle Present | 0.95 |
| Sound sensor spike | Camera detects stopped car | High-Confidence Crash / Collision | 0.98 |
| Moisture &lt; 2000 | Camera verifies wet asphalt glare | High-Confidence Wet Roadway | 0.94 |
| IR4 &rarr; IR3 sequence | Camera identifies opposite motion | High-Confidence Wrong-Way Vehicle | 0.95 |
