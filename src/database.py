"""database.py — SQLite storage layer"""
import sqlite3, json
from pathlib import Path
from datetime import datetime

DB = Path(__file__).parent.parent / "data" / "golf.db"

def _conn():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = _conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS deals (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        source          TEXT,
        title           TEXT,
        brand           TEXT,
        model           TEXT,
        club_type       TEXT,
        condition       TEXT,
        asking_price    REAL,
        est_resale      REAL,
        est_profit      REAL,
        roi_pct         REAL,
        deal_score      INTEGER,
        grade           TEXT,
        sell_speed      TEXT,
        risk_level      TEXT,
        fake_flag       INTEGER DEFAULT 0,
        fake_reason     TEXT,
        listing_url     TEXT,
        image_url       TEXT,
        offer_price     REAL,
        status          TEXT DEFAULT 'new',
        actual_sell_price REAL,
        actual_profit   REAL,
        raw_json        TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS scan_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ran_at      TEXT,
        source      TEXT,
        found       INTEGER,
        alerted     INTEGER
    );
    """)
    c.commit(); c.close()

def save_deal(d: dict) -> int:
    c = _conn()
    cur = c.execute("""
        INSERT INTO deals (source,title,brand,model,club_type,condition,
            asking_price,est_resale,est_profit,roi_pct,deal_score,grade,
            sell_speed,risk_level,fake_flag,fake_reason,listing_url,
            image_url,offer_price,raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (d.get("source",""), d.get("title",""), d.get("brand",""),
          d.get("model",""), d.get("club_type",""), d.get("condition",""),
          d.get("asking_price",0), d.get("est_resale",0), d.get("est_profit",0),
          d.get("roi_pct",0), d.get("deal_score",0), d.get("grade","F"),
          d.get("sell_speed",""), d.get("risk_level","MEDIUM"),
          1 if d.get("fake_flag") else 0, d.get("fake_reason",""),
          d.get("listing_url",""), d.get("image_url",""),
          d.get("offer_price",0), json.dumps(d)))
    row_id = cur.lastrowid
    c.commit(); c.close()
    return row_id

def get_all_deals(status: str = None, limit: int = 100) -> list[dict]:
    c = _conn()
    if status:
        rows = c.execute("SELECT * FROM deals WHERE status=? ORDER BY deal_score DESC LIMIT ?",
                         (status, limit)).fetchall()
    else:
        rows = c.execute("SELECT * FROM deals ORDER BY deal_score DESC LIMIT ?",
                         (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]

def get_sold_items() -> list[dict]:
    c = _conn()
    rows = c.execute("SELECT * FROM deals WHERE status='sold' ORDER BY updated_at DESC").fetchall()
    c.close()
    return [dict(r) for r in rows]

def update_deal_status(deal_id: int, status: str, sell_price: float = None):
    c = _conn()
    if sell_price and status == "sold":
        row = c.execute("SELECT asking_price FROM deals WHERE id=?", (deal_id,)).fetchone()
        actual_profit = sell_price - (row["asking_price"] if row else 0)
        c.execute("""UPDATE deals SET status=?, actual_sell_price=?, actual_profit=?,
                     updated_at=datetime('now') WHERE id=?""",
                  (status, sell_price, actual_profit, deal_id))
    else:
        c.execute("UPDATE deals SET status=?, updated_at=datetime('now') WHERE id=?",
                  (status, deal_id))
    c.commit(); c.close()

def get_portfolio_stats() -> dict:
    c = _conn()
    sold   = c.execute("SELECT * FROM deals WHERE status='sold'").fetchall()
    active = c.execute("SELECT * FROM deals WHERE status='purchased'").fetchall()
    c.close()
    total_profit  = sum(r["actual_profit"] or 0 for r in sold)
    budget_used   = sum(r["asking_price"] or 0 for r in active)
    avg_profit    = (total_profit / len(sold)) if sold else 0
    profits       = [r["actual_profit"] or 0 for r in sold]
    avg_roi       = (sum((r["actual_profit"] or 0) / max(r["asking_price"],1) * 100
                        for r in sold) / len(sold)) if sold else 0
    return {
        "total_profit": total_profit,
        "total_sold":   len(sold),
        "avg_profit":   avg_profit,
        "avg_roi":      avg_roi,
        "budget_used":  budget_used,
    }
