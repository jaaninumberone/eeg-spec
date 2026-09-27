"""CSV to report payload, end to end. The reference implementation of spec 40 and 50.

Nothing here carries a device constant. Every parameter is read from the profile, and a
field the profile marks unverified stops the run rather than being guessed.
"""
from __future__ import annotations

import numpy as np

from . import dsp, io, metrics, profile as P, quality

VERSION = "eeg-spec/0.2.0-phase3"


def _unavailable(reason: str) -> dict:
    """R-50.3: absent-for-a-reason, never silently omitted."""
    return {"available": False, "value": None, "n": 0, "reason": reason}


def run(path, prof: dict, *, mode: str = "eeg",
        dialect: io.Dialect | None = None) -> dict:
    """Process one recording into a payload conforming to spec section 50."""
    rec = io.read(path, prof, dialect=dialect, mode=mode)

    payload: dict = {
        "pipeline_version": VERSION,                       # R-50.6
        "profile_id": prof.get("profile_id"),              # R-50.6
        "mode": mode,
        "source": {
            "file": rec.source,
            "samples": rec.n_samples,
            "duration_s": round(rec.duration_s, 3),
            "fs_hz": rec.fs_hz,
            "timebase": rec.timebase,                      # measured | asserted
            "gaps": len(rec.gaps),
            "dialect": rec.dialect,
        },
        "warnings": [],
        "metrics": {},
        "impedance": None,
        "quality": None,
    }

    if rec.timebase == "asserted":
        payload["warnings"].append(
            "R-30.8: the timebase is asserted, not measured. This file cannot express a "
            "gap, so any gap-dependent result from it is unverified.")
    if rec.gaps:
        payload["warnings"].append(
            f"{len(rec.gaps)} gap(s) in the timebase; they were preserved, not closed up.")

    # ---- absolute units, if the profile earned them -------------------------
    try:
        x_uv = io.to_microvolts(rec, prof, mode)
        absolute_ok = True
    except P.UnverifiedClaim as e:
        x_uv = rec.data
        absolute_ok = False
        payload["warnings"].append(
            "absolute units unavailable: " + str(e).splitlines()[0] +
            " Ratios below remain valid; absolute power does not.")

    # ---- impedance reads the RAW, undecimated signal (R-40.14) --------------
    mode_block = prof["firmware"]["modes"][mode]
    has_carrier = bool(mode_block.get("carrier_present", {}).get("value", False))
    if has_carrier:
        try:
            payload["impedance"] = quality.impedance_kohm(x_uv, rec.fs_hz, prof)
            neg = payload["impedance"]["negative_channels"]
            if neg:
                payload["warnings"].append(
                    f"R-40.17: channels {neg} report NEGATIVE electrode impedance. That is "
                    f"physically impossible, so it is the calibration announcing an error. "
                    f"The value is left signed deliberately.")
        except Exception as e:                              # noqa: BLE001
            payload["impedance"] = _unavailable(f"{type(e).__name__}: {e}")
    else:
        payload["impedance"] = _unavailable(
            f"mode {mode!r} declares no impedance carrier")

    # ---- main branch --------------------------------------------------------
    x, fs, trimmed = dsp.antialias_and_decimate(x_uv, prof)
    corner = 1.0
    edges = P.value(prof, "conventions.band_edges_hz", needed_for="high-pass corner")
    if edges:
        corner = min(lo for lo, _ in edges.values())
    x = dsp.highpass(x, fs, corner)
    referenced = dsp.common_reference(x)
    x, notched = dsp.suppress_lines(x, fs, prof)
    payload["source"]["decimated_to_hz"] = fs
    payload["source"]["edge_trim_samples"] = trimmed
    payload["source"]["notched_hz"] = notched

    # R-40.6/R-40.7: gates read the referenced montage, metrics the unreferenced one.
    g = quality.gate_epochs(x, fs, prof, gate_signal=dsp.common_reference(x))
    payload["quality"] = {
        "epochs": g.n_epochs,
        "kept": int(g.kept.shape[0]),
        "retention": round(g.retention, 4),
        "rejected_by": g.rejected_by,                       # R-40.13
        "gate_montage": "common-referenced",
        "metric_montage": "unreferenced",
        "notes": g.notes,
    }
    payload["warnings"] += g.notes

    if g.kept.shape[0] < 2:
        payload["metrics"] = {"band_power": _unavailable(
            f"only {g.kept.shape[0]} epoch(s) survived gating")}
        return payload

    flat = g.kept.reshape(-1, g.kept.shape[2])
    f, pxx = dsp.psd(flat, fs)
    bands = dsp.band_power(f, pxx, prof)
    rel = metrics.relative_band_power(bands)
    n_ep = int(g.kept.shape[0])

    payload["metrics"]["band_power"] = {
        "available": absolute_ok, "n": n_ep,
        "unit": "uV^2" if absolute_ok else "file_units^2",
        "value": {k: [round(float(v), 6) for v in np.atleast_1d(vv)]
                  for k, vv in bands.items()},
        **({} if absolute_ok else
           {"reason": "uv_scale_factor unverified; values are in file units"}),
    }
    payload["metrics"]["relative_band_power"] = {
        "available": True, "n": n_ep, "unit": "fraction",
        "value": {k: [round(float(v), 6) for v in np.atleast_1d(vv)]
                  for k, vv in rel.items()},
        "note": "Ratios cancel a constant scale factor and are valid regardless of "
                "whether absolute units were available.",
    }

    # R-50.4/R-50.5: uncertainty is mandatory, and 'unmeasured' is a valid answer.
    payload["metrics"]["noise_floor"] = _unavailable(
        "Test-retest variability has not been measured for this profile. No change "
        "reported from this payload can be said to exceed measurement noise.")
    return payload
