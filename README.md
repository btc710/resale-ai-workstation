# resale-ai-workstation

AI copilot for a one-person junk-hauling + resale operation.

**What it does:** Drop a folder of photos of an item you pulled off a job → get back a complete marketplace listing (title, description, condition grade, comp-based price, target marketplace, priority). Bulk-upload the CSV to crosslist.com to syndicate across eBay, Mercari, Poshmark, Facebook Marketplace, and more.

**Why it exists:** The bottleneck in resale isn't listing distribution — crosslist.com already solves that. The bottleneck is *writing* the listing: identifying the item, grading condition, pricing it against comps, writing a title buyers actually search for. This tool collapses that from 10–15 minutes per item to ~30 seconds.

---

## What you get per item

- **`listings/<sku>/listing.json`** — full structured data
- **`listings/<sku>/listing.md`** — human-readable preview to eyeball before posting
- **`listings/listings.csv`** — one master CSV, every item appended as a row, ready to import into crosslist.com

Each listing includes:

| | |
|---|---|
| **Title** | eBay-optimized, ≤80 chars |
| **Description** | 3–5 paragraph marketing copy |
| **Condition** | 7-point grade + honest flaw notes |
| **Pricing** | Suggested price + low/high range + rationale |
| **Target marketplace** | eBay / Whatnot / FB Marketplace / Mercari / Poshmark / Depop / local / donate / dump |
| **Priority** | High (list today) / medium / low (or donate) |
| **Keywords** | 5–15 buyer search terms |
| **Whatnot hook** | One-line stream pitch if applicable |
| **Research flag** | Flags items that need a human second look before listing |

---

## Setup

```bash
# 1. Clone & enter
git clone <repo-url>
cd resale-ai-workstation

# 2. Python env (3.10+)
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows

# 3. Install deps
pip install -r requirements.txt

# 4. API key
cp .env.example .env
# edit .env and add your key from https://console.anthropic.com/settings/keys
```

---

## Usage

### 1. Organize photos

One folder per item. Folder name becomes the SKU. All photos of the same item in the same folder:

```
photos/
├── 2026-04-14-001-blue-vase/
│   ├── front.jpg
│   ├── side.jpg
│   ├── bottom-mark.jpg
│   └── inside.jpg
├── 2026-04-14-002-craftsman-wrench/
│   ├── IMG_1234.jpg
│   └── IMG_1235.jpg
```

Suggested naming: `YYYY-MM-DD-NNN-short-description`. Sortable, unique, descriptive at a glance.

### 2. List one item

```bash
python -m resale list photos/2026-04-14-001-blue-vase/
```

Output:

```
📸 Analyzing 2026-04-14-001-blue-vase...
  ✓ 2026-04-14-001-blue-vase: Vintage Mid-Century Cobalt Blue Ceramic Bud Vase...
    $28.00 ($22–$45) → ebay [medium] (12.3s)
  → listings/2026-04-14-001-blue-vase/ + listings/listings.csv
```

Pass operator context when you know something the camera can't see:

```bash
python -m resale list photos/2026-04-14-001-blue-vase/ \
  --notes "signed 'Murano' on bottom, slight hairline crack inside rim"
```

### 3. Batch-list a whole truck haul

```bash
python -m resale batch photos/
```

Processes every subfolder. Per-item cost drops ~90% after the first item thanks to prompt caching.

### 4. Cross-post via crosslist.com

1. Open `listings/listings.csv`
2. Eyeball the preview `listing.md` files for items flagged `needs_research`
3. Import the CSV into crosslist.com (they map custom columns during import)
4. Ship.

---

## Architecture

- **Model:** Claude Opus 4.6 with adaptive thinking
- **Vision:** All photos of an item sent in one request so the model reasons across angles
- **Structured output:** Pydantic schema → guaranteed valid listing every time, no JSON parsing roulette
- **Prompt caching:** ~11K-token system prompt cached with `cache_control`, ~90% cost reduction after item #1
- **Image handling:** Auto-resized to 1568px max edge (Anthropic's sweet spot)

Cost ballpark: ~$0.05–0.15 per item after cache warms up. Break-even against your time is instant.

---

## Roadmap

v1 (shipped): Photos → listings → CSV
v2: eBay API auto-posting, sold-comp lookup for tighter pricing, web UI
v3: OBS overlay for Whatnot live streams, Quest 3 point-of-pickup triage, inventory/velocity dashboard

---

## Commands

| | |
|---|---|
| `python -m resale list <folder>` | List one item |
| `python -m resale list <folder> --notes "..."` | List one item with operator context |
| `python -m resale batch <folder>` | List every subfolder |
| `python -m resale schema` | Print the JSON schema of a Listing |
