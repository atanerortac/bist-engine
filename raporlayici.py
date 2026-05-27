import json
import pandas as pd
import sqlite3
import os
from temel_motoru import temel_verileri_getir


def _load_ps_cfg():
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategy_config.json")
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("position_sizing", {})
    except Exception:
        return {}


def _hesapla_lot(kapanis, stop_loss, ps_cfg):
    if not ps_cfg.get("enabled") or not ps_cfg.get("portfolio_value"):
        return None, None
    stop_mesafe = kapanis - stop_loss
    if stop_mesafe <= 0:
        return None, None
    risk_tl = ps_cfg["portfolio_value"] * ps_cfg.get("risk_pct", 0.02)
    lot = int(risk_tl / stop_mesafe)
    if lot < 1:
        return None, None
    max_pct = ps_cfg.get("max_position_pct", 0.15)
    max_lot = int(ps_cfg["portfolio_value"] * max_pct / kapanis)
    lot = min(lot, max_lot)
    sermaye = lot * kapanis
    return lot, sermaye


def _piyasa_durumu_hesapla(conn, son_tarih):
    """Market breadth hesapla ve durum dict döndür."""
    df = pd.read_sql(
        f"SELECT Kapanis, EMA_20 FROM Hisse_Indikatorleri WHERE Tarih='{son_tarih}'", conn
    )
    toplam = len(df)
    if toplam == 0:
        return {'durum': 'KIRMIZI', 'oran': 0.0}
    ema20_ustu = len(df[df['Kapanis'] > df['EMA_20']])
    oran = (ema20_ustu / toplam) * 100
    if oran < 35:
        durum = 'KIRMIZI'
    elif oran < 50:
        durum = 'SARI'
    else:
        durum = 'YESIL'
    return {'durum': durum, 'oran': oran}


def _yazdir_piyasa_durumu(piyasa):
    durum = piyasa['durum']
    oran = piyasa['oran']
    print("\n" + "="*55)
    print("🌐 PİYASA DURUMU (Market Breadth)")
    if durum == 'KIRMIZI':
        print(f"  🔴 PİYASA KIRMIZI (%{oran:.0f} hisse EMA20 üstü)")
        print("  ⚠️  Tüm sinyaller BİLGİ AMAÇLI gösterilir — İşlem önerilmez!")
        print("    ↳ Piyasa geneli düşüşte. Sinyaller uyarı etiketi ile listelenir.")
    elif durum == 'SARI':
        print(f"  🟡 PİYASA SARI (%{oran:.0f} hisse EMA20 üstü)")
        print("  ✓ Aktif: Kısa Vade Fırsat (savunmacı, kısa vadeli)")
        print("  ✓ Aktif: Düzeltme Fırsatı (trend içi geri çekilme alımları)")
        print("  ✗ Bloke: Kısa Vade Diamond — bilgi amaçlı aşağıda görüntülenir")
        print("  ✗ Bloke: Orta Vade (tüm tier), Momentum — bilgi amaçlı aşağıda görüntülenir")
    else:
        print(f"  ✅ PİYASA YEŞİL (%{oran:.0f} hisse EMA20 üstü)")
        print("  ✓ Aktif: Kısa Vade Diamond + Ruby (~3-7 gün)")
        print("  ✓ Aktif: Orta Vade Diamond + Fırsat (~3-6 hafta)")
        print("  ✓ Aktif: Düzeltme Fırsatı (trend içi geri çekilme alımları)")


# Vade+Tier etiketleri ve açıklamaları
_VADE_KONFIG = {
    ('Kisa', None):      ('🚀 KISA VADE (3-7 gün)', '~3-7 gün momentum — [⭐ Diamond] en güçlü; [🔶 Ruby] güçlü sinyal'),
    ('Momentum', None):  ('💥 MOMENTUM PATLAMA (Pocket Pivot)', 'Bollinger sıkışması + Pocket Pivot — patlama öncesi birikim  [⚡ Diamond] [🔥 Firsat]'),
    ('Orta', 'Diamond'): ('💎 ORTA VADE DIAMOND', '~3-6 hafta, en güçlü trend — 4+ koşul aynı anda tetiklendi'),
    ('Orta', 'Firsat'):  ('🔵 ORTA VADE FIRSAT',  '~3-6 hafta, trend ile fırsat'),
    ('Duzeltme', 'Firsat'): ('📉 DÜZELTME (PULLBACK)', 'Trend içi geri çekilme — sağlıklı dipten alım'),
}


