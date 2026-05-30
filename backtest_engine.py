import collections
import json
import os
import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime, timedelta

from strategy_engine import (
    hesapla_kisa_vade_puan,
    hesapla_orta_vade_puan,
    hesapla_duzeltme_puan,
    hesapla_momentum_patlama_puan,
    _safe,
    _max_puan,
    strateji_sec,
    _rolling_perf_from_results,
)


def _load_cfg():
    cfg_path = os.path.join(os.path.dirname(__file__), 'strategy_config.json')
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            return json.load(f)
    return {}

# ── CONFIG ────────────────────────────────────────────────────────────────────
LOOKBACK_MONTHS = 36   # 3 yıl — pencere analizi için geniş veri gerekli
WINDOW_MONTHS   = 8    # Her pencere 8 aylık (~4 pencere = 3 yıl)
COMMISSION_RT   = 0.004   # overridden at runtime from strategy_config.json backtest.commission_rt
SLIPPAGE_EACH   = 0.005   # overridden at runtime from strategy_config.json backtest.slippage_each
HARD_MAX_LOSS   = 0.22    # overridden at runtime from strategy_config.json backtest.hard_max_loss_pct

MAX_HOLD = {'Kisa': 15, 'Orta': 40, 'Duzeltme': 15, 'Momentum': 15}

# Tracks corporate-action gap-drops excluded during simulation; reset per run.
_gap40_count = 0

PARAMS = {
    'Kisa':     {'stop_atr': 1.5, 'stop_floor': 0.85, 'target_atr': 2.0, 'min_rr': 1.2},
    'Orta':     {'stop_atr': 2.0, 'stop_floor': 0.82, 'target_atr': 5.0, 'min_rr': 2.0},
    'Duzeltme': {'stop_atr': 1.5, 'stop_floor': 0.85, 'target_atr': 3.0, 'min_rr': 1.5},
    'Momentum': {'stop_atr': 1.5, 'stop_floor': 0.82, 'target_atr': 3.0, 'min_rr': 1.8},
}

# Günlük kota — sinyalleri_uret() CAPS dict ile eşleşmeli
QUOTALAR = {
    ('Kisa', 'Diamond'):    5,
    ('Kisa', 'Ruby'):       8,
    ('Orta', 'Diamond'):    2,   # 4.3: reduced from 3 (weakest WR 32.8%, CPCV 5th)
    ('Orta', 'Firsat'):     5,   # 4.3: kept at 5 (quota=6 diluted PF 1.29→1.09 in 24m test)
    ('Momentum', 'Diamond'): 5,
}

# Fallback thresholds — overridden at runtime by _compute_thresholds(cfg)
_DEFAULT_THRESHOLDS = {
    'kisa_ruby':     65,
    'kisa_diamond':  80,
    'orta_firsat':   55,
    'orta_diamond':  80,
    'duz_firsat':    35,
    'mom_firsat':    50,
    'mom_diamond':   80,
}


def _compute_thresholds(cfg):
    """Compute dynamic Diamond/Ruby thresholds from scoring config.

    Mirrors sinyalleri_uret() logic. Fallbacks reproduce old hardcoded values
    when strategy_config.json scoring section is absent.
    """
    sc_all = (cfg or {}).get('scoring', {})
    thr    = (cfg or {}).get('thresholds', {})

    kisa_sc      = sc_all.get('kisa_vade', {})
    kisa_max     = _max_puan(kisa_sc, include_base=kisa_sc.get('_base', 50))
    kisa_diamond = int(kisa_max * thr.get('kisa_diamond_pct', 0.80))
    kisa_ruby    = int(kisa_max * thr.get('kisa_ruby_pct', 0.65))

    orta_sc      = sc_all.get('orta_vade', {})
    orta_max     = _max_puan(orta_sc)
    orta_diamond = int(orta_max * thr.get('orta_diamond_pct', 0.80))
    orta_firsat  = int(orta_max * thr.get('orta_firsat_pct', 0.41))

    duz_sc     = sc_all.get('duzeltme', {})
    duz_max    = _max_puan(duz_sc)
    duz_firsat = int(duz_max * thr.get('duzeltme_firsat_pct', 0.28))

    mom_sc      = sc_all.get('momentum_patlama', {})
    mom_max     = _max_puan(mom_sc)
    mom_diamond = int(mom_max * thr.get('momentum_diamond_pct', 0.80))

    return {
        'kisa_ruby':    kisa_ruby,
        'kisa_diamond': kisa_diamond,
        'orta_firsat':  orta_firsat,
        'orta_diamond': orta_diamond,
        'duz_firsat':   duz_firsat,
        'mom_diamond':  mom_diamond,
        'kisa_max':     kisa_max,
        'orta_max':     orta_max,
        'duz_max':      duz_max,
        'mom_max':      mom_max,
    }

MIN_HACIM = {
    'Kisa':     50_000_000,
    'Orta':     50_000_000,
    'Duzeltme': 10_000_000,
    'Momentum': 50_000_000,
}

MIN_STOCKS_PER_DATE = 100

# Variants: (name, target_atr_map, use_trailing, min_rr_map, partial_exit, partial_exit_atr,
#            partial_exit_vades, quota_override, ruby_ema50_gate, ruby_rolling_pf_gate)
# target_atr_map: None = use PARAMS defaults | 'adaptive' = HV_20_Pct-based | dict = per-vade override
# partial_exit: exit 50% at partial_exit_atr×ATR, move stop to breakeven, hold rest to full target
# partial_exit_vades: None = all strategies | list = only these Vade values use partial exit
# quota_override: None = use QUOTALAR | dict e.g. {('Kisa','Ruby'): 4} overrides specific buckets
# ruby_ema50_gate: True = block Kisa Ruby on days XU100 is below its own EMA50
# ruby_rolling_pf_gate: True = skip Ruby when rolling PF (last 15 trades) drops below 0.8
VARIANTS = [
    # T10: Baseline = adaptive_orta (Orta vol-adaptive only, matches live config)
    ('Baseline',
     'adaptive_orta', False, None, False, 0.0, None, None, False, False),
    ('Partial Exit (50%@1.5xATR->breakeven)',
     None, False, None, True, 1.5, None, None, False, False),
    ('Fixed ATR (reference)',
     None, False, None, False, 0.0, None, None, False, False),
    ('Partial + Fixed ATR',
     None, False, None, True, 1.5, None, None, False, False),
    ('Ruby Quota=4',
     'adaptive_orta', False, None, False, 0.0, None, {('Kisa', 'Ruby'): 4}, False, False),
    ('Ruby XU100 EMA50 Gate',
     'adaptive_orta', False, None, False, 0.0, None, None, True, False),
    ('Ruby Rolling PF Gate (last-15, PF<0.8)',
     'adaptive_orta', False, None, False, 0.0, None, None, False, True),
]


# ── MARKET BREADTH ────────────────────────────────────────────────────────────

def _get_piyasa(df_date, yesil_threshold=55):
    toplam = len(df_date)
    if toplam < MIN_STOCKS_PER_DATE:
        return 'KIRMIZI', 0.0
    ema20_ustu = (df_date['Kapanis'] > df_date['EMA_20']).sum()
    oran = ema20_ustu / toplam * 100
    if oran < 35:                   return 'KIRMIZI', oran
    elif oran < yesil_threshold:    return 'SARI', oran
    else:                           return 'YESIL', oran


# ── VOLATILITY-ADAPTIVE ATR TARGET ───────────────────────────────────────────

def _dynamic_target_atr(hv_20_pct, vade):
    """Return target ATR multiplier based on stock's 20-day HV percentile rank.

    Research-backed logic:
    - Low vol (squeeze, HV_20_Pct < 30): tight target → high WR, quick win
    - Normal (30-60): balanced target
    - Trending/high vol (>60): wider target → let the move run

    Derived from: volatility-adaptive ATR studies showing +34% profitability vs fixed ATR.
    """
    hv = float(hv_20_pct) if hv_20_pct is not None else 50.0
    if vade == 'Kisa':
        if hv < 30: return 1.5
        if hv < 60: return 2.0
        return 2.5
    elif vade == 'Orta':
        if hv < 30: return 3.5
        if hv < 60: return 5.0
        return 6.5
    elif vade == 'Duzeltme':
        if hv < 30: return 2.0
        return 3.0
    else:  # Momentum — squeeze breakout = fast move expected
        if hv < 30: return 2.0
        if hv < 60: return 3.0
        return 3.5


# ── SIGNAL GENERATION FOR ONE DATE ───────────────────────────────────────────

def _uret_sinyaller_tarih(df_date, df_prev_indexed, piyasa, cfg=None, thresholds=None, df_5d_ago_indexed=None, breadth_oran=100.0):
    """Returns all qualifying signal dicts for a single date (no dedup, no quotas)."""
    sinyaller = []
    cfg = cfg or {}
    thr = thresholds or _DEFAULT_THRESHOLDS
    o_cfg = cfg.get('orta', {})
    has_pocket = 'Pocket_Pivot' in df_date.columns
    _ruby_min_breadth = float(cfg.get('market', {}).get('kisa_ruby_min_breadth', 55))
    _wtf_on = cfg.get('market', {}).get('weekly_trend_filter', False)
    _has_ema100 = 'EMA_100' in df_date.columns

    for _, row in df_date.iterrows():
        kapanis = _safe(row['Kapanis'])
        atr     = _safe(row['ATR_14'])
        hacim   = _safe(row['Hacim_TL'])
        if atr <= 0 or kapanis <= 0:
            continue

        # ── KISA VADE ────────────────────────────────────────────────────────
        if hacim >= MIN_HACIM['Kisa']:
            hisse = row['Hisse']
            prev_mh_kisa = None
            prev_bb_g_kisa = None
            if not df_prev_indexed.empty and hisse in df_prev_indexed.index:
                prev_val = df_prev_indexed.loc[hisse, 'MACD_Hist']
                if not pd.isna(prev_val):
                    prev_mh_kisa = float(prev_val)
                if 'BB_Genislik' in df_prev_indexed.columns:
                    bb_val = df_prev_indexed.loc[hisse, 'BB_Genislik']
                    if not pd.isna(bb_val):
                        prev_bb_g_kisa = float(bb_val)
            puan = hesapla_kisa_vade_puan(row, cfg, prev_macd_hist=prev_mh_kisa, prev_bb_genislik=prev_bb_g_kisa)
            if puan >= thr['kisa_ruby']:
                if puan >= thr['kisa_diamond']:
                    tier = 'Diamond'
                else:
                    tier = 'Ruby'
                # Weekly trend filter: Ruby only — Diamond exempt (small sample needs all signals)
                _wtf_ruby = (
                    _wtf_on and _has_ema100 and tier == 'Ruby'
                    and _safe(row.get('EMA_100', 0)) > 0
                    and kapanis < _safe(row.get('EMA_100', 0))
                )
                # EMA gate for Kisa Diamond — EMA_100, EMA_50, or mid-zone filter
                _kd_ema100_on  = cfg.get('market', {}).get('kisa_diamond_ema100_gate', False)
                _kd_ema50_on   = cfg.get('market', {}).get('kisa_diamond_ema50_gate', False)
                _kd_midzone_on = cfg.get('market', {}).get('kisa_diamond_mid_zone_gate', False)
                _has_ema50 = 'EMA_50' in df_date.columns
                _ema50_val  = _safe(row.get('EMA_50', 0))
                _ema100_val = _safe(row.get('EMA_100', 0))
                _kd_ema100_skip = _kd_ema100_on and _has_ema100 and _ema100_val > 0 and kapanis < _ema100_val
                _kd_ema50_skip  = _kd_ema50_on  and _has_ema50  and _ema50_val > 0  and kapanis < _ema50_val
                _kd_mid_skip    = (_kd_midzone_on and _has_ema50 and _has_ema100
                                   and _ema50_val > 0 and _ema100_val > 0
                                   and _ema50_val <= kapanis < _ema100_val)
                _wtf_diamond = tier == 'Diamond' and (_kd_ema100_skip or _kd_ema50_skip or _kd_mid_skip)
                # SARI: tüm Kisa bloke (M2 fix). Ruby: breadth gate (N4) + weekly trend filter
                _kisa_skip = piyasa == 'SARI' or (tier == 'Ruby' and breadth_oran < _ruby_min_breadth) or _wtf_ruby or _wtf_diamond
                if not _kisa_skip:
                    p    = PARAMS['Kisa']
                    stop = max(kapanis - p['stop_atr'] * atr, kapanis * p['stop_floor'])
                    hdf  = kapanis + p['target_atr'] * atr
                    risk = kapanis - stop
                    if risk > 0 and (hdf - kapanis) / risk >= p['min_rr']:
                        _hv = row.get('HV_20_Pct') if hasattr(row, 'get') else getattr(row, 'HV_20_Pct', None)
                        sinyaller.append({
                            'Hisse': row['Hisse'], 'Vade': 'Kisa', 'Tier': tier,
                            'Puan': puan, 'PuanPct': puan / thr['kisa_max'] if thr.get('kisa_max') else 0,
                            'Kapanis': kapanis, 'ATR': atr,
                            'HV_20_Pct': float(_hv) if _hv is not None and not pd.isna(_hv) else 50.0,
                        })

        # ── ORTA VADE (YESIL only) ────────────────────────────────────────
        if piyasa == 'YESIL' and hacim >= MIN_HACIM['Orta']:
            # Prev-day MACD_Hist for freshness detection
            hisse = row['Hisse']
            prev_mh = None
            if not df_prev_indexed.empty and hisse in df_prev_indexed.index:
                prev_val = df_prev_indexed.loc[hisse, 'MACD_Hist']
                if not pd.isna(prev_val):
                    prev_mh = float(prev_val)

            adx_ok = not o_cfg.get('adx_gate', False) or (
                _safe(row['ADX_14']) > o_cfg.get('adx_min', 20)
                and _safe(row.get('Plus_DI', 0)) > _safe(row.get('Minus_DI', 0))
            )
            if adx_ok:
                puan = hesapla_orta_vade_puan(row, cfg, prev_macd_hist=prev_mh)
                if puan >= thr['orta_firsat']:
                    tier = 'Diamond' if puan >= thr['orta_diamond'] else 'Firsat'
                    # EMA_100 gate for Orta Diamond (medium-term trend alignment)
                    if tier == 'Diamond' and o_cfg.get('diamond_ema100_gate', False) and _has_ema100:
                        _ema100 = _safe(row.get('EMA_100', 0))
                        if _ema100 > 0 and kapanis < _ema100:
                            continue
                    # ADX Diamond gate — Diamond-only, not all Orta (adx_gate tests rejected for all-Orta)
                    if tier == 'Diamond' and o_cfg.get('diamond_adx_gate', False):
                        if _safe(row.get('ADX_14', 0)) < o_cfg.get('diamond_adx_min', 22):
                            continue
                    p    = PARAMS['Orta']
                    stop = max(kapanis - p['stop_atr'] * atr, kapanis * p['stop_floor'])
                    hdf  = kapanis + p['target_atr'] * atr
                    risk = kapanis - stop
                    if risk > 0 and (hdf - kapanis) / risk >= p['min_rr']:
                        _hv = row.get('HV_20_Pct') if hasattr(row, 'get') else getattr(row, 'HV_20_Pct', None)
                        sinyaller.append({
                            'Hisse': hisse, 'Vade': 'Orta', 'Tier': tier,
                            'Puan': puan, 'PuanPct': puan / thr['orta_max'] if thr.get('orta_max') else 0,
                            'Kapanis': kapanis, 'ATR': atr,
                            'HV_20_Pct': float(_hv) if _hv is not None and not pd.isna(_hv) else 50.0,
                        })

        # ── DUZELTME ─────────────────────────────────────────────────────────
        if (cfg or {}).get('duzeltme', {}).get('enabled', True) and not df_prev_indexed.empty and hacim >= MIN_HACIM['Duzeltme']:
            hisse = row['Hisse']
            if hisse in df_prev_indexed.index:
                dun_kapanis = _safe(df_prev_indexed.loc[hisse, 'Kapanis'])
                macd_ok = (
                    _safe(row['MACD']) > _safe(row['MACD_Signal'])
                    and _safe(row['MACD_Hist']) > 0
                )
                if kapanis < dun_kapanis and macd_ok and kapanis > _safe(row['EMA_20']):
                    puan = hesapla_duzeltme_puan(row, cfg)
                    if puan >= thr['duz_firsat']:
                        p    = PARAMS['Duzeltme']
                        stop = max(kapanis - p['stop_atr'] * atr, kapanis * p['stop_floor'])
                        hdf  = kapanis + p['target_atr'] * atr
                        risk = kapanis - stop
                        if risk > 0 and (hdf - kapanis) / risk >= p['min_rr']:
                            _hv = row.get('HV_20_Pct') if hasattr(row, 'get') else getattr(row, 'HV_20_Pct', None)
                            sinyaller.append({
                                'Hisse': hisse, 'Vade': 'Duzeltme', 'Tier': 'Firsat',
                                'Puan': puan, 'PuanPct': puan / thr['duz_max'] if thr.get('duz_max') else 0,
                                'Kapanis': kapanis, 'ATR': atr,
                                'HV_20_Pct': float(_hv) if _hv is not None and not pd.isna(_hv) else 50.0,
                            })

        # ── MOMENTUM PATLAMA: YESIL tam aktif; diamond_min_breadth üstü SARI'da Diamond ayrıca ────
        _d_min_b = (cfg or {}).get('momentum', {}).get('diamond_min_breadth', 60)
        _mom_ok = (piyasa == 'YESIL') or (piyasa == 'SARI' and breadth_oran >= _d_min_b)
        if _mom_ok and has_pocket and hacim >= MIN_HACIM['Momentum']:
            puan = hesapla_momentum_patlama_puan(row, cfg)
            if puan >= thr['mom_diamond']:
                tier = 'Diamond'

                # Diamond quality gates (mirrors sinyalleri_uret logic — Diamond-only)
                _m_g = (cfg or {}).get('momentum', {})
                if tier == 'Diamond':
                    _r63 = _m_g.get('diamond_rs63_min')
                    if _r63 is not None:
                        rs63_v = row.get('RS_63') if hasattr(row, 'get') else getattr(row, 'RS_63', None)
                        if rs63_v is None or pd.isna(rs63_v) or float(rs63_v) < float(_r63):
                            continue
                    _d_vol = _m_g.get('diamond_vol_mult')
                    if _d_vol is not None:
                        htl = _safe(row['Hacim_TL'])
                        h20 = _safe(row.get('Hacim_Ort_20', 0))
                        if h20 <= 0 or htl < h20 * float(_d_vol):
                            continue
                    if _m_g.get('diamond_bullish_close', False):
                        k  = _safe(row['Kapanis'])
                        hi = _safe(row.get('En_Yuksek', 0))
                        lo = _safe(row.get('En_Dusuk', k))
                        if hi > lo and (k - lo) / (hi - lo) <= 0.60:
                            continue
                    if _m_g.get('diamond_ema_stack', False):
                        e20 = _safe(row.get('EMA_20', 0)); e50 = _safe(row.get('EMA_50', 0)); e200 = _safe(row.get('EMA_200', 0))
                        if not (e20 > e50 > e200 > 0):
                            continue
                    if _m_g.get('diamond_rs_accel', False) and df_5d_ago_indexed is not None:
                        hisse = row['Hisse'] if hasattr(row, '__getitem__') else getattr(row, 'Hisse', '')
                        rs_now = _safe(row.get('RS_63', 0))
                        if hisse in df_5d_ago_indexed.index:
                            rs_ago = df_5d_ago_indexed.loc[hisse, 'RS_63'] if 'RS_63' in df_5d_ago_indexed.columns else None
                            if rs_ago is None or pd.isna(float(rs_ago)) or rs_now <= float(rs_ago):
                                continue
                        else:
                            continue
                    if _m_g.get('diamond_vol_persist', False):
                        h5 = _safe(row.get('Hacim_Ort_5', 0)); h20 = _safe(row.get('Hacim_Ort_20', 0))
                        if h20 <= 0 or h5 <= h20:
                            continue
                    # O'Neil base requirement: PP must fire near EMA_20, not extended
                    _prox_max = _m_g.get('diamond_ema20_proximity_max', 1.10)
                    _e20_v = _safe(row.get('EMA_20', 0))
                    if _e20_v > 0 and kapanis / _e20_v > _prox_max:
                        continue

                p    = PARAMS['Momentum']
                ema20 = _safe(row['EMA_20'])
                stop = max(kapanis - p['stop_atr'] * atr,
                           ema20 * 0.99 if ema20 > 0 else kapanis * p['stop_floor'])
                hdf  = kapanis + p['target_atr'] * atr
                risk = kapanis - stop
                if risk > 0 and (hdf - kapanis) / risk >= p['min_rr']:
                    _hv = row.get('HV_20_Pct') if hasattr(row, 'get') else getattr(row, 'HV_20_Pct', None)
                    sinyaller.append({
                        'Hisse': row['Hisse'], 'Vade': 'Momentum', 'Tier': tier,
                        'Puan': puan, 'PuanPct': puan / thr['mom_max'] if thr.get('mom_max') else 0,
                        'Kapanis': kapanis, 'ATR': atr,
                        'HV_20_Pct': float(_hv) if _hv is not None and not pd.isna(_hv) else 50.0,
                    })

    return sinyaller


