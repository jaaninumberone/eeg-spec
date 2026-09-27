#!/usr/bin/env python3
"""Check any device profile against the spec, and report what fails and why.

This is the load-bearing part of the repo. The prose in spec/ describes intent; this
decides whether a given device actually conforms. A specification nothing is checked
against is decoration.

    python3 conformance/run_against.py reference-8ch-500
    python3 conformance/run_against.py _legacy-fixed-carrier-model   # expected to FAIL
    python3 conformance/run_against.py /path/to/private/my-board-500.json

Exit 0 conformant, 1 non-conformant, 2 unusable (malformed or missing).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eegspec import profile as P  # noqa: E402

RATES = (250, 500, 1000, 2000)


def _check(name, fn, why):
    """Run one check. Returns (name, ok, detail, why)."""
    try:
        detail = fn()
        return (name, True, detail or "ok", why)
    except P.UnverifiedClaim as e:
        return (name, False, str(e).splitlines()[0], why)
    except Exception as e:  # noqa: BLE001 - any failure is non-conformance
        return (name, False, f"{type(e).__name__}: {e}", why)


def checks(prof: dict):
    out = []

    def carrier_tracks_rate():
        fs0 = prof["firmware"]["sample_rate_hz"]["value"]
        try:
            seen = []
            for fs in RATES:
                prof["firmware"]["sample_rate_hz"]["value"] = fs
                seen.append((fs, P.carrier_hz(prof)))
        finally:
            prof["firmware"]["sample_rate_hz"]["value"] = fs0
        for fs, hz in seen:
            if abs(hz - fs / 4.0) > 1e-9:
                raise AssertionError(f"carrier {hz} Hz at fs={fs}, expected {fs/4}")
        return ", ".join(f"{fs}->{hz:g}Hz" for fs, hz in seen)

    def attenuation_rate_independent():
        fs0 = prof["firmware"]["sample_rate_hz"]["value"]
        try:
            vals = []
            for fs in RATES:
                prof["firmware"]["sample_rate_hz"]["value"] = fs
                vals.append(P.sinc3_at(prof, P.carrier_hz(prof)))
        finally:
            prof["firmware"]["sample_rate_hz"]["value"] = fs0
        if max(vals) - min(vals) > 1e-9:
            raise AssertionError(f"varies with rate: {vals}")
        return f"sinc3 = {vals[0]:.6f} at every rate"

    def scale_measured_not_inferred():
        bad = [m for m in prof.get("firmware", {}).get("modes", {})
               if P.inferred_from_register(prof, m)]
        if bad:
            raise AssertionError(
                f"scale factor justified by a PGA register in mode(s) {bad}; "
                f"a register describes the amplifier, not the conversion")
        return f"{len(prof['firmware']['modes'])} mode(s) declared independently"

    def lines_explicit():
        lines = P.interference_lines(prof)
        return f"{len(lines)} line(s) declared explicitly"

    def amplitude_convention_declared():
        v = P.value(prof, "conventions.carrier_amplitude_convention",
                    needed_for="carrier amplitude to RMS conversion")
        known = {"sine_rms", "square_rms", "legacy_sqrt2"}
        if v not in known:
            raise AssertionError(f"unknown convention {v!r}; expected one of {sorted(known)}")
        return f"{v} (declared, not inherited)"

    def intercept_stated():
        v = P.value(prof, "board.carrier_intercept_uv",
                    needed_for="impedance estimate")
        return f"intercept = {v} uV (stated, not assumed)"

    out.append(_check("carrier tracks fs/4", carrier_tracks_rate,
                      "a fixed-frequency carrier model breaks on any new sample rate"))
    out.append(_check("carrier attenuation rate-independent", attenuation_rate_independent,
                      "one calibration constant can only serve all rates if this holds"))
    out.append(_check("uV scale not inferred from register", scale_measured_not_inferred,
                      "a register value is not a measurement of the firmware's conversion"))
    out.append(_check("interference lines explicit", lines_explicit,
                      "a clock-locked comb is at fixed Hz, not at k*fs/N"))
    out.append(_check("carrier intercept stated", intercept_stated,
                      "a one-point fit silently assumes zero and is wrong at range"))
    out.append(_check("peak-to-RMS convention declared", amplitude_convention_declared,
                      "two implementations disagreeing here differ by 2x in every impedance"))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("profile")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        prof = P.load(args.profile)
    except Exception as e:  # noqa: BLE001
        print(f"UNUSABLE: {e}", file=sys.stderr)
        return 2

    print(f"profile: {prof['profile_id']}   ({prof['_source']})")
    if prof.get("description") and not args.quiet:
        print(f"  {prof['description'][:140]}")
    print()

    rows = checks(prof)
    width = max(len(n) for n, *_ in rows)
    failed = 0
    for name, ok, detail, why in rows:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name:<{width}}  {detail}")
        if not ok:
            failed += 1
            print(f"         why it matters: {why}")

    print()
    if failed:
        print(f"NON-CONFORMANT: {failed} of {len(rows)} checks failed.")
        print("Fix the profile, or measure the field and record the procedure. Do not")
        print("relax a check to make a device pass -- that is the defect being prevented.")
        return 1
    print(f"CONFORMANT: {len(rows)}/{len(rows)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