def gunluk_ozet_raporu():
    print("\n" + "="*55)
    print("📊 BIST AJANI - GÜNLÜK İŞLEM RAPORU")
    print("="*55)
    conn = sqlite3.connect('bist_ajan.db')

    cursor = conn.cursor()
    cursor.execute(
        "SELECT Tarih FROM Hisse_Indikatorleri GROUP BY Tarih HAVING COUNT(Hisse) > 100 ORDER BY Tarih DESC LIMIT 1"
    )
    row = cursor.fetchone()
    son_tarih = row[0] if row else None

    # 1. MEVCUT POZİSYONLAR
    try:
        aktifler = pd.read_sql("SELECT * FROM Aktif_Pozisyonlar", conn)
        print(f"\n💼 AKTİF POZİSYONLAR ({len(aktifler)} adet):")

        if not aktifler.empty and son_tarih:
            hisseler_str = "','".join(aktifler['Hisse'].tolist())
            fiyatlar_df = pd.read_sql(
                f"SELECT Hisse, Kapanis FROM Hisse_Indikatorleri WHERE Tarih='{son_tarih}' AND Hisse IN ('{hisseler_str}')", conn
            )
            fiyat_dict = fiyatlar_df.set_index('Hisse')['Kapanis'].to_dict()

            for _, row in aktifler.iterrows():
                hisse = row['Hisse']
                guncel_fiyat = fiyat_dict.get(hisse, row['Alis_Fiyati'])
                hedef = row['Hedef_Fiyat']
                stop = row['Guncel_Stop_Loss']
                alis = row['Alis_Fiyati']
                k_z = ((guncel_fiyat - alis) / alis) * 100
                hedefe_kalan = ((hedef - guncel_fiyat) / guncel_fiyat) * 100
                stopa_kalan = ((guncel_fiyat - stop) / guncel_fiyat) * 100
                print(f"- {hisse:<8} | Alış: {alis:.2f} | Fiyat: {guncel_fiyat:.2f} (K/Z: %{k_z:.1f})")
                print(f"  └─> Hedef: {hedef:.2f} (Kalan: %{hedefe_kalan:.1f}) | Stop: {stop:.2f} (Uzaklık: %{stopa_kalan:.1f})")
        else:
            print("- Şu an açık pozisyon bulunmuyor.")
    except Exception as e:
        print(f"\n💼 AKTİF POZİSYONLAR: Tablo okunamadı ({e}).")

    # 1.5 GERÇEK PORTFÖY
    print("\n" + "="*55)
    print("💎 GERÇEK PORTFÖY (Aktif İşlemler)")
    print("Açıklama: gercek_islemler.txt dosyasındaki gerçekten alımı yapılmış hisselerinizin performansı.\n")
    try:
        portfoy_dosyasi = "gercek_islemler.txt"
        gercek_portfoy = []
        if os.path.exists(portfoy_dosyasi):
            with open(portfoy_dosyasi, "r", encoding="utf-8") as f:
                for satir in f:
                    satir = satir.strip()
                    if satir and not satir.startswith("#"):
                        p = [x.strip() for x in satir.split(",")]
                        if len(p) >= 4:
                            hisse = p[0].upper()
                            if not hisse.endswith(".IS"):
                                hisse += ".IS"
                            durum = p[6] if len(p) > 6 else "Aktif"
                            if durum != "Aktif":
                                continue
                            gercek_portfoy.append({
                                'hisse': hisse, 'maliyet': float(p[1]),
                                'lot': int(float(p[2])), 'tarih': p[3],
                                'hedef': float(p[4]) if len(p) > 4 else None,
                                'stop': float(p[5]) if len(p) > 5 else None,
                            })

        if gercek_portfoy and son_tarih:
            gercek_hisseler = [p['hisse'] for p in gercek_portfoy]
            gercek_str = "','".join(gercek_hisseler)
            gercek_fiyatlar = pd.read_sql(
                f"SELECT Hisse, Kapanis, ATR_14, RSI_14 FROM Hisse_Indikatorleri WHERE Tarih='{son_tarih}' AND Hisse IN ('{gercek_str}')", conn
            )
            gercek_fiyat_dict = gercek_fiyatlar.set_index('Hisse').to_dict('index')

            toplam_yatirilan = 0
            toplam_guncel = 0

            for p in gercek_portfoy:
                hisse = p['hisse']
                maliyet = p['maliyet']
                lot = p['lot']
                if hisse in gercek_fiyat_dict:
                    guncel = gercek_fiyat_dict[hisse]['Kapanis']
                    rsi = gercek_fiyat_dict[hisse].get('RSI_14', 0)
                    yatirilan = maliyet * lot
                    guncel_tutar = guncel * lot
                    kz_tl = guncel_tutar - yatirilan
                    kz_yuzde = (kz_tl / yatirilan) * 100
                    toplam_yatirilan += yatirilan
                    toplam_guncel += guncel_tutar
                    isaret = "+" if kz_tl > 0 else ""
                    renk = "🟩" if kz_tl > 0 else ("🟥" if kz_tl < 0 else "⬜")
                    hedef_str = f" | Hedef: {p['hedef']:.2f}" if p.get('hedef') else ""
                    stop_str = f" | Stop: {p['stop']:.2f}" if p.get('stop') else ""
                    print(f"  - {hisse.replace('.IS',''):<8} | {lot} Lot | Maliyet: {maliyet:.2f} -> Güncel: {guncel:.2f} | K/Z: {isaret}{kz_tl:.2f} ₺ ({isaret}%{kz_yuzde:.1f}) {renk}")
                    print(f"    └─ RSI: {rsi:.1f}{hedef_str}{stop_str}")

            genel_kz = toplam_guncel - toplam_yatirilan
            genel_yuzde = (genel_kz / toplam_yatirilan) * 100 if toplam_yatirilan > 0 else 0
            g_isaret = "+" if genel_kz > 0 else ""
            g_renk = "🟩" if genel_kz > 0 else "🟥"
            print(f"\n  💰 TOPLAM: Yatırılan: {toplam_yatirilan:.2f} ₺ | Güncel: {toplam_guncel:.2f} ₺ | Net: {g_isaret}{genel_kz:.2f} ₺ ({g_isaret}%{genel_yuzde:.1f}) {g_renk}")
        else:
            print("  - Aktif gerçek işlem bulunmuyor.")
    except Exception as e:
        print(f"  - Gerçek portföy okunamadı: {e}")

    # 2. PİYASA DURUMU (Market Breadth — stratejilerin neden aktif/bloke olduğunu açıklar)
    try:
        if son_tarih:
            piyasa = _piyasa_durumu_hesapla(conn, son_tarih)
            _yazdir_piyasa_durumu(piyasa)
    except Exception as e:
        print(f"\n  - Piyasa durumu hesaplanamadı: {e}")

    # 2.5 DRAWDOWN UYARISI (Son 10 algoritmik işlemde 6+ kayıp)
    try:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Islem_Gecmisi'"
        )
        if cursor.fetchone():
            son_islemler = pd.read_sql(
                "SELECT Kar_Zarar_Yuzdesi FROM Islem_Gecmisi ORDER BY Satis_Tarihi DESC LIMIT 10",
                conn
            )
            if len(son_islemler) >= 5:
                kayip_sayisi = int((son_islemler['Kar_Zarar_Yuzdesi'] < 0).sum())
                toplam = len(son_islemler)
                if kayip_sayisi >= 6:
                    print("\n" + "!" * 55)
                    print("  ⚠️  DRAWDOWN UYARISI")
                    print(f"  Son {toplam} işlemde {kayip_sayisi} kayıp (%{kayip_sayisi/toplam*100:.0f})")
                    print("  Sistem kötü bir dönemde. Yeni pozisyon açmadan önce")
                    print("  piyasa koşullarını manuel olarak değerlendirin.")
                    print("!" * 55)
    except Exception:
        pass

    # 3. AL SİNYALLERİ (Puanlama sistemi)
    ps_cfg = _load_ps_cfg()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Gunluk_Sinyaller'")
        if cursor.fetchone() and son_tarih:
            sorgu = f"""
                SELECT s.*, i.RSI_14, i.ADX_14, i.Stoch_K, i.MACD, i.MACD_Signal, i.RS_63
                FROM Gunluk_Sinyaller s
                JOIN Hisse_Indikatorleri i ON s.Hisse = i.Hisse AND s.Tarih = i.Tarih
                WHERE s.Tarih='{son_tarih}' AND (s.Bloke IS NULL OR s.Bloke = 0)
                ORDER BY s.Puan DESC
            """
            sinyaller = pd.read_sql(sorgu, conn)

            print("\n" + "="*55)
            print("🎯 GÜNÜN AL SİNYALLERİ")
            print("Açıklama: Puanlama sistemiyle seçilen en iyi fırsatlar. Tier = sinyal gücü.\n")

            if not sinyaller.empty:
                gosterilen = False
                for (vade, tier), (baslik, aciklama) in _VADE_KONFIG.items():
                    if tier is None:
                        # Merged: show Diamond + Ruby in one list, sorted by Puan DESC
                        grup = sinyaller[sinyaller['Vade'] == vade].sort_values('Puan', ascending=False)
                    else:
                        strateji_key = f"{vade}_{tier}"
                        grup = sinyaller[sinyaller['Strateji'] == strateji_key]
                    if grup.empty:
                        continue
                    gosterilen = True
                    print(f"  {baslik}")
                    print(f"  ({aciklama})")
                    for _, row in grup.iterrows():
                        fk, pddd = temel_verileri_getir(row['Hisse'])
                        fk_str = f"{fk:.1f}" if fk else "Yok/Zarar"
                        pddd_str = f"{pddd:.1f}" if pddd else "Yok"
                        temel_uyari = " ⚠️ PAHALI" if ((fk and fk > 30) or (pddd and pddd > 10)) else ""
                        puan_val = int(row['Puan']) if 'Puan' in row.index and not pd.isna(row['Puan']) else 0
                        yildiz = "⭐" * int(min(5, max(1, row['Potansiyel_Getiri'] // 6)))
                        macd_durum = "AL" if row['MACD'] > row['MACD_Signal'] else "SAT"
                        try:
                            rs63_str = f"{float(row['RS_63']):+.1f}%"
                        except (KeyError, TypeError, ValueError):
                            rs63_str = "N/A"
                        # Tier badge for merged list
                        if tier is None:
                            row_tier = str(row.get('Tier', '')) if hasattr(row, 'get') else ''
                            row_vade2 = str(row.get('Vade', vade)) if hasattr(row, 'get') else vade
                            if row_vade2 == 'Momentum':
                                tier_badge = "⚡ " if row_tier == 'Diamond' else "🔥 "
                            else:
                                tier_badge = "⭐ " if row_tier == 'Diamond' else "🔶 "
                            tier_hint  = f" [{row_tier}]" if row_tier else ""
                        else:
                            row_vade2  = vade
                            tier_badge = ""
                            tier_hint  = ""
                        partial = row.get('Partial_Cikis') if hasattr(row, 'get') else getattr(row, 'Partial_Cikis', None)
                        _has_partial = bool(partial and not pd.isna(partial))
                        # Kısmi çıkış sadece Momentum için (backtest: Kisa/Orta'da PF düşürüyor)
                        partial_str = f" | 🔶 K.Çıkış: {partial:.2f}" if (row_vade2 == 'Momentum' and _has_partial) else ""
                        lot_val, sermaye_val = _hesapla_lot(row['Kapanis'], row['Stop_Loss'], ps_cfg)
                        lot_str = f" | 📊 {lot_val} lot (₺{int(sermaye_val):,})" if lot_val else ""
                        print(f"  - AL -> {tier_badge}{row['Hisse'].replace('.IS',''):<8} | Fiyat: {row['Kapanis']:.2f} | Stop: {row['Stop_Loss']:.2f}{partial_str} | Hedef: {row['Hedef_Fiyat']:.2f} (Pot: %{row['Potansiyel_Getiri']:.1f} {yildiz}) | Puan: {puan_val}{tier_hint}{temel_uyari}{lot_str}")
                        print(f"    └─ RSI: {row['RSI_14']:.1f} | ADX: {row['ADX_14']:.1f} | StochK: {row['Stoch_K']:.1f} | MACD: {macd_durum} | RS63: {rs63_str} | F/K: {fk_str} | PD/DD: {pddd_str}")
                        if row_vade2 == 'Momentum' and _has_partial:
                            print(f"    └─ 💡 {partial:.2f} ₺'de stop tıkıştır ya da %50 kısmi çıkış (12ay: WR ↑ %47.9→%58.7, PF ↓ 1.43→1.07)")
                        elif row_vade2 == 'Orta':
                            print(f"    └─ 💡 Sabırla bekle (~16-17 gün). Stop sıkma — kaybedenlerin %30'u hedefe yaklaşıp döndü")
                        elif row_vade2 == 'Kisa':
                            print(f"    └─ 💡 Tam hedefte çık. Kısmi çıkış bu vadede avantaj sağlamaz (ort. 3-7 gün)")
                    print("")
                if not gosterilen:
                    print("- Bugün yeterli puana ulaşan hisse bulunamadı. (Nakitte bekle)")
            else:
                print("- Bugün yeterli puana ulaşan hisse bulunamadı. (Nakitte bekle)")
    except Exception as e:
        print(f"\n🎯 AL SİNYALLERİ: Okunamadı. {e}")

    # 3b. BLOKE SİNYALLER (Bilgi Amaçlı)
    try:
        cursor.execute("SELECT name FROM pragma_table_info('Gunluk_Sinyaller') WHERE name='Bloke'")
        if cursor.fetchone() and son_tarih:
            bloke_sorgu = f"""
                SELECT s.*, i.RSI_14, i.ADX_14, i.Stoch_K, i.MACD, i.MACD_Signal, i.RS_63
                FROM Gunluk_Sinyaller s
                JOIN Hisse_Indikatorleri i ON s.Hisse = i.Hisse AND s.Tarih = i.Tarih
                WHERE s.Tarih='{son_tarih}' AND s.Bloke = 1
                ORDER BY s.Puan DESC
            """
            bloke_df = pd.read_sql(bloke_sorgu, conn)
            if not bloke_df.empty:
                print("\n" + "="*55)
                print("⚠️  BLOKE SİNYALLER — BİLGİ AMAÇLI (ZAYIF PİYASADA)")
                print("İşlem önerilmez. Piyasa güçlenirse yeniden değerlendirin.\n")
                for (vade, tier), (baslik, _) in _VADE_KONFIG.items():
                    if tier is None:
                        grup = bloke_df[bloke_df['Vade'] == vade].sort_values('Puan', ascending=False)
                    else:
                        strateji_key = f"{vade}_{tier}"
                        grup = bloke_df[bloke_df['Strateji'] == strateji_key]
                    if grup.empty:
                        continue
                    print(f"  {baslik}")
                    for _, row in grup.iterrows():
                        puan_val = int(row['Puan']) if 'Puan' in row.index and not pd.isna(row['Puan']) else 0
                        yildiz = "⭐" * int(min(5, max(1, row['Potansiyel_Getiri'] // 6)))
                        macd_durum = "AL" if row['MACD'] > row['MACD_Signal'] else "SAT"
                        if tier is None:
                            row_tier = str(row.get('Tier', '')) if hasattr(row, 'get') else ''
                            tier_badge = "⭐ " if row_tier == 'Diamond' else "🔶 "
                            tier_hint  = f" [{row_tier}]"
                        else:
                            tier_badge = ""
                            tier_hint  = ""
                        try:
                            rs63_str = f"{float(row['RS_63']):+.1f}%"
                        except (KeyError, TypeError, ValueError):
                            rs63_str = "N/A"
                        print(f"  - ⛔ {tier_badge}{row['Hisse'].replace('.IS',''):<8} | Fiyat: {row['Kapanis']:.2f} | Stop: {row['Stop_Loss']:.2f} | Hedef: {row['Hedef_Fiyat']:.2f} (Pot: %{row['Potansiyel_Getiri']:.1f} {yildiz}) | Puan: {puan_val}{tier_hint}")
                        print(f"    └─ RSI: {row['RSI_14']:.1f} | ADX: {row['ADX_14']:.1f} | StochK: {row['Stoch_K']:.1f} | MACD: {macd_durum} | RS63: {rs63_str}")
                    print("")
    except Exception:
        pass

    # 4. TEKNİK ÖNERİ ÖZETİ
    print("\n" + "="*55)
    print("📋 TEKNİK ÖNERİ ÖZETİ (Sinyal Motorundan)")
    print("Açıklama: Strateji bazında en yüksek puanlı ilk 3 hisse.\n")
    try:
        oneri_df = pd.read_sql(
            f"SELECT Hisse, Strateji, Kapanis, Hedef_Fiyat, Stop_Loss, Potansiyel_Getiri, Puan FROM Gunluk_Sinyaller WHERE Tarih='{son_tarih}' AND (Bloke IS NULL OR Bloke = 0) ORDER BY Puan DESC",
            conn
        )
        if not oneri_df.empty:
            for (vade, tier), (baslik, _) in _VADE_KONFIG.items():
                if tier is None:
                    grup = oneri_df[oneri_df['Vade'] == vade].head(3)
                    tier_col = True
                else:
                    strateji_key = f"{vade}_{tier}"
                    grup = oneri_df[oneri_df['Strateji'] == strateji_key].head(3)
                    tier_col = False
                if not grup.empty:
                    ozet = " | ".join([
                        f"{'💎' if tier_col and str(r.get('Tier',''))=='Diamond' else ('🔴' if tier_col else '')}"
                        f"{r['Hisse'].replace('.IS','')}: %{r['Potansiyel_Getiri']:.0f} ({int(r['Puan'])}p)"
                        for _, r in grup.iterrows()
                    ])
                    print(f"  {baslik}: {ozet}")
        else:
            print("  - Henüz teknik öneri üretilmedi.")
    except Exception as e:
        print(f"  - Teknik öneri tablosu okunamadı: {e}")

    # 5. RADARDAKİLER (Watchlist)
    print("\n" + "="*55)
    print("👀 RADARDAKİLER (Henüz AL Sinyali Yok - Sadece İzleyin)")
    print("Açıklama: Tam sinyal üretmeyen ama yakın takipteki hisseler.\n")
    try:
        watchlist_df = pd.read_sql(f'''
            SELECT Hisse, Kapanis, RSI_14, MACD, MACD_Signal, BB_Ust, BB_Alt, ATR_14, ADX_14, Stoch_K
            FROM Hisse_Indikatorleri
            WHERE Tarih = '{son_tarih}'
            AND Kapanis > EMA_200
            AND RSI_14 BETWEEN 45 AND 60
            AND MACD > MACD_Signal
            AND Hacim_TL > 10000000
            ORDER BY RSI_14 ASC LIMIT 5
        ''', conn)

        if not watchlist_df.empty:
            for _, row in watchlist_df.iterrows():
                fk, pddd = temel_verileri_getir(row['Hisse'])
                fk_str = f"{fk:.1f}" if fk else "Yok/Zarar"
                pddd_str = f"{pddd:.1f}" if pddd else "Yok"
                direnc = row['BB_Ust']
                destek = row['BB_Alt']
                macd_durum = "AL" if row['MACD'] > row['MACD_Signal'] else "SAT"
                print(f"- {row['Hisse']:<8} | Fiyat: {row['Kapanis']:<5.2f} | Direnç: {direnc:.2f} | Destek: {destek:.2f} | Hedef Marjı: %{((direnc-row['Kapanis'])/row['Kapanis'])*100:.1f}")
                print(f"  └─ RSI: {row['RSI_14']:.1f} | MACD: {macd_durum} | F/K: {fk_str} | PD/DD: {pddd_str}")
        else:
            print("- İzleme listesine uygun hisse bulunamadı.")
    except Exception as e:
        print(f"- İzleme listesi verisi okunamadı: {e}")

    print("\n" + "-"*55)
    print("💡 İNDİKATÖR REHBERİ:")
    print("  - RSI (30-70): 50 üzeri pozitif, 70 üzeri aşırı alım, 30 altı aşırı satım.")
    print("  - ADX (>25): Trendin gücünü gösterir. 25 üzerindeyse trend çok güçlüdür.")
    print("  - StochK (0-100): 20 altından yukarı kesmesi AL, 80 üstünden aşağı kesmesi SAT.")
    print("  - MACD: AL vermesi yükseliş ivmesinin başladığını/korunduğunu gösterir.")
    print("  - Puan: Sinyal kalitesi 0-100. Diamond ≥ 80, Fırsat ≥ 50.")
    print("="*55 + "\n")
    conn.close()


if __name__ == "__main__":
    gunluk_ozet_raporu()
