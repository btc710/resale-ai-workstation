"""Core listing generator: folder of photos → structured Listing.

Uses Claude Opus 4.6 vision with:
- Prompt caching on the system prompt (per-item cost drops ~90% after item #1)
- Structured outputs via Pydantic for guaranteed schema conformance
- Adaptive thinking for better reasoning on trickier identification calls
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import List, Tuple

import anthropic
from PIL import Image

from .prompts import Listing, SYSTEM_PROMPT

MODEL = "claude-opus-4-6"
MAX_IMAGE_DIM = 1568  # Anthropic's recommended max edge for vision cost/quality balance
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _resize_if_needed(img_path: Path) -> Tuple[bytes, str]:
    """Load and resize image if larger than MAX_IMAGE_DIM. Returns (bytes, media_type)."""
    media_type, _ = mimetypes.guess_type(str(img_path))
    if media_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        media_type = "image/jpeg"

    with Image.open(img_path) as img:
        # Normalize mode for JPEG compatibility
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
            media_type = "image/jpeg"

        if max(img.size) > MAX_IMAGE_DIM:
            img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.LANCZOS)

        from io import BytesIO

        buf = BytesIO()
        fmt = "JPEG" if media_type == "image/jpeg" else media_type.split("/")[1].upper()
        save_kwargs = {"quality": 88, "optimize": True} if fmt == "JPEG" else {}
        img.save(buf, format=fmt, **save_kwargs)
        return buf.getvalue(), media_type


def _photos_in(folder: Path) -> List[Path]:
    """All image files in folder, sorted by name."""
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def _build_image_blocks(photos: List[Path]) -> List[dict]:
    """Convert photo paths to Anthropic vision content blocks."""
    blocks = []
    for i, p in enumerate(photos, start=1):
        data, media_type = _resize_if_needed(p)
        b64 = base64.standard_b64encode(data).decode("utf-8")
        blocks.append({"type": "text", "text": f"Photo {i} ({p.name}):"})
        blocks.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            }
        )
    return blocks


def list_item(
    folder: Path,
    *,
    item_notes: str = "",
    client: anthropic.Anthropic | None = None,
) -> Listing:
    """Generate a Listing from a folder of photos of a single item.

    Args:
        folder: Path to a folder containing photos of ONE item.
        item_notes: Optional operator notes — "found in barn, smells musty",
                    "serial number on bottom reads XYZ", etc. Goes to the model.
        client: Optional Anthropic client (creates default if None).

    Returns:
        A validated Listing object.

    Raises:
        FileNotFoundError: If folder doesn't exist or has no photos.
        anthropic.APIError: On API failure.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"Not a directory: {folder}")

    photos = _photos_in(folder)
    if not photos:
        raise FileNotFoundError(f"No photos found in {folder} (looking for {sorted(IMAGE_EXTS)})")

    if client is None:
        client = anthropic.Anthropic()

    user_content: List[dict] = []

    # Item context header
    context_header = f"# Item: {folder.name}\n\nPhotos of one item pulled from a junk job. Analyze all photos together — they show the same item from multiple angles."
    if item_notes:
        context_header += f"\n\n## Operator notes\n\n{item_notes}"

    user_content.append({"type": "text", "text": context_header})
    user_content.extend(_build_image_blocks(photos))
    user_content.append(
        {
            "type": "text",
            "text": "Generate the complete Listing. Be decisive — this is the listing the operator will actually post.",
        }
    )

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": Listing},
    )

    listing = response.parsed_output
    if listing is None:
        raise RuntimeError(
            f"Model returned unparseable output for {folder.name}. "
            f"Stop reason: {response.stop_reason}"
        )

    return listing


def cache_stats(response) -> dict:
    """Extract cache hit info from an API response for cost telemetry."""
    u = response.usage
    return {
        "input_tokens": u.input_tokens,
        "cache_creation": getattr(u, "cache_creation_input_tokens", 0),
        "cache_read": getattr(u, "cache_read_input_tokens", 0),
        "output_tokens": u.output_tokens,
    }
