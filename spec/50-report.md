# 50 · Report payload

The contract between processing and whatever renders it. **Shape, not thresholds.**

## 50.1 Separation

> **R-50.1** The processing layer decides *what is true*. The rendering layer decides
> *how it looks*. A renderer MUST NOT compute a value or compose a claim.

The payload therefore carries finished statements, not raw numbers the renderer is
expected to interpret. This is what allows the interpretation to be reviewed in one place.

## 50.2 Required per metric

> **R-50.2** Every metric entry MUST carry: an identifier; the value in stated units; the
> `n` it rests on; and an availability flag with a reason when absent.
>
> **R-50.3** A metric that could not be computed MUST be present and marked unavailable,
> with the reason. It MUST NOT be silently omitted.

An omitted key and a key that is absent for a reason are indistinguishable downstream,
and the difference decides whether a reader should worry.

## 50.3 Uncertainty is mandatory

> **R-50.4** A metric reported as a change or trend MUST carry an explicit statement of
> whether it exceeds the known measurement noise for that quantity.
>
> **R-50.5** Where that noise floor has not been measured, the payload MUST say so.

A difference smaller than test-retest variability is not a finding. A payload that cannot
express "this moved, and we do not know whether that is meaningful" will have that
distinction lost by every consumer.

## 50.4 Provenance travels

> **R-50.6** The payload MUST carry the `profile_id` and the pipeline version that
> produced it.

A number without the device that produced it cannot be compared against another device's,
and the scale factors alone make that comparison wrong.

## 50.5 Thresholds are not here

> **R-50.7** Favourable ranges, clinical bands and their validation are **out of scope**.
> Where a payload carries a band, the band MUST arrive from the profile or from a
> configuration the specification does not define.

This specification describes measurement. What a measurement means for a person is a
separate question with a different evidentiary standard, and merging the two is how an
unvalidated threshold acquires the authority of a measured quantity.
