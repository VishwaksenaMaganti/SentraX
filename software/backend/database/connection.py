"""
SentraX SQLite Database Connection & Initialization
"""

import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

DB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"
DB_PATH = DB_DIR / "sentrax.db"

_initialized = False


def get_db_path() -> Path:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def init_db():
    global _initialized
    db_file = get_db_path()
    with sqlite3.connect(str(db_file)) as conn:
        cursor = conn.cursor()

        # 1. Devices
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            connection_state TEXT NOT NULL,
            last_seen REAL NOT NULL,
            rssi INTEGER,
            firmware_version TEXT,
            uptime_seconds INTEGER,
            port_or_address TEXT,
            last_event TEXT
        );
        """)

        # 2. Telemetry
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            timestamp REAL NOT NULL,
            measured_speed_kmh REAL,
            recommended_speed_kmh REAL,
            posted_speed_kmh REAL,
            traffic_count INTEGER,
            traffic_level TEXT,
            road_condition TEXT,
            collision INTEGER,
            wrong_way INTEGER,
            stalled_vehicle INTEGER,
            emergency_vehicle INTEGER,
            temperature_c REAL,
            humidity_pct REAL,
            moisture_raw INTEGER,
            sound_active INTEGER,
            rfid_active INTEGER,
            night_mode INTEGER,
            cv_vehicle_count INTEGER,
            hazard_count INTEGER,
            risk_score INTEGER,
            risk_reasons TEXT,
            source TEXT,
            is_simulated INTEGER
        );
        """)

        # 3. Events
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            source TEXT NOT NULL,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            confidence REAL NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            payload_json TEXT,
            is_simulated INTEGER
        );
        """)

        # 4. Road Segments
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS road_segments (
            id TEXT PRIMARY KEY,
            name TEXT,
            start_lat REAL,
            start_lng REAL,
            end_lat REAL,
            end_lng REAL,
            health_score INTEGER,
            risk_score INTEGER,
            health_band TEXT,
            color_hex TEXT,
            recommended_speed_kmh REAL,
            collision_count INTEGER,
            wet INTEGER,
            traffic_density TEXT,
            timestamp REAL
        );
        """)

        # 5. Hazards
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hazards (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            radius_meters REAL,
            severity TEXT,
            confidence REAL,
            created_at REAL,
            expires_at REAL,
            source TEXT,
            is_active INTEGER,
            is_simulated INTEGER
        );
        """)

        # 7. Vehicles / Tracks
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cv_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL,
            vehicle_class TEXT NOT NULL,
            confidence REAL,
            direction TEXT,
            estimated_speed_kmh REAL,
            is_calibrated_speed INTEGER,
            lane INTEGER,
            timestamp REAL,
            is_hazard INTEGER,
            hazard_reason TEXT
        );
        """)

        # 8. Route Sessions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS route_sessions (
            session_id TEXT PRIMARY KEY,
            origin_name TEXT,
            destination_name TEXT,
            total_distance_km REAL,
            overall_health_score INTEGER,
            overall_health_band TEXT,
            overall_risk_score INTEGER,
            recommended_speed_kmh REAL,
            collision_zones_count INTEGER,
            created_at REAL
        );
        """)

        # 9. Recommendations
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            recommended_speed_kmh REAL,
            posted_speed_kmh REAL,
            reasons_json TEXT,
            vehicle_type TEXT,
            vehicle_rationale TEXT
        );
        """)

        # 10. Risk Scores
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            score INTEGER,
            reasons_json TEXT
        );
        """)

        # 11. Simulation Sessions
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS simulation_sessions (
            id TEXT PRIMARY KEY,
            started_at REAL,
            stopped_at REAL,
            scenario_name TEXT,
            step_count INTEGER,
            notes TEXT
        );
        """)

        cursor.execute("SELECT COUNT(*) FROM devices;")
        if cursor.fetchone()[0] == 0:
            now_time = 0.0
            cursor.execute("""
            INSERT INTO devices (device_id, display_name, connection_state, last_seen, rssi, firmware_version, uptime_seconds, port_or_address, last_event)
            VALUES 
            ('SENTRAX-ESP32', 'SentraX Road Controller (ESP32)', 'DISCONNECTED', ?, -65, 'v2.4.0-esp32', 0, 'BLE / COM Port', 'STANDBY'),
            ('SENTRAX-ESP8266', 'SentraX Auxiliary Unit (ESP8266)', 'DISCONNECTED', ?, -72, 'v1.8.0-esp8266', 0, 'UART Link / COM Port', 'STANDBY');
            """, (now_time, now_time))

        conn.commit()
    _initialized = True


@contextmanager
def get_db_connection():
    global _initialized
    if not _initialized:
        init_db()
    db_file = get_db_path()
    conn = sqlite3.connect(str(db_file), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("SentraX database initialized successfully at:", DB_PATH)
