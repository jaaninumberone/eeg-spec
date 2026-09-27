"""Derived spectral quantities. No clinical definitions and no thresholds.

What a measurement means for a person is a separate question with a different evidentiary
standard (spec 50.5). This module computes band power and generic ratios; it does not name
them clinically and does not judge them.
"""
from __future__ import annotations

import numpy as np


def relative_band_power(bands: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Each band as a fraction of the total across all bands."""
    total = sum(bands.values())
    with np.errstate(divide="ignore", invalid="ignore"):
        return {k: np.where(total > 0, v / total, np.nan) for k, v in bands.items()}


def band_ratio(bands: dict[str, np.ndarray], num: str, den: str) -> np.ndarray:
    """A ratio of two band powers.

    Ratios cancel any constant scale factor, which is why they survive an unverified
    uv_scale_factor while absolute power does not -- and also why a wrong scale factor can
    persist unnoticed behind them.
    """
    if num not in bands or den not in bands:
        raise KeyError(f"need bands {num!r} and {den!r}; have {sorted(bands)}")
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(bands[den] > 0, bands[num] / bands[den], np.nan)
