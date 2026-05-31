# Backtest Sonuclari — 8 Variant Karsilastirmasi

**Calisma zamani:** 2026-05-31 00:51
**Test araligi:** 2025-06-05 -> 2026-05-29
**Variants:** Baseline | Partial Exit (50%@1.5xATR->breakeven) | Fixed ATR (reference) | Partial + Fixed ATR | Ruby Quota=4 | Ruby XU100 EMA50 Gate | Ruby Rolling PF Gate (last-15, PF<0.8) | Live Mode (J3 + Orta Vol-Adaptive)

> Survivorship bias: aktif hisse evreni, tarihsel olarak devreden cikmis hisseler haric.
> BIST kucuk/orta olcekli hisselerin ~%20-30'u herhangi bir 5 yillik donemde islem disi kaliyor.
> Arastirmalar EM kucuk-cap backtestlerde WR'nin gercekte 5-15pp daha dusuk oldugunu gosteriyor.
> Corporate action gap-drop (>%40 gece dususu): 8 pozisyon hariç tutuldu.

---

## Baseline
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %60.4 |
| Profit Factor | 1.57 |
| Ort. Kazanc | +%6.98 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.8 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.1 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 57 |
| WR | %57.9 |
| Profit Factor | 1.42 |
| Ort. Kazanc | +%6.60 |
| Ort. Kayip | %-6.39 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 92 |
| WR | %43.5 |
| Profit Factor | 2.06 |
| Ort. Kazanc | +%28.77 |
| Ort. Kayip | %-10.76 |
| Ort. Tutma | 18.2 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.4 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 170 |
| WR | %38.2 |
| Profit Factor | 1.45 |
| Ort. Kazanc | +%23.89 |
| Ort. Kayip | %-10.20 |
| Ort. Tutma | 19.4 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 84 |
| WR | %50.0 |
| Profit Factor | 1.69 |
| Ort. Kazanc | +%11.45 |
| Ort. Kayip | %-6.79 |
| Ort. Tutma | 6.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %23.5 |

---

## Partial Exit (50%@1.5xATR->breakeven)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %62.3 |
| Profit Factor | 0.99 |
| Ort. Kazanc | +%4.07 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.4 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %20.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 57 |
| WR | %61.4 |
| Profit Factor | 0.87 |
| Ort. Kazanc | +%3.42 |
| Ort. Kayip | %-6.22 |
| Ort. Tutma | 4.7 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 118 |
| WR | %66.1 |
| Profit Factor | 0.89 |
| Ort. Kazanc | +%5.03 |
| Ort. Kayip | %-11.00 |
| Ort. Tutma | 9.9 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %9.7 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 223 |
| WR | %57.8 |
| Profit Factor | 0.95 |
| Ort. Kazanc | +%6.87 |
| Ort. Kayip | %-9.92 |
| Ort. Tutma | 11.2 gun |
| En Kotu | %-18.81 |
| Ort. Hedefe Yakinlik (kaybedenler) | %13.8 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 85 |
| WR | %56.5 |
| Profit Factor | 1.08 |
| Ort. Kazanc | +%5.72 |
| Ort. Kayip | %-6.88 |
| Ort. Tutma | 5.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %17.2 |

---

## Fixed ATR (reference)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %60.4 |
| Profit Factor | 1.57 |
| Ort. Kazanc | +%6.98 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.8 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.1 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 57 |
| WR | %57.9 |
| Profit Factor | 1.42 |
| Ort. Kazanc | +%6.60 |
| Ort. Kayip | %-6.39 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 112 |
| WR | %45.5 |
| Profit Factor | 1.98 |
| Ort. Kazanc | +%24.58 |
| Ort. Kayip | %-10.37 |
| Ort. Tutma | 16.2 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %26.3 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 200 |
| WR | %37.0 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%21.50 |
| Ort. Kayip | %-9.86 |
| Ort. Tutma | 17.0 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.8 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 84 |
| WR | %50.0 |
| Profit Factor | 1.69 |
| Ort. Kazanc | +%11.45 |
| Ort. Kayip | %-6.79 |
| Ort. Tutma | 6.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %23.5 |

---

## Partial + Fixed ATR
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %62.3 |
| Profit Factor | 0.99 |
| Ort. Kazanc | +%4.07 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.4 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %20.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 57 |
| WR | %61.4 |
| Profit Factor | 0.87 |
| Ort. Kazanc | +%3.42 |
| Ort. Kayip | %-6.22 |
| Ort. Tutma | 4.7 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %22.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 118 |
| WR | %66.1 |
| Profit Factor | 0.89 |
| Ort. Kazanc | +%5.03 |
| Ort. Kayip | %-11.00 |
| Ort. Tutma | 9.9 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %9.7 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 223 |
| WR | %57.8 |
| Profit Factor | 0.95 |
| Ort. Kazanc | +%6.87 |
| Ort. Kayip | %-9.92 |
| Ort. Tutma | 11.2 gun |
| En Kotu | %-18.81 |
| Ort. Hedefe Yakinlik (kaybedenler) | %13.8 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 85 |
| WR | %56.5 |
| Profit Factor | 1.08 |
| Ort. Kazanc | +%5.72 |
| Ort. Kayip | %-6.88 |
| Ort. Tutma | 5.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %17.2 |

---