def _apply_quotas_and_dedup(sinyaller, quota_override=None):
    """Apply daily (Vade, Tier) quotas and cross-strategy dedup.
    Mirrors sinyalleri_uret() logic exactly:
      1. Dedup: keep highest puan per hisse across all strategies.
      2. Quota: per (Vade, Tier) bucket, keep top-N by puan.
    quota_override: dict like {('Kisa','Ruby'): 4} — merges with QUOTALAR for this call.
    """
    effective_quotas = QUOTALAR if quota_override is None else {**QUOTALAR, **quota_override}

    # Step 1: cross-strategy dedup — highest normalized score (PuanPct) wins
    # Raw Puan is not comparable cross-strategy (Orta max>130, Momentum max=100)
    best = {}
    for s in sinyaller:
        h = s['Hisse']
        pct = s.get('PuanPct', s['Puan'] / 100.0)
        if h not in best or pct > best[h].get('PuanPct', best[h]['Puan'] / 100.0):
            best[h] = s
    deduped = list(best.values())

    # Step 2: quota per (Vade, Tier), sorted by puan DESC
    result = []
    for key, quota in effective_quotas.items():
        vade, tier = key
        bucket = [s for s in deduped if s['Vade'] == vade and s['Tier'] == tier]
        bucket.sort(key=lambda x: x['Puan'], reverse=True)
        result.extend(bucket[:quota])

    return result


def _apply_corr_cap(date_signals, df_returns, tarih, cfg):
    """Remove correlated signal duplicates. Keeps highest-scoring signal per corr group.

    Uses 20-day rolling return correlation from precomputed df_returns.
    Config: position_sizing.corr_cap_enabled / corr_cap_threshold / corr_cap_max.
    corr_cap_max=1 means only 1 signal per correlated cluster.
    """
    ps = (cfg or {}).get('position_sizing', {})
    if not ps.get('corr_cap_enabled', False) or df_returns is None or len(date_signals) <= 1:
        return date_signals

    threshold = float(ps.get('corr_cap_threshold', 0.70))
    max_corr_peers = int(ps.get('corr_cap_max', 1))

    if tarih not in df_returns.index:
        return date_signals

    loc = df_returns.index.get_loc(tarih)
    if not isinstance(loc, (int, np.integer)):
        loc = int(loc)
    if loc < 20:
        return date_signals

    tickers = [s['Hisse'] for s in date_signals]
    ret_slice = df_returns.iloc[loc - 20:loc][
        [t for t in tickers if t in df_returns.columns]
    ]

    sorted_sigs = sorted(date_signals, key=lambda s: -s['Puan'])
    selected = []

    for sig in sorted_sigs:
        t = sig['Hisse']
        if t not in ret_slice.columns:
            selected.append(sig)
            continue

        corr_count = 0
        for sel in selected:
            st = sel['Hisse']
            if st not in ret_slice.columns:
                continue
            pair = ret_slice[[t, st]].dropna()
            if len(pair) < 10:
                continue
            corr_val = pair.corr().iloc[0, 1]
            if not np.isnan(corr_val) and corr_val >= threshold:
                corr_count += 1

        if corr_count < max_corr_peers:
            selected.append(sig)

    return selected


# ── POSITION SIMULATION ───────────────────────────────────────────────────────

def _build_result(signal, sinyal_tarihi, entry_tarih, exit_tarih, hold_days,
                  entry_price, exit_price, neden, max_en_yuksek, hedef):
    kz_pct = (exit_price - entry_price) / entry_price * 100 - COMMISSION_RT * 100
    target_range = hedef - entry_price
    max_gain_pct = (max_en_yuksek - entry_price) / entry_price * 100
    target_reached_pct = (
        min((max_en_yuksek - entry_price) / target_range * 100, 100.0)
        if target_range > 0 else 0.0
    )
    return {
        'Hisse':              signal['Hisse'],
        'Vade':               signal['Vade'],
        'Tier':               signal['Tier'],
        'Puan':               signal['Puan'],
        'Sinyal_Tarihi':      sinyal_tarihi,
        'Giris_Tarihi':       entry_tarih,
        'Cikis_Tarihi':       exit_tarih,
        'Hold_Days':          hold_days,
        'Entry':              round(entry_price, 4),
        'Exit':               round(exit_price, 4),
        'KZ_Pct':             round(kz_pct, 2),
        'Neden':              neden,
        'Max_Gain_Pct':       round(max_gain_pct, 2),
        'Target_Reached_Pct': round(target_reached_pct, 1),
        'Stop_Loss':          round(float(signal.get('Stop_Loss', 0) or 0), 4),
    }


def _simulate_trade(signal, sinyal_tarihi, hisse_raw_df, all_dates,
                    target_atr=None, use_trailing_stop=False, min_rr=None,
                    gap_filter=True, gap_up_pct=1.02, stop_atr=None,
                    partial_exit=False, partial_exit_atr=1.0,
                    partial_exit_vades=None):
    """
    Simulate one trade.
    target_atr: override target multiplier (None = use PARAMS default)
    stop_atr: override stop multiplier (None = use PARAMS default)
    use_trailing_stop: update stop upward after profitable days
    min_rr: override minimum risk:reward ratio (None = use PARAMS default)
    gap_filter: skip entry if next-day open gaps above signal close
    gap_up_pct: gap threshold (default 1.02 = 2% above close)
    partial_exit: exit 50% at partial_exit_atr×ATR gain, move stop to breakeven,
                  hold remaining 50% to full target. Mechanically boosts WR (~+30%).
                  Backed by research: staggered exits improve realized-win frequency.
    partial_exit_vades: if set, partial exit only for signals whose Vade is in this list.
    """
    vade = signal['Vade']
    # Gate partial exit to specific strategies when list provided
    if partial_exit_vades is not None:
        partial_exit = partial_exit and vade in partial_exit_vades
    atr  = signal['ATR']
    p    = PARAMS[vade]

    try:
        sig_idx = all_dates.index(sinyal_tarihi)
    except ValueError:
        return None
    # Phase 0.1: enter at NEXT DAY's OPEN — honest fill. Signal is computed on the
    # close of day T, so the earliest executable price is T+1 open. (Reverses the
    # T2 close-entry, which captured the unattainable signal-day close.)
    signal_close = signal['Kapanis']
    ohlcv = hisse_raw_df.set_index('Tarih')
    if signal_close <= 0:
        return None

    entry_idx = sig_idx + 1
    if entry_idx >= len(all_dates):
        return None
    entry_tarih = all_dates[entry_idx]
    if entry_tarih not in ohlcv.index:
        return None
    try:
        entry_open = float(ohlcv.loc[entry_tarih, 'Acilis'])
    except (TypeError, ValueError, KeyError):
        return None
    if np.isnan(entry_open) or entry_open <= 0:
        return None
    # Gap filter: skip if the stock already gapped up beyond threshold at the open
    # (chasing a gap-up degrades fills and edge).
    if gap_filter and entry_open > float(signal_close) * gap_up_pct:
        return None

    entry_price = entry_open * (1 + SLIPPAGE_EACH)

    s_atr = stop_atr if stop_atr is not None else p['stop_atr']
    stop  = max(entry_price - s_atr * atr, entry_price * p['stop_floor'])
    t_atr = target_atr if target_atr is not None else p['target_atr']
    hedef = entry_price + t_atr * atr

    eff_min_rr = min_rr if min_rr is not None else p['min_rr']
    risk = entry_price - stop
    if risk <= 0 or (hedef - entry_price) / risk < eff_min_rr:
        return None

    partial1_price = None
    partial1_done  = False
    p1_level       = entry_price + partial_exit_atr * atr if partial_exit else float('inf')

    # Simulation runs from the entry day (inclusive): intraday stop/target may hit
    # the same day we entered at the open.
    sim_dates     = all_dates[entry_idx: entry_idx + MAX_HOLD[vade]]
    max_en_yuksek = entry_price
    prev_close    = float(signal_close)

    for i, sim_tarih in enumerate(sim_dates):
        if sim_tarih not in ohlcv.index:
            continue

        r = ohlcv.loc[sim_tarih]
        try:
            en_yuksek = float(r['En_Yuksek'])
            en_dusuk  = float(r['En_Dusuk'])
            kapanis   = float(r['Kapanis'])
            open_r    = float(r['Acilis'])
        except (TypeError, ValueError):
            continue

        if np.isnan(en_yuksek) or np.isnan(en_dusuk):
            if not np.isnan(kapanis):
                prev_close = kapanis
                # No intraday data: use close as stop proxy
                if kapanis <= stop:
                    ep = _blend(kapanis * (1 - SLIPPAGE_EACH))
                    return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                         i + 1, entry_price, ep, 'Stop_NaN', max_en_yuksek, hedef)
                if (kapanis / entry_price - 1) < -HARD_MAX_LOSS:
                    ep = _blend(kapanis * (1 - SLIPPAGE_EACH))
                    return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                         i + 1, entry_price, ep, 'HardStop_NaN', max_en_yuksek, hedef)
            continue

        max_en_yuksek = max(max_en_yuksek, en_yuksek)
        taban_hit = prev_close > 0 and en_dusuk <= prev_close * 0.90

        # Corporate action gap-down: >40% overnight open drop = rights offering / split artifact
        if not np.isnan(open_r) and prev_close > 0 and open_r < prev_close * 0.60 and i > 0:
            global _gap40_count
            _gap40_count += 1
            return None  # exclude — unadjusted corporate action distorts P&L

        # ── Partial exit trigger: first half exits at p1_level ────────────────
        if partial_exit and not partial1_done and en_yuksek >= p1_level:
            partial1_price = p1_level * (1 - SLIPPAGE_EACH)
            partial1_done  = True
            stop           = entry_price           # move stop to breakeven
            # Don't return — continue simulation for remaining 50%

        def _blend(ep2):
            """Blend 50% partial + 50% remaining exit for final price."""
            if partial1_done and partial1_price is not None:
                return 0.5 * partial1_price + 0.5 * ep2
            return ep2

        # Gap above target
        if not np.isnan(open_r) and open_r >= hedef:
            ep = _blend(open_r * (1 - SLIPPAGE_EACH))
            neden = 'Hedef_Partial' if partial1_done else 'Hedef'
            return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                 i + 1, entry_price, ep, neden, max_en_yuksek, hedef)

        # Gap below stop (no taban)
        if not np.isnan(open_r) and open_r <= stop and not taban_hit:
            ep = _blend(open_r * (1 - SLIPPAGE_EACH))
            neden = 'Breakeven' if partial1_done else 'Stop'
            return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                 i + 1, entry_price, ep, neden, max_en_yuksek, hedef)

        # Target hit intraday
        if en_yuksek >= hedef and en_dusuk > stop:
            ep = _blend(hedef * (1 - SLIPPAGE_EACH))
            neden = 'Hedef_Partial' if partial1_done else 'Hedef'
            return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                 i + 1, entry_price, ep, neden, max_en_yuksek, hedef)

        # Stop hit intraday (conservative: stop wins when both triggered)
        if en_dusuk <= stop:
            if taban_hit:
                raw_ep = None
                next_i = i + 1
                if next_i < len(sim_dates) and sim_dates[next_i] in ohlcv.index:
                    nxt_open = ohlcv.loc[sim_dates[next_i], 'Acilis']
                    if not pd.isna(nxt_open) and float(nxt_open) > 0:
                        raw_ep = float(nxt_open) * (1 - SLIPPAGE_EACH)
                if raw_ep is None:
                    raw_ep = stop * (1 - SLIPPAGE_EACH)
                # Stop-limit behavior: taban exit cannot fill worse than stop price
                # (standing limit order at stop fills at stop even when next-day open gaps below)
                stop_limit_price = stop * (1 - SLIPPAGE_EACH)
                if raw_ep < stop_limit_price:
                    raw_ep = stop_limit_price
                ep    = _blend(raw_ep)
                neden = 'Breakeven_Taban' if partial1_done else 'Stop_Taban'
                return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                     i + 1, entry_price, ep, neden, max_en_yuksek, hedef)
            else:
                raw_ep = stop * (1 - SLIPPAGE_EACH)
                ep     = _blend(raw_ep)
                neden  = 'Breakeven' if partial1_done else 'Stop'
                return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                     i + 1, entry_price, ep, neden, max_en_yuksek, hedef)

        if not np.isnan(kapanis):
            # Trailing stop update: lock in gains after profitable close
            if use_trailing_stop and kapanis > entry_price:
                trail_candidate = kapanis - s_atr * atr
                if trail_candidate > stop:
                    stop = trail_candidate
            prev_close = kapanis
            # Hard max loss: force next-day open exit if close exceeds HARD_MAX_LOSS below entry
            if (kapanis / entry_price - 1) < -HARD_MAX_LOSS:
                next_i = i + 1
                raw_ep2 = kapanis * (1 - SLIPPAGE_EACH)
                if next_i < len(sim_dates) and sim_dates[next_i] in ohlcv.index:
                    nxt_open = ohlcv.loc[sim_dates[next_i], 'Acilis']
                    if not pd.isna(nxt_open) and float(nxt_open) > 0:
                        raw_ep2 = float(nxt_open) * (1 - SLIPPAGE_EACH)
                ep = _blend(raw_ep2)
                return _build_result(signal, sinyal_tarihi, entry_tarih, sim_tarih,
                                     i + 1, entry_price, ep, 'HardStop', max_en_yuksek, hedef)

    # Max hold expired
    last_tarih = sim_dates[-1] if sim_dates else entry_tarih
    raw_ep = entry_price
    if last_tarih in ohlcv.index:
        lc = ohlcv.loc[last_tarih, 'Kapanis']
        if not pd.isna(lc) and float(lc) > 0:
            raw_ep = float(lc) * (1 - SLIPPAGE_EACH)
    ep    = (0.5 * partial1_price + 0.5 * raw_ep) if partial1_done and partial1_price else raw_ep
    neden = 'Süre_Doldu_Partial' if partial1_done else 'Süre_Doldu'
    return _build_result(signal, sinyal_tarihi, entry_tarih, last_tarih,
                         len(sim_dates), entry_price, ep, neden, max_en_yuksek, hedef)


# ── STATISTICS ────────────────────────────────────────────────────────────────

def _stats(df):
    if df.empty:
        return {'total': 0, 'wr': 0, 'avg_win': 0, 'avg_loss': 0,
                'pf': 0, 'avg_hold': 0, 'worst': 0, 'avg_tgt': 0, 'avg_mg': 0}
    total   = len(df)
    winners = df[df['KZ_Pct'] > 0]
    losers  = df[df['KZ_Pct'] <= 0]
    wr      = len(winners) / total * 100
    avg_win  = winners['KZ_Pct'].mean() if len(winners) else 0.0
    avg_loss = losers['KZ_Pct'].mean()  if len(losers)  else 0.0
    avg_hold = df['Hold_Days'].mean()
    worst    = df['KZ_Pct'].min()
    gross_w  = winners['KZ_Pct'].sum()
    gross_l  = abs(losers['KZ_Pct'].sum())
    pf       = gross_w / gross_l if gross_l > 0 else float('inf')
    non_win  = df[df['KZ_Pct'] <= 0]
    avg_tgt  = non_win['Target_Reached_Pct'].mean() if len(non_win) else 0.0
    avg_mg   = non_win['Max_Gain_Pct'].mean()        if len(non_win) else 0.0
    return dict(total=total, wr=wr, avg_win=avg_win, avg_loss=avg_loss,
                pf=pf, avg_hold=avg_hold, worst=worst, avg_tgt=avg_tgt, avg_mg=avg_mg)


