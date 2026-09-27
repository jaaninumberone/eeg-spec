# 00 · Overview

This specification describes an EEG acquisition and analysis chain built on the TI
ADS1299 family, from the input network through firmware and a BLE link to a CSV, to
processing, to a report payload.

It is written to be **device-agnostic**. Everything that varies between one device and
the next lives in a *device profile* (`profiles/profile.schema.json`); everything in
these documents holds for any device that declares one.

## The three tiers, and why the split is the whole design

| tier | what it covers | who establishes it |
| --- | --- | --- |
| **chip** | Carrier at `fs / divisor`, `sinc³` decimation, lead-off current, available PGA gains | Follows from the part and its registers |
| **board** | Series resistor, carrier slope **and intercept**, CM→DM leak, any analogue pole | Must be measured on the board |
| **firmware** | Sample rate, PGA gain and µV scale **per mode**, interference lines as explicit Hz, mains | Declared by its author, verified against a known input |
| **conventions** | Peak-to-RMS choice, analysis rate, band edges | Neither derivable nor measurable — declared |

A specification that fixes a number in the wrong tier is wrong for every device but one.
That is not a hypothetical: porting a working single-device implementation into this
structure surfaced **four** such numbers, one of which had an entire experiment built on
top of it. They are catalogued in [90 · Porting audit](90-porting-audit.md), and each is
the reason a corresponding field exists in the schema.

## What conformance means

A device conforms when its profile passes `conformance/run_against.py`. The checks are
deliberately few and each maps to a mistake observed in the field:

1. **The carrier tracks `fs/4`.** Not a stored frequency.
2. **Carrier attenuation is rate-independent.** The consequence of (1), and what lets one
   calibration constant serve every rate.
3. **The µV scale is not inferred from a PGA register.** A register describes the
   amplifier; the firmware's conversion is a separate question.
4. **Interference lines are explicit Hz.** A clock-locked comb is not at `k·fs/N`.
5. **The carrier calibration states an intercept.** Zero is a legitimate value; *unstated*
   is not.

A field marked `unverified` refuses rather than returning a plausible number. That rule is
the specification's only real teeth.

## Chain

```
electrode ─→ input network ─→ ADS1299 ─→ firmware ─→ BLE ─→ CSV
                  §10            §10        §20      §20    §30
                                                              │
                        report payload ←── processing ────────┘
                              §50              §40
```

## Sections

| | |
| --- | --- |
| [10 · Circuitry](10-circuitry.md) | Input network, protection resistor, bias/DRL, and what each costs |
| [20 · Firmware and BLE](20-firmware-ble.md) | Register configuration, packet format, **the scale contract** |
| [30 · CSV format](30-csv-format.md) | One canonical schema, and how to declare a dialect |
| [40 · Processing](40-processing.md) | The chain, stage by stage, profile-driven |
| [50 · Report payload](50-report.md) | The output contract — shape, not thresholds |
| [90 · Porting audit](90-porting-audit.md) | What porting a real implementation revealed |

## What this is not

**Not a clinical specification.** Metric thresholds, favourable ranges and their validation
are a separate matter and are not in this repository.

**Not a real-time chain.** Zero-phase filtering (`filtfilt`) looks both ways along the
signal. An online implementation needs every stage redesigned.

**Not sufficient for a montage of four electrodes.** Source separation by ICA needs more
channels than a frontal headband carries; artefact handling here is epoch-level rejection.
