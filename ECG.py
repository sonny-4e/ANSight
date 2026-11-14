import numpy as np
import scipy.signal as sig
from scipy.integrate import trapezoid
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt

class ECG:
    def __init__(self, ecg_signal=None, sampling_frequency=None, name='ECG', time=None, gaps=None):
        """time - opcjonalna os czasu [s] (np. z kolumny Timestamp, z uwzglednieniem luk),
        gaps - lista przerw w danych [(t_poczatek, t_koniec), ...] w tej samej osi czasu.
        RR obejmujace przerwe sa oznaczane jako nieprawidlowe."""
        self.name = name
        self.gaps = list(gaps) if gaps is not None else []

        if ecg_signal is not None and sampling_frequency is not None:
            self.signal = np.array(ecg_signal).flatten()
            self.Fs = sampling_frequency
            self.len = len(self.signal)
            T = 1.0 / self.Fs
            if time is not None:
                self.timeVal = np.asarray(time, dtype=float).flatten()
                if len(self.timeVal) != self.len:
                    raise ValueError("Os czasu musi miec tyle samo probek co sygnal.")
            else:
                self.timeVal = np.arange(self.len) * T
        else:
            self.signal = np.array([])
            self.Fs = 0
            self.len = 0
            self.timeVal = np.array([])

        self.BPMglobal = 0.0
        self.BPMlocal = 0.0
        self.SDNN = 0.0
        self.rmsRR = 0.0
        self.NN50 = 0
        self.pNN50 = 0.0
        self.IBImean = 0.0
        self.IBIrange = [0.0, 0.0]
        self.SD1 = 0.0
        self.SD2 = 0.0
        self.S_area = 0.0
        self.lfPower = 0.0
        self.hfPower = 0.0
        self.lowFreqHighFreqRatio = 0.0
        self.TotPower = 0.0
        self.LFperc = 0.0
        self.HFperc = 0.0
        self.SegmentCount = 0
        self.SegmentLength = 0
        self.Segments = []
        self.pks = np.array([])
        self.locs = np.array([])
        self.rr = np.array([])
        self.pkTimes = np.array([])
        self.rrA = np.array([])
        self.pkTimesA = np.array([])
        self.reject = np.array([])
        self.valid_idx = np.array([], dtype=bool)  # POPRAWKA: maska prawidlowych RR (potrzebna do roznic)
        self.HRV_R = np.array([])
        self.tHRV = np.array([])
        self.LHRV = 0
        self.hrvSpan = 0.0  # czas [s] pokryty prawidlowymi RR (do oceny, czy widmo ma sens)
        self.FsHRV = 4
        self.fftHRV = np.array([])
        self.p1 = np.array([])
        self.hf = np.array([])
        self.p1HF = np.array([])
        self.lf = np.array([])
        self.p1LF = np.array([])
        self.segmentBoundaries = np.array([])

    def init(self, **kwargs):
        off_set_elim = kwargs.get('offSetElim', 'on')
        de_trend = kwargs.get('deTrend', 'on')
        if off_set_elim.lower() == 'on':
            self.offsetEliminate()
        if de_trend.lower() == 'on':
            self.deTrending(**kwargs)
        self.peakDetect(**kwargs)
        self.variabilityReject(**kwargs)
        self.calculateHRVNumerics()
        self.resampleHRV()
        self.freqAnalysisHRV()

    def offsetEliminate(self):
        self.signal = self.signal - np.mean(self.signal)

    def deTrending(self, **kwargs):
        ord_val = kwargs.get('ORD', 3)
        fl_val = kwargs.get('FL', 9999)
        if fl_val % 2 == 0:
            fl_val += 1
        fl_val = min(fl_val, self.len if self.len % 2 != 0 else self.len - 1)
        if fl_val < ord_val + 2:
            return
        trend = sig.savgol_filter(self.signal, window_length=fl_val, polyorder=ord_val)
        self.signal = self.signal - trend

    def filter(self, b, a, **kwargs):
        self.signal = sig.filtfilt(b, a, self.signal)

    def peakDetect(self, **kwargs):
        prominence = kwargs.get('MinPeakProminence', 0.1)
        distance = kwargs.get('MinPeakDistance', 0.4)
        height = kwargs.get('MinPeakHeight', 0.5)
        distance_samples = int(distance * self.Fs)
        peaks, properties = sig.find_peaks(self.signal, prominence=prominence, distance=distance_samples, height=height)
        self.locs = self.timeVal[peaks]
        self.pks = self.signal[peaks]
        if len(self.locs) > 1:
            self.BPMglobal = (len(self.locs) / (self.len / self.Fs)) * 60
            self.rr = np.diff(self.locs)
            self.pkTimes = self.locs[1:]  # RR przypisany do uderzenia, ktore go konczy
            self.BPMlocal = 60 / np.mean(self.rr)

    def variabilityReject(self, **kwargs):
        """Odrzucanie nieprawidlowych RR (artefakty, zgubione/dodatkowe uderzenia, luki w danych).

        Kryteria:
          1) granice fizjologiczne: RRmin <= RR <= RRmax [s],
          2) RR odbiega od mediany sasiednich RR o wiecej niz RRmaxDev (np. 0.2 = 20%),
          3) RR obejmuje przerwe w danych (self.gaps).
        W odroznieniu od progu srednia +- k*SD nie wyrzuca prawidlowych uderzen
        z czystego sygnalu i nie 'scina' prawdziwej zmiennosci rytmu."""
        self.rrA = self.rr.copy()
        self.pkTimesA = self.pkTimes.copy()
        n = len(self.rrA)
        valid = np.ones(n, dtype=bool)

        if kwargs.get('Reject', 'on') == 'on' and n > 0:
            rr_min = kwargs.get('RRmin', 0.3)
            rr_max = kwargs.get('RRmax', 2.0)
            max_dev = kwargs.get('RRmaxDev', 0.2)
            half = kwargs.get('RRmedianHalfWidth', 5)

            valid &= (self.rrA >= rr_min) & (self.rrA <= rr_max)
            for i in range(n):
                lo, hi = max(0, i - half), min(n, i + half + 1)
                sasiedzi = np.r_[self.rrA[lo:i], self.rrA[i + 1:hi]]
                sasiedzi = sasiedzi[(sasiedzi >= rr_min) & (sasiedzi <= rr_max)]
                if len(sasiedzi) >= 2:
                    med = np.median(sasiedzi)
                    if abs(self.rrA[i] - med) > max_dev * med:
                        valid[i] = False

        # RR, ktorego przedzial [poprzednie R, R] nachodzi na przerwe w danych, jest niewiarygodny
        if n > 0 and self.gaps:
            margines = kwargs.get('GapMargin', 0.3)
            pocz = self.locs[:-1]
            kon = self.locs[1:]
            for g0, g1 in self.gaps:
                valid &= ~((pocz <= g1 + margines) & (kon >= g0 - margines))

        self.valid_idx = valid
        self.rr = self.rrA[valid]
        self.pkTimes = self.pkTimesA[valid]
        if len(self.rr) > 0:
            self.BPMlocal = 60 / np.mean(self.rr)

    def calculateHRVNumerics(self):
        if len(self.rr) < 2: return
        self.SDNN = np.std(self.rr * 1000, ddof=1)
        self.IBImean = np.mean(self.rr * 1000)
        self.IBIrange = [np.min(self.rr * 1000), np.max(self.rr * 1000)]

        # roznice (RMSSD, NN50, SD1/SD2) tylko miedzy SASIEDNIMI prawidlowymi RR
        baza = self.rrA
        para = self.valid_idx[:-1] & self.valid_idx[1:]
        differences = np.diff(baza)[para]
        if len(differences) < 2: return

        self.rmsRR = np.sqrt(np.mean(differences**2)) * 1000
        self.NN50 = np.sum(np.abs(differences * 1000) > 50)
        self.pNN50 = self.NN50 * 100.0 / len(differences)
        pmX = baza[:-1][para] * 1000
        pmY = baza[1:][para] * 1000
        self.SD1 = np.std(pmX - pmY, ddof=1) / np.sqrt(2)
        self.SD2 = np.std(pmX + pmY, ddof=1) / np.sqrt(2)

    def resampleHRV(self, FsHRV=4):
        """Interpolacja prawidlowych RR [ms] do rownomiernej siatki FsHRV [Hz] (tachogram)."""
        self.FsHRV = FsHRV
        THRV = 1.0 / self.FsHRV
        self.hrvSpan = float(self.pkTimes[-1] - self.pkTimes[0]) if len(self.pkTimes) > 1 else 0.0
        if len(self.pkTimes) >= 4:
            interp_func = interp1d(self.pkTimes, self.rr * 1000, kind='cubic')
            self.tHRV = np.arange(self.pkTimes[0], self.pkTimes[-1], THRV)
            self.HRV_R = interp_func(self.tHRV)
            self.LHRV = len(self.HRV_R)
            self.tHRV = np.arange(self.LHRV) * THRV

    def freqAnalysisHRV(self):
        """Gestosc widmowa mocy (Welch, okno Hanna, detrend liniowy) tachogramu w ms^2/Hz,
        moc w pasmach = calka PSD [ms^2] - tak jak w Kubios / Task Force 1996."""
        if self.LHRV < 16: return
        y = self.HRV_R - np.mean(self.HRV_R)
        nperseg = min(256, self.LHRV)
        self.fftHRV, self.p1 = sig.welch(y, fs=self.FsHRV, window='hann', nperseg=nperseg,
                                         noverlap=nperseg // 2, detrend='linear')

        lf_idx = (self.fftHRV >= 0.04) & (self.fftHRV < 0.15)
        self.lf = self.fftHRV[lf_idx]
        self.p1LF = self.p1[lf_idx]
        self.lfPower = trapezoid(self.p1LF, self.lf) if lf_idx.sum() > 1 else 0.0

        hf_idx = (self.fftHRV >= 0.15) & (self.fftHRV <= 0.4)
        self.hf = self.fftHRV[hf_idx]
        self.p1HF = self.p1[hf_idx]
        self.hfPower = trapezoid(self.p1HF, self.hf) if hf_idx.sum() > 1 else 0.0

        if self.hfPower > 0:
            self.lowFreqHighFreqRatio = self.lfPower / self.hfPower
        self.TotPower = self.lfPower + self.hfPower
        if self.TotPower > 0:
            self.LFperc = self.lfPower * 100 / self.TotPower
            self.HFperc = 100 - self.LFperc

    def dispHRVNumerics(self):
        print(f"Heartrate from Number of Peaks: {self.BPMglobal:.2f} bpm")
        print(f"Heartrate from RR intervals: {self.BPMlocal:.2f} bpm")
        print(f"SDNN: {self.SDNN:.2f} ms")
        print(f"RMSSD: {self.rmsRR:.2f} ms")
        print(f"NN50: {self.NN50}")
        print(f"pNN50: {self.pNN50:.2f} %")
        print(f"SD1: {self.SD1:.2f} ms")
        print(f"SD2: {self.SD2:.2f} ms")
        if self.SD2 > 0:
            print(f"SD1/SD2: {(self.SD1/self.SD2)*100:.2f} %")

    def dispPower(self):
        print(f"Total Power: {self.TotPower:.2f} ms^2")
        print(f"LF Power: {self.lfPower:.2f} ms^2")
        print(f"HF Power: {self.hfPower:.2f} ms^2")
        if self.hfPower > 0:
            print(f"LF/HF Ratio: {self.lowFreqHighFreqRatio:.2f}")
        print(f"LF|HF: {self.LFperc:.2f} % | {self.HFperc:.2f} %")