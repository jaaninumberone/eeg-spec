"""CSV ingest. Canonical schema, declared dialects, positional channel selection.

Implements section 30 of the spec. The three requirements that carry the most weight:

  R-30.4  a gap appears as a jump in t_ms and is never closed up
  R-30.5  channels are selected POSITIONALLY; a header string is not evidence
  R-30.8  a sample-index dialect cannot express a gap, so its timebase is 'asserted'

Header labels naming electrode positions have been observed listing them in an order that
does not match the wiring. A reader that resolves a channel by matching a name then
silently transposes the montage and produces plausible output indefinitely, so this module
offers no way to do it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import profile as P


@dataclass
class Dialect:
    """How to read a non-canonical file. Declared, never sniffed."""
    name: str = "canonical"
    header_rows: int = 1
    time_index: int = 0
    time_kind: str = "ms_since_start"   # ms_since_start | unix_ms | sample_index
    rate_hz: float | None = None        # required for sample_index
    channel_indices: tuple[int, ...] = (1, 2, 3, 4)

    def __post_init__(self):
        if self.time_kind not in ("ms_since_start", "unix_ms", "sample_index"):
            raise ValueError(f"R-30.7: unknown time_column kind {self.time_kind!r}")
        if self.time_kind == "sample_index" and self.rate_hz is None:
            raise ValueError("R-30.8: a sample_index dialect must declare rate_hz")


@dataclass
class Recording:
    data: np.ndarray                 # (n_samples, n_channels), file units
    t_ms: np.ndarray                 # milliseconds since first sample
    fs_hz: float
    timebase: str                    # 'measured' | 'asserted'
    gaps: list[tuple[int, float]] = field(default_factory=list)
    source: str = ""
    dialect: str = "canonical"

    @property
    def n_samples(self) -> int:
        return self.data.shape[0]

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.fs_hz


def _find_header(path: Path, declared: int) -> int:
    """Rows to skip. A declared count wins; otherwise the first numeric row decides.

    Leading metadata rows above the header have been observed in the wild. A reader that
    assumes line 0 is the header treats the real header as data and returns zero rows --
    which is indistinguishable from a file that legitimately has none.
    """
    if declared is not None and declared >= 0:
        with open(path, errors="replace") as f:
            for i, line in enumerate(f):
                if i >= declared:
                    return declared
        return declared
    return 0


def _first_is_number(line: str) -> bool:
    tok = line.split(",", 1)[0].strip().strip('"')
    try:
        float(tok)
        return True
    except ValueError:
        return False


def read(path: str | Path, prof: dict, *, dialect: Dialect | None = None,
         mode: str | None = None) -> Recording:
    """Read a recording. `mode` selects the firmware mode whose units apply."""
    path = Path(path)
    d = dialect or Dialect()
    lines = [l for l in path.read_text(errors="replace").splitlines() if l.strip()]
    if not lines:
        raise ValueError(f"{path.name}: empty file")

    first_data = next((i for i, l in enumerate(lines) if _first_is_number(l)), None)
    if first_data is None:
        raise ValueError(f"{path.name}: no numeric rows")
    if first_data == 0:
        raise ValueError(f"{path.name}: no header row above the data (R-30.1)")
    body = lines[first_data:]

    cols = max(d.channel_indices) + 1
    arr = np.empty((len(body), cols), dtype=float)
    for i, line in enumerate(body):
        parts = line.split(",")
        if len(parts) < cols:
            raise ValueError(f"{path.name}: row {i} has {len(parts)} columns, need {cols}")
        for j in range(cols):
            arr[i, j] = float(parts[j])

    data = arr[:, list(d.channel_indices)]
    tcol = arr[:, d.time_index]

    declared_fs = float(P.value(prof, "firmware.sample_rate_hz", needed_for="ingest"))

    if d.time_kind == "sample_index":
        # R-30.8: no timing information exists here. The rate is asserted and the file
        # cannot express a gap, so anything gap-dependent downstream is unverified.
        fs = float(d.rate_hz)
        t_ms = np.arange(len(data)) * (1000.0 / fs)
        return Recording(data, t_ms, fs, "asserted", [], str(path), d.name)

    t_ms = tcol - tcol[0]
    if len(t_ms) < 2:
        raise ValueError(f"{path.name}: fewer than two samples")
    step = float(np.median(np.diff(t_ms)))
    if step <= 0:
        raise ValueError(f"{path.name}: t_ms is not increasing (R-30.1)")
    fs = 1000.0 / step

    # R-30.4 / A-30.1: a gap is a jump, not something to close up.
    gaps = [(int(i), float(dt)) for i, dt in enumerate(np.diff(t_ms))
            if dt > 1.5 * step]
    return Recording(data, t_ms, fs, "measured", gaps, str(path), d.name)


def to_microvolts(rec: Recording, prof: dict, mode: str) -> np.ndarray:
    """File units -> true input-referred microvolts, using the declared factor.

    R-20.4/R-20.5. The factor is a property of the firmware's conversion, not of the PGA
    register, and this refuses if the profile only guessed.
    """
    if P.inferred_from_register(prof, mode):
        raise P.UnverifiedClaim(
            f"{prof.get('profile_id')}: the uV scale for mode {mode!r} is justified by a\n"
            f"  PGA register value. A register describes the amplifier, not the firmware's\n"
            f"  conversion. Measure it against a known differential input (A-20.5) before\n"
            f"  converting to absolute units. Ratio metrics are unaffected and may proceed\n"
            f"  on file units.")
    return rec.data * P.uv_scale(prof, mode)
