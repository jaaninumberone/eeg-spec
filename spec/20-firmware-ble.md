# 20 · Firmware and BLE

## 20.1 Register configuration the profile depends on

| register field | why the profile needs it |
| --- | --- |
| `FLEAD_OFF[1:0]` | `11` selects fDR/4 — the carrier tracks the sample rate. Any other setting changes `chip.lead_off_freq_divisor`. |
| `ILEAD_OFF[1:0]` | Sets the injected current, the `I` in Ohm's law for impedance. |
| `CHnSET[6:4]` (PGA) | Per-mode gain. **Necessary but not sufficient** to know the µV scale — see §20.3. |
| Data rate | `firmware.sample_rate_hz`. Sets the carrier frequency and the decimation response together. |

> **R-20.1** The profile MUST declare the sample rate and, per mode, the PGA gain.

## 20.2 Modes

A device may expose several acquisition modes — commonly one optimised for signal and one
that enables impedance measurement. They can differ in gain, in whether the carrier is
present, **and in scaling**.

> **R-20.2** Each mode MUST appear separately under `firmware.modes`, with its own
> `pga_gain`, `uv_scale_factor` and `carrier_present`.
>
> **R-20.3** Recordings from different modes MUST NOT be compared in absolute units until
> both scale factors are verified.

## 20.3 The scale contract

**This is the most important requirement in this document.**

> **R-20.4** Firmware MUST declare, per mode, the factor converting a CSV value to true
> input-referred microvolts.
>
> **R-20.5** That factor MUST NOT be inferred from the PGA register alone.
>
> **A-20.5** *Acceptance.* Apply a **known differential sine** of known amplitude to the
> inputs. Record in each mode. The recovered amplitude divided by the applied amplitude is
> the factor. Repeat at two amplitudes to confirm linearity.

A PGA register describes the amplifier. The conversion from ADC counts to microvolts is a
separate step in firmware that may use a different constant, may be applied once for all
modes, or may have been changed and not documented. **Only a known input settles it.**

The failure this prevents is quiet: ratio metrics and log-differences cancel a constant
factor, so a wrong scale is invisible in most headline numbers and appears only in
absolute power and cross-mode comparison. An implementation can carry an incorrect factor
for a long time with nothing to reveal it. See [90 · A2](90-porting-audit.md).

## 20.4 Interference lines

> **R-20.6** The profile MUST list instrumental line frequencies explicitly in Hz, in
> `firmware.interference_lines_hz`.
>
> **R-20.7** They MUST NOT be expressed as a function of the sample rate.

A comb produced by a switching regulator or a clock sits at fixed frequencies. Writing it
as `k·fs/N` is a coincidence that holds at one rate. Mains is a separate, environmental
line and belongs in `firmware.mains_hz`.

**Distinguishing the two is cheap and worth doing.** A clock-locked line is stationary to
the sample clock and its frequency is rock-steady between blocks; a grid line wanders.
Measuring per-block frequency stability separates them without any other instrument.

## 20.5 BLE transport

The link is a transport concern and the spec constrains it only where the constraint
reaches the data.

> **R-20.8** Each packet MUST carry enough sequencing for the receiver to detect loss.
>
> **R-20.9** A gap MUST be representable in the CSV — see [30 · CSV format](30-csv-format.md).
> A dropped packet that silently closes up is indistinguishable from good data and
> corrupts every timing-dependent measurement downstream.
>
> **R-20.10** The writer MUST NOT resample, interpolate or smooth. Whatever buffering the
> application layer does, the samples written MUST be the samples received.

> **A-20.10** *Acceptance.* Record with the link deliberately interrupted. The CSV MUST
> show the gap, and the sample count MUST fall short of duration × rate by the gap length.
