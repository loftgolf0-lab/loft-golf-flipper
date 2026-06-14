# ⛳ Golf Flipper — Full Project Plan & Guide

## Overview

Golf Flipper is a legal, ethical tool to help you identify underpriced golf
equipment, estimate resale profit, and track your flipping business. It uses
only official APIs and manual data entry — no scraping.

---

## Project Architecture

```
golf-flipper/
├── app.py                  ← Streamlit dashboard (main entry point)
├── requirements.txt
├── .env.example            ← Copy to .env and fill in your keys
├── data/
│   └── listings.db         ← SQLite database (auto-created)
└── src/
    ├── ebay_fetcher.py     ← eBay Browse API integration
    ├── manual_entry.py     ← DB layer + manual listing entry
    ├── scorer.py           ← Deal scoring + profit estimation
    └── notifier.py         ← Alert system (email/Discord/Telegram)
```

---

## Setup Instructions

### Step 1 — Install Python dependencies

```bash
# Recommended: create a virtual environment first
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Step 2 — Configure your eBay API keys

1. Go to https://developer.ebay.com and sign in (free account)
2. Click **My Account → Application Keys**
3. Click **Create Application** (choose "Production" for live data)
4. Copy your **App ID** and **Cert ID**
5. Copy `.env.example` to `.env` and fill in the values

```bash
cp .env.example .env
# Edit .env with your keys
```

### Step 3 — Run the app

```bash
streamlit run app.py
```

Open your browser to http://localhost:8501

---

## How to Use Each Platform

### eBay (Automated via API ✅)
- Use the **🔍 eBay Search** page
- Enter a query like "Scotty Cameron putter" or "Titleist T100 irons"
- The app fetches active listings AND recent sold comps automatically
- Listings are scored and ranked by profit potential

### Facebook Marketplace (Manual Entry ✅)
- Browse Facebook Marketplace in your browser normally
- When you find something interesting, copy the title, price, and URL
- Go to **✍️ Add Listing** in the app, select "facebook" as source
- Paste in the details — the app will score it instantly

### Craigslist, OfferUp, Mercari, SidelineSwap (Manual Entry ✅)
- Same as Facebook Marketplace workflow above
- For SidelineSwap and GolfWRX: these have large communities of motivated
  sellers; check them daily for the best deals

### eBay Sold Price Research (Semi-automated ✅)
- The app's eBay Search automatically pulls in recent sold comps
- For manual research: search eBay → filter "Completed Listings" → 
  enter the sold prices in the "Comp 1-8" fields on the Add Listing page

---

## Deal Scoring Formula

Scores are weighted 0-100 across 8 components:

| Component          | Weight | What it measures                               |
|--------------------|--------|------------------------------------------------|
| Price vs market    | 35 pts | How far below comp prices the ask is          |
| Brand demand       | 15 pts | Resale velocity for this brand                |
| Resale ease        | 10 pts | How quickly this club type sells              |
| Condition          | 15 pts | Condition multiplier on resale value          |
| Local pickup       |  5 pts | Can you avoid inbound shipping?               |
| Listing age        |  5 pts | Fresh listings = motivated sellers            |
| Seller trust       | 10 pts | Feedback score                                |
| Info quality       |  5 pts | Photos, brand/model info present              |

**Grades:**
- S (85-100): Exceptional — act fast
- A (70-84):  Strong buy
- B (55-69):  Good deal, worth pursuing
- C (40-54):  Marginal — negotiate down first
- D (25-39):  Weak — only if price drops
- F (0-24):   Pass

---

## Profit Estimation Formula

```
Est. Resale = Median(comparable sold prices) × condition_multiplier

Total Buy Cost = asking_price + inbound_shipping + cleaning_cost

eBay Fees = resale × 13.35% (FVF) + resale × 3% (payment) + $0.35 + $0.30

Net Profit = Est. Resale − Total Buy Cost − eBay Fees − outbound_shipping

