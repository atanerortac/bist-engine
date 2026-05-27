# BIST Ajan — Istanbul Stock Exchange Signal Engine

A Python-based swing trade signal engine for BIST (Borsa Istanbul). Fetches all BIST tickers daily, calculates technical indicators, and generates ranked buy signals across 4 strategies with stop-loss and target prices.

**Honest performance disclaimer:** Backtested 36-month WR of 54–63% for top-tier signals. Regime-dependent — system performs well in trending BIST markets, weakens in sustained bear/choppy periods (see [Regime Sensitivity](#regime-sensitivity)).

---

## Architecture

```
bist_ajan.db (SQLite)
     ↑
veri_motoru.py       ← fetches OHLCV for all ~500 BIST tickers via yfinance
     ↓
indicator_engine.py  ← calculates EMA/RSI/MACD/ATR/BB/Stoch/ADX/MFI/OBV/RS_63
     ↓
strategy_engine.py   ← scoring engine → buy signals with stop/target
     ↓
portfolio_manager.py ← live position tracking, trailing stops, max-hold exits
     ↓
raporlayici.py       ← console daily summary
takip_motoru.py      ← full HTML + Markdown report
```

---

## Module Map

| File | Role |
|------|------|
| `main.py` | Entry point. Runs full pipeline or schedules daily at 18:30. |
| `veri_motoru.py` | Downloads all BIST tickers from TradingView, OHLCV via yfinance, SQLite storage. First run = 5-year history, subsequent = incremental. |
| `indicator_engine.py` | EMA 20/50/100/200, RSI 14, MACD, ATR 14 (Wilder), ATR 20, Bollinger Bands, Stochastic K/D, ADX 14, MFI 14, OBV, RS_63 vs XU100, HV_20, Pocket Pivot, Squeeze columns. |
| `strategy_engine.py` | 4 scoring-based strategies. Market breadth filter → scoring → Diamond/Ruby/Firsat tiers → quota enforcement → global dedup. |
| `portfolio_manager.py` | Algorithmic position simulation. Per-vade trailing stops, intraday high/low target check, max hold enforcement. |
| `backtest_engine.py` | Realistic historical simulation. Next-day open entry, commission+slippage, BIST taban (limit-down) rule, walk-forward OOS, grid search. |
| `raporlayici.py` | Console summary: market status, new signals with tier/score, active positions, lot sizing. |
| `takip_motoru.py` | Full HTML + MD report: portfolio P&L, signal cards, Gecen Gun Sinyalleri, Tavan Takip scanner, risk badges. |
| `temel_motoru.py` | Fetches F/K (P/E) and PD/DD (P/B) from Yahoo Finance per ticker with in-run cache. |

---

## Strategies

| Strategy | Tier | Conditions | Market Filter |
|----------|------|-----------|---------------|
| `Kisa_Vade` | Diamond / Ruby | MACD crossover + RSI 45-65 + volume spike + EMA20 above + Stoch + MFI | GREEN (>50% stocks above EMA20) |
| `Orta_Vade` | Diamond / Firsat | EMA50 above + ADX + MACD + OBV + RS_63 vs XU100 | GREEN only |
| `Momentum_Patlama` | Diamond | Pocket Pivot volume + BB squeeze breakout + RSI 55-70 + EMA structure | GREEN, breadth >=60% |
| `Duzeltme` | Firsat | *Disabled* - grid search found no viable PF > 1.0 configuration on BIST data |

**Market Breadth Filter:**
- Red: < 35% stocks above EMA20 - No signals (stay cash)
- Yellow: 35-50% - Orta Firsat only
- Green: > 50% - All strategies active

**Stop/Target:**
- Kisa: stop = `max(entry - 2.0xATR, entry x 0.85)`, target = `entry + 2.0xATR`, min R:R 1.2
- Orta: vol-adaptive target (HV<30 -> 3.5xATR, HV 30-60 -> 5.0xATR, HV>=60 -> 6.5xATR)
- Momentum: stop = `max(entry - 1.5xATR, EMA_20 x 0.99)`, target = `entry + 3.0xATR`

---

## Backtest Results (36-month, 2023-06 to 2026-05)

> Slippage 0.5% per fill, entry at signal-day close.
> Survivorship bias present - actual WR ~2-5pp lower.

| Strategy | Tier | Trades | Win Rate | Profit Factor |
|----------|------|--------|----------|---------------|
| Kisa_Vade | Diamond | 96 | 56.2% | 1.39 |
| Kisa_Vade | Ruby | 154 | 63.0% | 1.81 |
| Orta_Vade | Diamond | 283 | 37.8% | 1.41 |
| Orta_Vade | Firsat | 478 | 43.9% | 1.74 |
| Momentum | Diamond | 267 | 46.8% | 1.40 |

Walk-forward OOS (2024-06 to 2025-06): WR drops ~20pp - this period = documented BIST bear. See Regime Sensitivity below.

---

## Regime Sensitivity

**Known bad windows:**
- Kisa Ruby 2024-10 to 2025-06: PF 0.43 - mid-cap distribution while XU100 above MAs; no static filter reliably detects this
- Orta Firsat 2024-02 to 2024-10: PF 0.69 - TRY depreciation + choppy index
- Momentum 2024-02 to 2024-10: PF 0.35

**Mitigations built in:**
- Rolling PF gate (J3): auto-reduces quota for Kisa Ruby, Orta Firsat, Momentum Diamond when last-N closed trades drop below PF threshold
- Weekly trend filter (EMA_100): halves Kisa Ruby trade count, +5pp WR
- `xu100_regime_filter`: blocks signals when XU100 < own EMA20

These mitigations reduce bad-window damage but do not eliminate it. The system is not suitable as a fully automated black-box - use in conjunction with market awareness.

---

## Setup

### Requirements

```bash
pip install -r requirements.txt
```

### Configuration

```bash
cp .env.example .env
cp benim_hisselerim.txt.example benim_hisselerim.txt
cp gercek_islemler.txt.example gercek_islemler.txt
# Edit files with your data
```

Strategy parameters in `strategy_config.json` - all tunable without touching code.

### First Run

```bash
python main.py
# Option 1: run once
# Option 2: schedule daily at 18:30
```

First run downloads ~5 years of OHLCV data for ~500 BIST tickers (~15 min). Subsequent runs are incremental (<2 min).

### Individual Modules

```bash
python veri_motoru.py       # data update only
python indicator_engine.py  # recalculate indicators
python strategy_engine.py   # generate today's signals
python takip_motoru.py      # generate HTML + MD report
python backtest_engine.py   # run backtest (36m default)
python backtest_engine.py --months=6
python backtest_engine.py --walkforward
python backtest_engine.py --grid=Kisa
```

---

## Database Schema

SQLite at `bist_ajan.db`:

```
Hisse_Verileri         -> OHLCV per ticker per date
Hisse_Indikatorleri    -> all indicator columns per ticker per date
Gunluk_Sinyaller       -> daily signals with stop/target/score/tier
Aktif_Pozisyonlar      -> open algorithmic simulation positions
Islem_Gecmisi          -> closed algorithmic simulation trades
```

---

## Anti-Overfitting Notes

- All strategy parameters externalized to `strategy_config.json`
- Walk-forward validation: 2yr in-sample (2022-06 to 2024-06), 1yr OOS (2024-06 to 2025-06)
- Each indicator added one at a time with backtest verification before keeping
- Grid search sweeps target/stop/min_rr/threshold combinations; results in `tasks/grid_*.csv`
- OOS WR significantly lower than IS WR - IS period was a strong BIST bull, not representative

---

## Limitations

- No position sizing beyond lot calculator (default 2% risk / 15% max position)
- Survivorship bias - delisted tickers absent from universe
- yfinance data quality varies; some BIST tickers have gaps
- Fundamental overlay (F/K, PD/DD) is informational only - does not block signals
- `Duzeltme` strategy disabled - no viable config found on 36m BIST data
