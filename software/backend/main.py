"""
SentraX Intelligent & Adaptive Road Safety Platform - Main Application Entrypoint
FastAPI Backend orchestrating Microcontroller Communication, BLE Gateway,
Computer Vision, Road Health Intelligence, Route Analytics, and Live WebSocket Telemetry.
"""

import asyncio
import os
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from software.backend.core.config import settings
from software.backend.core.logging import setup_logging
from software.backend.database.connection import init_db
from software.backend.api.routes import router as api_router, set_services
from software.backend.api.websocket import ws_hub
from software.backend.simulation.simulator import SentraXSimulator
from software.backend.cv.cv_pipeline import CVPipeline
from software.backend.ble.bleak_transport import SentraXBLEGateway
from software.backend.ble.live_ble_service import LiveBLEManager
from software.backend.serial_comm.live_serial_service import LiveSerialManager
from software.backend.engines.data_fusion import DataFusionEngine
from software.backend.engines.emergency_tracker import emergency_tracker
from software.backend.engines.speed_tracker import speed_tracker

setup_logging()

# Global background tasks and components
simulator = SentraXSimulator()
cv_pipeline = CVPipeline(camera_index=-1, use_simulation=True)
ble_gateway = SentraXBLEGateway(use_mock=True)


async def broadcast_telemetry_event(telemetry, event):
    """Callback invoked by simulator or physical hardware receivers to broadcast updates."""
    tele_data = (
        telemetry.model_dump() if hasattr(telemetry, "model_dump")
        else (telemetry.dict() if hasattr(telemetry, "dict") else telemetry)
    )
    evt_data = None
    if event:
        evt_data = (
            event.model_dump() if hasattr(event, "model_dump")
            else (event.dict() if hasattr(event, "dict") else event)
        )

    msg = {
        "type": "telemetry_update",
        "timestamp": time.time(),
        "telemetry": tele_data,
        "event": evt_data
    }
    await ws_hub.broadcast(msg)


# Physical hardware managers
live_ble = LiveBLEManager(on_telemetry_broadcast=broadcast_telemetry_event)
live_serial = LiveSerialManager(on_telemetry_broadcast=broadcast_telemetry_event)

# Register instances with router
set_services(simulator, cv_pipeline, live_ble, live_serial)
simulator.broadcast_callback = broadcast_telemetry_event