ROI % = (Net Profit / Total Buy Cost) × 100
```

**Fee note:** eBay's fees change. Always verify at ebay.com/seller/fees.
As of 2024: ~13.35% final value fee + ~3% managed payments for most categories.

---

## Database Schema

### listings table
| Column             | Type    | Notes                                      |
|--------------------|---------|--------------------------------------------|
| item_id            | TEXT PK | Auto-generated hash                        |
| source             | TEXT    | ebay/facebook/craigslist/etc               |
| title              | TEXT    | Listing title                              |
| brand              | TEXT    |                                            |
| model              | TEXT    |                                            |
| club_type          | TEXT    | Driver/Putter/Iron Set/etc                 |
| condition          | TEXT    |                                            |
| asking_price       | REAL    |                                            |
| shipping_cost      | REAL    | Inbound shipping cost                      |
| total_cost         | REAL    | asking + shipping                          |
| location           | TEXT    |                                            |
| listing_url        | TEXT    |                                            |
| image_url          | TEXT    |                                            |
| listed_at          | TEXT    | ISO datetime                               |
| added_at           | TEXT    | When you added it                          |
| est_resale         | REAL    | Estimated resale value                     |
| est_profit         | REAL    | Estimated net profit                       |
| roi_pct            | REAL    | Estimated ROI %                            |
| deal_score         | INTEGER | 0-100 deal score                           |
| risk_level         | TEXT    | LOW/MEDIUM/HIGH/VERY_HIGH                  |
| status             | TEXT    | new/watching/contacted/purchased/listed/sold|
| actual_sell_price  | REAL    | What you actually sold it for              |
| actual_profit      | REAL    | Actual profit after all costs              |

### comparable_sales table
Stores recent eBay sold prices for market value estimation.

### watchlist table
Saved search queries with alert thresholds.

---

## Legal & Ethical Guidelines

### ✅ What this tool DOES
- Uses official eBay API (completely legal, free tier available)
- Manual entry for platforms without public APIs
- Stores only listing data you voluntarily enter
- Respects rate limits on all API calls

### ❌ What this tool does NOT do
- **No scraping** of any website
- **No bypassing login walls** or CAPTCHAs
- **No automated browsing** of Facebook, Craigslist, etc.
- **No mass-messaging** sellers (the app has no send/contact feature)
- **No storing personal data** about sellers beyond feedback score

### Platform-specific notes

| Platform         | Automated Access      | Method                          |
|------------------|-----------------------|---------------------------------|
| eBay             | ✅ Yes (official API) | Browse API + OAuth              |
| SidelineSwap     | ⚠️  Check ToS         | Manual entry only               |
| GolfWRX          | ⚠️  Check ToS         | Manual entry only               |
| Facebook Mktpl.  | ❌ No (login required)| Manual entry only               |
| Craigslist       | ❌ No (blocks bots)   | Manual entry only               |
| OfferUp          | ❌ No                 | Manual entry only               |
| Mercari          | ❌ No (login required)| Manual entry only               |
| 2nd Swing        | ✅ (public listings)  | Manual; contact them for feeds  |

---

## Recommended Brands & Models to Watch

### Highest demand / easiest resale
- **Putters:** Scotty Cameron (any model), Bettinardi BB/Studio series
- **Drivers:** TaylorMade Stealth/Qi10, Titleist TSR, Callaway Paradym
- **Irons:** Titleist T100/T150, TaylorMade P770/P790, Mizuno JPX 923
- **Wedges:** Vokey SM series, Cleveland RTX, Titleist Vokey
- **Fairway/Hybrids:** TaylorMade Qi10, Callaway Paradym, Ping G430

### High profit potential when found underpriced
- Scotty Cameron limited/tour-issue putters
- Vintage/classic Ping BeCu irons
- TaylorMade OG Burner/r7/r9 drivers (collector items)
- Mizuno MP series blades
- Any TOUR issue/used equipment

---

## Future Improvements

### Phase 2: Browser Extension
Build a simple Chrome/Firefox extension (Manifest V3) that:
- Detects when you're on a supported marketplace page
- Adds a "Score This" button to the page
- Sends the listing data to a local Flask API on localhost:5001
- The API scores it and returns the deal grade as an overlay

This is 100% ToS-compliant because a human is browsing — no automation.

### Phase 3: SidelineSwap RSS Feed
SidelineSwap offers RSS feeds for search results. These are public, no login
required, and commonly used for alerts. You can poll these feeds on a schedule
to get notified of new listings matching your criteria.

```python
# Example RSS feed URL (check SidelineSwap for current format)
url = "https://sidelineswap.com/search?q=scotty+cameron&format=rss"
```

### Phase 4: eBay Advanced Filters
- Use eBay's Finding API (legacy but still active) for completed/sold listings
  with more precise date filtering
- Add eBay saved search + notification via eBay's own alert system

### Phase 5: Scheduled Scanning
Use Python `schedule` or a cron job to:
```python
import schedule, time
def daily_scan():
    # Run eBay searches for each watchlist item
    # Send alerts for new deals that meet threshold
    pass
schedule.every(6).hours.do(daily_scan)
while True:
    schedule.run_pending()
    time.sleep(60)
```

### Phase 6: Price History Charts
Store historical comps over time and plot price trends per model using Plotly.

---

## Quick Reference: Key Golf Resale Markets

| Platform      | Best For                          | Typical Buyer      |
|---------------|-----------------------------------|--------------------|
| eBay          | Any item, highest reach           | Nationwide         |
| SidelineSwap  | Golf-specific, active community   | Golfers nationwide |
| GolfWRX       | High-end/premium equipment        | Serious golfers    |
| Facebook Mktpl| Local quick sales                 | Local golfers      |
| Craigslist    | Local only, cash deals            | Local              |
| OfferUp       | Casual sellers, good deals        | Local + ship       |
| 2nd Swing     | Consignment for premium clubs     | Nationwide         |

---

*Built for educational and personal use. Always verify eBay fee structures
at ebay.com/seller/fees before making purchasing decisions.*
