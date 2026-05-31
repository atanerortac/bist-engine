# Backtest Sonuclari — 8 Variant Karsilastirmasi

**Calisma zamani:** 2026-05-31 00:51
**Test araligi:** 2025-12-02 -> 2026-05-29
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
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 2.18 |
| Ort. Kazanc | +%7.13 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 38 |
| WR | %52.6 |
| Profit Factor | 1.21 |
| Ort. Kazanc | +%6.79 |
| Ort. Kayip | %-6.22 |
| Ort. Tutma | 4.4 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 42 |
| WR | %38.1 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%22.13 |
| Ort. Kayip | %-10.68 |
| Ort. Tutma | 14.5 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.3 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 73 |
| WR | %31.5 |
| Profit Factor | 1.06 |
| Ort. Kazanc | +%24.39 |
| Ort. Kayip | %-10.58 |
| Ort. Tutma | 19.7 gun |
| En Kotu | %-19.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %33.5 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %55.6 |
| Profit Factor | 1.94 |
| Ort. Kazanc | +%10.90 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 7.8 gun |
| En Kotu | %-8.72 |
| Ort. Hedefe Yakinlik (kaybedenler) | %36.1 |

---

## Partial Exit (50%@1.5xATR->breakeven)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 1.27 |
| Ort. Kazanc | +%4.17 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.3 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 38 |
| WR | %55.3 |
| Profit Factor | 0.75 |
| Ort. Kazanc | +%3.57 |
| Ort. Kayip | %-5.89 |
| Ort. Tutma | 4.1 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.4 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 52 |
| WR | %63.5 |
| Profit Factor | 0.89 |
| Ort. Kazanc | +%5.33 |
| Ort. Kayip | %-10.43 |
| Ort. Tutma | 8.7 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %9.9 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 94 |
| WR | %60.6 |
| Profit Factor | 0.99 |
| Ort. Kazanc | +%6.53 |
| Ort. Kayip | %-10.21 |
| Ort. Tutma | 10.9 gun |
| En Kotu | %-18.81 |
| Ort. Hedefe Yakinlik (kaybedenler) | %15.3 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %66.7 |
| Profit Factor | 1.47 |
| Ort. Kazanc | +%4.69 |
| Ort. Kayip | %-6.37 |
| Ort. Tutma | 7.0 gun |
| En Kotu | %-8.49 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.1 |

---

## Fixed ATR (reference)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 2.18 |
| Ort. Kazanc | +%7.13 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 38 |
| WR | %52.6 |
| Profit Factor | 1.21 |
| Ort. Kazanc | +%6.79 |
| Ort. Kayip | %-6.22 |
| Ort. Tutma | 4.4 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 50 |
| WR | %42.0 |
| Profit Factor | 1.26 |
| Ort. Kazanc | +%18.18 |
| Ort. Kayip | %-10.46 |
| Ort. Tutma | 13.6 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.5 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 84 |
| WR | %33.3 |
| Profit Factor | 1.13 |
| Ort. Kazanc | +%23.04 |
| Ort. Kayip | %-10.22 |
| Ort. Tutma | 17.7 gun |
| En Kotu | %-19.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %32.9 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %55.6 |
| Profit Factor | 1.94 |
| Ort. Kazanc | +%10.90 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 7.8 gun |
| En Kotu | %-8.72 |
| Ort. Hedefe Yakinlik (kaybedenler) | %36.1 |

---

## Partial + Fixed ATR
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 1.27 |
| Ort. Kazanc | +%4.17 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.3 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 38 |
| WR | %55.3 |
| Profit Factor | 0.75 |
| Ort. Kazanc | +%3.57 |
| Ort. Kayip | %-5.89 |
| Ort. Tutma | 4.1 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %24.4 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 52 |
| WR | %63.5 |
| Profit Factor | 0.89 |
| Ort. Kazanc | +%5.33 |
| Ort. Kayip | %-10.43 |
| Ort. Tutma | 8.7 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %9.9 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 94 |
| WR | %60.6 |
| Profit Factor | 0.99 |
| Ort. Kazanc | +%6.53 |
| Ort. Kayip | %-10.21 |
| Ort. Tutma | 10.9 gun |
| En Kotu | %-18.81 |
| Ort. Hedefe Yakinlik (kaybedenler) | %15.3 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %66.7 |
| Profit Factor | 1.47 |
| Ort. Kazanc | +%4.69 |
| Ort. Kayip | %-6.37 |
| Ort. Tutma | 7.0 gun |
| En Kotu | %-8.49 |
| Ort. Hedefe Yakinlik (kaybedenler) | %25.1 |

---

