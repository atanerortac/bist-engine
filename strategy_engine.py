import json
import os
import pandas as pd
import sqlite3
import numpy as np


def _load_cfg():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strategy_config.json')
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _safe(val, default=0.0):
    """Returns default if val is NaN or None."""
    try:
        f = float(val)
        return default if np.isnan(f) else f
    except (TypeError, ValueError):
        return default


def _max_puan(sc, include_base=0):
    """Sum of enabled criteria points. include_base adds fixed base (Kisa uses 50).
    Skips keys starting with '_' (metadata).
    """
    return include_base + sum(
        v.get('points', 0)
        for key, v in sc.items()
        if not key.startswith('_') and isinstance(v, dict) and v.get('enabled', True)
    )


def _pts(sc, key, default):
    """Points for a scoring criterion if enabled, else 0."""
    entry = sc.get(key, {})
    if not isinstance(entry, dict):
        return default
    return entry.get('points', default) if entry.get('enabled', True) else 0


# ─────────────────────────── PUANLAMA FONKSİYONLARI ────────────────────────


def hesapla_kisa_vade_puan(row, cfg=None, prev_macd_hist=None, prev_bb_genislik=None):
    """Kısa vadeli momentum sinyali. ~3-7 günlük ufuk.

    Binary gate system: her koşul sert geçiş noktası (AND mantığı).
    Herhangi bir gate başarısız olursa 0 döner (sinyal üretilmez).
    Tüm gateler geçilirse kalite skoru hesaplanır (50-100 arası, sıralama için).

    prev_macd_hist:    dünkü MACD_Hist — histogram ivmesi kontrolü.
    prev_bb_genislik:  dünkü BB_Genislik — sıkışma genişleme bonusu için.
    """
    k = (cfg or {}).get('kisa', {})

    # ── HARD GATES (sıralı — ilk başarısızlıkta hemen çık) ───────────────────

    # 1. MACD crossover + histogram ivmesi: trend yukarı VE momentum hızlanıyor
    if k.get('macd_crossover', True):
        curr_hist = _safe(row['MACD_Hist'])
        macd_above = _safe(row['MACD']) > _safe(row['MACD_Signal'])
        if prev_macd_hist is not None:
            hist_ok = curr_hist > float(prev_macd_hist)   # ivme artıyor
        else:
            hist_ok = curr_hist > 0                        # fallback: pozitif histogram
        if not (macd_above and hist_ok):
            return 0

    # 2. RSI aralığı: ne aşırı satım ne aşırı alım (orta bölge momentum)
    rsi = _safe(row['RSI_14'])
    if not (k.get('rsi_min', 50) < rsi < k.get('rsi_max', 65)):
        return 0

    # 3. Hacim spike: 5 günlük ortalamanın 1.5x üstü (kurumsal ilgi)
    if k.get('volume_spike_5d', True):
        hacim_ort = max(_safe(row['Hacim_Ort_5']), 1)
        if not (_safe(row['Hacim_TL']) > hacim_ort * 1.5):
            return 0

    # 4. EMA20 üstü: kısa vadeli trend sağlam
    if k.get('ema20_above', True):
        if not (_safe(row['Kapanis']) > _safe(row['EMA_20'])):
            return 0

    # 5. Stochastic crossover: K>D ve aşırı alım bölgesinde değil
    stoch_k = _safe(row['Stoch_K'])
    if k.get('stoch_crossover', True):
        if not (stoch_k > _safe(row['Stoch_D']) and 20 < stoch_k < 80):
            return 0

    # 6. MFI > 50: hacim-ağırlıklı momentum pozitif (sahte hareket filtresi)
    if k.get('mfi_above50', True):
        mfi = row.get('MFI_14') if hasattr(row, 'get') else getattr(row, 'MFI_14', None)
        if mfi is None or pd.isna(mfi) or float(mfi) <= 50:
            return 0

    # 7. Extended run filtresi: EMA20 üstünde %12+ = geç giriş, atlama
    if k.get('extended_run_penalty', True):
        ema20 = _safe(row['EMA_20'])
        threshold = k.get('extended_run_threshold', 1.12)
        if ema20 > 0 and _safe(row['Kapanis']) / ema20 > threshold:
            return 0

    # 8. Opsiyonel: 20 günlük hacim ortalaması gate
    if k.get('volume_spike_20d', False):
        h20 = row.get('Hacim_Ort_20') if hasattr(row, 'get') else getattr(row, 'Hacim_Ort_20', None)
        if h20 is None or pd.isna(h20) or float(h20) <= 0:
            return 0
        if not (_safe(row['Hacim_TL']) > float(h20)):
            return 0

    # 9. Sıkışma (coiling) filtresi: HV_20_Pct düşük = düşük volatilite sıkışması
    if k.get('coiling_filter', False):
        hv_pct = row.get('HV_20_Pct') if hasattr(row, 'get') else getattr(row, 'HV_20_Pct', None)
        if hv_pct is None or pd.isna(hv_pct):
            return 0
        if float(hv_pct) > k.get('coiling_max_pct', 40):
            return 0

    # ── TÜM GATELER GEÇİLDİ — Kalite skoru (sıralama için) ──────────────────
    # Skor 50-100 arasında; Diamond/Ruby eşiği _max_puan() üzerinden dinamik hesaplanır.
    sc = (cfg or {}).get('scoring', {}).get('kisa_vade', {})

    hacim_ort = max(_safe(row['Hacim_Ort_5']), 1)
    hacim_ratio = _safe(row['Hacim_TL']) / hacim_ort
    max_vol = _pts(sc, 'vol_bonus', 25)
    vol_bonus = min(max_vol, int((hacim_ratio - 1.5) * 10))

    max_rsi = _pts(sc, 'rsi_bonus', 15)
    rsi_bonus = max(0, max_rsi - int(abs(rsi - 57.5) * 1.5))

    max_stoch = _pts(sc, 'stoch_bonus', 10)
    stoch_bonus = max(0, max_stoch - int(abs(stoch_k - 50) * 0.2))

    ema200_bonus = 0
    if k.get('ema200_bonus', False):
        ema200 = row.get('EMA_200') if hasattr(row, 'get') else getattr(row, 'EMA_200', None)
        if ema200 is not None and not pd.isna(ema200) and _safe(row['Kapanis']) > float(ema200):
            ema200_bonus = _pts(sc, 'ema200_bonus', 10)

    bb_support_bonus = 0
    if k.get('bb_support_entry', False):
        bb_alt = row.get('BB_Alt') if hasattr(row, 'get') else getattr(row, 'BB_Alt', None)
        if bb_alt is not None and not pd.isna(bb_alt) and float(bb_alt) > 0:
            if 0 < _safe(row['Kapanis']) <= float(bb_alt) * 1.02:
                bb_support_bonus = _pts(sc, 'bb_support', 10)

    bb_squeeze_bonus = 0
    if k.get('bb_squeeze_expand', False) and prev_bb_genislik is not None:
        bb_g = row.get('BB_Genislik') if hasattr(row, 'get') else getattr(row, 'BB_Genislik', None)
        if bb_g is not None and not pd.isna(bb_g) and float(bb_g) > float(prev_bb_genislik):
            bb_squeeze_bonus = _pts(sc, 'bb_squeeze', 5)

    vol_accum_bonus = 0
    if k.get('volume_accum_10d', False):
        hb10 = row.get('Hacim_Birikim_10') if hasattr(row, 'get') else getattr(row, 'Hacim_Birikim_10', None)
        if hb10 is not None and not pd.isna(hb10) and float(hb10) >= k.get('volume_accum_min_days', 6):
            vol_accum_bonus = 10  # direct bonus — not via _pts() to avoid _max_puan inflation

    # Direct bonus: NOT in scoring section (avoids _max_puan inflation).
    # Like MACD freshness — additive on top, threshold unchanged.
    w52h_bonus = 0
    if k.get('52w_high_bonus', False):
        _d52 = row.get('Dist_52W_Pct') if hasattr(row, 'get') else getattr(row, 'Dist_52W_Pct', None)
        if _d52 is not None and not pd.isna(_d52) and float(_d52) >= k.get('52w_high_min_pct', -20):
            w52h_bonus = 10

    rsi_div_bonus = 0
    if k.get('rsi_divergence_bonus', False):
        _rdiv = row.get('RSI_Div_Bullish') if hasattr(row, 'get') else getattr(row, 'RSI_Div_Bullish', None)
        if _rdiv is not None and not pd.isna(_rdiv) and int(_rdiv) == 1:
            rsi_div_bonus = 10

    base = sc.get('_base', 50)
    return max(base, base + vol_bonus + rsi_bonus + stoch_bonus + ema200_bonus
               + bb_support_bonus + bb_squeeze_bonus + vol_accum_bonus + w52h_bonus + rsi_div_bonus)


