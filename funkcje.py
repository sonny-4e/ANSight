"""
funkcje.py - parametry, przetwarzanie wstepne i funkcje pomocnicze dla main.py.
Cala matematyka HRV jest w klasie ECG (ECG.py) - tutaj tylko ja wywolujemy,
tak samo w pomiarze na zywo i w analizie offline.
"""
import numpy as np
import pandas as pd
import scipy.signal as sig
from ECG import ECG


# PARAMETRY DOMYSLNE - GUI w main.py nadpisuje czesc z nich przed pomiarem / obliczeniami

PARAMETRY = {
    "fs": 250,                  # czestotliwosc probkowania [Hz] (Aidlab = 250)
    "filtr_dol": 0.5,           # filtr pasmowy Butterwortha: dolna granica [Hz]
    "filtr_gora": 40.0,         # filtr pasmowy Butterwortha: gorna granica [Hz]
    "rzad_filtru": 3,           # rzad filtra
    "MinPeakHeight": 1.5,       # detekcja R na sygnale Z-score
    "MinPeakProminence": 1.0,
    "MinPeakDistance": 0.35,    # minimalny odstep pikow [s]
    "RRmaxDev": 0.2,            # odrzucanie RR odbiegajacego od lokalnej mediany o > 20%
    "RRmin": 0.3,               # granice fizjologiczne RR [s] (200 i 30 BPM)
    "RRmax": 2.0,
    "min_uderzen": 20,          # okno jest 'wazne', gdy ma min. tyle uderzen...
    "max_odrzucone": 0.2,       # ...i odrzucono mniej niz taki odsetek RR
    "prog_luki_s": 0.05,        # odstep Timestamp > 50 ms = zgubione probki (luka w danych)
    "min_okno_hf_s": 50,        # HF liczymy, gdy prawidlowe RR pokrywaja min. tyle sekund
    "min_okno_lf_s": 110,       # LF i LF/HF - min. ok. 2 min (pasmo LF zaczyna sie od 0,04 Hz)
}

# nazwy cech zwracanych przez funkcje ponizej
CECHY = ["bpm", "sdnn", "rmssd", "pnn50", "sd1", "sd2", "lf", "hf", "lf_hf"]


def apply_aidlab_bandpass_filter(signal, fs=250, f_dol=0.5, f_gora=40.0, rzad=3):
    """Filtr pasmowoprzepustowy Butterwortha (filtfilt) z parametrami z GUI."""
    nyquist = 0.5 * fs
    low = f_dol / nyquist
    high = f_gora / nyquist
    b, a = sig.butter(rzad, [low, high], btype='band')
    return sig.filtfilt(b, a, signal)


def standaryzuj(sygnal):
    """Z-score: (x - srednia) / odchylenie standardowe."""
    return (sygnal - np.mean(sygnal)) / (np.std(sygnal) + 1e-9)


def przygotuj_sygnal(surowy, p):
    """Cały preprocessing w jednym miejscu: filtr pasmowy + Z-score."""
    przefiltrowany = apply_aidlab_bandpass_filter(
        np.asarray(surowy, dtype=float), p["fs"], p["filtr_dol"], p["filtr_gora"], p["rzad_filtru"])
    return standaryzuj(przefiltrowany)


def os_czasu(timestamps, n, fs, prog_luki_s=0.05):
    """Os czasu [s] od poczatku nagrania z uwzglednieniem zgubionych probek.

    Czas wewnatrz ciaglych fragmentow liczymy z numeru probki (Timestamp z opaski ma
    jitter rzedu kilku ms, wiec nie nadaje sie do wyznaczania polozenia R), ale gdy odstep
    miedzy kolejnymi Timestamp przekracza prog_luki_s, przesuwamy dalsza czesc osi
    o brakujacy czas. Zwraca (t, luki), luki = [(t_poczatek, t_koniec), ...]."""
    t = np.arange(n) / fs
    if timestamps is None or n < 2:
        return t, []
    ts = np.asarray(timestamps, dtype=float) / 1000.0  # Aidlab: ms -> s
    dt = np.diff(ts)
    idx = np.where(dt > prog_luki_s)[0]
    if len(idx) == 0:
        return t, []
    nadmiar = np.zeros(n)
    nadmiar[idx + 1] = dt[idx] - 1.0 / fs
    t = t + np.cumsum(nadmiar)
    luki = [(t[i], t[i + 1]) for i in idx]
    return t, luki


def uruchom_ecg(sygnal_std, p, nazwa="ECG", czas=None, luki=None):
    """Tworzy obiekt ECG dla przygotowanego sygnalu i liczy wszystkie cechy.
    Parametry detekcji pochodza z GUI (slownik p)."""
    ecg = ECG(ecg_signal=sygnal_std, sampling_frequency=p["fs"], name=nazwa, time=czas, gaps=luki)
    ecg.init(
        offSetElim='off', deTrend='off', Reject='on',
        MinPeakHeight=p["MinPeakHeight"], MinPeakProminence=p["MinPeakProminence"],
        MinPeakDistance=p["MinPeakDistance"],
        RRmaxDev=p.get("RRmaxDev", 0.2), RRmin=p.get("RRmin", 0.3), RRmax=p.get("RRmax", 2.0),
    )
    return ecg


