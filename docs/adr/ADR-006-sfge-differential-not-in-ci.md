# ADR-006: The sfge differential is deliberately NOT in CI

## Status

**Accepted**

## Date

2026-07-18 (decision taken when the differential became systematic; recorded retrospectively)

## Author

Mustafa Aksu

## Context

`benchmark/sfge_diff.py` runs Salesforce's own Graph Engine and this tool
over the same 21 org-adjudicated cases and scores both against the org
(currently: sfge contradicted on 8/21, this tool on 0/21 — and 2/21 even on
sfge's own binary scale). It is the strongest competitive evidence in the
project, it takes 42 seconds, and the obvious move is to gate CI on it.
Speed is not the issue.

## Decision

The differential stays OUT of CI. The CI gate's contract is to prove **this
analyzer** correct (tests + benchmark + mutation, no org needed); the
differential proves a **comparative claim** that does not change per commit.
Gating it would put a third-party Java engine in the critical path and turn
the build red when *sfge* changes — punishing this repo for someone else's
release. The script exits non-zero only if **this tool** contradicts the
org, and the standing rule is: **re-run it before repeating its numbers**,
because if sfge fixes its apiVersion blindness, the headline goes stale and
nothing else would announce that.

## Consequences

### Positive

- CI failures always mean "this analyzer regressed" — one cause, one
  responder. No red builds from upstream sfge releases, Java toolchain
  drift, or download flakiness.
- The comparative claim keeps its integrity precisely because it is
  re-measured deliberately, with both scoring scales published (a sceptic
  can fairly object to a three-level scale against a binary engine, so both
  numbers are always reported).

### Negative / Trade-offs

- Staleness is a real risk and is accepted BY NAME: the numbers in README
  and the case study carry a re-run obligation, not a freshness guarantee.
- A contributor could break `sfge_diff.py` itself without CI noticing;
  the cost lands on the next deliberate run.

## Alternatives Considered

### Alternative A — gate CI on the differential

Rejected: conflates two contracts. A gate must prove the thing that changes
per commit; a comparison against a moving third party proves a snapshot.

### Alternative B — scheduled (weekly) differential job

Considered and parked: it would bound staleness without blocking commits,
but it needs the Java/sfge toolchain maintained in CI for a claim that is
only cited at publication moments. If the numbers start being quoted on a
cadence (e.g. a public dashboard), revisit — that would supersede this ADR.

## References

- Source: CLAUDE.md §8 (CI paragraph), §6.1 (how the differential must be framed)
- Related ADRs: ADR-005 (what IS gated and why), ADR-003 (the severity scale the dual scoring respects)
