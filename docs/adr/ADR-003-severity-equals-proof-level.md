# ADR-003: Severity = proof level, not impact

## Status

**Accepted**

## Date

2026-07-18 (in effect since the rules existed; recorded retrospectively)

## Author

Mustafa Aksu

## Context

Security scanners conventionally grade findings by impact (how bad would it
be) — which forces them to guess, and the guesses decay into noise. This
tool's findings feed security reviews and DPIAs, where the reader's first
question is not "how bad" but "is this *true*". Meanwhile two failure modes
cost credibility symmetrically: a silent false-clean (the classic sin) and a
theatrical false positive — the stripInaccessible ERROR that the runtime
oracle refuted in-org is the paid-for proof that the second is as real as
the first.

## Decision

Severity encodes **how well the claim is proven**, not how bad the outcome
would be:

- **ERROR** = proven. The escalation is demonstrated by resolution semantics
  the org has confirmed (e.g. Authority Path `returned`; a trigger whose own
  body performs DML the user can't).
- **WARN** = a real boundary that could not be proven (Authority Path
  `internal`; `stripInaccessible` present but path unprovable — caps at
  WARN, never clears; a legacy trigger with no observed DML).
- **Undetermined** on a severity-relevant path worst-cases to ERROR;
  **unknown reach** is its own finding (PS504) — the honest unknown, which
  never becomes clean.

## Consequences

### Positive

- Every ERROR survives adversarial review by construction — the proof is in
  the finding text. This is what let the sfge differential score "0/19
  contradicted by the org".
- WARN stays meaningful: it marks exactly the boundary between what static
  analysis proved and what it couldn't, so a reviewer knows where to spend
  manual effort.
- The discipline is testable: the benchmark labels severity per case, and
  the oracle punishes overclaiming exactly like underclaiming.

### Negative / Trade-offs

- A GDPR field reaching the model as WARN (path unprovable) *feels* wrong to
  impact-trained readers; the report must explain that the severity speaks
  to proof, and PS506's sort order (first in the report) carries the impact
  signal instead.
- Rules need explicit proof criteria (PS509: read the trigger body), which
  is more implementation work than a blanket ERROR.

## Alternatives Considered

### Alternative A — severity by impact (CVSS-style)

Rejected: impact of an escalation depends on data sensitivity and org
context the analyzer often cannot see; guessing it produces confident noise
and buries the one thing the tool actually knows — whether the claim is
proven.

### Alternative B — everything uncertain is ERROR ("conservative")

Rejected: that is sfge's stance, and the differential measured its cost
(no credit for secure-by-default, 7/19 against the org). A tool that cries
ERROR on proven-safe code trains users to ignore it.

## References

- Source: CLAUDE.md §3 (honesty discipline), §7 (stripInaccessible false positive)
- Related ADRs: ADR-005 (the oracle that enforces this), ADR-008 (the same honesty for numbers)
