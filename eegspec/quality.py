"""Epoch gating and impedance. Implements spec 40.6 and 40.7.

Both are places where a plausible wrong number is easy to produce and hard to notice, so
both report more than their result: gating reports what each gate rejected, and impedance
reports which calibration route it used and keeps its sign.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import profile as P


# ── epoch gating ─────────────────────────────────────────────────────────────

@dataclass
class GateResult:
    kept: np.ndarray                      # (n_kept, epoch_len, n_channels)
    n_epochs: int = 0
    rejected_by: dict[str, int] = field(default_factory=dict)
    retention: float = 0.0
    notes: list[str] = field(default_factory=list)


def gate_epochs(x: np.ndarray, fs: float, prof: dict,
                gate_signal: np.ndarray | None = None) -> GateResult:
    """Split into epochs and reject contaminated ones.

    ``gate_signal`` lets gates read a different montage from the one the epochs are cut
    from -- legitimate, and R-40.6 requires each to say which it read.

    R-40.13: the per-gate counts are the cheapest diagnostic in the chain and are usually
    missing. Two failures they catch at a glance: a gate that fires on NOTHING, which is
    dead weight carrying unearned credibility, and a gate that fires on almost
    EVERYTHING, which is not selecting epochs but setting the retention rate by itself.
    """
    thresholds = P.value(prof, "conventions.epoch_gates",
                         needed_for="epoch rejection")
    epoch_s = float(P.value(prof, "conventions.epoch_seconds",
                            needed_for="epoch rejection"))
    n = int(round(epoch_s * fs))
    if n < 8 or x.shape[0] < n:
        return GateResult(np.empty((0, max(n, 1), x.shape[1])), 0, {}, 0.0,
                          ["recording shorter than one epoch"])

    src = x if gate_signal is None else gate_signal
    n_ep = x.shape[0] // n
    ep = x[: n_ep * n].reshape(n_ep, n, x.shape[1])
    gs = src[: n_ep * n].reshape(n_ep, n, src.shape[1])

    keep = np.ones(n_ep, dtype=bool)
    counts: dict[str, int] = {}

    def apply(name: str, bad: np.ndarray) -> None:
        # count against epochs still alive, so the numbers sum to the rejections
        fires = int((bad & keep).sum())
        counts[name] = fires
        keep[bad] = False

    if "max_p2p_uv" in thresholds:
        p2p = gs.max(axis=1) - gs.min(axis=1)
        apply("p2p", np.any(p2p > float(thresholds["max_p2p_uv"]), axis=1))
    if "max_std_uv" in thresholds:
        apply("std", np.any(gs.std(axis=1) > float(thresholds["max_std_uv"]), axis=1))
    if "min_std_uv" in thresholds:
        apply("flat", np.any(gs.std(axis=1) < float(thresholds["min_std_uv"]), axis=1))
    if "max_gradient_uv_per_sample" in thresholds:
        grad = np.abs(np.diff(gs, axis=1)).max(axis=1)
        apply("gradient",
              np.any(grad > float(thresholds["max_gradient_uv_per_sample"]), axis=1))

    notes = []
    for name, c in counts.items():
        if c == 0:
            notes.append(f"gate {name!r} rejected nothing on this recording")
        elif c >= 0.9 * n_ep:
            notes.append(f"gate {name!r} rejected {c}/{n_ep} epochs and is setting "
                         f"retention by itself")
    return GateResult(ep[keep], n_ep, counts, float(keep.sum()) / n_ep, notes)


# ── impedance ────────────────────────────────────────────────────────────────

def rms_from_vpp(vpp: float | np.ndarray, convention: str):
    """Peak-to-peak to RMS, by declared convention (spec 40.7, R-40.15).

    The three differ by up to 2x, so an implementation that inherits one silently reports
    every impedance at twice another's with nothing in the output to reveal it.
    """
    if convention == "sine_rms":
        return vpp / (2.0 * math.sqrt(2.0))
    if convention == "square_rms":
        return vpp / 2.0
    if convention == "legacy_sqrt2":
        return vpp / math.sqrt(2.0)
    raise ValueError(f"R-40.15: unknown amplitude convention {convention!r}")


def carrier_amplitude(x: np.ndarray, fs: float, carrier_hz: float,
                      block_s: float = 2.0) -> np.ndarray:
    """Per-channel carrier amplitude: coherent fit per block, median across blocks.

    A whole-record transform assumes the carrier stays phase-coherent for the whole
    recording; one sample slip destroys that and the estimate collapses, silently and
    downward -- which reads as a BETTER electrode. Per-block fitting is immune, and the
    median is robust to the blocks that are genuinely disturbed.
    """
    n = int(block_s * fs)
    nb = x.shape[0] // n
    if nb < 1:
        raise ValueError("recording shorter than one carrier block")
    t = np.arange(n) / fs
    D = np.column_stack([np.sin(2 * np.pi * carrier_hz * t),
                         np.cos(2 * np.pi * carrier_hz * t)])
    out = []
    for ch in range(x.shape[1]):
        amps = []
        for b in range(nb):
            seg = x[b * n:(b + 1) * n, ch]
            seg = seg - seg.mean()
            c, *_ = np.linalg.lstsq(D, seg, rcond=None)
            amps.append(float(np.hypot(*c)))
        out.append(float(np.median(amps)))
    return np.array(out)


def impedance_kohm(raw_uv: np.ndarray, fs: float, prof: dict) -> dict:
    """Electrode impedance per channel, in kOhm. R-40.14 through R-40.17.

    Two routes, and the payload says which was used:

      ladder    Z_total = (A - intercept) / slope. Preferred: the constants are fitted
                on the real analogue chain and absorb everything between injection and
                ADC. Needs a two-point resistor ladder to establish.
      ohms_law  Z_total = Vrms / I. Needs only datasheet values, and is therefore the
                fallback when no ladder has been run -- but it inherits every unmodelled
                gain in the path.

    The result stays SIGNED (R-40.17). A negative electrode impedance is physically
    impossible, so it is a calibration error announcing itself; abs() turns that
    announcement into a reassuring small positive reading on a shorted electrode.
    """
    carrier = P.carrier_hz(prof)
    if carrier >= fs / 2.0:
        raise ValueError(
            f"carrier at {carrier} Hz is at or above Nyquist for fs={fs}; "
            f"the impedance branch must read the RAW signal (R-40.14)")
    amp = carrier_amplitude(raw_uv, fs, carrier)
    r_series_kohm = float(P.value(prof, "board.r_series_ohm",
                                  needed_for="impedance")) / 1000.0

    have_ladder = (P.claim(prof, "board.carrier_slope_uv_per_kohm")["provenance"]
                   != "unverified")
    if have_ladder:
        slope = float(P.value(prof, "board.carrier_slope_uv_per_kohm",
                              needed_for="impedance"))
        icept = float(P.value(prof, "board.carrier_intercept_uv",
                              needed_for="impedance"))
        z_total = (amp - icept) / slope
        route = "ladder"
    else:
        conv = P.value(prof, "conventions.carrier_amplitude_convention",
                       needed_for="impedance")
        i_na = float(P.value(prof, "chip.lead_off_current_na", needed_for="impedance"))
        vrms = rms_from_vpp(2.0 * amp, conv)
        z_total = vrms / (i_na / 1000.0) / 1000.0     # uV / uA -> ohm -> kohm
        route = f"ohms_law[{conv}]"

    z_elec = z_total - r_series_kohm
    return {
        "route": route,
        "carrier_hz": carrier,
        "carrier_amplitude_uv": [round(float(a), 3) for a in amp],
        "z_total_kohm": [round(float(v), 2) for v in z_total],
        "z_electrode_kohm": [round(float(v), 2) for v in z_elec],   # signed
        "negative_channels": [i for i, v in enumerate(z_elec) if v < 0],
    }
