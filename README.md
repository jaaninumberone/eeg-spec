# eeg-spec — a device-agnostic ADS1299 EEG specification

A specification, a reference implementation, and a **conformance suite** for EEG devices
built on the TI ADS1299 family: from the input network, through firmware and a BLE
writer, to a CSV, to processing, to a report payload.

The suite is the point. A specification nothing is checked against is decoration, so the
first thing built here is the runner, not the prose.

## Why a profile, and not a config file

The question a spec has to answer is *which of these numbers is a property of the chip,
which of the board, and which of the firmware?* Getting it wrong is not hypothetical. An
existing implementation:

- models the impedance carrier as a **fixed physical frequency**. With `FLEAD_OFF=11` the
  lead-off source runs at **fDR/4**, so the carrier *tracks the sample rate*. Both models
  agree at the two rates that hardware has ever run at, which is why it survived — and
  they diverge at any third rate. The error is invisible until someone builds the next
  device.
- infers the **microvolt scale factor from the PGA register**. A register describes the
  amplifier. What the firmware's conversion actually did is a separate question that only
  a known differential input settles, and measuring it can give a materially different
  answer.

So every field in a profile carries its **provenance** — `measured`, `closed-form`,
`declared` or `unverified` — and a `measured` claim must carry the procedure that
established it. **Anything depending on an `unverified` field refuses to run**, because a
plausible wrong number is worse than a stop.

```
chip      ADS1299 behaviour: carrier at fs/divisor, sinc^3 decimation,
          lead-off current, available PGA gains.          Not configurable.
board     per build: series resistor, carrier slope AND INTERCEPT, CM->DM leak,
          any analogue pole.                              Must be measured.
firmware  sample rate, PGA gain and uV scale per mode, interference lines as
          explicit Hz, mains frequency.                   Declared and verified.
```

## Run it

```bash
python3 conformance/run_against.py reference-8ch-500          # a conformant device
python3 conformance/run_against.py _legacy-fixed-carrier-model # must FAIL, on purpose
python3 conformance/run_against.py /path/to/my-board-500.json

python3 -m pytest conformance/ -q                             # the checks themselves
python3 conformance/check_publishable.py                      # boundary guard, see below
```

`_legacy-fixed-carrier-model.json` is not a device. It encodes the beliefs above so the
suite can be shown to catch them: **all five checks fail against it, each with a reason.**
A conformance suite that passes on the thing it was written to correct has proved nothing.

## What is public, and what is not

This tree is built to be publishable **without clearance**: chip physics, the profile
schema, the CSV format, reference code, synthetic fixtures. No measured constant from any
particular organisation's hardware, no clinical thresholds, no recordings.

Device-specific values live in a private overlay — a profile JSON and its fixtures — which
this repo consumes and never contains. A profile is *data*, which is what makes the split
clean rather than a compromise.

## The specification

[`spec/00-overview.md`](spec/00-overview.md) is the entry point.

| | |
| --- | --- |
| [10 · Circuitry](spec/10-circuitry.md) | Input network, protection resistor, bias/DRL |
| [20 · Firmware and BLE](spec/20-firmware-ble.md) | Registers, packets, **the scale contract** |
| [30 · CSV format](spec/30-csv-format.md) | One schema; dialects declared, never sniffed |
| [40 · Processing](spec/40-processing.md) | The chain, stage by stage, profile-driven |
| [50 · Report payload](spec/50-report.md) | Output contract — shape, not thresholds |
| [90 · Porting audit](spec/90-porting-audit.md) | **What porting a real implementation revealed** |

The audit is worth reading first if you are short of time. The specification was derived
by porting a working, well-documented single-device implementation into the tiered
structure, and that port surfaced four numbers treated as properties of the world which
are in fact properties of one device, one firmware, or one lab's habit. One of them had a
parameter-sweep experiment built on top of it. Each is why a corresponding schema field
exists.

## The reference implementation

```bash
python3 -m eegspec RECORDING.csv --profile reference-8ch-500
python3 -m eegspec REC.csv --profile my-board.json --mode impedance
python3 -m eegspec REC.csv --profile p.json --dialect sample_index --rate 500
```

CSV to report payload, profile-driven throughout. `io` reads canonical files and declared
dialects and selects channels positionally; `dsp` refuses a non-integer decimation rather
than rounding it; `quality` gates epochs and reports what each gate rejected, and recovers
impedance by the two-point route while keeping the result signed; `pipeline` assembles a
payload that states its `n`, names anything unavailable and why, and declares that the
measurement noise floor is unknown.

Three behaviours worth knowing:

- **An unverified `uv_scale_factor` degrades rather than lies.** Absolute band power
  becomes unavailable with a reason; relative power and ratios, which cancel a constant
  factor, stay valid and say so.
- **A negative electrode impedance is reported, not clipped.** It is physically
  impossible, so it is the calibration announcing an error; `abs()` would turn that into
  a reassuring small reading on a shorted electrode.
- **Gate counts always appear**, including zeros. A gate that rejects nothing is dead
  weight carrying unearned credibility; one that rejects almost everything is setting the
  retention rate by itself. Both are visible at a glance and otherwise invisible.

## Status

Phases 1–3 of 4 complete. **34 conformance checks pass.** The reference profile is
conformant on 6/6 and the legacy model fails 6/6, as intended. A carrier synthesised for a
known electrode impedance round-trips through the profile's own calibration to within
0.6 kΩ at 0, 5 and 25 kΩ.

Not yet built: conformance against a production implementation (Phase 4), which is
internal work and does not belong in this repository.

## Licence

Apache-2.0. The patent grant is the reason for choosing it over MIT: this describes how to
build and characterise hardware, and an implementer wants assurance that doing so does not
expose them.

## Layout

```
profiles/     profile.schema.json, the synthetic reference, the legacy failing model
eegspec/      reference implementation (currently: the profile loader)
conformance/  run_against.py, check_publishable.py, synth.py, 34 checks
spec/         the written specification                       (Phase 2)
```
