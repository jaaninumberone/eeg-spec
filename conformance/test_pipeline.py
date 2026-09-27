"""End-to-end conformance for the reference implementation, on synthetic data only.

Each test names the requirement it checks, so a failure says which part of the spec was
violated rather than which line of code broke.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "conformance"))

import synth  # noqa: E402
from eegspec import dsp, io, pipeline, profile as P, quality  # noqa: E402


@pytest.fixture
def prof():
    return P.load("reference-8ch-500")


@pytest.fixture
def canonical(tmp_path, prof):
    t, x = synth.make(prof, seconds=24, n_channels=4, seed=1)
    return synth.write_csv(tmp_path / "rec.csv", t, x)


# ── section 30 · ingest ──────────────────────────────────────────────────────

def test_canonical_read_measures_its_own_rate(canonical, prof):
    """R-30.1/A-30.1: the rate is measurable from the file, not asserted."""
    rec = io.read(canonical, prof)
    assert rec.timebase == "measured"
    assert rec.fs_hz == pytest.approx(500.0)
    assert rec.gaps == []


def test_gap_is_preserved_not_closed(tmp_path, prof):
    """R-30.4: a dropped packet must stay visible."""
    t, x = synth.make(prof, seconds=20, gap_at_s=8.0, seed=2)
    rec = io.read(synth.write_csv(tmp_path / "gap.csv", t, x), prof)
    assert len(rec.gaps) == 1, "the gap was closed up"


def test_metadata_row_and_typo_header_are_handled(tmp_path, prof):
    """A leading metadata row plus a misspelled header. A reader that assumes line 0 is
    the header returns zero rows, which looks exactly like a file with no data."""
    t, x = synth.make(prof, seconds=12, seed=3)
    p = synth.write_legacy_csv(tmp_path / "legacy.csv", t, x)
    d = io.Dialect(name="legacy-counter", time_kind="sample_index", rate_hz=500.0)
    rec = io.read(p, prof, dialect=d)
    assert rec.n_samples == len(t), "rows were lost to the metadata line"


def test_sample_index_dialect_marks_timebase_asserted(tmp_path, prof):
    """R-30.8: a counter carries no timing, so it cannot express a gap."""
    t, x = synth.make(prof, seconds=12, seed=4)
    p = synth.write_legacy_csv(tmp_path / "l.csv", t, x)
    rec = io.read(p, prof, dialect=io.Dialect(time_kind="sample_index", rate_hz=500.0))
    assert rec.timebase == "asserted"


def test_sample_index_dialect_without_rate_is_refused():
    """R-30.8 again: refusing beats inventing a rate."""
    with pytest.raises(ValueError, match="R-30.8"):
        io.Dialect(time_kind="sample_index")


# ── section 40 · processing ──────────────────────────────────────────────────

def test_non_integer_decimation_refused(prof):
    """R-40.1: refuse, never round."""
    p = copy.deepcopy(prof)
    p["conventions"]["analysis_rate_hz"]["value"] = 120
    with pytest.raises(ValueError, match="R-40.1"):
        dsp.decimation_factor(p)


def test_lines_notched_only_where_declared(prof, canonical):
    """R-40.8: nothing is notched at a frequency derived from the sample rate."""
    rec = io.read(canonical, prof)
    _, applied = dsp.suppress_lines(rec.data, rec.fs_hz, prof)
    declared = set(P.interference_lines(prof)) | {float(prof["firmware"]["mains_hz"]["value"])}
    assert set(applied) <= declared


def test_across_channel_mean_of_referenced_data_is_zero(prof, canonical):
    """R-40.7: the trap, demonstrated. Any statistic defined on this mean becomes a
    statistic of nothing once a common reference has been subtracted."""
    rec = io.read(canonical, prof)
    ref = dsp.common_reference(rec.data)
    assert np.abs(ref.mean(axis=1)).max() < 1e-9


def test_gate_counts_are_reported(prof, canonical):
    """R-40.13: per-gate rejection counts, the cheapest diagnostic in the chain."""
    out = pipeline.run(canonical, prof)
    assert set(out["quality"]["rejected_by"]) >= {"p2p", "std", "flat", "gradient"}
    assert out["quality"]["gate_montage"] != out["quality"]["metric_montage"]


# ── section 40.7 · impedance ─────────────────────────────────────────────────

@pytest.mark.parametrize("z_true", [0.0, 5.0, 25.0])
def test_impedance_round_trips_through_the_profile(tmp_path, prof, z_true):
    """A-40.17: a carrier synthesised for a known electrode impedance must come back.

    The amplitude is built from the profile's own slope and intercept, so this exercises
    the calibration path rather than a constant baked into the test.
    """
    t, x = synth.make(prof, seconds=24, alpha_uv=2.0, carrier_for_kohm=z_true, seed=5)
    p = synth.write_csv(tmp_path / f"imp{z_true}.csv", t, x)
    rec = io.read(p, prof)
    got = quality.impedance_kohm(rec.data, rec.fs_hz, prof)
    assert got["route"] == "ladder"
    for v in got["z_electrode_kohm"]:
        assert v == pytest.approx(z_true, abs=0.6), f"expected {z_true}, got {v}"


def test_impedance_stays_signed(tmp_path, prof):
    """R-40.17: abs() would turn a calibration error into a reassuring reading."""
    t, x = synth.make(prof, seconds=20, alpha_uv=1.0, carrier_for_kohm=-8.0, seed=6)
    p = synth.write_csv(tmp_path / "neg.csv", t, x)
    rec = io.read(p, prof)
    got = quality.impedance_kohm(rec.data, rec.fs_hz, prof)
    assert min(got["z_electrode_kohm"]) < 0
    assert got["negative_channels"]


def test_amplitude_conventions_differ_by_the_factor_they_claim():
    """Spec 40.7 / audit A3: two implementations disagreeing here differ by 2x."""
    vpp = 100.0
    assert quality.rms_from_vpp(vpp, "legacy_sqrt2") == pytest.approx(
        2.0 * quality.rms_from_vpp(vpp, "sine_rms"))


# ── section 50 · payload ─────────────────────────────────────────────────────

def test_payload_carries_provenance(canonical, prof):
    """R-50.6: a number without the device that produced it cannot be compared."""
    out = pipeline.run(canonical, prof)
    assert out["profile_id"] == prof["profile_id"]
    assert out["pipeline_version"]


def test_unavailable_metric_is_present_with_a_reason(canonical, prof):
    """R-50.3/R-50.5: absent-for-a-reason, never silently omitted."""
    out = pipeline.run(canonical, prof)
    nf = out["metrics"]["noise_floor"]
    assert nf["available"] is False and nf["reason"]


def test_every_metric_states_its_n(canonical, prof):
    """R-50.2."""
    out = pipeline.run(canonical, prof)
    for name, m in out["metrics"].items():
        assert "n" in m, f"{name} does not state its n"


def test_unverified_scale_degrades_to_ratios_not_a_wrong_number(canonical, prof):
    """R-20.5: absolute units refuse, ratios survive, and the payload says which."""
    p = copy.deepcopy(prof)
    p["firmware"]["modes"]["eeg"]["uv_scale_factor"].update(
        {"provenance": "declared", "note": "inferred from the PGA register"})
    out = pipeline.run(canonical, p)
    assert out["metrics"]["band_power"]["available"] is False
    assert out["metrics"]["relative_band_power"]["available"] is True
    assert any("absolute units unavailable" in w for w in out["warnings"])
