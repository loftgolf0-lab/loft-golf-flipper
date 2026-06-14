"""
scanner.py — Automatic deal scanner
Scans SidelineSwap (public pages) and eBay (when API keys available)
"""
import os, re, json, requests, time, hashlib
from dotenv import load_dotenv

try:
    from lookup import lookup_club
    from scorer import score_deal
    from database import save_deal, _conn
    from notifier import send_discord_alert
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from lookup import lookup_club
    from scorer import score_deal
    from database import save_deal, _conn
    from notifier import send_discord_alert

load_dotenv()

EBAY_APP_ID  = os.getenv("EBAY_APP_ID", "")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID", "")

try:
    import streamlit as st
    EBAY_APP_ID  = EBAY_APP_ID  or st.secrets.get("EBAY_APP_ID", "")
    EBAY_CERT_ID = EBAY_CERT_ID or st.secrets.get("EBAY_CERT_ID", "")
except Exception:
    pass

_token_cache: dict = {"token": None, "expires_at": 0}

MIN_SCORE_TO_SAVE  = 55
MIN_SCORE_TO_ALERT = 70

SCAN_TARGETS = [
    {"query": "Scotty Cameron putter",     "brand": "Scotty Cameron", "model": "putter",        "type": "putter",     "max": 500},
    {"query": "Scotty Cameron Newport",    "brand": "Scotty Cameron", "model": "Newport",        "type": "putter",     "max": 400},
    {"query": "Titleist T100 irons",       "brand": "Titleist",       "model": "T100",           "type": "iron set",   "max": 700},
    {"query": "Titleist T200 irons",       "brand": "Titleist",       "model": "T200",           "type": "iron set",   "max": 600},
    {"query": "TaylorMade P790 irons",     "brand": "TaylorMade",     "model": "P790",           "type": "iron set",   "max": 700},
    {"query": "TaylorMade P770 irons",     "brand": "TaylorMade",     "model": "P770",           "type": "iron set",   "max": 600},
    {"query": "TaylorMade Stealth driver", "brand": "TaylorMade",     "model": "Stealth",        "type": "driver",     "max": 350},
    {"query": "TaylorMade Qi10 driver",    "brand": "TaylorMade",     "model": "Qi10",           "type": "driver",     "max": 450},
    {"query": "Callaway Paradym driver",   "brand": "Callaway",       "model": "Paradym",        "type": "driver",     "max": 400},
    {"query": "Titleist Vokey SM9 wedge",  "brand": "Vokey",          "model": "SM9",            "type": "wedge",      "max": 180},
    {"query": "Titleist Vokey SM8 wedge",  "brand": "Vokey",          "model": "SM8",            "type": "wedge",      "max": 140},
    {"query": "Ping G430 irons",           "brand": "Ping",           "model": "G430",           "type": "iron set",   "max": 500},
    {"query": "Mizuno JPX 923 irons",      "brand": "Mizuno",         "model": "JPX 923",        "type": "iron set",   "max": 600},
    {"query": "Bettinardi BB putter",      "brand": "Bettinardi",     "model": "BB",             "type": "putter",     "max": 400},
    {"query": "Titleist TSR2 driver",      "brand": "Titleist",       "model": "TSR2",           "type": "driver",     "max": 400},
    {"query": "Titleist TSR3 driver",      "brand": "Titleist",       "model": "TSR3",           "type": "driver",     "max": 420},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


# ── Duplicate detection ───────────────────────────────────────────────────────

def _already_seen(item_id: str) -> bool:
    try:
        c = _conn()
        row = c.execute("SELECT id FROM deals WHERE raw_json LIKE ?",
                        (f"%{item_id}%",)).fetchone()
        c.close()
        return row is not None
    except Exception:
        return False


def _make_id(source: str, url: str, price: float) -> str:
    return hashlib.md5(f"{source}{url}{price}".encode()).hexdigest()[:16]


# ── SidelineSwap scanner ──────────────────────────────────────────────────────

def _search_sidelineswap(query: str, max_price: float) -> list[dict]:
    """
    Fetch public SidelineSwap search results.
    SidelineSwap is a public marketplace — no login required to browse.
    We read the same data a browser would see when searching their site.
    """
    results = []
    try:
        encoded = requests.utils.quote(query)
        url = f"https://sidelineswap.com/search?query={encoded}&sport=golf"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return []

        # SidelineSwap embeds listing data in a __NEXT_DATA__ JSON block
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            r.text, re.DOTALL
        )
        if not match:
            # Fallback: try to find price/title patterns in HTML
            return _parse_sidelineswap_html(r.text, max_price, query)

        data = json.loads(match.group(1))

        # Navigate to items in the JSON structure
        items = []
        try:
            props = data.get("props", {}).get("pageProps", {})
            items = (props.get("items") or
                     props.get("searchResults", {}).get("items") or
                     props.get("results", {}).get("items") or [])
        except Exception:
            pass

        for item in items:
            try:
                price = float(item.get("price", 0) or item.get("asking_price", 0) or 0)
                if price <= 0 or price > max_price:
                    continue
                title     = item.get("name", "") or item.get("title", "")
                item_url  = f"https://sidelineswap.com/gear/{item.get('id','')}"
                item_id   = str(item.get("id", _make_id("sls", item_url, price)))
                condition = item.get("condition", {})
                if isinstance(condition, dict):
                    condition = condition.get("name", "Good")
                image_url = ""
                photos = item.get("photos", [])
                if photos and isinstance(photos, list):
                    image_url = photos[0].get("url", "") if isinstance(photos[0], dict) else ""

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
                continue

    except requests.exceptions.Timeout:
        pass
    except Exception:
        pass

    return results


