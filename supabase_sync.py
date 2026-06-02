"""
Reads bist_ajan.db and upserts to Supabase.
Run after main.py completes.

Requires:
  SUPABASE_URL and SUPABASE_SERVICE_KEY in environment (or .env file).

Tables synced:
  signals        <- last 90 days from Gunluk_Sinyaller
  positions      <- all from Aktif_Pozisyonlar
  trades         <- all from Islem_Gecmisi
  market_breadth <- last 90 days (derived: date + breadth_pct + durum)
  technicals     <- latest indicator snapshot per ticker from Hisse_Indikatorleri
  prices         <- last 90 days from Hisse_Verileri (ticker, date, close)
"""

import argparse
import os
import sqlite3
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from supabase import create_client
except ImportError:
    raise ImportError("pip install supabase")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
DB_PATH = "bist_ajan.db"
SYNC_DAYS = 90


def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def sync_signals(conn, sb):
    cutoff = (datetime.now() - timedelta(days=SYNC_DAYS)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT Tarih, Hisse, Kapanis, Strateji, Sinyal, Stop_Loss, Hedef_Fiyat, "
        "Potansiyel_Getiri, Puan, Vade, Tier "
        "FROM Gunluk_Sinyaller WHERE Tarih >= ? ORDER BY Tarih DESC",
        (cutoff,)
    ).fetchall()
    cols = ["date", "ticker", "close", "strategy", "signal", "stop_loss",
            "target_price", "potential_return", "score", "vade", "tier"]
    data = [dict(zip(cols, r)) for r in rows]
    if data:
        sb.table("signals").upsert(data, on_conflict="date,ticker,strategy").execute()
    print(f"Synced {len(data)} signals")


def sync_positions(conn, sb):
    rows = conn.execute(
        "SELECT Hisse, Alis_Tarihi, Alis_Fiyati, Guncel_Stop_Loss, Hedef_Fiyat, Vade, Tier "
        "FROM Aktif_Pozisyonlar"
    ).fetchall()
    cols = ["ticker", "entry_date", "entry_price", "current_stop", "target_price", "vade", "tier"]
    data = [dict(zip(cols, r)) for r in rows]
    if data:
        sb.table("positions").upsert(data, on_conflict="ticker").execute()
    print(f"Synced {len(data)} positions")


def sync_trades(conn, sb):
    rows = conn.execute(
        "SELECT Hisse, Alis_Tarihi, Satis_Tarihi, Alis_Fiyati, Satis_Fiyati, "
        "Kar_Zarar_Yuzdesi, Kapanis_Nedeni, Vade, Tier "
        "FROM Islem_Gecmisi ORDER BY Satis_Tarihi DESC"
    ).fetchall()
    cols = ["ticker", "entry_date", "exit_date", "entry_price", "exit_price",
            "pnl_pct", "close_reason", "vade", "tier"]
    data = [dict(zip(cols, r)) for r in rows]
    if data:
        sb.table("trades").upsert(data, on_conflict="ticker,entry_date").execute()
    print(f"Synced {len(data)} trades")


def sync_tavan_takip(conn, sb):
    today = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute(
        """
        SELECT b.Tarih, b.Hisse,
               ROUND((b.Kapanis - d.Kapanis) / d.Kapanis * 100, 2) AS move_pct,
               b.Hacim_TL,
               ROUND(b.Hacim_TL / NULLIF(b.Hacim_Ort_5, 0), 2) AS vol_ratio
        FROM Hisse_Indikatorleri b
        JOIN Hisse_Indikatorleri d
          ON b.Hisse = d.Hisse
         AND d.Tarih = (
               SELECT MAX(Tarih) FROM Hisse_Indikatorleri i2
               WHERE i2.Hisse = b.Hisse AND i2.Tarih < b.Tarih
             )
        WHERE b.Tarih = ?
          AND b.Hacim_TL >= 10000000
          AND (b.Kapanis - d.Kapanis) / d.Kapanis >= 0.095
          AND b.Hacim_TL > b.Hacim_Ort_5 * 2.0
        ORDER BY move_pct DESC
        LIMIT 10
        """,
        (today,)
    ).fetchall()
    cols = ["date", "ticker", "move_pct", "volume_tl", "vol_ratio"]
    data = [dict(zip(cols, r)) for r in rows]
    if data:
        sb.table("tavan_takip").upsert(data, on_conflict="date,ticker").execute()
    print(f"Synced {len(data)} tavan_takip rows")


