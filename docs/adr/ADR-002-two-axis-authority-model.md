# ADR-002: Two axes, tracked separately — record sharing ≠ CRUD/FLS, and `None` stays honest

## Status

**Accepted**

## Date

2026-07-18 (in effect since Milestone 0; recorded retrospectively)

## Author

Mustafa Aksu

## Context

"Does this code run as the user?" is not one question. Salesforce enforces
**record visibility** (sharing) and **object CRUD + field-level security**
on separate switches: the sharing keyword governs the record axis (and only
under system mode), while the apiVersion default / explicit clause governs
CRUD/FLS. The combination `with sharing` at v58 — sharing enforced, CRUD/FLS
bypassed — can read an object the user has **no permission on at all** while
still filtering rows. Reviewers get this wrong constantly, and the author
got it wrong once too: the live TechnoStore run caught a finding that
treated one axis's enforcement as covering both.

There is also a third state: a class with no sharing declaration inherits
its caller's context (proven in E2/E10), so its record axis is genuinely
*unknown* when the caller is outside the analysed set.

## Decision

Every resolved operation carries two independent booleans-or-None:
`enforces_sharing` (record axis) and `enforces_fls` (CRUD + FLS axis).
"Bounded by the running user" requires **both** True. `None` means
undetermined, is reported as such, and **never silently becomes safe**.

## Consequences

### Positive

- The `with sharing` + pre-v67 trap is representable and detected (E2b
  proved the two axes enforce independently at v67: 0 rows AND a blocked
  read).
- Rules can be precise about *which* boundary is crossed: PS501 is the
  record axis, PS502/PS503 the FLS/CRUD axis — different evidence, different
  fixes.
- `None` gives the entry-point matrix an honest answer where measurement is
  impossible without invoking the agent (ADR-009).

### Negative / Trade-offs

- Three-valued logic everywhere: every consumer of the resolution must
  handle True/False/None, and tests must cover the None paths.
- Reports need more explanation (the two-axis table in CLAUDE.md §2 exists
  because every new reader asks).

## Alternatives Considered

### Alternative A — one "runs as user" boolean

Rejected: cannot represent `(sharing=True, fls=False)` — the exact
combination that makes legacy `with sharing` code dangerous while looking
safe.

### Alternative B — treat undetermined as the worst case everywhere

Rejected as a *blanket* rule: worst-casing is right for Authority Path
severity (undetermined → ERROR), but forcing `None` to False on the sharing
axis would fabricate a proven-bypass claim the org never exhibited. Honesty
cuts both ways: severity may worst-case, *facts* may not.

## References

- Source: CLAUDE.md §2 (two-axes table, E2b), §7 (the TechnoStore catch)
- Related ADRs: ADR-003 (how uncertainty maps to severity), ADR-009 (the unmeasurable cell)
