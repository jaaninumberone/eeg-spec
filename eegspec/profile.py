"""Load, validate and query an ADS1299 device profile.

WHY THIS EXISTS. A device profile is the spec's answer to "which of these numbers is a
property of the chip, which of the board, and which of the firmware?" Getting that wrong
is not hypothetical: an existing implementation models the impedance carrier as a fixed
physical frequency (it is fs/4, so it tracks the rate) and infers the microvolt scale
factor from the PGA register (a register describes the amplifier, not the firmware's
conversion). Both survived because they are invisible at the only two sample rates ever
used.

THE ONE RULE. A claim marked ``unverified`` refuses. Anything that depends on such a
field raises rather than returning a plausible number, because a plausible wrong number
is worse than a stop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILES = Path(__file__).resolve().parent.parent / "profiles"
SCHEMA = PROFILES / "profile.schema.json"

#: Provenance values, weakest last. ``unverified`` is the only one that refuses.
PROVENANCE = ("measured", "closed-form", "declared", "unverified")


class ProfileError(ValueError):
    """The profile is malformed, or a required claim is unverified."""


class UnverifiedClaim(ProfileError):
    """A field this computation depends on has no established provenance."""


def load(name_or_path: str | Path, *, validate: bool = True) -> dict:
    p = Path(name_or_path)
    if not p.exists():
        p = PROFILES / f"{name_or_path}.json"
    if not p.exists():
        raise ProfileError(f"no such profile: {name_or_path}")
    prof = json.loads(p.read_text())
    if validate:
        _validate(prof)
    prof["_source"] = str(p)
    return prof


def _validate(prof: dict) -> None:
    try:
        import jsonschema
    except ImportError as e:  # pragma: no cover - environment dependent
        raise ProfileError(f"jsonschema needed to validate a profile: {e}") from e
    jsonschema.validate(prof, json.loads(SCHEMA.read_text()))


def claim(prof: dict, dotted: str) -> dict:
    """Fetch a claim object by dotted path, e.g. ``chip.lead_off_freq_divisor``."""
    node: Any = prof
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ProfileError(f"{prof.get('profile_id')}: no such field {dotted!r}")
        node = node[part]
    if not isinstance(node, dict) or "provenance" not in node:
        raise ProfileError(f"{prof.get('profile_id')}: {dotted!r} is not a claim")
    return node


def value(prof: dict, dotted: str, *, needed_for: str | None = None) -> Any:
    """The value, refusing if its provenance is ``unverified``.

    ``needed_for`` names the computation, so the refusal says why it mattered.
    """
    c = claim(prof, dotted)
    if c["provenance"] == "unverified":
        why = f" needed for {needed_for}" if needed_for else ""
        raise UnverifiedClaim(
            f"{prof.get('profile_id')}: {dotted}{why} is marked 'unverified'.\n"
            f"  {c.get('note', '(no note)')}\n"
            f"  Measure it and record the procedure, or state it as 'declared' with the\n"
            f"  reason it is safe to assume. Do not proceed on an unverified field."
        )
    return c["value"]


def carrier_hz(prof: dict) -> float:
    """Impedance-carrier frequency for this device.

    fs / divisor, NOT a stored constant. This function is the whole argument: a spec that
    stores the carrier as a number is correct for one device and silently wrong for the
    next one with a different sample rate.
    """
    fs = value(prof, "firmware.sample_rate_hz", needed_for="carrier frequency")
    div = value(prof, "chip.lead_off_freq_divisor", needed_for="carrier frequency")
    return float(fs) / float(div)


def sinc3_at(prof: dict, f_hz: float) -> float:
    """Chip decimation response at a frequency. sinc^3(f/fs)."""
    import numpy as np

    resp = value(prof, "chip.decimation_response", needed_for="decimation response")
    if resp != "sinc3":
        raise ProfileError(f"unsupported decimation response {resp!r}")
    fs = float(value(prof, "firmware.sample_rate_hz", needed_for="decimation response"))
    return float(np.sinc(f_hz / fs) ** 3)


def interference_lines(prof: dict) -> list[float]:
    """Instrumental line frequencies, explicit. Never derived from the sample rate."""
    return list(value(prof, "firmware.interference_lines_hz",
                      needed_for="interference line suppression"))


def mode(prof: dict, name: str) -> dict:
    modes = prof.get("firmware", {}).get("modes", {})
    if name not in modes:
        raise ProfileError(
            f"{prof.get('profile_id')}: no mode {name!r}; have {sorted(modes)}")
    return modes[name]


def uv_scale(prof: dict, mode_name: str) -> float:
    """Multiply CSV values by this for true input-referred microvolts."""
    return float(value(prof, f"firmware.modes.{mode_name}.uv_scale_factor",
                       needed_for=f"microvolt scaling in {mode_name} mode"))


def inferred_from_register(prof: dict, mode_name: str) -> bool:
    """Is the scale factor's justification a PGA register value?

    A register describes the amplifier. The firmware's conversion is a separate thing
    that may or may not use the same gain, and only a known input settles it. A profile
    whose note admits the inference is flagged rather than trusted.
    """
    c = claim(prof, f"firmware.modes.{mode_name}.uv_scale_factor")
    note = (c.get("note") or "").lower()
    return c["provenance"] != "measured" and (
        "register" in note or "inferred" in note or "pga" in note)
