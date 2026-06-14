"""
scanner.py — Auto Deal Scanner (v2)
====================================
Scans eBay (with API keys) and SidelineSwap (public pages).

Key improvements over v1:
  - Same exclusion keywords as lookup for consistent filtering
  - Brand minimum price floors — no accessories ever saved
  - Deduplication by URL, not just item ID
  - Confidence check before saving — needs enough price data
  - Clear source tagging on every deal
  - Respectful rate limiting
"""

import os, re, json, hashlib, requests, time
from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
    EBAY_APP_ID  = os.getenv("EBAY_APP_ID","") or st.secrets.get("EBAY_APP_ID","")
    EBAY_CERT_ID = os.getenv("EBAY_CERT_ID","") or st.secrets.get("EBAY_CERT_ID","")
except Exception:
    EBAY_APP_ID  = os.getenv("EBAY_APP_ID","")
    EBAY_CERT_ID = os.getenv("EBAY_CERT_ID","")

try:
    import sys, os as _os
    sys.path.insert(0, _os.path.dirname(__file__))
    from lookup import (lookup_club, EBAY_CATEGORIES, BRAND_MIN_PRICE,
                        EXCLUSION_KEYWORDS, _get_ebay_token, _is_valid_price)
    from scorer import score_deal
    from database import save_deal, _conn
    from notifier import send_discord_alert
except Exception as e:
    raise ImportError(f"Scanner could not import dependencies: {e}")

MIN_SCORE_TO_SAVE  = 55
MIN_SCORE_TO_ALERT = 70

SKIP_TITLE_WORDS = [
    "headcover", "head cover", "grip", "marker", "divot",
    "tool", "towel", "hat", "shirt", "glove", "ball", "tee",
    "cover", "case", "sleeve", "adapter", "wrench",
]

SCAN_TARGETS = [
    {"brand": "Scotty Cameron", "model": "Newport 2",     "type": "putter",     "max": 500},
    {"brand": "Scotty Cameron", "model": "Newport",       "type": "putter",     "max": 450},
    {"brand": "Scotty Cameron", "model": "Phantom X",     "type": "putter",     "max": 600},
    {"brand": "Scotty Cameron", "model": "Special Select","type": "putter",     "max": 550},
    {"brand": "Titleist",       "model": "T100",          "type": "iron set",   "max": 750},
    {"brand": "Titleist",       "model": "T200",          "type": "iron set",   "max": 650},
    {"brand": "Titleist",       "model": "TSR2",          "type": "driver",     "max": 400},
    {"brand": "Titleist",       "model": "TSR3",          "type": "driver",     "max": 450},
    {"brand": "TaylorMade",     "model": "P790",          "type": "iron set",   "max": 750},
    {"brand": "TaylorMade",     "model": "P770",          "type": "iron set",   "max": 650},
    {"brand": "TaylorMade",     "model": "Stealth",       "type": "driver",     "max": 350},
    {"brand": "TaylorMade",     "model": "Qi10",          "type": "driver",     "max": 450},
    {"brand": "Callaway",       "model": "Paradym",       "type": "driver",     "max": 400},
    {"brand": "Callaway",       "model": "Apex",          "type": "iron set",   "max": 650},
    {"brand": "Ping",           "model": "G430",          "type": "iron set",   "max": 550},
    {"brand": "Mizuno",         "model": "JPX 923",       "type": "iron set",   "max": 650},
    {"brand": "Vokey",          "model": "SM9",           "type": "wedge",      "max": 180},
    {"brand": "Vokey",          "model": "SM8",           "type": "wedge",      "max": 150},
    {"brand": "Bettinardi",     "model": "BB",            "type": "putter",     "max": 450},
    {"brand": "Odyssey",        "model": "White Hot",     "type": "putter",     "max": 200},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


# ── Deduplication ─────────────────────────────────────────────────────────────

def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:16]


def _already_seen(url: str, item_id: str = "") -> bool:
    try:
        c = _conn()
        url_h = _url_hash(url)
        row = c.execute(
            "SELECT id FROM deals WHERE raw_json LIKE ? OR raw_json LIKE ?",
            (f"%{url_h}%", f"%{item_id}%")
        ).fetchone()
        c.close()
        return row is not None
    except Exception:
        return False


def _is_accessory(title: str) -> bool:
    t = title.lower()
    return any(w in t for w in SKIP_TITLE_WORDS)


# ── eBay scanner ──────────────────────────────────────────────────────────────

