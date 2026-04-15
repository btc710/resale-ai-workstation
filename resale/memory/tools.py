"""Anthropic tool definitions for memory access + the dispatcher.

These tools let Claude pull memory on demand instead of bulk-loading it.
That keeps per-turn token cost low while making the operator's full history
available when relevant.
"""

from __future__ import annotations

from typing import Any

from .store import VALID_KINDS, MemoryStore, format_capture_brief

TOOL_DEFINITIONS = [
    {
        "name": "capture",
        "description": (
            "Save a thought, idea, task, item fact, or learned fact to the "
            "operator's persistent memory. Use this WHENEVER the operator says "
            "anything worth remembering — explicit ('remember that...', 'add to "
            "my list', 'note for later') OR implicit (mentions a follow-up, a "
            "lead, a thing to try, a preference). DO NOT ask permission first; "
            "capture immediately and acknowledge briefly. Be liberal — better "
            "to over-capture than under."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        "The content to save. Make it self-contained — readable "
                        "weeks later without surrounding conversation. Include "
                        "names, numbers, locations, deadlines if mentioned."
                    ),
                },
                "kind": {
                    "type": "string",
                    "enum": sorted(VALID_KINDS),
                    "description": (
                        "task: something to do | idea: thing to try/explore | "
                        "item: facts about a specific resale item | fact: "
                        "general knowledge learned (pricing, contacts, processes) "
                        "| note: catch-all for thoughts that don't fit above"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional short tags for retrieval, e.g. ['whatnot', "
                        "'pricing', 'estate-cleanout', 'pyrex']. Lowercase, "
                        "hyphenated. Skip if nothing obvious."
                    ),
                },
            },
            "required": ["text", "kind"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Search the operator's memory for past captures relevant to a "
            "query. Use this when the operator references something earlier "
            "('that vase I mentioned', 'what did we say about Whatnot pricing'), "
            "asks for a price/comp/fact you don't currently have in context, or "
            "when domain context would clearly improve your answer. Returns up "
            "to `limit` matches sorted by relevance + recency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords or short phrase. Specific words work best.",
                },
                "kind": {
                    "type": "string",
                    "enum": sorted(VALID_KINDS) + ["any"],
                    "description": "Filter to one kind, or 'any' for all. Default 'any'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return. Default 5, max 20.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_open",
        "description": (
            "List the operator's open tasks or unreviewed ideas, oldest first "
            "(stale stuff bubbles up). Use when they ask 'what's on my list', "
            "'what should I work on', 'any open tasks', etc. Returns up to "
            "`limit` items."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["task", "idea"],
                    "description": "task (default) or idea.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results. Default 10, max 50.",
                },
            },
        },
    },
    {
        "name": "complete",
        "description": (
            "Mark a captured task or idea as done. The operator will say things "
            "like 'mark that done', 'finished the X task', or 'kill that idea'. "
            "Use the id from a previous recall/list_open result."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The capture id (e.g. cap_abc123).",
                },
            },
            "required": ["id"],
        },
    },
]


def execute_tool(name: str, arguments: dict[str, Any], store: MemoryStore) -> str:
    """Run a tool and return the string result Claude will see."""
    try:
        if name == "capture":
            text = arguments["text"]
            kind = arguments["kind"]
            tags = arguments.get("tags") or []
            cap = store.capture(kind=kind, text=text, tags=tags)
            return f"Captured: {cap.id} ({cap.kind}). Acknowledge briefly to the operator."

        if name == "recall":
            query = arguments["query"]
            kind = arguments.get("kind") or "any"
            limit = min(int(arguments.get("limit") or 5), 20)
            results = store.recall(
                query=query, kind=None if kind == "any" else kind, limit=limit
            )
            if not results:
                return f"No matches for {query!r}."
            lines = [f"{len(results)} match{'es' if len(results) != 1 else ''} for {query!r}:"]
            lines.extend(format_capture_brief(c) for c in results)
            return "\n".join(lines)

        if name == "list_open":
            kind = arguments.get("kind") or "task"
            limit = min(int(arguments.get("limit") or 10), 50)
            items = store.list_open(kind=kind, limit=limit)
            if not items:
                return f"No open {kind}s."
            lines = [f"{len(items)} open {kind}{'s' if len(items) != 1 else ''} (oldest first):"]
            lines.extend(format_capture_brief(c) for c in items)
            return "\n".join(lines)

        if name == "complete":
            cid = arguments["id"]
            ok = store.set_status(cid, "done")
            if not ok:
                return f"No capture with id {cid!r}."
            return f"Marked {cid} as done."

        return f"Unknown tool {name!r}."

    except Exception as e:
        return f"Tool error ({type(e).__name__}): {e}"
