"""
Tests for SentraX FastAPI REST Endpoints
"""

import pytest
from fastapi.testclient import TestClient
from software.backend.main import app

client = TestClient(app)


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ONLINE"
    assert "SentraX" in data["service"]


def test_telemetry_latest_endpoint():
    res = client.get("/api/telemetry/latest")
    assert res.status_code == 200
    data = res.json()
    assert "measured_speed_kmh" in data
    assert "recommended_speed_kmh" in data


def test_events_endpoint():
    res = client.get("/api/events")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)


def test_road_health_endpoint():
    res = client.get("/api/road-health")
    assert res.status_code == 200
    data = res.json()
    assert "road_health_score" in data
    assert "health_band" in data


def test_route_health_endpoint():
    res = client.get("/api/route-health")
    assert res.status_code == 200
    data = res.json()
    assert "segments" in data
    assert len(data["segments"]) > 0
    assert "overall_health_score" in data


def test_recommendations_endpoint():
    res = client.get("/api/recommendations")
    assert res.status_code == 200
    data = res.json()
    assert "speed_advisory" in data
    assert "multimodal_recommendation" in data
    assert data["speed_advisory"]["is_legal_limit"] is False


def test_simulation_status_endpoint():
    res = client.get("/api/simulation/status")
    assert res.status_code == 200
    data = res.json()
    assert "scenario" in data
