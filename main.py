import sys
import time
import schedule
from veri_motoru import verileri_guncelle
from indicator_engine import hesapla_ve_kaydet
from strategy_engine import sinyalleri_uret
from portfolio_manager import portfoyu_yonet
from raporlayici import gunluk_ozet_raporu
from takip_motoru import takip_raporu_olustur

def ajani_baslat():
    print("🚀 BIST AJANI BAŞLATILIYOR...\n")
    baslangic = time.time()

    verileri_guncelle()
    hesapla_ve_kaydet()
    sinyalleri_uret()
    portfoyu_yonet()
    gunluk_ozet_raporu()
    takip_raporu_olustur()

    bitis = time.time()
    print(f"⏱️ Toplam Çalışma Süresi: {round(bitis - baslangic, 2)} saniye.")
    print("⏳ Görev tamamlandı.\n")

if __name__ == "__main__":
    # --auto flag: non-interactive mode for CI/scheduled runs
    if "--auto" in sys.argv:
        try:
            ajani_baslat()
        except Exception as e:
            print(f"\n❌ SİSTEM HATASI: {e}")
            sys.exit(1)
        sys.exit(0)

    print("="*40)
    print("🤖 BIST ANALİZ AJANI")
    print("="*40)
    print("1. Hemen Çalıştır ve Kapat")
    print("2. Zamanlanmış Görev Olarak Arka Planda Başlat (Örn: Her gün 18:30)")
    secim = input("Seçiminiz (1/2): ")

    if secim == '1':
        ajani_baslat()
    elif secim == '2':
        saat = input("Çalışma saati girin (Örn: 18:30) [Varsayılan: 18:30]: ")
        if not saat:
            saat = "18:30"
        schedule.every().day.at(saat).do(ajani_baslat)
        print(f"✅ Zamanlayıcı kuruldu. Sistem her gün {saat} itibarıyla çalışacak.")
        print("Arka planda çalışıyor. Kapatmak için CTRL+C'ye basabilirsiniz.")
        while True:
            schedule.run_pending()
            time.sleep(60) # Her 1 dakikada bir saati kontrol et
    else:
        print("Geçersiz seçim.")