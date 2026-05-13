"""FastAPI server for voice-to-voice with Claude + persistent memory.

- `GET /` serves the web UI (push-to-talk, browser Web Speech for STT/TTS)
- `POST /api/chat` streams Claude's reply as SSE, including tool events
- In-memory conversation per session_id (capped at HISTORY_CAP turns)
- Persistent memory via MemoryStore (.memory/) — Claude pulls via tools
- System prompt + core profile cached per request (~90% off after first turn)
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

from ..memory import MemoryStore
from ..memory.tools import TOOL_DEFINITIONS, execute_tool

load_dotenv()

MODEL = os.environ.get("RESALE_VOICE_MODEL", "claude-opus-4-6")
MAX_TOKENS = int(os.environ.get("RESALE_VOICE_MAX_TOKENS", "1200"))
# History sliding window: keep last N message PAIRS (user+assistant)
# At ~50 tokens per voice turn, 20 pairs ≈ 2K tokens — stays cheap.
HISTORY_CAP_PAIRS = int(os.environ.get("RESALE_HISTORY_PAIRS", "20"))
# Hard ceiling on tool-use loop iterations per user turn (safety)
MAX_TOOL_ITERATIONS = 8

VOICE_SYSTEM_PROMPT = """You are the voice copilot for a one-person junk-hauling + resale operation. The operator is talking to you over voice — your replies will be read aloud by TTS.

# Voice-mode rules (NON-NEGOTIABLE)

- **Keep replies SHORT.** 1-3 sentences for routine answers. Nobody wants a paragraph read aloud.
- **No markdown, no bullet lists, no headers.** Plain spoken English.
- **No preamble.** Skip "Great question!" / "Let me think about that". Just answer.
- **Use contractions.** "It's", "you'd", "won't". Write like you talk.
- **Numbers spelled out for voice when natural.** "Eighty bucks", "a hundred and ten dollars". Use numerals for model numbers, years, serials, IDs.
- If an answer is genuinely long (full listing copy, detailed strategy), say it'll be long and offer to put it in the dashboard/email instead of speaking it.

# Memory tools — USE LIBERALLY

You have persistent memory of this operator across all sessions. Four tools:

**capture** — Save anything worth remembering. Use it AGGRESSIVELY:
- Operator says "remember that...", "note that...", "I should...", "remind me..." → capture
- Operator mentions a follow-up ("I'll call Dave tomorrow"), a lead ("the Anderson estate has tools"), a thing to try, a price they learned, a contact → capture
- Operator describes an item they'll process later → capture as kind=item
- DO NOT ask permission first. Capture, then briefly acknowledge ("Got it.", "Saved.", "On your list.")
- Better to over-capture than to lose a thought. The operator has ADHD — they spin up ideas fast. Your job is to keep none of them dropped.

**recall** — Search memory when the operator references the past:
- "That vase I told you about last week" → recall("vase")
- "What did we say about Whatnot pricing for Funko Pops" → recall("Whatnot Funko pricing")
- ALSO use proactively when context would obviously help — don't bluff if memory has the answer.

**list_open** — When they ask "what's on my list", "what should I work on", "any open tasks":
- Call list_open and read the top items aloud, oldest first.

**complete** — When they say "mark that done", "killed it", "finished X":
- Call complete with the relevant id (from a previous list_open or recall).

# What you know about the operation

(See the always-loaded operator profile that follows for current context. The profile updates over time as the operation evolves.)

# Camera / photo analysis

When the operator sends photos alongside their voice message, they're showing you an item through their phone camera. This replaces their old Grok video workflow — no more copy/paste. Your job:

1. **IDENTIFY** — What is it? Brand, era, type. Read visible marks/labels carefully. If you see a maker's mark, call it out.
2. **QUICK VERBAL ASSESSMENT** — Condition + estimated price range + best marketplace. Keep it 2-3 sentences, they're standing in the shop.
3. **AUTO-CAPTURE** — Call `capture` with kind="item" including what you identified, price range, and condition. Don't ask permission, just save.
4. **OFFER NEXT STEP** — "Want me to generate a full listing?" or "Snap the bottom/marks for a better ID."

If you can't confidently identify it, say so and ask for specific photos: maker's marks, labels, bottom stamps. Better to say "I need to see the bottom" than to guess wrong.

Multiple photos of the same item may arrive — analyze them together as different angles of one item, unless the operator says otherwise.

# Tone