def _apply_concurrent_filter(trade_df, max_conc, max_heat):
    """Filter trades to enforce concurrent-position and portfolio-heat caps (3.2).

    Processes trades in entry-date order. At each potential entry:
    - Counts open positions (accepted trades with Cikis_Tarihi > entry date).
    - Computes current portfolio heat = sum of (entry - stop) / entry for open positions.
    - Skips trade if either cap is exceeded.

    max_conc=0 disables concurrent cap. max_heat=0.0 disables heat cap.
    """
    if max_conc <= 0 and max_heat <= 0.0:
        return trade_df

    accepted_rows = []

    for _, row in trade_df.iterrows():
        entry_date = str(row['Giris_Tarihi'])
        entry      = float(row['Entry'])
        stop_raw   = row.get('Stop_Loss', None)
        stop       = float(stop_raw) if stop_raw and float(stop_raw) > 0 else entry * 0.85

        open_pos = [a for a in accepted_rows if str(a['Cikis_Tarihi']) > entry_date]

        if max_conc > 0 and len(open_pos) >= max_conc:
            continue

        if max_heat > 0.0:
            current_heat = sum(
                max(float(a['Entry']) - float(a.get('Stop_Loss') or a['Entry'] * 0.85), float(a['Entry']) * 0.01)
                / float(a['Entry'])
                for a in open_pos
            )
            new_heat = max(entry - stop, entry * 0.01) / entry
            if current_heat + new_heat > max_heat:
                continue

        accepted_rows.append(dict(row))

    return pd.DataFrame(accepted_rows) if accepted_rows else pd.DataFrame(columns=trade_df.columns)


def _run_ff_sim(trade_df, initial, risk_pct, max_pct):
    """Run fixed-fractional + flat-lot equity simulation on a DataFrame of trades.

    Returns (ff_eq, ff_max_dd, flat_eq, flat_max_dd) or None if empty.
    """
    if trade_df.empty:
        return None

    flat_eq = 100.0; flat_peak = flat_eq; flat_max_dd = 0.0
    ff_eq   = initial; ff_peak = ff_eq;   ff_max_dd   = 0.0

    for _, row in trade_df.iterrows():
        entry  = float(row['Entry'])
        exit_p = float(row['Exit'])
        stop   = float(row.get('Stop_Loss', entry * 0.85) or (entry * 0.85))
        kz_pct = float(row['KZ_Pct']) / 100

        flat_eq = flat_eq * (1 + kz_pct)
        if flat_eq > flat_peak:
            flat_peak = flat_eq
        flat_max_dd = max(flat_max_dd, (flat_peak - flat_eq) / flat_peak if flat_peak > 0 else 0)

        stop_dist = entry - stop
        if stop_dist <= 0:
            stop_dist = entry * 0.05
        lot = min(int(ff_eq * risk_pct / stop_dist), int(ff_eq * max_pct / entry))
        lot = max(lot, 1)
        ff_eq = max(ff_eq + lot * (exit_p - entry), 1.0)
        if ff_eq > ff_peak:
            ff_peak = ff_eq
        ff_max_dd = max(ff_max_dd, (ff_peak - ff_eq) / ff_peak if ff_peak > 0 else 0)

    return ff_eq, ff_max_dd, flat_eq, flat_max_dd


def _equity_curve_stats(df, cfg=None):
    """Fixed-fractional equity simulation for MaxDD comparison.

    Base: sequential approximation (trades in entry-date order, no overlap).
    3.2: if max_concurrent_positions or max_portfolio_heat_pct set in config,
         also runs concurrent-filtered sim and reports Calmar comparison.
    Returns dict with ff/flat/conc metrics — or None if sizing disabled.
    """
    if df.empty or 'Entry' not in df.columns:
        return None
    ps = (cfg or {}).get('position_sizing', {})
    if not ps.get('enabled'):
        return None

    initial  = float(ps.get('portfolio_value', 100_000))
    risk_pct = float(ps.get('risk_pct', 0.02))
    max_pct  = float(ps.get('max_position_pct', 0.15))
    max_conc = int(ps.get('max_concurrent_positions', 0))
    max_heat = float(ps.get('max_portfolio_heat_pct', 0.0))

    trade_df = df.dropna(subset=['Entry', 'Exit', 'KZ_Pct']).sort_values('Giris_Tarihi').reset_index(drop=True)
    if trade_df.empty:
        return None

    base = _run_ff_sim(trade_df, initial, risk_pct, max_pct)
    if base is None:
        return None
    ff_eq, ff_max_dd, flat_eq, flat_max_dd = base

    try:
        from datetime import date as _d
        d1 = _d.fromisoformat(str(trade_df['Giris_Tarihi'].iloc[0]))
        d2 = _d.fromisoformat(str(trade_df['Giris_Tarihi'].iloc[-1]))
        n_yrs = max((d2 - d1).days / 365, 0.1)
    except Exception:
        n_yrs = 2.0

    ff_cagr    = (ff_eq / initial)  ** (1 / n_yrs) - 1
    flat_cagr  = (flat_eq / 100.0) ** (1 / n_yrs) - 1
    ff_calmar  = ff_cagr   / ff_max_dd   if ff_max_dd   > 0 else float('inf')
    flat_calmar = flat_cagr / flat_max_dd if flat_max_dd > 0 else float('inf')

    result = {
        'ff_cagr': ff_cagr, 'ff_max_dd': ff_max_dd, 'ff_calmar': ff_calmar, 'ff_final': ff_eq,
        'flat_cagr': flat_cagr, 'flat_max_dd': flat_max_dd, 'flat_calmar': flat_calmar,
        'base_n': len(trade_df),
    }

    # 3.2: concurrent-cap variant
    if max_conc > 0 or max_heat > 0.0:
        conc_df = _apply_concurrent_filter(trade_df, max_conc, max_heat)
        if not conc_df.empty:
            conc = _run_ff_sim(conc_df, initial, risk_pct, max_pct)
            if conc:
                cff_eq, cff_max_dd, _, _ = conc
                cff_cagr   = (cff_eq / initial) ** (1 / n_yrs) - 1
                cff_calmar = cff_cagr / cff_max_dd if cff_max_dd > 0 else float('inf')
                result.update({
                    'conc_n':      len(conc_df),
                    'conc_cagr':   cff_cagr,
                    'conc_max_dd': cff_max_dd,
                    'conc_calmar': cff_calmar,
                    'conc_final':  cff_eq,
                })

    return result


def _print_variant_block(variant_name, df_results):
    """Print per-strategy stats for one variant."""
    all_vadeler = ['Kisa', 'Orta', 'Duzeltme', 'Momentum']
    print(f"\n  {'═'*56}")
    print(f"  VARIANT: {variant_name}")
    print(f"  {'═'*56}")
    for vade in all_vadeler:
        if vade == 'Kisa':
            tiers = ['Diamond', 'Ruby']
        elif vade == 'Duzeltme':
            tiers = ['Firsat']
        else:
            tiers = ['Diamond', 'Firsat']
        for tier in tiers:
            sub = df_results[(df_results['Vade'] == vade) & (df_results['Tier'] == tier)]
            if sub.empty:
                continue
            s = _stats(sub)
            pf_str = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "∞"
            neden = ', '.join(f"{k}:{v}" for k, v in sub['Neden'].value_counts().items())
            print(f"\n  ┌─ {vade} {tier} ({s['total']} işlem)")
            print(f"  │  WR: %{s['wr']:.1f}  |  PF: {pf_str}  |  "
                  f"Ort.Kazanç: +%{s['avg_win']:.2f}  |  Ort.Kayıp: %{s['avg_loss']:.2f}")
            print(f"  │  Ort.Süre: {s['avg_hold']:.1f}g  |  En kötü: %{s['worst']:.2f}")
            print(f"  │  Kaybedenler — Maks.kazanç: +%{s['avg_mg']:.2f} "
                  f"| Hedefe yakınlık: %{s['avg_tgt']:.1f}")
            # Proximity bucket distribution for non-winners
            non_win = sub[sub['KZ_Pct'] <= 0]
            if len(non_win) > 0:
                buckets = [(0, 25, '0-25%'), (25, 50, '25-50%'),
                           (50, 75, '50-75%'), (75, 100, '75-100%')]
                dist = ' | '.join(
                    f"{lbl}:{len(non_win[(non_win['Target_Reached_Pct'] >= lo) & (non_win['Target_Reached_Pct'] < hi)])}"
                    for lo, hi, lbl in buckets
                )
                briefly_up = len(non_win[non_win['Max_Gain_Pct'] > 0])
                briefly_pct = briefly_up / len(non_win) * 100
                print(f"  │  Yakınlık dağılımı: {dist}")
                print(f"  │  Kısa süre karda: {briefly_up}/{len(non_win)} (%{briefly_pct:.0f})")
            print(f"  │  Çıkış: {neden}")
            print(f"  └{'─'*52}")


def _analiz_kazanan_kaybeden(df):
    """Winner vs loser deep-dive: by month, hold period bucket, puan decile."""
    print(f"\n{'═'*70}")
    print("  KAZANAN vs KAYBEDEN ANALİZİ (Baseline)")
    print(f"{'═'*70}")

    for vade_tier, label in [
        (('Kisa', 'Diamond'), 'Kisa Diamond'),
        (('Kisa', 'Ruby'),    'Kisa Ruby'),
        (('Orta', 'Firsat'),  'Orta Firsat'),
    ]:
        sub = df[(df['Vade'] == vade_tier[0]) & (df['Tier'] == vade_tier[1])].copy()
        if sub.empty:
            continue
        print(f"\n  [{label}]")

        # WR by month
        sub['Ay'] = sub['Sinyal_Tarihi'].str[:7]
        month_wr = sub.groupby('Ay').apply(
            lambda g: round(len(g[g['KZ_Pct'] > 0]) / len(g) * 100, 1)
        ).reset_index()
        month_wr.columns = ['Ay', 'WR']
        print(f"  Aylık WR: {' | '.join(f'{r.Ay}: %{r.WR}' for _, r in month_wr.iterrows())}")

        # WR by puan bucket (fixed bins)
        puan_min, puan_max = sub['Puan'].min(), sub['Puan'].max()
        bins = [puan_min - 1, (puan_min + puan_max) / 2, puan_max + 1]
        labels_p = ['Dusuk', 'Yuksek']
        sub['Puan_Grp'] = pd.cut(sub['Puan'], bins=bins, labels=labels_p)
        decile_wr = sub.groupby('Puan_Grp', observed=True).apply(
            lambda g: (round(len(g[g['KZ_Pct'] > 0]) / len(g) * 100, 1), len(g))
        )
        print(f"  Puan Grubu WR (median split): {' | '.join(f'{k}: %{v[0]} ({v[1]} işlem)' for k, v in decile_wr.items())}")

        # WR by hold bucket
        sub['Hold_Bucket'] = pd.cut(sub['Hold_Days'], bins=[0,3,7,12,50], labels=['1-3g','4-7g','8-12g','13+g'])
        hold_wr = sub.groupby('Hold_Bucket', observed=True).apply(
            lambda g: (round(len(g[g['KZ_Pct'] > 0]) / len(g) * 100, 1), len(g))
        )
        print(f"  Hold Süresi WR: {' | '.join(f'{k}: %{v[0]} ({v[1]} işlem)' for k, v in hold_wr.items())}")

        # Exit type breakdown for winners vs losers
        win_exit = sub[sub['KZ_Pct'] > 0]['Neden'].value_counts()
        los_exit = sub[sub['KZ_Pct'] <= 0]['Neden'].value_counts()
        print(f"  Kazananlar çıkış: {dict(win_exit)}")
        print(f"  Kaybedenler çıkış: {dict(los_exit)}")


def _karsilastirma_tablosu(all_variant_results):
    """Print compact cross-variant comparison tables."""
    hdr = (f"  {'Variant':<28} {'İşlem':>6} {'WR%':>6} {'PF':>5} "
           f"{'OrtKaz':>8} {'OrtKay':>8} {'OrtSüre':>8}")
    sep = f"  {'-'*66}"

    def _blok(title, vade, tier):
        print(f"\n{'═'*70}")
        print(f"  KARSILASTIRMA TABLOSU — {title}")
        print(f"{'═'*70}")
        print(hdr); print(sep)
        for name, df in all_variant_results.items():
            sub = df[(df['Vade'] == vade) & (df['Tier'] == tier)]
            if sub.empty:
                print(f"  {name:<28} {'—':>6}"); continue
            s = _stats(sub)
            pf_s = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "∞"
            print(f"  {name:<28} {s['total']:>6} {s['wr']:>5.1f}% {pf_s:>5} "
                  f"{s['avg_win']:>+7.2f}% {s['avg_loss']:>+7.2f}% {s['avg_hold']:>7.1f}g")

    # Kisa Diamond + Ruby combined row
    def _kisa_blok(title):
        print(f"\n{'═'*70}")
        print(f"  KARSILASTIRMA TABLOSU — {title}")
        print(f"{'═'*70}")
        print(hdr); print(sep)
        for name, df in all_variant_results.items():
            sub = df[df['Vade'] == 'Kisa']
            if sub.empty:
                print(f"  {name:<28} {'—':>6}"); continue
            s = _stats(sub)
            pf_s = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "∞"
            d_n = len(sub[sub['Tier'] == 'Diamond'])
            r_n = len(sub[sub['Tier'] == 'Ruby'])
            print(f"  {name:<28} {s['total']:>6} {s['wr']:>5.1f}% {pf_s:>5} "
                  f"{s['avg_win']:>+7.2f}% {s['avg_loss']:>+7.2f}% {s['avg_hold']:>7.1f}g"
                  f"  (💎{d_n} 🔴{r_n})")
    _kisa_blok('Kisa Vade  (Diamond 💎 + Ruby 🔴 birlikte)')
    _blok('Orta Firsat', 'Orta', 'Firsat')

    for name, df in all_variant_results.items():
        if not df[df['Vade'] == 'Momentum'].empty:
            _blok('Momentum Patlama (tum tier)', 'Momentum', 'Diamond')
            break


# ── WINDOWED ANALYSIS ─────────────────────────────────────────────────────────

def _get_window_ranges(all_dates, window_months=WINDOW_MONTHS):
    """Split all_dates into non-overlapping ~window_months-month ranges."""
    if not all_dates:
        return []
    windows = []
    start_dt = pd.to_datetime(all_dates[0])
    end_dt   = pd.to_datetime(all_dates[-1])
    cursor   = start_dt
    while cursor < end_dt:
        next_cursor = cursor + pd.DateOffset(months=window_months)
        w_start = cursor.strftime('%Y-%m-%d')
        w_end   = next_cursor.strftime('%Y-%m-%d')
        dates_in = [d for d in all_dates if w_start <= d < w_end]
        if dates_in:
            windows.append((w_start, w_end))
        cursor = next_cursor
    return windows