def cechy_z_ecg(ecg, p):
    """Zamienia obiekt ECG na slownik cech + ocene jakosci okna (jeden wiersz datasetu)."""
    n_beats = len(ecg.locs)
    # RR odrzucone przez variabilityReject (rrA = wszystkie, rr = po odrzuceniu)
    if len(ecg.rrA) > 0:
        odrzucone = 1 - len(ecg.rr) / len(ecg.rrA)
    else:
        odrzucone = 1.0
    ma_rr = len(ecg.rr) >= 10
    ma_roznice = ma_rr and ecg.rmsRR > 0
    # widmo ma sens dopiero przy odpowiednio dlugim zapisie: HF ~1 min, LF ~2 min
    ma_hf = ma_rr and ecg.hrvSpan >= p.get("min_okno_hf_s", 50) and ecg.hfPower > 0
    ma_lf = ma_hf and ecg.hrvSpan >= p.get("min_okno_lf_s", 110)

    return {
        "bpm": ecg.BPMlocal if ma_rr else np.nan,
        "sdnn": ecg.SDNN if ma_rr else np.nan,
        "rmssd": ecg.rmsRR if ma_roznice else np.nan,
        "pnn50": ecg.pNN50 if ma_roznice else np.nan,
        "sd1": ecg.SD1 if ma_roznice else np.nan,
        "sd2": ecg.SD2 if ma_roznice else np.nan,
        "lf": ecg.lfPower if ma_lf else np.nan,
        "hf": ecg.hfPower if ma_hf else np.nan,
        "lf_hf": ecg.lowFreqHighFreqRatio if ma_lf else np.nan,
        "n_beats": n_beats,
        "rr_reject_frac": odrzucone,
        "n_gaps": len(ecg.gaps),
        "amp_range": float(np.ptp(ecg.signal)) if ecg.len else 0.0,
        "valid": bool(ma_roznice and n_beats >= p["min_uderzen"] and odrzucone < p["max_odrzucone"]),
    }


def analizuj_okno_live(surowy, p, przytnij_s=1.0, timestamps=None):
    """Analiza bufora z pomiaru na zywo (SUROWY sygnal): filtr + odciecie brzegow
    (artefakty filtfilt) + Z-score + ECG. Zwraca slownik cech."""
    surowy = np.asarray(surowy, dtype=float)
    czas, luki = os_czasu(timestamps, len(surowy), p["fs"], p.get("prog_luki_s", 0.05))
    sygnal = apply_aidlab_bandpass_filter(
        surowy, p["fs"], p["filtr_dol"], p["filtr_gora"], p["rzad_filtru"])
    k = int(przytnij_s * p["fs"])
    if len(sygnal) > 4 * k:
        sygnal, czas = sygnal[k:-k], czas[k:-k]
    ecg = uruchom_ecg(standaryzuj(sygnal), p, "Live", czas, luki)
    return cechy_z_ecg(ecg, p)


def analizuj_nagranie(sciezka, p, baseline_s=300, okno_s=60, krok_s=15):
    """Analiza offline jednego pliku CSV (kolumny 'ECG_Value' i opcjonalnie 'Timestamp'):
    filtr + Z-score calego nagrania, potem okna okno_s co krok_s (w czasie rzeczywistym,
    z uwzglednieniem zgubionych probek).
    Etykieta: 0 = okno w calosci w baseline, 1 = okno w calosci po baseline
    (okna na granicy faz sa pomijane). Zwraca DataFrame: jedno okno = jeden wiersz,
    z kolumnami *_rel (cecha / mediana z waznych okien baseline) oraz ts_start/ts_end
    (czas bezwzgledny z opaski [ms], do synchronizacji z eye-trackerem)."""
    df = pd.read_csv(sciezka)
    if "ECG_Value" not in df.columns:
        raise ValueError("Brak kolumny 'ECG_Value' w pliku.")

    fs = p["fs"]
    sygnal_std = przygotuj_sygnal(df["ECG_Value"].to_numpy(), p)
    ts = df["Timestamp"].to_numpy(dtype=float) if "Timestamp" in df.columns else None
    czas, luki = os_czasu(ts, len(sygnal_std), fs, p.get("prog_luki_s", 0.05))
    if czas[-1] < okno_s:
        raise ValueError("Nagranie jest krotsze niz jedno okno analizy.")

    wiersze = []
    for t0 in np.arange(0, czas[-1] - okno_s + 1e-9, krok_s):
        t1 = t0 + okno_s
        if t1 <= baseline_s:
            etykieta = 0
        elif t0 >= baseline_s:
            etykieta = 1
        else:
            continue
        a, b = np.searchsorted(czas, [t0, t1])
        luki_okna = [(g0, g1) for g0, g1 in luki if g1 >= t0 and g0 <= t1]
        ecg_chunk = uruchom_ecg(sygnal_std[a:b], p, f"Okno {t0:.0f}-{t1:.0f}s", czas[a:b], luki_okna)
        cechy = cechy_z_ecg(ecg_chunk, p)
        cechy.update(plik=sciezka.replace("\\", "/").split("/")[-1],
                     t_start=t0, t_end=t1, label=etykieta)
        if ts is not None:
            # rzeczywisty Timestamp pierwszej / ostatniej probki okna (bez dryfu zegara)
            cechy.update(ts_start=ts[a], ts_end=ts[b - 1])
        wiersze.append(cechy)

    wyniki = pd.DataFrame(wiersze)
    if wyniki.empty:
        raise ValueError("Brak okien do analizy (sprawdz baseline / dlugosc okna).")

    odniesienie = wyniki[(wyniki.label == 0) & wyniki.valid][CECHY].median()
    for k in CECHY:
        ref = odniesienie[k]
        wyniki[k + "_rel"] = wyniki[k] / ref if (ref and not np.isnan(ref)) else np.nan
    return wyniki
