"""Tests for backtest_engine.py — pure-logic, no DB required."""
import sys
import os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest_engine as be


# ── FIXTURES ─────────────────────────────────────────────────────────────────

def _make_raw_ohlcv(n=60, start_price=10.0, end_price=20.0, hisse='TEST'):
    """Deterministic OHLCV DataFrame (Tarih as string, cols: Tarih/Hisse/Acilis/En_Yuksek/En_Dusuk/Kapanis)."""
    from datetime import date, timedelta
    closes = np.linspace(start_price, end_price, n)
    spread = 0.05
    records = []
    for i, c in enumerate(closes):
        d = (date(2023, 1, 2) + timedelta(days=i)).strftime('%Y-%m-%d')
        records.append({
            'Tarih':      d,
            'Hisse':      hisse,
            'Acilis':     round(c * (1 - spread / 2), 4),
            'En_Yuksek':  round(c * (1 + spread), 4),
            'En_Dusuk':   round(c * (1 - spread), 4),
            'Kapanis':    round(c, 4),
        })
    return pd.DataFrame(records)


def _make_signal(hisse='TEST', vade='Kisa', tier='Diamond', kapanis=15.0,
                 atr=0.5, puan=85, hv_pct=40.0):
    return {
        'Hisse':      hisse,
        'Vade':       vade,
        'Tier':       tier,
        'Kapanis':    kapanis,
        'ATR':        atr,
        'Puan':       puan,
        'HV_20_Pct':  hv_pct,
        'EMA_20':     kapanis * 0.98,
        'EMA_50':     kapanis * 0.95,
    }


# ── _stats ───────────────────────────────────────────────────────────────────

def test_stats_empty_returns_zeros():
    s = be._stats(pd.DataFrame())
    assert s['total'] == 0 and s['wr'] == 0 and s['pf'] == 0


def test_stats_all_winners():
    df = pd.DataFrame({'KZ_Pct': [5.0, 10.0, 3.0], 'Hold_Days': [5, 7, 3],
                       'Target_Reached_Pct': [100, 100, 100], 'Max_Gain_Pct': [5, 10, 3]})
    s = be._stats(df)
    assert s['total'] == 3
    assert s['wr'] == 100.0
    assert s['pf'] == float('inf')
    assert s['avg_win'] == pytest.approx(6.0)


def test_stats_all_losers():
    df = pd.DataFrame({'KZ_Pct': [-5.0, -10.0], 'Hold_Days': [10, 15],
                       'Target_Reached_Pct': [20, 30], 'Max_Gain_Pct': [1, 2]})
    s = be._stats(df)
    assert s['wr'] == 0.0
    assert s['pf'] == 0.0


def test_stats_mixed():
    df = pd.DataFrame({'KZ_Pct': [10.0, -5.0], 'Hold_Days': [5, 8],
                       'Target_Reached_Pct': [100, 50], 'Max_Gain_Pct': [10, 3]})
    s = be._stats(df)
    assert s['total'] == 2
    assert s['wr'] == 50.0
    assert s['pf'] == pytest.approx(10.0 / 5.0)


# ── _compute_thresholds ──────────────────────────────────────────────────────

def test_compute_thresholds_uses_defaults_when_cfg_empty():
    thr = be._compute_thresholds({})
    assert isinstance(thr['kisa_ruby'], int)
    assert isinstance(thr['kisa_diamond'], int)
    assert thr['kisa_diamond'] >= thr['kisa_ruby']


def test_compute_thresholds_diamond_above_ruby():
    import json
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'strategy_config.json')
    with open(cfg_path, encoding='utf-8') as f:
        cfg = json.load(f)
    thr = be._compute_thresholds(cfg)
    assert thr['kisa_diamond'] > thr['kisa_ruby'], "Diamond threshold must exceed Ruby"
    assert thr['orta_diamond'] > thr['orta_firsat'], "Orta Diamond must exceed Firsat"


# ── _dynamic_target_atr ──────────────────────────────────────────────────────

def test_dynamic_target_atr_orta_low_hv():
    assert be._dynamic_target_atr(20.0, 'Orta') == 3.5


def test_dynamic_target_atr_orta_mid_hv():
    assert be._dynamic_target_atr(45.0, 'Orta') == 5.0


def test_dynamic_target_atr_orta_high_hv():
    assert be._dynamic_target_atr(70.0, 'Orta') == 6.5


def test_dynamic_target_atr_none_hv_defaults_to_mid():
    result = be._dynamic_target_atr(None, 'Orta')
    assert result == 5.0  # HV=50 (default) → mid bucket


# ── _simulate_trade ──────────────────────────────────────────────────────────

