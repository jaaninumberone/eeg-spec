"""The main processing branch. Every parameter comes from the profile.

Implements section 40.1-40.5. No stage may carry a device constant as a literal.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, firwin, iirnotch, filtfilt, sosfiltfilt, tf2sos, welch
from scipy.integrate import trapezoid

from . import profile as P

#: Butterworth order for the drift high-pass. A chain property, not a device one.
HIGHPASS_ORDER = 4
#: Notch sharpness. Narrow enough not to eat a band, wide enough to catch a steady line.
NOTCH_Q = 30.0


def decimation_factor(prof: dict) -> int:
    """R-40.1: an integer, or a refusal. Never a rounded ratio."""
    fs = float(P.value(prof, "firmware.sample_rate_hz", needed_for="decimation"))
    target = P.value(prof, "conventions.analysis_rate_hz", needed_for="decimation")
    if target is None:
        return 1
    ratio = fs / float(target)
    m = int(round(ratio))
    if m < 1 or abs(ratio - m) > 1e-9:
        raise ValueError(
            f"R-40.1: {fs} Hz / {target} Hz = {ratio:.6f} is not an integer.\n"
            f"  Refusing rather than rounding. Either declare an analysis rate that\n"
            f"  divides this device's source rate, or resample explicitly -- a target\n"
            f"  chosen because it divides some OTHER device's rate is not a property of\n"
            f"  this method.")
    return m


def antialias_and_decimate(x: np.ndarray, prof: dict) -> tuple[np.ndarray, float, int]:
    """R-40.2/R-40.3. Returns (signal, new_fs, samples trimmed per side)."""
    m = decimation_factor(prof)
    fs = float(P.value(prof, "firmware.sample_rate_hz", needed_for="anti-alias"))
    if m == 1:
        return x, fs, 0
    new_fs = fs / m
    nyq_new = new_fs / 2.0
    passband = nyq_new * 0.72
    stopband = nyq_new * 0.98
    numtaps = int(8 * fs / (stopband - passband)) | 1     # odd, symmetric
    taps = firwin(numtaps, (passband + stopband) / 2.0, window="blackman", fs=fs)
    y = filtfilt(taps, [1.0], x, axis=0)
    # R-40.3: filtfilt's reflection padding leaves a transient at each end.
    trim = numtaps - 1
    if y.shape[0] <= 2 * trim + m:
        raise ValueError(f"R-40.3: recording too short to trim {trim} samples per side")
    y = y[trim:-trim]
    return y[::m], new_fs, trim


def highpass(x: np.ndarray, fs: float, corner_hz: float) -> np.ndarray:
    """R-40.5: second-order sections, always.

    Transfer-function form at very low normalised frequencies loses precision
    catastrophically -- coefficients spanning many orders of magnitude produce output far
    larger than the input, which then trips every amplitude gate downstream and rejects
    the whole recording. It fails loudly, but only after several plausible-looking steps.
    """
    sos = butter(HIGHPASS_ORDER, corner_hz / (fs / 2.0), "highpass", output="sos")
    return sosfiltfilt(sos, x, axis=0)


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    sos = butter(4, [lo / (fs / 2.0), hi / (fs / 2.0)], "bandpass", output="sos")
    return sosfiltfilt(sos, x, axis=0)


def common_reference(x: np.ndarray, channels: list[int] | None = None) -> np.ndarray:
    """Subtract the across-channel mean, sample by sample.

    R-40.7 is the trap: after this, that mean is identically zero BY CONSTRUCTION. Any
    statistic defined across channels silently becomes a statistic of nothing. Compute
    such measures on the unreferenced signal.
    """
    cols = list(range(x.shape[1])) if channels is None else list(channels)
    return x - x[:, cols].mean(axis=1, keepdims=True)


def suppress_lines(x: np.ndarray, fs: float, prof: dict) -> tuple[np.ndarray, list[float]]:
    """R-40.8: notch only at declared frequencies. Never at k*fs/N.

    Returns (signal, frequencies actually notched). Lines at or above Nyquist are skipped
    rather than wrapped, and reported so the caller can see what was left alone.
    """
    lines = list(P.interference_lines(prof))
    mains = P.claim(prof, "firmware.mains_hz")["value"] if "mains_hz" in prof.get("firmware", {}) else None
    if mains:
        lines.append(float(mains))
    applied = []
    y = x
    for f0 in sorted(set(float(f) for f in lines)):
        if not (0 < f0 < fs / 2.0):
            continue
        b, a = iirnotch(f0, NOTCH_Q, fs)
        y = sosfiltfilt(tf2sos(b, a), y, axis=0)
        applied.append(f0)
    return y, applied


def psd(x: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """R-40.10: segment length an integer multiple of fs, so integer-Hz tones land on
    bin centres rather than straddling two and leaking into their neighbours."""
    seg = int(round(fs)) * max(1, int(4 * fs // max(int(round(fs)), 1)))
    seg = min(seg, x.shape[0])
    if seg < 8:
        raise ValueError("too few samples for a spectral estimate")
    f, pxx = welch(x, fs=fs, nperseg=seg, noverlap=seg // 2,
                   window="blackman", axis=0)
    return f, pxx


def band_power(f: np.ndarray, pxx: np.ndarray, prof: dict) -> dict[str, np.ndarray]:
    """R-40.11: band edges come from the profile."""
    edges = P.value(prof, "conventions.band_edges_hz", needed_for="band power")
    out = {}
    for name, (lo, hi) in edges.items():
        m = (f >= lo) & (f < hi)
        out[name] = trapezoid(pxx[m], f[m], axis=0) if m.sum() > 1 else np.zeros(pxx.shape[1])
    return out
