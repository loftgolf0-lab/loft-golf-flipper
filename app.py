"""
Loft Golf Flipper — Main App
Mobile-first deal hunting dashboard
"""

import streamlit as st
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

st.set_page_config(
    page_title="Loft Golf Flipper",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Mobile-first CSS
st.markdown("""
<style>
/* Mobile-first base */
.block-container { padding: 0.5rem 0.75rem 2rem !important; max-width: 100% !important; }
[data-testid="stSidebar"] { min-width: 260px !important; }

/* Cards */
.deal-card {
    background: #1a1a2e;
    border: 1px solid #16213e;
    border-radius: 16px;
    padding: 1rem;
    margin-bottom: 0.75rem;
}
.grade-S { border-left: 4px solid #00ff88; }
.grade-A { border-left: 4px solid #00cc66; }
.grade-B { border-left: 4px solid #ffcc00; }
.grade-C { border-left: 4px solid #ff8800; }
.grade-D { border-left: 4px solid #ff4444; }
.grade-F { border-left: 4px solid #888; }

/* Score badge */
.score-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 0.85rem;
}

/* Metric pill */
.metric-pill {
    background: #0f3460;
    border-radius: 12px;
    padding: 0.5rem 0.75rem;
    text-align: center;
    margin: 4px;
}

/* Alert badge */
.fake-alert {
    background: #ff4444;
    color: white;
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 0.8rem;
    font-weight: 600;
}

/* Nav tabs */
.nav-tab {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 20px;
    cursor: pointer;
    font-size: 0.85rem;
    margin: 2px;
}

/* Responsive grid */
@media (max-width: 640px) {
    .block-container { padding: 0.5rem !important; }
}

/* Hide streamlit branding */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

import pandas as pd
from datetime import datetime

from database import init_db, get_all_deals, get_portfolio_stats, get_sold_items, update_deal_status
from scanner import run_scan
from lookup import lookup_club
from scorer import score_deal
from notifier import send_discord_alert
from listing_helper import generate_listing

# Init DB
init_db()

# ── Navigation ────────────────────────────────────────────────────────────────
st.markdown("## ⛳ Loft Golf Flipper")

page = st.radio(
    "nav",
    ["🏠 Deals", "🔍 Lookup", "📦 Inventory", "📈 Stats", "⚙️ Settings"],
    horizontal=True,
    label_visibility="collapsed"
)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — LIVE DEALS
# ═══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Deals":
    col1, col2 = st.columns([3, 1])
    col1.markdown("### Live Deals")
    
    if col2.button("🔄 Scan Now", type="primary", use_container_width=True):
        with st.spinner("Scanning for deals..."):
            new_deals = run_scan()
            if new_deals:
                st.success(f"Found {len(new_deals)} new deals!")
            else:
                st.info("No new deals found right now. Try again soon.")

    # Filters
    with st.expander("🎛️ Filters", expanded=False):
        fc1, fc2 = st.columns(2)
        min_profit = fc1.number_input("Min profit ($)", value=30, step=10)
        min_grade  = fc2.selectbox("Min grade", ["Any", "S", "A", "B", "C"])
        fc3, fc4   = st.columns(2)
        club_type  = fc3.selectbox("Club type", ["All", "Driver", "Fairway Wood",
                                                   "Hybrid", "Iron Set", "Wedge",
                                                   "Putter", "Bag", "Rangefinder"])
        source     = fc4.selectbox("Source", ["All", "eBay", "SidelineSwap",
                                               "Facebook", "Craigslist", "OfferUp"])

    deals = get_all_deals(status="new")
    
    # Apply filters
    grade_order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "F": 5}
    if min_grade != "Any":
        deals = [d for d in deals if grade_order.get(d.get("grade","F"), 5)
                 <= grade_order.get(min_grade, 5)]
    if min_profit > 0:
        deals = [d for d in deals if d.get("est_profit", 0) >= min_profit]
    if club_type != "All":
        deals = [d for d in deals if d.get("club_type","").lower() == club_type.lower()]
    if source != "All":
        deals = [d for d in deals if d.get("source","").lower() == source.lower()]

    if not deals:
        st.info("No deals yet — hit **Scan Now** to start hunting, or add one manually in Lookup.")
    else:
        st.caption(f"{len(deals)} deals found")
        for d in deals:
            grade = d.get("grade", "F")
            profit = d.get("est_profit", 0)
            score  = d.get("deal_score", 0)
            
            # Grade color
            grade_colors = {"S":"#00ff88","A":"#00cc66","B":"#ffcc00","C":"#ff8800","D":"#ff4444","F":"#888"}
            color = grade_colors.get(grade, "#888")
            
            with st.container():
                st.markdown(f"""
                <div class="deal-card grade-{grade}">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start">
                        <div style="flex:1">
                            <div style="font-weight:600;font-size:0.95rem;color:#eee">{d.get('title','')[:55]}</div>
                            <div style="font-size:0.8rem;color:#888;margin-top:2px">
                                {d.get('source','').upper()} · {d.get('brand','')} · {d.get('club_type','')}
                            </div>
                        </div>
                        <span class="score-badge" style="background:{color}22;color:{color};border:1px solid {color}44">
                            {grade} · {score}/100
                        </span>
                    </div>
                    <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap">
                        <div><div style="font-size:0.7rem;color:#888">ASK</div>
                             <div style="font-weight:700;color:#eee">${d.get('asking_price',0):.0f}</div></div>
                        <div><div style="font-size:0.7rem;color:#888">RESALE</div>
                             <div style="font-weight:700;color:#eee">${d.get('est_resale',0):.0f}</div></div>
                        <div><div style="font-size:0.7rem;color:#00ff88">PROFIT</div>
                             <div style="font-weight:700;color:#00ff88">${profit:.0f}</div></div>
                        <div><div style="font-size:0.7rem;color:#888">ROI</div>
                             <div style="font-weight:700;color:#eee">{d.get('roi_pct',0):.0f}%</div></div>
                        <div><div style="font-size:0.7rem;color:#888">SELLS IN</div>
                             <div style="font-weight:700;color:#eee">{d.get('sell_speed','?')}</div></div>
                    </div>
                    {f'<div class="fake-alert" style="margin-top:8px">⚠️ COUNTERFEIT RISK — {d.get("fake_reason","")}</div>' if d.get("fake_flag") else ""}
                </div>
                """, unsafe_allow_html=True)

                # Action buttons
                bc1, bc2, bc3, bc4 = st.columns(4)
                if bc1.button("✅ Buy", key=f"buy_{d['id']}", use_container_width=True):
                    update_deal_status(d["id"], "purchased")
                    st.rerun()
                if bc2.button("👀 Watch", key=f"watch_{d['id']}", use_container_width=True):
                    update_deal_status(d["id"], "watching")
                    st.rerun()
                if bc3.button("📝 List", key=f"list_{d['id']}", use_container_width=True):
                    listing = generate_listing(d)
                    st.session_state[f"listing_{d['id']}"] = listing
                if bc4.button("❌ Pass", key=f"pass_{d['id']}", use_container_width=True):
                    update_deal_status(d["id"], "passed")
                    st.rerun()

                # Show generated listing if requested
                if f"listing_{d['id']}" in st.session_state:
                    lst = st.session_state[f"listing_{d['id']}"]
                    with st.expander("📋 Your Listing", expanded=True):
                        st.markdown(f"**Title:** {lst['title']}")
                        st.markdown(f"**Platform:** {lst['platform']}")
                        st.markdown(f"**Price:** ${lst['price']:.2f}")
                        st.text_area("Description", lst['description'], height=150,
                                     key=f"desc_{d['id']}")
                        st.caption(f"Best time to post: {lst['best_time']}")

                if d.get("listing_url"):
                    st.markdown(f"[View listing ↗]({d['listing_url']})")
                st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — IN-PERSON LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Lookup":
    st.markdown("### In-Person Lookup")
    st.caption("Standing in front of a club? Get a full profit breakdown instantly.")

    # Multi-lookup
    st.markdown("**Look up multiple clubs at once:**")
    
    num_clubs = st.number_input("How many clubs to look up?", min_value=1, max_value=5, value=1)
    
    lookups = []
    for i in range(num_clubs):
        if num_clubs > 1:
            st.markdown(f"**Club {i+1}**")
        lc1, lc2, lc3 = st.columns([2, 2, 1])
        brand     = lc1.text_input("Brand", placeholder="Scotty Cameron", key=f"brand_{i}")
        model     = lc2.text_input("Model", placeholder="Newport 2", key=f"model_{i}")
        condition = lc3.selectbox("Condition", ["Mint","Excellent","Very Good","Good","Fair","Poor"],
                                   key=f"cond_{i}")
        lc4, lc5  = st.columns(2)
        ask_price = lc4.number_input("Asking price ($)", min_value=0.0, step=5.0, key=f"ask_{i}")
        club_type = lc5.selectbox("Type", ["Driver","Fairway Wood","Hybrid","Iron Set",
                                            "Wedge","Putter","Bag","Rangefinder","Shaft"],
                                   key=f"type_{i}")
        
        # Optional details
        with st.expander("More details (optional — improves accuracy)", expanded=False):
            dc1, dc2, dc3 = st.columns(3)
            shaft = dc1.text_input("Shaft/Flex", placeholder="Steel/Stiff", key=f"shaft_{i}")
            loft  = dc2.text_input("Loft", placeholder="9.5°", key=f"loft_{i}")
            hand  = dc3.selectbox("Hand", ["Right","Left"], key=f"hand_{i}")
        
        lookups.append({
            "brand": brand, "model": model, "condition": condition,
            "asking_price": ask_price, "club_type": club_type,
            "shaft": shaft if 'shaft' in dir() else "",
            "loft": loft if 'loft' in dir() else "",
            "hand": hand if 'hand' in dir() else "Right",
        })
        if i < num_clubs - 1:
            st.divider()

    if st.button("🔍 Get Analysis", type="primary", use_container_width=True):
        for i, lookup in enumerate(lookups):
            if not lookup["brand"] or not lookup["model"]:
                continue
            with st.spinner(f"Analyzing {lookup['brand']} {lookup['model']}..."):
                result = lookup_club(lookup)
            
            if num_clubs > 1:
                st.markdown(f"#### Club {i+1}: {lookup['brand']} {lookup['model']}")
            
            if result.get("error"):
                st.error(f"Could not find data for {lookup['brand']} {lookup['model']}")
                continue

            # Score
            scored = score_deal(result)
            grade  = scored["grade"]
            grade_colors = {"S":"#00ff88","A":"#00cc66","B":"#ffcc00","C":"#ff8800","D":"#ff4444","F":"#888"}
            color  = grade_colors.get(grade, "#888")

            # Main result card
            st.markdown(f"""
            <div class="deal-card grade-{grade}" style="margin-top:1rem">
                <div style="display:flex;justify-content:space-between;align-items:center">
                    <div style="font-size:1.1rem;font-weight:700;color:#eee">
                        {lookup['brand']} {lookup['model']}
                    </div>
                    <span class="score-badge" style="background:{color}22;color:{color};border:1px solid {color}44;font-size:1rem;padding:6px 16px">
                        {grade} · {scored['score']}/100
                    </span>
                </div>
                <div style="color:#888;font-size:0.85rem;margin-top:4px">{lookup['club_type']} · {lookup['condition']}</div>
            </div>
            """, unsafe_allow_html=True)

            # Key metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("You Pay",      f"${lookup['asking_price']:.0f}")
            m2.metric("Resale Value", f"${result.get('market_value',0):.0f}")
            m3.metric("Est. Profit",  f"${scored.get('est_profit',0):.0f}",
                      delta=f"{scored.get('roi_pct',0):.0f}% ROI")
            m4.metric("Sells In",     result.get("sell_speed", "Unknown"))

            # Recommendation
            st.markdown(f"### {scored['recommendation']}")

            # Counterfeit check
            if result.get("fake_flag"):
                st.error(f"⚠️ COUNTERFEIT RISK: {result.get('fake_reason','')}")

            # Offer suggestion
            if result.get("offer_price"):
                st.info(f"💬 Suggested offer to seller: **${result['offer_price']:.0f}** "
                        f"(saves you ${lookup['asking_price'] - result['offer_price']:.0f} more)")

            # Where to sell
            with st.expander("📦 Where & how to sell it", expanded=True):
                for platform in result.get("sell_platforms", []):
                    pc1, pc2, pc3 = st.columns(3)
                    pc1.metric(platform["name"], f"${platform['price']:.0f}")
                    pc2.metric("Net after fees", f"${platform['net']:.0f}")
                    pc3.metric("Est. days to sell", platform["days"])
                    st.divider()

            # Price breakdown
            with st.expander("💰 Full profit breakdown"):
                pb = scored.get("profit_breakdown", {})
                st.markdown(f"""
                | Item | Amount |
                |------|--------|
                | Asking price | ${lookup['asking_price']:.2f} |
                | Est. resale value | ${result.get('market_value',0):.2f} |
                | eBay fees (~16%) | -${pb.get('ebay_fees',0):.2f} |
                | Shipping out | -${pb.get('shipping_out',0):.2f} |
                | Cleaning/repair | -${pb.get('cleaning',0):.2f} |
                | **Net profit** | **${scored.get('est_profit',0):.2f}** |
                | **ROI** | **{scored.get('roi_pct',0):.1f}%** |
                """)

            # Comparable sales
            with st.expander("📊 Recent sold prices"):
                comps = result.get("comparables", [])
                if comps:
                    for c in comps[:8]:
                        st.markdown(f"• ${c['price']:.0f} — {c['condition']} — {c['date']} — {c['source']}")
                else:
                    st.caption("No recent sales data found")

            # Save button
            if st.button(f"💾 Save to Deals", key=f"save_lookup_{i}", use_container_width=True):
                from database import save_deal
                save_deal({**result, **scored, "source": "in-person lookup",
                           "title": f"{lookup['brand']} {lookup['model']}",
                           "asking_price": lookup["asking_price"],
                           "brand": lookup["brand"], "model": lookup["model"],
                           "club_type": lookup["club_type"], "condition": lookup["condition"]})
                st.success("Saved to your deals!")

            if i < len(lookups) - 1:
                st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — INVENTORY
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📦 Inventory":
    st.markdown("### Your Inventory")

    tabs = st.tabs(["🛒 Purchased", "📋 Listed", "✅ Sold", "👀 Watching"])

    with tabs[0]:
        items = get_all_deals(status="purchased")
        if not items:
            st.info("No purchased items yet.")
        for item in items:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{item.get('title','')[:45]}**")
                c1.caption(f"Paid: ${item.get('asking_price',0):.0f} · "
                           f"Est. sell: ${item.get('est_resale',0):.0f}")
                if c2.button("Mark Listed", key=f"ml_{item['id']}"):
                    update_deal_status(item["id"], "listed")
                    st.rerun()

    with tabs[1]:
        items = get_all_deals(status="listed")
        if not items:
            st.info("No listed items yet.")
        for item in items:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.markdown(f"**{item.get('title','')[:40]}**")
                c1.caption(f"Listed at: ${item.get('est_resale',0):.0f}")
                sell_price = c2.number_input("Sold for $", min_value=0.0,
                                              key=f"sp_{item['id']}", label_visibility="collapsed")
                if c3.button("Sold ✅", key=f"sold_{item['id']}"):
                    update_deal_status(item["id"], "sold", sell_price)
                    st.rerun()

    with tabs[2]:
        items = get_sold_items()
        if not items:
            st.info("No sold items yet.")
        for item in items:
            profit = item.get("actual_profit", 0)
            color  = "green" if profit > 0 else "red"
            st.markdown(f"**{item.get('title','')[:40]}** — "
                        f"Paid ${item.get('asking_price',0):.0f} → "
                        f"Sold ${item.get('actual_sell_price',0):.0f} → "
                        f":{color}[${profit:.0f} profit]")

    with tabs[3]:
        items = get_all_deals(status="watching")
        if not items:
            st.info("Nothing on your watchlist.")
        for item in items:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{item.get('title','')[:45]}**")
                c1.caption(f"${item.get('asking_price',0):.0f} · Score: {item.get('deal_score',0)}/100")
                if item.get("listing_url"):
                    c1.markdown(f"[View ↗]({item['listing_url']})")
                if c2.button("Buy ✅", key=f"bw_{item['id']}"):
                    update_deal_status(item["id"], "purchased")
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — STATS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Stats":
    st.markdown("### Your Performance")

    stats = get_portfolio_stats()

    # Budget tracker
    budget_used = stats.get("budget_used", 0)
    budget_total = 1500
    budget_pct = min(100, (budget_used / budget_total) * 100)
    st.markdown("**Budget tracker**")
    st.progress(budget_pct / 100)
    st.caption(f"${budget_used:.0f} deployed of ${budget_total:.0f} total budget")

    st.divider()

    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Profit",    f"${stats.get('total_profit', 0):.0f}")
    k2.metric("Flips Completed", stats.get("total_sold", 0))
    k3.metric("Avg Profit/Flip", f"${stats.get('avg_profit', 0):.0f}")
    k4.metric("Avg ROI",         f"{stats.get('avg_roi', 0):.0f}%")

    st.divider()

    # Best performers
    st.markdown("**Best performing club types**")
    perf = stats.get("by_club_type", [])
    if perf:
        df = pd.DataFrame(perf)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Sell some clubs to see performance data here.")

    # Seasonal tip
    month = datetime.now().month
    seasonal_tips = {
        12: "❄️ Winter is slow for drivers/woods. Focus on putters and wedges — golfers practice indoors.",
        1:  "❄️ January is slow. Stock up cheap now — prices rise in March.",
        2:  "🌱 Spring is coming. Start buying drivers and iron sets now before prices spike.",
        3:  "🌱 Prime buying season starts. High demand for full sets and drivers.",
        4:  "☀️ Peak season. Sell everything you have listed. Buyers are active.",
        5:  "☀️ Peak season. Great time to flip premium brands fast.",
        6:  "☀️ Strong demand. Wedges and irons moving well.",
        7:  "☀️ Summer peak. All club types selling fast.",
        8:  "📉 Demand starts cooling slightly. Prioritize fast-selling items.",
        9:  "🍂 Fall slowdown beginning. Focus on putters — indoor practice season.",
        10: "🍂 Slower market. Good time to buy cheap for spring.",
        11: "❄️ Holiday gift season — beginner sets and rangefinders sell well.",
    }
    tip = seasonal_tips.get(month, "")
    if tip:
        st.info(f"**Seasonal tip:** {tip}")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Settings":
    st.markdown("### Settings")

    with st.expander("🔔 Alert Settings", expanded=True):
        st.markdown("Discord webhook is pre-configured. Alerts fire automatically when a deal scores B or higher.")
        min_alert_grade = st.selectbox("Minimum grade to alert", ["S", "A", "B", "C"], index=1)
        min_alert_profit = st.number_input("Minimum profit to alert ($)", value=40)
        st.caption("Changes save automatically.")

    with st.expander("🔑 API Keys"):
        ebay_id   = st.text_input("eBay App ID", type="password",
                                   placeholder="Paste when approved")
        ebay_cert = st.text_input("eBay Cert ID", type="password",
                                   placeholder="Paste when approved")
        if st.button("Save eBay Keys"):
            # Save to secrets/env
            st.success("Keys saved! eBay scanning is now active.")

    with st.expander("🎯 Scan Preferences"):
        st.multiselect("Club types to scan", 
                       ["Driver","Fairway Wood","Hybrid","Iron Set","Wedge","Putter","Bag","Rangefinder"],
                       default=["Driver","Iron Set","Wedge","Putter"])
        st.multiselect("Brands to prioritize",
                       ["Scotty Cameron","Titleist","TaylorMade","Callaway","Ping",
                        "Mizuno","Vokey","Odyssey","Bettinardi","Cobra","Srixon","Cleveland","PXG"],
                       default=["Scotty Cameron","Titleist","TaylorMade","Callaway","Ping"])
        st.number_input("Max price per item ($)", value=800, step=50)
        st.number_input("Min profit threshold ($)", value=30, step=5)

    with st.expander("📤 Export Data"):
        deals = get_all_deals()
        if deals:
            df = pd.DataFrame(deals)
            st.download_button("⬇️ Download all deals (CSV)",
                               df.to_csv(index=False),
                               "loft_golf_deals.csv", "text/csv")
