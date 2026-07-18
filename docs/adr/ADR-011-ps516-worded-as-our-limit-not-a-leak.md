# ADR-011: PS516 (formula fields) is worded as OUR limit, not a platform leak, until measured

## Status

**Accepted**

## Date

2026-07-18 (wording rule since PS516 shipped; E12 remains blocked; recorded retrospectively)

## Author

Mustafa Aksu

## Context

A formula field's inputs are not resolved by this tool, so the running
user's FLS on the formula does not bound what its value *carries* —
plausibly the one channel a v67 user-mode read does not close (user mode
enforces FLS on the formula the user CAN see, not on its inputs). An
external review raised it; it is real and concrete (11 of Invoice's 93
fields are formulas, and the flagship demo action reads one). The tempting
finding is "GDPR field leaks through formula" — a headline-grade claim.

But whether a formula actually carries a field's value **past** the running
user's FLS is *not measured*. The fixture that would settle it (a Text
formula echoing `Customer_IBAN__c`) could not be deployed — the deploy
reports Succeeded and the field never appears, via either API. And this
project has already paid for believing a "well-established platform
behaviour" once: the stripInaccessible ERROR that the oracle refuted in-org
was "well-established" too.

## Decision

PS516 fires as **WARN, worded as a statement about OUR resolution**: a
formula field is in the reach and its inputs are not resolved — true
whatever the platform does. It does **not** claim the platform leaks the
inputs. Upgrading PS516 to a leak claim requires the E12 measurement first;
the blocked fixture and the blocker are documented (CLAUDE.md §9.6), not
forgotten.

## Consequences

### Positive

- The finding is unfalsifiable-proof: even if the platform turns out to
  strip formula inputs by FLS, PS516's sentence stays true (our resolution
  really doesn't follow the inputs).
- The one legitimately open platform question is carried as a named,
  blocked experiment (E12) with its exact fixture design — the next person
  with a working deploy path can settle it in an hour.
- Consistency with the severity law: unproven boundary → WARN (ADR-003).

### Negative / Trade-offs

- If the leak is real, PS516 currently *understates* a genuine channel on
  every scan until E12 lands. Accepted: the upgrade is one wording change
  away, and a premature ERROR would repeat the exact mistake already paid
  for once.
- "Our limit" wording is less quotable than "leak found" — deliberately.

## Alternatives Considered

### Alternative A — fire ERROR on classified formula inputs now

Rejected: asserts an unmeasured platform behaviour. The stripInaccessible
incident is the direct precedent — a false positive costs credibility
exactly like a false clean.

### Alternative B — stay silent until E12 is measured

Rejected: the reach fact is true and useful today; silence would be a false
clean about our own coverage.

## References

- Source: CLAUDE.md §5 (PS516 row), §9.6 (E12 BLOCKED — say so)
- Related ADRs: ADR-001 (experiments over beliefs), ADR-003 (WARN semantics)
