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

### Shop-walk capture protocol (the fast way)

Walk the shop with one phone. **Do not tap "new folder" for each item** — let timestamps do the organizing.

For every item:

1. **Triage first** — 2-second sniff test. If it's <$20 potential, skip the photos (donate/dump pile).
2. **Burst 3-5 photos in <30 seconds:**
   - Wide front
   - Back / opposite side
   - Any **marks, labels, signatures, model numbers** (close + crisp)
   - Any **damage** (chips, stains, tears)
   - Optional: inside / bottom
3. **Pause 60+ seconds before the next item.** The time gap is how the tool separates items.
4. **Voice notes welcome.** If you know something the camera can't show ("smells like cigarettes", "works when plugged in", "hallmark is a crown over W"), transcribe into a `.txt` file timestamped near the item. The cluster tool picks it up as `notes.txt` automatically.

### 1. Dump phone photos

Drop everything into `photos/raw/` — a single flat folder. Don't organize manually.

### 2. Cluster by timestamp

```bash
# Preview first (no files moved)
python -m resale cluster photos/raw/ --dry-run

# Looks right? Do it.
python -m resale cluster photos/raw/
```

Output:

```
🔍 CLUSTERING — gap threshold: 45s

  📦 2026-04-14-001: 4 photos over 18s
  📦 2026-04-14-002: 3 photos over 12s + 1 note
  📦 2026-04-14-003: 5 photos over 22s
  ...
✓ 47 item folders created

Next: python -m resale batch photos/
```

Tune the gap if you shoot fast (`--gap 30`) or slow (`--gap 90`).

### 3. Generate listings

```bash
# All items at once (after cluster)
python -m resale batch photos/

# Or one at a time
python -m resale list photos/2026-04-14-001/
```

Prompt caching kicks in from item #2 onward — per-item cost drops ~90%.

### 4. Check inventory

```bash
python -m resale inventory
```

Shows total list value, priority breakdown, marketplace split, and top 10 by price. Highlights items flagged `needs_research`.

### 5. Cross-post via crosslist.com

1. Open `listings/listings.csv`
2. Eyeball `listing.md` files for items flagged `needs_research` before posting
3. Import the CSV into crosslist.com (they map custom columns during import)
4. Ship.

### Manual folder naming (alternative to clustering)

If you'd rather organize by hand, one folder per item, folder name = SKU. Suggested naming: `YYYY-MM-DD-NNN-short-description`. Sortable, unique, descriptive at a glance.

```
photos/
├── 2026-04-14-001-blue-vase/
│   ├── front.jpg
│   ├── side.jpg
│   ├── bottom-mark.jpg
│   └── notes.txt          ← optional, operator context
├── 2026-04-14-002-craftsman-wrench/
│   ├── IMG_1234.jpg
│   └── IMG_1235.jpg
```

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

## Memory (persistent, token-efficient)

Your AI partner has a brain that survives across sessions. Stored locally in `.memory/`:

- **`core.md`** — your operator profile, always loaded into context (~500 token budget). Edit it directly any time.
- **`captures.jsonl`** — append-only log of every idea/task/item/fact ever saved
- **`statuses.jsonl`** — append-only status changes (tasks marked done, etc.)

### Why it stays cheap

- Memory is **pulled, not pushed**. The system prompt + `core.md` are always there (~3.5K tokens) and cached so they cost ~$0.0005 per turn after the first. Beyond that, nothing from memory is in the context until Claude *decides* to pull it via the `recall` tool.
- Conversation history is capped at the last 20 user/assistant pairs (sliding window).
- Per voice exchange: **~$0.005 amortized** after cache warms up. Half a cent.

### How it stays evolving

Five capture kinds — Claude picks which:

