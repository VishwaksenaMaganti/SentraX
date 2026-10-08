"""
SentraX "Ask SentraX" Copilot
Answers operator questions in plain English by reading live SentraX data through
read-only tools (telemetry, events, analytics, road health, hardware status).

Safety posture:
  - Read-only. The copilot has no tool that writes to the database or sends commands
    to the ESP32, LEDs or E-Ink sign. Hardware control stays in the Aerial Twin console.
  - The deterministic RoadRiskEngine remains the source of truth; the copilot explains
    its output and never produces its own risk scores.
"""

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any, AsyncIterator, Dict, List

import anthropic

from software.backend.core.config import settings
from software.backend.api import routes as api

logger = logging.getLogger("sentrax.ai")

SYSTEM_PROMPT = """You are SentraX Copilot, the operator assistant inside the SentraX road-safety command dashboard.

SentraX is a physical smart-road testbed (a scale model corridor driven by toy cars) built around an ESP32 core controller:
- 4 IR presence sensors (IR1 entrance, IR2 mid-left, IR3 mid-right, IR4 exit) on GPIO 25/26/27/33.
- Dual ultrasonic speed gate (US1 entry, US2 exit) 0.30 m apart that times passing vehicles.
- Acoustic crash sensor (GPIO 32), rain/surface moisture sensor (GPIO 35, raw < 2000 means WET), DHT11 temperature and humidity (GPIO 13).
- RFID emergency-vehicle tag reader, ambient light (night mode), 60 WS2812B roadside LEDs and a 1.54" E-Ink overhead speed sign.

Detection rules: congestion = 2+ IR sensors occupied for 5 s or more; stalled vehicle = one IR sensor occupied for 6 s or more; wrong-way = IR4 then IR3 within 15 s.
Advisory speeds: 80 km/h normal, 60 congestion, 40 wet road, 35 high temperature (>= 30 C), 30 stalled, 25 wrong-way, 20 collision.
Speeds in the demo are toy-car speeds; the demo overspeed threshold is 4.0 km/h.
The road risk score (0-100) comes from SentraX's deterministic prototype risk engine. The road health score is a prototype metric, not an official government rating. Recommended speeds are advisory; posted limits remain legally binding.

How to work:
- Use the tools to read live data before answering anything about the current state, recent incidents or trends. Never invent readings, counts or timestamps.
- If the ESP32 is not connected, the dashboard is in hardware standby and live readings are not meaningful. Say so plainly and explain what the operator needs to do (pair the ESP32 over Bluetooth or USB COM).
- Explain risk scores by pointing at the engine's listed factors and their weights. Do not compute your own risk score.
- You are read-only. You cannot change speed limits, trigger alerts or control the LEDs and E-Ink sign. If asked, point the operator to the Hardware Command console on the Aerial Digital Twin tab.
- Answer like a concise control-room colleague: lead with the answer, then the evidence. Short paragraphs or bullets, numbers with units, local times as HH:MM:SS. No filler."""