Confident, blue-collar-friendly, no jargon unless they use it first. You run with them; you don't work for them. Push back on bad ideas — don't be a sycophant."""


app = FastAPI(title="Resale Voice Copilot")

# In-memory conversation store: session_id -> list of message dicts
# (assistant content stored as the FULL block list to preserve tool_use blocks
# and any thinking blocks for cache integrity.)
_sessions: Dict[str, List[dict]] = {}

# Shared singletons
_client = anthropic.Anthropic()
_store = MemoryStore()


class ChatImage(BaseModel):
    data: str
    media_type: str = "image/jpeg"


class ChatRequest(BaseModel):
    session_id: str
    message: str
    images: List[ChatImage] = []


def _build_system() -> List[dict]:
    """System prompt + operator profile, cached together as a stable prefix."""
    core = _store.get_core()
    return [
        {"type": "text", "text": VOICE_SYSTEM_PROMPT},
        {
            "type": "text",
            "text": f"# Always-loaded operator profile\n\n{core}",
            "cache_control": {"type": "ephemeral"},
        },
    ]


def _trim_history(history: List[dict]) -> List[dict]:
    """Keep at most HISTORY_CAP_PAIRS user/assistant pairs.

    A "pair" can include intermediate tool-use rounds (assistant -> user with
    tool_results -> assistant ...). To keep this simple we count BACK from the
    end until we find HISTORY_CAP_PAIRS user messages, then drop everything
    before that point.
    """
    user_indices = [i for i, m in enumerate(history) if m["role"] == "user"]
    if len(user_indices) <= HISTORY_CAP_PAIRS:
        return history
    cut_at = user_indices[-HISTORY_CAP_PAIRS]
    return history[cut_at:]


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """Stream Claude's reply as SSE. Handles multi-iteration tool-use loops."""
    history = _sessions.setdefault(req.session_id, [])

    # Store TEXT-ONLY in history (keeps token cost low across turns).
    # Images are injected into the CURRENT API call only.
    history.append({"role": "user", "content": req.message})
    turn_images = req.images  # ephemeral, one-turn-only

    def event_stream():
        nonlocal history
        total_in = 0
        total_out = 0
        total_cache_read = 0
        total_cache_creation = 0

        try:
            for iteration in range(MAX_TOOL_ITERATIONS):
                history = _trim_history(history)
                _sessions[req.session_id] = history

                # Build messages; inject images into the LAST user message
                # for the current turn only (first iteration of the loop).
                api_messages = list(history)
                if turn_images and iteration == 0:
                    # Replace last user message with image+text content blocks
                    last = api_messages[-1]
                    content_blocks: List[dict] = []
                    for img in turn_images:
                        content_blocks.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": img.media_type,
                                    "data": img.data,
                                },
                            }
                        )
                    content_blocks.append(
                        {"type": "text", "text": last["content"]}
                    )
                    api_messages[-1] = {"role": "user", "content": content_blocks}

                with _client.messages.stream(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=_build_system(),
                    tools=TOOL_DEFINITIONS,
                    messages=api_messages,
                ) as stream:
                    pending_tool_name = None
                    for event in stream:
                        if event.type == "content_block_start":
                            block = event.content_block
                            if block.type == "tool_use":
                                pending_tool_name = block.name
                                yield _sse({"tool_start": {"name": block.name}})
                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if delta.type == "text_delta":
                                yield _sse({"delta": delta.text})
                            # input_json_delta also fires here; we don't surface
                            # tool args to the UI.
                        elif event.type == "content_block_stop":
                            pending_tool_name = None

                    final = stream.get_final_message()

                # Tally usage from this iteration
                u = final.usage
                total_in += u.input_tokens
                total_out += u.output_tokens
                total_cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
                total_cache_creation += (
                    getattr(u, "cache_creation_input_tokens", 0) or 0
                )

                # Append the FULL assistant turn (preserves thinking + tool_use blocks)
                history.append({"role": "assistant", "content": final.content})

                if final.stop_reason == "end_turn":
                    break

                # Extract tool_use blocks; if none, we're done
                tool_uses = [b for b in final.content if b.type == "tool_use"]
                if not tool_uses:
                    break

                # Execute each tool, build tool_result blocks
                tool_results = []
                for tu in tool_uses:
                    result = execute_tool(tu.name, dict(tu.input), _store)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tu.id,
                            "content": result,
                        }
                    )
                    yield _sse({"tool_done": {"name": tu.name}})

                history.append({"role": "user", "content": tool_results})
            else:
                # Loop exhausted MAX_TOOL_ITERATIONS — bail
                yield _sse(
                    {
                        "error": (
                            "Tool-use loop hit safety limit. "
                            "Try a fresh question or simpler ask."
                        )
                    }
                )

            yield _sse(
                {
                    "done": True,
                    "usage": {
                        "input_tokens": total_in,
                        "output_tokens": total_out,
                        "cache_read": total_cache_read,
                        "cache_creation": total_cache_creation,
                    },
                }
            )

        except anthropic.APIError as e:
            yield _sse({"error": f"API error: {e}"})
        except Exception as e:
            yield _sse({"error": f"{type(e).__name__}: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/reset")
async def reset(body: dict) -> dict:
    """Clear conversation history for a session. Memory store is untouched."""
    sid = body.get("session_id")
    if sid in _sessions:
        del _sessions[sid]
    return {"ok": True}


@app.get("/api/memory/stats")
async def memory_stats() -> dict:
    return _store.stats()


# Static assets
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(_STATIC_DIR / "index.html")


def run(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Entrypoint for the `python -m resale voice` CLI command."""
    import uvicorn

    stats = _store.stats()
    print(f"🎙  Voice copilot starting on http://{host}:{port}")
    print(f"   Model: {MODEL}")
    print(f"   Memory: {stats['total']} captures ({stats['by_kind']})")
    print(f"   Open tasks: {stats['by_status'].get('open', 0)}")
    print(f"   Open this in a browser. On phone: http://<LAN-ip>:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run()
