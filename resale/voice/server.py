"""FastAPI server for voice-to-voice with Claude.

- `GET /` serves the web UI (push-to-talk, browser Web Speech for STT/TTS)
- `POST /api/chat` streams Claude's response as SSE text deltas
- In-memory conversation per session_id (no DB — single-operator MVP)

Per-session system prompt is identical across sessions and cached, so the
first reply in a fresh session pays full system-prompt cost and every reply
after that ~reads from cache.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

MODEL = os.environ.get("RESALE_VOICE_MODEL", "claude-opus-4-6")
MAX_TOKENS = int(os.environ.get("RESALE_VOICE_MAX_TOKENS", "800"))

SYSTEM_PROMPT = """You are the voice copilot for a one-person junk-hauling + resale operation. The operator is talking to you over voice — your replies will be read aloud by TTS.

# Voice-mode rules (NON-NEGOTIABLE)

- **Keep replies SHORT.** 1-3 sentences for routine answers. Nobody wants a paragraph read aloud.
- **No markdown, no bullet lists, no headers.** Plain spoken English.
- **No preamble.** Skip "Great question!" / "Let me think about that" / "I'd be happy to help." Just answer.
- **Use contractions.** "It's", "you'd", "won't". Write like you talk.
- **Numbers spelled out for voice.** "eighty bucks" not "$80" when it flows better; use numerals for model numbers, years, serials.
- If an answer is genuinely long (full listing copy, detailed strategy), SAY it'll be long and offer to put it in the dashboard/email instead of speaking it.

# What you know about the operation

- Solo operator. Junk-hauling company's resale vertical. Cost basis on every item is $0 — alternative is dumping.
- Primary marketplaces in rough order: eBay, Facebook Marketplace, Whatnot, Mercari, Poshmark, Depop.
- Cross-posts via crosslist.com.
- Has a photos-to-listings pipeline you're part of (same codebase) that takes shop photos and generates marketplace listings, pricing, marketplace recs.
- Shop-walk workflow: phone burst photos with 60s+ gaps, then the cluster tool groups them by timestamp.

# How you help

When they describe an item verbally:
- Ask one pointed question if you need it (brand? condition? any marks?).
- Give a DECISIVE answer: a price range, a marketplace rec, a go/no-go on whether to bother listing.
- If it sounds potentially valuable and ID is unclear, say "worth researching — check for marks on X before listing."
- Offer to generate a full written listing if they shoot photos.

When they ask strategy/ops questions:
- Specific, tactical, short. What they can do today.
- Reference the actual tools they have (cluster, batch, inventory, crosslist).

When they just want to think out loud:
- Be a business partner, not a sycophant. Push back if an idea is bad.
- Ask one sharp question that helps them decide.

# Tone

Confident, blue-collar-friendly, no jargon unless they use it first. You run with them; you don't work for them."""

app = FastAPI(title="Resale Voice Copilot")

# In-memory session store: session_id -> list of message params
# Reset on server restart; fine for single-operator MVP.
_sessions: Dict[str, List[dict]] = {}

# Shared Anthropic client (thread-safe for concurrent requests)
_client = anthropic.Anthropic()


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Stream Claude's reply as SSE text chunks."""
    history = _sessions.setdefault(req.session_id, [])
    history.append({"role": "user", "content": req.message})

    def event_stream():
        assistant_text_parts: List[str] = []
        try:
            with _client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=history,
            ) as stream:
                for text in stream.text_stream:
                    assistant_text_parts.append(text)
                    # SSE format: `data: <json>\n\n`
                    yield f"data: {json.dumps({'delta': text})}\n\n"
                final = stream.get_final_message()
                usage = {
                    "input_tokens": final.usage.input_tokens,
                    "cache_read": getattr(final.usage, "cache_read_input_tokens", 0),
                    "cache_creation": getattr(
                        final.usage, "cache_creation_input_tokens", 0
                    ),
                    "output_tokens": final.usage.output_tokens,
                }
                yield f"data: {json.dumps({'done': True, 'usage': usage})}\n\n"
        except anthropic.APIError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # Persist the assistant turn only if we streamed successfully.
        full_text = "".join(assistant_text_parts)
        if full_text:
            history.append({"role": "assistant", "content": full_text})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable buffering on reverse proxies
        },
    )


@app.post("/api/reset")
async def reset(body: dict) -> dict:
    """Clear conversation history for a session."""
    sid = body.get("session_id")
    if sid in _sessions:
        del _sessions[sid]
    return {"ok": True}


# Static assets
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


def run(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Entrypoint for the `python -m resale voice` CLI command."""
    import uvicorn

    print(f"🎙  Voice copilot starting on http://{host}:{port}")
    print(f"   Model: {MODEL}")
    print(f"   Open http://localhost:{port} on this machine,")
    print(f"   or http://<this-machine-LAN-ip>:{port} on your phone (same WiFi).")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
