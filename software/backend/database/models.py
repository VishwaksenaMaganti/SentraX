"""
Database access helpers and query repository for SentraX
"""

import json
import time
from typing import List, Optional, Dict, Any
from software.backend.database.connection import get_db_connection
from software.backend.schemas.telemetry import CanonicalTelemetry, DeviceStatus, ConnectionState
from software.backend.schemas.events import CanonicalEvent, EventType, EventSeverity
from software.backend.schemas.hazards import HazardZone, VehicleTrack


def save_telemetry(t: CanonicalTelemetry) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO telemetry (
            device_id, timestamp, measured_speed_kmh, recommended_speed_kmh, posted_speed_kmh,
            traffic_count, traffic_level, road_condition, collision, wrong_way,
            stalled_vehicle, emergency_vehicle, temperature_c, humidity_pct, moisture_raw,
            sound_active, rfid_active, night_mode, cv_vehicle_count,
            hazard_count, risk_score, risk_reasons, source, is_simulated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t.device_id, t.timestamp, t.measured_speed_kmh, t.recommended_speed_kmh, t.posted_speed_kmh,
            t.traffic_count, t.traffic_level.value, t.road_condition.value,
            1 if t.collision else 0, 1 if t.wrong_way else 0,
            1 if t.stalled_vehicle else 0, 1 if t.emergency_vehicle else 0,
            t.temperature_c, t.humidity_pct, t.moisture_raw,
            1 if t.sound_active else 0, 1 if t.rfid_active else 0,
            1 if t.night_mode else 0, t.cv_vehicle_count,
            t.hazard_count, t.risk_score, json.dumps(t.risk_reasons),
            t.source.value, 1 if t.is_simulated else 0
        ))
        conn.commit()
        return cursor.lastrowid


def save_event(event: CanonicalEvent) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO events (
            event_id, timestamp, source, type, severity, confidence, title, description, payload_json, is_simulated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.event_id, event.timestamp, event.source, event.type.value,
            event.severity.value, event.confidence, event.title, event.description,
            json.dumps(event.payload), 1 if event.is_simulated else 0
        ))
        conn.commit()
        return event.event_id


def get_latest_telemetry() -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM telemetry WHERE is_simulated = 0 ORDER BY id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if "risk_reasons" in d and isinstance(d["risk_reasons"], str):
            try:
                d["risk_reasons"] = json.loads(d["risk_reasons"])
            except Exception:
                d["risk_reasons"] = [d["risk_reasons"]]
        return d


def get_telemetry_history(limit: int = 50) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM telemetry WHERE is_simulated = 0 ORDER BY id DESC LIMIT ?;", (limit,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if "risk_reasons" in d and isinstance(d["risk_reasons"], str):
                try:
                    d["risk_reasons"] = json.loads(d["risk_reasons"])
                except Exception:
                    pass
            result.append(d)
        return result


def get_events(limit: int = 50, event_type: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM events WHERE is_simulated = 0"
        params = []
        if event_type:
            query += " AND type = ?"
            params.append(event_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if "payload_json" in d and isinstance(d["payload_json"], str):
                try:
                    d["payload"] = json.loads(d["payload_json"])
                except Exception:
                    d["payload"] = {}
            result.append(d)
        return result


def get_devices() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM devices ORDER BY device_id ASC;")
        return [dict(r) for r in cursor.fetchall()]


def update_device_status(
    device_id: str,
    state: str,
    rssi: Optional[int] = None,
    last_event: Optional[str] = None,
    port_or_address: Optional[str] = None
):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = time.time()
        cursor.execute("""
        UPDATE devices
        SET connection_state = ?, last_seen = ?, rssi = COALESCE(?, rssi), last_event = COALESCE(?, last_event), port_or_address = COALESCE(?, port_or_address)
        WHERE device_id = ?;
        """, (state, now, rssi, last_event, port_or_address, device_id))
        conn.commit()


def save_hazard_zone(hz: HazardZone) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO hazards (
            id, type, title, description, latitude, longitude, radius_meters,
            severity, confidence, created_at, expires_at, source, is_active, is_simulated
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hz.id, hz.type.value, hz.title, hz.description, hz.latitude, hz.longitude,
            hz.radius_meters, hz.severity.value, hz.confidence, hz.created_at,
            hz.expires_at, hz.source, 1 if hz.is_active else 0, 1 if hz.is_simulated else 0
        ))
        conn.commit()
        return hz.id


def get_active_hazards() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        now = time.time()
        cursor.execute("""
        SELECT * FROM hazards
        WHERE is_active = 1 AND (expires_at IS NULL OR expires_at > ?)
        ORDER BY created_at DESC;
        """, (now,))
        return [dict(r) for r in cursor.fetchall()]
