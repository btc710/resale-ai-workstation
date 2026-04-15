"""CLI: photos → listings.

Usage:
    # Single item
    python -m resale list photos/item-001/

    # Single item with operator notes
    python -m resale list photos/item-001/ --notes "found in barn, serial on bottom = XYZ123"

    # Batch process every subfolder under photos/
    python -m resale batch photos/

    # Preview without API call (schema check)
    python -m resale schema
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from .cluster import cluster_folder
from .export import append_to_csv, listing_to_markdown
from .lister import list_item
from .prompts import Listing

load_dotenv()

LISTINGS_DIR = Path("listings")
CSV_PATH = LISTINGS_DIR / "listings.csv"


def _slug(path: Path) -> str:
    """Folder name used as SKU."""
    return path.name


def _read_notes(folder: Path) -> str:
    """Pick up notes.txt / notes.md in an item folder, if present."""
    for name in ("notes.txt", "notes.md"):
        p = folder / name
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace").strip()
    return ""


def _write_outputs(sku: str, folder: Path, listing: Listing) -> Path:
    """Write per-item JSON + Markdown, append to master CSV. Returns output dir."""
    out_dir = LISTINGS_DIR / sku
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "listing.json").write_text(
        listing.model_dump_json(indent=2), encoding="utf-8"
    )
    (out_dir / "listing.md").write_text(
        listing_to_markdown(listing, sku), encoding="utf-8"
    )

    append_to_csv(CSV_PATH, sku, listing, photo_folder=str(folder))
    return out_dir


def _print_summary(sku: str, listing: Listing, elapsed: float) -> None:
    price_band = f"${listing.price_range_low_usd:.0f}–${listing.price_range_high_usd:.0f}"
    flag = " ⚠️ needs research" if listing.needs_research else ""
    print(
        f"  ✓ {sku}: {listing.title[:60]}{'…' if len(listing.title) > 60 else ''}\n"
        f"    ${listing.suggested_price_usd:.2f} ({price_band}) → "
        f"{listing.target_marketplace.value} [{listing.listing_priority.value}] "
        f"({elapsed:.1f}s){flag}"
    )


def cmd_list(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    sku = _slug(folder)
    print(f"📸 Analyzing {sku}...")
    # Priority: explicit --notes flag overrides notes.txt, otherwise merge.
    notes = args.notes or _read_notes(folder)
    t0 = time.time()
    try:
        listing = list_item(folder, item_notes=notes)
    except FileNotFoundError as e:
        print(f"  ✗ {e}", file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    out_dir = _write_outputs(sku, folder, listing)
    _print_summary(sku, listing, elapsed)
    print(f"  → {out_dir}/ + {CSV_PATH}")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    root = Path(args.folder)
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    item_folders = sorted(
        p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    if not item_folders:
        print(f"No item folders in {root}/", file=sys.stderr)
        return 1

    print(f"📦 Batch: {len(item_folders)} items\n")

    successes = 0
    failures = []

    for folder in item_folders:
        sku = _slug(folder)
        notes = _read_notes(folder)
        t0 = time.time()
        try:
            listing = list_item(folder, item_notes=notes)
        except Exception as e:
            print(f"  ✗ {sku}: {type(e).__name__}: {e}", file=sys.stderr)
            failures.append((sku, str(e)))
            continue

        elapsed = time.time() - t0
        _write_outputs(sku, folder, listing)
        _print_summary(sku, listing, elapsed)
        successes += 1

    print(f"\n✓ {successes}/{len(item_folders)} items listed")
    if failures:
        print(f"✗ {len(failures)} failures:")
        for sku, err in failures:
            print(f"   - {sku}: {err}")
    print(f"\nMaster CSV: {CSV_PATH}")
    return 0 if not failures else 1


def cmd_cluster(args: argparse.Namespace) -> int:
    """Group loose photos into per-item folders by timestamp gaps."""
    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_dir():
        print(f"Not a directory: {raw_dir}", file=sys.stderr)
        return 1

    out_parent = Path(args.out) if args.out else Path("photos")
    mode = "DRY RUN" if args.dry_run else "CLUSTERING"
    print(f"🔍 {mode} — gap threshold: {args.gap}s\n")

    created = cluster_folder(
        raw_dir,
        out_parent,
        gap_seconds=args.gap,
        dry_run=args.dry_run,
        start_index=args.start,
    )

    print(f"\n✓ {len(created)} item folder{'s' if len(created) != 1 else ''} "
          f"{'planned' if args.dry_run else 'created'}")
    if not args.dry_run and created:
        print(f"\nNext: python -m resale batch {out_parent}/")
    return 0


def cmd_inventory(_args: argparse.Namespace) -> int:
    """Scan listings/*/listing.json for a quick status overview."""
    if not LISTINGS_DIR.is_dir():
        print("No listings/ directory yet.")
        return 0

    rows = []
    total = 0.0
    needs_research = 0
    by_priority = {"high": 0, "medium": 0, "low": 0}
    by_marketplace: dict[str, int] = {}

    for item_dir in sorted(LISTINGS_DIR.iterdir()):
        if not item_dir.is_dir():
            continue
        listing_file = item_dir / "listing.json"
        if not listing_file.exists():
            continue
        try:
            listing = Listing.model_validate_json(listing_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append((item_dir.name, listing))
        total += listing.suggested_price_usd
        if listing.needs_research:
            needs_research += 1
        by_priority[listing.listing_priority.value] = by_priority.get(listing.listing_priority.value, 0) + 1
        mp = listing.target_marketplace.value
        by_marketplace[mp] = by_marketplace.get(mp, 0) + 1

    if not rows:
        print("No listings yet. Run `python -m resale list` or `batch` first.")
        return 0

    print(f"📊 Inventory: {len(rows)} items, ${total:,.2f} total list value\n")
    print(f"   Priority:   high={by_priority.get('high', 0)}  medium={by_priority.get('medium', 0)}  low={by_priority.get('low', 0)}")
    print(f"   Marketplace: " + "  ".join(f"{k}={v}" for k, v in sorted(by_marketplace.items(), key=lambda x: -x[1])))
    if needs_research:
        print(f"   ⚠️  {needs_research} items flagged needs_research")
    print()

    # Top 10 by price
    rows.sort(key=lambda r: -r[1].suggested_price_usd)
    print("Top 10 by suggested price:")
    for sku, listing in rows[:10]:
        flag = " ⚠️" if listing.needs_research else ""
        print(f"  ${listing.suggested_price_usd:>7.2f}  [{listing.listing_priority.value:6s}]  {sku}  →  {listing.title[:55]}{flag}")

    return 0


def cmd_voice(args: argparse.Namespace) -> int:
    """Start the voice-to-voice web UI."""
    try:
        from .voice.server import run as run_voice
    except ImportError as e:
        print(
            f"Voice deps not installed ({e}). Run: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1
    run_voice(host=args.host, port=args.port)
    return 0


def cmd_schema(_args: argparse.Namespace) -> int:
    """Print the Listing JSON schema — useful for verifying structure."""
    print(json.dumps(Listing.model_json_schema(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resale", description="Photos → marketplace listings, powered by Claude."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="Generate listing for one item folder.")
    p_list.add_argument("folder", help="Path to folder of photos (one item).")
    p_list.add_argument("--notes", help="Operator notes to pass to the model.")
    p_list.set_defaults(func=cmd_list)

    p_batch = sub.add_parser("batch", help="Generate listings for every subfolder.")
    p_batch.add_argument("folder", help="Parent folder containing item subfolders.")
    p_batch.set_defaults(func=cmd_batch)

    p_cluster = sub.add_parser(
        "cluster",
        help="Group loose photos into per-item folders by EXIF timestamp gaps.",
    )
    p_cluster.add_argument("raw_dir", help="Folder containing loose photos (phone dump).")
    p_cluster.add_argument(
        "--out", help="Parent folder for item subfolders (default: photos/)."
    )
    p_cluster.add_argument(
        "--gap", type=int, default=45,
        help="Seconds between items that separate clusters (default: 45).",
    )
    p_cluster.add_argument(
        "--start", type=int, default=1, help="First item number (default: 1)."
    )
    p_cluster.add_argument(
        "--dry-run", action="store_true", help="Preview grouping without moving files."
    )
    p_cluster.set_defaults(func=cmd_cluster)

    p_inv = sub.add_parser("inventory", help="Summary of all generated listings.")
    p_inv.set_defaults(func=cmd_inventory)

    p_voice = sub.add_parser(
        "voice", help="Start the voice-to-voice web UI (browser STT/TTS + Claude)."
    )
    p_voice.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0).")
    p_voice.add_argument("--port", type=int, default=8765, help="Port (default: 8765).")
    p_voice.set_defaults(func=cmd_voice)

    p_schema = sub.add_parser("schema", help="Print the Listing JSON schema.")
    p_schema.set_defaults(func=cmd_schema)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
