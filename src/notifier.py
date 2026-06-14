"""notifier.py — Discord alert system"""
import os, requests
from dotenv import load_dotenv
load_dotenv()

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

GRADE_EMOJI = {"S": "🟣", "A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}

def send_discord_alert(deal: dict):
    if not DISCORD_WEBHOOK:
        return
    grade  = deal.get("grade","?")
    profit = deal.get("est_profit", 0)
    score  = deal.get("deal_score", deal.get("score", 0))
    emoji  = GRADE_EMOJI.get(grade, "⚪")
    fake   = "⚠️ COUNTERFEIT RISK\n" if deal.get("fake_flag") else ""

    msg = (
        f"{emoji} **GOLF FLIP ALERT — Grade {grade} ({score}/100)**\n"
        f"**{deal.get('title','')[:60]}**\n"
        f"Source: {deal.get('source','').upper()}\n"
        f"Ask: **${deal.get('asking_price',0):.0f}** → "
        f"Resale: **${deal.get('est_resale', deal.get('market_value',0)):.0f}**\n"
        f"Est. profit: **${profit:.0f}** · ROI: **{deal.get('roi_pct',0):.0f}%**\n"
        f"Sells in: {deal.get('sell_speed','?')}\n"
        f"{fake}"
        f"{deal.get('recommendation','')}\n"
        f"{deal.get('listing_url','')}"
    )
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=8)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
"""listing_helper.py — Auto-generate sell listings"""

from datetime import datetime

LISTING_TEMPLATES = {
    "putter": {
        "title_format": "{brand} {model} Putter {hand} Handed {condition} Condition",
        "description": (
            "Up for sale is a {condition} condition {brand} {model} putter.\n\n"
            "✅ Ships same day or next business day\n"
            "✅ Carefully packaged with bubble wrap and box\n"
            "✅ 100% authentic\n\n"
            "Details:\n"
            "- Brand: {brand}\n"
            "- Model: {model}\n"
            "- Condition: {condition}\n"
            "- Hand: {hand}\n\n"
            "Message with any questions. Thanks for looking!"
        ),
    },
    "driver": {
        "title_format": "{brand} {model} Driver {condition} Condition",
        "description": (
            "Selling my {brand} {model} driver in {condition} condition.\n\n"
            "✅ Fast shipping — same or next day\n"
            "✅ Securely packaged\n\n"
            "Specs:\n"
            "- Brand: {brand}\n"
            "- Model: {model}\n"
            "- Condition: {condition}\n\n"
            "Feel free to ask questions!"
        ),
    },
    "iron set": {
        "title_format": "{brand} {model} Iron Set {condition} Condition",
        "description": (
            "{brand} {model} iron set in {condition} condition.\n\n"
            "✅ Full set included\n"
            "✅ Ships carefully packaged\n\n"
            "- Brand: {brand}\n"
            "- Model: {model}\n"
            "- Condition: {condition}\n\n"
            "Message with questions!"
        ),
    },
}

BEST_POST_TIMES = {
    "ebay":         "Thursday or Sunday evening, 7–9 PM Eastern",
    "sidelineswap": "Tuesday or Wednesday morning, 8–10 AM Eastern",
    "facebook":     "Saturday morning, 9–11 AM local time",
}


def generate_listing(deal: dict) -> dict:
    brand     = deal.get("brand","")
    model     = deal.get("model","")
    club_type = deal.get("club_type","driver").lower()
    condition = deal.get("condition","Good")
    hand      = deal.get("hand","Right")
    price     = deal.get("est_resale", deal.get("market_value", 0))

    template = LISTING_TEMPLATES.get(club_type, LISTING_TEMPLATES["driver"])
    fields   = {"brand": brand, "model": model, "condition": condition, "hand": hand}

    title       = template["title_format"].format(**fields)
    description = template["description"].format(**fields)

    # Best platform
    platforms = deal.get("sell_platforms", [])
    platform  = platforms[0]["name"] if platforms else "eBay"

    return {
        "title":       title,
        "description": description,
        "price":       round(price * 0.97, 0),  # slight buffer for offers
        "platform":    platform,
        "best_time":   BEST_POST_TIMES.get(platform.lower(), "Thursday or Sunday evening"),
    }
