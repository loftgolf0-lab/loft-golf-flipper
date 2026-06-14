"""scanner.py — Automatic deal scanner"""
import os, requests, time
from dotenv import load_dotenv
from lookup import lookup_club
from scorer import score_deal
from database import save_deal, _conn
from notifier import send_discord_alert

load_dotenv()

EBAY_APP_ID  = os.getenv("EBAY_APP_ID","")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID","")
_token_cache: dict = {"token": None, "expires_at": 0}

# What to scan for
SCAN_TARGETS = [
    {"query": "Scotty Cameron putter",    "brand": "Scotty Cameron", "type": "putter",      "max": 500},
    {"query": "Titleist T100 irons",      "brand": "Titleist",       "type": "iron set",    "max": 700},
    {"query": "TaylorMade P790 irons",    "brand": "TaylorMade",     "type": "iron set",    "max": 700},
    {"query": "TaylorMade Stealth driver","brand": "TaylorMade",     "type": "driver",      "max": 350},
    {"query": "TaylorMade Qi10 driver",   "brand": "TaylorMade",     "type": "driver",      "max": 450},
    {"query": "Callaway Paradym driver",  "brand": "Callaway",       "type": "driver",      "max": 400},
    {"query": "Titleist Vokey SM9 wedge", "brand": "Vokey",          "type": "wedge",       "max": 180},
    {"query": "Ping G430 irons",          "brand": "Ping",           "type": "iron set",    "max": 500},
    {"query": "Mizuno JPX 923 irons",     "brand": "Mizuno",         "type": "iron set",    "max": 600},
    {"query": "Bettinardi putter",        "brand": "Bettinardi",     "type": "putter",      "max": 400},
    {"query": "Titleist TSR driver",      "brand": "Titleist",       "type": "driver",      "max": 400},
]

MIN_SCORE_TO_SAVE  = 55   # Grade B or better
MIN_SCORE_TO_ALERT = 70   # Grade A or better


def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    if not EBAY_APP_ID:
        return ""
    try:
        r = requests.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={"Content-Type":"application/x-www-form-urlencoded"},
            data={"grant_type":"client_credentials",
                  "scope":"https://api.ebay.com/oauth/api_scope"},
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
    token = _get_token()
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
            "title":        i.get("title",""),
            "asking_price": float(i.get("price",{}).get("value",0)),
            "shipping_cost":float((i.get("shippingOptions") or [{}])[0].get("shippingCost",{}).get("value",0)),
            "condition":    i.get("condition","Good"),
            "listing_url":  i.get("itemWebUrl",""),
            "image_url":    i.get("image",{}).get("imageUrl",""),
            "item_id":      i.get("itemId",""),
            "source":       "eBay",
        } for i in items if float(i.get("price",{}).get("value",0)) > 5]
    except Exception:
        return []


def _already_seen(item_id: str) -> bool:
    c = _conn()
    row = c.execute("SELECT id FROM deals WHERE raw_json LIKE ?",
                    (f'%{item_id}%',)).fetchone()
    c.close()
    return row is not None


def run_scan() -> list[dict]:
    """Run a full scan across all targets. Returns list of new deals found."""
    new_deals = []
    for target in SCAN_TARGETS:
        listings = _search_ebay(target["query"], target["max"])
        for listing in listings:
            if _already_seen(listing.get("item_id","")):
                continue
            # Score it
            lookup_result = lookup_club({
                "brand":        target["brand"],
                "model":        target["query"].replace(target["brand"],"").strip(),
                "condition":    listing.get("condition","Good"),
                "asking_price": listing["asking_price"] + listing.get("shipping_cost",0),
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
                "title":       listing["title"],
                "source":      "eBay",
                "listing_url": listing["listing_url"],
                "image_url":   listing["image_url"],
                "brand":       target["brand"],
                "club_type":   target["type"],
                "raw_item_id": listing.get("item_id",""),
            }
            save_deal(deal)
            new_deals.append(deal)

            if scored["score"] >= MIN_SCORE_TO_ALERT:
                send_discord_alert(deal)

        time.sleep(0.3)  # gentle rate limiting

    return new_deals
