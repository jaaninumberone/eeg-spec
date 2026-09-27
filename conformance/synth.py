"""Synthetic recordings built from a profile. No patient data anywhere in this repo.

Every fixture the conformance suite needs is generated here from the profile's own
declared parameters, which is what lets the public tree carry no recordings at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eegspec import profile as P  # noqa: E402


def make(prof: dict, *, seconds: float = 20.0, n_channels: int = 4,
         alpha_uv: float = 12.0, carrier_for_kohm: float | None = None,
         line_uv: float = 0.0, gap_at_s: float | None = None,
         seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Return (t_ms, data). Pink-ish background, an alpha bump, optional extras.

    ``carrier_for_kohm`` injects a carrier whose amplitude corresponds to that electrode
    impedance THROUGH THE PROFILE's own calibration, so a round-trip through the pipeline
    is a real test of the calibration path rather than of a hard-coded constant.
    """
    rng = np.random.default_rng(seed)
    fs = float(P.value(prof, "firmware.sample_rate_hz", needed_for="synthesis"))
    n = int(seconds * fs)
    t = np.arange(n) / fs

    # 1/f-ish background via cumulative sum, per channel, then a narrowband bump
    x = np.cumsum(rng.standard_normal((n, n_channels)), axis=0)
    x = (x - x.mean(axis=0)) / x.std(axis=0) * 8.0
    for ch in range(n_channels):
        x[:, ch] += alpha_uv * np.sin(2 * np.pi * 10.0 * t + rng.uniform(0, 6.28))

    if carrier_for_kohm is not None:
        slope = float(P.value(prof, "board.carrier_slope_uv_per_kohm",
                              needed_for="synthesis"))
        icept = float(P.value(prof, "board.carrier_intercept_uv",
                              needed_for="synthesis"))
        r_kohm = float(P.value(prof, "board.r_series_ohm",
                               needed_for="synthesis")) / 1000.0
        amp = slope * (carrier_for_kohm + r_kohm) + icept
        x += amp * np.sin(2 * np.pi * P.carrier_hz(prof) * t)[:, None]

    if line_uv:
        mains = float(prof["firmware"]["mains_hz"]["value"])
        x += line_uv * np.sin(2 * np.pi * mains * t)[:, None]

    t_ms = t * 1000.0
    if gap_at_s is not None:
        cut = int(gap_at_s * fs)
        keep = np.r_[np.arange(cut), np.arange(cut + int(0.5 * fs), n)]
        x, t_ms = x[keep], t_ms[keep]
    return t_ms, x


def write_csv(path, t_ms: np.ndarray, data: np.ndarray) -> Path:
    """Canonical form: t_ms, ch1..chN."""
    path = Path(path)
    head = "t_ms," + ",".join(f"ch{i+1}" for i in range(data.shape[1]))
    rows = [head]
    for i in range(len(t_ms)):
        rows.append(f"{t_ms[i]:.3f}," + ",".join(f"{v:.6f}" for v in data[i]))
    path.write_text("\n".join(rows) + "\n")
    return path


def write_legacy_csv(path, t_ms: np.ndarray, data: np.ndarray) -> Path:
    """A dialect: a metadata line, a typo'd header, and a bare sample counter.

    All three have been observed together. A reader that assumes line 0 is the header
    treats the real header as data and returns zero rows -- indistinguishable from a file
    that legitimately has none.
    """
    path = Path(path)
    rows = [" EEG data save here   Date-> 01::01::2026",
            "count, ch1(micro volts),ch2(micro volts),ch3(micro volts),ch4(micro volts)"]
    for i in range(len(t_ms)):
        rows.append(f"{i}," + ",".join(f"{v:.6f}" for v in data[i]))
    path.write_text("\n".join(rows) + "\n")
    return path
