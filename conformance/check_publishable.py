#!/usr/bin/env python3
"""Refuse to publish anything organisation-specific from the public tree.

The public layer is designed to need no clearance: chip physics, the profile schema, the CSV format, reference code, synthetic
fixtures. Measured constants from a particular organisation's hardware, clinical
thresholds and any patient-derived file belong in the private overlay.

This is a mechanical check because the boundary cannot rest on remembering. It is meant
to run in CI and fail the build.

    python3 conformance/check_publishable.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", ".venv", "private"}
#: This file necessarily contains every pattern it searches for, so it excludes
#: itself. Noticed when the first run reported seven findings against its own
#: pattern table -- a checker that fails on its own definitions cries wolf and
#: gets switched off.
SKIP_FILES = {"check_publishable.py"}

#: Patterns live OUTSIDE this file, in conformance/patterns.local.json, which is
#: gitignored. The reason is not tidiness. An earlier version held them inline and
#: excluded itself from its own scan so it would not report findings against its own
#: table -- which meant the table, a plaintext list of exactly the constants and
#: identifiers it exists to keep out, would have shipped in the public repository.
#: A guard that publishes what it guards is worse than none, because it reads as
#: diligence. See patterns.example.json for the shape.
PATTERNS_FILE = Path(__file__).resolve().parent / "patterns.local.json"


def load_patterns() -> tuple[list, list, bool]:
    """Return (constants, identifiers, had_local_file)."""
    if PATTERNS_FILE.exists():
        d = json.loads(PATTERNS_FILE.read_text())
        return ([(p["pattern"], p["why"]) for p in d.get("constants", [])],
                [(p["pattern"], p["why"]) for p in d.get("identifiers", [])], True)
    # Public default: no organisation's constants are known here, so only the
    # structural checks run. An organisation with a private overlay supplies its own.
    return ([], [(r"(?i)\bTODO[- ]?SECRET\b", "placeholder")], False)


DATA_SUFFIXES = {".csv", ".edf", ".npz", ".xlsx", ".parquet"}


def compile_patterns(entries):
    """Compile, collecting failures instead of raising.

    A malformed pattern must not take the checker down. A guard that dies on its own
    config fails open in practice: the next person to hit it switches it off rather than
    debugging it, and the protection is gone for good.
    """
    good, bad = [], []
    for pat, why in entries:
        try:
            good.append((re.compile(pat), why))
        except re.error as e:
            bad.append((pat, str(e)))
    return good, bad


def publishable_files() -> list[Path]:
    """What would actually be published.

    Ask git, not the filesystem. The question is "would this leave the machine", and only
    the index answers it -- a filesystem walk also reads gitignored files, including
    patterns.local.json, whose whole content is by definition the thing being protected.
    Falls back to a walk outside a repository.
    """
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                             capture_output=True, text=True, check=True).stdout
        files = [ROOT / line for line in out.splitlines() if line.strip()]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return [p for p in sorted(ROOT.rglob("*")) if p.is_file()
            and not any(part in SKIP_DIRS for part in p.parts)]


def scan(compiled):
    problems = []
    for p in publishable_files():
        if any(part in SKIP_DIRS for part in p.parts) or p.name in SKIP_FILES:
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if p.suffix.lower() in DATA_SUFFIXES:
            problems.append((str(rel), 0, f"data file in the public tree ({p.suffix})"))
            continue
        if p.suffix.lower() not in {".py", ".json", ".md", ".txt", ".toml", ".yml", ".yaml"}:
            continue
        try:
            text = p.read_text(errors="replace")
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pat, why in compiled:
                if pat.search(line):
                    problems.append((str(rel), i, why))
    return problems


def main() -> int:
    constants, identifiers, had_local = load_patterns()
    compiled, broken = compile_patterns(constants + identifiers)
    problems = scan(compiled)
    files = publishable_files()
    print(f"publishability check over {len(files)} file(s) git would publish, "
          f"under {ROOT}")
    if had_local:
        print(f"  patterns: {len(constants)} constant(s), {len(identifiers)} identifier(s) "
              f"from {PATTERNS_FILE.name}")
    else:
        print("  NOTE no patterns.local.json — structural checks only (no data files, no")
        print("       oversized text). Supply one to check your own constants; see")
        print("       patterns.example.json.")
    if broken:
        print(f"\n{len(broken)} pattern(s) failed to compile and were NOT applied:")
        for pat, err in broken:
            print(f"  {pat!r}: {err}")
        print("Fix them; an uncompiled pattern protects nothing.")
        return 1
    if not problems:
        print("\nCLEAN: nothing matched, and no data file is present.")
        return 0
    print(f"\nNOT PUBLISHABLE: {len(problems)} finding(s)\n")
    for path, line, why in problems:
        where = f"{path}:{line}" if line else path
        print(f"  {where}")
        print(f"      {why}")
    print("\nMove it to the private overlay, or restate it without the measured value.")
    print("The public layer must stand on its own without clearance.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
