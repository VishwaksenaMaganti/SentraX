"""
REST endpoints for the "Ask SentraX" copilot.
  GET  /api/ai/status  -> model and whether an API key is configured (never the key itself)
  POST /api/ai/chat    -> Server-Sent Events stream of the answer
  POST /api/ai/reset   -> forget a conversation
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from software.backend.ai.copilot import copilot

router = APIRouter(prefix="/ai")


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)


class ResetRequest(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)


@router.get("/status")
def ai_status():
    return copilot.status()


@router.post("/chat")
async def ai_chat(req: ChatRequest):
    return StreamingResponse(
        copilot.stream_answer(req.session_id, req.message.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/reset")
def ai_reset(req: ResetRequest):
    copilot.reset(req.session_id)
    return {"status": "reset"}