## Ruby Quota=4
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 2.18 |
| Ort. Kazanc | +%7.13 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 37 |
| WR | %54.1 |
| Profit Factor | 1.27 |
| Ort. Kazanc | +%6.79 |
| Ort. Kayip | %-6.28 |
| Ort. Tutma | 4.5 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.4 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 42 |
| WR | %38.1 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%22.13 |
| Ort. Kayip | %-10.68 |
| Ort. Tutma | 14.5 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.3 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 73 |
| WR | %31.5 |
| Profit Factor | 1.06 |
| Ort. Kazanc | +%24.39 |
| Ort. Kayip | %-10.58 |
| Ort. Tutma | 19.7 gun |
| En Kotu | %-19.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %33.5 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %55.6 |
| Profit Factor | 1.94 |
| Ort. Kazanc | +%10.90 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 7.8 gun |
| En Kotu | %-8.72 |
| Ort. Hedefe Yakinlik (kaybedenler) | %36.1 |

---

## Ruby XU100 EMA50 Gate
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 2.18 |
| Ort. Kazanc | +%7.13 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 38 |
| WR | %52.6 |
| Profit Factor | 1.21 |
| Ort. Kazanc | +%6.79 |
| Ort. Kayip | %-6.22 |
| Ort. Tutma | 4.4 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %27.1 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 42 |
| WR | %38.1 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%22.13 |
| Ort. Kayip | %-10.68 |
| Ort. Tutma | 14.5 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.3 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 73 |
| WR | %31.5 |
| Profit Factor | 1.06 |
| Ort. Kazanc | +%24.39 |
| Ort. Kayip | %-10.58 |
| Ort. Tutma | 19.7 gun |
| En Kotu | %-19.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %33.5 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %55.6 |
| Profit Factor | 1.94 |
| Ort. Kazanc | +%10.90 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 7.8 gun |
| En Kotu | %-8.72 |
| Ort. Hedefe Yakinlik (kaybedenler) | %36.1 |

---

## Ruby Rolling PF Gate (last-15, PF<0.8)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 30 |
| WR | %66.7 |
| Profit Factor | 2.18 |
| Ort. Kazanc | +%7.13 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.6 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 27 |
| WR | %51.9 |
| Profit Factor | 1.18 |
| Ort. Kazanc | +%6.72 |
| Ort. Kayip | %-6.11 |
| Ort. Tutma | 4.1 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %29.7 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 42 |
| WR | %38.1 |
| Profit Factor | 1.28 |
| Ort. Kazanc | +%22.13 |
| Ort. Kayip | %-10.68 |
| Ort. Tutma | 14.5 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.3 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 73 |
| WR | %31.5 |
| Profit Factor | 1.06 |
| Ort. Kazanc | +%24.39 |
| Ort. Kayip | %-10.58 |
| Ort. Tutma | 19.7 gun |
| En Kotu | %-19.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %33.5 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 18 |
| WR | %55.6 |
| Profit Factor | 1.94 |
| Ort. Kazanc | +%10.90 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 7.8 gun |
| En Kotu | %-8.72 |
| Ort. Hedefe Yakinlik (kaybedenler) | %36.1 |

---

## Live Mode (J3 + Orta Vol-Adaptive)
### Kisa Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 33 |
| WR | %69.7 |
| Profit Factor | 2.51 |
| Ort. Kazanc | +%7.14 |
| Ort. Kayip | %-6.54 |
| Ort. Tutma | 4.5 gun |
| En Kotu | %-8.12 |
| Ort. Hedefe Yakinlik (kaybedenler) | %11.6 |

### Kisa Ruby
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 35 |
| WR | %54.3 |
| Profit Factor | 1.29 |
| Ort. Kazanc | +%6.70 |
| Ort. Kayip | %-6.19 |
| Ort. Tutma | 4.1 gun |
| En Kotu | %-8.41 |
| Ort. Hedefe Yakinlik (kaybedenler) | %28.8 |

### Orta Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 43 |
| WR | %39.5 |
| Profit Factor | 1.29 |
| Ort. Kazanc | +%21.08 |
| Ort. Kayip | %-10.68 |
| Ort. Tutma | 15.0 gun |
| En Kotu | %-20.55 |
| Ort. Hedefe Yakinlik (kaybedenler) | %21.3 |

### Orta Firsat
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 68 |
| WR | %30.9 |
| Profit Factor | 1.05 |
| Ort. Kazanc | +%25.54 |
| Ort. Kayip | %-10.89 |
| Ort. Tutma | 20.1 gun |
| En Kotu | %-20.13 |
| Ort. Hedefe Yakinlik (kaybedenler) | %33.9 |

### Momentum Diamond
| Metrik | Deger |
|--------|-------|
| Toplam Islem | 19 |
| WR | %57.9 |
| Profit Factor | 2.16 |
| Ort. Kazanc | +%10.99 |
| Ort. Kayip | %-7.00 |
| Ort. Tutma | 7.8 gun |
| En Kotu | %-8.72 |
| Ort. Hedefe Yakinlik (kaybedenler) | %36.1 |

---
