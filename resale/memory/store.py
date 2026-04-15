"""Persistent memory store.

Two append-only files for durability and simplicity:
  .memory/captures.jsonl   — every capture (note/idea/task/item/fact)
  .memory/statuses.jsonl   — status changes (later events override earlier)

Plus:
  .memory/core.md          — operator profile, always-loaded into system prompt

Recall is keyword-based with a recency boost. Good enough for thousands of
entries; we can swap in embeddings later without changing the API.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

DEFAULT_CORE = """# Operator profile

(This file is auto-loaded into every voice/chat session as your AI partner's "always know" context. Edit freely. Keep it under ~500 tokens — short and high-signal.)

## Business
- One-person junk-hauling + resale vertical
- Cost basis on items: $0 (alternative is dump)
- Primary marketplaces: eBay, Facebook Marketplace, Whatnot, Mercari
- Cross-posts via crosslist.com

## How I work
- ADHD-leaning. Prefer short, decisive answers. No filler.
- Capture ideas/tasks aggressively — review later.
- Voice copilot mode is for hands-busy moments; text/CLI for deep work.

## Current focus
(Update this as priorities shift.)
"""


VALID_KINDS = {"note", "idea", "task", "item", "fact"}


@dataclass
class Capture:
    id: str
    ts: str  # ISO 8601 UTC
    kind: str
    text: str
    tags: List[str] = field(default_factory=list)
    status: str = "open"  # open, in_progress, done, archived

    def to_jsonl(self) -> str:
        d = asdict(self)
        # Keep the file lean — drop status (it lives in statuses.jsonl)
        d.pop("status", None)
        return json.dumps(d, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "Capture":
        return cls(
            id=d["id"],
            ts=d["ts"],
            kind=d["kind"],
            text=d["text"],
            tags=list(d.get("tags") or []),
            status="open",
        )


def _new_id() -> str:
    return "cap_" + secrets.token_urlsafe(8).rstrip("_-").lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> Iterable[dict]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Skip corrupt lines rather than failing — append-only files
                # tolerate occasional bad rows from interrupted writes.
                continue


def _append_jsonl(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


# --- recall scoring -----------------------------------------------------------


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(s: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s)]


def _score(capture: Capture, query_tokens: List[str], now: datetime) -> float:
    """Higher = more relevant. Combines term hits, tag hits, and recency."""
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(capture.text)
    tag_tokens = [t.lower() for t in capture.tags]

    # Term hits in text
    text_hits = sum(1 for q in query_tokens if q in text_tokens)
    # Term hits in tags (worth 3x — tags are deliberate)
    tag_hits = 3 * sum(1 for q in query_tokens if q in tag_tokens)

    base = text_hits + tag_hits
    if base == 0:
        return 0.0

    # Recency boost: 0..0.3 added based on age in days
    try:
        age_days = (now - datetime.fromisoformat(capture.ts)).days
    except ValueError:
        age_days = 9999
    recency = max(0.0, 1.0 - min(age_days, 365) / 365.0) * 0.3

    return base + recency


# --- store --------------------------------------------------------------------


class MemoryStore:
    def __init__(self, root: Path | str = ".memory") -> None:
        self.root = Path(root)
        self.captures_path = self.root / "captures.jsonl"
        self.statuses_path = self.root / "statuses.jsonl"
        self.core_path = self.root / "core.md"
        self._ensure_init()

    def _ensure_init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.core_path.exists():
            self.core_path.write_text(DEFAULT_CORE, encoding="utf-8")

    # ---- core profile ----

    def get_core(self) -> str:
        return self.core_path.read_text(encoding="utf-8")

    def update_core(self, content: str) -> None:
        # Atomic write to avoid corruption mid-flight
        tmp = self.core_path.with_suffix(".md.tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(self.core_path)

    # ---- captures ----

    def capture(
        self, kind: str, text: str, tags: Optional[List[str]] = None
    ) -> Capture:
        if kind not in VALID_KINDS:
            raise ValueError(
                f"Invalid kind {kind!r}; expected one of {sorted(VALID_KINDS)}"
            )
        cap = Capture(
            id=_new_id(),
            ts=_now(),
            kind=kind,
            text=text.strip(),
            tags=list(tags or []),
        )
        _append_jsonl(self.captures_path, cap.to_jsonl())
        return cap

    def _all_captures(self) -> List[Capture]:
        captures = [Capture.from_dict(d) for d in _read_jsonl(self.captures_path)]

        # Apply latest status per id
        latest_status: dict[str, str] = {}
        for d in _read_jsonl(self.statuses_path):
            cid = d.get("id")
            st = d.get("status")
            if cid and st:
                latest_status[cid] = st
        for cap in captures:
            if cap.id in latest_status:
                cap.status = latest_status[cap.id]
        return captures

    def recent(
        self, n: int = 10, kind: Optional[str] = None, status: Optional[str] = None
    ) -> List[Capture]:
        items = self._all_captures()
        items.sort(key=lambda c: c.ts, reverse=True)
        out = []
        for c in items:
            if kind and c.kind != kind:
                continue
            if status and c.status != status:
                continue
            out.append(c)
            if len(out) >= n:
                break
        return out

    def recall(
        self,
        query: str,
        kind: Optional[str] = None,
        limit: int = 5,
    ) -> List[Capture]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        now = datetime.now(timezone.utc)
        scored: list[tuple[float, Capture]] = []
        for c in self._all_captures():
            if kind and c.kind != kind:
                continue
            s = _score(c, query_tokens, now)
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def list_open(self, kind: str = "task", limit: int = 20) -> List[Capture]:
        items = [
            c
            for c in self._all_captures()
            if c.kind == kind and c.status in ("open", "in_progress")
        ]
        items.sort(key=lambda c: c.ts)  # oldest first — surface stale items
        return items[:limit]

    def set_status(self, capture_id: str, status: str) -> bool:
        if status not in {"open", "in_progress", "done", "archived"}:
            raise ValueError(f"Invalid status {status!r}")
        # Verify the id exists (fast scan; could index later)
        ids = {c.id for c in self._all_captures()}
        if capture_id not in ids:
            return False
        _append_jsonl(
            self.statuses_path,
            json.dumps(
                {"id": capture_id, "ts": _now(), "status": status},
                separators=(",", ":"),
            ),
        )
        return True

    def get(self, capture_id: str) -> Optional[Capture]:
        for c in self._all_captures():
            if c.id == capture_id:
                return c
        return None

    def stats(self) -> dict:
        captures = self._all_captures()
        by_kind: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for c in captures:
            by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
            by_status[c.status] = by_status.get(c.status, 0) + 1
        return {
            "total": len(captures),
            "by_kind": by_kind,
            "by_status": by_status,
        }


def format_capture_brief(c: Capture) -> str:
    """One-line representation suitable for tool results / CLI output."""
    tags = f" [{', '.join(c.tags)}]" if c.tags else ""
    status = "" if c.status == "open" else f" ({c.status})"
    # Trim long text so tool results stay token-cheap
    text = c.text if len(c.text) <= 240 else c.text[:237] + "..."
    return f"{c.id} · {c.kind} · {c.ts[:10]}{tags}{status} — {text}"
