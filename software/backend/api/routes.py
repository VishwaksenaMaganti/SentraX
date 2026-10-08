"""
SentraX REST API Router
Implements all core endpoints for devices, telemetry, events, road health, hazards,
navigation routes, analytics, physical BLE/Serial connectivity, and simulation control.
"""

from fastapi import APIRouter, HTTPException, Query, Body, Response
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional
import time

from software.backend.schemas.telemetry import (
    CanonicalTelemetry, DeviceStatus, ConnectionState, RoadCondition, TrafficLevel, DeviceSource
)
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.schemas.hazards import HazardZone, PotholeRecord
from software.backend.schemas.routes import RouteHealthRequest, RouteHealthResponse
from software.backend.schemas.recommendations import SpeedRecommendation, VehicleTypeRecommendation
from software.backend.database.models import (
    get_latest_telemetry, get_telemetry_history, save_telemetry, get_events, save_event,
    get_devices, update_device_status, get_active_hazards, save_hazard_zone,
    get_potholes
)
from software.backend.engines.risk_engine import RoadRiskEngine
from software.backend.engines.recommendation_engine import RecommendationEngine
from software.backend.engines.road_health_engine import RoadHealthEngine
from software.backend.maps.route_service import RouteHealthService

router = APIRouter()
route_service = RouteHealthService()

# References injected by main.py
simulator_instance = None
cv_pipeline_instance = None
live_ble_instance = None
live_serial_instance = None
is_live_hardware_mode = False


def set_services(sim, cv, ble=None, serial=None):
    global simulator_instance, cv_pipeline_instance, live_ble_instance, live_serial_instance
    simulator_instance = sim
    cv_pipeline_instance = cv
    live_ble_instance = ble
    live_serial_instance = serial


@router.get("/health")
def health_check():
    return {
        "status": "ONLINE",
        "service": "SentraX Road Safety & Smart Infrastructure Platform",
        "timestamp": time.time(),
        "version": "2.4.0",
        "mode": "LIVE HARDWARE" if is_live_hardware_mode else "SIMULATION / DEMO",
        "ble_connected": live_ble_instance.is_connected if live_ble_instance else False,
        "serial_connected": live_serial_instance.is_connected if live_serial_instance else False
    }


# =====================================================================
# HARDWARE BLE & SERIAL CONNECTIONS
# =====================================================================
@router.get("/ble/scan")
async def scan_ble_devices():
    """Scans Windows Bluetooth radio for nearby physical BLE peripherals."""
    if live_ble_instance:
        return await live_ble_instance.scan_devices(timeout=3.5)
    return []


@router.post("/ble/connect")
async def connect_ble(address: Optional[str] = Body(None, embed=True)):
    """Connects to physical SENTRAX-ESP32 via Bleak."""
    global is_live_hardware_mode
    if live_ble_instance:
        target_addr = address.strip() if (address and isinstance(address, str) and address.strip()) else None
        success = await live_ble_instance.connect(target_addr)
        if success:
            is_live_hardware_mode = True
            return {
                "status": "connected",
                "address": live_ble_instance.connected_device_address,
                "device": live_ble_instance.connected_device_name or "SENTRAX-ESP32"
            }
        err = (live_ble_instance.last_error if getattr(live_ble_instance, "last_error", None)
               else "Failed to connect to BLE device. Ensure ESP32 is powered on and advertising.")
        raise HTTPException(status_code=400, detail=err)
    raise HTTPException(status_code=500, detail="BLE service unavailable")


@router.post("/ble/disconnect")
async def disconnect_ble():
    if live_ble_instance:
        await live_ble_instance.disconnect()
        return {"status": "disconnected"}
    return {"status": "ok"}


@router.get("/serial/ports")
def list_serial_ports():
    """Lists all physical USB and Bluetooth Virtual COM Ports detected on Windows."""
    if live_serial_instance:
        return live_serial_instance.list_available_ports()
    return []