def _print_windowed_stats(baseline_df, all_dates, label='Baseline'):
    """Per 8-month window WR/PF breakdown for key strategy+tier pairs."""
    windows = _get_window_ranges(all_dates)
    if len(windows) < 2:
        return
    print(f"\n{'═'*70}")
    print(f"  PENCERE ANALİZİ — {len(windows)} × {WINDOW_MONTHS} Aylık Dönem ({label})")
    print(f"{'═'*70}")
    hdr = f"  {'Dönem':<16} {'İşlem':>6} {'WR%':>6} {'PF':>5} {'OrtKaz':>8} {'OrtKay':>8}"
    sep = f"  {'-'*52}"

    for vade_tier, label in [
        (('Kisa', 'Diamond'), 'Kisa Diamond'),
        (('Kisa', 'Ruby'),    'Kisa Ruby'),
        (('Orta', 'Firsat'),  'Orta Firsat'),
        (('Momentum', 'Diamond'), 'Momentum Diamond'),
    ]:
        sub_all = baseline_df[
            (baseline_df['Vade'] == vade_tier[0]) &
            (baseline_df['Tier'] == vade_tier[1])
        ]
        if sub_all.empty:
            continue
        print(f"\n  [{label}]")
        print(hdr); print(sep)
        for w_start, w_end in windows:
            sub = sub_all[
                (sub_all['Sinyal_Tarihi'] >= w_start) &
                (sub_all['Sinyal_Tarihi'] < w_end)
            ]
            period = f"{w_start[:7]}→{w_end[:7]}"
            if sub.empty:
                print(f"  {period:<16} {'—':>6}")
                continue
            s = _stats(sub)
            pf_s = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "∞"
            print(f"  {period:<16} {s['total']:>6} {s['wr']:>5.1f}% "
                  f"{pf_s:>5} {s['avg_win']:>+7.2f}% {s['avg_loss']:>+7.2f}%")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def _build_xu100_regime_map(df_raw):
    """Returns {date: bool} — True = XU100 close > EMA20 on that date."""
    xu100 = df_raw[df_raw['Hisse'] == 'XU100.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if xu100.empty:
        return {}
    xu100['EMA_20'] = xu100['Kapanis'].ewm(span=20, adjust=False).mean()
    xu100['ok'] = xu100['Kapanis'] > xu100['EMA_20']
    return xu100.set_index('Tarih')['ok'].to_dict()


def _build_xu100_ema50_map(df_raw):
    """Returns {date: bool} — True = XU100 close > EMA50 (stricter long-term trend gate)."""
    xu100 = df_raw[df_raw['Hisse'] == 'XU100.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if xu100.empty:
        return {}
    xu100['EMA_50'] = xu100['Kapanis'].ewm(span=50, adjust=False).mean()
    xu100['ok'] = xu100['Kapanis'] > xu100['EMA_50']
    return xu100.set_index('Tarih')['ok'].to_dict()


def _build_xu100_vol_map(df_raw):
    """Returns {date: float} — Wilder ATR_14 / Close ratio for XU100 on each date.
    High ratio = choppy/volatile market. Gate Orta Firsat when this exceeds xu100_vol_max."""
    xu100 = df_raw[df_raw['Hisse'] == 'XU100.IS'][
        ['Tarih', 'En_Yuksek', 'En_Dusuk', 'Kapanis']
    ].sort_values('Tarih').copy()
    if xu100.empty:
        return {}
    prev_close = xu100['Kapanis'].shift(1)
    tr = pd.concat([
        xu100['En_Yuksek'] - xu100['En_Dusuk'],
        (xu100['En_Yuksek'] - prev_close).abs(),
        (xu100['En_Dusuk']  - prev_close).abs(),
    ], axis=1).max(axis=1)
    xu100['ATR_14'] = tr.ewm(alpha=1/14, adjust=False).mean()
    xu100['vol_ratio'] = xu100['ATR_14'] / xu100['Kapanis'].replace(0, float('nan'))
    return xu100.set_index('Tarih')['vol_ratio'].fillna(0.0).to_dict()


def _build_xutum_rs_map(df_raw):
    """Returns {date: float} — XU100 20d return minus XUTUM 20d return (%).
    Positive = large caps outperforming small/mid = cap-rotation risk-off.
    Ruby gate fires when this exceeds market.xutum_rs_threshold (default 3.0)."""
    xu100 = df_raw[df_raw['Hisse'] == 'XU100.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    xutum = df_raw[df_raw['Hisse'] == 'XUTUM.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if xu100.empty or xutum.empty:
        return {}
    xu100['ret_20'] = xu100['Kapanis'].pct_change(20) * 100
    xutum['ret_20'] = xutum['Kapanis'].pct_change(20) * 100
    merged = xu100.merge(xutum, on='Tarih', suffixes=('_xu', '_xt'))
    merged['xutum_rs'] = merged['ret_20_xu'] - merged['ret_20_xt']
    return merged.set_index('Tarih')['xutum_rs'].fillna(0.0).to_dict()


def _build_try_regime_map(df_raw):
    """Returns {date: bool} — True = USD/TRY above its 20d EMA (TRY weakening).
    Gate Orta signals when True: TRY depreciation drives BIST selloffs regardless of technicals."""
    usdtry = df_raw[df_raw['Hisse'] == 'USDTRY=X'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if usdtry.empty:
        return {}
    usdtry['EMA_20'] = usdtry['Kapanis'].ewm(span=20, adjust=False).mean()
    usdtry['try_above'] = usdtry['Kapanis'] > usdtry['EMA_20']
    return usdtry.set_index('Tarih')['try_above'].to_dict()


def _build_xbank_regime_map(df_raw):
    """Returns {date: bool} — True = XBANK.IS above its 20d EMA (banking sector healthy).
    Block Ruby when False: XBANK downtrend correlates with mid-cap distribution (50.6% bad-window days
    vs 18.9-24.3% in good windows)."""
    xbank = df_raw[df_raw['Hisse'] == 'XBANK.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if xbank.empty:
        return {}
    xbank['EMA_20'] = xbank['Kapanis'].ewm(span=20, adjust=False).mean()
    xbank['above_ema'] = xbank['Kapanis'] >= xbank['EMA_20']
    return xbank.set_index('Tarih')['above_ema'].to_dict()


def _build_xu100_roc_map(df_raw):
    """Returns {date: float} — XU100 10-day rate-of-change (%).
    Negative ROC = index declining over last 10 trading days.
    Gate fires when ROC < threshold (default -2%) — blocks bear-rally signals."""
    xu100 = df_raw[df_raw['Hisse'] == 'XU100.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if xu100.empty:
        return {}
    xu100['roc_10'] = xu100['Kapanis'].pct_change(10) * 100.0
    return xu100.set_index('Tarih')['roc_10'].fillna(0.0).to_dict()


def _build_xu100_ema200_map(df_raw):
    """Returns {date: bool} — True = XU100 close > EMA200 (long-term trend intact).
    Slow master-switch: only fires in deep sustained bears (not short-term corrections).
    All signals blocked when False. Unlike EMA20/50 which whipsaw on bear rallies."""
    xu100 = df_raw[df_raw['Hisse'] == 'XU100.IS'][['Tarih', 'Kapanis']].sort_values('Tarih').copy()
    if xu100.empty:
        return {}
    xu100['EMA_200'] = xu100['Kapanis'].ewm(span=200, adjust=False).mean()
    xu100['ok'] = xu100['Kapanis'] > xu100['EMA_200']
    return xu100.set_index('Tarih')['ok'].to_dict()


def _collect_signals(df_ind, all_dates, cfg=None, xu100_regime_map=None, xu100_vol_map=None,
                     thresholds=None, apply_quotas=True, force_all_markets=False,
                     xutum_rs_map=None, try_regime_map=None, xbank_regime_map=None,
                     xu100_roc_map=None, bar_counts=None, xu100_ema200_map=None):
    """Signal collection phase — returns list of (tarih, signal_dict).

    apply_quotas=True (default): applies daily dedup + quota per (Vade, Tier), exactly
      matching the live sinyalleri_uret() logic. Use for realistic backtest simulation.
    apply_quotas=False: returns ALL qualifying signals. Use for grid-search raw collection
      where you want to re-filter/re-quota with different threshold combos.
    force_all_markets=False: when True, treats all non-KIRMIZI dates as YESIL so all
      strategies run (for yellow-market analysis). Each signal tagged with '_market'.
    """
    cfg = cfg or {}
    m_cfg = cfg.get('market', {})
    yesil_thr = m_cfg.get('yesil_threshold', 55)
    min_bars  = int(m_cfg.get('min_bars', 0))
    xu100_filter    = m_cfg.get('xu100_regime_filter', False)
    xu100_ema200_f  = m_cfg.get('xu100_ema200_filter', False) and xu100_ema200_map is not None
    o_cfg = cfg.get('orta', {})
    xu100_vol_gate = o_cfg.get('xu100_vol_gate', False) and xu100_vol_map is not None
    xu100_vol_max  = float(o_cfg.get('xu100_vol_max', 0.025))
    xutum_filter   = m_cfg.get('xutum_ruby_filter', False) and xutum_rs_map is not None
    xutum_rs_thr   = float(m_cfg.get('xutum_rs_threshold', 3.0))
    try_filter     = m_cfg.get('try_regime_filter', False) and try_regime_map is not None
    xbank_filter   = m_cfg.get('xbank_ruby_filter', False) and xbank_regime_map is not None
    roc_filter     = m_cfg.get('xu100_roc_filter', False) and xu100_roc_map is not None
    roc_min        = float(m_cfg.get('xu100_roc_min', -2.0))
    candidate_signals = []

    for i, tarih in enumerate(all_dates):
        if i % 50 == 0:
            print(f"        {tarih}  ({i}/{len(all_dates)}) — aday: {len(candidate_signals)}")

        df_date = df_ind[df_ind['Tarih'] == tarih]
        piyasa, breadth_oran = _get_piyasa(df_date, yesil_thr)
        if piyasa == 'KIRMIZI':
            continue

        # XU100 regime filter: skip date when index is below its own EMA20
        if xu100_filter and xu100_regime_map is not None:
            if not xu100_regime_map.get(tarih, True):
                continue

        # XU100 EMA200 master-switch: skip ALL signals when index below 200d MA (deep bear)
        if xu100_ema200_f and not xu100_ema200_map.get(tarih, True):
            continue

        # XU100 ROC(10d) gate: skip date when index lost >roc_min% over last 10 days
        if roc_filter and xu100_roc_map.get(tarih, 0.0) < roc_min:
            continue

        effective_piyasa = 'YESIL' if force_all_markets else piyasa

        df_prev = (
            df_ind[df_ind['Tarih'] == all_dates[i - 1]].set_index('Hisse')
            if i > 0 else pd.DataFrame()
        )
        df_5d = (
            df_ind[df_ind['Tarih'] == all_dates[i - 5]].set_index('Hisse')
            if i >= 5 else pd.DataFrame()
        )

        date_signals = _uret_sinyaller_tarih(df_date, df_prev, effective_piyasa, cfg, thresholds=thresholds, df_5d_ago_indexed=df_5d, breadth_oran=breadth_oran)

        # Min-bars gate: drop signals for stocks with insufficient history (noisy EMA_200/100)
        if min_bars > 0 and bar_counts is not None:
            date_signals = [s for s in date_signals if bar_counts.get(s['Hisse'], 0) >= min_bars]

        # XU100 vol gate: drop Orta when index ATR_14/Close too high (choppy)
        if xu100_vol_gate and xu100_vol_map.get(tarih, 0.0) > xu100_vol_max:
            date_signals = [s for s in date_signals if s.get('Vade') != 'Orta']

        # XUTUM divergence gate: block Ruby when large-cap/small-cap RS > threshold
        if xutum_filter and xutum_rs_map.get(tarih, 0.0) > xutum_rs_thr:
            date_signals = [s for s in date_signals
                            if not (s.get('Vade') == 'Kisa' and s.get('Tier') == 'Ruby')]

        # USD/TRY regime gate: block Orta when TRY weakening
        if try_filter and try_regime_map.get(tarih, False):
            date_signals = [s for s in date_signals if s.get('Vade') != 'Orta']

        # XBANK regime gate: block Ruby when banking sector in downtrend (XBANK < EMA20)
        if xbank_filter and not xbank_regime_map.get(tarih, True):
            date_signals = [s for s in date_signals
                            if not (s.get('Vade') == 'Kisa' and s.get('Tier') == 'Ruby')]

        if force_all_markets:
            for s in date_signals:
                s['_market'] = piyasa

        if apply_quotas and date_signals:
            date_signals = _apply_quotas_and_dedup(date_signals)

        for signal in date_signals:
            candidate_signals.append((tarih, signal))

    return candidate_signals



def _backtest_j3_adaptive(df_ind, df_raw, all_dates, cfg, thresholds,
                          xu100_regime_map, xu100_vol_map,
                          xutum_rs_map=None, try_regime_map=None, xbank_regime_map=None,
                          xu100_roc_map=None, xu100_ema200_map=None):
    """J3: Simulate with per-date adaptive quotas based on running closed-trade performance.

    Unlike the variants loop (pre-collects all signals, simulates in fixed quota mode),
    J3 processes one date at a time:
      1. Collect raw signals for date (no quotas)
      2. Compute rolling PF from trades closed so far
      3. strateji_sec() → adaptive quota dict
      4. Apply adaptive quotas + dedup → that day's entries
      5. Simulate, record closed trades → feed back into rolling perf

    This accurately mirrors how strateji_sec() behaves in live trading.
    """
    print("        [J3] Raw sinyal toplaniyor (kota uygulanmadan)...")
    raw_signals = _collect_signals(
        df_ind, all_dates, cfg,
        xu100_regime_map=xu100_regime_map,
        xu100_vol_map=xu100_vol_map,
        thresholds=thresholds,
        apply_quotas=False,
        xutum_rs_map=xutum_rs_map,
        try_regime_map=try_regime_map,
        xbank_regime_map=xbank_regime_map,
        xu100_roc_map=xu100_roc_map,
        xu100_ema200_map=xu100_ema200_map,
    )

    # Group raw signals by date
    raw_by_date = {}
    for tarih, signal in raw_signals:
        raw_by_date.setdefault(tarih, []).append(signal)

    # Pre-compute breadth per date (needed for Ruby breadth gate inside strateji_sec)
    yesil_thr   = cfg.get('market', {}).get('yesil_threshold', 55)
    breadth_map = {}
    for tarih in all_dates:
        df_d = df_ind[df_ind['Tarih'] == tarih]
        _, b = _get_piyasa(df_d, yesil_thr)
        breadth_map[tarih] = b

    raw_by_hisse = {h: g.reset_index(drop=True) for h, g in df_raw.groupby('Hisse')}
    m_cfg      = cfg.get('market', {})
    gap_filter = m_cfg.get('gap_up_filter', True)
    gap_pct    = m_cfg.get('gap_up_pct', 1.02)
    vol_adaptive_orta = cfg.get('orta', {}).get('vol_adaptive_target', False)

    closed_results = []
    open_pos = {'Kisa': {}, 'Orta': {}, 'Duzeltme': {}, 'Momentum': {}}
    results  = []

    for tarih in sorted(raw_by_date.keys()):
        # Adaptive caps from trades closed before this date
        rolling_perf  = _rolling_perf_from_results(closed_results, cfg)
        adaptive_caps = strateji_sec(rolling_perf, cfg, verbose=False)

        # Apply adaptive quotas to today's raw signals
        day_signals = _apply_quotas_and_dedup(raw_by_date[tarih],
                                              quota_override=adaptive_caps)

        for signal in day_signals:
            vade  = signal['Vade']
            hisse = signal['Hisse']

            mevcut_exit = open_pos[vade].get(hisse, '')
            if mevcut_exit and tarih <= mevcut_exit:
                continue

            raw_df = raw_by_hisse.get(hisse)
            if raw_df is None:
                continue

            t_atr = None
            if vol_adaptive_orta and vade == 'Orta':
                t_atr = _dynamic_target_atr(signal.get('HV_20_Pct', 50), 'Orta')

            result = _simulate_trade(
                signal, tarih, raw_df, all_dates,
                gap_filter=gap_filter, gap_up_pct=gap_pct,
                target_atr=t_atr,
            )
            if result is None:
                continue

            open_pos[vade][hisse] = result['Cikis_Tarihi']
            results.append(result)
            closed_results.append(result)

    return pd.DataFrame(results) if results else pd.DataFrame()


def backtest_calistir(cfg=None, months=None, days=None, out_suffix=''):
    """Full backtest. months or days override LOOKBACK_MONTHS. out_suffix appended to output filenames."""
    if cfg is None:
        cfg = _load_cfg()

    if days is not None:
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        period_label = f"{days} gunluk"
    else:
        lb_months = months if months is not None else LOOKBACK_MONTHS
        cutoff = (datetime.now() - timedelta(days=lb_months * 30)).strftime('%Y-%m-%d')
        period_label = f"{lb_months} aylik"

    print(f"Backtest Motoru: {period_label} gercek strateji simulasyonu - 4 variant karsilastirmasi...")

    conn   = sqlite3.connect('bist_ajan.db')

    df_ind = pd.read_sql(
        f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih >= '{cutoff}' ORDER BY Tarih ASC",
        conn,
    )
    df_raw = pd.read_sql(
        "SELECT Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis "
        f"FROM Hisse_Verileri WHERE Tarih >= '{cutoff}' ORDER BY Tarih ASC",
        conn,
    )
    # Full-history bar counts per stock (not just cutoff period) for min_bars gate
    _bc_q = pd.read_sql("SELECT Hisse, COUNT(*) as n FROM Hisse_Indikatorleri GROUP BY Hisse", conn)
    bar_counts_full = dict(zip(_bc_q['Hisse'], _bc_q['n']))
    conn.close()

    if df_ind.empty:
        print("Veri yok. Once veri_motoru.py ve indicator_engine.py calistirin.")
        return

    has_pocket = 'Pocket_Pivot' in df_ind.columns
    if not has_pocket:
        print("  NOT: Pocket_Pivot kolonu yok — Momentum strateji atlanacak.")
        print("       Eklemek icin: py indicator_engine.py")

    import backtest_engine as _self
    bst = cfg.get('backtest', {})
    _self.COMMISSION_RT = float(bst.get('commission_rt', 0.004))
    _self.SLIPPAGE_EACH = float(bst.get('slippage_each', 0.005))
    _self.HARD_MAX_LOSS = float(bst.get('hard_max_loss_pct', 0.22))
    _self.PARAMS['Kisa']['target_atr']     = float(bst.get('target_atr_kisa', 2.0))
    _self.PARAMS['Kisa']['stop_atr']       = float(bst.get('stop_atr_kisa', 1.5))
    _self.PARAMS['Orta']['stop_atr']       = float(bst.get('stop_atr_orta', 2.0))
    _self.PARAMS['Duzeltme']['stop_atr']   = float(bst.get('stop_atr_duzeltme', 1.5))
    _self.PARAMS['Duzeltme']['target_atr'] = float(bst.get('target_atr_duzeltme', 3.0))
    _self.PARAMS['Momentum']['stop_atr']   = float(bst.get('stop_atr_momentum', 1.5))
    _self.PARAMS['Momentum']['target_atr'] = float(bst.get('target_atr_momentum', 3.0))
    _self.PARAMS['Momentum']['min_rr']     = float(bst.get('min_rr_momentum', 1.8))

    all_dates    = sorted(df_ind['Tarih'].unique().tolist())
    raw_by_hisse = {h: g.reset_index(drop=True) for h, g in df_raw.groupby('Hisse')}

    komisyon_str = f"%{_self.COMMISSION_RT*100:.2f}" if _self.COMMISSION_RT > 0 else "yok"
    print(f"  Tarih : {all_dates[0]} -> {all_dates[-1]}  ({len(all_dates)} gun)")
    print(f"  Hisse : {df_ind['Hisse'].nunique()}")
    print(f"  Maliyet: komisyon {komisyon_str} + %{_self.SLIPPAGE_EACH*200:.1f} toplam slipaj")
    print()

    # ── PHASE 1: Signal collection ────────────────────────────────────────────
    thresholds = _compute_thresholds(cfg)
    print(f"  Eşikler: KisaDiamond={thresholds['kisa_diamond']} KisaRuby={thresholds['kisa_ruby']} "
          f"OrtaDiamond={thresholds['orta_diamond']} OrtaFirsat={thresholds['orta_firsat']} "
          f"DuzFirsat={thresholds['duz_firsat']} MomDiamond={thresholds['mom_diamond']}")
    print("  [1/2] Sinyaller uretiliyor...")
    xu100_regime_map  = _build_xu100_regime_map(df_raw)
    xu100_ema50_map   = _build_xu100_ema50_map(df_raw)
    xu100_ema200_map  = _build_xu100_ema200_map(df_raw)
    xu100_vol_map     = _build_xu100_vol_map(df_raw)
    xutum_rs_map      = _build_xutum_rs_map(df_raw)
    try_regime_map    = _build_try_regime_map(df_raw)
    xbank_regime_map  = _build_xbank_regime_map(df_raw)
    xu100_roc_map     = _build_xu100_roc_map(df_raw)
    candidate_signals = _collect_signals(df_ind, all_dates, cfg, xu100_regime_map=xu100_regime_map,
                                         xu100_vol_map=xu100_vol_map,
                                         thresholds=thresholds, apply_quotas=True,
                                         xutum_rs_map=xutum_rs_map, try_regime_map=try_regime_map,
                                         xbank_regime_map=xbank_regime_map,
                                         xu100_roc_map=xu100_roc_map,
                                         bar_counts=bar_counts_full,
                                         xu100_ema200_map=xu100_ema200_map)
    print(f"  Toplam aday sinyal: {len(candidate_signals)}")

    # 3.3: Correlation cap — remove correlated duplicates per date
    ps_cfg = cfg.get('position_sizing', {})
    if ps_cfg.get('corr_cap_enabled', False):
        df_pivot = df_ind.pivot_table(index='Tarih', columns='Hisse', values='Kapanis', aggfunc='last')
        df_returns = df_pivot.pct_change()
        by_date = {}
        for tarih, sig in candidate_signals:
            by_date.setdefault(tarih, []).append(sig)
        pre_cap = len(candidate_signals)
        candidate_signals = []
        for tarih in sorted(by_date):
            for sig in _apply_corr_cap(by_date[tarih], df_returns, tarih, cfg):
                candidate_signals.append((tarih, sig))
        print(f"  Korelasyon kapi: {pre_cap} → {len(candidate_signals)} sinyal "
              f"(thr={ps_cfg.get('corr_cap_threshold', 0.70):.2f}, max={ps_cfg.get('corr_cap_max', 1)})")
    print()

    # ── PHASE 2: Variant simulation ──────────────────────────────────────────
    print(f"  [2/2] {len(VARIANTS)} variant simulasyonu yapiliyor...")
    all_variant_results = {}
    m_cfg      = cfg.get('market', {})
    gap_filter = m_cfg.get('gap_up_filter', True)
    gap_pct    = m_cfg.get('gap_up_pct', 1.02)

    for v_name, target_atr_map, use_trailing, min_rr_map, do_partial, p_atr, p_vades, quota_override, ruby_ema50_gate, ruby_rolling_pf_gate in VARIANTS:
        print(f"        {v_name}...")
        open_pos = {'Kisa': {}, 'Orta': {}, 'Duzeltme': {}, 'Momentum': {}}
        results  = []

        # Variant-level signal filtering
        v_signals = candidate_signals
        if quota_override is not None:
            by_date = {}
            for t, s in candidate_signals:
                by_date.setdefault(t, []).append(s)
            v_signals = []
            for t in sorted(by_date):
                for s in _apply_quotas_and_dedup(by_date[t], quota_override):
                    v_signals.append((t, s))
        if ruby_ema50_gate:
            v_signals = [
                (t, s) for t, s in v_signals
                if s['Vade'] != 'Kisa' or s['Tier'] != 'Ruby'
                or xu100_ema50_map.get(t, True)
            ]

        # Rolling PF gate state (per-variant, reset each variant run)
        # Bleed-through fix: every 30 calendar days, allow 1 "probe" trade to update the deque.
        ruby_recent_kz = collections.deque(maxlen=15) if ruby_rolling_pf_gate else None
        ruby_gate_last_probe = None  # date of last probe trade

        for tarih, signal in v_signals:
            vade  = signal['Vade']
            hisse = signal['Hisse']
            tier  = signal.get('Tier', '')

            # Rolling PF gate: skip Ruby when recent PF < 0.8 (need ≥10 samples)
            if ruby_rolling_pf_gate and vade == 'Kisa' and tier == 'Ruby':
                if len(ruby_recent_kz) >= 10:
                    wins   = sum(r for r in ruby_recent_kz if r > 0)
                    losses = sum(abs(r) for r in ruby_recent_kz if r < 0)
                    rolling_pf = wins / losses if losses > 0 else float('inf')
                    if rolling_pf < 0.8:
                        # Bleed-through: allow 1 probe trade every 30 days to update deque
                        probe_ok = (
                            ruby_gate_last_probe is None
                            or (datetime.strptime(tarih, '%Y-%m-%d') -
                                datetime.strptime(ruby_gate_last_probe, '%Y-%m-%d')).days >= 30
                        )
                        if not probe_ok:
                            continue
                        ruby_gate_last_probe = tarih

            mevcut_exit = open_pos[vade].get(hisse, '')
            if mevcut_exit and tarih <= mevcut_exit:
                continue

            raw_df = raw_by_hisse.get(hisse)
            if raw_df is None:
                continue

            # Resolve target ATR: adaptive_orta = adaptive only for Orta (live config),
            # adaptive = all vades (full experiment), dict/None = explicit override
            if target_atr_map == 'adaptive_orta':
                t_atr = _dynamic_target_atr(signal.get('HV_20_Pct', 50), 'Orta') if vade == 'Orta' else None
            elif target_atr_map == 'adaptive':
                t_atr = _dynamic_target_atr(signal.get('HV_20_Pct', 50), vade)
            elif isinstance(target_atr_map, dict):
                t_atr = target_atr_map.get(vade, None)
            else:
                t_atr = None

            m_rr   = (min_rr_map or {}).get(vade, None) if min_rr_map else None
            result = _simulate_trade(signal, tarih, raw_df, all_dates,
                                     target_atr=t_atr,
                                     use_trailing_stop=use_trailing,
                                     min_rr=m_rr,
                                     gap_filter=gap_filter,
                                     gap_up_pct=gap_pct,
                                     partial_exit=do_partial,
                                     partial_exit_atr=p_atr,
                                     partial_exit_vades=p_vades)
            if result is None:
                continue

            # Update rolling PF state
            if ruby_rolling_pf_gate and vade == 'Kisa' and tier == 'Ruby':
                ruby_recent_kz.append(result['KZ_Pct'])

            open_pos[vade][hisse] = result['Cikis_Tarihi']
            results.append(result)

        all_variant_results[v_name] = pd.DataFrame(results) if results else pd.DataFrame()

    # ── PHASE 3: Live Mode (J3 + config-driven Orta vol-adaptive) ────────────
    _vol_adap = cfg.get('orta', {}).get('vol_adaptive_target', False)
    _j3_label = 'Live Mode (J3 + Orta Vol-Adaptive)' if _vol_adap else 'J3 Adaptive Quotas'
    print(f"        {_j3_label}...")
    df_j3 = _backtest_j3_adaptive(
        df_ind, df_raw, all_dates, cfg, thresholds, xu100_regime_map, xu100_vol_map,
        xutum_rs_map=xutum_rs_map, try_regime_map=try_regime_map, xbank_regime_map=xbank_regime_map,
        xu100_roc_map=xu100_roc_map, xu100_ema200_map=xu100_ema200_map,
    )
    all_variant_results[_j3_label] = df_j3

    # ── OUTPUT ────────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("BACKTEST SONUC RAPORU")
    print("=" * 70)

    for v_name, df_res in all_variant_results.items():
        if df_res.empty:
            print(f"\n  {v_name}: Hic islem yapilmadi.")
            continue
        _print_variant_block(v_name, df_res)

    _karsilastirma_tablosu(all_variant_results)

    global _gap40_count
    gap40_snap = _gap40_count
    if gap40_snap > 0:
        print(f"\n  [Secim Etkisi] Corporate action gap-drop (>%40 gece acilis dususu) nedeniyle "
              f"{gap40_snap} simule pozisyon hariç tutuldu. Bu kismi survivorship bias kaynagi.")
    _gap40_count = 0

    # Save best variant (baseline) to markdown + CSV
    baseline_df = all_variant_results.get('Baseline', pd.DataFrame())
    if not baseline_df.empty:
        run_time     = datetime.now().strftime('%Y-%m-%d %H:%M')
        tarih_aralik = f"{all_dates[0]} -> {all_dates[-1]}"
        md = _kaydet_markdown(all_variant_results, run_time, tarih_aralik, all_dates=all_dates, gap40_excluded=gap40_snap)
        os.makedirs('tasks', exist_ok=True)
        with open(f'tasks/backtest_results{out_suffix}.md', 'w', encoding='utf-8') as f:
            f.write(md)
        baseline_df.to_csv(f'tasks/backtest_trades{out_suffix}.csv', index=False, encoding='utf-8')
        print(f"\n  Sonuclar tasks/backtest_results{out_suffix}.md + tasks/backtest_trades{out_suffix}.csv dosyalarina kaydedildi.")
        _analiz_kazanan_kaybeden(baseline_df)
        _print_windowed_stats(baseline_df, all_dates)
        fixed_df = all_variant_results.get('Fixed ATR (reference)', pd.DataFrame())
        if not fixed_df.empty:
            _print_windowed_stats(fixed_df, all_dates, label='Fixed ATR (reference)')

    # 3.1: Equity curve simulation — fixed-frac vs flat-lot
    ec = _equity_curve_stats(baseline_df, cfg)
    if ec:
        ps = cfg.get('position_sizing', {})
        max_conc = int(ps.get('max_concurrent_positions', 0))
        max_heat = float(ps.get('max_portfolio_heat_pct', 0.0))
        print(f"\n  {'─'*60}")
        print("  EQUITY CURVE SİMÜLASYONU (Baseline, sequential approx.)")
        print(f"  {'─'*60}")
        print(f"  Fixed-Frac : CAGR %{ec['ff_cagr']*100:+.1f}  MaxDD %{ec['ff_max_dd']*100:.1f}  Calmar {ec['ff_calmar']:.2f}  Final {ec['ff_final']:,.0f} TL  ({ec.get('base_n',0)} işlem)")
        print(f"  Flat-Lot   : CAGR %{ec['flat_cagr']*100:+.1f}  MaxDD %{ec['flat_max_dd']*100:.1f}  Calmar {ec['flat_calmar']:.2f}")
        if ec['ff_calmar'] > ec['flat_calmar']:
            print("  ✅ Fixed-Frac Calmar > Flat-Lot — sizing ETKİLİ (KEEP)")
        else:
            print("  ❌ Fixed-Frac Calmar ≤ Flat-Lot — sizing ETKİSİZ → REVERT 3.1 ⚠")
        # 3.2: concurrent-cap comparison
        if 'conc_calmar' in ec:
            cap_label = f"max_conc={max_conc}" if max_conc > 0 else ""
            heat_label = f"max_heat={max_heat:.0%}" if max_heat > 0 else ""
            caps = " + ".join(filter(None, [cap_label, heat_label]))
            print(f"\n  3.2 Concurrent Cap ({caps}):")
            print(f"  Conc-Cap FF: CAGR %{ec['conc_cagr']*100:+.1f}  MaxDD %{ec['conc_max_dd']*100:.1f}  Calmar {ec['conc_calmar']:.2f}  Final {ec['conc_final']:,.0f} TL  ({ec['conc_n']} işlem)")
            delta_calmar = ec['conc_calmar'] - ec['ff_calmar']
            delta_cagr   = (ec['conc_cagr'] - ec['ff_cagr']) * 100
            delta_dd     = (ec['conc_max_dd'] - ec['ff_max_dd']) * 100
            print(f"  Delta vs Base: CAGR {delta_cagr:+.1f}pp  MaxDD {delta_dd:+.1f}pp  Calmar {delta_calmar:+.2f}")
            if ec['conc_calmar'] > ec['ff_calmar']:
                print("  ✅ Concurrent Cap Calmar > Base — KEEP 3.2")
            else:
                print("  ❌ Concurrent Cap Calmar ≤ Base — REVERT 3.2 ⚠")
        elif max_conc > 0 or max_heat > 0.0:
            print("  ⚠ 3.2: concurrent cap active but no trades survived filter")


def _kaydet_markdown(all_variant_results, run_time, tarih_aralik, all_dates=None, gap40_excluded=0):
    variant_names = ' | '.join(all_variant_results.keys())
    lines = [
        f"# Backtest Sonuclari — {len(all_variant_results)} Variant Karsilastirmasi",
        "",
        f"**Calisma zamani:** {run_time}",
        f"**Test araligi:** {tarih_aralik}",
        f"**Variants:** {variant_names}",
        "",
        "> Survivorship bias: aktif hisse evreni, tarihsel olarak devreden cikmis hisseler haric.",
        "> BIST kucuk/orta olcekli hisselerin ~%20-30'u herhangi bir 5 yillik donemde islem disi kaliyor.",
        "> Arastirmalar EM kucuk-cap backtestlerde WR'nin gercekte 5-15pp daha dusuk oldugunu gosteriyor.",
        f"> Corporate action gap-drop (>%40 gece dususu): {gap40_excluded} pozisyon hariç tutuldu.",
        "",
        "---",
        "",
    ]

    for v_name, df in all_variant_results.items():
        lines.append(f"## {v_name}")
        if df.empty:
            lines += ["_Hic islem yok._", ""]
            continue
        for vade in ['Kisa', 'Orta', 'Duzeltme', 'Momentum']:
            if vade == 'Kisa':
                tiers = ['Diamond', 'Ruby']
            elif vade == 'Duzeltme':
                tiers = ['Firsat']
            else:
                tiers = ['Diamond', 'Firsat']
            for tier in tiers:
                sub = df[(df['Vade'] == vade) & (df['Tier'] == tier)]
                if sub.empty:
                    continue
                s    = _stats(sub)
                pf_s = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "inf"
                lines += [
                    f"### {vade} {tier}",
                    f"| Metrik | Deger |",
                    f"|--------|-------|",
                    f"| Toplam Islem | {s['total']} |",
                    f"| WR | %{s['wr']:.1f} |",
                    f"| Profit Factor | {pf_s} |",
                    f"| Ort. Kazanc | +%{s['avg_win']:.2f} |",
                    f"| Ort. Kayip | %{s['avg_loss']:.2f} |",
                    f"| Ort. Tutma | {s['avg_hold']:.1f} gun |",
                    f"| En Kotu | %{s['worst']:.2f} |",
                    f"| Ort. Hedefe Yakinlik (kaybedenler) | %{s['avg_tgt']:.1f} |",
                    "",
                ]
        lines.append("---")
        lines.append("")

    # Windowed breakdown (baseline only)
    if all_dates:
        baseline_df = all_variant_results.get('Baseline', pd.DataFrame())
        windows = _get_window_ranges(all_dates)
        if not baseline_df.empty and len(windows) >= 2:
            lines += ["---", "", "## Pencere Analizi — Baseline (8 Aylık Dönemler)", ""]
            for vade_tier, label in [
                (('Kisa', 'Diamond'), 'Kisa Diamond'),
                (('Kisa', 'Ruby'),    'Kisa Ruby'),
                (('Orta', 'Firsat'),  'Orta Firsat'),
            ]:
                sub_all = baseline_df[
                    (baseline_df['Vade'] == vade_tier[0]) &
                    (baseline_df['Tier'] == vade_tier[1])
                ]
                if sub_all.empty:
                    continue
                lines += [f"### {label}", "| Dönem | İşlem | WR% | PF |", "|-------|-------|-----|-----|"]
                for w_start, w_end in windows:
                    sub = sub_all[
                        (sub_all['Sinyal_Tarihi'] >= w_start) &
                        (sub_all['Sinyal_Tarihi'] < w_end)
                    ]
                    if sub.empty:
                        lines.append(f"| {w_start[:7]}→{w_end[:7]} | — | — | — |")
                        continue
                    s = _stats(sub)
                    pf_s = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "∞"
                    lines.append(f"| {w_start[:7]}→{w_end[:7]} | {s['total']} | %{s['wr']:.1f} | {pf_s} |")
                lines.append("")

    return '\n'.join(lines)


# ── GRID SEARCH ───────────────────────────────────────────────────────────────

def backtest_grid_arama(vade='Kisa', cfg=None, months=None):
    """Systematic parameter sweep for one strategy.

    Collects ALL signals once (floor thresholds, no quotas), then for each
    parameter combo: re-tiers signals, applies daily quotas, simulates.

    Usage: py backtest_engine.py --grid=Kisa
    """
    import itertools
    from collections import defaultdict

    if cfg is None:
        cfg = _load_cfg()

    lb_months = months if months is not None else LOOKBACK_MONTHS
    conn   = sqlite3.connect('bist_ajan.db')
    cutoff = (datetime.now() - timedelta(days=lb_months * 30)).strftime('%Y-%m-%d')
    df_ind = pd.read_sql(
        f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih >= '{cutoff}' ORDER BY Tarih ASC", conn)
    df_raw = pd.read_sql(
        "SELECT Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis "
        f"FROM Hisse_Verileri WHERE Tarih >= '{cutoff}' ORDER BY Tarih ASC", conn)
    conn.close()

    if df_ind.empty:
        print("Veri yok.")
        return None

    all_dates    = sorted(df_ind['Tarih'].unique().tolist())
    raw_by_hisse = {h: g.reset_index(drop=True) for h, g in df_raw.groupby('Hisse')}
    xu100_regime_map = _build_xu100_regime_map(df_raw)
    xu100_ema200_map = _build_xu100_ema200_map(df_raw)
    xu100_vol_map    = _build_xu100_vol_map(df_raw)
    xutum_rs_map     = _build_xutum_rs_map(df_raw)
    try_regime_map   = _build_try_regime_map(df_raw)
    xbank_regime_map = _build_xbank_regime_map(df_raw)
    xu100_roc_map    = _build_xu100_roc_map(df_raw)

    # Floor thresholds — capture all signals that pass hard gates
    FLOOR_THR = {
        'kisa_ruby': 30, 'kisa_diamond': 30,
        'orta_firsat': 20, 'orta_diamond': 20,
        'duz_firsat': 15, 'mom_firsat': 20, 'mom_diamond': 20,
    }

    print(f"\nGrid arama: {vade} | {lb_months}ay | sinyal toplanıyor...")
    all_raw_signals = _collect_signals(
        df_ind, all_dates, cfg, xu100_regime_map=xu100_regime_map, xu100_vol_map=xu100_vol_map,
        thresholds=FLOOR_THR, apply_quotas=False,
        xutum_rs_map=xutum_rs_map, try_regime_map=try_regime_map, xbank_regime_map=xbank_regime_map,
        xu100_roc_map=xu100_roc_map, xu100_ema200_map=xu100_ema200_map,
    )
    # Keep only target strategy, store with piyasa context embedded
    raw_for_vade = [(t, s) for t, s in all_raw_signals if s['Vade'] == vade]
    print(f"  Ham sinyal: {len(raw_for_vade)} ({vade})")

    # ── Parameter grids per strategy ─────────────────────────────────────────
    sc_all = (cfg or {}).get('scoring', {})
    thr    = (cfg or {}).get('thresholds', {})

    if vade == 'Kisa':
        kisa_sc  = sc_all.get('kisa_vade', {})
        kisa_max = _max_puan(kisa_sc, include_base=kisa_sc.get('_base', 50))
        grid = list(itertools.product(
            [1.5, 2.0, 2.5, 3.0],           # target_atr
            [1.0, 1.5, 2.0],                 # stop_atr
            [1.0, 1.2, 1.5, 1.8],            # min_rr
            [0.75, 0.80, 0.85, 0.90],        # diamond_pct
        ))
        def make_thr(combo):
            t_atr, s_atr, m_rr, d_pct = combo
            d_pts = int(kisa_max * d_pct)
            r_pts = int(kisa_max * thr.get('kisa_ruby_pct', 0.70))
            return {**_DEFAULT_THRESHOLDS, 'kisa_diamond': d_pts, 'kisa_ruby': r_pts}, t_atr, s_atr, m_rr
        def get_tier(puan, thr_d):
            kd = thr_d['kisa_diamond']; kr = thr_d['kisa_ruby']
            if puan >= kd: return 'Diamond'
            if puan >= kr: return 'Ruby'
            return None

    elif vade == 'Orta':
        orta_sc  = sc_all.get('orta_vade', {})
        orta_max = _max_puan(orta_sc)
        grid = list(itertools.product(
            [3.0, 4.0, 5.0, 6.0],            # target_atr
            [1.5, 2.0, 2.5],                  # stop_atr
            [1.5, 1.8, 2.0],                  # min_rr
            [0.35, 0.41, 0.50, 0.55],         # firsat_pct threshold
        ))
        def make_thr(combo):
            t_atr, s_atr, m_rr, f_pct = combo
            d_pts = int(orta_max * thr.get('orta_diamond_pct', 0.80))
            f_pts = int(orta_max * f_pct)
            return {**_DEFAULT_THRESHOLDS, 'orta_diamond': d_pts, 'orta_firsat': f_pts}, t_atr, s_atr, m_rr
        def get_tier(puan, thr_d):
            if puan >= thr_d['orta_diamond']: return 'Diamond'
            if puan >= thr_d['orta_firsat']:  return 'Firsat'
            return None

    elif vade == 'Duzeltme':
        duz_sc  = sc_all.get('duzeltme', {})
        duz_max = _max_puan(duz_sc)
        grid = list(itertools.product(
            [2.0, 2.5, 3.0],                  # target_atr
            [1.0, 1.5, 2.0],                  # stop_atr
            [1.0, 1.2, 1.5, 1.8],             # min_rr
            [0.22, 0.28, 0.33, 0.38],         # firsat_pct
        ))
        def make_thr(combo):
            t_atr, s_atr, m_rr, f_pct = combo
            f_pts = int(duz_max * f_pct)
            return {**_DEFAULT_THRESHOLDS, 'duz_firsat': f_pts}, t_atr, s_atr, m_rr
        def get_tier(puan, thr_d):
            if puan >= thr_d['duz_firsat']: return 'Firsat'
            return None

    else:  # Momentum
        mom_sc  = sc_all.get('momentum_patlama', {})
        mom_max = _max_puan(mom_sc)
        grid = list(itertools.product(
            [2.0, 2.5, 3.0],                  # target_atr
            [1.0, 1.5, 2.0],                  # stop_atr
            [1.5, 1.8, 2.0],                  # min_rr
            [0.65, 0.70, 0.75, 0.80, 0.85],  # diamond_pct
        ))
        def make_thr(combo):
            t_atr, s_atr, m_rr, d_pct = combo
            d_pts = int(mom_max * d_pct)
            f_pts = int(mom_max * thr.get('momentum_firsat_pct', 0.50))
            return {**_DEFAULT_THRESHOLDS, 'mom_diamond': d_pts, 'mom_firsat': f_pts}, t_atr, s_atr, m_rr
        def get_tier(puan, thr_d):
            if puan >= thr_d['mom_diamond']: return 'Diamond'
            if puan >= thr_d['mom_firsat']:  return 'Firsat'
            return None

    print(f"  {len(grid)} kombinasyon test ediliyor...\n")
    m_cfg      = (cfg or {}).get('market', {})
    gap_filter = m_cfg.get('gap_up_filter', True)
    gap_pct    = m_cfg.get('gap_up_pct', 1.02)

    results_rows = []

    for idx, combo in enumerate(grid):
        if idx % 40 == 0:
            print(f"  [{idx}/{len(grid)}] ...")

        thr_d, t_atr, s_atr, m_rr = make_thr(combo)

        # Re-tier and group by date
        by_date = defaultdict(list)
        for tarih, sig in raw_for_vade:
            tier = get_tier(sig['Puan'], thr_d)
            if tier is None:
                continue
            s2 = dict(sig)
            s2['Tier'] = tier
            by_date[tarih].append(s2)

        # Apply daily quotas
        quota_sigs = []
        for tarih in sorted(by_date):
            for s2 in _apply_quotas_and_dedup(by_date[tarih]):
                quota_sigs.append((tarih, s2))

        if not quota_sigs:
            continue

        # Simulate
        open_pos = {v: {} for v in ['Kisa', 'Orta', 'Duzeltme', 'Momentum']}
        sim_res  = []

        for tarih, sig in quota_sigs:
            h = sig['Hisse']
            v = sig['Vade']
            if open_pos[v].get(h, '') and tarih <= open_pos[v][h]:
                continue
            raw_df = raw_by_hisse.get(h)
            if raw_df is None:
                continue
            result = _simulate_trade(sig, tarih, raw_df, all_dates,
                                     target_atr=t_atr, stop_atr=s_atr, min_rr=m_rr,
                                     gap_filter=gap_filter, gap_up_pct=gap_pct)
            if result is None:
                continue
            open_pos[v][h] = result['Cikis_Tarihi']
            sim_res.append(result)

        if not sim_res:
            continue

        df_r = pd.DataFrame(sim_res)
        for tier in ['Diamond', 'Ruby', 'Firsat']:
            sub = df_r[df_r['Tier'] == tier]
            if len(sub) < 5:
                continue
            s = _stats(sub)
            if s['pf'] == float('inf'):
                score = s['wr'] * 3.0
            else:
                score = s['wr'] * min(s['pf'], 3.0)
            results_rows.append({
                'target_atr': combo[0], 'stop_atr': combo[1],
                'min_rr': combo[2], 'param4': combo[3],
                'tier': tier, 'total': s['total'],
                'wr': round(s['wr'], 1), 'pf': round(s['pf'], 2),
                'avg_win': round(s['avg_win'], 2), 'avg_loss': round(s['avg_loss'], 2),
                'avg_hold': round(s['avg_hold'], 1),
                'avg_tgt': round(s['avg_tgt'], 1),
                'score': round(score, 2),
            })

    if not results_rows:
        print("  Sonuç yok.")
        return None

    df_grid = pd.DataFrame(results_rows).sort_values('score', ascending=False)

    print(f"\n{'═'*80}")
    print(f"  GRID SONUÇLARI — {vade} (Top 25, skor = WR × min(PF, 3))")
    print(f"{'═'*80}")
    hdr4 = 'diam%' if vade != 'Duzeltme' else 'firs%'
    print(f"  {'t_atr':>5} {'s_atr':>5} {'min_rr':>6} {hdr4:>6} {'Tier':<10} "
          f"{'N':>5} {'WR%':>6} {'PF':>5} {'AvgW':>7} {'AvgL':>7} {'Skor':>6}")
    print(f"  {'-'*76}")
    for _, row in df_grid.head(25).iterrows():
        print(f"  {row['target_atr']:>5} {row['stop_atr']:>5} {row['min_rr']:>6} "
              f"{row['param4']:>6.2f} {row['tier']:<10} {row['total']:>5} "
              f"{row['wr']:>5.1f}% {row['pf']:>5.2f} "
              f"{row['avg_win']:>+6.1f}% {row['avg_loss']:>+6.1f}% {row['score']:>6.2f}")

    os.makedirs('tasks', exist_ok=True)
    out_path = f"tasks/grid_{vade.lower()}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df_grid.to_csv(out_path, index=False, encoding='utf-8')
    print(f"\n  CSV: {out_path}")

    # Best combo summary
    best = df_grid.iloc[0]
    print(f"\n  EN İYİ: target={best['target_atr']} stop={best['stop_atr']} "
          f"min_rr={best['min_rr']} param4={best['param4']:.2f} "
          f"→ {best['tier']} WR:{best['wr']}% PF:{best['pf']} N:{best['total']}")

    return df_grid


def backtest_yellow_calistir(cfg=None, months=None):
    """SARI piyasa dönemlerinde bloke edilen stratejilerin performansını test eder.

    Piyasa filtresini kaldırır (force_all_markets=True) ve sonuçları
    SARI vs YEŞİL piyasa dönemine göre karşılaştırır.
    Soru: Bloke edilen Diamond/Orta/Momentum sinyalleri SARI piyasada ne kadar başarılı?
    """
    if cfg is None:
        cfg = _load_cfg()

    lb_months = months if months is not None else 18
    cutoff = (datetime.now() - timedelta(days=lb_months * 30)).strftime('%Y-%m-%d')

    print(f"Yellow Market Backtest: son {lb_months} ay — piyasa filtresiz SARI vs YEŞİL karşılaştırması...")

    conn = sqlite3.connect('bist_ajan.db')
    df_ind = pd.read_sql(
        f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih >= '{cutoff}' ORDER BY Tarih ASC", conn)
    df_raw = pd.read_sql(
        "SELECT Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis "
        f"FROM Hisse_Verileri WHERE Tarih >= '{cutoff}' ORDER BY Tarih ASC", conn)
    conn.close()

    if df_ind.empty:
        print("Veri yok.")
        return

    import backtest_engine as _self
    bst = cfg.get('backtest', {})
    _self.COMMISSION_RT = float(bst.get('commission_rt', 0.004))
    _self.SLIPPAGE_EACH = float(bst.get('slippage_each', 0.005))
    _self.HARD_MAX_LOSS = float(bst.get('hard_max_loss_pct', 0.22))
    _self.PARAMS['Kisa']['target_atr']     = float(bst.get('target_atr_kisa', 2.0))
    _self.PARAMS['Kisa']['stop_atr']       = float(bst.get('stop_atr_kisa', 1.5))
    _self.PARAMS['Orta']['stop_atr']       = float(bst.get('stop_atr_orta', 2.0))
    _self.PARAMS['Duzeltme']['stop_atr']   = float(bst.get('stop_atr_duzeltme', 1.5))
    _self.PARAMS['Duzeltme']['target_atr'] = float(bst.get('target_atr_duzeltme', 3.0))

    all_dates    = sorted(df_ind['Tarih'].unique().tolist())
    raw_by_hisse = {h: g.reset_index(drop=True) for h, g in df_raw.groupby('Hisse')}
    xu100_regime_map = _build_xu100_regime_map(df_raw)
    xu100_ema200_map = _build_xu100_ema200_map(df_raw)
    xu100_vol_map    = _build_xu100_vol_map(df_raw)
    xutum_rs_map     = _build_xutum_rs_map(df_raw)
    try_regime_map   = _build_try_regime_map(df_raw)
    xbank_regime_map = _build_xbank_regime_map(df_raw)
    xu100_roc_map    = _build_xu100_roc_map(df_raw)
    thresholds = _compute_thresholds(cfg)

    m_cfg     = cfg.get('market', {})
    yesil_thr = m_cfg.get('yesil_threshold', 55)
    date_market = {}
    for tarih in all_dates:
        df_date = df_ind[df_ind['Tarih'] == tarih]
        p, _ = _get_piyasa(df_date, yesil_thr)
        date_market[tarih] = p

    sari_days  = sum(1 for m in date_market.values() if m == 'SARI')
    yesil_days = sum(1 for m in date_market.values() if m == 'YESIL')
    print(f"  Tarih: {all_dates[0]} → {all_dates[-1]} ({len(all_dates)} gün)")
    print(f"  SARI: {sari_days} gün | YEŞİL: {yesil_days} gün")
    print("  Sinyaller toplanıyor (piyasa filtresi kaldırıldı)...")

    candidate_signals = _collect_signals(
        df_ind, all_dates, cfg, xu100_regime_map=xu100_regime_map, xu100_vol_map=xu100_vol_map,
        thresholds=thresholds, apply_quotas=True, force_all_markets=True,
        xutum_rs_map=xutum_rs_map, try_regime_map=try_regime_map, xbank_regime_map=xbank_regime_map,
        xu100_roc_map=xu100_roc_map, xu100_ema200_map=xu100_ema200_map,
    )
    print(f"  Toplam sinyal: {len(candidate_signals)}")

    gap_filter = m_cfg.get('gap_up_filter', True)
    gap_pct    = m_cfg.get('gap_up_pct', 1.02)

    # Run three variants: Baseline, Partial Exit (all), Momentum-Only Partial Exit
    variant_configs = [
        ('Baseline',                   False, 0.0, None),
        ('Partial Exit',               True,  1.5, None),
        ('Momentum-Only Partial Exit', True,  1.5, ['Momentum']),
    ]
    all_results = {}
    for v_name, do_partial, p_atr, p_vades in variant_configs:
        open_pos = {v: {} for v in ['Kisa', 'Orta', 'Duzeltme', 'Momentum']}
        results  = []
        for tarih, signal in candidate_signals:
            vade  = signal['Vade']
            hisse = signal['Hisse']
            if open_pos[vade].get(hisse, '') and tarih <= open_pos[vade][hisse]:
                continue
            raw_df = raw_by_hisse.get(hisse)
            if raw_df is None:
                continue
            result = _simulate_trade(signal, tarih, raw_df, all_dates,
                                     gap_filter=gap_filter, gap_up_pct=gap_pct,
                                     partial_exit=do_partial, partial_exit_atr=p_atr,
                                     partial_exit_vades=p_vades)
            if result is None:
                continue
            result['Market'] = signal.get('_market', date_market.get(tarih, 'YESIL'))
            open_pos[vade][hisse] = result['Cikis_Tarihi']
            results.append(result)
        all_results[v_name] = pd.DataFrame(results) if results else pd.DataFrame()

    df_all = all_results.get('Baseline', pd.DataFrame())
    if df_all.empty:
        print("  Sonuç yok.")
        return

    print()
    print("=" * 70)
    print("YELLOW MARKET BACKTEST — SARI vs YEŞİL (Baseline + Partial Exit)")
    print("=" * 70)
    print("Soru: Bloke edilen stratejiler SARI piyasada ne kadar başarılı?")
    print()

    _hdr = (f"  {'Variant+Piyasa':<22} {'İşlem':>6} {'WR%':>6} {'PF':>5} "
            f"{'OrtKaz':>8} {'OrtKay':>8} {'OrtSüre':>7}")
    _sep = f"  {'-'*66}"

    checks = [
        (('Kisa',     'Diamond'),  'Kisa Diamond (SARI dönemde normalde BLOKE)'),
        (('Orta',     'Diamond'),  'Orta Diamond (SARI dönemde normalde BLOKE)'),
        (('Orta',     'Firsat'),   'Orta Firsat  (SARI dönemde normalde BLOKE)'),
        (('Momentum', 'Diamond'),  'Momentum Diamond (SARI dönemde normalde BLOKE)'),
        (('Kisa',     'Ruby'),     'Kisa Ruby (SARI dönemde AKTİF — kontrol)'),
        (('Duzeltme', 'Firsat'),   'Duzeltme  (SARI dönemde AKTİF — kontrol)'),
    ]

    verdicts = []
    for (vade, tier), label in checks:
        print(f"\n  [{label}]")
        print(_hdr); print(_sep)
        baseline_sari_wr = None
        baseline_yesil_wr = None
        for v_name, df_v in all_results.items():
            if df_v.empty:
                continue
            sub = df_v[(df_v['Vade'] == vade) & (df_v['Tier'] == tier)]
            if sub.empty:
                continue
            for market_label in ['SARI', 'YESIL', 'Toplam']:
                if market_label == 'Toplam':
                    m_sub = sub
                else:
                    m_sub = sub[sub['Market'] == market_label]
                if m_sub.empty:
                    continue
                s = _stats(m_sub)
                pf_s = f"{s['pf']:.2f}" if s['pf'] != float('inf') else "∞"
                tag = f"{v_name[:7]} {market_label}"
                print(f"  {tag:<22} {s['total']:>6} {s['wr']:>5.1f}% {pf_s:>5} "
                      f"{s['avg_win']:>+7.2f}% {s['avg_loss']:>+7.2f}% {s['avg_hold']:>7.1f}g")
                if v_name == 'Baseline':
                    if market_label == 'SARI':
                        baseline_sari_wr = s['wr'] if s['total'] >= 5 else None
                        baseline_sari_n  = s['total']
                    elif market_label == 'YESIL':
                        baseline_yesil_wr = s['wr'] if s['total'] >= 5 else None
            print(_sep)
        if baseline_sari_wr is not None and baseline_yesil_wr is not None:
            diff = baseline_sari_wr - baseline_yesil_wr
            if diff < -5:
                verdict = "✓ FİLTRE HAKLI — SARI piyasada belirgin kötü"
            elif diff > 5:
                verdict = "✗ FİLTRE GEREKSIZ? — SARI piyasada daha iyi"
            else:
                verdict = "⚠️ BENZER — fark küçük, filtre tartışılabilir"
            verdicts.append(f"  {vade} {tier}: {verdict} ({diff:+.1f}pp)")

    if verdicts:
        print(f"\n{'='*70}")
        print("ÖZET YORUM:")
        for v in verdicts:
            print(v)
        print()


# ── WALK-FORWARD OOS VALIDATION (T13) ────────────────────────────────────────

def _print_walkforward_comparison(results, IS_START, IS_END, OOS_END):
    """Print IS vs OOS comparison per (vade, tier) with overfit flags."""
    is_df  = results.get('IS',  pd.DataFrame())
    oos_df = results.get('OOS', pd.DataFrame())

    BUCKETS = [
        ('Kisa',     'Diamond'),
        ('Kisa',     'Ruby'),
        ('Orta',     'Diamond'),
        ('Orta',     'Firsat'),
        ('Momentum', 'Diamond'),
    ]

    print(f"\n{'═'*82}")
    print("  WALK-FORWARD KARSILASTIRMA — In-Sample vs Out-of-Sample")
    print(f"  IS : {IS_START} → {IS_END}  |  OOS: {IS_END} → {OOS_END}")
    print(f"  Kural: OOS WR < IS WR − 5pp → overfit uyarısı")
    print(f"{'═'*82}")
    hdr = (f"  {'Strateji':<20} {'IS_N':>5} {'IS_WR':>6} {'IS_PF':>5} | "
           f"{'OOS_N':>5} {'OOS_WR':>6} {'OOS_PF':>6} | {'ΔWR':>5}  Yorum")
    sep = f"  {'-'*80}"
    print(hdr); print(sep)

    overfit_count = 0
    lines_md = [hdr, sep]

    for vade, tier in BUCKETS:
        is_sub  = is_df[(is_df['Vade']  == vade) & (is_df['Tier']  == tier)] if not is_df.empty  else pd.DataFrame()
        oos_sub = oos_df[(oos_df['Vade'] == vade) & (oos_df['Tier'] == tier)] if not oos_df.empty else pd.DataFrame()

        is_s  = _stats(is_sub)  if not is_sub.empty  else None
        oos_s = _stats(oos_sub) if not oos_sub.empty else None

        name = f"{vade} {tier}"

        if is_s is None or oos_s is None or is_s['total'] < 10 or oos_s['total'] < 10:
            is_str  = f"{is_s['total']:>5} {is_s['wr']:>5.1f}% {is_s['pf']:>5.2f}" if is_s and is_s['total'] > 0 else "—"
            oos_str = f"{oos_s['total']:>5} {oos_s['wr']:>5.1f}% {oos_s['pf']:>5.2f}" if oos_s and oos_s['total'] > 0 else "—"
            row = f"  {name:<20}  {is_str}  |  {oos_str}  | yetersiz veri (<10)"
            print(row); lines_md.append(row)
            continue

        delta = oos_s['wr'] - is_s['wr']
        is_pf_s  = f"{is_s['pf']:.2f}"  if is_s['pf']  != float('inf') else "∞"
        oos_pf_s = f"{oos_s['pf']:.2f}" if oos_s['pf'] != float('inf') else "∞"

        if delta < -10:
            flag = "🔴 OVERFIT YÜKSEK (>10pp düşüş)"
            overfit_count += 1
        elif delta < -5:
            flag = "⚠️  ŞÜPHELI (>5pp düşüş)"
            overfit_count += 1
        elif delta < 0:
            flag = "✓  normal degradasyon"
        else:
            flag = "✅ OOS ≥ IS"

        row = (f"  {name:<20} {is_s['total']:>5} {is_s['wr']:>5.1f}% {is_pf_s:>5} | "
               f"{oos_s['total']:>5} {oos_s['wr']:>5.1f}% {oos_pf_s:>6} | {delta:>+5.1f}  {flag}")
        print(row); lines_md.append(row)

    print(sep)
    if overfit_count == 0:
        verdict = "VERDİCT: ✅ Tüm stratejiler OOS testini geçti (drop < 5pp)"
    else:
        verdict = f"VERDİCT: ⚠️  {overfit_count} strateji overfit uyarısı aldı"
    print(f"  {verdict}")
    print()
    return lines_md + [sep, f"  {verdict}"]


def _chunk_dates(all_dates, n_splits):
    n = len(all_dates)
    sz = n // n_splits
    return [all_dates[i * sz: (i + 1) * sz if i < n_splits - 1 else n] for i in range(n_splits)]


def _deflated_sharpe_ratio(returns_list, n_trials=200):
    """Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio (Phase 0.4).

    Corrects SR for non-normality (skew/kurtosis) and multiple-testing bias.

    Args:
        returns_list: per-trade P&L fractions (0.05 = 5%)
        n_trials: total strategy configs tested across all phases (M)

    Returns:
        (psr, dsr) — probabilities [0, 1], or (None, None) if n < 10.
        psr  : P(true SR > 0)            — positive expectancy?
        dsr  : P(true SR > SR_benchmark) — beats expected-max from M random trials?
               dsr < 0.5 → indistinguishable from noise at this trial count.
    """
    from scipy import stats as sp_stats
    import math

    n = len(returns_list)
    if n < 10:
        return None, None

    r = np.array(returns_list, dtype=float)
    mu = r.mean()
    sigma = r.std(ddof=1)
    if sigma < 1e-10:
        return None, None

    sr_hat = mu / sigma
    skew = float(sp_stats.skew(r))
    kurt = float(sp_stats.kurtosis(r, fisher=False))  # Pearson kurtosis (normal = 3)

    # Variance of SR_hat corrected for skew/kurtosis (López de Prado 2014 eq. 4)
    var_sr = (1 - skew * sr_hat + (kurt - 1) / 4 * sr_hat ** 2) / (n - 1)
    if var_sr <= 0:
        return None, None
    std_sr = math.sqrt(var_sr)

    # PSR = P(true SR > 0)
    psr = float(sp_stats.norm.cdf(sr_hat / std_sr))

    # Expected max SR from M independent trials (López de Prado 2014 eq. 5).
    # Under H0 (true SR=0), SR_hat ~ N(0, 1/n). The z-score benchmark is:
    #   z* = (1-γ)·Φ⁻¹(1-1/M) + γ·Φ⁻¹(1-1/(M·e))
    # Convert to per-trade SR units (same scale as sr_hat) by dividing by √(n-1).
    euler_gamma = 0.5772156649015329
    z_star = (
        (1 - euler_gamma) * sp_stats.norm.ppf(1 - 1 / n_trials) +
        euler_gamma * sp_stats.norm.ppf(1 - 1 / (n_trials * math.e))
    )
    sr_benchmark = z_star / math.sqrt(n - 1)

    # DSR = P(true SR > SR_benchmark)
    dsr = float(sp_stats.norm.cdf((sr_hat - sr_benchmark) / std_sr))

    return psr, dsr


def _cpcv_simulate_window(oos_dates, all_dates, df_ind, raw_by_hisse,
                           cfg, thresholds,
                           xu100_regime_map, xu100_vol_map,
                           xutum_rs_map, try_regime_map, xbank_regime_map,
                           xu100_roc_map, gap_filter, gap_pct,
                           xu100_ema200_map=None):
    """Run signal collection + trade simulation for a single CPCV OOS window."""
    oos_set = set(oos_dates)
    df_oos = df_ind[df_ind['Tarih'].isin(oos_set)]

    candidate_signals = _collect_signals(
        df_oos, oos_dates, cfg,
        xu100_regime_map=xu100_regime_map,
        xu100_vol_map=xu100_vol_map,
        thresholds=thresholds,
        apply_quotas=True,
        xutum_rs_map=xutum_rs_map,
        try_regime_map=try_regime_map,
        xbank_regime_map=xbank_regime_map,
        xu100_roc_map=xu100_roc_map,
        xu100_ema200_map=xu100_ema200_map,
    )

    open_pos = {'Kisa': {}, 'Orta': {}, 'Duzeltme': {}, 'Momentum': {}}
    results = []
    for tarih, signal in candidate_signals:
        vade = signal['Vade']
        hisse = signal['Hisse']
        if open_pos[vade].get(hisse, '') >= tarih:
            continue
        raw_df = raw_by_hisse.get(hisse)
        if raw_df is None:
            continue
        t_atr = _dynamic_target_atr(signal.get('HV_20_Pct', 50), 'Orta') if vade == 'Orta' else None
        result = _simulate_trade(
            signal, tarih, raw_df, all_dates,
            target_atr=t_atr,
            use_trailing_stop=False,
            gap_filter=gap_filter,
            gap_up_pct=gap_pct,
        )
        if result is None:
            continue
        open_pos[vade][hisse] = result['Cikis_Tarihi']
        results.append(result)

    return pd.DataFrame(results) if results else pd.DataFrame()


def backtest_cpcv(cfg=None, n_splits=6, k=2, lookback_months=36, embargo_days=5, compute_pbo=False, n_trials=200):
    """Combinatorial Purged Cross-Validation (Phase 0.2).

    Divides history into n_splits chunks, tests all C(n_splits, k) OOS
    combinations. Each combination = k non-contiguous chunks as OOS test set.
    Embargo: drop first embargo_days of each OOS chunk (near-boundary guard).
    Strategy params frozen — no training step needed.

    Output: per (Vade, Tier) OOS PF distribution. CLI: --cpcv
    """
    from itertools import combinations as _combinations
    from dateutil.relativedelta import relativedelta

    if cfg is None:
        cfg = _load_cfg()

    bst = cfg.get('backtest', {})
    import backtest_engine as _self
    _self.COMMISSION_RT = float(bst.get('commission_rt', 0.004))
    _self.SLIPPAGE_EACH = float(bst.get('slippage_each', 0.005))
    _self.HARD_MAX_LOSS = float(bst.get('hard_max_loss_pct', 0.22))
    _self.PARAMS['Kisa']['target_atr']     = float(bst.get('target_atr_kisa', 2.0))
    _self.PARAMS['Kisa']['stop_atr']       = float(bst.get('stop_atr_kisa', 1.5))
    _self.PARAMS['Orta']['stop_atr']       = float(bst.get('stop_atr_orta', 2.0))
    _self.PARAMS['Momentum']['stop_atr']   = float(bst.get('stop_atr_momentum', 1.5))
    _self.PARAMS['Momentum']['target_atr'] = float(bst.get('target_atr_momentum', 3.0))
    _self.PARAMS['Momentum']['min_rr']     = float(bst.get('min_rr_momentum', 1.8))

    n_combos = 1
    for i in range(k):
        n_combos = n_combos * (n_splits - i) // (i + 1)
    print(f"\n{'='*70}")
    print(f"  CPCV — Combinatorial Purged Cross-Validation (Phase 0.2 + DSR Phase 0.4)")
    print(f"  n_splits={n_splits}, k={k}, C({n_splits},{k})={n_combos} yol, "
          f"embargo={embargo_days}d, {lookback_months}m veri, M={n_trials} trials")
    print(f"{'='*70}\n")

    end_dt   = datetime.now().replace(day=1)
    start_dt = end_dt - relativedelta(months=lookback_months)
    start_str = start_dt.strftime('%Y-%m-%d')

    conn   = sqlite3.connect('bist_ajan.db')
    df_ind = pd.read_sql(
        f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih >= '{start_str}' ORDER BY Tarih ASC",
        conn,
    )
    df_raw = pd.read_sql(
        "SELECT Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis "
        f"FROM Hisse_Verileri WHERE Tarih >= '{start_str}' ORDER BY Tarih ASC",
        conn,
    )
    conn.close()

    if df_ind.empty:
        print("  Veri yok. Once veri_motoru.py ve indicator_engine.py calistirin.")
        return None

    all_dates    = sorted(df_ind['Tarih'].unique().tolist())
    raw_by_hisse = {h: g.reset_index(drop=True) for h, g in df_raw.groupby('Hisse')}

    xu100_regime_map = _build_xu100_regime_map(df_raw)
    xu100_ema200_map = _build_xu100_ema200_map(df_raw)
    xu100_vol_map    = _build_xu100_vol_map(df_raw)
    xutum_rs_map     = _build_xutum_rs_map(df_raw)
    try_regime_map   = _build_try_regime_map(df_raw)
    xbank_regime_map = _build_xbank_regime_map(df_raw)
    xu100_roc_map    = _build_xu100_roc_map(df_raw)
    thresholds       = _compute_thresholds(cfg)
    m_cfg      = cfg.get('market', {})
    gap_filter = m_cfg.get('gap_up_filter', True)
    gap_pct    = float(m_cfg.get('gap_up_pct', 1.02))

    chunks = _chunk_dates(all_dates, n_splits)
    print(f"  Chunk boyutları: {[len(c) for c in chunks]} gün")
    for i, c in enumerate(chunks):
        print(f"  Chunk {i + 1}: {c[0]} → {c[-1]} ({len(c)} gün)")
    print()

    BUCKETS = [
        ('Kisa', 'Diamond'), ('Kisa', 'Ruby'),
        ('Orta', 'Diamond'), ('Orta', 'Firsat'),
        ('Momentum', 'Diamond'),
    ]
    bucket_pf       = {b: [] for b in BUCKETS}
    bucket_wr       = {b: [] for b in BUCKETS}
    bucket_returns  = {b: [] for b in BUCKETS}   # pooled OOS trade returns for DSR
    bucket_pbo_pairs = {b: [] for b in BUCKETS}  # (is_pf, oos_pf) pairs for PBO

    all_combos = list(_combinations(range(n_splits), k))
    total = len(all_combos)

    for combo_idx, combo in enumerate(all_combos):
        oos_dates = []
        for ci in combo:
            chunk = chunks[ci]
            oos_dates.extend(chunk[embargo_days:] if len(chunk) > embargo_days else chunk)
        oos_dates = sorted(set(oos_dates))

        if len(oos_dates) < 20:
            continue

        chunk_labels = '+'.join(str(c + 1) for c in combo)
        print(f"  [{combo_idx + 1:>2}/{total}] Chunks {chunk_labels:<5} "
              f"{oos_dates[0]} – {oos_dates[-1]} ({len(oos_dates)} gün) ...",
              end=' ', flush=True)

        df_result = _cpcv_simulate_window(
            oos_dates, all_dates, df_ind, raw_by_hisse,
            cfg, thresholds,
            xu100_regime_map, xu100_vol_map,
            xutum_rs_map, try_regime_map, xbank_regime_map,
            xu100_roc_map, gap_filter, gap_pct,
            xu100_ema200_map=xu100_ema200_map,
        )

        if df_result.empty:
            print("sinyal yok")
            continue

        for vade, tier in BUCKETS:
            sub = df_result[(df_result['Vade'] == vade) & (df_result['Tier'] == tier)]
            if len(sub) < 5:
                continue
            s = _stats(sub)
            bucket_pf[vade, tier].append(s['pf'])
            bucket_wr[vade, tier].append(s['wr'])
            bucket_returns[vade, tier].extend(sub['KZ_Pct'].dropna().tolist())

        if compute_pbo:
            oos_chunk_set = set()
            for ci in combo:
                oos_chunk_set.update(chunks[ci])
            is_dates = [d for d in all_dates if d not in oos_chunk_set]
            if len(is_dates) >= 20:
                df_is = _cpcv_simulate_window(
                    is_dates, all_dates, df_ind, raw_by_hisse,
                    cfg, thresholds,
                    xu100_regime_map, xu100_vol_map,
                    xutum_rs_map, try_regime_map, xbank_regime_map,
                    xu100_roc_map, gap_filter, gap_pct,
                )
            else:
                df_is = pd.DataFrame()
            for vade, tier in BUCKETS:
                sub_oos = (df_result[(df_result['Vade'] == vade) & (df_result['Tier'] == tier)]
                           if not df_result.empty else pd.DataFrame())
                sub_is  = (df_is[(df_is['Vade'] == vade) & (df_is['Tier'] == tier)]
                           if not df_is.empty else pd.DataFrame())
                oos_pf = _stats(sub_oos)['pf'] if len(sub_oos) >= 5 else None
                is_pf  = _stats(sub_is)['pf']  if len(sub_is)  >= 5 else None
                if oos_pf is not None and is_pf is not None:
                    bucket_pbo_pairs[vade, tier].append((is_pf, oos_pf))
            is_msg = f" / IS:{len(df_is)} işlem" if compute_pbo else ""
            print(f"{len(df_result)} OOS{is_msg}")
        else:
            print(f"{len(df_result)} işlem")

    BUCKET_LABELS = {
        ('Kisa', 'Diamond'):     'Kisa Diamond',
        ('Kisa', 'Ruby'):        'Kisa Ruby',
        ('Orta', 'Diamond'):     'Orta Diamond',
        ('Orta', 'Firsat'):      'Orta Firsat',
        ('Momentum', 'Diamond'): 'Momentum Diamond',
    }

    print(f"\n{'='*70}")
    print(f"  CPCV SONUÇLARI — {n_combos} yol OOS PF Dağılımı")
    print(f"{'='*70}")
    header = (f"  {'Bucket':<20} {'Yollar':>6}  {'Min':>6}  {'P25':>6}  "
              f"{'Median':>6}  {'P75':>6}  {'Max':>6}  {'PF>1%':>6}  {'MedWR':>6}")
    sep = f"  {'-'*80}"
    print(header)
    print(sep)

    md_rows = [header.strip(), sep.strip()]
    results_summary = {}

    for bucket in BUCKETS:
        pf_vals = bucket_pf[bucket]
        label = BUCKET_LABELS[bucket]
        if not pf_vals:
            row = f"  {label:<20} {'—':>6}"
            print(row)
            md_rows.append(row.strip())
            continue
        arr = np.array(sorted(pf_vals))
        n   = len(arr)
        p25 = float(np.percentile(arr, 25))
        med = float(np.median(arr))
        p75 = float(np.percentile(arr, 75))
        pos_rate = float((arr > 1.0).mean() * 100)
        med_wr   = float(np.median(bucket_wr[bucket]))
        row = (f"  {label:<20} {n:>6}  {arr[0]:>6.2f}  {p25:>6.2f}  {med:>6.2f}  "
               f"{p75:>6.2f}  {arr[-1]:>6.2f}  {pos_rate:>5.0f}%  {med_wr:>5.1f}%")
        print(row)
        md_rows.append(row.strip())
        results_summary[label] = {
            'n': n, 'min': float(arr[0]), 'p25': p25, 'median': med,
            'p75': p75, 'max': float(arr[-1]), 'pos_rate': pos_rate, 'med_wr': med_wr,
        }

    weak = [lbl for lbl, r in results_summary.items() if r['median'] < 1.0]
    ok   = [lbl for lbl, r in results_summary.items() if r['median'] >= 1.0]
    print(f"\n  ⚠️  ZAYIF (median PF < 1.0): {weak if weak else 'yok — tüm bucketlar sağlam'}")
    print(f"  ✅ SAĞLAM (median PF ≥ 1.0): {ok if ok else 'yok'}")
    print(f"\n  Sanity: median PF değerlerini tasks/walkforward_results.md OOS PF ile karşılaştır.")
    print(f"  CPCV median PF >> WF OOS PF → WF tek kötü pencereye denk geldi.")
    print(f"  CPCV median PF << WF OOS PF → WF nispeten iyi pencereye denk geldi.")

    pbo_summary = {}
    pbo_md_rows = []
    if compute_pbo:
        print(f"\n{'='*70}")
        print(f"  PBO — Probability of Backtest Overfitting  (gate: PBO < 30%)")
        print(f"  Yöntem: IS-üst-yarı yollar arasında OOS median altı kalma oranı")
        print(f"{'='*70}")
        pbo_header = f"  {'Bucket':<20} {'PBO':>6}  {'N':>4}  {'Karar'}"
        pbo_sep    = f"  {'-'*55}"
        print(pbo_header)
        print(pbo_sep)
        pbo_md_rows = [pbo_header.strip(), pbo_sep.strip()]

        for bucket in BUCKETS:
            label = BUCKET_LABELS[bucket]
            pairs = bucket_pbo_pairs[bucket]
            if len(pairs) < 4:
                row = f"  {label:<20} {'N/A':>6}  {len(pairs):>4}  veri yetersiz"
                print(row); pbo_md_rows.append(row.strip())
                pbo_summary[label] = None
                continue
            T   = len(pairs)
            is_arr  = [p[0] for p in pairs]
            oos_arr = [p[1] for p in pairs]
            oos_med = float(np.median(oos_arr))
            # Sort descending by IS PF; top half = better IS periods
            top_half_idx = sorted(range(T), key=lambda i: is_arr[i], reverse=True)[:max(1, T // 2)]
            bad_oos = sum(1 for i in top_half_idx if oos_arr[i] < oos_med)
            pbo = bad_oos / len(top_half_idx)
            gate_ok = pbo < 0.30
            karar = "✅ CANLI" if gate_ok else "⚠️ ŞÜPHELI"
            row = f"  {label:<20} {pbo*100:>5.0f}%  {T:>4}  {karar}"
            print(row); pbo_md_rows.append(row.strip())
            pbo_summary[label] = {'pbo': pbo, 'n': T, 'gate_ok': gate_ok}

        suspect = [lbl for lbl, r in pbo_summary.items() if r is not None and not r['gate_ok']]
        print(f"\n  ⚠️  PBO ≥ 30% (şüpheli): {suspect if suspect else 'yok — tüm bucketlar temiz'}")

    # ── DSR — Deflated Sharpe Ratio (Phase 0.4) ───────────────────────────────
    print(f"\n{'='*70}")
    print(f"  DSR — Deflated Sharpe Ratio  (M={n_trials} trial, gate: DSR ≥ 0.50)")
    print(f"  PSR = P(true SR > 0)   DSR = P(true SR > expected-max from M trials)")
    print(f"  DSR < 0.50 → indistinguishable from noise at M={n_trials} strategy configs tested")
    print(f"{'='*70}")
    dsr_header = (f"  {'Bucket':<20} {'N':>5}  {'PSR':>6}  {'DSR':>6}  {'Karar'}")
    dsr_sep    = f"  {'-'*60}"
    print(dsr_header)
    print(dsr_sep)
    dsr_md_rows = [dsr_header.strip(), dsr_sep.strip()]
    dsr_summary = {}
    dsr_fail = []

    for bucket in BUCKETS:
        label = BUCKET_LABELS[bucket]
        rets = bucket_returns[bucket]
        if len(rets) < 10:
            row = f"  {label:<20} {len(rets):>5}  {'N/A':>6}  {'N/A':>6}  veri yetersiz"
            print(row); dsr_md_rows.append(row.strip())
            dsr_summary[label] = None
            continue
        psr, dsr = _deflated_sharpe_ratio(rets, n_trials=n_trials)
        if psr is None:
            row = f"  {label:<20} {len(rets):>5}  {'ERR':>6}  {'ERR':>6}  hesaplanamadı"
            print(row); dsr_md_rows.append(row.strip())
            dsr_summary[label] = None
            continue
        gate_ok = dsr >= 0.50
        karar = "✅ GÜRÜLTÜDEN AYIRT" if gate_ok else "❌ GÜRÜLTÜDEN AYIRT DEĞİL"
        row = f"  {label:<20} {len(rets):>5}  {psr:>5.1%}  {dsr:>5.1%}  {karar}"
        print(row); dsr_md_rows.append(row.strip())
        dsr_summary[label] = {'psr': psr, 'dsr': dsr, 'n': len(rets), 'gate_ok': gate_ok}
        if not gate_ok:
            dsr_fail.append(label)

    print(f"\n  ❌ DSR < 0.50 (gürültü): {dsr_fail if dsr_fail else 'yok — tüm bucketlar gürültüden ayırt edildi'}")
    print(f"  ⚠️  Not: M={n_trials} tahmini deneme sayısı. Gerçek trial sayısını --trials=N ile geç.")

    run_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines_md = [
        "# CPCV — Combinatorial Purged Cross-Validation",
        "",
        f"**Çalışma zamanı:** {run_time}",
        f"**Veri:** {all_dates[0]} → {all_dates[-1]} ({lookback_months}m)",
        f"**Parametre:** n_splits={n_splits}, k={k}, embargo={embargo_days}d, "
        f"C({n_splits},{k})={n_combos} yol",
        "",
        "---",
        "",
        "## OOS PF Dağılımı",
        "",
        "```",
    ] + md_rows + [
        "```",
        "",
        f"**Zayıf:** {weak if weak else 'yok'}",
        f"**Sağlam:** {ok if ok else 'yok'}",
        "",
        "---",
        "",
        "> Median PF < 1.0 → strateji bu dönemde net zarar → canlı riski yüksek.",
        "> PF dağılımı geniş (max-min > 1.0) → strateji rejim-duyarlı, tutarlı değil.",
    ]

    if compute_pbo and pbo_md_rows:
        suspect_pbo = [lbl for lbl, r in pbo_summary.items() if r is not None and not r['gate_ok']]
        lines_md += [
            "",
            "---",
            "",
            "## PBO — Probability of Backtest Overfitting",
            "",
            "**Yöntem:** IS-üst-yarı yollar içinde OOS median altı kalma oranı. Gate: < 30% = canlı-layık.",
            "",
            "```",
        ] + pbo_md_rows + [
            "```",
            "",
            f"**PBO ≥ 30% (şüpheli):** {suspect_pbo if suspect_pbo else 'yok — tüm bucketlar temiz'}",
        ]

    lines_md += [
        "",
        "---",
        "",
        "## DSR — Deflated Sharpe Ratio (Phase 0.4)",
        "",
        f"**M (trial sayısı):** {n_trials} (tüm faz boyunca test edilen yaklaşık config sayısı)",
        "**PSR:** P(true SR > 0) — strateji pozitif beklenti taşıyor mu?",
        "**DSR:** P(true SR > expected-max from M trials) — çoklu test yanlılığına göre düzeltilmiş",
        "**Gate:** DSR ≥ 0.50 = gürültüden istatistiksel olarak ayırt edilebilir",
        "",
        "```",
    ] + dsr_md_rows + [
        "```",
        "",
        f"**Gürültüden ayırt edilemeyen:** "
        f"{dsr_fail if dsr_fail else 'yok — tüm bucketlar DSR ≥ 0.50'}",
        "",
        "> DSR < 0.50: Gözlemlenen SR, M={n_trials} rastgele denemedeki beklenen maksimumun altında.",
        "> Bu bucket canlı ortamda gürültüden ayırt edilemez — çok dikkatli kullan.",
    ]

    os.makedirs('tasks', exist_ok=True)
    out_path = 'tasks/cpcv_results.md'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines_md))
    print(f"\n  Sonuçlar {out_path} dosyasına kaydedildi.")
    return results_summary


def backtest_walkforward(cfg=None):
    """Walk-Forward OOS validation (T13).

    In-sample : IS_START → IS_END (2yr — all parameter tuning done in this period)
    OOS       : IS_END   → OOS_END (1yr — never seen during strategy tuning)

    Runs Baseline variant (adaptive_orta, matching live config) on both windows.
    WR drop > 5pp in OOS = overfit signal.
    """
    IS_START = '2022-06-01'
    IS_END   = '2024-06-01'
    OOS_END  = '2025-06-01'

    if cfg is None:
        cfg = _load_cfg()

    print(f"\n{'='*70}")
    print("  WALK-FORWARD OOS VALIDATION (T13)")
    print(f"  In-Sample : {IS_START} → {IS_END} (2 yıl)")
    print(f"  OOS       : {IS_END} → {OOS_END} (1 yıl — ayar sırasında hiç görülmedi)")
    print(f"{'='*70}")

    conn   = sqlite3.connect('bist_ajan.db')
    df_ind = pd.read_sql(
        f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih >= '{IS_START}' ORDER BY Tarih ASC",
        conn,
    )
    df_raw = pd.read_sql(
        "SELECT Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis "
        f"FROM Hisse_Verileri WHERE Tarih >= '{IS_START}' ORDER BY Tarih ASC",
        conn,
    )
    conn.close()

    if df_ind.empty:
        print("  Veri yok. Once veri_motoru.py ve indicator_engine.py calistirin.")
        return

    import backtest_engine as _self
    bst = cfg.get('backtest', {})
    _self.COMMISSION_RT = float(bst.get('commission_rt', 0.004))
    _self.SLIPPAGE_EACH = float(bst.get('slippage_each', 0.005))
    _self.HARD_MAX_LOSS = float(bst.get('hard_max_loss_pct', 0.22))
    _self.PARAMS['Kisa']['target_atr']     = float(bst.get('target_atr_kisa', 2.0))
    _self.PARAMS['Kisa']['stop_atr']       = float(bst.get('stop_atr_kisa', 1.5))
    _self.PARAMS['Orta']['stop_atr']       = float(bst.get('stop_atr_orta', 2.0))
    _self.PARAMS['Duzeltme']['stop_atr']   = float(bst.get('stop_atr_duzeltme', 1.5))
    _self.PARAMS['Duzeltme']['target_atr'] = float(bst.get('target_atr_duzeltme', 3.0))
    _self.PARAMS['Momentum']['stop_atr']   = float(bst.get('stop_atr_momentum', 1.5))
    _self.PARAMS['Momentum']['target_atr'] = float(bst.get('target_atr_momentum', 3.0))
    _self.PARAMS['Momentum']['min_rr']     = float(bst.get('min_rr_momentum', 1.8))

    # Full date list for exit simulation (trades entered near window end need look-ahead)
    all_dates    = sorted(df_ind['Tarih'].unique().tolist())
    raw_by_hisse = {h: g.reset_index(drop=True) for h, g in df_raw.groupby('Hisse')}

    xu100_regime_map = _build_xu100_regime_map(df_raw)
    xu100_vol_map    = _build_xu100_vol_map(df_raw)
    xutum_rs_map     = _build_xutum_rs_map(df_raw)
    try_regime_map   = _build_try_regime_map(df_raw)
    xbank_regime_map = _build_xbank_regime_map(df_raw)
    xu100_roc_map    = _build_xu100_roc_map(df_raw)
    thresholds       = _compute_thresholds(cfg)
    m_cfg      = cfg.get('market', {})
    gap_filter = m_cfg.get('gap_up_filter', True)
    gap_pct    = m_cfg.get('gap_up_pct', 1.02)

    is_dates  = [d for d in all_dates if IS_START <= d < IS_END]
    oos_dates = [d for d in all_dates if IS_END   <= d < OOS_END]

    if not is_dates or not oos_dates:
        print("  Hata: yeterli veri yok (IS veya OOS penceresi boş).")
        return

    print(f"  IS  : {is_dates[0]} → {is_dates[-1]} ({len(is_dates)} gün)")
    print(f"  OOS : {oos_dates[0]} → {oos_dates[-1]} ({len(oos_dates)} gün)")
    print()

    sim_window_results = {}

    for label, window_dates, window_key in [
        ('In-Sample (IS)',       is_dates,  'IS'),
        ('Out-of-Sample (OOS)',  oos_dates, 'OOS'),
    ]:
        window_df_ind = df_ind[df_ind['Tarih'].isin(set(window_dates))].copy()

        print(f"  [{label}] Sinyaller toplanıyor...")
        candidate_signals = _collect_signals(
            window_df_ind, window_dates, cfg,
            xu100_regime_map=xu100_regime_map,
            xu100_vol_map=xu100_vol_map,
            thresholds=thresholds,
            apply_quotas=True,
            xutum_rs_map=xutum_rs_map,
            try_regime_map=try_regime_map,
            xbank_regime_map=xbank_regime_map,
            xu100_roc_map=xu100_roc_map,
        )
        print(f"  Aday sinyal: {len(candidate_signals)} — simülasyon yapılıyor...")

        open_pos    = {'Kisa': {}, 'Orta': {}, 'Duzeltme': {}, 'Momentum': {}}
        sim_results = []

        for tarih, signal in candidate_signals:
            vade  = signal['Vade']
            hisse = signal['Hisse']

            mevcut_exit = open_pos[vade].get(hisse, '')
            if mevcut_exit and tarih <= mevcut_exit:
                continue

            raw_df = raw_by_hisse.get(hisse)
            if raw_df is None:
                continue

            # Baseline: adaptive_orta (Orta vol-adaptive only — matches live config)
            t_atr = _dynamic_target_atr(signal.get('HV_20_Pct', 50), 'Orta') if vade == 'Orta' else None

            result = _simulate_trade(
                signal, tarih, raw_df, all_dates,
                target_atr=t_atr,
                use_trailing_stop=False,
                gap_filter=gap_filter,
                gap_up_pct=gap_pct,
            )
            if result is None:
                continue

            open_pos[vade][hisse] = result['Cikis_Tarihi']
            sim_results.append(result)

        df_result = pd.DataFrame(sim_results) if sim_results else pd.DataFrame()
        sim_window_results[window_key] = df_result
        print(f"  Tamamlanan işlem: {len(sim_results)}")

        if not df_result.empty:
            _print_variant_block(label, df_result)
        print()

    md_lines = _print_walkforward_comparison(sim_window_results, IS_START, IS_END, OOS_END)

    run_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    md_content = '\n'.join([
        f"# Walk-Forward OOS Validation",
        f"",
        f"**Çalışma zamanı:** {run_time}",
        f"**In-Sample:** {IS_START} → {IS_END} (2 yıl — tüm parametre ayarı bu dönemde)",
        f"**OOS:** {IS_END} → {OOS_END} (1 yıl — hiç görülmedi)",
        f"",
        "---",
        "",
    ] + md_lines)
    os.makedirs('tasks', exist_ok=True)
    with open('tasks/walkforward_results.md', 'w', encoding='utf-8') as f:
        f.write(md_content)
    print("  Sonuçlar tasks/walkforward_results.md dosyasına kaydedildi.")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    months_arg       = None
    days_arg         = None
    grid_vade        = None
    yellow_mode      = False
    walkforward_mode = False
    cpcv_mode        = False
    pbo_mode         = False
    n_trials_arg     = 200

    for arg in sys.argv[1:]:
        if arg.startswith('--months='):
            try:
                months_arg = int(arg.split('=')[1])
            except ValueError:
                print(f"  Gecersiz --months degeri: {arg}")
        elif arg.startswith('--weeks='):
            try:
                days_arg = int(arg.split('=')[1]) * 7
            except ValueError:
                print(f"  Gecersiz --weeks degeri: {arg}")
        elif arg.startswith('--days='):
            try:
                days_arg = int(arg.split('=')[1])
            except ValueError:
                print(f"  Gecersiz --days degeri: {arg}")
        elif arg.startswith('--grid='):
            grid_vade = arg.split('=')[1]
        elif arg == '--grid':
            grid_vade = 'Kisa'
        elif arg == '--yellow':
            yellow_mode = True
        elif arg == '--walkforward':
            walkforward_mode = True
        elif arg == '--cpcv':
            cpcv_mode = True
        elif arg == '--pbo':
            pbo_mode = True
        elif arg.startswith('--trials='):
            try:
                n_trials_arg = int(arg.split('=')[1])
            except ValueError:
                print(f"  Gecersiz --trials degeri: {arg}")

    if pbo_mode:
        backtest_cpcv(compute_pbo=True, n_trials=n_trials_arg)
    elif cpcv_mode:
        backtest_cpcv(n_trials=n_trials_arg)
    elif walkforward_mode:
        backtest_walkforward()
    elif yellow_mode:
        backtest_yellow_calistir(months=months_arg)
    elif grid_vade:
        valid = {'Kisa', 'Orta', 'Duzeltme', 'Momentum'}
        if grid_vade not in valid:
            print(f"  Gecersiz --grid degeri '{grid_vade}'. Gecerli: {valid}")
        else:
            backtest_grid_arama(vade=grid_vade, months=months_arg)
    elif months_arg is not None or days_arg is not None:
        # Explicit horizon: single run, no suffix
        backtest_calistir(months=months_arg, days=days_arg)
    else:
        # Default: run 6m, 12m, 24m automatically for full picture
        for m in [6, 12, 24]:
            print(f"\n{'='*70}")
            print(f"  HORIZON: {m} AYLIK BACKTEST")
            print(f"{'='*70}")
            backtest_calistir(months=m, out_suffix=f'_{m}m')
