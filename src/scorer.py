"""scorer.py — Deal scoring engine"""
import statistics

GRADE_THRESHOLDS = {"S": 85, "A": 70, "B": 55, "C": 40, "D": 25}

BRAND_DEMAND = {
    "scotty cameron": 10, "titleist": 9, "taylormade": 9, "callaway": 8,
    "ping": 8, "mizuno": 8, "vokey": 8, "odyssey": 7, "bettinardi": 8,
    "cobra": 7, "srixon": 7, "cleveland": 7, "pxg": 7,
}

CLUB_EASE = {
    "putter": 9, "driver": 8, "iron set": 8, "wedge": 8,
    "fairway wood": 7, "hybrid": 6, "rangefinder": 7, "bag": 5, "shaft": 6,
}

COND_MULT = {
    "mint": 1.05, "excellent": 1.0, "very good": 0.92,
    "good": 0.85, "fair": 0.70, "poor": 0.50,
}

EBAY_FEE_PCT   = 0.1335
PAYMENT_FEE    = 0.03
INSERTION_FEE  = 0.35

SHIP_OUT = {
    "driver": 22, "fairway wood": 20, "hybrid": 18, "iron set": 35,
    "wedge": 14, "putter": 18, "bag": 45, "rangefinder": 12, "shaft": 14,
}

CLEAN_COST = {"iron set": 15, "driver": 8, "putter": 5, "wedge": 5}

RECOMMENDATIONS = {
    "S": "🟢 BUY THIS NOW — exceptional deal, act fast",
    "A": "🟢 Strong buy — solid profit with low risk",
    "B": "🟡 Good deal — worth pursuing, verify condition",
    "C": "🟠 Marginal — negotiate price down first",
    "D": "🔴 Weak — only at a much lower price",
    "F": "🔴 Pass — not enough margin",
}


def score_deal(result: dict) -> dict:
    asking      = float(result.get("asking_price", 0))
    market      = float(result.get("market_value", 0))
    brand       = result.get("brand","").lower()
    club_type   = result.get("club_type","").lower()
    condition   = result.get("condition","good").lower()
    sell_speed  = result.get("sell_speed","7-14 days")
    fake_flag   = result.get("fake_flag", False)

    if market <= 0 or asking <= 0:
        return {"score": 0, "grade": "F", "est_profit": 0, "roi_pct": 0,
                "recommendation": RECOMMENDATIONS["F"], "profit_breakdown": {}}

    # Sub-scores (all 0.0 – 1.0)
    margin_ratio  = (market - asking) / market
    margin_score  = min(1.0, max(0.0, margin_ratio * 2))

    brand_score   = BRAND_DEMAND.get(brand, 5) / 10
    ease_score    = CLUB_EASE.get(club_type, 5) / 10
    cond_score    = COND_MULT.get(condition, 0.85)

    speed_score = 1.0
    if "1-3" in sell_speed:   speed_score = 1.0
    elif "3-7" in sell_speed: speed_score = 0.85
    elif "5-10" in sell_speed:speed_score = 0.70
    else:                      speed_score = 0.50

    fake_penalty  = 0.5 if fake_flag else 1.0

    weighted = (
        margin_score * 40 +
        brand_score  * 15 +
        ease_score   * 10 +
        cond_score   * 15 +
        speed_score  * 20
    ) * fake_penalty

    score = max(0, min(100, round(weighted)))
    grade = "F"
    for g, threshold in GRADE_THRESHOLDS.items():
        if score >= threshold:
            grade = g
            break

    # Profit calc
    ship_out   = SHIP_OUT.get(club_type, 20)
    clean      = CLEAN_COST.get(club_type, 5)
    ebay_fees  = round(market * (EBAY_FEE_PCT + PAYMENT_FEE) + INSERTION_FEE, 2)
    total_cost = round(asking + clean, 2)
    net_profit = round(market - total_cost - ebay_fees - ship_out, 2)
    roi        = round((net_profit / max(total_cost, 1)) * 100, 1)
    break_even = round(total_cost + ebay_fees + ship_out, 2)

    risk = "LOW" if score >= 70 and not fake_flag else \
           "MEDIUM" if score >= 50 else \
           "HIGH" if score >= 30 else "VERY HIGH"

    return {
        "score":          score,
        "grade":          grade,
        "est_profit":     net_profit,
        "est_resale":     market,
        "roi_pct":        roi,
        "risk_level":     risk,
        "recommendation": RECOMMENDATIONS.get(grade, RECOMMENDATIONS["F"]),
        "profit_breakdown": {
            "ebay_fees":    ebay_fees,
            "shipping_out": ship_out,
            "cleaning":     clean,
            "break_even":   break_even,
        }
    }