def hesapla_orta_vade_puan(row, cfg=None, prev_macd_hist=None):
    """Orta vadeli trend sinyali puanı. ~3-6 haftalık ufuk.

    prev_macd_hist: dünkü MACD_Hist değeri (freshness tespiti için).
      - Histogram büyüyorsa (ivme taze) → bonus
      - Histogram küçülüyorsa (geç giriş) → ceza
    """
    o = (cfg or {}).get('orta', {})

    # Hard gate: RS_63 minimum (opsiyonel) — XU100'ü yetersiz geçen hisseler atlanır
    rs_min = o.get('rs_min_pct', None)
    if rs_min is not None:
        rs63 = row.get('RS_63') if hasattr(row, 'get') else getattr(row, 'RS_63', None)
        if rs63 is None or pd.isna(rs63) or float(rs63) < float(rs_min):
            return 0

    # Hard gate: EMA_200 (opsiyonel) — uzun vadeli düşüş trendinde orta vade açma
    if o.get('ema200_gate', False):
        ema200 = row.get('EMA_200') if hasattr(row, 'get') else getattr(row, 'EMA_200', None)
        if ema200 is None or pd.isna(ema200) or _safe(row['Kapanis']) <= float(ema200):
            return 0

    puan = 0

    if o.get('ema50_above', True):
        if _safe(row['Kapanis']) > _safe(row['EMA_50']):
            puan += 25

    if _safe(row['ADX_14']) > o.get('adx_min', 20) and _safe(row.get('Plus_DI', 0)) > _safe(row.get('Minus_DI', 0)):
        puan += 20

    if o.get('macd_crossover', True):
        curr_hist = _safe(row['MACD_Hist'])
        if _safe(row['MACD']) > _safe(row['MACD_Signal']) and curr_hist > 0:
            puan += 20
            # MACD freshness: histogram ivmesi taze giriş = +bonus, geç giriş = ceza
            if prev_macd_hist is not None:
                if curr_hist > float(prev_macd_hist):        # ivme artıyor → taze giriş
                    puan += 10
                elif curr_hist < float(prev_macd_hist) * 0.6:  # ivme belirgin düşüyor → geç giriş
                    puan -= 10

    if o.get('obv_above_ema', True):
        obv = row.get('OBV') if hasattr(row, 'get') else getattr(row, 'OBV', None)
        obv_ema = row.get('OBV_EMA_10') if hasattr(row, 'get') else getattr(row, 'OBV_EMA_10', None)
        if obv is not None and obv_ema is not None and not pd.isna(obv) and not pd.isna(obv_ema):
            if float(obv) > float(obv_ema):
                puan += 15

    if o.get('ema20_above', True):
        if _safe(row['Kapanis']) > _safe(row['EMA_20']):
            puan += 10

    rsi = _safe(row['RSI_14'])
    if o.get('rsi_min', 45) < rsi < o.get('rsi_max', 60):
        puan += 10

    if o.get('rs_xu100', True):
        rs63 = row.get('RS_63') if hasattr(row, 'get') else getattr(row, 'RS_63', None)
        if rs63 is not None and not pd.isna(rs63) and float(rs63) > 0:
            puan += o.get('rs_xu100_bonus', 15)

    if o.get('volume_spike_20d', True):
        h20 = row.get('Hacim_Ort_20') if hasattr(row, 'get') else getattr(row, 'Hacim_Ort_20', None)
        if h20 is not None and not pd.isna(h20) and float(h20) > 0:
            if _safe(row['Hacim_TL']) > float(h20):
                puan += 10

    # Direct bonus: NOT in scoring section (avoids _max_puan inflation).
    o2 = (cfg or {}).get('orta', {})
    if o2.get('52w_high_bonus', False):
        _d52 = row.get('Dist_52W_Pct') if hasattr(row, 'get') else getattr(row, 'Dist_52W_Pct', None)
        if _d52 is not None and not pd.isna(_d52) and float(_d52) >= o2.get('52w_high_min_pct', -15):
            puan += 15

    if o2.get('rsi_divergence_bonus', False):
        _rdiv = row.get('RSI_Div_Bullish') if hasattr(row, 'get') else getattr(row, 'RSI_Div_Bullish', None)
        if _rdiv is not None and not pd.isna(_rdiv) and int(_rdiv) == 1:
            puan += 10

    return puan


