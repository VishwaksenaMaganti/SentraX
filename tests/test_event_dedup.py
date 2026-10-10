"""
A condition that persists across fusion cycles (every 0.5 s) is logged once per episode,
not once per cycle. The fuse() result still lists every active event.
"""

from unittest.mock import patch

from software.backend.schemas.telemetry import CanonicalTelemetry, RoadCondition
from software.backend.engines import fusion_engine as fe_mod
from software.backend.engines.fusion_engine import SensorCameraFusionEngine

WET = CanonicalTelemetry(road_condition=RoadCondition.WET, moisture_raw=1200)
DRY = CanonicalTelemetry()
CV = {"vehicle_count": 0}


def _run(engine, tele, at):
    with patch.object(fe_mod.time, "time", return_value=at), patch.object(fe_mod, "save_event") as saved:
        _, events = engine.fuse(tele, CV)
    return events, saved.call_count


def test_persistent_condition_logged_once():
    engine = SensorCameraFusionEngine()
    events, saved = _run(engine, WET, 1000.0)
    assert events and saved == 1
    assert engine.fresh_event_ids == {events[0].event_id}

    for k in range(1, 20):
        events, saved = _run(engine, WET, 1000.0 + k * 0.5)
        assert events, "the active event is still reported every cycle"
        assert saved == 0
        assert engine.fresh_event_ids == set()


def test_condition_relogged_after_it_clears():
    engine = SensorCameraFusionEngine()
    _run(engine, WET, 1000.0)
    _run(engine, DRY, 1001.0)
    _, saved = _run(engine, WET, 1000.0 + fe_mod.EVENT_GAP_SECONDS + 1.5)
    assert saved == 1


def test_long_condition_relogged_periodically():
    engine = SensorCameraFusionEngine()
    _run(engine, WET, 1000.0)
    t = 1000.0
    total = 0
    while t < 1000.0 + fe_mod.EVENT_RELOG_SECONDS + 1:
        t += 0.5
        total += _run(engine, WET, t)[1]
    assert total == 1
