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

from .export import append_to_csv, listing_to_markdown
from .lister import list_item
from .prompts import Listing

load_dotenv()

LISTINGS_DIR = Path("listings")
CSV_PATH = LISTINGS_DIR / "listings.csv"


def _slug(path: Path) -> str:
    """Folder name used as SKU."""
    return path.name


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
    t0 = time.time()
    try:
        listing = list_item(folder, item_notes=args.notes or "")
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
        t0 = time.time()
        try:
            listing = list_item(folder)
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

    p_schema = sub.add_parser("schema", help="Print the Listing JSON schema.")
    p_schema.set_defaults(func=cmd_schema)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