def _parse_sidelineswap_html(html: str, max_price: float, query: str) -> list[dict]:
    """Fallback HTML parser if JSON extraction fails."""
    results = []
    try:
        # Look for price patterns like $149.99 or $149
        price_pattern = re.findall(r'\$(\d+(?:\.\d{2})?)', html)
        prices = [float(p) for p in price_pattern if 10 < float(p) < max_price]
        if prices:
            # We found some prices — create a generic result
            for i, price in enumerate(prices[:5]):
                results.append({
                    "title":        f"{query} - SidelineSwap listing",
                    "asking_price": price,
                    "shipping_cost": 0,
                    "condition":    "Good",
                    "listing_url":  f"https://sidelineswap.com/search?query={requests.utils.quote(query)}&sport=golf",
                    "image_url":    "",
                    "item_id":      f"sls_fallback_{query}_{i}_{price}",
                    "source":       "SidelineSwap",
                })
    except Exception:
        pass
    return results


# ── eBay scanner ──────────────────────────────────────────────────────────────

def _get_ebay_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    if not EBAY_APP_ID:
        return ""
    try:
        r = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials",
                  "scope": "https://api.ebay.com/oauth/api_scope"},
            auth=(EBAY_APP_ID, EBAY_CERT_ID), timeout=10
        )
        r.raise_for_status()
        d = r.json()
        _token_cache["token"] = d["access_token"]
        _token_cache["expires_at"] = time.time() + d["expires_in"]
        return d["access_token"]
    except Exception:
        return ""


def _search_ebay(query: str, max_price: float) -> list[dict]:
    token = _get_ebay_token()
    if not token:
        return []
    try:
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {token}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params={"q": query, "category_ids": "1513",
                    "filter": f"price:[10..{max_price}],priceCurrency:USD",
                    "sort": "newlyListed", "limit": 30},
            timeout=15
        )
        r.raise_for_status()
        items = r.json().get("itemSummaries", [])
        return [{
            "title":        i.get("title", ""),
            "asking_price": float(i.get("price", {}).get("value", 0)),
            "shipping_cost": float((i.get("shippingOptions") or [{}])[0]
                                   .get("shippingCost", {}).get("value", 0)),
            "condition":    i.get("condition", "Good"),
            "listing_url":  i.get("itemWebUrl", ""),
            "image_url":    i.get("image", {}).get("imageUrl", ""),
            "item_id":      f"ebay_{i.get('itemId','')}",
            "source":       "eBay",
        } for i in items if float(i.get("price", {}).get("value", 0)) > 5]
    except Exception:
        return []


# ── Main scan function ────────────────────────────────────────────────────────

def run_scan() -> list[dict]:
    """
    Run a full scan across SidelineSwap and eBay (if keys available).
    Returns list of new deals found and saved.
    """
    new_deals = []
    sources_tried = []
    sources_found = []

    for target in SCAN_TARGETS:
        all_listings = []

        # Always try SidelineSwap (no API key needed)
        sls_listings = _search_sidelineswap(target["query"], target["max"])
        if sls_listings:
            sources_found.append("SidelineSwap")
        all_listings.extend(sls_listings)
        sources_tried.append("SidelineSwap")

        # Try eBay if keys available
        if EBAY_APP_ID:
            ebay_listings = _search_ebay(target["query"], target["max"])
            if ebay_listings:
                sources_found.append("eBay")
            all_listings.extend(ebay_listings)
            sources_tried.append("eBay")

        for listing in all_listings:
            item_id = listing.get("item_id", "")
            if item_id and _already_seen(item_id):
                continue

            total_price = listing["asking_price"] + listing.get("shipping_cost", 0)

            lookup_result = lookup_club({
                "brand":        target["brand"],
                "model":        target["model"],
                "condition":    listing.get("condition", "Good"),
                "asking_price": total_price,
                "club_type":    target["type"],
            })

            if lookup_result.get("error"):
                continue

            scored = score_deal(lookup_result)

            if scored["score"] < MIN_SCORE_TO_SAVE:
                continue

            deal = {
                **lookup_result,
                **scored,
                "title":       listing["title"] or f"{target['brand']} {target['model']}",
                "source":      listing["source"],
                "listing_url": listing["listing_url"],
                "image_url":   listing.get("image_url", ""),
                "brand":       target["brand"],
                "model":       target["model"],
                "club_type":   target["type"],
                "item_id":     item_id,
            }

            save_deal(deal)
            new_deals.append(deal)

            if scored["score"] >= MIN_SCORE_TO_ALERT:
                send_discord_alert(deal)

        time.sleep(0.5)  # respectful rate limiting

    return new_deals