def hesapla_duzeltme_puan(row, cfg=None):
    """Sağlıklı pullback kalitesini puanlar (maks ~90). Gate koşulları zaten geçilmiş olmalı."""
    d = (cfg or {}).get('duzeltme', {})

    # Hard gate: RSI floor — düşen bıçak girişlerini önler
    rsi_floor = d.get('rsi_floor', 38)
    if _safe(row['RSI_14']) < rsi_floor:
        return 0

    # Hard gate (opsiyonel): EMA_50 yükselen trend gerekliliği
    if d.get('ema50_ascending', False):
        ema50 = row.get('EMA_50') if hasattr(row, 'get') else getattr(row, 'EMA_50', None)
        if ema50 is None or pd.isna(ema50) or _safe(row['Kapanis']) < float(ema50):
            return 0

    # Hard gate (opsiyonel): EMA_200 — yalnızca uzun vadeli yükseliş trendinde giriş
    if d.get('ema200_gate', False):
        ema200 = row.get('EMA_200') if hasattr(row, 'get') else getattr(row, 'EMA_200', None)
        if ema200 is None or pd.isna(ema200) or _safe(row['Kapanis']) <= float(ema200):
            return 0

    puan = 0
    kapanis = _safe(row['Kapanis'])
    ema20 = _safe(row['EMA_20'], kapanis if kapanis > 0 else 1)

    # EMA20 yakınlığı: destek noktasına ne kadar yakın?
    if ema20 > 0:
        proximity_pct = (kapanis / ema20 - 1) * 100
        if proximity_pct < 3.0:    # EMA20'ye çok yakın → mükemmel giriş
            puan += 30
        elif proximity_pct < 7.0:  # Yakın, kabul edilebilir
            puan += 15

    hacim_ort = max(_safe(row['Hacim_Ort_5']), 1)
    if _safe(row['Hacim_TL']) < hacim_ort:  # Düşük hacimli geri çekilme = sağlıklı nefes alma
        puan += 25

    rsi = _safe(row['RSI_14'])
    if 40 < rsi < 55:      # RSI soğuma bölgesi: ideal
        puan += 20
    elif 35 <= rsi <= 40:  # Derin soğuma da değerlendirilebilir
        puan += 10

    stoch_k = _safe(row['Stoch_K'])
    if stoch_k < 30:    # Aşırı satım → güçlü dip potansiyeli
        puan += 15
    elif stoch_k < 50:  # Orta bölge → teknik geri çekilme alanı var
        puan += 8

    return puan  # Maks ~90


def hesapla_momentum_patlama_puan(row, cfg=None):
    """Pocket Pivot / Bollinger squeeze breakout puanı (0-100). GREEN piyasa only."""
    m = (cfg or {}).get('momentum', {})

    # Hard gate: MFI > 50 — kurumsal alım konfirmasyonu (sahte pocket pivot filtresi)
    if m.get('mfi_gate', True):
        mfi = row.get('MFI_14') if hasattr(row, 'get') else getattr(row, 'MFI_14', None)
        if mfi is None or pd.isna(mfi) or float(mfi) <= 50:
            return 0

    # Hard gate: PP+SQ — her iki sinyal ayni anda gerekli (tek sinyal = gurultu)
    if m.get('pp_sq_required', False):
        _pp = row.get('Pocket_Pivot') if hasattr(row, 'get') else getattr(row, 'Pocket_Pivot', None)
        _sq = row.get('Squeeze_Patlamasi') if hasattr(row, 'get') else getattr(row, 'Squeeze_Patlamasi', None)
        pp_ok = _pp is not None and not pd.isna(_pp) and int(_pp) == 1
        sq_ok = _sq is not None and not pd.isna(_sq) and int(_sq) == 1
        if not (pp_ok and sq_ok):
            return 0

    # Hard gate: MACD_Hist > 0 — momentum pozitif (Bollinger squeeze arastirmasi)
    if m.get('macd_hist_gate', False):
        if _safe(row['MACD_Hist']) <= 0:
            return 0

    puan = 0
    pocket = row.get('Pocket_Pivot') if hasattr(row, 'get') else getattr(row, 'Pocket_Pivot', None)
    squeeze = row.get('Squeeze_Patlamasi') if hasattr(row, 'get') else getattr(row, 'Squeeze_Patlamasi', None)
    if pocket is not None and not pd.isna(pocket) and int(pocket) == 1:
        puan += 30
    if squeeze is not None and not pd.isna(squeeze) and int(squeeze) == 1:
        puan += 20
    if 55 < _safe(row['RSI_14']) < 70:
        puan += 20
    if _safe(row['Kapanis']) > _safe(row['EMA_20']) > _safe(row['EMA_50']):
        puan += 15
    obv = row.get('OBV') if hasattr(row, 'get') else getattr(row, 'OBV', None)
    obv_ema = row.get('OBV_EMA_10') if hasattr(row, 'get') else getattr(row, 'OBV_EMA_10', None)
    if obv is not None and obv_ema is not None and not pd.isna(obv) and not pd.isna(obv_ema):
        if float(obv) > float(obv_ema):
            puan += 15

    # Direct bonus: NOT in scoring section (avoids _max_puan inflation).
    m2 = (cfg or {}).get('momentum', {})
    if m2.get('52w_high_bonus', False):
        _d52 = row.get('Dist_52W_Pct') if hasattr(row, 'get') else getattr(row, 'Dist_52W_Pct', None)
        if _d52 is not None and not pd.isna(_d52) and float(_d52) >= m2.get('52w_high_min_pct', -10):
            puan += 15

    return puan


# ─────────────────────────── ROLLING PERFORMANCE + ADAPTIVE QUOTAS ─────────


def _compute_perf_from_kz(kz_list):
    """Compute PF from a list of KZ_Pct values."""
    if not kz_list:
        return {'pf': float('inf'), 'n': 0}
    wins   = sum(r for r in kz_list if r > 0)
    losses = sum(abs(r) for r in kz_list if r < 0)
    return {'pf': wins / losses if losses > 0 else float('inf'), 'n': len(kz_list)}


def _get_rolling_perf(conn, cfg=None):
    """Query Islem_Gecmisi → {(Vade, Tier): {'pf', 'n'}} for live strateji_sec() calls."""
    gates   = (cfg or {}).get('market', {}).get('rolling_gates', {})
    buckets = [('Kisa', 'Ruby'), ('Orta', 'Firsat'),
               ('Kisa', 'Diamond'), ('Orta', 'Diamond'), ('Momentum', 'Diamond')]
    result  = {}
    for vade, tier in buckets:
        key    = f"{vade.lower()}_{tier.lower()}"
        window = gates.get(key, {}).get('window', 20 if vade == 'Orta' else 15)
        try:
            df = pd.read_sql(
                "SELECT Kar_Zarar_Yuzdesi FROM Islem_Gecmisi "
                "WHERE Vade=? AND Tier=? ORDER BY Satis_Tarihi DESC LIMIT ?",
                conn, params=[vade, tier, window]
            )
            if not df.empty:
                result[(vade, tier)] = _compute_perf_from_kz(df['Kar_Zarar_Yuzdesi'].tolist())
        except Exception:
            pass
    return result


