# 10 · Circuitry

Requirements and acceptance tests for the analogue front end. This section states what a
conforming board must achieve and how to demonstrate it — not how to build one.

## 10.1 Protection resistor

Each electrode line carries a series resistor between the connector and the ADS1299
input. It limits fault current and is the first term in the impedance path.

**It is also the dominant lever on common-mode rejection.** The leak from common mode into
differential is a divider imbalance: series resistance against the shunt impedance to
ground. Because the shunt path is capacitive, the leak **rises with frequency**, and it
scales **linearly with the series resistance**.

> **R-10.1** The profile MUST declare `board.r_series_ohm`.
>
> **A-10.1** *Acceptance.* Build two boards differing only in this resistor. The CM→DM
> leak MUST scale with the ratio of the two values, within measurement error. If it does
> not, the leak has another dominant source and the model in this section does not apply
> to that board.

This trade is roughly one-for-one in amplitude: halving the resistor buys about 6 dB of
rejection and costs proportional fault-current headroom. Choose it deliberately; do not
inherit it.

## 10.2 Common-mode to differential conversion

> **R-10.2** The profile SHOULD declare `board.cm_dm_at_50hz_db` and
> `board.cm_dm_slope_db_per_decade`.
>
> **A-10.2** *Acceptance.* Drive a common-mode sine into all inputs with the board
> otherwise shorted. Sweep frequency across the analysis band and at least one decade
> above it. Report the differential output as a ratio to the drive.

Two results to expect, and to be suspicious of if absent:

- A **rising** characteristic, on the order of +20 dB/decade. A flat characteristic
  indicates a resistive rather than capacitive imbalance and a different failure mode.
- A figure **far worse than the datasheet CMRR**. The datasheet describes the amplifier;
  this measures the whole input network. A large gap is normal and is a property of the
  board, not of the part.

⚠️ **A shorted-input measurement is silent about electrodes.** It characterises the
network with the electrode absent, and the electrode contributes series impedance that can
exceed the protection resistor by an order of magnitude. Do not conclude from a shorted
board that electrodes are not the dominant term in use. See §10.3.

## 10.3 Electrode contribution

> **R-10.3** Implementations MUST NOT assume the electrode's contribution to CM→DM is
> negligible on the basis of a shorted-board measurement.
>
> **A-10.3** *Acceptance.* On recordings made with electrodes, relate per-channel
> impedance **mismatch** — not level — to the differential residual after a common-mode
> reference is subtracted. A positive relation means the electrode is a material term.

Mismatch matters and level does not: identical impedances divide identically and convert
nothing, however high. That distinction is easy to lose, and it decides whether the
remedy is a board change or a preparation change.

## 10.4 Bias / driven-right-leg

> **R-10.4** The profile SHOULD record whether the bias loop is functional in each mode.
>
> **A-10.4** *Acceptance.* Measure the bias pin voltage in each operating mode. A pin at
> or near a supply rail is saturated and the loop is not cancelling anything.

A non-functional bias loop is survivable — software line suppression compensates — but it
must be **known**, because it moves line rejection from a hardware guarantee to a software
dependency, and it can differ per mode on the same board.

## 10.5 Analogue response beyond the chip

> **R-10.5** The profile MUST state `board.analogue_pole_hz`, which MAY be null. *Null
> means measured-and-absent, not unexamined.*
>
> **A-10.6** *Acceptance.* Sweep a **differential** sine across and above the analysis
> band. Divide the measured response by `sinc³(f/fs)`. Any residual roll-off is analogue
> and belongs to the board.

Run this at **two sample rates**. The chip's contribution is a function of `f/fs` and
moves with the rate; an analogue pole is a function of absolute frequency and does not.
That is what separates them, and a single-rate sweep cannot.

⚠️ A differential sweep stopping at the top of the analysis band cannot see a pole above
it. Sweep at least an octave beyond anything the chain will ever pass.
