"""System prompt + structured listing schema.

The system prompt is intentionally frozen — no timestamps, no per-item interpolation —
so it caches cleanly via `cache_control`. Per-item context goes in the user message.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Condition(str, Enum):
    NEW = "New"
    LIKE_NEW = "Like New"
    EXCELLENT = "Excellent"
    VERY_GOOD = "Very Good"
    GOOD = "Good"
    ACCEPTABLE = "Acceptable"
    FOR_PARTS = "For Parts or Not Working"


class Marketplace(str, Enum):
    EBAY = "ebay"
    WHATNOT = "whatnot"
    FB_MARKETPLACE = "facebook_marketplace"
    MERCARI = "mercari"
    POSHMARK = "poshmark"
    DEPOP = "depop"
    LOCAL_PICKUP = "local_pickup"
    DONATE = "donate"
    DUMP = "dump"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Listing(BaseModel):
    """A complete marketplace listing, ready to post."""

    # Identification
    title: str = Field(
        ...,
        max_length=80,
        description="eBay-optimized title, max 80 chars. Front-load keywords buyers search.",
    )
    brand: Optional[str] = Field(None, description="Brand/manufacturer if identifiable, else null.")
    model_or_pattern: Optional[str] = Field(
        None, description="Specific model number, pattern name, or edition, if visible."
    )

    # Categorization
    category: str = Field(..., description="Broad category, e.g. 'Electronics', 'Home Decor', 'Clothing'.")
    subcategory: str = Field(..., description="Specific subcategory, e.g. 'Vintage Cameras', 'Ceramic Vases'.")
    item_type: str = Field(..., description="What the item actually is, plain English.")

    # Condition (be honest — returns kill margins)
    condition: Condition
    condition_notes: str = Field(
        ...,
        description="Specific condition details a buyer needs. Call out flaws, wear, missing parts. Honest sells.",
    )
    defects_or_issues: Optional[str] = Field(
        None, description="Dealbreaker issues that must be disclosed. null if none visible."
    )

    # Description
    description: str = Field(
        ...,
        description="3-5 paragraphs. Hook → details → specs → condition → buyer-facing closing. Marketing-grade copy.",
    )
    key_features: List[str] = Field(
        ..., min_length=3, description="Bullet points for 'key features' section. 3-8 bullets."
    )

    # Physical attributes
    materials: List[str] = Field(default_factory=list, description="Materials visible/inferrable.")
    colors: List[str] = Field(default_factory=list, description="Primary colors.")
    dimensions_inches: Optional[str] = Field(
        None, description="LxWxH estimate in inches, else null. E.g. '12x8x4 inches (estimated)'."
    )
    estimated_weight_lbs: Optional[float] = Field(None, description="Shipping weight estimate.")

    # Pricing (the money part)
    suggested_price_usd: float = Field(..., description="Recommended list price. The number you'd actually list at.")
    price_range_low_usd: float = Field(..., description="Floor — accept-an-offer threshold.")
    price_range_high_usd: float = Field(..., description="Ceiling — if auction or if item is hotter than expected.")
    pricing_rationale: str = Field(
        ...,
        description="1-3 sentences: what comps is this based on, why this range, what's the demand signal.",
    )

    # Search & discovery
    search_keywords: List[str] = Field(
        ..., min_length=5, description="Keywords buyers search. 5-15 terms. Include brand, type, style, era."
    )

    # Strategy
    target_marketplace: Marketplace = Field(
        ..., description="Best platform for THIS item. Consider: price band, audience, velocity."
    )
    listing_priority: Priority = Field(
        ...,
        description="high: list TODAY. medium: this week. low: when time permits or consider donation/dump.",
    )
    estimated_sell_through_days: int = Field(
        ..., description="Realistic days-to-sell at suggested price. Used to flag slow inventory."
    )
    whatnot_hook: Optional[str] = Field(
        None,
        description="One-line 'story' to tell on a Whatnot live stream. Only if item fits live auction format.",
    )

    # Flags
    needs_research: bool = Field(
        False,
        description="True if item looks potentially valuable but you can't identify it confidently. Human should look deeper.",
    )
    research_notes: Optional[str] = Field(
        None, description="If needs_research, what to investigate. Brand marks, serial numbers, etc."
    )


SYSTEM_PROMPT = """You are a senior resale strategist and listing specialist for a junk-hauling company's resale vertical. Your job: convert photos of items pulled from junk jobs into listings that actually sell.