def _search_ebay(brand: str, model: str, club_type: str, max_price: float) -> list[dict]:
    token = _get_ebay_token()
    if not token:
        return []

    brand_key = brand.lower()
    min_price = BRAND_MIN_PRICE.get(brand_key, BRAND_MIN_PRICE["default"])
    cat_id    = EBAY_CATEGORIES.get(club_type.lower(), EBAY_CATEGORIES["default"])
    query     = f"{brand} {model} {EXCLUSION_KEYWORDS}"

    try:
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {token}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params={
                "q":            query,
                "category_ids": cat_id,
                "filter":       f"buyingOptions:{{FIXED_PRICE}},price:[{min_price}..{max_price}],priceCurrency:USD",
                "sort":         "newlyListed",
                "limit":        25,
            },
            timeout=15
        )
        r.raise_for_status()
        items = r.json().get("itemSummaries", [])

        results = []
        for i in items:
            price = float(i.get("price", {}).get("value", 0))
            title = i.get("title", "")
            url   = i.get("itemWebUrl", "")
            item_id = f"ebay_{i.get('itemId','')}"

            if _is_accessory(title):
                continue
            if not _is_valid_price(price, brand):
                continue

            ship = float((i.get("shippingOptions") or [{}])[0]
                         .get("shippingCost", {}).get("value", 0))

            results.append({
                "title":        title,
                "asking_price": price + ship,
                "shipping_cost": ship,
                "condition":    i.get("condition", "Good"),
                "listing_url":  url,
                "image_url":    i.get("image", {}).get("imageUrl", ""),
                "item_id":      item_id,
                "source":       "eBay",
            })
        return results

    except Exception:
        return []


# ── SidelineSwap scanner ──────────────────────────────────────────────────────

def _search_sidelineswap(brand: str, model: str, max_price: float) -> list[dict]:
    """Fetch public SidelineSwap search results (no login required)."""
    results = []
    try:
        query   = f"{brand} {model}"
        encoded = requests.utils.quote(query)
        url     = f"https://sidelineswap.com/search?query={encoded}&sport=golf"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text, re.DOTALL
        )
        if not match:
            return []

        data  = json.loads(match.group(1))
        props = data.get("props", {}).get("pageProps", {})
        items = (props.get("items") or
                 props.get("searchResults", {}).get("items") or
                 props.get("results", {}).get("items") or [])

        for item in items:
            price = float(item.get("price", 0) or 0)
            title = item.get("name", "") or item.get("title", "")
            if price <= 0 or price > max_price:
                continue
            if _is_accessory(title):
                continue
            if not _is_valid_price(price, brand):
                continue

            item_id   = str(item.get("id", ""))
            item_url  = f"https://sidelineswap.com/gear/{item_id}"
            condition = item.get("condition", {})
            if isinstance(condition, dict):
                condition = condition.get("name", "Good")
            photos    = item.get("photos", [])
            image_url = ""
            if photos and isinstance(photos[0], dict):
                image_url = photos[0].get("url", "")

            results.append({
                "title":        title,
                "asking_price": price,
                "shipping_cost": 0,
                "condition":    condition or "Good",
                "listing_url":  item_url,
                "image_url":    image_url,
                "item_id":      f"sls_{item_id}",
                "source":       "SidelineSwap",
            })

    except Exception:
        pass

    return results


# ── Main scan ─────────────────────────────────────────────────────────────────

def run_scan() -> list[dict]:
    """
    Scan all targets across eBay and SidelineSwap.
    Returns list of new deals found and saved.
    """
    new_deals = []

    for target in SCAN_TARGETS:
        brand     = target["brand"]
        model     = target["model"]
        club_type = target["type"]
        max_price = target["max"]

        all_listings = []

        # eBay (if keys available)
        if EBAY_APP_ID:
            ebay = _search_ebay(brand, model, club_type, max_price)
            all_listings.extend(ebay)

        # SidelineSwap (always try)
        sls = _search_sidelineswap(brand, model, max_price)
        all_listings.extend(sls)

        for listing in all_listings:
            url     = listing.get("listing_url", "")
            item_id = listing.get("item_id", "")

            if _already_seen(url, item_id):
                continue

            # Get full analysis
            lookup_result = lookup_club({
                "brand":        brand,
                "model":        model,
                "condition":    listing.get("condition", "Good"),
                "asking_price": listing["asking_price"],
                "club_type":    club_type,
            })

            if lookup_result.get("error"):
                continue

            # Only save if we have decent price confidence
            if lookup_result.get("confidence") == "Very Low":
                continue

            scored = score_deal(lookup_result)

            if scored["score"] < MIN_SCORE_TO_SAVE:
                continue

            deal = {
                **lookup_result,
                **scored,
                "title":       listing["title"] or f"{brand} {model}",
                "source":      listing["source"],
                "listing_url": url,
                "image_url":   listing.get("image_url", ""),
                "brand":       brand,
                "model":       model,
                "club_type":   club_type,
                "url_hash":    _url_hash(url),
            }

            save_deal(deal)
            new_deals.append(deal)

            if scored["score"] >= MIN_SCORE_TO_ALERT:
                send_discord_alert(deal)

        time.sleep(0.5)  # respectful rate limiting

    return new_deals
