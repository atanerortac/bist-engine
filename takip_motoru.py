import json
import sqlite3
import pandas as pd
import os
from datetime import datetime
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
from strategy_engine import (
    hesapla_kisa_vade_puan, hesapla_orta_vade_puan,
    hesapla_duzeltme_puan, hesapla_momentum_patlama_puan,
)


def _v(row, col):
    try:
        val = row[col]
        return float(val) if val is not None and not pd.isna(val) else None
    except (KeyError, TypeError, ValueError):
        return None


def _teknik_skor_hesapla(row):
    kisa = hesapla_kisa_vade_puan(row)
    orta = hesapla_orta_vade_puan(row)
    return kisa, orta


def _skor_badge(puan):
    if puan >= 80:
        return f"💎 Diamond ({puan})"
    elif puan >= 50:
        return f"🔵 Fırsat ({puan})"
    else:
        return f"⚠️ Zayıf ({puan})"


def _skor_renk(puan):
    if puan >= 80:
        return '#f0c040'
    elif puan >= 50:
        return '#58a6ff'
    else:
        return '#8b949e'


def _risk_badge_olustur(bugun_k, dun_k, dinamik_hedef):
    badges = []
    rsi = _v(bugun_k, 'RSI_14')
    stoch_k_b = _v(bugun_k, 'Stoch_K')
    stoch_d_b = _v(bugun_k, 'Stoch_D')
    stoch_k_d = _v(dun_k, 'Stoch_K')
    macd_hist_b = _v(bugun_k, 'MACD_Hist')
    macd_hist_d = _v(dun_k, 'MACD_Hist')
    kapanis = _v(bugun_k, 'Kapanis')
    ema20 = _v(bugun_k, 'EMA_20')
    if rsi and rsi > 72:
        badges.append('⚠️ RSI Aşırı Alım')
    if stoch_k_d and stoch_k_b and stoch_d_b and stoch_k_d > 80 and stoch_k_b < stoch_d_b:
        badges.append('⚠️ Stokastik Çapraz')
    if macd_hist_b is not None and macd_hist_d is not None and macd_hist_b < macd_hist_d:
        badges.append('⚠️ MACD Zayıflıyor')
    if kapanis and ema20 and kapanis < ema20:
        badges.append('⚠️ EMA20 Kırıldı')
    if kapanis and dinamik_hedef and kapanis >= dinamik_hedef * 0.95:
        badges.append('⚠️ Hedefe Yakın')
    return badges


def algoritmik_yorum_uret(bugun, dun, maliyet=None):
    # Fiyat, hacim ve MACD'ye bakarak yorum üretir
    hacim_artti_mi = bugun['Hacim_TL'] > dun['Hacim_TL']
    fiyat_artti_mi = bugun['Kapanis'] > dun['Kapanis']
    macd_pozitif = bugun['MACD'] > bugun['MACD_Signal']
    macd_kesisti_mi = macd_pozitif and (dun['MACD'] <= dun['MACD_Signal'])
    rsi_sisti_mi = bugun['RSI_14'] > 70
    rsi_diplendi_mi = bugun['RSI_14'] < 30
    trend_ustu = bugun['Kapanis'] > bugun['EMA_20']
    
    karar = "İZLE / BEKLE"
    yorum = "Yatay/Belirsiz seyir, momentum aranıyor ⏳"
    
    if macd_kesisti_mi and trend_ustu and hacim_artti_mi:
        karar = "AL / EKLE"
        yorum = "Para girişli yükseliş, MACD AL verdi. Yeni trend başlıyor olabilir 🚀"
    elif fiyat_artti_mi and hacim_artti_mi and trend_ustu:
        karar = "TUT / ALMAYA DEVAM"
        yorum = "Hacimli yükseliş, trend gücünü koruyor 🟩"
    elif rsi_sisti_mi and not macd_pozitif:
        karar = "KAR AL / KISMEN SAT"
        yorum = "Fiyat aşırı alım bölgesinde yoruluyor, kar satışları makul olabilir ⚠️"
    elif not trend_ustu and not macd_pozitif and not fiyat_artti_mi:
        karar = "SAT / STOP OL"
        yorum = "Trend desteği (EMA20) kırıldı ve MACD zayıf, satıcılar baskın 🟥"
    elif not fiyat_artti_mi and macd_pozitif and trend_ustu:
        karar = "TUT"
        yorum = "Fiyat düşüyor ama trend ve MACD hala pozitif, basit bir düzeltme (pullback) 📉"
    elif rsi_diplendi_mi and macd_kesisti_mi:
        karar = "DİPTEN TOPLA"
        yorum = "Aşırı satım bölgesinden dönüş sinyali geldi, dip avı için uygun 🎯"
        
    if maliyet is not None:
        zarar_yuzdesi = ((bugun['Kapanis'] - maliyet) / maliyet) * 100
        if zarar_yuzdesi < -10.0 and karar not in ["SAT / STOP OL", "ZARAR KES"]:
            karar = "ZARAR KES (STOP)"
            yorum = f"Maliyetin %10 altına inildi! Teknik dönüş yoksa stop olmak güvenlidir 🛑. ({yorum})"
            
    return f"**[KARAR: {karar}]** {yorum}"

