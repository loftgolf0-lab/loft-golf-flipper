"""listing_helper.py — Auto-generate sell listings"""

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
    "wedge": {
        "title_format": "{brand} {model} Wedge {condition} Condition",
        "description": (
            "{brand} {model} wedge in {condition} condition.\n\n"
            "✅ Ships fast, packaged securely\n\n"
            "- Brand: {brand}\n"
            "- Model: {model}\n"
            "- Condition: {condition}\n\n"
            "Questions welcome!"
        ),
    },
}

BEST_POST_TIMES = {
    "ebay":         "Thursday or Sunday evening, 7–9 PM Eastern",
    "sidelineswap": "Tuesday or Wednesday morning, 8–10 AM Eastern",
    "facebook":     "Saturday morning, 9–11 AM local time",
}


def generate_listing(deal: dict) -> dict:
    brand     = deal.get("brand", "")
    model     = deal.get("model", "")
    club_type = deal.get("club_type", "driver").lower()
    condition = deal.get("condition", "Good")
    hand      = deal.get("hand", "Right")
    price     = deal.get("est_resale", deal.get("market_value", 0))

    template  = LISTING_TEMPLATES.get(club_type, LISTING_TEMPLATES["driver"])
    fields    = {"brand": brand, "model": model, "condition": condition, "hand": hand}

    title       = template["title_format"].format(**fields)
    description = template["description"].format(**fields)

    platforms = deal.get("sell_platforms", [])
    platform  = platforms[0]["name"] if platforms else "eBay"

    return {
        "title":       title,
        "description": description,
        "price":       round(price * 0.97, 0),
        "platform":    platform,
        "best_time":   BEST_POST_TIMES.get(platform.lower(), "Thursday or Sunday evening"),
    }
