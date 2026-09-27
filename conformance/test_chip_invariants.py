"""Chip-invariant behaviour every ADS1299 profile must satisfy.

These tests encode four beliefs that an existing implementation gets wrong, and they are
written so that the wrong version FAILS. A conformance suite that passes on the thing it
was written to correct has proved nothing, so `_legacy-fixed-carrier-model.json` is kept
in the tree purely to be failed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eegspec import profile as P  # noqa: E402

REFERENCE = "reference-8ch-500"
LEGACY = "_legacy-fixed-carrier-model"


@pytest.fixture
def ref():
    return P.load(REFERENCE)


@pytest.fixture
def legacy():
    return P.load(LEGACY)


# ── 1 · the carrier tracks the sample rate ───────────────────────────────────

@pytest.mark.parametrize("fs,expected", [(250, 62.5), (500, 125.0), (1000, 250.0),
                                         (2000, 500.0)])
def test_carrier_is_fs_over_four_at_every_rate(ref, fs, expected):
    """With FLEAD_OFF=11 the lead-off source runs at fDR/4, so the carrier MOVES with fs.

    The rates matter. A 'fixed 125 Hz physical carrier' model agrees with fs/4 at 500 sps
    and is fudged into agreeing at 250 sps, which is why it survived: those are the only
    two rates the hardware has ever run at. It diverges at 1000 and 2000 sps -- so the
    error is invisible until someone builds the next device, which is exactly the failure
    a device-agnostic spec exists to prevent.
    """
    ref["firmware"]["sample_rate_hz"]["value"] = fs
    assert P.carrier_hz(ref) == pytest.approx(expected)


def test_carrier_attenuation_is_rate_independent(ref):
    """sinc^3 at the carrier is the same constant at every rate, because the carrier is at
    a fixed FRACTION of fs. This is why one calibration constant serves all rates -- and
    it only holds if the carrier tracks fs."""
    seen = []
    for fs in (250, 500, 1000):
        ref["firmware"]["sample_rate_hz"]["value"] = fs
        seen.append(P.sinc3_at(ref, P.carrier_hz(ref)))
    assert max(seen) - min(seen) < 1e-9
    assert seen[0] == pytest.approx(0.729766, abs=1e-5)


# ── 2 · the microvolt scale is measured, never inferred from a register ──────

def test_scale_factor_not_inferred_from_pga_register(ref):
    """A PGA register describes the amplifier. The firmware's conversion is a separate
    thing, and only a known differential input settles what it actually did."""
    for mode_name in ref["firmware"]["modes"]:
        assert not P.inferred_from_register(ref, mode_name), (
            f"{mode_name}: scale factor justified by a register value")


def test_legacy_scale_factor_is_caught(legacy):
    """The failing case, kept so the check is known to bite."""
    assert P.inferred_from_register(legacy, "eeg")


# ── 3 · interference lines are explicit, not derived from fs ─────────────────

def test_interference_lines_are_declared_not_derived(ref):
    lines = P.interference_lines(ref)
    assert isinstance(lines, list)


def test_lines_derived_from_sample_rate_are_refused(legacy):
    """A comb locked to a clock sits at fixed frequencies. Expressing it as k*fs/20
    happens to be right at one rate and wrong at every other, so that provenance is
    'unverified' and must refuse rather than return four plausible numbers."""
    with pytest.raises(P.UnverifiedClaim) as e:
        P.interference_lines(legacy)
    assert "interference" in str(e.value).lower()


# ── 4 · carrier calibration has an intercept ─────────────────────────────────

def test_carrier_calibration_declares_an_intercept(ref):
    """The carrier response is not through the origin. A single-point fit forces it
    through zero and folds the intercept into the slope; on real hardware that is
    measurably wrong at the far end of the impedance range. The intercept may legitimately be zero --
    but it must be stated, because 'zero' and 'never measured' are different claims."""
    assert P.claim(ref, "board.carrier_intercept_uv")["provenance"] != "unverified"


def test_legacy_intercept_refuses(legacy):
    with pytest.raises(P.UnverifiedClaim):
        P.value(legacy, "board.carrier_intercept_uv", needed_for="impedance estimate")


# ── the general rule ─────────────────────────────────────────────────────────

def test_unverified_claim_refuses_with_a_usable_message(legacy):
    with pytest.raises(P.UnverifiedClaim) as e:
        P.carrier_hz(legacy)
    msg = str(e.value)
    assert "unverified" in msg
    assert "Do not proceed" in msg


def test_reference_profile_has_no_unverified_claims(ref):
    """The reference must be usable end to end, or it cannot anchor the suite."""
    bad = []

    def walk(node, path):
        if isinstance(node, dict):
            if "provenance" in node and node["provenance"] == "unverified":
                bad.append(path)
                return
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else k)

    walk(ref, "")
    assert not bad, f"unverified claims in the reference profile: {bad}"


# ── 5 · the peak-to-RMS convention is declared, never inherited ──────────────

def test_amplitude_convention_is_declared(ref):
    """Surfaced by porting a real implementation, which converts Vpp to RMS with a factor
    its own prose calls a legacy convention kept for continuity with archival data. That
    is a legitimate reason -- but the factor is twice the sine value, so an implementation
    that inherits it silently reports every impedance at twice another's. Continuity is a
    decision; it has to be recorded as one."""
    v = P.value(ref, "conventions.carrier_amplitude_convention")
    assert v in {"sine_rms", "square_rms", "legacy_sqrt2"}


def test_legacy_convention_refuses(legacy):
    with pytest.raises(P.UnverifiedClaim):
        P.value(legacy, "conventions.carrier_amplitude_convention",
                needed_for="impedance estimate")


# ── the spec's requirement ids are unique ────────────────────────────────────

def test_requirement_ids_are_unique():
    """Every MUST/SHOULD in spec/ carries an id like R-40.1. Duplicates make a
    conformance claim ambiguous about what was actually checked."""
    import re
    from collections import Counter
    spec = Path(__file__).resolve().parent.parent / "spec"
    ids = []
    for f in sorted(spec.glob("*.md")):
        ids += re.findall(r"\*\*(R-\d+\.\d+)\*\*", f.read_text())
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    assert not dupes, f"duplicate requirement ids: {dupes}"
    assert len(ids) >= 20, f"expected the spec to carry requirements; found {len(ids)}"