def sync_technicals(conn, sb):
    """Upsert latest technical-indicator snapshot per ticker (most recent date)."""
    rows = conn.execute(
        """
        SELECT t.Hisse, t.Tarih, t.Kapanis,
               t.EMA_20, t.EMA_50, t.EMA_200,
               t.RSI_14, t.MACD, t.MACD_Signal, t.MACD_Hist,
               t.Stoch_K, t.Stoch_D, t.MFI_14,
               t.ADX_14, t.Plus_DI, t.Minus_DI,
               t.ATR_14, t.BB_Ust, t.BB_Orta, t.BB_Alt,
               t.HV_20, t.HV_20_Pct,
               t.Hacim_TL, t.Hacim_Ort_20,
               t.RS_63, t.Dist_52W_Pct
        FROM Hisse_Indikatorleri t
        JOIN (
            SELECT Hisse, MAX(Tarih) AS mx
            FROM Hisse_Indikatorleri
            GROUP BY Hisse
        ) m ON m.Hisse = t.Hisse AND m.mx = t.Tarih
        """
    ).fetchall()
    cols = ["ticker", "date", "close",
            "ema_20", "ema_50", "ema_200",
            "rsi_14", "macd", "macd_signal", "macd_hist",
            "stoch_k", "stoch_d", "mfi_14",
            "adx_14", "plus_di", "minus_di",
            "atr_14", "bb_ust", "bb_orta", "bb_alt",
            "hv_20", "hv_20_pct",
            "hacim_tl", "hacim_ort_20",
            "rs_63", "dist_52w_pct"]

    def _clean(v):
        # JSON can't carry NaN/Inf; Supabase rejects them.
        if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
            return None
        return v

    data = [{c: _clean(v) for c, v in zip(cols, r)} for r in rows]
    if data:
        batch_size = 1000
        for i in range(0, len(data), batch_size):
            sb.table("technicals").upsert(data[i:i + batch_size], on_conflict="ticker").execute()
    print(f"Synced {len(data)} technicals rows")


def sync_prices(conn, sb):
    cutoff = (datetime.now() - timedelta(days=SYNC_DAYS)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT Hisse, Tarih, Kapanis FROM Hisse_Verileri WHERE Tarih >= ? ORDER BY Tarih DESC",
        (cutoff,)
    ).fetchall()
    data = [{"ticker": r[0], "date": r[1], "close": r[2]} for r in rows]
    if data:
        # upsert in batches of 1000 to avoid payload limits (~54k rows total)
        batch_size = 1000
        for i in range(0, len(data), batch_size):
            sb.table("prices").upsert(data[i:i + batch_size], on_conflict="ticker,date").execute()
    print(f"Synced {len(data)} price rows")


def sync_market_breadth(conn, sb):
    cutoff = (datetime.now() - timedelta(days=SYNC_DAYS)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT Tarih, AVG(CASE WHEN Kapanis > EMA_20 THEN 1.0 ELSE 0.0 END) as breadth_pct "
        "FROM Hisse_Indikatorleri WHERE Tarih >= ? "
        "GROUP BY Tarih ORDER BY Tarih DESC",
        (cutoff,)
    ).fetchall()
    data = []
    for date, bp in rows:
        bp_pct = round(bp * 100, 1)
        durum = "YESIL" if bp_pct > 50 else ("SARI" if bp_pct > 35 else "KIRMIZI")
        data.append({"date": date, "breadth_pct": bp_pct, "durum": durum})
    if data:
        sb.table("market_breadth").upsert(data, on_conflict="date").execute()
    print(f"Synced {len(data)} breadth rows")


def _safe_sync(name, fn, conn, sb):
    try:
        fn(conn, sb)
    except sqlite3.OperationalError as e:
        print(f"⚠️ Skipped {name}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--light", action="store_true", help="Skip prices sync (faster, lower bandwidth)")
    parser.add_argument("--full", action="store_true", help="Sync all tables including prices")
    args = parser.parse_args()

    full = args.full or not args.light

    sb = _get_supabase()
    conn = sqlite3.connect(DB_PATH)
    try:
        _safe_sync("signals", sync_signals, conn, sb)
        _safe_sync("positions", sync_positions, conn, sb)
        _safe_sync("trades", sync_trades, conn, sb)
        _safe_sync("market_breadth", sync_market_breadth, conn, sb)
        _safe_sync("tavan_takip", sync_tavan_takip, conn, sb)
        _safe_sync("technicals", sync_technicals, conn, sb)
        if full:
            _safe_sync("prices", sync_prices, conn, sb)
        else:
            print("Skipped prices (light sync)")
        print("Sync complete")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
