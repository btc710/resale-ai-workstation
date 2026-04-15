"""Cluster loose photos (one big folder) into per-item subfolders.

Strategy: read each photo's EXIF `DateTimeOriginal`, fall back to file mtime.
Sort by timestamp. Items are separated by gaps >= `gap_seconds` (default 45s).
Photos within a gap get grouped into a single item folder.

Optional operator voice-memo / text notes: any `*.txt` / `*.md` in the raw
folder is assigned to the nearest-by-timestamp item folder as `notes.txt`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from PIL import ExifTags, Image

from .lister import IMAGE_EXTS

# EXIF tag IDs (stable numeric constants, no need to look them up by name)
_DATETIME_ORIGINAL = 36867  # 'DateTimeOriginal'
_DATETIME = 306             # fallback 'DateTime'

NOTE_EXTS = {".txt", ".md"}


@dataclass
class PhotoRecord:
    path: Path
    ts: datetime


def _exif_timestamp(path: Path) -> Optional[datetime]:
    """Extract EXIF DateTimeOriginal. Returns None if missing/unparseable."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            raw = exif.get(_DATETIME_ORIGINAL) or exif.get(_DATETIME)
            if not raw:
                # EXIF has a sub-IFD for photo-specific tags (DateTimeOriginal
                # often lives there). Walk into it.
                for tag_id, val in exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id)
                    if tag_name == "ExifOffset":
                        sub = exif.get_ifd(tag_id)
                        raw = sub.get(_DATETIME_ORIGINAL) or sub.get(_DATETIME)
                        break
            if not raw:
                return None
            # EXIF format: "YYYY:MM:DD HH:MM:SS"
            return datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def _photo_timestamp(path: Path) -> datetime:
    """Best timestamp: EXIF DateTimeOriginal, fallback to file mtime."""
    ts = _exif_timestamp(path)
    if ts is not None:
        return ts
    return datetime.fromtimestamp(path.stat().st_mtime)


def _collect_photos(raw_dir: Path) -> List[PhotoRecord]:
    records = [
        PhotoRecord(p, _photo_timestamp(p))
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    records.sort(key=lambda r: r.ts)
    return records


def _cluster(records: List[PhotoRecord], gap_seconds: int) -> List[List[PhotoRecord]]:
    """Group records into clusters separated by gaps >= gap_seconds."""
    if not records:
        return []
    groups: List[List[PhotoRecord]] = [[records[0]]]
    for prev, curr in zip(records, records[1:]):
        gap = (curr.ts - prev.ts).total_seconds()
        if gap >= gap_seconds:
            groups.append([curr])
        else:
            groups[-1].append(curr)
    return groups


def _item_folder_name(index: int, first_ts: datetime) -> str:
    """Folder naming: YYYY-MM-DD-NNN, sortable + unique."""
    return f"{first_ts.strftime('%Y-%m-%d')}-{index:03d}"


def _find_notes_for_item(
    notes: Iterable[Path], item_window_start: datetime, item_window_end: datetime
) -> List[Path]:
    """Any text note whose mtime falls inside the item's time window."""
    result = []
    for note in notes:
        mtime = datetime.fromtimestamp(note.stat().st_mtime)
        if item_window_start <= mtime <= item_window_end:
            result.append(note)
    return result


def cluster_folder(
    raw_dir: Path,
    out_parent: Path,
    *,
    gap_seconds: int = 45,
    dry_run: bool = False,
    start_index: int = 1,
) -> List[Path]:
    """Cluster loose photos in `raw_dir` into item subfolders under `out_parent`.

    Args:
        raw_dir: Folder with loose photos (phone dump).
        out_parent: Parent folder for item subfolders (usually `photos/`).
        gap_seconds: Time gap that separates two items. Default 45s.
        dry_run: Don't move files, just report the plan.
        start_index: First item number (so you can resume a numbering scheme).

    Returns:
        List of created item folder paths.
    """
    raw_dir = Path(raw_dir)
    out_parent = Path(out_parent)

    records = _collect_photos(raw_dir)
    if not records:
        return []

    # Collect text notes (operator voice-memo transcripts, scratchpad)
    notes = [
        p for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in NOTE_EXTS
    ]

    clusters = _cluster(records, gap_seconds)
    created: List[Path] = []

    # Number items with shop-walk-wide index so a batch over many days stays unique.
    # If you're shopping in a single day the prefix (YYYY-MM-DD) handles uniqueness
    # and NNN resets daily via _item_folder_name. For multi-day runs, pass start_index.
    for i, cluster in enumerate(clusters, start=start_index):
        first_ts = cluster[0].ts
        last_ts = cluster[-1].ts
        item_dir = out_parent / _item_folder_name(i, first_ts)
        created.append(item_dir)

        # Extend the note-match window 60s beyond the last photo — voice memos
        # are often recorded right after shooting the item.
        from datetime import timedelta
        note_window_start = first_ts - timedelta(seconds=30)
        note_window_end = last_ts + timedelta(seconds=90)
        matched_notes = _find_notes_for_item(notes, note_window_start, note_window_end)

        photo_count = len(cluster)
        note_count = len(matched_notes)
        span = (last_ts - first_ts).total_seconds()
        print(
            f"  📦 {item_dir.name}: {photo_count} photos over {span:.0f}s"
            f"{f' + {note_count} note' if note_count == 1 else f' + {note_count} notes' if note_count else ''}"
        )

        if dry_run:
            for rec in cluster:
                print(f"      {rec.path.name}  ({rec.ts.strftime('%H:%M:%S')})")
            continue

        item_dir.mkdir(parents=True, exist_ok=True)

        # Move photos into the item folder, keeping original filenames so EXIF
        # stays intact and the operator can trace back to the raw shot.
        for rec in cluster:
            dest = item_dir / rec.path.name
            if dest.exists():
                # Collision-safe: prefix with timestamp
                dest = item_dir / f"{rec.ts.strftime('%H%M%S')}-{rec.path.name}"
            rec.path.rename(dest)

        # Concatenate all matched notes into a single notes.txt
        if matched_notes:
            note_body_parts = []
            for note in matched_notes:
                note_body_parts.append(
                    f"--- {note.name} ({datetime.fromtimestamp(note.stat().st_mtime).isoformat()}) ---"
                )
                note_body_parts.append(note.read_text(encoding="utf-8", errors="replace").strip())
                note_body_parts.append("")
            (item_dir / "notes.txt").write_text("\n".join(note_body_parts), encoding="utf-8")
            for note in matched_notes:
                note.unlink()

    return created