async def background_perception_loop():
    """Main background loop: Gates telemetry behind confirmed connection of both ESP32 & ESP8266."""
    while True:
        try:
            from software.backend.schemas.telemetry import CanonicalTelemetry, ConnectionState, RoadCondition, TrafficLevel, DeviceSource

            # 1. Process CV step
            cv_stats = cv_pipeline.process_step()

            # 2. Check connection states of both microcontrollers
            esp32_conn = False
            esp8266_conn = False

            now = time.time()
            # Keep the last reading through the ESP32's blocking alert sequences (~9 s silence)
            stall_tolerance = settings.TELEMETRY_STALL_TOLERANCE_SECONDS
            if live_ble and live_ble.is_connected:
                esp32_conn = True
            elif live_serial and live_serial.is_esp32_connected:
                esp32_conn = True
            elif hasattr(simulator, "_latest_live_telemetry") and simulator._latest_live_telemetry:
                if (now - simulator._latest_live_telemetry.timestamp) < stall_tolerance:
                    esp32_conn = True

            if live_serial and live_serial.is_esp8266_connected:
                esp8266_conn = True
            elif hasattr(simulator, "_latest_live_telemetry") and simulator._latest_live_telemetry:
                if simulator._latest_live_telemetry.esp8266_connected and (now - simulator._latest_live_telemetry.timestamp < 2.0):
                    esp8266_conn = True

            both_conn = bool(esp32_conn)

            if both_conn:
                # ESP32 CONNECTED: Ingest fresh live sensor telemetry
                live_tele = None
                if live_ble and live_ble.is_connected and live_ble.latest_live_telemetry:
                    if (now - live_ble.latest_live_telemetry.timestamp < stall_tolerance):
                        live_tele = live_ble.latest_live_telemetry
                elif live_serial and live_serial.is_esp32_connected and live_serial.latest_live_telemetry:
                    if (now - live_serial.latest_live_telemetry.timestamp < stall_tolerance):
                        live_tele = live_serial.latest_live_telemetry
                elif hasattr(simulator, "_latest_live_telemetry") and simulator._latest_live_telemetry:
                    if (now - simulator._latest_live_telemetry.timestamp < stall_tolerance):
                        live_tele = simulator._latest_live_telemetry

                if live_tele:
                    live_tele.esp32_connected = True
                    live_tele.esp8266_connected = esp8266_conn
                    live_tele.both_modules_connected = True
                    live_tele.hardware_standby = False
                    live_tele.is_simulated = False
                    # Emergency and speed readings can start or expire while the ESP32 is silent
                    emergency_tracker.apply(live_tele)
                    speed_tracker.apply(live_tele)

                    # A simulated camera must not stand in for the ultrasonic speed reading
                    fused_tele, new_events = DataFusionEngine.fuse_telemetry_and_cv(
                        live_tele, cv_stats, allow_cv_speed_fallback=not cv_pipeline.use_simulation
                    )
                    fused_tele.is_simulated = False
                    simulator.telemetry = fused_tele
                    evt = new_events[0] if new_events else None
                    await broadcast_telemetry_event(fused_tele, evt)
                else:
                    both_conn = False

            if not both_conn:
                # HARDWARE STANDBY: Zero simulated data and wipe any cached telemetry
                if hasattr(simulator, "_latest_live_telemetry"):
                    simulator._latest_live_telemetry = None

                reasons = []
                if not esp32_conn:
                    reasons.append("ESP32 Gateway not connected")
                standby_msg = f"HARDWARE STANDBY: {', '.join(reasons)}"

                standby_tele = CanonicalTelemetry(
                    device_id="SENTRAX-STANDBY",
                    timestamp=time.time(),
                    connection_state=ConnectionState.DISCONNECTED,
                    measured_speed_kmh=0.0,
                    recommended_speed_kmh=0.0,
                    posted_speed_kmh=80.0,
                    traffic_count=0,
                    traffic_level=TrafficLevel.LIGHT,
                    road_condition=RoadCondition.DRY,
                    collision=False,
                    wrong_way=False,
                    stalled_vehicle=False,
                    emergency_vehicle=False,
                    temperature_c=0.0,
                    humidity_pct=0.0,
                    moisture_raw=0,
                    ir_sensors=[False, False, False, False],
                    sound_active=False,
                    rfid_active=False,
                    night_mode=False,
                    risk_score=0,
                    risk_reasons=[standby_msg],
                    source=DeviceSource.FUSION,
                    is_simulated=False,
                    esp32_connected=esp32_conn,
                    esp8266_connected=esp8266_conn,
                    both_modules_connected=False,
                    hardware_standby=True
                )
                simulator.telemetry = standby_tele
                await broadcast_telemetry_event(standby_tele, None)

        except Exception as e:
            pass

        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    cv_pipeline.start()
    await ble_gateway.initialize()
    task = asyncio.create_task(background_perception_loop())
    yield
    # Shutdown
    task.cancel()
    cv_pipeline.stop()
    if live_ble and live_ble.is_connected:
        await live_ble.disconnect()
    if live_serial and live_serial.is_connected:
        live_serial.disconnect()
    await ble_gateway.mock_manager.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Intelligent and Adaptive Road Safety & Smart Infrastructure Ecosystem",
    version="2.4.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router, prefix=settings.API_PREFIX)


# WebSocket endpoint for real-time live telemetry
@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await ws_hub.connect(websocket)
    # Immediately push current state
    await websocket.send_json({
        "type": "initial_state",
        "telemetry": simulator.telemetry.model_dump(),
        "cv_stats": cv_pipeline.get_summary_stats()
    })
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming WebSocket commands from dashboard
            if "ping" in data:
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_hub.disconnect(websocket)


# Mount static frontend assets
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = FRONTEND_DIR / "templates" / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return "<h1>SentraX Platform Backend Online</h1><p>Frontend template initializing...</p>"
