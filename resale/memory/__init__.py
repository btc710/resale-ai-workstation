"""Persistent memory for the resale operator.

Design goals:
- Append-only JSONL files for fast writes + simple recovery + zero corruption risk
- Recall is a TOOL Claude calls on demand, not bulk-injected per turn
- Core profile (`core.md`) is the only memory always-loaded into context
- Token cost stays small even as memory grows to thousands of entries
"""

from .store import MemoryStore  # noqa: F401
