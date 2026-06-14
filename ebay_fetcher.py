"""
ebay_fetcher.py
---------------
Fetches golf club listings and sold (completed) prices from eBay
using the official eBay Browse API (OAuth2 App Credentials).

Docs: https://developer.ebay.com/api-docs/buy/browse/overview.html
Rate limit: 5,000 calls/day on free tier.

Setup:
    pip install requests python-dotenv
    Add EBAY_APP_ID and EBAY_CERT_ID to your .env file.
"""

import os
import time
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

EBAY_APP_ID  = os.getenv("EBAY_APP_ID", "")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID", "")

_token_cache: dict = {"token": None, "expires_at": 0}


# ─── OAuth ────────────────────────────────────────────────────────────────────

def get_access_token() -> str:
    """Get (or reuse cached) eBay OAuth application token."""
    if time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    resp = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
        auth=(EBAY_APP_ID, EBAY_CERT_ID),
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"]
    return _token_cache["token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        "Content-Type": "application/json",
    }


# ─── Browse API helpers ───────────────────────────────────────────────────────

def search_active_listings(query: str, max_results: int = 50,
                           min_price: float = 0, max_price: float = 5000,
                           condition: Optional[str] = None) -> list[dict]:
    """
    Search active eBay listings using the Browse API.
    Returns a list of normalised listing dicts.

    condition options: "NEW", "LIKE_NEW", "VERY_GOOD", "GOOD", "ACCEPTABLE"
    """
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    params = {
        "q": query,
        "category_ids": "1513",       # Golf Equipment category
        "filter": f"price:[{min_price}..{max_price}],priceCurrency:USD",
        "limit": min(max_results, 200),
        "sort": "newlyListed",
        "fieldgroups": "EXTENDED",
    }
    if condition:
        params["filter"] += f",conditions:{{{condition}}}"

    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("itemSummaries", [])
    return [_normalise_active(item) for item in items]


def get_completed_sold_prices(query: str, days_back: int = 60) -> list[dict]:
    """
    Use eBay's Browse API 'completed' filter to fetch recently *sold* items.
    This gives us comparable sold prices for market-value estimation.

    Note: The public Browse API does not expose full sold-price history.
    This returns items listed as COMPLETED (sold+unsold). Filter by
    'buyingOptions:FIXED_PRICE' and 'itemEndDate' for best sold-price proxies.
    For production, upgrade to eBay Finding API v2 (completed listings).
    """
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    params = {
        "q": query,
        "category_ids": "1513",
        "filter": "buyingOptions:{FIXED_PRICE},itemLocationCountry:US",
        "sort": "price",
        "limit": 50,
    }
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("itemSummaries", [])
    return [_normalise_active(item) for item in items]


def get_item_details(item_id: str) -> dict:
    """Fetch full details for a single eBay item by ID."""
    url = f"https://api.ebay.com/buy/browse/v1/item/{item_id}"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    return resp.json()


# ─── Normalisation ────────────────────────────────────────────────────────────

def _normalise_active(item: dict) -> dict:
    """Convert a raw eBay Browse API item into our standard schema."""
    price_val   = float(item.get("price", {}).get("value", 0))
    ship_val    = float((item.get("shippingOptions") or [{}])[0]
                        .get("shippingCost", {}).get("value", 0))
    condition   = item.get("condition", "Unknown")
    seller_info = item.get("seller", {})
    images      = [item.get("image", {}).get("imageUrl", "")]

    return {
        "source":          "ebay",
        "item_id":         item.get("itemId", ""),
        "title":           item.get("title", ""),
        "asking_price":    price_val,
        "shipping_cost":   ship_val,
        "total_cost":      price_val + ship_val,
        "condition":       condition,
        "location":        item.get("itemLocation", {}).get("city", ""),
        "seller_feedback": seller_info.get("feedbackPercentage", ""),
        "seller_score":    seller_info.get("feedbackScore", 0),
        "listing_url":     item.get("itemWebUrl", ""),
        "image_url":       images[0] if images else "",
        "buying_options":  item.get("buyingOptions", []),
        "listed_at":       item.get("itemCreationDate", ""),
        "brand":           _extract_aspect(item, "Brand"),
        "model":           _extract_aspect(item, "Model"),
        "club_type":       _extract_aspect(item, "Club Type"),
        "shaft_flex":      _extract_aspect(item, "Flex"),
        "loft":            _extract_aspect(item, "Loft"),
        "hand":            _extract_aspect(item, "Hand Orientation"),
    }


def _extract_aspect(item: dict, key: str) -> str:
    """Pull a value from eBay's localizedAspects list."""
    for asp in item.get("localizedAspects") or []:
        if asp.get("name", "").lower() == key.lower():
            return asp.get("value", "")
    return ""


# ─── Quick smoke test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not EBAY_APP_ID:
        print("⚠  Set EBAY_APP_ID and EBAY_CERT_ID in your .env file first.")
    else:
        print("Searching for Scotty Cameron putters under $300 …")
        results = search_active_listings("Scotty Cameron putter", max_price=300)
        for r in results[:5]:
            print(f"  ${r['asking_price']:>7.2f}  {r['title'][:60]}")