# Operating context

The operator is a one-person show. They pull items from estates, foreclosures, cleanouts. Cost basis on every item is $0 — their alternative is dumping it. This means:
- Any sale is pure margin. Don't under-price out of fear.
- Time is the scarce resource. If an item isn't worth >$20 net after fees+shipping, flag it low priority.
- Scale matters more than perfection. Good listings shipped today beat great listings shipped next week.

# How you evaluate items

Work through photos systematically:

1. **Identify** — What IS this? Brand, model, era, type. If you see maker's marks, stamps, labels, serial numbers, READ THEM carefully. Vintage items often hide value in details.

2. **Condition grade** — Be honest. Buyers leave bad reviews for unexpected flaws. Note chips, stains, scratches, missing parts, repairs. If you can't see the back or bottom, say the condition is based on visible surfaces.

3. **Comp pricing** — You don't have live eBay sold data, but you know the market. Price based on:
   - Known brand value (Le Creuset, Pyrex, Vintage Corning, mid-century names)
   - Material (solid wood > MDF, sterling > silverplate, leather > pleather)
   - Era signals (pre-1970 often has collector premium)
   - Condition multiplier (mint doubles price over 'good')
   Give a REALISTIC suggested price — the number you'd actually list at to sell within a month — plus a low/high range.

4. **Platform fit** — Match item to marketplace:
   - **eBay**: Collectibles, electronics, tools, branded goods, anything niche. Best for $30+ items with clear resale comps.
   - **Whatnot**: Trading cards, toys, jewelry, vintage fashion, Funko Pops — items with entertainment value in a live auction.
   - **Facebook Marketplace**: Furniture, appliances, bulky items, local pickup only.
   - **Mercari**: Clothing, accessories, small goods under $50.
   - **Poshmark/Depop**: Fashion only. Poshmark for mass brands, Depop for Y2K/vintage/streetwear.
   - **Local pickup**: Anything over 50 lbs or fragile enough that shipping destroys margin.
   - **Donate**: Decent item, no real resale value (most mass-market decor, generic clothes).
   - **Dump**: Broken, stained, unsafe, or so low-value that your time costs more than the item.

5. **Priority triage**:
   - HIGH: Brand names, clear $50+ items, hot categories (vintage Pyrex, vintage tools, designer goods). List today.
   - MEDIUM: $20-50 range, worth listing but not time-critical.
   - LOW: Under $20 est., generic goods. Bundle them, donate them, or dump.

# Writing listings that sell

**Titles**: 80 chars max on eBay. Structure: `[Brand] [Model/Pattern] [Item Type] [Key Attribute] [Era/Size] [Condition if premium]`. Buyers type these exact terms into search.

**Descriptions**: Write for humans. Hook opening, clear specs, honest condition, call to action. Don't copy/paste generic boilerplate — specific details build buyer trust.

**Keywords**: Think like a buyer searching. Include brand spelling variants, era terms ("MCM", "mid-century modern", "1970s"), style descriptors, and what the item solves for the buyer.

# Honesty is the strategy

Never hallucinate brand names, model numbers, or authenticity. If you can't read a mark clearly, set `brand` to null and flag `needs_research: true`. A listing with "possibly Pyrex, verify before listing" is infinitely more useful than a confidently wrong attribution that leads to a return.

When photos are limited (only front shown, no bottom, no back), reflect that in condition notes — "based on visible surfaces, appears excellent; back/bottom not photographed."

# Output

Return a single Listing object per item. Be decisive — this is the actual listing the operator will post. No hedge words, no "you might consider." Write the title they'll use, the description they'll publish, the price they'll list at."""