@router.get("/hardware/status")
def get_hardware_status():
    """Returns the live connection and link status of both physical microcontrollers."""
    esp32_conn = False
    esp32_transport = "NONE"
    esp32_port_addr = None

    if live_ble_instance and live_ble_instance.is_connected:
        esp32_conn = True
        esp32_transport = "BLE"
        esp32_port_addr = live_ble_instance.connected_device_address or "SENTRAX-ESP32"
    elif live_serial_instance and live_serial_instance.is_esp32_connected:
        esp32_conn = True
        esp32_transport = "SERIAL"
        esp32_port_addr = live_serial_instance.esp32_port

    esp8266_conn = False
    esp8266_transport = "NONE"
    esp8266_port_addr = None
    last_hb = 0.0

    if live_ble_instance and live_ble_instance.is_connected and live_ble_instance.is_esp8266_connected:
        esp8266_conn = True
        esp8266_transport = "UART_BRIDGE_BLE"
        esp8266_port_addr = "ESP32_LINK (UART via BLE)"
        last_hb = live_ble_instance.last_esp8266_heartbeat
    elif live_serial_instance:
        if live_serial_instance.is_esp8266_direct_connected:
            esp8266_conn = True
            esp8266_transport = "DIRECT_SERIAL"
            esp8266_port_addr = live_serial_instance.esp8266_port
            last_hb = live_serial_instance.last_esp8266_heartbeat
        elif live_serial_instance.is_esp8266_connected:
            esp8266_conn = True
            esp8266_transport = "UART_BRIDGE"
            esp8266_port_addr = "ESP32_LINK (Pins 4/5)"
            last_hb = live_serial_instance.last_esp8266_heartbeat

    both_conn = esp32_conn

    return {
        "esp32": {
            "device_id": "SENTRAX-ESP32",
            "connected": esp32_conn,
            "transport": esp32_transport,
            "port_or_address": esp32_port_addr
        },
        "esp8266": {
            "device_id": "SENTRAX-ESP8266",
            "connected": esp8266_conn,
            "transport": esp8266_transport,
            "port_or_address": esp8266_port_addr,
            "last_heartbeat": last_hb
        },
        "both_modules_connected": esp32_conn,
        "hardware_standby": not esp32_conn
    }


# =====================================================================
# ESP32 CORE GATEWAY CONTROLS
# =====================================================================
@router.post("/esp32/connect/serial")
def connect_esp32_serial(
    port: str = Body(..., embed=True),
    baudrate: int = Body(115200, embed=True)
):
    """Connects to ESP32 Core Gateway via physical USB or Bluetooth Virtual COM port."""
    global is_live_hardware_mode
    if live_serial_instance:
        success = live_serial_instance.connect_esp32(port, baudrate)
        if success:
            is_live_hardware_mode = True
            return {"status": "connected", "port": port, "baudrate": baudrate, "device": "SENTRAX-ESP32"}
        raise HTTPException(
            status_code=400,
            detail=f"Access denied to {port}. Please close the Arduino IDE Serial Monitor so SentraX can bind to the port."
        )
    raise HTTPException(status_code=500, detail="Serial service unavailable")


@router.post("/esp32/disconnect")
async def disconnect_esp32():
    """Disconnects ESP32 serial or BLE connection."""
    global is_live_hardware_mode
    if live_serial_instance and live_serial_instance.is_esp32_connected:
        live_serial_instance.disconnect_esp32()
    if live_ble_instance and live_ble_instance.is_connected:
        await live_ble_instance.disconnect()
    if simulator_instance:
        simulator_instance._latest_live_telemetry = None
    return {"status": "disconnected", "device": "SENTRAX-ESP32"}