def _rolling_perf_from_results(results_list, cfg=None):
    """Compute rolling performance from a backtest results list (for J3 simulation)."""
    gates   = (cfg or {}).get('market', {}).get('rolling_gates', {})
    buckets = [('Kisa', 'Ruby'), ('Orta', 'Firsat'),
               ('Kisa', 'Diamond'), ('Orta', 'Diamond'), ('Momentum', 'Diamond')]
    result  = {}
    for vade, tier in buckets:
        key       = f"{vade.lower()}_{tier.lower()}"
        window    = gates.get(key, {}).get('window', 20 if vade == 'Orta' else 15)
        bucket_kz = [r['KZ_Pct'] for r in results_list
                     if r.get('Vade') == vade and r.get('Tier') == tier]
        recent = bucket_kz[-window:]
        if recent:
            result[(vade, tier)] = _compute_perf_from_kz(recent)
    return result


def strateji_sec(rolling_perf, cfg, verbose=True):
    """Return {(Vade, Tier): quota} — base CAPS adjusted by rolling PF gates.

    Rolling PF gates reduce quota when recent performance degrades.
    Regime-based blocking (KIRMIZI/SARI routing) and the Ruby breadth gate
    are handled separately in sinyalleri_uret() signal routing, not here.
    """
    m_cfg = (cfg or {}).get('market', {})
    gates = m_cfg.get('rolling_gates', {})

    result = {
        ('Kisa', 'Diamond'):     5,
        ('Kisa', 'Ruby'):        8,
        ('Orta', 'Diamond'):     2,   # 4.3: reduced from 3 (weakest WR 32.8%, CPCV 5th)
        ('Orta', 'Firsat'):      5,   # 4.3: kept at 5 (quota=6 diluted PF 1.29→1.09 in 24m test)
        ('Momentum', 'Diamond'): 5,
    }

    for (vade, tier) in list(result.keys()):
        key     = f"{vade.lower()}_{tier.lower()}"
        gate    = gates.get(key, {})
        if not gate.get('enabled', False):
            continue
        perf    = rolling_perf.get((vade, tier), {})
        n       = perf.get('n', 0)
        pf      = perf.get('pf', float('inf'))
        min_n   = gate.get('min_n', 10)
        min_pf  = gate.get('min_pf', 0.7)
        reduced = gate.get('reduced_cap', max(1, result[(vade, tier)] // 2))
        if n >= min_n and pf < min_pf:
            result[(vade, tier)] = reduced
            if verbose:
                print(f"  ⚠️  {vade} {tier} rolling PF={pf:.2f} < {min_pf} "
                      f"(n={n}) — kota {reduced}'e düşürüldü")

    return result


# ─────────────────────────── PİYASA AÇIKLAMASI ──────────────────────────────


def _yazdir_piyasa_durumu(piyasa_durumu, ema20_oran):
    print(f"\n{'='*55}")
    if piyasa_durumu == 'KIRMIZI':
        print(f"  🔴 PİYASA KIRMIZI (%{ema20_oran:.0f} hisse EMA20 üstü)")
        print("  ⚠️  Tüm sinyaller BİLGİ AMAÇLI gösterilir — İşlem önerilmez!")
        print("    ↳ Piyasa geneli düşüşte. Sinyaller uyarı etiketi ile listelenir.")
    elif piyasa_durumu == 'SARI':
        print(f"  🟡 PİYASA SARI (%{ema20_oran:.0f} hisse EMA20 üstü)")
        print("  ✓ Aktif: Düzeltme Fırsatı (trend içi geri çekilme alımları)")
        print("  ✗ Bloke (bilgi amaçlı): Kısa Vade Diamond + Ruby — aşağıda görüntülenir")
        print("  ✗ Bloke (bilgi amaçlı): Orta Vade, Momentum — aşağıda görüntülenir")
    else:
        print(f"  ✅ PİYASA YEŞİL (%{ema20_oran:.0f} hisse EMA20 üstü)")
        print("  ✓ Aktif: Kısa Vade Diamond + Ruby")
        print("  ✓ Aktif: Orta Vade Diamond + Fırsat")
        print("  ✓ Aktif: Düzeltme Fırsatı")
    print(f"{'='*55}\n")


# ─────────────────────────── ANA FONKSİYON ──────────────────────────────────


def sinyalleri_uret():
    print("🧠 Sinyal Motoru: Puanlama sistemiyle fırsatlar aranıyor...")
    cfg = _load_cfg()
    conn = sqlite3.connect('bist_ajan.db')
    cursor = conn.cursor()

    # Tablo oluştur (yeni şema)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS Gunluk_Sinyaller (
            Tarih TEXT, Hisse TEXT, Kapanis REAL, Strateji TEXT, Sinyal TEXT,
            Stop_Loss REAL, Hedef_Fiyat REAL, Potansiyel_Getiri REAL,
            Puan INTEGER DEFAULT 0, Vade TEXT, Tier TEXT, Partial_Cikis REAL,
            Bloke INTEGER DEFAULT 0
        )
    """)
    # Eski tabloya eksik sütunları güvenli ekle
    for col, typ in [('Puan', 'INTEGER'), ('Vade', 'TEXT'), ('Tier', 'TEXT'), ('Partial_Cikis', 'REAL'), ('Bloke', 'INTEGER')]:
        try:
            cursor.execute(f"ALTER TABLE Gunluk_Sinyaller ADD COLUMN {col} {typ}")
        except Exception:
            pass
    conn.commit()

    df = pd.read_sql("SELECT * FROM Hisse_Indikatorleri ORDER BY Tarih ASC", conn)
    if df.empty:
        conn.close()
        return

    tarih_sayilari = df.groupby('Tarih').size()
    gecerli_tarihler = sorted(tarih_sayilari[tarih_sayilari > 100].index)
    if not gecerli_tarihler:
        conn.close()
        return

    son_tarih = gecerli_tarihler[-1]
    guncel_veriler = df[df['Tarih'] == son_tarih]
    dun_veriler = (
        df[df['Tarih'] == gecerli_tarihler[-2]].set_index('Hisse')
        if len(gecerli_tarihler) > 1
        else pd.DataFrame()
    )

    # ── PİYASA FİLTRESİ ──
    toplam = len(guncel_veriler)
    ema20_ustu = len(guncel_veriler[guncel_veriler['Kapanis'] > guncel_veriler['EMA_20']])
    ema20_oran = (ema20_ustu / toplam * 100) if toplam > 0 else 0

    yesil_thr = cfg.get('market', {}).get('yesil_threshold', 55)
    if ema20_oran < 35:
        piyasa_durumu = 'KIRMIZI'
    elif ema20_oran < yesil_thr:
        piyasa_durumu = 'SARI'
    else:
        piyasa_durumu = 'YESIL'

    _yazdir_piyasa_durumu(piyasa_durumu, ema20_oran)

    # ── XU100 VOLATİLİTE ORANI (Orta vol gate için; sıfır = devre dışı) ──
    xu100_vol_ratio = 0.0
    if cfg.get('orta', {}).get('xu100_vol_gate', False):
        _xu = pd.read_sql(
            "SELECT Kapanis, ATR_14 FROM Hisse_Indikatorleri WHERE Hisse='XU100.IS' AND Tarih=? LIMIT 1",
            conn, params=[son_tarih]
        )
        if not _xu.empty:
            _k = float(_xu.iloc[0]['Kapanis'])
            _a = float(_xu.iloc[0]['ATR_14'])
            if _k > 0:
                xu100_vol_ratio = _a / _k

    # ── XUTUM DİVERJANS (büyük-hisse/geniş-piyasa ayrışması; Ruby risk-off sinyali) ──
    xutum_rs_xu100 = 0.0
    if cfg.get('market', {}).get('xutum_ruby_filter', False):
        try:
            _xu100_p = pd.read_sql(
                "SELECT Kapanis FROM Hisse_Verileri WHERE Hisse='XU100.IS' AND Tarih<=? ORDER BY Tarih DESC LIMIT 21",
                conn, params=[son_tarih]
            )
            _xutum_p = pd.read_sql(
                "SELECT Kapanis FROM Hisse_Verileri WHERE Hisse='XUTUM.IS' AND Tarih<=? ORDER BY Tarih DESC LIMIT 21",
                conn, params=[son_tarih]
            )
            if len(_xu100_p) >= 21 and len(_xutum_p) >= 21:
                xu100_ret = (_xu100_p['Kapanis'].iloc[0] / _xu100_p['Kapanis'].iloc[20] - 1) * 100
                xutum_ret = (_xutum_p['Kapanis'].iloc[0] / _xutum_p['Kapanis'].iloc[20] - 1) * 100
                xutum_rs_xu100 = float(xu100_ret - xutum_ret)
        except Exception:
            pass

    # ── XU100 EMA200 MASTER-SWITCH (tüm sinyaller bloke — derin bear market) ──
    xu100_ema200_ok = True
    if cfg.get('market', {}).get('xu100_ema200_filter', False):
        try:
            _xu = pd.read_sql(
                "SELECT Kapanis, EMA_200 FROM Hisse_Indikatorleri WHERE Hisse='XU100.IS' AND Tarih<=? ORDER BY Tarih DESC LIMIT 1",
                conn, params=[son_tarih]
            )
            if not _xu.empty and _xu.iloc[0]['EMA_200'] is not None:
                xu100_ema200_ok = float(_xu.iloc[0]['Kapanis']) > float(_xu.iloc[0]['EMA_200'])
        except Exception:
            pass

    # ── USD/TRY REJİMİ (TRY zayıflıyor mu? Orta için risk-off) ──
    usdtry_above_ema20 = False
    if cfg.get('market', {}).get('try_regime_filter', False):
        try:
            _try_p = pd.read_sql(
                "SELECT Kapanis FROM Hisse_Verileri WHERE Hisse='USDTRY=X' AND Tarih<=? ORDER BY Tarih DESC LIMIT 25",
                conn, params=[son_tarih]
            )
            if len(_try_p) >= 21:
                _try_series = _try_p['Kapanis'].iloc[::-1].reset_index(drop=True)
                _try_ema20 = float(_try_series.ewm(span=20, adjust=False).mean().iloc[-1])
                usdtry_above_ema20 = float(_try_p['Kapanis'].iloc[0]) > _try_ema20
        except Exception:
            pass

    # ── MİNİMUM HACİM FİLTRESİ (sabit kapı koşulu: 50M TL) ──
    filtreli = guncel_veriler[guncel_veriler['Hacim_TL'].fillna(0) >= 50_000_000].copy()

    # ── DİNAMİK EŞİKLER (etkin indikatör sayısına göre otomatik ayarlanır) ──
    # Defaults calibrated so hardcoded values (80/65/55/35/50) are preserved
    # when strategy_config.json scoring section is absent.
    sc_all = cfg.get('scoring', {})
    thr    = cfg.get('thresholds', {})

    kisa_sc      = sc_all.get('kisa_vade', {})
    kisa_max     = _max_puan(kisa_sc, include_base=kisa_sc.get('_base', 50))
    kisa_diamond = int(kisa_max * thr.get('kisa_diamond_pct', 0.80))
    kisa_ruby    = int(kisa_max * thr.get('kisa_ruby_pct', 0.65))

    orta_sc      = sc_all.get('orta_vade', {})
    orta_max     = _max_puan(orta_sc)
    orta_diamond = int(orta_max * thr.get('orta_diamond_pct', 0.80))
    orta_firsat  = int(orta_max * thr.get('orta_firsat_pct', 0.55))

    duz_sc     = sc_all.get('duzeltme', {})
    duz_max    = _max_puan(duz_sc)
    duz_firsat = int(duz_max * thr.get('duzeltme_firsat_pct', 0.28))

    mom_sc      = sc_all.get('momentum_patlama', {})
    mom_max     = _max_puan(mom_sc)
    mom_diamond = int(mom_max * thr.get('momentum_diamond_pct', 0.80))

    adaylar = []
    bloke_adaylar = []

    bst = cfg.get('backtest', {})
    kisa_stop_atr    = bst.get('stop_atr_kisa', 1.5)
    kisa_target_atr  = bst.get('target_atr_kisa', 2.0)
    kisa_min_rr      = bst.get('min_rr_kisa', 1.2)
    orta_stop_atr    = bst.get('stop_atr_orta', 2.0)
    orta_target_atr  = bst.get('target_atr_orta', 5.0)
    orta_min_rr      = bst.get('min_rr_orta', 2.0)
    duz_stop_atr     = bst.get('stop_atr_duzeltme', 2.0)
    duz_target_atr   = bst.get('target_atr_duzeltme', 3.0)
    duz_min_rr       = bst.get('min_rr_duzeltme', 1.5)

    # ── KISA VADE PUANLAMA ──
    for _, row in filtreli.iterrows():
        hisse_row = row['Hisse']
        prev_mh = None
        prev_bb_g = None
        if not dun_veriler.empty and hisse_row in dun_veriler.index:
            v = dun_veriler.loc[hisse_row, 'MACD_Hist']
            if not pd.isna(v):
                prev_mh = float(v)
            v2 = dun_veriler.loc[hisse_row, 'BB_Genislik'] if 'BB_Genislik' in dun_veriler.columns else None
            if v2 is not None and not pd.isna(v2):
                prev_bb_g = float(v2)
        puan = hesapla_kisa_vade_puan(row, cfg, prev_macd_hist=prev_mh, prev_bb_genislik=prev_bb_g)
        if puan < kisa_ruby:   # gate sistemi: 0 (başarısız) veya kisa_ruby+ arası
            continue
        if puan >= kisa_diamond:
            tier = 'Diamond'
        else:
            tier = 'Ruby'
        # Weekly trend filter: Ruby only — Diamond exempt (small sample needs all signals)
        if tier == 'Ruby' and cfg.get('market', {}).get('weekly_trend_filter', False):
            _ema100 = _safe(row.get('EMA_100', 0))
            if _ema100 > 0 and _safe(row['Kapanis']) < _ema100:
                continue
        # EMA gate for Kisa Diamond — EMA_100 or EMA_50 depending on config
        if tier == 'Diamond' and cfg.get('market', {}).get('kisa_diamond_ema100_gate', False):
            _ema100 = _safe(row.get('EMA_100', 0))
            if _ema100 > 0 and _safe(row['Kapanis']) < _ema100:
                continue
        if tier == 'Diamond' and cfg.get('market', {}).get('kisa_diamond_ema50_gate', False):
            _ema50 = _safe(row.get('EMA_50', 0))
            if _ema50 > 0 and _safe(row['Kapanis']) < _ema50:
                continue
        # Mid-zone gate: block EMA_50-EMA_100 zone (these signals have poor quality empirically)
        # Keeps: below EMA_50 (recovery bounces) OR above EMA_100 (uptrend continuation)
        if tier == 'Diamond' and cfg.get('market', {}).get('kisa_diamond_mid_zone_gate', False):
            _ema50  = _safe(row.get('EMA_50', 0))
            _ema100 = _safe(row.get('EMA_100', 0))
            if _ema50 > 0 and _ema100 > 0 and _ema50 <= _safe(row['Kapanis']) < _ema100:
                continue
        # SARI: tüm Kisa bloke (Diamond+Ruby). KIRMIZI: tüm tier bloke — M2 fix
        # Ruby: ek breadth kapısı — N4 fix
        _ruby_min_b = float(cfg.get('market', {}).get('kisa_ruby_min_breadth', 55))
        _xutum_thr  = float(cfg.get('market', {}).get('xutum_rs_threshold', 3.0))
        _xutum_on   = cfg.get('market', {}).get('xutum_ruby_filter', False)
        kisa_ruby_bloke = (tier == 'Ruby') and (
            ema20_oran < _ruby_min_b or (_xutum_on and xutum_rs_xu100 > _xutum_thr)
        )
        kisa_bloke = piyasa_durumu in ('KIRMIZI', 'SARI') or kisa_ruby_bloke or not xu100_ema200_ok

        kapanis = _safe(row['Kapanis'])
        atr = _safe(row['ATR_14'])
        if atr <= 0:
            continue

        stop = round(max(kapanis - kisa_stop_atr * atr, kapanis * 0.85), 2)
        hedef = round(kapanis + kisa_target_atr * atr, 2)
        risk = kapanis - stop
        reward = hedef - kapanis
        if risk <= 0 or reward / risk < kisa_min_rr:
            continue

        hacim_ort = max(_safe(row['Hacim_Ort_5']), 1)
        hacim_ratio = _safe(row['Hacim_TL']) / hacim_ort

        (bloke_adaylar if kisa_bloke else adaylar).append({
            'Hisse': row['Hisse'], 'Kapanis': kapanis, 'Vade': 'Kisa', 'Tier': tier,
            'Puan': puan, 'PuanPct': puan / kisa_max if kisa_max else 0,
            'Stop_Loss': stop, 'Hedef_Fiyat': hedef,
            'Potansiyel_Getiri': round((reward / kapanis) * 100, 2),
            'Partial_Cikis': round(kapanis + 1.5 * atr, 2),
            '_tie': -hacim_ratio,
        })

    # ── ORTA VADE PUANLAMA (YEŞİL aktif; SARI/KIRMIZI bilgi amaçlı) ──
    if piyasa_durumu in ('YESIL', 'SARI', 'KIRMIZI'):
        o_cfg = cfg.get('orta', {})
        _o_vol_blocked  = o_cfg.get('xu100_vol_gate', False) and xu100_vol_ratio > float(o_cfg.get('xu100_vol_max', 0.025))
        _try_blocked    = cfg.get('market', {}).get('try_regime_filter', False) and usdtry_above_ema20
        orta_bloke = piyasa_durumu in ('SARI', 'KIRMIZI') or _o_vol_blocked or _try_blocked or not xu100_ema200_ok
        for _, row in filtreli.iterrows():
            kapanis = _safe(row['Kapanis'])
            atr = _safe(row['ATR_14'])
            if atr <= 0:
                continue
            # Hard gate: ADX trend confirmation (opsiyonel)
            if o_cfg.get('adx_gate', False):
                if not (_safe(row['ADX_14']) > o_cfg.get('adx_min', 20)
                        and _safe(row.get('Plus_DI', 0)) > _safe(row.get('Minus_DI', 0))):
                    continue
            # Prev-day MACD_Hist for freshness
            hisse_row = row['Hisse']
            prev_mh = None
            if not dun_veriler.empty and hisse_row in dun_veriler.index:
                v = dun_veriler.loc[hisse_row, 'MACD_Hist']
                if not pd.isna(v):
                    prev_mh = float(v)
            puan = hesapla_orta_vade_puan(row, cfg, prev_macd_hist=prev_mh)
            if puan < orta_firsat:
                continue
            tier = 'Diamond' if puan >= orta_diamond else 'Firsat'
            # EMA_100 gate for Orta Diamond (medium-term trend alignment, like weekly_trend_filter for Kisa Ruby)
            if tier == 'Diamond' and o_cfg.get('diamond_ema100_gate', False):
                _ema100 = _safe(row.get('EMA_100', 0))
                if _ema100 > 0 and kapanis < _ema100:
                    continue
            # ADX Diamond gate — Diamond-only ADX filter (different from adx_gate which blocks all Orta)
            if tier == 'Diamond' and o_cfg.get('diamond_adx_gate', False):
                _adx = _safe(row.get('ADX_14', 0))
                if _adx < o_cfg.get('diamond_adx_min', 22):
                    continue

            stop = round(max(kapanis - orta_stop_atr * atr, kapanis * 0.82), 2)
            # N2: Vol-Adaptive target for Orta (36m validated: PF 1.53→1.62)
            if o_cfg.get('vol_adaptive_target', False):
                _hv = _safe(row.get('HV_20_Pct') if hasattr(row, 'get') else getattr(row, 'HV_20_Pct', None))
                if _hv <= 0 or pd.isna(_hv): _hv = 50.0
                _t_mult = 3.5 if _hv < 30 else (6.5 if _hv >= 60 else orta_target_atr)
            else:
                _t_mult = orta_target_atr
            hedef = round(kapanis + _t_mult * atr, 2)
            risk = kapanis - stop
            reward = hedef - kapanis
            if risk <= 0 or reward / risk < orta_min_rr:
                continue

            (bloke_adaylar if orta_bloke else adaylar).append({
                'Hisse': row['Hisse'], 'Kapanis': kapanis, 'Vade': 'Orta', 'Tier': tier,
                'Puan': puan, 'PuanPct': puan / orta_max if orta_max else 0,
                'Stop_Loss': stop, 'Hedef_Fiyat': hedef,
                'Potansiyel_Getiri': round((reward / kapanis) * 100, 2),
                'Partial_Cikis': round(kapanis + 2.5 * atr, 2),
                '_tie': -_safe(row['ADX_14']),
            })

    # ── DÜZELTME (PULLBACK) PUANLAMA ──
    # Grid arama (144 kombinasyon, 24ay): en iyi PF 0.87 — PF>1.0 yok. Strateji devre dışı.
    if cfg.get('duzeltme', {}).get('enabled', True) and not dun_veriler.empty:
        for _, row in filtreli.iterrows():
            hisse = row['Hisse']
            if hisse not in dun_veriler.index:
                continue
            dun_kapanis = _safe(dun_veriler.loc[hisse, 'Kapanis'])
            kapanis = _safe(row['Kapanis'])

            # Gate koşulları (sabit kapı — bunları geçmeden puanlamaya dahil etme)
            if kapanis >= dun_kapanis:  # Fiyat bugün düşmemiş
                continue
            if _safe(row['Hacim_TL']) < 10_000_000:
                continue
            if not (_safe(row['MACD']) > _safe(row['MACD_Signal']) and _safe(row['MACD_Hist']) > 0):
                continue
            if kapanis <= _safe(row['EMA_20']):
                continue

            puan = hesapla_duzeltme_puan(row, cfg)
            if puan < duz_firsat:
                continue

            atr = _safe(row['ATR_14'])
            if atr <= 0:
                continue

            stop = round(max(kapanis - duz_stop_atr * atr, kapanis * 0.85), 2)
            hedef = round(kapanis + duz_target_atr * atr, 2)
            risk = kapanis - stop
            reward = hedef - kapanis
            if risk <= 0 or reward / risk < duz_min_rr:
                continue

            ema20 = _safe(row['EMA_20'], kapanis)
            proximity = abs(kapanis / ema20 - 1) if ema20 > 0 else 1.0

            _duz_entry = {
                'Hisse': hisse, 'Kapanis': kapanis, 'Vade': 'Duzeltme', 'Tier': 'Firsat',
                'Puan': puan, 'PuanPct': puan / duz_max if duz_max else 0,
                'Stop_Loss': stop, 'Hedef_Fiyat': hedef,
                'Potansiyel_Getiri': round((reward / kapanis) * 100, 2),
                'Partial_Cikis': round(kapanis + 1.5 * atr, 2),
                '_tie': proximity,
            }
            (bloke_adaylar if piyasa_durumu == 'KIRMIZI' else adaylar).append(_duz_entry)

    # ── MOMENTUM PATLAMA (Pocket Pivot / Squeeze Breakout) ──
    # YEŞİL: tüm tier aktif. SARI: Diamond aktif (diamond_sari_ok=true ise), Firsat bloke. KIRMIZI: tümü bloke.
    if piyasa_durumu in ('YESIL', 'SARI', 'KIRMIZI'):
        _m_cfg = cfg.get('momentum', {})
        _diamond_min_breadth = _m_cfg.get('diamond_min_breadth', 60)
        _vdu_max       = _m_cfg.get('vdu_max_accum')             # Firsat: VDU hacim kurumasi
        _rs63_min      = _m_cfg.get('diamond_rs63_min')          # Diamond: XU100 ustperformans
        _d_vol_mult    = _m_cfg.get('diamond_vol_mult')          # Diamond: hacim carpani (1.8x)
        _d_bull_close  = _m_cfg.get('diamond_bullish_close', False)
        _d_ema_stack   = _m_cfg.get('diamond_ema_stack', False)  # Diamond: EMA_20>50>200
        _d_rs_accel    = _m_cfg.get('diamond_rs_accel', False)   # Diamond: RS_63 yukseliyor
        _d_vol_persist = _m_cfg.get('diamond_vol_persist', False) # Diamond: Ort5>Ort20

        # RS_63 5-gun-once (RSaccel kapisi icin)
        _rs63_5d_ago = {}
        if _d_rs_accel and len(gecerli_tarihler) > 5:
            _t5d = gecerli_tarihler[-6]
            _df5 = df[df['Tarih'] == _t5d][['Hisse', 'RS_63']]
            _rs63_5d_ago = dict(zip(_df5['Hisse'], _df5['RS_63']))
        for _, row in filtreli.iterrows():
            puan = hesapla_momentum_patlama_puan(row, cfg)
            if puan < mom_diamond:
                continue
            tier = 'Diamond'

            # Diamond-only quality gates
            if tier == 'Diamond':
                if _rs63_min is not None:
                    rs63_v = row.get('RS_63') if hasattr(row, 'get') else getattr(row, 'RS_63', None)
                    if rs63_v is None or pd.isna(rs63_v) or float(rs63_v) < float(_rs63_min):
                        continue
                if _d_vol_mult is not None:
                    htl = _safe(row['Hacim_TL'])
                    h20 = _safe(row.get('Hacim_Ort_20', 0))
                    if h20 <= 0 or htl < h20 * float(_d_vol_mult):
                        continue
                if _d_bull_close:
                    k  = _safe(row['Kapanis'])
                    hi = _safe(row.get('En_Yuksek', 0))
                    lo = _safe(row.get('En_Dusuk', k))
                    if hi > lo and (k - lo) / (hi - lo) <= 0.60:
                        continue
                if _d_ema_stack:
                    e20 = _safe(row.get('EMA_20', 0)); e50 = _safe(row.get('EMA_50', 0)); e200 = _safe(row.get('EMA_200', 0))
                    if not (e20 > e50 > e200 > 0):
                        continue
                if _d_rs_accel:
                    rs_now = _safe(row.get('RS_63', 0))
                    rs_ago = _rs63_5d_ago.get(row['Hisse'] if hasattr(row, '__getitem__') else getattr(row, 'Hisse', ''))
                    if rs_ago is None or pd.isna(float(rs_ago)) or rs_now <= float(rs_ago):
                        continue
                if _d_vol_persist:
                    h5 = _safe(row.get('Hacim_Ort_5', 0)); h20 = _safe(row.get('Hacim_Ort_20', 0))
                    if h20 <= 0 or h5 <= h20:
                        continue
                # O'Neil base requirement: PP must fire near EMA_20, not extended
                _prox_max = _m_cfg.get('diamond_ema20_proximity_max', 1.10)
                _e20_prox = _safe(row.get('EMA_20', 0))
                if _e20_prox > 0 and _safe(row['Kapanis']) / _e20_prox > _prox_max:
                    continue

            kapanis = _safe(row['Kapanis'])
            atr = _safe(row['ATR_14'])
            ema20 = _safe(row['EMA_20'])
            if atr <= 0 or ema20 <= 0:
                continue

            _m_stop_atr = bst.get('stop_atr_momentum', 1.5)
            _m_tgt_atr  = bst.get('target_atr_momentum', 3.0)
            _m_min_rr   = bst.get('min_rr_momentum', 1.8)
            stop = round(max(kapanis - _m_stop_atr * atr, ema20 * 0.99), 2)
            hedef = round(kapanis + _m_tgt_atr * atr, 2)
            risk = kapanis - stop
            reward = hedef - kapanis
            if risk <= 0 or reward / risk < _m_min_rr:
                continue

            max_down = row.get('Max_Down_Hacim_10') if hasattr(row, 'get') else getattr(row, 'Max_Down_Hacim_10', None)
            hacim_ort = max(_safe(row['Hacim_Ort_5']), 1)
            pp_ratio = _safe(row['Hacim_TL']) / max(
                float(max_down) if max_down is not None and not pd.isna(max_down) else hacim_ort, 1
            )

            _diamond_ok_in_sari = (tier == 'Diamond' and ema20_oran >= _diamond_min_breadth)
            _mom_bloke = piyasa_durumu == 'KIRMIZI' or (piyasa_durumu == 'SARI' and not _diamond_ok_in_sari) or not xu100_ema200_ok
            (bloke_adaylar if _mom_bloke else adaylar).append({
                'Hisse': row['Hisse'], 'Kapanis': kapanis, 'Vade': 'Momentum', 'Tier': tier,
                'Puan': puan, 'PuanPct': puan / mom_max if mom_max else 0,
                'Stop_Loss': stop, 'Hedef_Fiyat': hedef,
                'Potansiyel_Getiri': round((reward / kapanis) * 100, 2),
                'Partial_Cikis': round(kapanis + 1.5 * atr, 2),
                '_tie': -pp_ratio,
            })

    # ── GLOBAL DEDÜPLİKASYON: her hisse en yüksek puanlı track'te ──
    best_per_hisse = {}
    for a in adaylar:
        h = a['Hisse']
        pct = a.get('PuanPct', 0.0)
        if h not in best_per_hisse or pct > best_per_hisse[h].get('PuanPct', 0.0):
            best_per_hisse[h] = a
    adaylar = list(best_per_hisse.values())

    # ── BLOKE ADAYLAR DEDUP + KOTA ──
    best_bloke = {}
    for a in bloke_adaylar:
        h = a['Hisse']
        pct = a.get('PuanPct', 0.0)
        if h not in best_bloke or pct > best_bloke[h].get('PuanPct', 0.0):
            best_bloke[h] = a
    bloke_adaylar = list(best_bloke.values())
    BLOKE_CAPS = {
        ('Kisa', 'Diamond'):     5,
        ('Kisa', 'Ruby'):        8,
        ('Orta', 'Diamond'):     2,   # 4.3: matches live CAPS
        ('Orta', 'Firsat'):      5,   # 4.3: matches live CAPS
        ('Momentum', 'Diamond'): 5,
    }
    bloke_sinyaller = []
    for (vade, tier), cap in BLOKE_CAPS.items():
        bucket = [a for a in bloke_adaylar if a['Vade'] == vade and a['Tier'] == tier]
        bucket.sort(key=lambda x: (-x['Puan'], x['_tie']))
        for a in bucket[:cap]:
            bloke_sinyaller.append({
                'Tarih': son_tarih, 'Hisse': a['Hisse'], 'Kapanis': a['Kapanis'],
                'Strateji': f"{a['Vade']}_{a['Tier']}",
                'Sinyal': 'AL', 'Stop_Loss': a['Stop_Loss'], 'Hedef_Fiyat': a['Hedef_Fiyat'],
                'Potansiyel_Getiri': a['Potansiyel_Getiri'],
                'Puan': a['Puan'], 'Vade': a['Vade'], 'Tier': a['Tier'],
                'Partial_Cikis': a.get('Partial_Cikis'),
                'Bloke': 1,
            })

    # ── KOTA UYGULAMASI (J3: adaptive quotas via strateji_sec) ──
    rolling_perf = _get_rolling_perf(conn, cfg)
    CAPS = strateji_sec(rolling_perf, cfg)

    gunluk_sinyaller = []
    for (vade, tier), cap in CAPS.items():
        bucket = [a for a in adaylar if a['Vade'] == vade and a['Tier'] == tier]
        bucket.sort(key=lambda x: (-x['Puan'], x['_tie']))
        for a in bucket[:cap]:
            gunluk_sinyaller.append({
                'Tarih': son_tarih, 'Hisse': a['Hisse'], 'Kapanis': a['Kapanis'],
                'Strateji': f"{a['Vade']}_{a['Tier']}",
                'Sinyal': 'AL', 'Stop_Loss': a['Stop_Loss'], 'Hedef_Fiyat': a['Hedef_Fiyat'],
                'Potansiyel_Getiri': a['Potansiyel_Getiri'],
                'Puan': a['Puan'], 'Vade': a['Vade'], 'Tier': a['Tier'],
                'Partial_Cikis': a.get('Partial_Cikis'),
            })

    cursor.execute("DELETE FROM Gunluk_Sinyaller WHERE Tarih=?", (son_tarih,))
    conn.commit()

    if gunluk_sinyaller:
        pd.DataFrame(gunluk_sinyaller).to_sql('Gunluk_Sinyaller', conn, if_exists='append', index=False)
    if bloke_sinyaller:
        pd.DataFrame(bloke_sinyaller).to_sql('Gunluk_Sinyaller', conn, if_exists='append', index=False)

    conn.close()
    bloke_str = f" + {len(bloke_sinyaller)} bloke (bilgi amaçlı)" if bloke_sinyaller else ""
    print(f"✅ Sinyal üretimi tamamlandı. Toplam {len(gunluk_sinyaller)} sinyal üretildi{bloke_str}.")


if __name__ == "__main__":
    sinyalleri_uret()
