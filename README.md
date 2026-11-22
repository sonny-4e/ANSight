# ANSight

Ocena poziomu stresu na podstawie pracy serca (EKG z opaski Aidlab) i oczu (okulary Tobii Pro Glasses 3) z użyciem uczenia maszynowego (Projekt IPZ).

Nazwa pochodzi od **ANS** (*autonomic nervous system*, autonomiczny układ nerwowy), który pod wpływem stresu zmienia zarówno rytm serca, jak i średnicę źrenicy, oraz od *insight*.

**Status: wczesny etap rozwoju.** Gotowy jest moduł EKG (pomiar na żywo z opaski Aidlab i analiza offline). W przygotowaniu: protokół badania (kalibracja ok. 7 min, która tworzy profil osoby, i test właściwy ok. 30 min), program do odczytu danych z okularów, a potem baza danych i model.

## Co potrafi aplikacja

- **Pomiar na żywo** z opaski Aidlab (EKG, 250 Hz): wykres sygnału oraz bieżące parametry HRV (tętno, SDNN, RMSSD, pNN50) z oceną jakości okna.
- **Analiza offline** zapisanych nagrań CSV: podział na okna czasowe (domyślnie 60 s co 15 s), cechy HRV w dziedzinie czasu i częstotliwości, etykieta odpoczynek/zadanie oraz cechy względem własnej linii bazowej.
- **Wspólny silnik obliczeń** dla obu trybów, więc cechy na żywo i offline liczone są tak samo.
- **Parametry ustawiane w GUI** (filtr, progi detekcji załamków R, kryteria jakości) przed pomiarem i przed analizą.

## Parametry HRV

| Dziedzina | Cechy |
|---|---|
| Czas | BPM, SDNN, RMSSD, pNN50, SD1, SD2 |
| Częstotliwość | LF (0,04-0,15 Hz), HF (0,15-0,4 Hz), LF/HF – moc w ms² z PSD Welcha |

- **Odrzucanie RR:** granice fizjologiczne (300–2000 ms) i odchylenie od lokalnej mediany sąsiednich RR (domyślnie > 20%). RR obejmujące lukę w danych (zgubione pakiety BLE, wykrywane z kolumny `Timestamp`) są zawsze odrzucane.
- **Długość okna a widmo:** HF jest liczone, gdy prawidłowe RR pokrywają co najmniej ok. 50 s, a LF i LF/HF przy co najmniej ok. 110 s (pasmo LF zaczyna się od 0,04 Hz). W krótszych oknach te cechy mają wartość pustą (NaN).

Interpretacja parametrów i podstawy medyczne (autonomiczny układ nerwowy, HRV, ograniczenia metody) są opisane w dokumentacji w folderze `docs/`.

## Wymagania i instalacja

```
pip install -r requirements.txt
```

Moduł `aidlab` jest potrzebny tylko do pomiaru z opaski. Analiza offline działa bez niego.

## Uruchomienie

```
python main.py
```

Aplikacja ma dwie zakładki:

1. **Pomiar na żywo** – ustaw czas pomiaru, folder zapisu i parametry przetwarzania, a następnie kliknij „Połącz i start”.
2. **Analiza offline** – wskaż pliki CSV, ustaw koniec baseline'u (domyślnie 300 s) i długość okna, a następnie kliknij „Oblicz”. Wyniki zapisują się jako `features_<nazwa>.csv` obok nagrania.

## Struktura repozytorium

```
ANSight/
├── main.py            interfejs graficzny (PyQt5) i akwizycja z Aidlab
├── funkcje.py         parametry, filtrowanie, analiza nagrań
├── ECG.py             klasa ECG: detekcja R, cechy HRV
├── ECG/               oryginalny kod MATLAB
├── docs/              dokumentacja projektu (HRV, plan, podział pracy, harmonogram)
├── data/              lokalne pomiary (ignorowane przez git)
├── requirements.txt
└── README.md
```

Pliki `main.py`, `funkcje.py` i `ECG.py` muszą leżeć w jednym folderze. Folder `ECG/` zawiera tylko kod MATLAB i nie ma pliku `__init__.py`, dlatego Python wczytuje plik `ECG.py`, a nie folder. Nie należy dodawać do folderu `ECG/` plików `.py` ani `__init__.py`.

## Dokumenty projektu

W folderze `docs/`:

- `Dokumentacja projektu pomiar i analiza HRV z opaski Aidlab.pdf` – podstawy medyczne i opis liczenia HRV,
- `Plan_projektu_ANSight.pdf` – plan projektu,
- `Podzial_pracy.pdf` – zadania w zespole i kolejne kroki,
- `Harmonogram_do_kwietnia.pdf` – harmonogram do kwietnia 2027 z wykresem Gantta.

## Format danych

- **Wejście:** plik CSV z kolumnami `Timestamp` i `ECG_Value`, jedna próbka na wiersz (250 Hz).
- **Wyjście:** `features_*.csv`, jedno okno to jeden wiersz: cechy HRV, cechy względem baseline'u (`*_rel`), jakość okna (`n_beats`, `rr_reject_frac`, `n_gaps`, `valid`) oraz `t_start`, `t_end` (sekundy od początku nagrania, z uwzględnieniem luk), `ts_start`, `ts_end` (bezwzględny `Timestamp` z opaski [ms], do synchronizacji z eye-trackerem) i `label` (0 – odpoczynek, 1 – zadanie).

## Dane pomiarowe

Nagrania EKG to dane biomedyczne, dlatego nie są przechowywane w repozytorium (`data/` i pliki `aidlab_ecg_*.csv` są ignorowane przez git).

## Plan rozwoju

- [x] Przetwarzanie EKG i cechy HRV (czas i częstotliwość)
- [x] GUI: pomiar na żywo i analiza offline
- [ ] Protokół badania: kalibracja (ok. 7 min, profil osoby) i test właściwy (ok. 30 min)
- [ ] Program do odczytu parametrów z okularów Tobii Pro Glasses 3 (źrenica, spojrzenie, jakość pomiaru)
- [ ] Program do badania ze znacznikami czasu etapów
- [ ] Synchronizacja EKG i eye-trackingu z etapami badania
- [ ] Wskaźnik jakości sygnału (SQI) i odporność na artefakty ruchowe
- [ ] Dataset: cechy EKG i oczu jako zmiana względem kalibracji (delta)
- [ ] Model bazowy na cechach tabelarycznych, potem 1D-CNN
- [ ] Fuzja późna (late fusion) cech EKG i okulograficznych

Szczegółowe terminy są w `docs/Harmonogram_do_kwietnia.pdf`.
