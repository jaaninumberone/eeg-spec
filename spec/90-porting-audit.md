# 90 · Porting audit

This section exists because the specification was not written from first principles. It
was derived by porting a working, carefully documented, single-device implementation —
roughly 1,600 lines of chapter prose defending each design choice — into the tiered
profile structure.

That port is the reason several schema fields exist. Each entry below is a number the
source implementation treated as a property of the world, which is in fact a property of
one device, one firmware, or one lab's habit.

**None of these were sloppy.** The source is better documented than most production code;
one of the four is explicitly flagged as a legacy convention in its own prose. They
survived because a single-device implementation has no pressure to distinguish *true* from
*true here*.

---

## A1 · The impedance carrier modelled as a fixed physical frequency

**Claimed.** The lead-off source injects its carrier at a fixed physical frequency. At the
lower of the device's two sample rates it therefore lands at the Nyquist edge and
"aliases" down; at the higher rate it sits comfortably inside the band.

**Actually.** With `FLEAD_OFF[1:0] = 11` the ADS1299 lead-off source runs at **fDR/4**. The
carrier is *generated* at a quarter of the sample rate. Nothing aliases. At either rate it
sits at exactly half of Nyquist — equally well resolved, with identical `sinc³`
attenuation.

**Why it survived.** The two models give the same answer at the higher rate, and were
reconciled by hand at the lower one. Those were the only two rates the hardware ever ran
at, so the error had no observable consequence.

**What it cost.** Three things, none of them a crash:

- A section of the sampling chapter resolves an "apparent paradox" about phase ambiguity
  at the Nyquist edge. The paradox does not exist.
- The impedance chapter states that accuracy *degrades* at the lower sample rate because
  the carrier is "barely resolved". It is resolved identically at both rates.
- **An entire parameter-sweep experiment was built to quantify that degradation.** Whatever
  it measured, the stated cause cannot be it.

**Schema response.** `chip.lead_off_freq_divisor`, and `carrier_hz()` computes `fs /
divisor` rather than storing a frequency. Conformance checks it at four sample rates —
including two the hardware has never used, because that is where the two models diverge.

---

## A2 · The microvolt scale inferred from the PGA register

**Claimed.** The firmware applies one mode's LSB constant to every conversion, so values
recorded in the other mode are scaled by the ratio of the two PGA gains.

**Actually.** That is a hypothesis about the firmware, derived from a register value. A
register describes the amplifier. What the conversion did is a separate question, and only
a known differential input answers it. Measuring it can give a materially different
number.

**Why it survived.** The affected metrics are ratios and log-differences, in which a
constant factor cancels. The error is invisible in every headline number and appears only
in absolute band power and cross-mode comparison.

**Schema response.** `firmware.modes.<mode>.uv_scale_factor`, one per mode, and
`inferred_from_register()` flags any whose justification is a register value.

---

## A3 · A peak-to-RMS convention inherited rather than chosen

**Claimed.** Converting the measured carrier peak-to-peak to RMS with a `1/√2` factor,
documented candidly as *"the legacy convention inherited from older lab scripts … it keeps
the numerical output continuous with the entire historical body of lab measurements."*

**Actually.** For a sine the RMS is `Vpp/(2√2)`. The inherited factor is **twice** that.
Since the chip's `sinc³` decimation strips the injected square wave's harmonics, the
carrier arrives near-sinusoidal and the sine conversion is the physically correct one.

**This one is not an error.** Continuity with archival measurements is a real reason, and
the source says so plainly. It is in this audit because an *undeclared* convention is
indistinguishable from a wrong one: two conforming implementations that disagree here
differ by a factor of two in every impedance they report, with nothing to reveal it.

**Schema response.** `conventions.carrier_amplitude_convention`, with the three named
options and no default.

---

## A4 · An analysis rate that encodes two source rates

**Claimed.** Decimate to a fixed analysis rate, chosen so that both of the device's source
rates reduce by an integer factor.

**Actually.** A property of those two rates. On a device sampling at any other rate the
factor is not an integer, and the chain needs polyphase resampling or a different target.

**Schema response.** `conventions.analysis_rate_hz`, which must divide the profile's
source rate by an integer — checkable rather than assumed.

---

## What this audit is for

Phase ordering. The specification was written **before** the reference implementation
precisely so that these would surface as prose to be corrected rather than as constants to
be encoded. Three of the four are invisible in any output; two produce results that are
merely wrong by a constant; one had an experiment built on it.

A fifth class exists and is out of scope here: montage labels that do not match the
physical electrodes, where the header on disk and the wiring disagree. Readers must select
channels **positionally**, never by header label. See `montage.channel_order`.
