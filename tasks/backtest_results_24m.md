# Backtest Sonuclari — 8 Variant Karsilastirmasi

**Calisma zamani:** 2026-05-31 00:53
**Test araligi:** 2024-06-10 -> 2026-05-29
**Variants:** Baseline | Partial Exit (50%@1.5xATR->breakeven) | Fixed ATR (reference) | Partial + Fixed ATR | Ruby Quota=4 | Ruby XU100 EMA50 Gate | Ruby Rolling PF Gate (last-15, PF<0.8) | Live Mode (J3 + Orta Vol-Adaptive)

> Survivorship bias: aktif hisse evreni, tarihsel olarak devreden cikmis hisseler haric.
> BIST kucuk/orta olcekli hisselerin ~%20-30'u herhangi bir 5 yillik donemde islem disi kaliyor.
> Arastirmalar EM kucuk-cap backtestlerde WR'nin gercekte 5-15pp daha dusuk oldugunu gosteriyor.
> Corporate action gap-drop (>%40 gece dususu): 16 pozisyon hariç tutuldu.

---

## Baseline
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %60.0 |
| Profit Factor | 1.53 |
| Ort. Kazanc | +%7.29 |
| Ort. Kayip | %-7.15 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.8 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 70 |
| WR | %54.3 |
| Profit Factor | 1.20 |
| Ort. Kazanc | +%6.57 |
| Ort. Kayip | %-6.52 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %29.8 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 132 |
| WR | %37.9 |
| Profit Factor | 1.58 |
| Ort. Kazanc | +%27.65 |
| Ort. Kayip | %-10.65 |
| Ort. Tutma | 16.9 gun |
| En Kotu | %-21.94 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.2 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 248 |
| WR | %36.7 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%21.84 |
| Ort. Kayip | %-9.92 |
| Ort. Tutma | 18.6 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 116 |
| WR | %48.3 |
| Profit Factor | 1.48 |
| Ort. Kazanc | +%10.79 |
| Ort. Kayip | %-6.83 |
| Ort. Tutma | 7.2 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.4 |

---

## Partial Exit (50%@1.5xATR->breakeven)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %63.7 |
| Profit Factor | 0.97 |
| Ort. Kazanc | +%3.87 |
| Ort. Kayip | %-7.03 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 70 |
| WR | %57.1 |
| Profit Factor | 0.69 |
| Ort. Kazanc | +%3.30 |
| Ort. Kayip | %-6.41 |
| Ort. Tutma | 4.7 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.3 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 178 |
| WR | %61.2 |
| Profit Factor | 0.75 |
| Ort. Kazanc | +%5.00 |
| Ort. Kayip | %-10.58 |
| Ort. Tutma | 9.9 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %8.9 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 337 |
| WR | %55.2 |
| Profit Factor | 0.81 |
| Ort. Kazanc | +%6.23 |
| Ort. Kayip | %-9.51 |
| Ort. Tutma | 11.0 gun |
| En Kotu | %-18.81 |
| Ort. Hedefe Yakinlik (kaybedenler) | %13.0 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 117 |
| WR | %55.6 |
| Profit Factor | 0.98 |
| Ort. Kazanc | +%5.43 |
| Ort. Kayip | %-6.90 |
| Ort. Tutma | 6.3 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %19.6 |

---

## Fixed ATR (reference)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %60.0 |
| Profit Factor | 1.53 |
| Ort. Kazanc | +%7.29 |
| Ort. Kayip | %-7.15 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.8 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 70 |
| WR | %54.3 |
| Profit Factor | 1.20 |
| Ort. Kazanc | +%6.57 |
| Ort. Kayip | %-6.52 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %29.8 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 171 |
| WR | %39.8 |
| Profit Factor | 1.48 |
| Ort. Kazanc | +%23.02 |
| Ort. Kayip | %-10.24 |
| Ort. Tutma | 15.4 gun |
| En Kotu | %-21.94 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.1 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 308 |
| WR | %35.7 |
| Profit Factor | 1.14 |
| Ort. Kazanc | +%19.64 |
| Ort. Kayip | %-9.54 |
| Ort. Tutma | 16.3 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.6 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 116 |
| WR | %48.3 |
| Profit Factor | 1.48 |
| Ort. Kazanc | +%10.79 |
| Ort. Kayip | %-6.83 |
| Ort. Tutma | 7.2 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.4 |

---

## Partial + Fixed ATR
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %63.7 |
| Profit Factor | 0.97 |
| Ort. Kazanc | +%3.87 |
| Ort. Kayip | %-7.03 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 70 |
| WR | %57.1 |
| Profit Factor | 0.69 |
| Ort. Kazanc | +%3.30 |
| Ort. Kayip | %-6.41 |
| Ort. Tutma | 4.7 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.3 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 178 |
| WR | %61.2 |
| Profit Factor | 0.75 |
| Ort. Kazanc | +%5.00 |
| Ort. Kayip | %-10.58 |
| Ort. Tutma | 9.9 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %8.9 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 337 |
| WR | %55.2 |
| Profit Factor | 0.81 |
| Ort. Kazanc | +%6.23 |
| Ort. Kayip | %-9.51 |
| Ort. Tutma | 11.0 gun |
| En Kotu | %-18.81 |
| Ort. Hedefe Yakinlik (kaybedenler) | %13.0 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 117 |
| WR | %55.6 |
| Profit Factor | 0.98 |
| Ort. Kazanc | +%5.43 |
| Ort. Kayip | %-6.90 |
| Ort. Tutma | 6.3 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %19.6 |