# =====================================================================
# ESP8266 AUXILIARY NODE CONTROLS
# =====================================================================
@router.post("/esp8266/connect/serial")
def connect_esp8266_serial(
    port: str = Body(..., embed=True),
    baudrate: int = Body(9600, embed=True)
):
    """Connects to ESP8266 Auxiliary Node directly via USB COM port."""
    if live_serial_instance:
        success = live_serial_instance.connect_esp8266(port, baudrate)
        if success:
            return {"status": "connected", "port": port, "baudrate": baudrate, "device": "SENTRAX-ESP8266"}
        raise HTTPException(
            status_code=400,
            detail=f"Access denied to {port}. Close any Arduino IDE Serial Monitor windows."
        )
    raise HTTPException(status_code=500, detail="Serial service unavailable")


@router.post("/esp8266/disconnect")
def disconnect_esp8266():
    """Disconnects ESP8266 direct serial link."""
    if live_serial_instance:
        live_serial_instance.disconnect_esp8266()
    if simulator_instance:
        simulator_instance._latest_live_telemetry = None
    return {"status": "disconnected", "device": "SENTRAX-ESP8266"}


@router.post("/telemetry/reset")
async def reset_telemetry_to_standby():
    """Forces immediate flush of telemetry cache and transitions system to Hardware Standby."""
    global is_live_hardware_mode
    if simulator_instance:
        simulator_instance._latest_live_telemetry = None
    if live_serial_instance:
        live_serial_instance.latest_live_telemetry = None
        live_serial_instance._update_and_broadcast_standby_state()
    if live_ble_instance:
        live_ble_instance.latest_live_telemetry = None
    return {"status": "standby_enforced", "hardware_standby": True}