## Ruby Quota=4
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %60.4 |
| Profit Factor | 1.57 |
| Ort. Kazanc | +%6.98 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.8 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.1 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 56 |
| WR | %58.9 |
| Profit Factor | 1.47 |
| Ort. Kazanc | +%6.60 |
| Ort. Kayip | %-6.44 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.3 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 92 |
| WR | %43.5 |
| Profit Factor | 2.06 |
| Ort. Kazanc | +%28.77 |
| Ort. Kayip | %-10.76 |
| Ort. Tutma | 18.2 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.4 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 170 |
| WR | %38.2 |
| Profit Factor | 1.45 |
| Ort. Kazanc | +%23.89 |
| Ort. Kayip | %-10.20 |
| Ort. Tutma | 19.4 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 84 |
| WR | %50.0 |
| Profit Factor | 1.69 |
| Ort. Kazanc | +%11.45 |
| Ort. Kayip | %-6.79 |
| Ort. Tutma | 6.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %23.5 |

---

## Ruby XU100 EMA50 Gate
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %60.4 |
| Profit Factor | 1.57 |
| Ort. Kazanc | +%6.98 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.8 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.1 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 57 |
| WR | %57.9 |
| Profit Factor | 1.42 |
| Ort. Kazanc | +%6.60 |
| Ort. Kayip | %-6.39 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 92 |
| WR | %43.5 |
| Profit Factor | 2.06 |
| Ort. Kazanc | +%28.77 |
| Ort. Kayip | %-10.76 |
| Ort. Tutma | 18.2 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.4 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 170 |
| WR | %38.2 |
| Profit Factor | 1.45 |
| Ort. Kazanc | +%23.89 |
| Ort. Kayip | %-10.20 |
| Ort. Tutma | 19.4 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 84 |
| WR | %50.0 |
| Profit Factor | 1.69 |
| Ort. Kazanc | +%11.45 |
| Ort. Kayip | %-6.79 |
| Ort. Tutma | 6.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %23.5 |

---

## Ruby Rolling PF Gate (last-15, PF<0.8)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 53 |
| WR | %60.4 |
| Profit Factor | 1.57 |
| Ort. Kazanc | +%6.98 |
| Ort. Kayip | %-6.76 |
| Ort. Tutma | 4.8 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.1 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 46 |
| WR | %58.7 |
| Profit Factor | 1.46 |
| Ort. Kazanc | +%6.53 |
| Ort. Kayip | %-6.36 |
| Ort. Tutma | 5.1 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.8 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 92 |
| WR | %43.5 |
| Profit Factor | 2.06 |
| Ort. Kazanc | +%28.77 |
| Ort. Kayip | %-10.76 |
| Ort. Tutma | 18.2 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.4 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 170 |
| WR | %38.2 |
| Profit Factor | 1.45 |
| Ort. Kazanc | +%23.89 |
| Ort. Kayip | %-10.20 |
| Ort. Tutma | 19.4 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.2 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 84 |
| WR | %50.0 |
| Profit Factor | 1.69 |
| Ort. Kazanc | +%11.45 |
| Ort. Kayip | %-6.79 |
| Ort. Tutma | 6.9 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %23.5 |

---

## Live Mode (J3 + Orta Vol-Adaptive)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 62 |
| WR | %64.5 |
| Profit Factor | 1.85 |
| Ort. Kazanc | +%7.02 |
| Ort. Kayip | %-6.89 |
| Ort. Tutma | 5.0 gun |
| En Kotu | %-9.62 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.7 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 58 |
| WR | %60.3 |
| Profit Factor | 1.58 |
| Ort. Kazanc | +%6.64 |
| Ort. Kayip | %-6.38 |
| Ort. Tutma | 5.0 gun |
| En Kotu | %-8.86 |
| Ort. Hedefe Yakinlik (kaybedenler) | %30.8 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 85 |
| WR | %47.1 |
| Profit Factor | 2.31 |
| Ort. Kazanc | +%28.59 |
| Ort. Kayip | %-10.98 |
| Ort. Tutma | 18.8 gun |
| En Kotu | %-19.71 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.9 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 165 |
| WR | %37.6 |
| Profit Factor | 1.40 |
| Ort. Kazanc | +%24.12 |
| Ort. Kayip | %-10.36 |
| Ort. Tutma | 19.9 gun |
| En Kotu | %-20.78 |
| Ort. Hedefe Yakinlik (kaybedenler) | %30.1 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 87 |
| WR | %50.6 |
| Profit Factor | 1.77 |
| Ort. Kazanc | +%11.49 |
| Ort. Kayip | %-6.64 |
| Ort. Tutma | 7.0 gun |
| En Kotu | %-11.11 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.9 |

---

---

## Pencere Analizi — Baseline (8 Aylık Dönemler)

### Kisa Diamond
| Dönem | İşlem | WR% | PF |
|-------|-------|-----|-----|
| 2025-06→2026-02 | 35 | %48.6 | 0.98 |
| 2026-02→2026-10 | 18 | %83.3 | 4.91 |

### Kisa Ruby
| Dönem | İşlem | WR% | PF |
|-------|-------|-----|-----|
| 2025-06→2026-02 | 28 | %67.9 | 2.10 |
| 2026-02→2026-10 | 29 | %48.3 | 1.00 |

### Orta Firsat
| Dönem | İşlem | WR% | PF |
|-------|-------|-----|-----|
| 2025-06→2026-02 | 126 | %42.1 | 1.82 |
| 2026-02→2026-10 | 44 | %27.3 | 0.69 |
