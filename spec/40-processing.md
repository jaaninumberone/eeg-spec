# 40 · Processing

The chain from a conforming CSV to a report payload. Every stage reads its parameters from
the profile; none may carry a device constant as a literal.

```
CSV ─┬─→ trim ─→ anti-alias ─→ decimate ─→ high-pass ─→ reference ─→ line suppression
     │                                                                      │
     │                                                          PSD ─→ band power
     │                                                                      │
     └─→ (raw, undecimated) ─→ carrier amplitude ─→ impedance          epoch gating
                                                                            │
                                                                   report payload §50
```

Two branches, and the split is not stylistic: the impedance branch **must** read the raw
signal, because every stage in the main branch is designed to remove exactly what it
measures.

## 40.1 Rate reduction

> **R-40.1** The decimation factor MUST be an integer: `firmware.sample_rate_hz /
> conventions.analysis_rate_hz`. A non-integer ratio MUST be refused, not rounded.
>
> **R-40.2** An anti-alias filter MUST precede decimation, with its stopband below the new
> Nyquist.
>
> **R-40.3** Zero-phase filtering introduces an edge transient. At least `numtaps − 1`
> samples MUST be trimmed from each end before anything downstream reads the signal.

⚠️ An analysis rate chosen because it divides one device's source rates cleanly is a
property of that device. Declaring it in `conventions.analysis_rate_hz` makes R-40.1 a
check rather than an assumption — see [90 · A4](90-porting-audit.md).

## 40.2 Drift

> **R-40.4** A high-pass MUST remove sub-band drift, with its corner below the lowest
> analysis band edge.
>
> **R-40.5** Narrow low-frequency bandpasses MUST be constructed in second-order-section
> form.

R-40.5 is not stylistic. Transfer-function form at very low normalised frequencies loses
precision catastrophically — coefficients spanning many orders of magnitude produce output
larger than the input by orders of magnitude, which then trips every amplitude gate
downstream and rejects the entire recording. It fails loudly, but only after a chain of
plausible-looking intermediate steps.

## 40.3 Referencing

> **R-40.6** Where a common reference is subtracted, the profile's montage MUST be
> consulted for which channels participate.
>
> **R-40.7** Statistics computed **across** channels MUST NOT be computed on
> common-referenced data.

R-40.7 has a sharp edge: after subtracting the across-channel mean, that mean is
identically zero by construction. Any measure defined on it silently becomes a measure of
nothing. If gating and metrics want different montages, that is legitimate — but each must
state which it reads.

⚠️ Common referencing is not always an improvement. It removes what channels share; where
the disturbance is *not* shared, it redistributes one channel's noise into the others.
Whether it helps is a per-recording question and can be measured before choosing.

## 40.4 Line suppression

> **R-40.8** Notches MUST be placed at `firmware.interference_lines_hz` and
> `firmware.mains_hz`, never at frequencies derived from the sample rate.
>
> **R-40.9** A notch inside an analysis band MUST be justified against the band power it
> removes.

A narrow notch is not free. One placed inside a band removes real signal from every
recording forever, and if the line it targets is not actually there, that is the only
effect it has. Check that a line exists before notching it.

Two facts worth using: a **clock-locked** line has essentially zero block-to-block
frequency variation, while a **grid** line wanders by a fraction of a hertz — so a fixed
notch is well matched to the first and chronically mistuned against the second. And
narrowband interference can be **detected** rather than assumed: an instrumental line is
far sharper than any physiological rhythm, and the two separate cleanly on the ratio of
centre frequency to bandwidth.

## 40.5 Spectrum and band power

> **R-40.10** Segment length for a Welch estimate SHOULD be an integer multiple of the
> sample rate, so that integer-hertz tones fall on bin centres.
>
> **R-40.11** Band edges MUST come from `conventions.band_edges_hz`.

## 40.6 Epoch gating

> **R-40.12** Rejection thresholds MUST come from the profile or an explicit
> configuration. They MUST NOT be literals.
>
> **R-40.13** A gate set MUST be reported with the count of epochs each gate rejected.

R-40.13 is the cheapest diagnostic in the chain and it is usually missing. Two failure
modes it catches immediately: a gate that fires on **nothing**, which is dead weight
carrying unearned credibility; and a gate that fires on **almost everything**, which is
not selecting epochs but setting the retention rate by itself.

⚠️ A threshold tuned until the output looks reasonable has been fitted to the answer. If a
gate's justification is that a stricter value "rejects too much", it has no independent
evidence behind it. Derive thresholds from labelled artefact recordings, or declare them
as conventions — but do not present a fitted value as a measurement.

## 40.7 Impedance

> **R-40.14** The impedance branch MUST read the raw, undecimated signal.
>
> **R-40.15** Carrier amplitude MUST be converted using
> `conventions.carrier_amplitude_convention`, never a built-in factor.
>
> **R-40.16** Path impedance MUST be recovered as
> `(A − board.carrier_intercept_uv) / board.carrier_slope_uv_per_kohm`, and the electrode
> contribution as that minus `board.r_series_ohm`.
>
> **R-40.17** The result MUST remain signed. A negative value MUST NOT be clipped.

R-40.16 is the two-point form. A single-point calibration forces the line through the
origin and folds the intercept into the slope; it is exact at the calibration point by
construction and wrong everywhere else, with the error growing across the range.

R-40.17 matters more than it looks. A negative electrode impedance is physically
impossible, so it is a calibration error announcing itself. Taking the absolute value
converts that announcement into a plausible reading — on a shorted electrode, an error of
a few kilohms becomes a *reassuring* few kilohms.

> **A-40.17** *Acceptance.* Run the estimator on a shorted board of known series
> resistance. It MUST return approximately zero electrode impedance. Repeat with a second
> known resistance: both MUST come out right, which a single-point calibration cannot do.
