"""
lookup.py
---------
Core lookup engine. Given a brand/model/condition/price,
returns market value, comparables, sell speed, counterfeit flags,
offer suggestion, and platform recommendations.
"""

import os, requests, statistics
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

EBAY_APP_ID  = os.getenv("EBAY_APP_ID","")
EBAY_CERT_ID = os.getenv("EBAY_CERT_ID","")

# Also check Streamlit secrets when deployed on Streamlit Cloud
try:
    import streamlit as st
    EBAY_APP_ID  = EBAY_APP_ID  or st.secrets.get("EBAY_APP_ID", "")
    EBAY_CERT_ID = EBAY_CERT_ID or st.secrets.get("EBAY_CERT_ID", "")
except Exception:
    pass

_token_cache: dict = {"token": None, "expires_at": 0}

# ── Brand demand & sell speed data ───────────────────────────────────────────
BRAND_DATA = {
    "scotty cameron": {"demand": 10, "sell_days": "1-3 days",  "counterfeit_risk": True,  "min_legit_price": 150},
    "titleist":       {"demand":  9, "sell_days": "3-7 days",  "counterfeit_risk": False, "min_legit_price": 0},
    "taylormade":     {"demand":  9, "sell_days": "3-7 days",  "counterfeit_risk": False, "min_legit_price": 0},
    "callaway":       {"demand":  8, "sell_days": "3-7 days",  "counterfeit_risk": False, "min_legit_price": 0},
    "ping":           {"demand":  8, "sell_days": "5-10 days", "counterfeit_risk": False, "min_legit_price": 0},
    "mizuno":         {"demand":  8, "sell_days": "5-10 days", "counterfeit_risk": False, "min_legit_price": 0},
    "vokey":          {"demand":  8, "sell_days": "3-7 days",  "counterfeit_risk": False, "min_legit_price": 0},
    "odyssey":        {"demand":  7, "sell_days": "5-10 days", "counterfeit_risk": False, "min_legit_price": 0},
    "bettinardi":     {"demand":  8, "sell_days": "5-10 days", "counterfeit_risk": True,  "min_legit_price": 120},
    "cobra":          {"demand":  7, "sell_days": "7-14 days", "counterfeit_risk": False, "min_legit_price": 0},
    "srixon":         {"demand":  7, "sell_days": "7-14 days", "counterfeit_risk": False, "min_legit_price": 0},
    "cleveland":      {"demand":  7, "sell_days": "5-10 days", "counterfeit_risk": False, "min_legit_price": 0},
    "pxg":            {"demand":  7, "sell_days": "7-14 days", "counterfeit_risk": False, "min_legit_price": 0},
}

CONDITION_MULT = {
    "mint":      1.05, "excellent": 1.00, "very good": 0.92,
    "good":      0.85, "fair":      0.70, "poor":      0.50,
}

CLUB_SHIPPING = {
    "driver": 22, "fairway wood": 20, "hybrid": 18, "iron set": 35,
    "wedge": 14, "putter": 18, "bag": 45, "rangefinder": 12, "shaft": 14,
}

PLATFORM_FEES = {
    "eBay":          0.1335,
    "SidelineSwap":  0.09,
    "Facebook":      0.05,
}

SELL_PLATFORMS_BY_TYPE = {
    "putter":       ["eBay", "SidelineSwap", "Facebook"],
    "driver":       ["eBay", "SidelineSwap", "Facebook"],
    "iron set":     ["eBay", "Facebook", "SidelineSwap"],
    "wedge":        ["eBay", "SidelineSwap", "Facebook"],
    "fairway wood": ["eBay", "SidelineSwap"],
    "hybrid":       ["eBay", "SidelineSwap"],
    "rangefinder":  ["eBay", "Facebook"],
    "bag":          ["Facebook", "eBay"],
}

# Counterfeit model keywords
COUNTERFEIT_MODELS = [
    "newport", "phantom", "special select", "golo", "bb1", "studio",
    "futura", "bb zero", "studio stock",
]


def _get_ebay_token() -> str:
    import time
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
        return _token_cache["token"]
    except Exception:
        return ""


def _fetch_ebay_comparables(brand: str, model: str, club_type: str) -> list[dict]:
    token = _get_ebay_token()
    if not token:
        return _fallback_comparables(brand, model)
    try:
        headers = {"Authorization": f"Bearer {token}",
                   "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers=headers,
            params={"q": f"{brand} {model}", "category_ids": "1513",
                    "filter": "buyingOptions:{FIXED_PRICE}", "limit": 20,
                    "sort": "price"},
            timeout=12
        )
        r.raise_for_status()
        items = r.json().get("itemSummaries", [])
        return [{"price":  float(i.get("price",{}).get("value",0)),
                 "condition": i.get("condition",""),
                 "date":   i.get("itemCreationDate","")[:10],
                 "source": "eBay",
                 "url":    i.get("itemWebUrl","")}
                for i in items if float(i.get("price",{}).get("value",0)) > 5]
    except Exception:
        return _fallback_comparables(brand, model)


