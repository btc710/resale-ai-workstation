"""Export listings to marketplace-friendly formats.

Current targets:
- crosslist.com bulk import CSV (generic multi-marketplace fields)
- Human-readable Markdown for review before posting
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .prompts import Listing


# CSV columns chosen to cover crosslist.com's bulk-upload + common marketplace fields.
# Crosslist accepts custom CSVs during import mapping — extra columns are fine.
CSV_COLUMNS = [
    "sku",
    "title",
    "brand",
    "category",
    "subcategory",
    "item_type",
    "condition",
    "condition_notes",
    "description",
    "key_features",
    "materials",
    "colors",
    "dimensions",
    "weight_lbs",
    "price",
    "price_min",
    "price_max",
    "keywords",
    "target_marketplace",
    "priority",
    "est_days_to_sell",
    "defects",
    "whatnot_hook",
    "needs_research",
    "research_notes",
    "pricing_rationale",
    "photo_folder",
]


def listing_to_row(sku: str, listing: Listing, photo_folder: str) -> dict:
    """Flatten a Listing into a CSV row dict."""
    return {
        "sku": sku,
        "title": listing.title,
        "brand": listing.brand or "",
        "category": listing.category,
        "subcategory": listing.subcategory,
        "item_type": listing.item_type,
        "condition": listing.condition.value,
        "condition_notes": listing.condition_notes,
        "description": listing.description,
        "key_features": " | ".join(listing.key_features),
        "materials": ", ".join(listing.materials),
        "colors": ", ".join(listing.colors),
        "dimensions": listing.dimensions_inches or "",
        "weight_lbs": listing.estimated_weight_lbs or "",
        "price": f"{listing.suggested_price_usd:.2f}",
        "price_min": f"{listing.price_range_low_usd:.2f}",
        "price_max": f"{listing.price_range_high_usd:.2f}",
        "keywords": ", ".join(listing.search_keywords),
        "target_marketplace": listing.target_marketplace.value,
        "priority": listing.listing_priority.value,
        "est_days_to_sell": listing.estimated_sell_through_days,
        "defects": listing.defects_or_issues or "",
        "whatnot_hook": listing.whatnot_hook or "",
        "needs_research": "YES" if listing.needs_research else "",
        "research_notes": listing.research_notes or "",
        "pricing_rationale": listing.pricing_rationale,
        "photo_folder": photo_folder,
    }


def append_to_csv(csv_path: Path, sku: str, listing: Listing, photo_folder: str) -> None:
    """Append a listing as a row. Writes header if file doesn't exist."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(listing_to_row(sku, listing, photo_folder))


def write_csv(csv_path: Path, rows: Iterable[tuple[str, Listing, str]]) -> None:
    """Write a fresh CSV from scratch."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for sku, listing, folder in rows:
            writer.writerow(listing_to_row(sku, listing, folder))


def listing_to_markdown(listing: Listing, sku: str) -> str:
    """Human-readable listing preview for review before publishing."""
    lines = [
        f"# {listing.title}",
        "",
        f"**SKU:** `{sku}`  ",
        f"**Price:** ${listing.suggested_price_usd:.2f}  (range ${listing.price_range_low_usd:.2f}–${listing.price_range_high_usd:.2f})  ",
        f"**Condition:** {listing.condition.value}  ",
        f"**Target:** {listing.target_marketplace.value}  |  **Priority:** {listing.listing_priority.value}  |  **Est. days to sell:** {listing.estimated_sell_through_days}",
        "",
    ]

    if listing.brand or listing.model_or_pattern:
        lines.append(f"**Brand/Model:** {listing.brand or '?'} / {listing.model_or_pattern or '?'}  ")

    lines.extend(
        [
            f"**Category:** {listing.category} > {listing.subcategory} ({listing.item_type})",
            "",
            "## Description",
            "",
            listing.description,
            "",
            "## Key features",
            "",
        ]
    )
    lines.extend(f"- {kf}" for kf in listing.key_features)

    lines.extend(
        [
            "",
            "## Condition notes",
            "",
            listing.condition_notes,
        ]
    )

    if listing.defects_or_issues:
        lines.extend(["", "### Defects / issues to disclose", "", listing.defects_or_issues])

    specs = []
    if listing.materials:
        specs.append(f"**Materials:** {', '.join(listing.materials)}")
    if listing.colors:
        specs.append(f"**Colors:** {', '.join(listing.colors)}")
    if listing.dimensions_inches:
        specs.append(f"**Dimensions:** {listing.dimensions_inches}")
    if listing.estimated_weight_lbs:
        specs.append(f"**Est. weight:** {listing.estimated_weight_lbs} lbs")
    if specs:
        lines.extend(["", "## Specs", "", *specs])

    lines.extend(
        [
            "",
            "## Pricing rationale",
            "",
            listing.pricing_rationale,
            "",
            "## Search keywords",
            "",
            ", ".join(listing.search_keywords),
        ]
    )

    if listing.whatnot_hook:
        lines.extend(["", "## Whatnot stream hook", "", f"> {listing.whatnot_hook}"])

    if listing.needs_research:
        lines.extend(
            [
                "",
                "## ⚠️  Needs research before listing",
                "",
                listing.research_notes or "Flagged for further investigation.",
            ]
        )

    return "\n".join(lines) + "\n"
