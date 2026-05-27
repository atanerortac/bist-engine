import yfinance as yf

_temel_cache = {}

def temel_verileri_getir(hisse):
    """
    Belirtilen hisse senedi için Yahoo Finance üzerinden F/K (trailingPE) 
    ve PD/DD (priceToBook) verilerini çeker.
    Eğer hata oluşursa veya veri yoksa (None, None) döner.
    """
    if not hisse.endswith('.IS'):
        hisse += '.IS'

    if hisse in _temel_cache:
        return _temel_cache[hisse]

    try:
        ticker = yf.Ticker(hisse)
        info = ticker.info

        fk = info.get('trailingPE', None)
        pddd = info.get('priceToBook', None)

        if fk is not None and (not isinstance(fk, (int, float)) or fk < 0):
            fk = None

        result = (fk, pddd)
        _temel_cache[hisse] = result
        return result
    except Exception:
        _temel_cache[hisse] = (None, None)
        return None, None
