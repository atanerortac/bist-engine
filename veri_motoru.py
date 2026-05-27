import requests
import pandas as pd
import yfinance as yf
import sqlite3
import warnings

warnings.filterwarnings('ignore')

def tum_bist_hisselerini_getir():
    print("🌐 TradingView API üzerinden tüm BIST hisseleri çekiliyor (JSON)...")
    url = "https://scanner.tradingview.com/turkey/scan"
    
    payload = {
        "columns": ["name"],
        "filter": [{"left": "type", "operation": "equal", "right": "stock"}]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()
        hisseler = [item['d'][0] + ".IS" for item in data.get('data', [])]
        print(f"✅ Toplam {len(hisseler)} adet hisse senedi başarıyla bulundu.")
        return hisseler
    except Exception as e:
        print(f"❌ API Hatası: {e}")
        return ['THYAO.IS', 'TUPRS.IS', 'ASELS.IS']

def verileri_guncelle():
    conn = sqlite3.connect('bist_ajan.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Hisse_Verileri (
            Tarih TEXT, Hisse TEXT, Acilis REAL, En_Yuksek REAL, En_Dusuk REAL, Kapanis REAL, Hacim REAL,
            UNIQUE(Tarih, Hisse)
        )
    ''')
    
    # Veritabanındaki son tarihi al
    cursor.execute("SELECT MAX(Tarih) FROM Hisse_Verileri")
    son_tarih = cursor.fetchone()[0]
    
    hisse_evreni = tum_bist_hisselerini_getir()
    if 'XU100.IS' not in hisse_evreni:
        hisse_evreni.append('XU100.IS')
    if 'XUTUM.IS' not in hisse_evreni:
        hisse_evreni.append('XUTUM.IS')
    if 'USDTRY=X' not in hisse_evreni:
        hisse_evreni.append('USDTRY=X')

    if not son_tarih:
        print("🤖 1/5 - Veri Motoru: Veritabanı BOŞ. İlk kurulum yapılıyor, 5 Yıllık veriler çekilecek (Zaman alabilir)...")
        # Toplu indirme (Çok daha hızlı)
        data = yf.download(hisse_evreni, period="5y", group_by="ticker", threads=True, multi_level_index=True)
    else:
        # son_tarih'ten sonrasını çekmek için format ayarlaması
        # yfinance start parametresini bir gün öncesinden alabiliriz garantili olması için
        baslangic_tarihi = (pd.to_datetime(son_tarih) - pd.Timedelta(days=5)).strftime('%Y-%m-%d')
        print(f"🤖 1/5 - Veri Motoru: Veritabanı DOLU. Eksik veriler ({baslangic_tarihi} sonrası) çekiliyor...")
        data = yf.download(hisse_evreni, start=baslangic_tarihi, group_by="ticker", threads=True, multi_level_index=True)

    # Datanın parse edilip DB'ye yazılması
    # yfinance toplu indirdiğinde MultiIndex döner (Eğer birden fazla hisse varsa)
    
    # Hızlı insert için liste hazırlama
    insert_data = []
    
    if len(hisse_evreni) == 1:
        # Tek hisse varsa MultiIndex dönmez
        hisse = hisse_evreni[0]
        data.reset_index(inplace=True)
        for index, row in data.iterrows():
            tarih = pd.to_datetime(row['Date']).strftime('%Y-%m-%d')
            insert_data.append((tarih, hisse, float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']), float(row['Volume'])))
    else:
        for hisse in hisse_evreni:
            if hisse in data:
                hisse_data = data[hisse]
                if hisse_data.empty or hisse_data['Close'].isna().all():
                    continue
                hisse_data = hisse_data.reset_index()
                for index, row in hisse_data.iterrows():
                    if pd.isna(row['Close']): continue
                    tarih = pd.to_datetime(row['Date']).strftime('%Y-%m-%d')
                    insert_data.append((tarih, hisse, float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']), float(row['Volume'])))

    if insert_data:
        cursor.executemany('''
            INSERT OR REPLACE INTO Hisse_Verileri
            (Tarih, Hisse, Acilis, En_Yuksek, En_Dusuk, Kapanis, Hacim)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', insert_data)
        
    conn.commit()
    conn.close()
    print(f"✅ 1/5 Tamamlandı: {len(insert_data)} adet fiyat verisi işlendi.")

if __name__ == "__main__":
    verileri_guncelle()