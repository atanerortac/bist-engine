import pandas as pd
import sqlite3
import numpy as np
import warnings

warnings.filterwarnings('ignore')


def _hesapla_hisse(group: pd.DataFrame, xu100_raw=None) -> pd.DataFrame:
    """Calculate all technical indicators for one stock's OHLCV DataFrame.

    Args:
        group: DataFrame with Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis, Hacim.
        xu100_raw: Optional DataFrame indexed by Tarih with XU100_K column (for RS_63).

    Returns:
        Same DataFrame with all indicator columns added.
    """
    group = group.sort_values('Tarih').reset_index(drop=True)

    # --- HAREKETLI ORTALAMALAR ---
    group['EMA_20'] = group['Kapanis'].ewm(span=20, adjust=False).mean()
    group['EMA_50'] = group['Kapanis'].ewm(span=50, adjust=False).mean()
    group['EMA_100'] = group['Kapanis'].ewm(span=100, adjust=False).mean()
    group['EMA_200'] = group['Kapanis'].ewm(span=200, adjust=False).mean()

    # --- RSI ---
    delta = group['Kapanis'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    group['RSI_14'] = 100 - (100 / (1 + rs))

    # --- MACD ---
    ema_12 = group['Kapanis'].ewm(span=12, adjust=False).mean()
    ema_26 = group['Kapanis'].ewm(span=26, adjust=False).mean()
    group['MACD'] = ema_12 - ema_26
    group['MACD_Signal'] = group['MACD'].ewm(span=9, adjust=False).mean()
    group['MACD_Hist'] = group['MACD'] - group['MACD_Signal']

    # --- ATR (Wilder Smoothing — SMA'dan düzeltildi) ---
    high_low = group['En_Yuksek'] - group['En_Dusuk']
    high_close = (group['En_Yuksek'] - group['Kapanis'].shift()).abs()
    low_close = (group['En_Dusuk'] - group['Kapanis'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    group['ATR_14'] = tr.ewm(alpha=1/14, adjust=False).mean()
    group['ATR_20'] = tr.ewm(alpha=1/20, adjust=False).mean()

    # --- HACİM ---
    group['Hacim_TL'] = group['Hacim'] * group['Kapanis']
    group['Hacim_Ort_5']  = group['Hacim_TL'].rolling(5).mean()
    group['Hacim_Ort_20'] = group['Hacim_TL'].rolling(20).mean()

    # --- BOLLINGER BANDS ---
    group['BB_Orta'] = group['Kapanis'].rolling(window=20).mean()
    bb_std = group['Kapanis'].rolling(window=20).std()
    group['BB_Ust'] = group['BB_Orta'] + (bb_std * 2)
    group['BB_Alt'] = group['BB_Orta'] - (bb_std * 2)

    # --- STOCHASTIC ---
    low_14 = group['En_Dusuk'].rolling(window=14).min()
    high_14 = group['En_Yuksek'].rolling(window=14).max()
    denom = (high_14 - low_14).replace(0, np.nan)
    group['Stoch_K'] = 100 * ((group['Kapanis'] - low_14) / denom)
    group['Stoch_D'] = group['Stoch_K'].rolling(window=3).mean()

    # --- MFI (Money Flow Index — RSI'ın hacimle ağırlıklandırılmış versiyonu) ---
    typical_price = (group['En_Yuksek'] + group['En_Dusuk'] + group['Kapanis']) / 3
    raw_mf = typical_price * group['Hacim']
    tp_change = typical_price.diff()
    positive_mf = raw_mf.where(tp_change > 0, 0).rolling(14).sum()
    negative_mf = raw_mf.where(tp_change < 0, 0).rolling(14).sum()
    group['MFI_14'] = np.where(
        negative_mf == 0,
        100.0,
        100 - (100 / (1 + positive_mf / negative_mf))
    )

    # --- OBV (On Balance Volume — hacim birikim trendi) ---
    price_diff = group['Kapanis'].diff()
    obv_daily = np.where(
        price_diff > 0, group['Hacim'],
        np.where(price_diff < 0, -group['Hacim'], 0)
    )
    group['OBV'] = pd.Series(obv_daily, index=group.index).cumsum()
    group['OBV_EMA_10'] = group['OBV'].ewm(span=10, adjust=False).mean()

    # --- ADX (Wilder Smoothing — rolling sum'dan düzeltildi) ---
    plus_dm = group['En_Yuksek'].diff()
    minus_dm = group['En_Dusuk'].diff() * -1

    plus_dm[plus_dm < 0] = 0
    plus_dm[plus_dm < minus_dm] = 0

    minus_dm[minus_dm < 0] = 0
    minus_dm[minus_dm < plus_dm] = 0

    tr_smooth = tr.ewm(alpha=1/14, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=1/14, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=1/14, adjust=False).mean()

    tr_safe = tr_smooth.replace(0, 1e-9)
    plus_di = 100 * (plus_dm_smooth / tr_safe)
    minus_di = 100 * (minus_dm_smooth / tr_safe)

    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, 1e-9))
    group['ADX_14'] = dx.ewm(alpha=1/14, adjust=False).mean()
    group['Plus_DI'] = plus_di.ewm(alpha=1/14, adjust=False).mean()
    group['Minus_DI'] = minus_di.ewm(alpha=1/14, adjust=False).mean()

    # --- RS_63: Hissenin XU100'e göre 63 günlük göreceli gücü ---
    if xu100_raw is not None:
        merged = group.set_index('Tarih').join(xu100_raw, how='left')
        merged['XU100_K'] = merged['XU100_K'].ffill()
        stock_ret = merged['Kapanis'].pct_change(63)
        xu100_ret = merged['XU100_K'].pct_change(63)
        group = group.copy()
        group['RS_63'] = (stock_ret.values - xu100_ret.values) * 100
    else:
        group['RS_63'] = np.nan

    # --- HV_20: 20 günlük tarihsel volatilite (yıllıklaştırılmış %) ---
    # --- HV_20_Pct: son 252g içindeki yüzdelik dilim (düşük = sıkışma) ---
    returns = group['Kapanis'].pct_change()
    group['HV_20'] = returns.rolling(20).std() * np.sqrt(252) * 100
    group['HV_20_Pct'] = group['HV_20'].rolling(252, min_periods=60).apply(
        lambda x: float(pd.Series(x).rank(pct=True).iloc[-1]) * 100, raw=False
    )

    # --- BB GENİŞLİK & SQUEEZE (Momentum_Patlama için) ---
    group['BB_Genislik'] = (group['BB_Ust'] - group['BB_Alt']) / group['BB_Orta'].replace(0, np.nan)
    group['BB_Genislik_Min_20'] = group['BB_Genislik'].rolling(20).min()
    group['Squeeze_Patlamasi'] = (
        (group['BB_Genislik'].shift(1) <= group['BB_Genislik_Min_20'].shift(1) * 1.1) &
        (group['BB_Genislik'] > group['BB_Genislik'].shift(1))
    ).astype(int)

    # --- POCKET PIVOT (Momentum_Patlama için) ---
    group['Is_Up_Day'] = (group['Kapanis'] > group['Kapanis'].shift(1)).astype(int)
    group['Down_Hacim'] = group['Hacim_TL'].where(group['Kapanis'] < group['Kapanis'].shift(1), 0)
    group['Max_Down_Hacim_10'] = group['Down_Hacim'].rolling(10).max()
    group['Pocket_Pivot'] = (
        (group['Is_Up_Day'] == 1) &
        (group['Hacim_TL'] > group['Max_Down_Hacim_10'])
    ).astype(int)

    # --- HACİM BİRİKİMİ (son 10 günde yukarı + hacim güçlü gün sayısı) ---
    vol_above_avg5 = (group['Hacim_TL'] > group['Hacim_Ort_5']).astype(int)
    group['Hacim_Birikim_10'] = (group['Is_Up_Day'] & vol_above_avg5).rolling(10).sum()

    # --- 52 HAFTALIK ZİRVEYE YAKINLIK (üst direnç filtresi) ---
    group['High_252D'] = group['En_Yuksek'].rolling(252, min_periods=20).max()
    group['Dist_52W_Pct'] = (group['Kapanis'] / group['High_252D'] - 1) * 100

    # --- RSI BULLISH DIVERGENCE (iki pencere karşılaştırması) ---
    # Son 10 günlük en düşük kapanış vs önceki 10 günün en düşük kapanışı
    # Fiyat son pencerede daha düşük AMA RSI daha yüksek = boğa diverjansı
    N = 10
    price_recent_min = group['Kapanis'].shift(1).rolling(N).min()
    rsi_recent_min   = group['RSI_14'].shift(1).rolling(N).min()
    price_prior_min  = group['Kapanis'].shift(N + 1).rolling(N).min()
    rsi_prior_min    = group['RSI_14'].shift(N + 1).rolling(N).min()
    group['RSI_Div_Bullish'] = (
        (price_recent_min < price_prior_min) &  # fiyat son pencerede daha düşük
        (rsi_recent_min > rsi_prior_min)         # RSI son pencerede daha yüksek (diverjans)
    ).astype(int)

    return group


def hesapla_ve_kaydet():
    print("⚙️ İndikatör Motoru: Vektörel hesaplamalar yapılıyor...")
    conn = sqlite3.connect('bist_ajan.db')
    df = pd.read_sql("SELECT * FROM Hisse_Verileri ORDER BY Tarih ASC", conn)

    if df.empty:
        print("⚠️ Hata: Veritabanı boş.")
        conn.close()
        return

    # XU100 reference prices for RS_63 computation
    xu100_raw = df[df['Hisse'] == 'XU100.IS'][['Tarih', 'Kapanis']].set_index('Tarih')
    xu100_raw = xu100_raw.rename(columns={'Kapanis': 'XU100_K'}).sort_index()
    has_xu100 = not xu100_raw.empty

    hesaplanmis_datalar = []

    for hisse, group in df.groupby('Hisse'):
        # XU100.IS gets its own indicators (ATR_14 needed for vol gate) but no RS_63 vs itself
        xu100_ref = None if hisse == 'XU100.IS' else (xu100_raw if has_xu100 else None)
        group = _hesapla_hisse(group, xu100_ref)
        hesaplanmis_datalar.append(group)

    final_df = pd.concat(hesaplanmis_datalar, ignore_index=True)
    final_df.dropna(subset=['ATR_14', 'MACD_Hist'], inplace=True)

    yazilacak_kolonlar = [
        'Tarih', 'Hisse', 'Kapanis', 'En_Yuksek', 'En_Dusuk', 'Hacim_TL', 'Hacim_Ort_5',
        'Hacim_Ort_20',
        'EMA_20', 'EMA_50', 'EMA_100', 'EMA_200', 'RSI_14',
        'MACD', 'MACD_Signal', 'MACD_Hist', 'ATR_14', 'ATR_20',
        'BB_Ust', 'BB_Orta', 'BB_Alt', 'Stoch_K', 'Stoch_D', 'ADX_14', 'Plus_DI', 'Minus_DI',
        'MFI_14', 'OBV', 'OBV_EMA_10',
        'HV_20', 'HV_20_Pct',
        'BB_Genislik', 'Squeeze_Patlamasi', 'Pocket_Pivot',
        'Hacim_Birikim_10',
        'RS_63',
        'High_252D', 'Dist_52W_Pct',
        'RSI_Div_Bullish'
    ]

    final_df[yazilacak_kolonlar].to_sql('Hisse_Indikatorleri', conn, if_exists='replace', index=False)
    conn.close()
    print("✅ İndikatörler hesaplandı: ATR+ADX Wilder düzeltmesi, MFI-14 ve OBV eklendi.")

if __name__ == "__main__":
    hesapla_ve_kaydet()
