"""Tests for indicator calculations in indicator_engine.py."""
import sys
import os
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indicator_engine import _hesapla_hisse

# ── FIXTURES ─────────────────────────────────────────────────────────────────

WARMUP = 30  # rows before indicators are reliable


def _make_ohlcv(n=60, start_price=10.0, end_price=20.0, volume=1_000_000):
    """Deterministic OHLCV: linear price from start to end, 5% daily spread."""
    dates = [(date(2024, 1, 1) + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    closes = np.linspace(start_price, end_price, n)
    spread = 0.05
    data = [
        {
            'Tarih': d,
            'Hisse': 'TEST',
            'Acilis': c * (1 - spread / 2),
            'En_Yuksek': c * (1 + spread),
            'En_Dusuk': c * (1 - spread),
            'Kapanis': c,
            'Hacim': float(volume),
        }
        for d, c in zip(dates, closes)
    ]
    return pd.DataFrame(data)


def _make_flat_ohlcv(n=60, price=10.0):
    """OHLCV where High == Low == Close == price (Stoch denominator = 0)."""
    dates = [(date(2024, 1, 1) + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(n)]
    data = [
        {
            'Tarih': d,
            'Hisse': 'TEST',
            'Acilis': price,
            'En_Yuksek': price,
            'En_Dusuk': price,
            'Kapanis': price,
            'Hacim': 1_000_000.0,
        }
        for d in dates
    ]
    return pd.DataFrame(data)


# ── RSI ──────────────────────────────────────────────────────────────────────

def test_rsi_bounds():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    rsi = result['RSI_14'].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_rsi_uptrend_above_50():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    assert result['RSI_14'].iloc[WARMUP:].mean() > 50


def test_rsi_downtrend_below_50():
    result = _hesapla_hisse(_make_ohlcv(60, 20.0, 10.0))
    assert result['RSI_14'].iloc[WARMUP:].mean() < 50


# ── ATR ──────────────────────────────────────────────────────────────────────

def test_atr_positive():
    result = _hesapla_hisse(_make_ohlcv(60))
    assert (result['ATR_14'].iloc[WARMUP:] > 0).all()


def test_atr_larger_spread_gives_larger_atr():
    tight = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    wide = _make_ohlcv(60, 10.0, 20.0)
    wide['En_Yuksek'] = wide['Kapanis'] * 1.15
    wide['En_Dusuk'] = wide['Kapanis'] * 0.85
    wide_result = _hesapla_hisse(wide)
    assert wide_result['ATR_14'].iloc[-1] > tight['ATR_14'].iloc[-1]


# ── BOLLINGER BANDS ───────────────────────────────────────────────────────────

def test_bollinger_ordering():
    result = _hesapla_hisse(_make_ohlcv(60))
    post = result.iloc[WARMUP:]
    assert (post['BB_Ust'] > post['BB_Orta']).all()
    assert (post['BB_Orta'] > post['BB_Alt']).all()


def test_bollinger_middle_is_sma20():
    df = _make_ohlcv(60)
    result = _hesapla_hisse(df)
    expected = df['Kapanis'].rolling(20).mean()
    pd.testing.assert_series_equal(
        result['BB_Orta'].round(8),
        expected.round(8),
        check_names=False,
    )


def test_bollinger_width_zero_for_flat():
    result = _hesapla_hisse(_make_flat_ohlcv(60))
    post = result.iloc[WARMUP:]
    assert (post['BB_Ust'] == post['BB_Orta']).all()
    assert (post['BB_Alt'] == post['BB_Orta']).all()


# ── STOCHASTIC ────────────────────────────────────────────────────────────────

def test_stoch_bounds():
    result = _hesapla_hisse(_make_ohlcv(60))
    stoch = result['Stoch_K'].dropna()
    assert (stoch >= 0).all() and (stoch <= 100).all()


def test_stoch_flat_price_is_nan():
    """D5 bug fix: High == Low → denom = 0 → NaN, not 0.0."""
    result = _hesapla_hisse(_make_flat_ohlcv(60))
    assert result['Stoch_K'].iloc[14:].isna().all()


def test_stoch_uptrend_high():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    # Strong uptrend: last close is near rolling high → Stoch_K near 100
    assert result['Stoch_K'].iloc[-1] > 70


# ── ADX ──────────────────────────────────────────────────────────────────────

def test_adx_bounds():
    result = _hesapla_hisse(_make_ohlcv(60))
    adx = result['ADX_14'].dropna()
    assert (adx >= 0).all() and (adx <= 100).all()


def test_adx_uptrend_plus_di_dominates():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    assert result['Plus_DI'].iloc[-1] > result['Minus_DI'].iloc[-1]


def test_adx_downtrend_minus_di_dominates():
    result = _hesapla_hisse(_make_ohlcv(60, 20.0, 10.0))
    assert result['Minus_DI'].iloc[-1] > result['Plus_DI'].iloc[-1]


# ── MFI ──────────────────────────────────────────────────────────────────────

def test_mfi_bounds():
    result = _hesapla_hisse(_make_ohlcv(60))
    mfi = result['MFI_14'].dropna()
    assert (mfi >= 0).all() and (mfi <= 100).all()


def test_mfi_uptrend_above_50():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    assert result['MFI_14'].iloc[WARMUP:].mean() > 50


# ── MACD ─────────────────────────────────────────────────────────────────────

def test_macd_formula():
    df = _make_ohlcv(60)
    result = _hesapla_hisse(df)
    ema12 = df['Kapanis'].ewm(span=12, adjust=False).mean()
    ema26 = df['Kapanis'].ewm(span=26, adjust=False).mean()
    expected = ema12 - ema26
    pd.testing.assert_series_equal(result['MACD'].round(8), expected.round(8), check_names=False)


def test_macd_hist_equals_macd_minus_signal():
    result = _hesapla_hisse(_make_ohlcv(60))
    expected = result['MACD'] - result['MACD_Signal']
    pd.testing.assert_series_equal(
        result['MACD_Hist'].round(8), expected.round(8), check_names=False
    )


def test_macd_uptrend_positive():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    # EMA_12 > EMA_26 in uptrend → MACD > 0
    assert result['MACD'].iloc[-1] > 0


# ── OBV ──────────────────────────────────────────────────────────────────────

def test_obv_uptrend_increases():
    result = _hesapla_hisse(_make_ohlcv(60, 10.0, 20.0))
    assert result['OBV'].iloc[-1] > result['OBV'].iloc[0]


def test_obv_downtrend_decreases():
    result = _hesapla_hisse(_make_ohlcv(60, 20.0, 10.0))
    assert result['OBV'].iloc[-1] < result['OBV'].iloc[0]


# ── VOLUME ────────────────────────────────────────────────────────────────────

def test_hacim_tl_formula():
    df = _make_ohlcv(60)
    result = _hesapla_hisse(df)
    expected = df['Hacim'] * df['Kapanis']
    pd.testing.assert_series_equal(result['Hacim_TL'].round(6), expected.round(6), check_names=False)


# ── RS_63 ─────────────────────────────────────────────────────────────────────

def test_rs63_without_xu100_is_nan():
    result = _hesapla_hisse(_make_ohlcv(80), xu100_raw=None)
    assert result['RS_63'].isna().all()


def test_rs63_outperforming_stock_is_positive():
    n = 80
    df = _make_ohlcv(n, 10.0, 30.0)  # stock +200%
    dates = df['Tarih'].tolist()
    xu100_raw = pd.DataFrame({'XU100_K': [100.0] * n}, index=dates)  # flat index
    result = _hesapla_hisse(df, xu100_raw=xu100_raw)
    valid = result['RS_63'].iloc[63:].dropna()
    assert len(valid) > 0 and valid.mean() > 0


def test_rs63_underperforming_stock_is_negative():
    n = 80
    df = _make_ohlcv(n, 30.0, 10.0)  # stock -67%
    dates = df['Tarih'].tolist()
    xu100_raw = pd.DataFrame({'XU100_K': [100.0] * n}, index=dates)  # flat index
    result = _hesapla_hisse(df, xu100_raw=xu100_raw)
    valid = result['RS_63'].iloc[63:].dropna()
    assert len(valid) > 0 and valid.mean() < 0


# ── EMA ORDERING ─────────────────────────────────────────────────────────────

def test_ema_ordering_long_uptrend():
    df = _make_ohlcv(250, 10.0, 60.0)
    result = _hesapla_hisse(df)
    last = result.iloc[-1]
    assert last['EMA_20'] > last['EMA_50'] > last['EMA_200']


def test_ema_ordering_long_downtrend():
    df = _make_ohlcv(250, 60.0, 10.0)
    result = _hesapla_hisse(df)
    last = result.iloc[-1]
    assert last['EMA_20'] < last['EMA_50'] < last['EMA_200']


# ── HACIM BİRİKİMİ ────────────────────────────────────────────────────────────

def test_hacim_birikim_bounds():
    result = _hesapla_hisse(_make_ohlcv(60))
    accum = result['Hacim_Birikim_10'].dropna()
    assert (accum >= 0).all() and (accum <= 10).all()


def test_hacim_birikim_all_10_in_uptrend():
    # Constant volume > Hacim_Ort_5 on every up day (all days are up days)
    df = _make_ohlcv(60, 10.0, 20.0, volume=5_000_000)
    result = _hesapla_hisse(df)
    last_val = result['Hacim_Birikim_10'].iloc[-1]
    assert last_val == 10.0


# ── POCKET PIVOT ─────────────────────────────────────────────────────────────

def test_pocket_pivot_in_uptrend():
    df = _make_ohlcv(60, 10.0, 20.0)
    result = _hesapla_hisse(df)
    assert result['Pocket_Pivot'].iloc[WARMUP:].sum() > 0


def test_pocket_pivot_is_binary():
    result = _hesapla_hisse(_make_ohlcv(60))
    values = result['Pocket_Pivot'].dropna().unique()
    assert set(values).issubset({0, 1})