def _run_sim(start_price=10.0, end_price=20.0, n=40, vade='Kisa', tier='Diamond',
             target_atr=None, stop_atr=None, kapanis=None, atr=0.5):
    raw = _make_raw_ohlcv(n=n, start_price=start_price, end_price=end_price)
    all_dates = raw['Tarih'].tolist()
    entry_date = all_dates[5]
    entry_close = float(raw.loc[raw['Tarih'] == entry_date, 'Kapanis'].iloc[0])
    sig = _make_signal(vade=vade, tier=tier, kapanis=kapanis or entry_close, atr=atr)
    result = be._simulate_trade(sig, entry_date, raw, all_dates,
                                target_atr=target_atr, stop_atr=stop_atr,
                                gap_filter=False)
    return result


def test_simulate_trade_uptrend_hits_target():
    # target_atr=3.0, stop_atr=1.5 (PARAMS default) → RR=2.0 ≥ min_rr=1.2
    result = _run_sim(start_price=10.0, end_price=30.0, n=40, atr=0.3, target_atr=3.0)
    assert result is not None
    assert result['KZ_Pct'] > 0
    assert result['Neden'] in ('Hedef', 'Hedef_Partial')


def test_simulate_trade_downtrend_hits_stop():
    result = _run_sim(start_price=20.0, end_price=5.0, n=40, vade='Kisa',
                      kapanis=20.0, atr=0.5, stop_atr=0.5)
    assert result is not None
    assert result['KZ_Pct'] < 0
    # Stop_Taban = circuit breaker (>10% overnight drop), also valid stop exit
    assert 'Stop' in result['Neden'] or 'HardStop' in result['Neden']


def test_simulate_trade_max_hold_respected():
    # atr=0.5: stop at entry*0.85 (floor), target at entry+50 — both out of reach for flat price
    raw = _make_raw_ohlcv(n=80, start_price=15.0, end_price=15.5)
    all_dates = raw['Tarih'].tolist()
    entry_date = all_dates[5]
    sig = _make_signal(vade='Kisa', kapanis=15.0, atr=0.5)
    result = be._simulate_trade(sig, entry_date, raw, all_dates,
                                target_atr=100.0, stop_atr=50.0, gap_filter=False)
    assert result is not None
    assert result['Hold_Days'] == be.MAX_HOLD['Kisa']
    assert 'Süre' in result['Neden']


def test_simulate_trade_invalid_date_returns_none():
    raw = _make_raw_ohlcv(n=20)
    all_dates = raw['Tarih'].tolist()
    sig = _make_signal(kapanis=10.0, atr=0.5)
    result = be._simulate_trade(sig, '1900-01-01', raw, all_dates, gap_filter=False)
    assert result is None


def test_simulate_trade_rr_filter_rejects_bad_setup():
    # stop_atr=2.0 (risk ≈ 1.0), target_atr=0.5 (reward ≈ 0.25) → RR ≈ 0.25 < min_rr=1.2
    raw = _make_raw_ohlcv(n=40, start_price=10.0, end_price=12.0)
    all_dates = raw['Tarih'].tolist()
    entry_date = all_dates[5]
    sig = _make_signal(kapanis=10.0, atr=0.5, vade='Kisa')
    result = be._simulate_trade(sig, entry_date, raw, all_dates,
                                target_atr=0.5, stop_atr=2.0, gap_filter=False)
    assert result is None


def test_simulate_trade_result_fields():
    result = _run_sim(start_price=10.0, end_price=30.0, n=40, atr=0.3, target_atr=3.0)
    assert result is not None
    for field in ('Hisse', 'Vade', 'Tier', 'Puan', 'Sinyal_Tarihi', 'Giris_Tarihi',
                  'Cikis_Tarihi', 'Hold_Days', 'Entry', 'Exit', 'KZ_Pct', 'Neden',
                  'Max_Gain_Pct', 'Target_Reached_Pct'):
        assert field in result, f"Missing field: {field}"


def test_simulate_trade_entry_price_includes_slippage():
    raw = _make_raw_ohlcv(n=40, start_price=10.0, end_price=20.0)
    all_dates = raw['Tarih'].tolist()
    entry_date = all_dates[5]
    close = float(raw.loc[raw['Tarih'] == entry_date, 'Kapanis'].iloc[0])
    sig = _make_signal(kapanis=close, atr=0.3)
    result = be._simulate_trade(sig, entry_date, raw, all_dates,
                                target_atr=3.0, gap_filter=False)
    if result is not None:
        expected_entry = close * (1 + be.SLIPPAGE_EACH)
        assert abs(result['Entry'] - expected_entry) < 0.001


# ── _get_piyasa ───────────────────────────────────────────────────────────────

def test_piyasa_kirmizi_when_few_stocks():
    df = pd.DataFrame({'Kapanis': [100.0] * 50, 'EMA_20': [101.0] * 50})
    p, oran = be._get_piyasa(df)
    assert p == 'KIRMIZI'