| Kind | Use for |
|---|---|
| `task` | Things to do (follow up with Dave, list those Funkos, call the auctioneer) |
| `idea` | Things to try / explore (test Whatnot pricing for vintage tools, set up an LLC for resale vertical) |
| `item` | Notable items mentioned that need follow-up before listing |
| `fact` | Stuff learned (Pyrex Spring Blossom 1972 sells $80-150, Dave pays cash for tools) |
| `note` | Catch-all |

Tasks/ideas have an **open / in_progress / done / archived** status. `list_open` returns oldest first so stale stuff bubbles to the top — the antidote to ADHD drift.

### Voice flow examples

> "Remember Dave's coming Tuesday for that 5-bedroom estate cleanout, mostly mid-century stuff."
> 📝 saving — "Got it, on your list."

> "What was that price you quoted on the vintage Singer?"
> 🔎 recalling — "$385, listed three days ago. Marked high priority."

> "What's on my list?"
> 📋 reading list — "Three open tasks. Dave's estate Tuesday, list those Funko Pops on Whatnot, and follow up on the Anderson lead from last week."

> "Mark the Funko one done."
> ✓ marking done — "Killed."

### CLI quick commands

```bash
# Quick capture without opening voice
python -m resale capture --kind task "Email auctioneer about Saturday consignment"
python -m resale capture --kind item --tags "pyrex,vintage" "Cinderella set, complete, light wear on yellow bowl"

# Review surface — your ADHD command center
python -m resale review

# Search memory
python -m resale recall pyrex
python -m resale recall --kind task dave

# Mark something done
python -m resale complete cap_abc123def
```

`python -m resale review` shows total counts, all open tasks (oldest first), open ideas, and recent notes/items/facts. Run it daily with your coffee.

### Editing your profile

Open `.memory/core.md` in your editor any time. Add context, preferences, current focus areas. It auto-loads into every voice/CLI session as the cached profile block. Keep it under ~500 tokens for cost efficiency — if you need more depth on something, capture it as a `fact` instead.

---

## Voice copilot

Talk to your AI partner. Browser-based, no app to install.

```bash
python -m resale voice
```

Open `http://localhost:8765` on your laptop, **or** open `http://<your-LAN-ip>:8765` on your phone (same WiFi). Tap the mic, talk, get a spoken reply.

What it does well right now:
- Push-to-talk: tap mic, talk, tap to send (or pause and it auto-sends)
- Streams Claude Opus 4.6 sentence-by-sentence so the voice starts speaking before Claude finishes
- Knows it's *your* resale operation's copilot — short answers, decisive pricing, marketplace recs, no markdown read aloud
- Conversation memory per browser (clear with the ↺ button)
- Barge-in: tap the mic while Claude is talking to interrupt and respond

Browser support: Chrome, Edge, Android Chrome (full). iOS Safari: TTS works, but STT is limited — use the iOS keyboard's mic button as a workaround.

Voice quality: uses your operating system's built-in voices (free). Want studio-quality voices? Tell me and I'll wire in ElevenLabs or OpenAI TTS.

## Commands

**Voice + memory**
| | |
|---|---|
| `python -m resale voice` | Start the voice-to-voice web UI |
| `python -m resale capture <text>` | Quick-save to memory (`--kind task/idea/item/fact/note`, `--tags a,b`) |
| `python -m resale review` | ADHD command center: open tasks, ideas, recent captures |
| `python -m resale recall <query>` | Search memory by keyword |
| `python -m resale complete <cap_id>` | Mark a task done |

**Listings pipeline**
| | |
|---|---|
| `python -m resale cluster <raw_dir>` | Group loose photos into per-item folders by EXIF timestamp |
| `python -m resale cluster <raw_dir> --dry-run` | Preview clustering without moving files |
| `python -m resale list <folder>` | Generate listing for one item |
| `python -m resale list <folder> --notes "..."` | Generate listing with operator context |
| `python -m resale batch <folder>` | Generate listings for every subfolder |
| `python -m resale inventory` | Summary: total value, priority, marketplace split, top 10 |
| `python -m resale schema` | Print the Listing JSON schema |