def takip_raporu_olustur():
    ps_cfg = _load_ps_cfg()
    print("📝 Takip Motoru: İzleme listesi ve Gerçek Portföy raporlanıyor...")
    
    # 1. İzleme Listesi (Radar)
    hisseler_dosyasi = "benim_hisselerim.txt"
    izleme_listesi = []
    
    if os.path.exists(hisseler_dosyasi):
        with open(hisseler_dosyasi, "r", encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if satir and not satir.startswith("#"):
                    p = [x.strip() for x in satir.split(",")]
                    hisse = p[0].upper()
                    if not hisse.endswith(".IS"):
                        hisse += ".IS"
                    maliyet = float(p[1]) if len(p) > 1 else None
                    lot = int(float(p[2])) if len(p) > 2 else None
                    tarih = p[3] if len(p) > 3 else None
                    izleme_listesi.append({
                        'hisse': hisse,
                        'maliyet': maliyet,
                        'lot': lot,
                        'tarih': tarih
                    })
                    
    # 2. Gerçek Portföy
    portfoy_dosyasi = "gercek_islemler.txt"
    gercek_portfoy = []
    baslangic_sermaye = None

    if os.path.exists(portfoy_dosyasi):
        with open(portfoy_dosyasi, "r", encoding="utf-8") as f:
            for satir in f:
                satir = satir.strip()
                if satir.startswith("# BASLANGIC_SERMAYE="):
                    try:
                        baslangic_sermaye = float(satir.split("=")[1].strip())
                    except Exception:
                        pass
                    continue
                if satir and not satir.startswith("#"):
                    p = [x.strip() for x in satir.split(",")]
                    if len(p) >= 4:
                        hisse = p[0].upper()
                        if not hisse.endswith(".IS"):
                            hisse += ".IS"
                        gercek_portfoy.append({
                            'hisse': hisse,
                            'maliyet': float(p[1]),
                            'lot': int(float(p[2])),
                            'tarih': p[3],
                            'hedef': float(p[4]) if len(p) > 4 else None,
                            'stop': float(p[5]) if len(p) > 5 else None,
                            'durum': p[6] if len(p) > 6 else "Aktif",
                            'satis_fiyati': float(p[7]) if len(p) > 7 else None,
                            'satis_tarihi': p[8] if len(p) > 8 else None
                        })

    aktif_portfoy = [x for x in gercek_portfoy if x['durum'] == 'Aktif']
    kapali_islemler = [x for x in gercek_portfoy if x['durum'] == 'Satıldı' and x['satis_fiyati'] is not None]
    tum_hisseler = list(set([x['hisse'] for x in izleme_listesi] + [x['hisse'] for x in aktif_portfoy]))
    
    conn = sqlite3.connect('bist_ajan.db')
    tarih_df = pd.read_sql("SELECT Tarih FROM Hisse_Indikatorleri GROUP BY Tarih HAVING COUNT(Hisse) > 100 ORDER BY Tarih DESC LIMIT 3", conn)

    if len(tarih_df) < 2:
        print("⚠️ Takip motoru için yeterli geçmiş gün verisi yok.")
        conn.close()
        return

    bugun_tarih = tarih_df.iloc[0]['Tarih']
    dun_tarih = tarih_df.iloc[1]['Tarih']
    evvelsi_tarih = tarih_df.iloc[2]['Tarih'] if len(tarih_df) >= 3 else None
    
    hisseler_str = "','".join(tum_hisseler)
    bugun_veriler = pd.read_sql(f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih='{bugun_tarih}' AND Hisse IN ('{hisseler_str}')", conn).set_index('Hisse')
    dun_veriler = pd.read_sql(f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih='{dun_tarih}' AND Hisse IN ('{hisseler_str}')", conn).set_index('Hisse')
    
    rapor_icerigi = f"# 📅 PORTFÖY VE İZLEME RAPORU ({bugun_tarih})\n\n"
    
    html_body = f"<h1>📅 PORTFÖY VE İZLEME RAPORU ({bugun_tarih})</h1>"
    
    # ---------------- BÖLÜM 1: GERÇEK PORTFÖY ----------------
    rapor_icerigi += "## 💼 GERÇEK PORTFÖY VE K/Z DURUMU\n"
    rapor_icerigi += "> Açıklama: Gerçekten alımı yapılan hisselerinizin performansı ve güncel durumu.\n\n"
    
    html_body += "<h2>💼 GERÇEK PORTFÖY VE K/Z DURUMU</h2>"
    html_body += "<blockquote>Açıklama: Gerçekten alımı yapılan hisselerinizin performansı ve güncel durumu.</blockquote>"
    html_body += "<div class='grid-container'>"
    
    toplam_maliyet_tl = 0
    toplam_guncel_tl = 0
    
    if aktif_portfoy:
        for p in aktif_portfoy:
            hisse = p['hisse']
            maliyet = p['maliyet']
            lot = p['lot']
            durum = p['durum']
            
            if hisse in bugun_veriler.index and hisse in dun_veriler.index:
                bugun_k = bugun_veriler.loc[hisse]
                dun_k = dun_veriler.loc[hisse]
                kapanis = bugun_k['Kapanis']
                atr = bugun_k['ATR_14']
                
                # Dinamik Hedef / Stop (Güncel ATR'ye Göre)
                dinamik_hedef = kapanis + (3.0 * atr)
                hesaplanan_dinamik_stop = kapanis - (1.5 * atr)
                # Maksimum risk kuralı (Sinyal motoruyla aynı: %15'ten fazla stop yazılamaz)
                dinamik_stop = max(hesaplanan_dinamik_stop, kapanis * 0.85)
                
                # Trailing Stop Düzeltmesi: Dinamik stop, orijinal stoptan daha düşük olamaz!
                if p.get('stop'):
                    dinamik_stop = max(float(p['stop']), dinamik_stop)
                
                # Kar zarar hesapları
                yatirilan = maliyet * lot
                guncel_tutar = kapanis * lot
                kar_zarar_tl = guncel_tutar - yatirilan
                kar_zarar_yuzde = (kar_zarar_tl / yatirilan) * 100
                
                toplam_maliyet_tl += yatirilan
                toplam_guncel_tl += guncel_tutar
                
                isaret = "+" if kar_zarar_tl > 0 else ""
                renk = "🟩" if kar_zarar_tl > 0 else ("🟥" if kar_zarar_tl < 0 else "⬜")
                html_renk = "#3fb950" if kar_zarar_tl > 0 else ("#f85149" if kar_zarar_tl < 0 else "#c9d1d9")
                
                gunluk_degisim = ((kapanis - dun_k['Kapanis']) / dun_k['Kapanis']) * 100
                g_isaret = "+" if gunluk_degisim > 0 else ""
                
                yorum = algoritmik_yorum_uret(bugun_k, dun_k, maliyet)
                kisa_skor, orta_skor = _teknik_skor_hesapla(bugun_k)
                risk_badges = _risk_badge_olustur(bugun_k, dun_k, dinamik_hedef)

                fk, pddd = temel_verileri_getir(hisse)
                fk_str = f"{fk:.1f}" if fk else "Yok"
                pddd_str = f"{pddd:.1f}" if pddd else "Yok"
                try:
                    rs63_str = f"{float(bugun_k['RS_63']):+.1f}%"
                except (KeyError, TypeError, ValueError):
                    rs63_str = "N/A"

                try:
                    gun_tutulan = (datetime.strptime(bugun_tarih, "%Y-%m-%d") - datetime.strptime(p['tarih'], "%Y-%m-%d")).days
                    gun_tutulan_str = f"{gun_tutulan} gün"
                except Exception:
                    gun_tutulan_str = "?"

                hedef_uzaklik = ((dinamik_hedef - kapanis) / kapanis) * 100
                stop_uzaklik = ((dinamik_stop - kapanis) / kapanis) * 100

                border_class = "border-neutral"
                if len(risk_badges) >= 2:
                    border_class = "border-risk"
                elif "KARAR: AL" in yorum or "EKLE" in yorum:
                    border_class = "border-al"
                elif "KARAR: SAT" in yorum or "ZARAR KES" in yorum:
                    border_class = "border-sat"
                elif "KARAR: TUT" in yorum or "KAR AL" in yorum:
                    border_class = "border-tut"
                elif "DİPTEN TOPLA" in yorum:
                    border_class = "border-dip"

                # Markdown Ekle
                rapor_icerigi += f"- **{hisse.replace('.IS', '')}** ({durum}) | {lot} Lot\n"
                rapor_icerigi += f"  - Maliyet: {maliyet:.2f} ₺ -> Güncel: {kapanis:.2f} ₺ (Günlük: {g_isaret}%{gunluk_degisim:.2f})\n"
                if p['hedef'] and p['stop']:
                    rapor_icerigi += f"  - **İlk Plan:** Hedef {p['hedef']} ₺ | Stop {p['stop']} ₺\n"
                rapor_icerigi += f"  - **Güncel Dinamik:** Hedef {dinamik_hedef:.2f} ₺ (+%{hedef_uzaklik:.1f}) | Stop {dinamik_stop:.2f} ₺ (%{stop_uzaklik:.1f})\n"
                rapor_icerigi += f"  - **Net K/Z:** {isaret}{kar_zarar_tl:.2f} ₺ ({isaret}%{kar_zarar_yuzde:.2f}) {renk}\n"
                rapor_icerigi += f"  - **Teknik ve Temel:** RSI: {bugun_k['RSI_14']:.1f} | RS63: {rs63_str} | F/K: {fk_str} | PD/DD: {pddd_str}\n"
                rapor_icerigi += f"  - **Teknik Skor:** Kısa {_skor_badge(kisa_skor)} | Orta {_skor_badge(orta_skor)}\n"
                if risk_badges:
                    rapor_icerigi += f"  - **Risk:** {' | '.join(risk_badges)}\n"
                rapor_icerigi += f"  - Algoritmik Yorum: {yorum}\n\n"

                risk_html = ""
                if risk_badges:
                    badges_html = " ".join(
                        f"<span style='background:#d2992222;color:#d29922;border:1px solid #d2992244;padding:2px 8px;border-radius:8px;font-size:0.78em;'>{b}</span>"
                        for b in risk_badges
                    )
                    risk_html = f"<div style='margin-top:8px;display:flex;gap:4px;flex-wrap:wrap;'>{badges_html}</div>"
                    risk_html += "<div style='margin-top:6px;font-size:0.78em;color:#8b949e;font-style:italic;'>Risk uyarıları çıkış sinyali DEĞİLDİR. Stop-loss birincil korunmanızdır.</div>"

                # HTML Ekle
                html_body += f"""
                <div class='card {border_class}'>
                    <div class='card-title'><strong>{hisse.replace('.IS', '')}</strong> <span>({durum}) | {lot} Lot | {gun_tutulan_str}</span></div>
                    <div class='card-content'>
                        <div>Maliyet: <strong>{maliyet:.2f} ₺</strong></div>
                        <div>Güncel: <strong>{kapanis:.2f} ₺</strong> <span style="color:#8b949e; font-size:0.9em">(Günlük: {g_isaret}%{gunluk_degisim:.2f})</span></div>
                """
                if p['hedef'] and p['stop']:
                    html_body += f"<div style='color:#d29922; font-size:0.9em; margin-top:4px;'>İlk Plan: Hedef <strong>{p['hedef']} ₺</strong> | Stop <strong>{p['stop']} ₺</strong></div>"
                html_body += f"""
                        <div style='color:#58a6ff; font-size:0.9em;'>Güncel: Hedef <strong>{dinamik_hedef:.2f} ₺</strong> <span style='color:#3fb950;'>(+%{hedef_uzaklik:.1f})</span> | Stop <strong>{dinamik_stop:.2f} ₺</strong> <span style='color:#f85149;'>(%{stop_uzaklik:.1f})</span></div>
                        <div style='margin-top:8px; padding-top:8px; border-top:1px solid #30363d;'>
                            Net K/Z: <strong style='color:{html_renk}'>{isaret}{kar_zarar_tl:.2f} ₺ ({isaret}%{kar_zarar_yuzde:.2f})</strong>
                        </div>
                        <div style='margin-top:8px; font-size:0.85em; color:#8b949e;'>Teknik: RSI: {bugun_k['RSI_14']:.1f} | RS63: {rs63_str} | F/K: {fk_str} | PD/DD: {pddd_str}</div>
                        <div style='margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;'>
                            <span style='background:{_skor_renk(kisa_skor)}22;color:{_skor_renk(kisa_skor)};border:1px solid {_skor_renk(kisa_skor)}44;padding:2px 8px;border-radius:8px;font-size:0.8em;'>Kısa: {_skor_badge(kisa_skor)}</span>
                            <span style='background:{_skor_renk(orta_skor)}22;color:{_skor_renk(orta_skor)};border:1px solid {_skor_renk(orta_skor)}44;padding:2px 8px;border-radius:8px;font-size:0.8em;'>Orta: {_skor_badge(orta_skor)}</span>
                        </div>
                        {risk_html}
                        <div class='card-comment'>{yorum.replace('**', '')}</div>
                    </div>
                </div>
                """

        # Toplam K/Z
        genel_kz_tl = toplam_guncel_tl - toplam_maliyet_tl
        genel_kz_yuzde = (genel_kz_tl / toplam_maliyet_tl) * 100 if toplam_maliyet_tl > 0 else 0
        g_isaret = "+" if genel_kz_tl > 0 else ""
        g_renk = "🟩" if genel_kz_tl > 0 else "🟥"
        g_html_renk = "#3fb950" if genel_kz_tl > 0 else "#f85149"

        # Başlangıç sermayesine göre net getiri (açık + gerçekleşen)
        toplam_gerceklesen = sum((x['satis_fiyati'] - x['maliyet']) * x['lot'] for x in kapali_islemler)
        net_getiri_tl = genel_kz_tl + toplam_gerceklesen
        net_getiri_md = ""
        net_getiri_html = ""
        if baslangic_sermaye:
            net_getiri_yuzde = (net_getiri_tl / baslangic_sermaye) * 100
            n_isaret = "+" if net_getiri_tl >= 0 else ""
            n_renk = "#3fb950" if net_getiri_tl >= 0 else "#f85149"
            net_getiri_md = f"- Başlangıç Sermayesi: **{baslangic_sermaye:.2f} ₺**\n- **NET GETİRİ (Gerçekleşen+Açık):** {n_isaret}{net_getiri_tl:.2f} ₺ ({n_isaret}%{net_getiri_yuzde:.2f})\n"
            net_getiri_html = f"""
            <div style='margin-top:10px;padding-top:10px;border-top:1px solid #30363d;'>
                Başlangıç Sermayesi: <strong>{baslangic_sermaye:.2f} ₺</strong>
            </div>
            <div style='font-size:1.05em;margin-top:4px;'>
                Net Getiri: <strong style='color:{n_renk}'>{n_isaret}{net_getiri_tl:.2f} ₺ ({n_isaret}%{net_getiri_yuzde:.2f})</strong>
            </div>"""

        rapor_icerigi += f"### 💰 TOPLAM PORTFÖY DURUMU\n"
        rapor_icerigi += f"- Aktif Pozisyonlara Yatırılan: **{toplam_maliyet_tl:.2f} ₺**\n"
        rapor_icerigi += f"- Güncel Piyasa Değeri: **{toplam_guncel_tl:.2f} ₺**\n"
        rapor_icerigi += f"- **Açık K/Z:** {g_isaret}{genel_kz_tl:.2f} ₺ ({g_isaret}%{genel_kz_yuzde:.2f}) {g_renk}\n"
        rapor_icerigi += net_getiri_md + "\n"

        html_body += f"""
        </div>
        <div class='summary-box'>
            <h3>💰 TOPLAM PORTFÖY DURUMU</h3>
            <div>Aktif Yatırılan: <strong>{toplam_maliyet_tl:.2f} ₺</strong></div>
            <div>Güncel Piyasa Değeri: <strong>{toplam_guncel_tl:.2f} ₺</strong></div>
            <div style='margin-top:8px; font-size:1.05em;'>
                Açık K/Z: <strong style='color:{g_html_renk}'>{g_isaret}{genel_kz_tl:.2f} ₺ ({g_isaret}%{genel_kz_yuzde:.2f})</strong>
            </div>
            {net_getiri_html}
        </div>
        """
    else:
        rapor_icerigi += "*Aktif pozisyonunuz bulunmuyor.*\n\n"
        html_body += "<p><em>Aktif pozisyonunuz bulunmuyor.</em></p></div>"
        

    # ---------------- BÖLÜM 1b: KAPATILAN İŞLEMLER ----------------
    if kapali_islemler:
        from datetime import datetime

        rapor_icerigi += "## 📒 KAPATILAN İŞLEMLER (Gerçekleşen K/Z)\n"
        rapor_icerigi += "> Açıklama: Satışı tamamlanan pozisyonların gerçekleşen kâr/zarar özeti.\n\n"

        html_body += "<h2>📒 KAPATILAN İŞLEMLER (Gerçekleşen K/Z)</h2>"
        html_body += "<blockquote>Açıklama: Satışı tamamlanan pozisyonların gerçekleşen kâr/zarar özeti.</blockquote>"
        html_body += "<div class='grid-container'>"

        toplam_gerceklesen_kz = 0
        kapali_kazanc_listesi = []

        for p in kapali_islemler:
            hisse = p['hisse']
            alis = p['maliyet']
            satis = p['satis_fiyati']
            lot = p['lot']
            alis_tarihi = p['tarih']
            satis_tarihi = p['satis_tarihi']

            kz_tl = (satis - alis) * lot
            kz_yuzde = ((satis / alis) - 1) * 100
            toplam_gerceklesen_kz += kz_tl
            kapali_kazanc_listesi.append(kz_yuzde)

            isaret = "+" if kz_tl >= 0 else ""
            html_renk = "#3fb950" if kz_tl >= 0 else "#f85149"
            border_class = "border-al" if kz_tl >= 0 else "border-sat"
            rozet = "✅ KAZANÇ" if kz_tl >= 0 else "❌ ZARAR"
            rozet_renk = "#3fb950" if kz_tl >= 0 else "#f85149"

            try:
                gun_fark = (datetime.strptime(satis_tarihi, "%Y-%m-%d") - datetime.strptime(alis_tarihi, "%Y-%m-%d")).days
            except Exception:
                gun_fark = None
            gun_str = f"{gun_fark} gün" if gun_fark is not None else "?"

            rapor_icerigi += f"- **{hisse.replace('.IS', '')}** | {lot} Lot | {alis_tarihi} → {satis_tarihi} ({gun_str})\n"
            rapor_icerigi += f"  - Alış: {alis:.2f} ₺ → Satış: {satis:.2f} ₺\n"
            rapor_icerigi += f"  - **Gerçekleşen K/Z:** {isaret}{kz_tl:.2f} ₺ ({isaret}%{kz_yuzde:.2f}) {'🟩' if kz_tl >= 0 else '🟥'}\n\n"

            html_body += f"""
            <div class='card {border_class}'>
                <div class='card-title'>
                    <strong>{hisse.replace('.IS', '')}</strong>
                    <span style='background:{rozet_renk}22;color:{rozet_renk};border:1px solid {rozet_renk}44;padding:2px 8px;border-radius:8px;font-size:0.8em;margin-left:8px;'>{rozet}</span>
                </div>
                <div class='card-content'>
                    <div style='color:#8b949e;font-size:0.85em;'>{alis_tarihi} → {satis_tarihi} &nbsp;|&nbsp; {gun_str} &nbsp;|&nbsp; {lot} Lot</div>
                    <div style='margin-top:6px;'>Alış: <strong>{alis:.2f} ₺</strong> &nbsp;→&nbsp; Satış: <strong>{satis:.2f} ₺</strong></div>
                    <div style='margin-top:8px;padding-top:8px;border-top:1px solid #30363d;font-size:1.05em;'>
                        Gerçekleşen K/Z: <strong style='color:{html_renk}'>{isaret}{kz_tl:.2f} ₺ ({isaret}%{kz_yuzde:.2f})</strong>
                    </div>
                </div>
            </div>
            """

        # Toplam gerçekleşen K/Z özeti
        toplam_isaret = "+" if toplam_gerceklesen_kz >= 0 else ""
        toplam_renk = "#3fb950" if toplam_gerceklesen_kz >= 0 else "#f85149"

        # İstatistikler
        kazananlar = [k for k in kapali_kazanc_listesi if k >= 0]
        kaybedenler = [k for k in kapali_kazanc_listesi if k < 0]
        toplam_islem = len(kapali_islemler)
        kazanma_orani = (len(kazananlar) / toplam_islem * 100) if toplam_islem > 0 else 0
        ort_kazanc = sum(kazananlar) / len(kazananlar) if kazananlar else 0
        ort_kayip = sum(kaybedenler) / len(kaybedenler) if kaybedenler else 0
        en_iyi = max(zip(kapali_kazanc_listesi, [x['hisse'].replace('.IS','') for x in kapali_islemler]), key=lambda x: x[0]) if kapali_islemler else None
        en_kotu = min(zip(kapali_kazanc_listesi, [x['hisse'].replace('.IS','') for x in kapali_islemler]), key=lambda x: x[0]) if kapali_islemler else None

        rapor_icerigi += f"### 🏦 TOPLAM GERÇEKLEŞen K/Z: {toplam_isaret}{toplam_gerceklesen_kz:.2f} ₺\n"
        rapor_icerigi += f"### 📊 İŞLEM İSTATİSTİKLERİ\n"
        rapor_icerigi += f"- Toplam Kapatılan: **{toplam_islem}** işlem\n"
        rapor_icerigi += f"- Kazanma Oranı: **%{kazanma_orani:.0f}** ({len(kazananlar)}K / {len(kaybedenler)}Z)\n"
        if kazananlar: rapor_icerigi += f"- Ort. Kazanç: **+%{ort_kazanc:.2f}**\n"
        if kaybedenler: rapor_icerigi += f"- Ort. Kayıp: **%{ort_kayip:.2f}**\n"
        if en_iyi: rapor_icerigi += f"- En İyi İşlem: **{en_iyi[1]}** (+%{en_iyi[0]:.2f})\n"
        if en_kotu: rapor_icerigi += f"- En Kötü İşlem: **{en_kotu[1]}** (%{en_kotu[0]:.2f})\n"
        rapor_icerigi += "\n"

        html_body += f"""
        </div>
        <div class='summary-box'>
            <h3>🏦 TOPLAM GERÇEKLEŞen K/Z</h3>
            <div style='font-size:1.2em;margin-top:8px;'>
                <strong style='color:{toplam_renk}'>{toplam_isaret}{toplam_gerceklesen_kz:.2f} ₺</strong>
            </div>
            <div style='margin-top:12px;border-top:1px solid #30363d;padding-top:10px;'>
                <div>📊 <strong>İşlem İstatistikleri</strong></div>
                <div style='margin-top:6px;'>Toplam Kapatılan: <strong>{toplam_islem}</strong> işlem</div>
                <div>Kazanma Oranı: <strong style='color:#3fb950'>%{kazanma_orani:.0f}</strong> &nbsp;({len(kazananlar)} Kazanç / {len(kaybedenler)} Zarar)</div>
                {'<div>Ort. Kazanç: <strong style="color:#3fb950">+%' + f'{ort_kazanc:.2f}' + '</strong></div>' if kazananlar else ''}
                {'<div>Ort. Kayıp: <strong style="color:#f85149">%' + f'{ort_kayip:.2f}' + '</strong></div>' if kaybedenler else ''}
                {'<div>En İyi: <strong>' + en_iyi[1] + f'</strong> <span style="color:#3fb950">(+%{en_iyi[0]:.2f})</span></div>' if en_iyi else ''}
                {'<div>En Kötü: <strong>' + en_kotu[1] + f'</strong> <span style="color:#f85149">(%{en_kotu[0]:.2f})</span></div>' if en_kotu else ''}
            </div>
        </div>
        """

    # ---------------- BÖLÜM 2: İZLEME LİSTESİ ----------------
    rapor_icerigi += "## 👁️ RADARIM (Sadece İzleme Listesi)\n"
    rapor_icerigi += "> Açıklama: Alım yapılmamış ancak takipte olduğunuz hisseler.\n\n"
    
    html_body += "<h2>👁️ RADARIM (Sadece İzleme Listesi)</h2>"
    html_body += "<blockquote>Açıklama: Alım yapılmamış ancak takipte olduğunuz hisseler. (Maliyet girilenler Sanal K/Z hesaplar)</blockquote>"
    html_body += "<div class='grid-container'>"
    
    if izleme_listesi:
        for p in izleme_listesi:
            hisse = p['hisse']
            maliyet = p['maliyet']
            lot = p['lot']
            
            if hisse in bugun_veriler.index and hisse in dun_veriler.index:
                bugun_k = bugun_veriler.loc[hisse]
                dun_k = dun_veriler.loc[hisse]
                kapanis = bugun_k['Kapanis']
                atr = bugun_k['ATR_14']
                
                dinamik_hedef = kapanis + (3.0 * atr)
                hesaplanan_dinamik_stop = kapanis - (1.5 * atr)
                dinamik_stop = max(hesaplanan_dinamik_stop, kapanis * 0.85)
                
                gunluk_degisim = ((kapanis - dun_k['Kapanis']) / dun_k['Kapanis']) * 100
                gunluk_isaret = "+" if gunluk_degisim > 0 else ""
                gunluk_renk = "🟩" if gunluk_degisim > 0 else ("🟥" if gunluk_degisim < 0 else "⬜")
                
                yorum = algoritmik_yorum_uret(bugun_k, dun_k, maliyet)
                kisa_skor, orta_skor = _teknik_skor_hesapla(bugun_k)

                border_class = "border-neutral"
                if "KARAR: AL" in yorum or "EKLE" in yorum: border_class = "border-al"
                elif "KARAR: SAT" in yorum or "ZARAR KES" in yorum: border_class = "border-sat"
                elif "KARAR: TUT" in yorum or "KAR AL" in yorum: border_class = "border-tut"
                elif "DİPTEN TOPLA" in yorum: border_class = "border-dip"

                fk, pddd = temel_verileri_getir(hisse)
                fk_str = f"{fk:.1f}" if fk else "Yok"
                pddd_str = f"{pddd:.1f}" if pddd else "Yok"
                try:
                    rs63_str = f"{float(bugun_k['RS_63']):+.1f}%"
                except (KeyError, TypeError, ValueError):
                    rs63_str = "N/A"

                html_body += f"""
                <div class='card {border_class}'>
                    <div class='card-title'><strong>{hisse.replace('.IS', '')}</strong></div>
                    <div class='card-content'>
                """
                
                if maliyet is not None:
                    # Sanal K/Z Hesaplama
                    sanal_fark = (kapanis - maliyet)
                    sanal_fark_yuzde = (sanal_fark / maliyet) * 100
                    sanal_isaret = "+" if sanal_fark > 0 else ""
                    sanal_renk = "🟩" if sanal_fark > 0 else ("🟥" if sanal_fark < 0 else "⬜")
                    s_html_renk = "#3fb950" if sanal_fark > 0 else ("#f85149" if sanal_fark < 0 else "#c9d1d9")
                    
                    ilk_hedef_str = ""
                    ilk_hedef_html = ""
                    if p.get('tarih'):
                        try:
                            c = conn.cursor()
                            # Tarih <= p['tarih'] yaparak hafta sonu girilen tarihleri en yakın işlem gününe yuvarlıyoruz
                            c.execute("SELECT ATR_14 FROM Hisse_Indikatorleri WHERE Hisse=? AND Tarih <= ? ORDER BY Tarih DESC LIMIT 1", (hisse, p['tarih']))
                            atr_row = c.fetchone()
                            if atr_row and atr_row[0]:
                                ilk_atr = atr_row[0]
                                ilk_hedef = maliyet + (3.0 * ilk_atr)
                                hesaplanan_ilk_stop = maliyet - (1.5 * ilk_atr)
                                ilk_stop = max(hesaplanan_ilk_stop, maliyet * 0.85)
                                
                                # Trailing Stop Düzeltmesi: Fiyat düşse bile stop aşağı çekilmez!
                                dinamik_stop = max(ilk_stop, dinamik_stop)
                                
                                ilk_hedef_str = f"  - **İlk Plan:** Hedef {ilk_hedef:.2f} ₺ | Stop {ilk_stop:.2f} ₺\n"
                                ilk_hedef_html = f"<div style='color:#d29922; font-size:0.9em; margin-top:4px;'>İlk Plan: Hedef <strong>{ilk_hedef:.2f} ₺</strong> | Stop <strong>{ilk_stop:.2f} ₺</strong></div>"
                        except Exception:
                            pass
                    
                    if lot:
                        sanal_fark_tl = sanal_fark * lot
                        rapor_icerigi += f"- **{hisse.replace('.IS', '')}**: Maliyet: {maliyet:.2f} ₺ -> Fiyat: {kapanis:.2f} ₺ (Günlük: {gunluk_isaret}%{gunluk_degisim:.2f})\n"
                        if ilk_hedef_str: rapor_icerigi += ilk_hedef_str
                        rapor_icerigi += f"  - **Güncel Dinamik:** Hedef {dinamik_hedef:.2f} ₺ | Stop {dinamik_stop:.2f} ₺\n"
                        rapor_icerigi += f"  - *Sanal Net K/Z:* {sanal_isaret}{sanal_fark_tl:.2f} ₺ ({sanal_isaret}%{sanal_fark_yuzde:.2f}) {sanal_renk}\n"
                        html_body += f"""
                        <div>Maliyet: <strong>{maliyet:.2f} ₺</strong></div>
                        <div>Fiyat: <strong>{kapanis:.2f} ₺</strong> <span style="color:#8b949e; font-size:0.9em">(Günlük: {gunluk_isaret}%{gunluk_degisim:.2f})</span></div>
                        {ilk_hedef_html}
                        <div style='color:#58a6ff; font-size:0.9em; margin-top:4px;'>Güncel: Hedef <strong>{dinamik_hedef:.2f} ₺</strong> | Stop <strong>{dinamik_stop:.2f} ₺</strong></div>
                        <div style='margin-top:8px; padding-top:8px; border-top:1px solid #30363d;'>
                            Sanal K/Z: <strong style='color:{s_html_renk}'>{sanal_isaret}{sanal_fark_tl:.2f} ₺ ({sanal_isaret}%{sanal_fark_yuzde:.2f})</strong>
                        </div>
                        """
                    else:
                        rapor_icerigi += f"- **{hisse.replace('.IS', '')}**: Maliyet: {maliyet:.2f} ₺ -> Fiyat: {kapanis:.2f} ₺ (Günlük: {gunluk_isaret}%{gunluk_degisim:.2f})\n"
                        if ilk_hedef_str: rapor_icerigi += ilk_hedef_str
                        rapor_icerigi += f"  - **Güncel Dinamik:** Hedef {dinamik_hedef:.2f} ₺ | Stop {dinamik_stop:.2f} ₺\n"
                        rapor_icerigi += f"  - *Sanal K/Z:* {sanal_isaret}%{sanal_fark_yuzde:.2f} {sanal_renk}\n"
                        html_body += f"""
                        <div>Maliyet: <strong>{maliyet:.2f} ₺</strong></div>
                        <div>Fiyat: <strong>{kapanis:.2f} ₺</strong> <span style="color:#8b949e; font-size:0.9em">(Günlük: {gunluk_isaret}%{gunluk_degisim:.2f})</span></div>
                        {ilk_hedef_html}
                        <div style='color:#58a6ff; font-size:0.9em; margin-top:4px;'>Güncel: Hedef <strong>{dinamik_hedef:.2f} ₺</strong> | Stop <strong>{dinamik_stop:.2f} ₺</strong></div>
                        <div style='margin-top:8px; padding-top:8px; border-top:1px solid #30363d;'>
                            Sanal K/Z: <strong style='color:{s_html_renk}'>{sanal_isaret}%{sanal_fark_yuzde:.2f}</strong>
                        </div>
                        """
                else:
                    rapor_icerigi += f"- **{hisse.replace('.IS', '')}**: Fiyat: {kapanis:.2f} ₺ (Günlük: {gunluk_isaret}%{gunluk_degisim:.2f} {gunluk_renk})\n"
                    rapor_icerigi += f"  - **Güncel Dinamik:** Hedef {dinamik_hedef:.2f} ₺ | Stop {dinamik_stop:.2f} ₺\n"
                    html_body += f"""
                    <div>Fiyat: <strong>{kapanis:.2f} ₺</strong> <span style="color:#8b949e; font-size:0.9em">(Günlük: {gunluk_isaret}%{gunluk_degisim:.2f})</span></div>
                    <div style='color:#58a6ff; font-size:0.9em; margin-top:4px;'>Güncel: Hedef <strong>{dinamik_hedef:.2f} ₺</strong> | Stop <strong>{dinamik_stop:.2f} ₺</strong></div>
                    """
                
                al_flag = " ← AL bölgesinde!" if max(kisa_skor, orta_skor) >= 50 else ""
                rapor_icerigi += f"  - Teknik ve Temel: RSI: {bugun_k['RSI_14']:.1f} | RS63: {rs63_str} | F/K: {fk_str} | PD/DD: {pddd_str}\n"
                rapor_icerigi += f"  - **Teknik Skor:** Kısa {_skor_badge(kisa_skor)} | Orta {_skor_badge(orta_skor)}{al_flag}\n"
                rapor_icerigi += f"  - Algoritmik Yorum: {yorum}\n\n"

                html_body += f"""
                        <div style='margin-top:8px; font-size:0.85em; color:#8b949e;'>Teknik: RSI: {bugun_k['RSI_14']:.1f} | RS63: {rs63_str} | F/K: {fk_str} | PD/DD: {pddd_str}</div>
                        <div style='margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;'>
                            <span style='background:{_skor_renk(kisa_skor)}22;color:{_skor_renk(kisa_skor)};border:1px solid {_skor_renk(kisa_skor)}44;padding:2px 8px;border-radius:8px;font-size:0.8em;'>Kısa: {_skor_badge(kisa_skor)}</span>
                            <span style='background:{_skor_renk(orta_skor)}22;color:{_skor_renk(orta_skor)};border:1px solid {_skor_renk(orta_skor)}44;padding:2px 8px;border-radius:8px;font-size:0.8em;'>Orta: {_skor_badge(orta_skor)}</span>
                            {"<span style='color:#f0c040;font-size:0.8em;font-weight:600;'>← AL bölgesinde!</span>" if max(kisa_skor, orta_skor) >= 50 else ""}
                        </div>
                        <div class='card-comment'>{yorum.replace('**', '')}</div>
                    </div>
                </div>
                """
        html_body += "</div>"
    else:
        rapor_icerigi += "*İzleme listeniz boş.*\n\n"
        html_body += "<p><em>İzleme listeniz boş.</em></p></div>"

    # ---------------- BÖLÜM 3: ALGORİTMİK TEKNİK ÖNERİLER ----------------
    rapor_icerigi += "## 📊 ALGORİTMİK TEKNİK ÖNERİLER\n"
    rapor_icerigi += "> Açıklama: Sinyal motorunun ürettiği günün en iyi AL fırsatları (puanlama sistemi).\n\n"

    html_body += "<h2>📊 ALGORİTMİK TEKNİK ÖNERİLER</h2>"
    html_body += "<blockquote>Açıklama: Puanlama sistemiyle seçilen en iyi AL fırsatları. 💎 Diamond = 4+ koşul aynı anda, 🔵 Fırsat = güçlü sinyal.</blockquote>"

    # Piyasa durumu banner'ı
    try:
        piyasa_df = pd.read_sql(
            f"SELECT Kapanis, EMA_20 FROM Hisse_Indikatorleri WHERE Tarih='{bugun_tarih}'", conn
        )
        toplam_p = len(piyasa_df)
        ema20_ustu_p = len(piyasa_df[piyasa_df['Kapanis'] > piyasa_df['EMA_20']]) if toplam_p > 0 else 0
        ema20_oran_p = (ema20_ustu_p / toplam_p * 100) if toplam_p > 0 else 0
        if ema20_oran_p < 35:
            p_durum = 'KIRMIZI'
        elif ema20_oran_p < 50:
            p_durum = 'SARI'
        else:
            p_durum = 'YESIL'

        if p_durum == 'KIRMIZI':
            p_css = 'market-red'
            p_header = f"🔴 PİYASA KIRMIZI (%{ema20_oran_p:.0f} hisse EMA20 üstü)"
            p_tracks = [
                ("blocked", "✗ Tüm sinyaller bloke — NAKİTTE KAL!"),
                ("blocked", "↳ Bireysel hisse sinyalleri piyasa dalgasına karşı çalışmaz."),
            ]
        elif p_durum == 'SARI':
            p_css = 'market-yellow'
            p_header = f"🟡 PİYASA SARI (%{ema20_oran_p:.0f} hisse EMA20 üstü)"
            p_tracks = [
                ("active",  "✓ Aktif: Kısa Vade Fırsat — kısa süreli, savunmacı pozisyonlar"),
                ("active",  "✓ Aktif: Düzeltme Fırsatı — trend içi geri çekilme alımları"),
                ("blocked", "✗ Bloke: Kısa Vade Diamond — zayıf piyasada 4+ koşul aynı anda nadiren güvenilirdir"),
                ("blocked", "✗ Bloke: Orta Vade (tüm tier) — 3-6 haftalık pozisyon zayıf piyasaya karşı savaşır"),
            ]
        else:
            p_css = 'market-green'
            p_header = f"✅ PİYASA YEŞİL (%{ema20_oran_p:.0f} hisse EMA20 üstü)"
            p_tracks = [
                ("active", "✓ Aktif: Kısa Vade Diamond + Ruby (~3-7 gün)"),
                ("active", "✓ Aktif: Orta Vade Diamond + Fırsat (~3-6 hafta)"),
                ("active", "✓ Aktif: Düzeltme Fırsatı (trend içi geri çekilme alımları)"),
            ]

        tracks_html = "".join(
            f"<div class='track-item {cls}'>{txt}</div>" for cls, txt in p_tracks
        )
        html_body += f"<div class='market-status {p_css}'><h3 style='margin:0 0 10px 0;'>{p_header}</h3>{tracks_html}</div>"

        tracks_md = "\n".join(f"  - {txt}" for _, txt in p_tracks)
        rapor_icerigi += f"### 🌐 Piyasa Durumu\n{p_header}\n{tracks_md}\n\n"
    except Exception as e:
        html_body += f"<p><em>Piyasa durumu hesaplanamadı: {e}</em></p>"

    # Vade+Tier konfigürasyonu
    vade_konfig = {
        ('Kisa', None):      ('🚀 Kısa Vade (3-7 gün)', '#f0c040', '~3-7 gün — ⭐ Diamond en güçlü | 🔶 Ruby güçlü sinyal'),
        ('Momentum', None):  ('💥 Momentum Patlama', '#ff7b00', 'Bollinger sıkışması + Pocket Pivot — patlama öncesi birikim | ⚡ Diamond | 🔥 Firsat'),
        ('Orta', 'Diamond'): ('💎 Orta Vade Diamond',  '#d29922', '~3-6 hafta, en güçlü trend'),
        ('Orta', 'Firsat'):  ('🔵 Orta Vade Fırsat',   '#bc8cff', '~3-6 hafta, trend fırsatı'),
        ('Duzeltme', 'Firsat'): ('📉 Düzeltme (Pullback)', '#3fb950', 'Trend içi sağlıklı dipten alım'),
    }

    try:
        sinyal_df = pd.read_sql(
            f"SELECT * FROM Gunluk_Sinyaller WHERE Tarih='{bugun_tarih}' ORDER BY Puan DESC",
            conn
        )

        if not sinyal_df.empty:
            # Filter out tickers already held as active positions
            aktif_hisseler = {x['hisse'] for x in aktif_portfoy}
            atlanacaklar = sinyal_df[sinyal_df['Hisse'].isin(aktif_hisseler)].copy()
            sinyal_df = sinyal_df[~sinyal_df['Hisse'].isin(aktif_hisseler)]

            if not atlanacaklar.empty:
                atlanacaklar_sorted = atlanacaklar.sort_values('Potansiyel_Getiri', ascending=False)
                atlanacak_listesi = ", ".join(
                    f"{r['Hisse'].replace('.IS','')} (%{r['Potansiyel_Getiri']:.1f})"
                    for _, r in atlanacaklar_sorted.iterrows()
                )
                n = len(atlanacaklar)
                rapor_icerigi += f"> ℹ️ {n} sinyal portföyünüzde zaten var, atlandı: {atlanacak_listesi}\n\n"
                html_body += f"""<div style='background:#161b22;border:1px solid #30363d;border-left:4px solid #58a6ff;
border-radius:6px;padding:10px 16px;margin-bottom:20px;color:#8b949e;font-size:0.9em;'>
ℹ️ <strong>{n} sinyal</strong> portföyünüzde zaten mevcut olduğu için atlandı:
<span style='color:#c9d1d9;'>{atlanacak_listesi}</span></div>"""

            for (vade, tier), (baslik, renk, aciklama) in vade_konfig.items():
                if tier is None:
                    # Merged Kisa: Diamond + Ruby together, sorted by Puan DESC
                    grup = sinyal_df[sinyal_df['Vade'] == vade].sort_values('Puan', ascending=False).head(8)
                else:
                    strateji_key = f"{vade}_{tier}"
                    grup = sinyal_df[sinyal_df['Strateji'] == strateji_key].head(5)
                if grup.empty:
                    continue

                rapor_icerigi += f"### {baslik}\n"
                rapor_icerigi += f"> {aciklama}\n\n"
                html_body += f"<div class='strateji-baslik' style='border-left:4px solid {renk};padding-left:12px;margin:25px 0 15px 0;'>"
                html_body += f"<h3 style='margin:0;color:{renk};'>{baslik}</h3>"
                html_body += f"<span style='font-size:0.85em;color:#8b949e;'>{aciklama}</span></div>"
                html_body += "<div class='grid-container'>"

                for _, row in grup.iterrows():
                    hisse = row['Hisse']
                    kapanis = row['Kapanis']
                    hedef = row['Hedef_Fiyat']
                    stop = row['Stop_Loss']
                    potansiyel = row['Potansiyel_Getiri']
                    puan_val = int(row['Puan']) if 'Puan' in row.index and not pd.isna(row['Puan']) else 0

                    fk, pddd = temel_verileri_getir(hisse)
                    fk_str = f"{fk:.1f}" if fk else "Yok"
                    pddd_str = f"{pddd:.1f}" if pddd else "Yok"

                    yildiz = "⭐" * int(min(5, max(1, potansiyel // 6)))

                    # Tier badge for merged (Kisa or Momentum) list
                    if tier is None:
                        row_tier = str(row.get('Tier', '')) if hasattr(row, 'get') else str(row['Tier']) if 'Tier' in row.index else ''
                        row_vade = str(row.get('Vade', vade)) if hasattr(row, 'get') else vade
                        if row_vade == 'Momentum':
                            tier_emoji = "⚡" if row_tier == 'Diamond' else "🔥"
                            tier_color = '#ff7b00' if row_tier == 'Diamond' else '#cc6200'
                        else:
                            tier_emoji = "⭐" if row_tier == 'Diamond' else "🔶"
                            tier_color = '#f0c040' if row_tier == 'Diamond' else '#e08800'
                        tier_label  = row_tier
                    else:
                        row_tier   = tier
                        row_vade   = vade
                        tier_emoji = ""
                        tier_label = tier
                        tier_color = renk

                    partial_raw  = row.get('Partial_Cikis') if hasattr(row, 'get') else getattr(row, 'Partial_Cikis', None)
                    _has_partial = bool(partial_raw and not pd.isna(partial_raw))
                    is_momentum  = (row_vade == 'Momentum')

                    # Kısmi çıkış sadece Momentum için (backtest: Kisa/Orta'da PF düşürüyor)
                    partial_md = f" | 🔶 K.Çıkış: {partial_raw:.2f}" if (is_momentum and _has_partial) else ""
                    lot_val, sermaye_val = _hesapla_lot(kapanis, stop, ps_cfg)
                    lot_md = f" | 📊 {lot_val} lot (₺{int(sermaye_val):,})" if lot_val else ""
                    rapor_icerigi += f"- **AL -> {tier_emoji}{hisse.replace('.IS', '')}** | Fiyat: {kapanis:.2f} | Stop: {stop:.2f}{partial_md} | Hedef: {hedef:.2f} (Pot: %{potansiyel:.1f} {yildiz}) | Puan: {puan_val} [{tier_label}]{lot_md}\n"

                    if is_momentum and _has_partial:
                        rapor_icerigi += f"  - 💡 Öneri: {partial_raw:.2f} ₺'de stop tıkıştır ya da %50 kısmi çıkış (12ay: WR ↑ %47.9→%58.7, PF ↓ 1.43→1.07)\n"
                    elif row_vade == 'Orta':
                        rapor_icerigi += "  - 💡 Öneri: Sabırla bekle (~16-17 gün). Stop sıkma — kaybedenlerin %30'u hedefe yaklaşıp döndü (12ay PF 1.38)\n"
                    elif row_vade == 'Kisa':
                        rapor_icerigi += "  - 💡 Öneri: Tam hedefte çık. Kısmi çıkış bu vadede avantaj sağlamaz (ort. 3-7 gün)\n"
                    rapor_icerigi += f"  - Temel: F/K: {fk_str} | PD/DD: {pddd_str}\n\n"

                    partial_html = (
                        f"<div style='color:#e08800;font-size:0.9em;'>🔶 Kısmi Çıkış (50%): <strong>{partial_raw:.2f} ₺</strong> → stop breakeven'e çek</div>"
                        if (is_momentum and _has_partial) else ""
                    )
                    if is_momentum and _has_partial:
                        oneri_html = f"<div style='background:#1c2128;border-left:3px solid #ff7b00;padding:6px 10px;margin-top:6px;font-size:0.82em;color:#c9d1d9;border-radius:0 4px 4px 0;'>💡 <strong>Öneri:</strong> {partial_raw:.2f} ₺'de stop tıkıştır ya da %50 kısmi çıkış → stopı maliyete çek.<br><small style='color:#8b949e;'>12ay: Kısmi çıkış WR ↑ %47.9→%58.7, PF ↓ 1.43→1.07 (risk azalır, kazanç küçülür)</small></div>"
                    elif row_vade == 'Orta':
                        oneri_html = "<div style='background:#1c2128;border-left:3px solid #58a6ff;padding:6px 10px;margin-top:6px;font-size:0.82em;color:#c9d1d9;border-radius:0 4px 4px 0;'>💡 <strong>Öneri:</strong> Sabırla bekle. Ort. tutma 16-17 gün, ort. kazanç +%22.9.<br><small style='color:#8b949e;'>Kaybedenlerin %30'u hedefe yaklaşıp döndü — stop sıkma (12ay PF 1.38)</small></div>"
                    elif row_vade == 'Kisa':
                        oneri_html = "<div style='background:#1c2128;border-left:3px solid #3fb950;padding:6px 10px;margin-top:6px;font-size:0.82em;color:#c9d1d9;border-radius:0 4px 4px 0;'>💡 <strong>Öneri:</strong> Tam hedefte çık. Kısmi çıkış bu vadede avantaj sağlamaz.<br><small style='color:#8b949e;'>Ort. tutma 3-7 gün. 12ay backtest: Ruby WR %55.3, Diamond WR %75</small></div>"
                    else:
                        oneri_html = ""
                    html_body += f"""
                    <div class='card' style='border-left-color:{tier_color};'>
                        <div class='card-title'>
                            <strong>{tier_emoji} {hisse.replace('.IS', '')}</strong>
                            <span class='badge' style='background:{tier_color};color:#0d1117;padding:2px 8px;border-radius:10px;font-size:0.75em;float:right;'>AL</span>
                        </div>
                        <div class='card-content'>
                            <div style='margin-bottom:6px;'>
                                <span style='background:{tier_color}22;color:{tier_color};border:1px solid {tier_color}44;padding:2px 8px;border-radius:8px;font-size:0.8em;'>{tier_label} | {puan_val} puan</span>
                            </div>
                            <div>Fiyat: <strong>{kapanis:.2f} ₺</strong></div>
                            <div style='color:#3fb950;'>Hedef: <strong>{hedef:.2f} ₺</strong> <span style='font-size:0.85em;'>(Pot: %{potansiyel:.1f} {yildiz})</span></div>
                            <div style='color:#f85149;'>Stop: <strong>{stop:.2f} ₺</strong></div>
                            {partial_html}
                            {oneri_html}
                            {f"<div style='color:#58a6ff;font-size:0.9em;margin-top:4px;'>📊 <strong>{lot_val} lot</strong> &nbsp;|&nbsp; Sermaye: <strong>₺{int(sermaye_val):,}</strong> &nbsp;|&nbsp; Risk: ₺{int(ps_cfg.get('portfolio_value',0)*ps_cfg.get('risk_pct',0.02)):,}</div>" if lot_val else ""}
                            <div style='margin-top:8px;font-size:0.85em;color:#8b949e;'>F/K: {fk_str} | PD/DD: {pddd_str}</div>
                        </div>
                    </div>
                    """
                html_body += "</div>"

            if sinyal_df.empty:
                rapor_icerigi += "*Tüm sinyaller portföyünüzde zaten mevcut — yeni fırsat üretilmedi.*\n\n"
                html_body += "<p><em>Tüm sinyaller portföyünüzde zaten mevcut — yeni fırsat üretilmedi.</em></p>"
            rapor_icerigi += "\n"
        else:
            rapor_icerigi += "*Bugün sinyal motorundan öneri üretilmedi.*\n\n"
            html_body += "<p><em>Bugün sinyal motorundan öneri üretilmedi.</em></p>"
    except Exception as e:
        rapor_icerigi += f"*Teknik öneriler okunamadı: {e}*\n\n"
        html_body += f"<p><em>Teknik öneriler okunamadı: {e}</em></p>"

    # ---------------- BÖLÜM 4: GEÇEN GÜN SİNYALLERİ (F1) ----------------
    try:
        if evvelsi_tarih:
            sinyal_today_df = pd.read_sql(
                "SELECT DISTINCT Hisse FROM Gunluk_Sinyaller WHERE Tarih=?",
                conn, params=(bugun_tarih,)
            )
            today_tickers = set(sinyal_today_df['Hisse'].tolist())
            aktif_tickers = {x['hisse'] for x in aktif_portfoy}

            prev_df = pd.read_sql(
                "SELECT * FROM Gunluk_Sinyaller WHERE Tarih IN (?, ?) ORDER BY Tarih DESC, Puan DESC",
                conn, params=(dun_tarih, evvelsi_tarih)
            )
            prev_df = prev_df[~prev_df['Hisse'].isin(today_tickers | aktif_tickers)]
            prev_df = prev_df.drop_duplicates(subset=['Hisse'], keep='first')

            if not prev_df.empty:
                prev_hisseler = prev_df['Hisse'].tolist()
                ph_str = "','".join(prev_hisseler)
                prev_ind_df = pd.read_sql(
                    f"SELECT * FROM Hisse_Indikatorleri WHERE Tarih='{bugun_tarih}' AND Hisse IN ('{ph_str}')",
                    conn
                ).set_index('Hisse')

                gecerli_rows = []
                for _, row in prev_df.iterrows():
                    hisse = row['Hisse']
                    if hisse not in prev_ind_df.index:
                        continue
                    ind_row = prev_ind_df.loc[hisse]
                    kapanis_bugun = _v(ind_row, 'Kapanis')
                    ema20_bugun = _v(ind_row, 'EMA_20')
                    if not kapanis_bugun or not ema20_bugun or kapanis_bugun < ema20_bugun:
                        continue  # EMA20 altı = eski setup bozuldu

                    vade = str(row.get('Vade', '')) if pd.notna(row.get('Vade')) else ''
                    skor_fn_map = {
                        'Kisa': hesapla_kisa_vade_puan,
                        'Orta': hesapla_orta_vade_puan,
                        'Duzeltme': hesapla_duzeltme_puan,
                        'Momentum': hesapla_momentum_patlama_puan,
                    }
                    threshold_map = {'Kisa': 50, 'Orta': 55, 'Duzeltme': 35, 'Momentum': 50}
                    fn = skor_fn_map.get(vade)
                    threshold = threshold_map.get(vade, 50)
                    bugun_skor = fn(ind_row) if fn else 0
                    orijinal_skor = int(row['Puan']) if pd.notna(row.get('Puan')) else 0

                    if bugun_skor >= threshold * 0.7:  # still at least 70% of threshold
                        if bugun_skor >= threshold:
                            badge = "✅ Hâlâ Geçerli"
                            badge_renk = "#3fb950"
                        else:
                            badge = "🔶 Zayıflıyor"
                            badge_renk = "#d29922"
                        gecerli_rows.append({
                            'hisse': hisse,
                            'tarih': row['Tarih'],
                            'vade': vade,
                            'tier': str(row.get('Tier', '')) if pd.notna(row.get('Tier')) else '',
                            'orijinal_skor': orijinal_skor,
                            'bugun_skor': bugun_skor,
                            'kapanis': kapanis_bugun,
                            'stop': row.get('Stop_Loss'),
                            'hedef': row.get('Hedef_Fiyat'),
                            'badge': badge,
                            'badge_renk': badge_renk,
                        })

                if gecerli_rows:
                    rapor_icerigi += "## 🔁 GEÇEN GÜN SİNYALLERİ (Hâlâ Geçerli Mi?)\n"
                    rapor_icerigi += "> Açıklama: Dünkü veya önceki günün sinyalleri — bugün tekrar sinyal üretilmedi ama setup hâlâ geçerli mi?\n\n"
                    html_body += "<h2>🔁 GEÇEN GÜN SİNYALLERİ (Hâlâ Geçerli Mi?)</h2>"
                    html_body += "<blockquote>Dünkü sinyaller — bugün listede yok ama teknik setup devam ediyor mu? Gün 1 optimal giriş noktasıdır; geç giriş risk/ödülü bozar.</blockquote>"
                    html_body += "<div class='grid-container'>"

                    for r in gecerli_rows:
                        rapor_icerigi += f"- **{r['hisse'].replace('.IS','')}** [{r['badge']}] | {r['tarih']} | {r['vade']} {r['tier']}\n"
                        rapor_icerigi += f"  - Orijinal Skor: {r['orijinal_skor']} → Bugün: {r['bugun_skor']} | Fiyat: {r['kapanis']:.2f} ₺\n"
                        if r['hedef'] and r['stop']:
                            rapor_icerigi += f"  - Hedef: {r['hedef']:.2f} ₺ | Stop: {r['stop']:.2f} ₺\n"
                        rapor_icerigi += "\n"

                        html_body += f"""
                        <div class='card' style='border-left-color:{r['badge_renk']};'>
                            <div class='card-title'>
                                <strong>{r['hisse'].replace('.IS','')}</strong>
                                <span style='background:{r['badge_renk']}22;color:{r['badge_renk']};border:1px solid {r['badge_renk']}44;padding:2px 8px;border-radius:8px;font-size:0.78em;float:right;'>{r['badge']}</span>
                            </div>
                            <div class='card-content'>
                                <div style='font-size:0.85em;color:#8b949e;'>{r['tarih']} &nbsp;|&nbsp; {r['vade']} {r['tier']}</div>
                                <div style='margin-top:6px;'>Fiyat: <strong>{r['kapanis']:.2f} ₺</strong></div>
                                <div style='margin-top:4px;font-size:0.9em;'>Skor: <strong>{r['orijinal_skor']}</strong> → bugün <strong style='color:{r['badge_renk']}'>{r['bugun_skor']}</strong></div>
                                {"<div style='margin-top:6px;font-size:0.85em;color:#3fb950;'>Hedef: " + f"{r['hedef']:.2f}" + " ₺ &nbsp;|&nbsp; <span style='color:#f85149;'>Stop: " + f"{r['stop']:.2f}" + " ₺</span></div>" if r['hedef'] and r['stop'] else ''}
                            </div>
                        </div>
                        """

                    html_body += "</div>"
                    rapor_icerigi += "\n"
    except Exception as e:
        html_body += f"<p><em>Geçen gün sinyalleri okunamadı: {e}</em></p>"

    # ---------------- BÖLÜM 5: TAVAN TAKİP (F2) ----------------
    try:
        if p_durum != 'KIRMIZI':
            tavan_df = pd.read_sql("""
                SELECT b.Hisse,
                       b.Kapanis  AS bugun_kapanis,
                       d.Kapanis  AS dun_kapanis,
                       b.Hacim_TL,
                       b.Hacim_Ort_5,
                       (b.Kapanis - d.Kapanis) / d.Kapanis * 100 AS hareket_pct,
                       b.Hacim_TL / b.Hacim_Ort_5 AS hacim_oran
                FROM Hisse_Indikatorleri b
                JOIN Hisse_Indikatorleri d ON b.Hisse = d.Hisse AND d.Tarih = ?
                WHERE b.Tarih = ?
                  AND b.Hacim_TL >= 10000000
                  AND (b.Kapanis - d.Kapanis) / d.Kapanis >= 0.095
                  AND b.Hacim_TL > b.Hacim_Ort_5 * 2.0
                ORDER BY hareket_pct DESC
                LIMIT 10
            """, conn, params=(dun_tarih, bugun_tarih))

            if not tavan_df.empty:
                rapor_icerigi += "## 🚀 TAVAN TAKİP (Olası Zincirleme)\n"
                rapor_icerigi += "> ⚠️ BU LİSTE ALIM SİNYALİ DEĞİLDİR. Tavan zincirleme devam edebilir AMA haberle gelen tavanlar beklenti karşılamazsa sert düşer.\n\n"
                html_body += "<h2>🚀 TAVAN TAKİP (Olası Zincirleme)</h2>"
                html_body += """<div style='background:#1f1a08;border:1px solid #d29922;border-left:4px solid #d29922;border-radius:6px;padding:10px 16px;margin-bottom:20px;color:#d29922;font-size:0.9em;'>
                    ⚠️ <strong>Bu liste alım sinyali DEĞİLDİR.</strong> Tavan zincirleme devam edebilir AMA haberle gelen tavanlar beklenti karşılamazsa sert düşer.
                    </div>"""
                html_body += "<div class='grid-container'>"

                for _, row in tavan_df.iterrows():
                    hisse = row['Hisse'].replace('.IS', '')
                    hpct = float(row['hareket_pct'])
                    horan = float(row['hacim_oran'])
                    kapanis = float(row['bugun_kapanis'])
                    rapor_icerigi += f"- **{hisse}** | +%{hpct:.1f} | Hacim Oranı: {horan:.1f}× | Kapanış: {kapanis:.2f} ₺\n"

                    html_body += f"""
                    <div class='card' style='border-left-color:#d29922;'>
                        <div class='card-title'><strong>{hisse}</strong>
                            <span style='background:#d2992222;color:#d29922;border:1px solid #d2992244;padding:2px 8px;border-radius:8px;font-size:0.78em;float:right;'>TAVAN</span>
                        </div>
                        <div class='card-content'>
                            <div style='color:#f0c040;font-size:1.1em;font-weight:600;'>+%{hpct:.1f}</div>
                            <div style='margin-top:4px;'>Kapanış: <strong>{kapanis:.2f} ₺</strong></div>
                            <div style='font-size:0.85em;color:#8b949e;margin-top:4px;'>Hacim: <strong>{horan:.1f}×</strong> ort.</div>
                        </div>
                    </div>
                    """
                html_body += "</div>"
                rapor_icerigi += "\n"
    except Exception as e:
        html_body += f"<p><em>Tavan takip hesaplanamadı: {e}</em></p>"

    conn.close()

    # Dosyaya yaz (MD)
    rapor_dosyasi = "takip_raporu.md"
    with open(rapor_dosyasi, "w", encoding="utf-8") as f:
        f.write(rapor_icerigi)
        
    # Güzel HTML Üret
    css_style = """
    <style>
        body { font-family: 'Inter', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0d1117; color: #c9d1d9; line-height: 1.5; max-width: 1400px; margin: 0 auto; padding: 30px; }
        h1 { color: #58a6ff; border-bottom: 1px solid #21262d; padding-bottom: 15px; font-weight: 600; text-align: center; margin-bottom: 40px; }
        h2 { color: #3fb950; margin-top: 40px; margin-bottom: 20px; font-weight: 600; border-bottom: 1px solid #21262d; padding-bottom: 10px; }
        blockquote { background: #161b22; border-left: 4px solid #58a6ff; margin: 0 0 30px 0; padding: 15px 20px; font-style: italic; border-radius: 6px; color: #8b949e; font-size: 0.95em; }
        
        .grid-container { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 20px; margin-bottom: 40px; }
        
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; border-left: 5px solid #8b949e; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); transition: transform 0.2s, box-shadow 0.2s; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-5px); box-shadow: 0 8px 16px rgba(0,0,0,0.5); border-color: #8b949e; }
        
        .border-al { border-left-color: #3fb950; }
        .border-sat { border-left-color: #f85149; }
        .border-tut { border-left-color: #d29922; }
        .border-dip { border-left-color: #bc8cff; }
        .border-risk { border-left-color: #d29922; border: 1px solid #d2992266; }
        
        .card-title { font-size: 1.1em; font-weight: 600; margin-bottom: 12px; color: #c9d1d9; border-bottom: 1px solid #30363d; padding-bottom: 8px; }
        .card-title span { font-weight: normal; font-size: 0.85em; color: #8b949e; float: right; margin-top: 3px; }
        .card-content { display: flex; flex-direction: column; gap: 6px; font-size: 0.95em; }
        .card-content strong { color: #ffffff; }
        
        .card-comment { margin-top: 12px; padding: 10px; background: #0d1117; border-radius: 6px; font-size: 0.9em; color: #b1bac4; font-style: italic; border: 1px solid #21262d; }
        
        .summary-box { background: #161b22; padding: 25px; border-radius: 12px; border: 1px solid #30363d; margin-top: 20px; text-align: center; }
        .summary-box h3 { color: #ffca28; margin-top: 0; border-bottom: 1px solid #30363d; padding-bottom: 10px; }

        .market-status { padding: 16px 20px; border-radius: 10px; margin: 20px 0 30px 0; }
        .market-green { background: #0a1f0e; border: 1px solid #3fb950; }
        .market-yellow { background: #1f1a08; border: 1px solid #d29922; }
        .market-red { background: #1f0808; border: 1px solid #f85149; }
        .market-status h3 { font-size: 1em; font-weight: 600; }
        .track-item { margin: 5px 0; font-size: 0.9em; }
        .track-item.active { color: #3fb950; }
        .track-item.blocked { color: #f85149; }
    </style>
    """
    html_content = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>BIST Takip Raporu</title>{css_style}</head><body>{html_body}</body></html>"
    
    with open("takip_raporu.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("✅ HTML Raporu 'takip_raporu.html' dosyasına (NATIVE HTML) kaydedildi.")
    
if __name__ == "__main__":
    takip_raporu_olustur()