def test_piyasa_yesil_when_most_above_ema20():
    n = 200
    df = pd.DataFrame({'Kapanis': [100.0] * n, 'EMA_20': [99.0] * n})
    p, oran = be._get_piyasa(df)
    assert p == 'YESIL'
    assert oran == 100.0


def test_piyasa_sari_boundary():
    n = 200
    above = int(n * 0.40)
    closes = [100.0] * n
    ema20s = [99.0] * above + [101.0] * (n - above)
    df = pd.DataFrame({'Kapanis': closes, 'EMA_20': ema20s})
    p, oran = be._get_piyasa(df)
    assert p == 'SARI'


def test_piyasa_kirmizi_below_threshold():
    n = 200
    above = int(n * 0.30)
    closes = [100.0] * n
    ema20s = [99.0] * above + [101.0] * (n - above)
    df = pd.DataFrame({'Kapanis': closes, 'EMA_20': ema20s})
    p, oran = be._get_piyasa(df)
    assert p == 'KIRMIZI'


# ── _get_window_ranges ────────────────────────────────────────────────────────

def test_get_window_ranges_empty_returns_empty():
    assert be._get_window_ranges([]) == []


def test_get_window_ranges_produces_non_overlapping_windows():
    from datetime import date, timedelta
    dates = [(date(2023, 1, 1) + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(365)]
    windows = be._get_window_ranges(dates, window_months=4)
    starts = [w[0] for w in windows]
    assert starts == sorted(set(starts)), "Window starts must be ordered"
    for i in range(len(windows) - 1):
        assert windows[i][1] <= windows[i + 1][0]


def test_get_window_ranges_covers_full_span():
    from datetime import date, timedelta
    dates = [(date(2022, 1, 1) + timedelta(days=i * 7)).strftime('%Y-%m-%d') for i in range(100)]
    windows = be._get_window_ranges(dates, window_months=6)
    assert len(windows) >= 2
    assert windows[0][0] <= dates[0]
    assert windows[-1][1] >= dates[-1]


# ── _print_walkforward_comparison ────────────────────────────────────────────

def test_walkforward_comparison_all_oos_better(capsys):
    """OOS WR >= IS WR on all buckets → VERDICT pass."""
    is_rows  = [{'Vade': 'Kisa', 'Tier': 'Diamond', 'KZ_Pct': 5.0,  'Hold_Days': 5,
                 'Target_Reached_Pct': 100, 'Max_Gain_Pct': 5}] * 20
    oos_rows = [{'Vade': 'Kisa', 'Tier': 'Diamond', 'KZ_Pct': 6.0,  'Hold_Days': 5,
                 'Target_Reached_Pct': 100, 'Max_Gain_Pct': 6}] * 20
    results = {'IS': pd.DataFrame(is_rows), 'OOS': pd.DataFrame(oos_rows)}
    lines = be._print_walkforward_comparison(results, '2022-06-01', '2024-06-01', '2025-06-01')
    out = capsys.readouterr().out
    assert 'OOS' in out
    verdict_line = [l for l in lines if 'VERDİCT' in l][0]
    assert '✅' in verdict_line


def test_walkforward_comparison_overfit_flagged(capsys):
    """OOS WR drops >5pp → ⚠️ flag in output."""
    is_rows  = ([{'Vade': 'Kisa', 'Tier': 'Diamond', 'KZ_Pct':  8.0, 'Hold_Days': 5,
                  'Target_Reached_Pct': 100, 'Max_Gain_Pct': 8}] * 14 +
                [{'Vade': 'Kisa', 'Tier': 'Diamond', 'KZ_Pct': -3.0, 'Hold_Days': 5,
                  'Target_Reached_Pct': 30, 'Max_Gain_Pct': 1}] * 6)   # 70% WR
    oos_rows = ([{'Vade': 'Kisa', 'Tier': 'Diamond', 'KZ_Pct':  8.0, 'Hold_Days': 5,
                  'Target_Reached_Pct': 100, 'Max_Gain_Pct': 8}] * 12 +
                [{'Vade': 'Kisa', 'Tier': 'Diamond', 'KZ_Pct': -3.0, 'Hold_Days': 5,
                  'Target_Reached_Pct': 30, 'Max_Gain_Pct': 1}] * 8)   # 60% WR → -10pp
    results = {'IS': pd.DataFrame(is_rows), 'OOS': pd.DataFrame(oos_rows)}
    lines = be._print_walkforward_comparison(results, '2022-06-01', '2024-06-01', '2025-06-01')
    out = capsys.readouterr().out
    assert '⚠️' in out or '🔴' in out
    verdict_line = [l for l in lines if 'VERDİCT' in l][0]
    assert '⚠️' in verdict_line