@router.post("/esp8266/test/buzzer")
def test_esp8266_buzzer():
    """Triggers diagnostic 5-beep buzzer test on ESP8266."""
    if live_serial_instance:
        if live_serial_instance.is_esp8266_direct_connected and live_serial_instance.esp8266_conn:
            try:
                live_serial_instance.esp8266_conn.write(b"BUZZER_TEST\n")
                return {"status": "triggered", "mode": "direct_serial"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        elif live_serial_instance.is_esp32_connected and live_serial_instance.esp32_conn:
            try:
                live_serial_instance.esp32_conn.write(b"BUZZER_TEST\n")
                return {"status": "triggered", "mode": "via_esp32_bridge"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    return {"status": "queued", "message": "Will trigger on next communication cycle"}


# Legacy aliases for backward compatibility
@router.post("/serial/connect")
def connect_serial_legacy(
    port: str = Body(..., embed=True),
    baudrate: int = Body(115200, embed=True)
):
    return connect_esp32_serial(port, baudrate)


@router.post("/serial/disconnect")
def disconnect_serial_legacy():
    return disconnect_esp32()


# =====================================================================
# MANUAL OVERRIDE & HARDWARE COMMAND CONTROLS
# =====================================================================
@router.post("/speed/override")
async def override_speed(speed: float = Body(..., embed=True)):
    """Manually sets vehicle speed, commands physical hardware, and updates risk/advisory."""
    global is_live_hardware_mode
    is_live_hardware_mode = True
    cmd = f"SPEED:{speed:.1f}"

    if live_ble_instance and live_ble_instance.is_connected:
        await live_ble_instance.send_command(cmd)
    elif live_serial_instance and live_serial_instance.is_esp32_connected:
        live_serial_instance.send_command(cmd)

    t = simulator_instance.telemetry if simulator_instance else CanonicalTelemetry()
    t.measured_speed_kmh = float(speed)
    t.timestamp = time.time()
    t.esp32_connected = True
    t.both_modules_connected = True
    t.hardware_standby = False
    t.is_simulated = False

    score, reasons = RoadRiskEngine.calculate_risk(t)
    t.risk_score = score
    t.risk_reasons = reasons
    rec = RecommendationEngine.get_recommended_speed(t, t.posted_speed_kmh)
    t.recommended_speed_kmh = rec.recommended_speed_kmh

    save_telemetry(t)
    if simulator_instance:
        simulator_instance.telemetry = t
        simulator_instance._latest_live_telemetry = t
        if hasattr(simulator_instance, "broadcast_callback") and simulator_instance.broadcast_callback:
            await simulator_instance.broadcast_callback(t, None)

    return {"status": "speed_updated", "speed": speed, "recommended": t.recommended_speed_kmh}


@router.post("/alerts/trigger")
async def trigger_manual_alert(
    alert: str = Body(..., embed=True),
    sensor_index: Optional[int] = Body(None, embed=True)
):
    """Manually triggers any alert, commanding physical ESP32, e-ink, LEDs, and updating digital twin."""
    global is_live_hardware_mode
    is_live_hardware_mode = True
    alert_upper = alert.upper()
    cmd = f"ALERT:{alert_upper}"
    if alert_upper == "STALLED" and sensor_index is not None:
        cmd = f"ALERT:STALLED:{sensor_index}"

    if live_ble_instance and live_ble_instance.is_connected:
        await live_ble_instance.send_command(cmd)
    elif live_serial_instance and live_serial_instance.is_esp32_connected:
        live_serial_instance.send_command(cmd)

    t = simulator_instance.telemetry if simulator_instance else CanonicalTelemetry()
    t.timestamp = time.time()
    t.esp32_connected = True
    t.both_modules_connected = True
    t.hardware_standby = False
    t.is_simulated = False

    # Reset all alert flags
    t.collision = False
    t.wrong_way = False
    t.stalled_vehicle = False
    t.emergency_vehicle = False
    t.sound_active = False
    t.rfid_active = False

    evt_type = EventType.NORMAL
    evt_title = f"Manual Trigger: {alert_upper}"

    if alert_upper == "COLLISION":
        t.collision = True
        t.sound_active = True
        evt_type = EventType.COLLISION
    elif alert_upper == "WRONG_WAY":
        t.wrong_way = True
        evt_type = EventType.WRONG_WAY
    elif alert_upper == "STALLED":
        t.stalled_vehicle = True
        idx = sensor_index if sensor_index is not None else 1
        ir_arr = [False, False, False, False]
        if 0 <= idx < 4:
            ir_arr[idx] = True
        t.ir_sensors = ir_arr
        evt_type = EventType.STALLED
    elif alert_upper == "CONGESTION":
        t.traffic_level = TrafficLevel.CONGESTED
        t.ir_sensors = [True, True, False, False]
        evt_type = EventType.CONGESTION
    elif alert_upper in ("WET_ROAD", "WET"):
        t.road_condition = RoadCondition.WET
        t.moisture_raw = 1200
        evt_type = EventType.WET_ROAD
    elif alert_upper in ("HIGH_TEMP", "TEMP"):
        t.temperature_c = 38.5
        evt_type = EventType.HIGH_TEMP
    elif alert_upper in ("EMERGENCY", "RFID"):
        t.emergency_vehicle = True
        t.rfid_active = True
        evt_type = EventType.EMERGENCY
    elif alert_upper in ("NORMAL", "CLEAR"):
        t.road_condition = RoadCondition.DRY
        t.traffic_level = TrafficLevel.LIGHT
        t.moisture_raw = 3100
        t.temperature_c = 26.5
        t.ir_sensors = [False, False, False, False]
        evt_type = EventType.NORMAL

    score, reasons = RoadRiskEngine.calculate_risk(t)
    t.risk_score = score
    t.risk_reasons = reasons
    rec = RecommendationEngine.get_recommended_speed(t, t.posted_speed_kmh)
    t.recommended_speed_kmh = rec.recommended_speed_kmh

    canon_evt = CanonicalEvent(
        source="MANUAL_OVERRIDE",
        type=evt_type,
        severity=EventSeverity.CRITICAL if alert_upper in ("COLLISION", "WRONG_WAY", "EMERGENCY") else EventSeverity.WARNING,
        title=evt_title,
        description=f"Manual command '{alert_upper}' triggered via Command Center UI",
        is_simulated=False
    )
    save_event(canon_evt)
    save_telemetry(t)

    if simulator_instance:
        simulator_instance.telemetry = t
        simulator_instance._latest_live_telemetry = t
        if hasattr(simulator_instance, "broadcast_callback") and simulator_instance.broadcast_callback:
            await simulator_instance.broadcast_callback(t, canon_evt)

    return {"status": "alert_triggered", "alert": alert_upper, "risk_score": t.risk_score, "recommended": t.recommended_speed_kmh}


# =====================================================================
# DEVICES
# =====================================================================
@router.get("/devices")
def list_devices():
    return get_devices()


@router.get("/devices/{device_id}")
def get_device(device_id: str):
    devices = get_devices()
    for d in devices:
        if d["device_id"] == device_id:
            return d
    raise HTTPException(status_code=404, detail="Device not found")


# =====================================================================
# TELEMETRY
# =====================================================================
@router.get("/telemetry/latest")
def latest_telemetry():
    if simulator_instance and not simulator_instance.telemetry.both_modules_connected:
        return simulator_instance.telemetry.model_dump()
    t = get_latest_telemetry()
    if not t and simulator_instance:
        return simulator_instance.telemetry.model_dump()
    return t or {}


@router.get("/telemetry/history")
def history_telemetry(limit: int = Query(50, ge=1, le=500)):
    return get_telemetry_history(limit)


@router.post("/telemetry/ingest")
async def ingest_live_telemetry(payload: Dict[str, Any] = Body(...)):
    """
    Direct ingestion endpoint for live hardware telemetry received via Web Bluetooth API
    in the browser or external gateway scripts. Disables simulation and updates entire state.
    """
    global is_live_hardware_mode
    is_live_hardware_mode = True
    now = time.time()

    ir_list = payload.get("ir", [0, 0, 0, 0])
    if isinstance(ir_list, list):
        ir_bools = [bool(x) for x in ir_list]
    else:
        ir_bools = [False, False, False, False]

    alert_str = str(payload.get("alert", "NORMAL"))
    moist_val = int(payload.get("moist", payload.get("moisture_raw", 3100)))
    temp_val = float(payload.get("temp", payload.get("temperature_c", 26.5)))
    hum_val = float(payload.get("hum", payload.get("humidity_pct", 55.0)))
    speed_val = float(payload.get("speed", payload.get("spd", payload.get("measured_speed_kmh", 0.0))))
    sound_val = bool(payload.get("sound", payload.get("sound_active", 0)))
    rfid_val = bool(payload.get("rfid", payload.get("rfid_active", 0)))
    night_val = bool(payload.get("night", payload.get("night_mode", 0)))

    esp8266_flag = bool(payload.get("esp8266", 0))
    if esp8266_flag:
        update_device_status("SENTRAX-ESP8266", "CONNECTED", last_event="UART_LINK_ACTIVE")
        if live_serial_instance:
            live_serial_instance.esp8266_uart_bridge_active = True
            live_serial_instance.last_esp8266_heartbeat = now

    esp8266_conn = esp8266_flag or (live_serial_instance and live_serial_instance.is_esp8266_connected)
    both_conn = True

    cond = RoadCondition.WET if (alert_str == "WET_ROAD" or moist_val < 2000) else RoadCondition.DRY
    traf = TrafficLevel.CONGESTED if (alert_str == "CONGESTION" or sum([1 for x in ir_bools if x]) >= 2) else TrafficLevel.LIGHT

    tele = CanonicalTelemetry(
        device_id="SENTRAX-ESP32",
        timestamp=now,
        connection_state=ConnectionState.CONNECTED,
        measured_speed_kmh=speed_val,
        recommended_speed_kmh=float(payload.get("rec_speed", payload.get("recommended_speed_kmh", 80.0))),
        posted_speed_kmh=80.0,
        traffic_count=sum([1 for x in ir_bools if x]),
        traffic_level=traf,
        road_condition=cond,
        collision=(alert_str == "COLLISION" or sound_val),
        wrong_way=(alert_str == "WRONG_WAY"),
        stalled_vehicle=(alert_str == "STALLED"),
        emergency_vehicle=(alert_str == "EMERGENCY" or rfid_val),
        temperature_c=temp_val,
        humidity_pct=hum_val,
        moisture_raw=moist_val,
        ir_sensors=ir_bools,
        sound_active=sound_val,
        rfid_active=rfid_val,
        night_mode=night_val,
        source=DeviceSource.ESP32,
        is_simulated=False,
        esp32_connected=True,
        esp8266_connected=bool(esp8266_conn),
        both_modules_connected=True,
        hardware_standby=False
    )

    score, reasons = RoadRiskEngine.calculate_risk(tele)
    tele.risk_score = score
    tele.risk_reasons = reasons
    rec = RecommendationEngine.get_recommended_speed(tele, tele.posted_speed_kmh)
    tele.recommended_speed_kmh = rec.recommended_speed_kmh

    save_telemetry(tele)
    update_device_status("SENTRAX-ESP32", "CONNECTED", last_event=alert_str)

    if simulator_instance:
        simulator_instance.telemetry = tele
        simulator_instance._latest_live_telemetry = tele
        if hasattr(simulator_instance, "broadcast_callback") and simulator_instance.broadcast_callback:
            await simulator_instance.broadcast_callback(tele, None)

    return {"status": "ingested", "is_live": True, "device": "SENTRAX-ESP32"}


# =====================================================================
# EVENTS
# =====================================================================
@router.get("/events")
def list_events(
    limit: int = Query(50, ge=1, le=500),
    type: Optional[str] = None,
    severity: Optional[str] = None
):
    return get_events(limit, type, severity)


@router.post("/events")
def create_event(event: CanonicalEvent):
    eid = save_event(event)
    return {"status": "recorded", "event_id": eid}


# =====================================================================
# ROAD HEALTH & HAZARDS
# =====================================================================
@router.get("/road-health")
def road_health_summary():
    score, band, color, reasons = RoadHealthEngine.evaluate_segment_health(
        potholes=len(get_potholes(10)),
        collision_history=1,
        is_wet=False,
        traffic_congestion=False,
        base_score=92
    )
    return {
        "road_health_score": score,
        "health_band": band,
        "status_color": color,
        "deterioration_factors": reasons,
        "potholes_count": len(get_potholes(50)),
        "active_hazards_count": len(get_active_hazards()),
        "scoring_model": "SentraX Prototype Road Health Model (Not an official govt standard)"
    }


@router.get("/hazards")
def list_hazards():
    return get_active_hazards()


@router.post("/hazards")
def add_hazard(hazard: HazardZone):
    hid = save_hazard_zone(hazard)
    return {"status": "created", "hazard_id": hid}


@router.get("/potholes")
def list_potholes(limit: int = Query(50, ge=1, le=200)):
    return get_potholes(limit)


# =====================================================================
# ROUTE HEALTH & MAP NAVIGATION
# =====================================================================
@router.get("/route-health")
def default_route_health():
    req = RouteHealthRequest()
    tele = simulator_instance.telemetry if simulator_instance else None
    return route_service.calculate_route_health(req, live_telemetry=tele)


@router.post("/route-health")
def compute_route_health(req: RouteHealthRequest):
    tele = simulator_instance.telemetry if simulator_instance else None
    return route_service.calculate_route_health(req, live_telemetry=tele)


@router.get("/maps/config")
def get_maps_config():
    api_key = route_service.google_api_key
    has_key = bool(api_key and not api_key.startswith("mock") and len(api_key) > 10)
    return {
        "google_maps_configured": has_key,
        "api_key_masked": (api_key[:4] + "..." + api_key[-4:]) if has_key else "",
        "default_origin": "Woxsen North Roundabout",
        "default_destination": "Woxsen Hostels & Blue Embers",
        "origin_coords": [17.6638, 77.9272],
        "dest_coords": [17.6596, 77.9248]
    }


@router.post("/maps/config")
def update_maps_config(key: str = Body(..., embed=True)):
    route_service.set_api_key(key)
    has_key = bool(key and not key.startswith("mock") and len(key) > 10)
    return {
        "status": "updated",
        "google_maps_configured": has_key,
        "api_key_masked": (key[:4] + "..." + key[-4:]) if has_key else ""
    }


# =====================================================================
# RECOMMENDATIONS
# =====================================================================
@router.get("/recommendations")
def get_recommendations():
    tele = simulator_instance.telemetry if simulator_instance else CanonicalTelemetry()
    speed_rec = RecommendationEngine.get_recommended_speed(tele, tele.posted_speed_kmh)
    transit_rec = RecommendationEngine.get_vehicle_recommendation(
        trip_distance_km=6.5,
        traffic_level=tele.traffic_level,
        road_condition=tele.road_condition
    )
    return {
        "speed_advisory": speed_rec.model_dump(),
        "multimodal_recommendation": transit_rec.model_dump(),
        "disclaimer": "SentraX Recommended Speed is purely advisory. Posted speed limits remain legally binding."
    }


# =====================================================================
# ANALYTICS
# =====================================================================
@router.get("/analytics")
def analytics_metrics():
    events = get_events(limit=200)
    history = get_telemetry_history(limit=50)

    by_type = {}
    for e in events:
        t = e.get("type", "UNKNOWN")
        by_type[t] = by_type.get(t, 0) + 1

    speeds = [h.get("measured_speed_kmh", 0.0) for h in history if h.get("measured_speed_kmh", 0) > 0]
    avg_speed = round(sum(speeds) / len(speeds), 1) if speeds else 3.8

    return {
        "total_events_logged": len(events),
        "events_by_type": by_type,
        "overspeed_count": by_type.get("OVERSPEED", 0),
        "wrong_way_count": by_type.get("WRONG_WAY", 0),
        "collision_count": by_type.get("COLLISION", 0),
        "congestion_count": by_type.get("CONGESTION", 0),
        "stalled_count": by_type.get("STALLED", 0),
        "wet_road_count": by_type.get("WET_ROAD", 0),
        "emergency_count": by_type.get("EMERGENCY", 0),
        "average_speed_kmh": avg_speed,
        "road_health_trend": [88, 86, 85, 82, 79, 81, 84, 82],
        "speed_history": [h.get("measured_speed_kmh", 0) for h in reversed(history[:20])],
        "risk_history": [h.get("risk_score", 0) for h in reversed(history[:20])],
        "timestamps": [h.get("timestamp", 0) for h in reversed(history[:20])]
    }


# =====================================================================
# SIMULATION & DEMO CONTROL
# =====================================================================
@router.post("/simulation/start")
async def start_demo():
    if simulator_instance:
        await simulator_instance.start_one_click_demo()
        return {"status": "started", "scenario": "9-step automated expo sequence"}
    return {"status": "error"}


@router.post("/simulation/stop")
async def stop_demo():
    if simulator_instance:
        await simulator_instance.stop_one_click_demo()
        return {"status": "stopped"}
    return {"status": "error"}


@router.get("/simulation/status")
def simulation_status():
    if simulator_instance:
        res = simulator_instance.get_status()
        res["is_live_hardware_mode"] = is_live_hardware_mode
        return res
    return {"is_active": False}


@router.post("/simulation/scenario")
async def set_scenario(scenario: str = Body(..., embed=True)):
    if simulator_instance:
        await simulator_instance.trigger_scenario(scenario)
        return {"status": "applied", "scenario": scenario}
    return {"status": "error"}


# =====================================================================
# COMPUTER VISION FEED & METRICS
# =====================================================================
@router.get("/cv/stats")
def get_cv_stats():
    if cv_pipeline_instance:
        return cv_pipeline_instance.get_summary_stats()
    return {}


@router.get("/cv/feed")
def get_cv_feed():
    def frame_generator():
        while True:
            if cv_pipeline_instance and cv_pipeline_instance.last_frame_jpeg:
                frame_bytes = cv_pipeline_instance.last_frame_jpeg
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.08)

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")
