"""CSV to report payload.

    python3 -m eegspec RECORDING.csv --profile reference-8ch-500
    python3 -m eegspec REC.csv --profile my-board.json --mode impedance
    python3 -m eegspec REC.csv --profile p.json --dialect sample_index --rate 500
"""
from __future__ import annotations

import argparse
import json
import sys

from . import io, pipeline, profile as P


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("recording")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--mode", default="eeg")
    ap.add_argument("--dialect", choices=["canonical", "sample_index"],
                    default="canonical")
    ap.add_argument("--rate", type=float, help="required with --dialect sample_index")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    args = ap.parse_args(argv)

    try:
        prof = P.load(args.profile)
    except P.ProfileError as e:
        print(f"profile unusable: {e}", file=sys.stderr)
        return 2

    dialect = None
    if args.dialect == "sample_index":
        if args.rate is None:
            print("--dialect sample_index requires --rate (R-30.8): a counter carries no "
                  "timing, so the rate must be asserted explicitly", file=sys.stderr)
            return 2
        dialect = io.Dialect(name="sample_index", time_kind="sample_index",
                             rate_hz=args.rate)

    try:
        payload = pipeline.run(args.recording, prof, mode=args.mode, dialect=dialect)
    except P.UnverifiedClaim as e:
        print(f"\nREFUSED\n{e}", file=sys.stderr)
        return 2
    except (ValueError, KeyError) as e:
        print(f"\nFAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    text = json.dumps(payload, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    for w in payload.get("warnings", []):
        print(f"  warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
