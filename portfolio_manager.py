import json
import pandas as pd
import sqlite3
from datetime import date as _date

def portfoyu_yonet():
    print("💼 4/5 - Portföy Yöneticisi: Risk ve Trailing Stop yönetimi...")
    conn = sqlite3.connect('bist_ajan.db')
    cursor = conn.cursor()

    cursor.execute('CREATE TABLE IF NOT EXISTS Aktif_Pozisyonlar (Hisse TEXT PRIMARY KEY, Alis_Tarihi TEXT, Alis_Fiyati REAL, Guncel_Stop_Loss REAL, Hedef_Fiyat REAL, Vade TEXT, Tier TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS Islem_Gecmisi (Hisse TEXT, Alis_Tarihi TEXT, Satis_Tarihi TEXT, Alis_Fiyati REAL, Satis_Fiyati REAL, Kar_Zarar_Yuzdesi REAL, Kapanis_Nedeni TEXT, Vade TEXT, Tier TEXT)')
    for _col in ('Vade', 'Tier'):
        for _tbl in ('Aktif_Pozisyonlar', 'Islem_Gecmisi'):
            try:
                cursor.execute(f"ALTER TABLE {_tbl} ADD COLUMN {_col} TEXT")
            except Exception:
                pass

    try:
        with open('strategy_config.json', 'r', encoding='utf-8') as _f:
            _cfg = json.load(_f)
    except Exception:
        _cfg = {}
    _bst = _cfg.get('backtest', {})
    STOP_ATR = {
        'Kisa':     float(_bst.get('stop_atr_kisa', 2.0)),
        'Orta':     float(_bst.get('stop_atr_orta', 2.5)),
        'Momentum': float(_bst.get('stop_atr_momentum', 1.5)),
    }
    MAX_HOLD = {'Kisa': 15, 'Orta': 40, 'Momentum': 15}

    sorgu = '''
    SELECT t1.Hisse, t1.Tarih, t1.Kapanis, t1.En_Yuksek, t1.En_Dusuk, t1.ATR_14
    FROM Hisse_Indikatorleri t1
    INNER JOIN (
        SELECT Hisse, MAX(Tarih) as MaxTarih
        FROM Hisse_Indikatorleri
        GROUP BY Hisse
    ) t2 ON t1.Hisse = t2.Hisse AND t1.Tarih = t2.MaxTarih
    '''
    fiyat_df = pd.read_sql(sorgu, conn)
    guncel_durum = fiyat_df.set_index('Hisse').to_dict('index')

    cursor.execute("SELECT Tarih FROM Hisse_Indikatorleri GROUP BY Tarih HAVING COUNT(Hisse) > 100 ORDER BY Tarih DESC LIMIT 1")
    bugunun_tarihi_res = cursor.fetchone()
    bugunun_tarihi = bugunun_tarihi_res[0] if bugunun_tarihi_res else "Bilinmiyor"

    # 1. MEVCUT POZİSYONLARI GÜNCELLE
    aktifler = pd.read_sql("SELECT * FROM Aktif_Pozisyonlar", conn)
    for index, row in aktifler.iterrows():
        hisse = row['Hisse']
        if hisse not in guncel_durum:
            continue

        guncel_fiyat = guncel_durum[hisse]['Kapanis']
        en_yuksek    = guncel_durum[hisse]['En_Yuksek']
        en_dusuk     = guncel_durum[hisse]['En_Dusuk']    # T6: same-day priority fix
        atr          = guncel_durum[hisse]['ATR_14']
        alis_fiyati, stop_loss, hedef_fiyat = row['Alis_Fiyati'], row['Guncel_Stop_Loss'], row['Hedef_Fiyat']

        _vade = row.get('Vade'); _vade = _vade if _vade and str(_vade) != 'nan' else None
        _tier = row.get('Tier'); _tier = _tier if _tier and str(_tier) != 'nan' else None

        # T4: max hold — force close at today's close when hold period exceeded
        try:
            hold_days = (_date.fromisoformat(bugunun_tarihi) - _date.fromisoformat(row['Alis_Tarihi'])).days
            if hold_days >= MAX_HOLD.get(_vade, 30):
                kz_oran = ((guncel_fiyat - alis_fiyati) / alis_fiyati) * 100
                cursor.execute("INSERT INTO Islem_Gecmisi (Hisse, Alis_Tarihi, Satis_Tarihi, Alis_Fiyati, Satis_Fiyati, Kar_Zarar_Yuzdesi, Kapanis_Nedeni, Vade, Tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (hisse, row['Alis_Tarihi'], bugunun_tarihi, alis_fiyati, guncel_fiyat, kz_oran, 'Max Hold', _vade, _tier))
                cursor.execute("DELETE FROM Aktif_Pozisyonlar WHERE Hisse=?", (hisse,))
                continue
        except Exception:
            pass

        # T6: target check requires en_dusuk > stop_loss (both legs can't hit same day)
        if en_yuksek >= hedef_fiyat and en_dusuk > stop_loss:
            kz_oran = ((hedef_fiyat - alis_fiyati) / alis_fiyati) * 100
            cursor.execute("INSERT INTO Islem_Gecmisi (Hisse, Alis_Tarihi, Satis_Tarihi, Alis_Fiyati, Satis_Fiyati, Kar_Zarar_Yuzdesi, Kapanis_Nedeni, Vade, Tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (hisse, row['Alis_Tarihi'], bugunun_tarihi, alis_fiyati, hedef_fiyat, kz_oran, 'Hedef Fiyat', _vade, _tier))
            cursor.execute("DELETE FROM Aktif_Pozisyonlar WHERE Hisse=?", (hisse,))
        elif (guncel_fiyat / alis_fiyati - 1) < -0.22:
            kz_oran = ((guncel_fiyat - alis_fiyati) / alis_fiyati) * 100
            cursor.execute("INSERT INTO Islem_Gecmisi (Hisse, Alis_Tarihi, Satis_Tarihi, Alis_Fiyati, Satis_Fiyati, Kar_Zarar_Yuzdesi, Kapanis_Nedeni, Vade, Tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (hisse, row['Alis_Tarihi'], bugunun_tarihi, alis_fiyati, guncel_fiyat, kz_oran, 'HardStop', _vade, _tier))
            cursor.execute("DELETE FROM Aktif_Pozisyonlar WHERE Hisse=?", (hisse,))
        elif guncel_fiyat <= stop_loss:
            kz_oran = ((stop_loss - alis_fiyati) / alis_fiyati) * 100
            cursor.execute("INSERT INTO Islem_Gecmisi (Hisse, Alis_Tarihi, Satis_Tarihi, Alis_Fiyati, Satis_Fiyati, Kar_Zarar_Yuzdesi, Kapanis_Nedeni, Vade, Tier) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (hisse, row['Alis_Tarihi'], bugunun_tarihi, alis_fiyati, stop_loss, kz_oran, 'Stop Loss', _vade, _tier))
            cursor.execute("DELETE FROM Aktif_Pozisyonlar WHERE Hisse=?", (hisse,))
        else:
            # T3: per-vade trailing stop multiplier from config
            stop_mult = STOP_ATR.get(_vade, 1.5)
            yeni_potansiyel_stop = round(guncel_fiyat - (stop_mult * atr), 2)
            if yeni_potansiyel_stop > stop_loss:
                cursor.execute("UPDATE Aktif_Pozisyonlar SET Guncel_Stop_Loss=? WHERE Hisse=?", (yeni_potansiyel_stop, hisse))

    # 2. YENİ SİNYALLERİ EKLE — T1: filter blocked signals (Bloke=1 are info-only)
    try:
        yeni_sinyaller = pd.read_sql(
            "SELECT * FROM Gunluk_Sinyaller WHERE Tarih=? AND (Bloke IS NULL OR Bloke=0)",
            conn, params=(bugunun_tarihi,)
        )
        for index, row in yeni_sinyaller.iterrows():
            cursor.execute("SELECT 1 FROM Aktif_Pozisyonlar WHERE Hisse=?", (row['Hisse'],))
            if cursor.fetchone():
                continue
            cursor.execute('INSERT INTO Aktif_Pozisyonlar (Hisse, Alis_Tarihi, Alis_Fiyati, Guncel_Stop_Loss, Hedef_Fiyat, Vade, Tier) VALUES (?, ?, ?, ?, ?, ?, ?)', (row['Hisse'], row['Tarih'], row['Kapanis'], row['Stop_Loss'], row['Hedef_Fiyat'], row.get('Vade'), row.get('Tier')))
    except Exception as e:
        print(f"⚠️ Insert hatası: {e}")

    conn.commit()
    conn.close()
    print("✅ 4/5 Tamamlandı: Portföy güncellendi.")

if __name__ == "__main__":
    portfoyu_yonet()