_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "get_live_telemetry",
        "description": "Latest fused telemetry snapshot: hardware connection flags, measured and recommended speed, risk score with the engine's reasons, traffic level, road condition, every sensor reading (IR grid, ultrasonic gate, sound, moisture, temperature, humidity, RFID, night mode) and active incident flags.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_events",
        "description": "Recent incidents from the persistent event log, newest first. Each has local time, type, severity, source, title and description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of events to return (1-100). Default 20."},
                "severity": {"type": "string", "enum": ["INFO", "WARNING", "CRITICAL"], "description": "Only return events of this severity."},
                "event_type": {"type": "string", "description": "Only return events of this type, e.g. COLLISION, WRONG_WAY, STALLED, CONGESTION, WET_ROAD, OVERSPEED, EMERGENCY."},
            },
            "required": [],
        },
    },
    {
        "name": "get_telemetry_history",
        "description": "Recent live (non-simulated) telemetry samples, oldest first, condensed to time, measured speed, recommended speed, risk score, traffic level and road condition. Use for trends.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Number of samples (1-200). Default 40."}},
            "required": [],
        },
    },
    {
        "name": "get_analytics",
        "description": "Aggregate analytics: total logged incidents, incident counts by type, average measured speed and the road health trend.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_road_health",
        "description": "Prototype road health score, band, deterioration factors and pothole/hazard counts, plus the default route's segment health summary.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_hardware_status",
        "description": "Connection status of the ESP32 core controller (transport BLE or SERIAL, address/port) and the ESP8266 link, plus registered device records.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

# Eager input streaming is the default for streamed client tools; inputs are validated in _run_tool.
TOOLS = [{**spec, "eager_input_streaming": True} for spec in _TOOL_SPECS]

TOOL_STATUS_LABELS = {
    "get_live_telemetry": "Reading live telemetry",
    "get_recent_events": "Checking the incident log",
    "get_telemetry_history": "Reviewing telemetry history",
    "get_analytics": "Pulling analytics",
    "get_road_health": "Checking road health",
    "get_hardware_status": "Checking hardware links",
}


def _local_time(ts: Any) -> str:
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return "unknown"


def _bounded_int(value: Any, default: int, low: int, high: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected a number, got {value!r}")
    return max(low, min(high, int(value)))


def _live_telemetry() -> Dict[str, Any]:
    if api.simulator_instance is not None:
        t = api.simulator_instance.telemetry.model_dump()
    else:
        t = api.latest_telemetry()
    t = dict(t)
    t["local_time"] = _local_time(t.get("timestamp"))
    t["hardware_standby"] = not bool(t.get("esp32_connected"))
    return t


def _recent_events(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    limit = _bounded_int(args.get("limit"), 20, 1, 100)
    severity = args.get("severity")
    event_type = args.get("event_type")
    if severity is not None and severity not in ("INFO", "WARNING", "CRITICAL"):
        raise ValueError("severity must be INFO, WARNING or CRITICAL")
    if event_type is not None and not isinstance(event_type, str):
        raise ValueError("event_type must be a string")
    events = api.get_events(limit, event_type.upper() if event_type else None, severity)
    return [
        {
            "time": _local_time(e.get("timestamp")),
            "type": e.get("type"),
            "severity": e.get("severity"),
            "source": e.get("source"),
            "title": e.get("title"),
            "description": e.get("description"),
        }
        for e in events
    ]


def _telemetry_history(args: Dict[str, Any]) -> List[Dict[str, Any]]:
    limit = _bounded_int(args.get("limit"), 40, 1, 200)
    rows = api.get_telemetry_history(limit)
    return [
        {
            "time": _local_time(r.get("timestamp")),
            "measured_speed_kmh": r.get("measured_speed_kmh"),
            "recommended_speed_kmh": r.get("recommended_speed_kmh"),
            "risk_score": r.get("risk_score"),
            "traffic_level": r.get("traffic_level"),
            "road_condition": r.get("road_condition"),
        }
        for r in reversed(rows)
    ]


def _road_health() -> Dict[str, Any]:
    route = api.default_route_health()
    route = route.model_dump() if hasattr(route, "model_dump") else route
    return {
        "road_health": api.road_health_summary(),
        "route": {
            "overall_health_score": route.get("overall_health_score"),
            "overall_health_band": route.get("overall_health_band"),
            "recommended_speed_kmh": route.get("recommended_speed_kmh"),
            "pothole_count": route.get("pothole_count"),
            "collision_zones_count": route.get("collision_zones_count"),
            "segments": [
                {
                    "name": s.get("name"),
                    "health_score": s.get("health_score"),
                    "health_band": s.get("health_band"),
                    "recommended_speed_kmh": s.get("recommended_speed_kmh"),
                }
                for s in route.get("segments", [])
            ],
        },
    }


def _hardware_status() -> Dict[str, Any]:
    return {"links": api.get_hardware_status(), "devices": api.list_devices()}


def _run_tool(name: str, args: Any) -> str:
    if not isinstance(args, dict):
        raise ValueError("tool input must be a JSON object")
    if name == "get_live_telemetry":
        result: Any = _live_telemetry()
    elif name == "get_recent_events":
        result = _recent_events(args)
    elif name == "get_telemetry_history":
        result = _telemetry_history(args)
    elif name == "get_analytics":
        result = api.analytics_metrics()
    elif name == "get_road_health":
        result = _road_health()
    elif name == "get_hardware_status":
        result = _hardware_status()
    else:
        raise ValueError(f"unknown tool {name}")
    return json.dumps(result, default=str)


def _sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class CopilotService:
    """Holds per-browser-session conversations in memory and streams Claude's answers."""

    MAX_SESSIONS = 50
    MAX_TOOL_ROUNDS = 8

    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None
        self._sessions: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
        self._locks: Dict[str, asyncio.Lock] = {}

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        return self._client

    def status(self) -> Dict[str, Any]:
        return {
            "model": settings.AI_MODEL,
            "effort": settings.AI_EFFORT,
            "api_key_configured": settings.ANTHROPIC_API_KEY_SET,
        }

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _history(self, session_id: str) -> List[Dict[str, Any]]:
        if session_id in self._sessions:
            self._sessions.move_to_end(session_id)
        else:
            self._sessions[session_id] = []
            while len(self._sessions) > self.MAX_SESSIONS:
                old_id, _ = self._sessions.popitem(last=False)
                self._locks.pop(old_id, None)
        return self._sessions[session_id]

    async def stream_answer(self, session_id: str, user_text: str) -> AsyncIterator[str]:
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        if lock.locked():
            yield _sse({"type": "error", "message": "SentraX is still answering your previous question."})
            return

        async with lock:
            history = self._history(session_id)
            # Work on a copy and only commit complete turns, so a failed request never
            # leaves a dangling user turn or an unanswered tool_use in the conversation.
            messages = list(history)
            messages.append({"role": "user", "content": user_text})

            try:
                for _ in range(self.MAX_TOOL_ROUNDS):
                    async with self.client.beta.messages.stream(
                        model=settings.AI_MODEL,
                        max_tokens=64000,
                        system=SYSTEM_PROMPT,
                        tools=TOOLS,
                        messages=messages,
                        output_config={"effort": settings.AI_EFFORT},
                        cache_control={"type": "ephemeral"},
                        betas=["server-side-fallback-2026-07-01"],
                        fallbacks="default",
                    ) as stream:
                        async for event in stream:
                            if event.type == "text":
                                yield _sse({"type": "text", "text": event.text})
                        response = await stream.get_final_message()

                    messages.append({"role": "assistant", "content": response.content})

                    if response.stop_reason == "refusal":
                        yield _sse({"type": "error", "message": "SentraX can't help with that request."})
                        return

                    tool_uses = [b for b in response.content if b.type == "tool_use"]
                    if response.stop_reason == "pause_turn":
                        continue
                    if not tool_uses:
                        history[:] = messages
                        yield _sse({"type": "done"})
                        return
                    if response.stop_reason == "max_tokens":
                        yield _sse({"type": "error", "message": "The answer was cut off. Try a narrower question."})
                        return

                    results = []
                    for block in tool_uses:
                        yield _sse({"type": "status", "label": TOOL_STATUS_LABELS.get(block.name, "Reading SentraX data")})
                        try:
                            content = await asyncio.to_thread(_run_tool, block.name, block.input)
                            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
                        except Exception as exc:  # report tool failures back to the model, don't crash the turn
                            logger.warning("Copilot tool %s failed: %s", block.name, exc)
                            results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "is_error": True,
                                "content": f"Tool error: {exc}",
                            })
                    messages.append({"role": "user", "content": results})

                yield _sse({"type": "error", "message": "SentraX needed too many lookups for that question. Try a more specific one."})

            except ValueError as exc:
                # Raised by the SDK stream iterator when a streamed tool input is unparseable JSON.
                logger.warning("Copilot received malformed tool input: %s", exc)
                yield _sse({"type": "error", "message": "SentraX hit a glitch reading data. Please ask again."})
            except anthropic.AuthenticationError:
                yield _sse({"type": "error", "message": "The Anthropic API key is missing or invalid. Add ANTHROPIC_API_KEY to the .env file and restart the server."})
            except anthropic.PermissionDeniedError:
                yield _sse({"type": "error", "message": "The Anthropic API key doesn't have access to this model."})
            except anthropic.RateLimitError:
                yield _sse({"type": "error", "message": "Rate limit reached. Wait a few seconds and ask again."})
            except anthropic.APIConnectionError:
                yield _sse({"type": "error", "message": "Can't reach the Anthropic API. Check the internet connection."})
            except anthropic.APIStatusError as exc:
                logger.error("Copilot API error %s: %s", exc.status_code, exc.message)
                yield _sse({"type": "error", "message": f"Claude API error ({exc.status_code}). Please try again."})
            except anthropic.AnthropicError as exc:
                logger.error("Copilot error: %s", exc)
                yield _sse({"type": "error", "message": "AI request failed. Check that ANTHROPIC_API_KEY is set in the .env file, then restart the server."})
            except Exception as exc:
                # e.g. the SDK cannot resolve any credentials at request time
                if not settings.ANTHROPIC_API_KEY_SET:
                    logger.warning("Copilot called without ANTHROPIC_API_KEY: %s", exc)
                    message = "AI is not configured yet. Add ANTHROPIC_API_KEY to the .env file and restart the server."
                else:
                    logger.exception("Copilot unexpected error")
                    message = f"AI request failed ({type(exc).__name__}). Check the server log."
                yield _sse({"type": "error", "message": message})


copilot = CopilotService()
