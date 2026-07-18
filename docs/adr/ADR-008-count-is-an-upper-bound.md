# ADR-008: The live COUNT is an upper bound, never a measurement — and `n/a` beats an estimate

## Status

**Accepted**

## Date

2026-07-18 (in effect since the record-reach correction; recorded retrospectively)

## Author

Mustafa Aksu

## Context

`--include-counts` runs a live `COUNT()` per reached object to give the
escalation a magnitude. The tool's own history shows how this number goes
wrong: an early headline said *"the agent reaches 31 records where the user
sees 0"* on HanseWatt — **false**, because the classes were v67 (bounded by
the user; no record escalation at all) and because predicates and `LIMIT`
are not resolved statically. The number was mode-blind and predicate-blind,
and it was presented as a measurement.

The second temptation is estimating sharing-dependent visibility ("the user
probably sees ~40%") to keep the table full.

## Decision

Three rules, worded into the report itself:

1. The org COUNT is an **upper bound**: "could reach up to N", never
   "reaches N" — predicates/LIMIT are not resolved.
2. The bound applies **only to system-mode reads**; a user-mode read is
   bounded by the user and the gap is 0 *by construction*.
3. Sharing-dependent visibility is **`n/a` ("run as the user to measure"),
   never estimated**. Only the deterministic case (no object permission at
   all — CRUD) prints a number. Never fabricate.

The counts live OUTSIDE the fingerprint seal (they measure the org at the
moment of the run — ADR-007), and the footer says so.

## Consequences

### Positive

- The record-reach table survives scrutiny: every number in it is either an
  upper bound labelled as such or a deterministic CRUD gap.
- The demo benefits directly: two runs with the same fingerprint and
  different counts are the *liveness proof*, because the report predicted
  exactly that behaviour in writing.
- `n/a` marks precisely where a run-as-user measurement would add value —
  the honest unknown doubles as a work order.

### Negative / Trade-offs

- "Up to 3" is rhetorically weaker than "3". Accepted: the strong version
  was false once, and the correction is documented in README §what external
  review changed.
- A live COUNT needs org connectivity at scan time; scans without
  `--include-counts` lose the magnitude column entirely rather than reusing
  a stale count.

## Alternatives Considered

### Alternative A — resolve predicates statically to tighten the bound

Rejected for now: WHERE-clause resolution against live data is a research
project, and a half-resolved predicate produces exactly the false precision
this ADR bans.

### Alternative B — estimate sharing-dependent visibility

Rejected: an estimate in an evidence document is a fabricated number with
confidence formatting. `n/a` tells the truth and names the measurement that
would replace it.

## References

- Source: CLAUDE.md §3 (never fabricate / upper bound rules), README §What external review changed
- Related ADRs: ADR-003 (severity honesty, same principle), ADR-007 (counts outside the seal)