def _fallback_comparables(brand: str, model: str) -> list[dict]:
    """
    Static fallback price data when API isn't available.
    Covers the most commonly flipped clubs.
    """
    fallback = {
        ("scotty cameron", "newport 2"):        [280, 320, 295, 310, 340, 275, 300],
        ("scotty cameron", "newport"):          [220, 250, 235, 260, 245, 230, 270],
        ("scotty cameron", "phantom x"):        [350, 380, 420, 395, 370, 410, 360],
        ("scotty cameron", "special select"):   [300, 330, 315, 350, 290, 320, 340],
        ("titleist", "t100"):                   [550, 600, 580, 620, 560, 590, 610],
        ("titleist", "t200"):                   [480, 520, 500, 540, 490, 510, 530],
        ("titleist", "tsr2"):                   [280, 310, 295, 320, 270, 300, 315],
        ("titleist", "tsr3"):                   [300, 340, 320, 360, 310, 330, 350],
        ("taylormade", "stealth"):              [200, 240, 220, 250, 210, 230, 245],
        ("taylormade", "qi10"):                 [300, 340, 320, 360, 310, 330, 350],
        ("taylormade", "p790"):                 [600, 650, 620, 670, 590, 640, 660],
        ("taylormade", "p770"):                 [550, 600, 570, 620, 540, 580, 610],
        ("callaway", "paradym"):                [260, 300, 280, 320, 270, 290, 310],
        ("callaway", "apex"):                   [500, 550, 520, 570, 490, 530, 560],
        ("ping", "g430"):                       [220, 260, 240, 270, 230, 250, 265],
        ("mizuno", "jpx 923"):                  [480, 520, 500, 540, 470, 510, 530],
        ("vokey", "sm9"):                       [100, 130, 115, 140, 105, 120, 135],
        ("vokey", "sm8"):                       [80,  110, 95,  120, 85,  100, 115],
        ("odyssey", "white hot"):               [80,  110, 95,  120, 85,  100, 115],
        ("bettinardi", "bb1"):                  [180, 220, 200, 240, 190, 210, 230],
    }
    key = (brand.lower().strip(), model.lower().strip())
    prices = fallback.get(key, [])
    if not prices:
        for k, v in fallback.items():
            if k[0] == brand.lower() and k[1] in model.lower():
                prices = v
                break
    return [{"price": p, "condition": "Good", "date": "recent", "source": "Historical data"}
            for p in prices]


def _counterfeit_check(brand: str, model: str, asking_price: float) -> tuple[bool, str]:
    brand_key = brand.lower().strip()
    data = BRAND_DATA.get(brand_key, {})
    if not data.get("counterfeit_risk"):
        return False, ""
    min_price = data.get("min_legit_price", 0)
    model_lower = model.lower()
    is_risky_model = any(m in model_lower for m in COUNTERFEIT_MODELS)
    if asking_price < min_price * 0.5:
        return True, (f"Price ${asking_price:.0f} is extremely low for authentic "
                      f"{brand}. Genuine examples sell for ${min_price}+. "
                      f"Inspect serial number and headcover carefully.")
    if asking_price < min_price * 0.65 and is_risky_model:
        return True, (f"Price seems low for a genuine {brand} {model}. "
                      f"Verify authenticity — check font, serial number, and finish quality.")
    return False, ""


def _offer_price(asking: float, market: float, days_listed: int = 0) -> float:
    if market <= 0:
        return asking * 0.8
    target_cost = market * 0.55
    if days_listed > 14:
        target_cost = market * 0.50
    return round(min(asking * 0.85, max(target_cost, asking * 0.70)), 0)


def lookup_club(info: dict) -> dict:
    brand     = info.get("brand","").strip()
    model     = info.get("model","").strip()
    condition = info.get("condition","Good").lower()
    asking    = float(info.get("asking_price", 0))
    club_type = info.get("club_type","").lower()

    if not brand or not model:
        return {"error": "Brand and model required"}

    # Get comparables
    comps = _fetch_ebay_comparables(brand, model, club_type)
    prices = [c["price"] for c in comps if c["price"] > 10]

    if not prices:
        return {"error": f"No price data found for {brand} {model}"}

    median_price   = statistics.median(prices)
    cond_mult      = CONDITION_MULT.get(condition, 0.85)
    market_value   = round(median_price * cond_mult, 2)

    # Counterfeit check
    fake_flag, fake_reason = _counterfeit_check(brand, model, asking)

    # Offer suggestion
    offer = _offer_price(asking, market_value)

    # Brand data
    brand_info = BRAND_DATA.get(brand.lower(), {"demand": 5, "sell_days": "7-14 days"})
    sell_speed = brand_info["sell_days"]

    # Platform recommendations
    platforms_order = SELL_PLATFORMS_BY_TYPE.get(club_type, ["eBay", "SidelineSwap"])
    ship_out = CLUB_SHIPPING.get(club_type, 20)
    sell_platforms = []
    for p in platforms_order:
        fee    = PLATFORM_FEES.get(p, 0.10)
        net    = round(market_value * (1 - fee) - ship_out, 2)
        days   = {"eBay": "3-7", "SidelineSwap": "5-10", "Facebook": "1-5"}.get(p, "5-10")
        sell_platforms.append({"name": p, "price": market_value, "net": net, "days": days})
    sell_platforms.sort(key=lambda x: x["net"], reverse=True)

    return {
        "brand":          brand,
        "model":          model,
        "club_type":      club_type,
        "condition":      condition,
        "asking_price":   asking,
        "market_value":   market_value,
        "median_comp":    median_price,
        "comparables":    comps[:10],
        "sell_speed":     sell_speed,
        "fake_flag":      fake_flag,
        "fake_reason":    fake_reason,
        "offer_price":    offer,
        "sell_platforms": sell_platforms,
        "ship_out":       ship_out,
    }
