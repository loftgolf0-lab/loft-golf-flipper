"""
manual_entry.py
---------------
Handles manual entry of listings from platforms that prohibit automated
scraping: Facebook Marketplace, Craigslist, OfferUp, Mercari, SidelineSwap.

Workflow:
  1. You browse these sites normally in your browser.
  2. When you see something interesting, you paste the URL and key details here.
  3. The app saves the listing, scores it, and shows profit estimates.

Future upgrade: a browser extension (Manifest V3) can pre-fill these fields
from the page you're viewing, sending data to a local Flask endpoint on
localhost:5001. That keeps full ToS compliance with zero automation.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "listings.db"


@dataclass
class ManualListing:
    source: str          # "facebook", "craigslist", "offerup", "mercari", "sidelineswap"
    title: str
    asking_price: float
    listing_url: str
    condition: str       # "Mint", "Excellent", "Good", "Fair", "Poor"
    location: str = ""
    shipping_cost: float = 0.0
    brand: str = ""
    model: str = ""
    club_type: str = ""  # "Driver","Fairway Wood","Hybrid","Iron Set","Wedge","Putter","Bag","Rangefinder","Shaft"
    shaft_flex: str = ""
    loft: str = ""
    hand: str = "Right"
    seller_rating: str = ""
    notes: str = ""
    image_url: str = ""
    item_id: str = ""

    # Auto-set
    listed_at: str = ""
    added_at: str = ""

    def __post_init__(self):
        if not self.listed_at:
            self.listed_at = datetime.now().isoformat()
        if not self.added_at:
            self.added_at = datetime.now().isoformat()
        if not self.item_id:
            import hashlib
            self.item_id = hashlib.md5(
                f"{self.source}{self.listing_url}{self.asking_price}".encode()
            ).hexdigest()[:12]

    @property
    def total_cost(self) -> float:
        return self.asking_price + self.shipping_cost


# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist yet."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            item_id         TEXT PRIMARY KEY,
            source          TEXT NOT NULL,
            title           TEXT,
            brand           TEXT,
            model           TEXT,
            club_type       TEXT,
            condition       TEXT,
            asking_price    REAL,
            shipping_cost   REAL,
            total_cost      REAL,
            location        TEXT,
            shaft_flex      TEXT,
            loft            TEXT,
            hand            TEXT,
            seller_rating   TEXT,
            listing_url     TEXT,
            image_url       TEXT,
            notes           TEXT,
            listed_at       TEXT,
            added_at        TEXT,
            -- Scoring / analysis fields (filled by scorer.py)
            est_resale      REAL,
            est_profit      REAL,
            roi_pct         REAL,
            deal_score      INTEGER,
            risk_level      TEXT,
            -- Workflow status
            status          TEXT DEFAULT 'new',   -- new|watching|contacted|purchased|listed|sold
            actual_sell_price REAL,
            actual_profit   REAL
        );

        CREATE TABLE IF NOT EXISTS comparable_sales (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            query           TEXT,
            title           TEXT,
            sold_price      REAL,
            condition       TEXT,
            source          TEXT DEFAULT 'ebay',
            sold_date       TEXT,
            listing_url     TEXT,
            fetched_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            search_query    TEXT NOT NULL,
            brand           TEXT,
            club_type       TEXT,
            max_price       REAL,
            min_profit      REAL DEFAULT 50,
            min_roi         REAL DEFAULT 30,
            active          INTEGER DEFAULT 1,
            created_at      TEXT
        );
    """)
    conn.commit()
    conn.close()


def save_listing(listing: ManualListing) -> str:
    """Insert or replace a listing. Returns the item_id."""
    conn = get_connection()
    d = asdict(listing)
    d["total_cost"] = listing.total_cost
    cols = ", ".join(d.keys())
    placeholders = ", ".join(["?"] * len(d))
    conn.execute(
        f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})",
        list(d.values())
    )
    conn.commit()
    conn.close()
    return listing.item_id


def get_listing(item_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM listings WHERE item_id = ?", (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_status(item_id: str, status: str,
                  actual_sell_price: float = None, actual_profit: float = None):
    conn = get_connection()
    if actual_sell_price is not None:
        conn.execute(
            "UPDATE listings SET status=?, actual_sell_price=?, actual_profit=? WHERE item_id=?",
            (status, actual_sell_price, actual_profit, item_id)
        )
    else:
        conn.execute("UPDATE listings SET status=? WHERE item_id=?", (status, item_id))
    conn.commit()
    conn.close()


def save_comparable(query: str, title: str, sold_price: float,
                    condition: str = "", sold_date: str = "",
                    listing_url: str = "", source: str = "ebay"):
    conn = get_connection()
    conn.execute(
        """INSERT INTO comparable_sales
           (query, title, sold_price, condition, source, sold_date, listing_url, fetched_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (query, title, sold_price, condition, source,
         sold_date, listing_url, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_comparable_prices(query: str, limit: int = 20) -> list[dict]:
    """Fetch recent comparable sold prices for a query string."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM comparable_sales
           WHERE query LIKE ?
           ORDER BY fetched_at DESC LIMIT ?""",
        (f"%{query}%", limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_listings(status_filter: str = None, limit: int = 200) -> list[dict]:
    conn = get_connection()
    if status_filter:
        rows = conn.execute(
            "SELECT * FROM listings WHERE status=? ORDER BY added_at DESC LIMIT ?",
            (status_filter, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM listings ORDER BY deal_score DESC NULLS LAST, added_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Watchlist ────────────────────────────────────────────────────────────────

def add_to_watchlist(search_query: str, brand: str = "", club_type: str = "",
                     max_price: float = 500, min_profit: float = 50,
                     min_roi: float = 30):
    conn = get_connection()
    conn.execute(
        """INSERT INTO watchlist (search_query, brand, club_type, max_price,
           min_profit, min_roi, created_at) VALUES (?,?,?,?,?,?,?)""",
        (search_query, brand, club_type, max_price,
         min_profit, min_roi, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_watchlist() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM watchlist WHERE active=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Init on import ───────────────────────────────────────────────────────────
init_db()
