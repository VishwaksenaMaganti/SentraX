"""
SentraX Real-Time WebSocket Hub
Broadcasts live telemetry, alerts, and hazard updates to connected dashboard clients.
"""

from typing import List, Dict, Any
from fastapi import WebSocket
import logging
import json

logger = logging.getLogger("sentrax.websocket")


class WebSocketHub:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("Client connected to SentraX WebSocket. Active count: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Client disconnected from SentraX WebSocket. Active count: %d", len(self.active_connections))

    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
        payload = json.dumps(message)
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(payload)
            except Exception as e:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)


ws_hub = WebSocketHub()