---

## Ruby Quota=4
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %60.0 |
| Profit Factor | 1.53 |
| Ort. Kazanc | +%7.29 |
| Ort. Kayip | %-7.15 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.8 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 69 |
| WR | %55.1 |
| Profit Factor | 1.23 |
| Ort. Kazanc | +%6.57 |
| Ort. Kayip | %-6.56 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %30.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 132 |
| WR | %37.9 |
| Profit Factor | 1.58 |
| Ort. Kazanc | +%27.65 |
| Ort. Kayip | %-10.65 |
| Ort. Tutma | 16.9 gun |
| En Kotu | %-21.94 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.2 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 248 |
| WR | %36.7 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%21.84 |
| Ort. Kayip | %-9.92 |
| Ort. Tutma | 18.6 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 116 |
| WR | %48.3 |
| Profit Factor | 1.48 |
| Ort. Kazanc | +%10.79 |
| Ort. Kayip | %-6.83 |
| Ort. Tutma | 7.2 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.4 |

---

## Ruby XU100 EMA50 Gate
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %60.0 |
| Profit Factor | 1.53 |
| Ort. Kazanc | +%7.29 |
| Ort. Kayip | %-7.15 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.8 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 70 |
| WR | %54.3 |
| Profit Factor | 1.20 |
| Ort. Kazanc | +%6.57 |
| Ort. Kayip | %-6.52 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %29.8 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 132 |
| WR | %37.9 |
| Profit Factor | 1.58 |
| Ort. Kazanc | +%27.65 |
| Ort. Kayip | %-10.65 |
| Ort. Tutma | 16.9 gun |
| En Kotu | %-21.94 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.2 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 248 |
| WR | %36.7 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%21.84 |
| Ort. Kayip | %-9.92 |
| Ort. Tutma | 18.6 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 116 |
| WR | %48.3 |
| Profit Factor | 1.48 |
| Ort. Kazanc | +%10.79 |
| Ort. Kayip | %-6.83 |
| Ort. Tutma | 7.2 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.4 |

---

## Ruby Rolling PF Gate (last-15, PF<0.8)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 80 |
| WR | %60.0 |
| Profit Factor | 1.53 |
| Ort. Kazanc | +%7.29 |
| Ort. Kayip | %-7.15 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.8 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 19 |
| WR | %36.8 |
| Profit Factor | 0.57 |
| Ort. Kazanc | +%6.85 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 5.5 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %31.0 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 132 |
| WR | %37.9 |
| Profit Factor | 1.58 |
| Ort. Kazanc | +%27.65 |
| Ort. Kayip | %-10.65 |
| Ort. Tutma | 16.9 gun |
| En Kotu | %-21.94 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.2 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 248 |
| WR | %36.7 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%21.84 |
| Ort. Kayip | %-9.92 |
| Ort. Tutma | 18.6 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 116 |
| WR | %48.3 |
| Profit Factor | 1.48 |
| Ort. Kazanc | +%10.79 |
| Ort. Kayip | %-6.83 |
| Ort. Tutma | 7.2 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.4 |

---

## Live Mode (J3 + Orta Vol-Adaptive)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 97 |
| WR | %61.9 |
| Profit Factor | 1.66 |
| Ort. Kazanc | +%7.26 |
| Ort. Kayip | %-7.09 |
| Ort. Tutma | 5.5 gun |
| En Kotu | %-15.44 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.8 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 72 |
| WR | %52.8 |
| Profit Factor | 1.15 |
| Ort. Kazanc | +%6.82 |
| Ort. Kayip | %-6.61 |
| Ort. Tutma | 5.2 gun |
| En Kotu | %-13.09 |
| Ort. Hedefe Yakinlik (kaybedenler) | %34.0 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 104 |
| WR | %38.5 |
| Profit Factor | 1.55 |
| Ort. Kazanc | +%27.14 |
| Ort. Kayip | %-10.95 |
| Ort. Tutma | 16.6 gun |
| En Kotu | %-19.71 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.1 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 235 |
| WR | %34.9 |
| Profit Factor | 1.22 |
| Ort. Kazanc | +%22.69 |
| Ort. Kayip | %-9.95 |
| Ort. Tutma | 18.8 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.5 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 117 |
| WR | %47.0 |
| Profit Factor | 1.43 |
| Ort. Kazanc | +%10.77 |
| Ort. Kayip | %-6.66 |
| Ort. Tutma | 7.2 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.7 |

---

---

## Pencere Analizi — Baseline (8 Aylık Dönemler)

### Kisa Diamond
| Dönem | İşlem | WR% | PF |
|-------|-------|-----|-----|
| 2024-06→2025-02 | 23 | %60.9 | 1.47 |
| 2025-02→2025-10 | 22 | %63.6 | 1.74 |
| 2025-10→2026-06 | 35 | %57.1 | 1.46 |

### Kisa Ruby
| Dönem | İşlem | WR% | PF |
|-------|-------|-----|-----|
| 2024-06→2025-02 | 12 | %25.0 | 0.27 |
| 2025-02→2025-10 | 19 | %73.7 | 2.62 |
| 2025-10→2026-06 | 39 | %53.8 | 1.28 |

### Orta Firsat
| Dönem | İşlem | WR% | PF |
|-------|-------|-----|-----|
| 2024-06→2025-02 | 58 | %39.7 | 1.05 |
| 2025-02→2025-10 | 101 | %41.6 | 1.71 |
| 2025-10→2026-06 | 89 | %29.2 | 1.00 |
