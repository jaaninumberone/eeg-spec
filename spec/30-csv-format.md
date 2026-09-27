# 30 · CSV format

One canonical schema. Everything else is a **declared dialect**, never a special case
discovered at read time.

## 30.1 Canonical form

```csv
t_ms,ch1,ch2,ch3,ch4
0,-127087.4640,-201730.1395,-200249.0287,-181672.3797
2,-129601.4900,-204108.9827,-202448.7009,-183806.8745
```

> **R-30.1** Column 0 MUST be `t_ms`: milliseconds since the first sample, monotonically
> non-decreasing. Not a wall clock, not a sample index.
>
> **R-30.2** Channel columns MUST be named `ch1..chN` in **physical channel order**.
>
> **R-30.3** Values MUST be in the units declared by `uv_scale_factor` for the recording's
> mode, which MUST be stated in a sidecar (§30.4).
>
> **R-30.4** A gap MUST appear as a jump in `t_ms`. Rows MUST NOT be interpolated, and a
> gap MUST NOT be closed up.

### Why `t_ms` and not a sample index

An index carries no timing. It cannot express a dropped packet, so a reader must be told
the rate out of band and must trust that no sample is missing — two assumptions that fail
silently together. A millisecond column makes the rate measurable from the file and makes
loss visible.

> **A-30.1** *Acceptance.* The median difference between consecutive `t_ms` values MUST
> equal `1000 / firmware.sample_rate_hz` within tolerance. Deviations are gaps, and a
> reader MUST be able to enumerate them.

### Why `ch1..chN` and not electrode names

**Because a header label is not evidence about a physical electrode.** Headers naming
electrode positions have been observed listing them in an order that does not match the
wiring, and a reader selecting *by name* then silently transposes the montage — a defect
that produces plausible output indefinitely.

> **R-30.5** Readers MUST select channels **positionally**. A conforming reader MUST NOT
> resolve a channel by matching a header string.
>
> **R-30.6** The mapping from position to electrode belongs in `montage.channel_order`, in
> the profile, where it is a declared claim with provenance.

## 30.2 Dialects

Existing recordings will not be canonical, and rewriting archives is usually worse than
reading them. A dialect is declared, not inferred.

```json
{
  "dialect": "legacy-counter",
  "header_rows": 1,
  "time_column": {"index": 0, "kind": "sample_index", "rate_hz": 500},
  "channel_columns": [1, 2, 3, 4],
  "note": "Column 0 counts samples, not milliseconds; the rate is asserted, not measurable from the file."
}
```

> **R-30.7** A dialect MUST declare `time_column.kind` as one of `ms_since_start`,
> `unix_ms`, or `sample_index`.
>
> **R-30.8** A `sample_index` dialect MUST carry `rate_hz`, and a reader MUST mark the
> resulting timebase as **asserted**. A file of this kind cannot express a gap; treat any
> gap-dependent result from it as unverified.

Two dialect properties that must be declared rather than sniffed, because both have been
observed and both are silent:

- **Leading metadata rows** before the header. A reader that assumes the first line is the
  header will treat the real header as data and produce zero rows — which looks identical
  to a file with no data.
- **Header spelling**, including typos. Match by declared position, never by string.

## 30.3 What must never be in the file

> **R-30.9** No patient identifier, session identifier, or wall-clock date. A filename is
> part of the file for this purpose.

Timing must be relative to the recording's own start. An absolute timestamp re-identifies
against a schedule even when every other field is anonymous.

## 30.4 Sidecar

> **R-30.10** Every recording MUST be accompanied by a sidecar naming the `profile_id`,
> the acquisition `mode`, and the dialect if not canonical.

Without it the file's units are unknowable: the same numbers mean different things in
different modes on the same device, and nothing in the CSV says which.
