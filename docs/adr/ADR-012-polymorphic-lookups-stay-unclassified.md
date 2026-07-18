# ADR-012: Polymorphic lookups stay unclassified — an honest hole over a confident guess

## Status

**Accepted**

## Date

2026-07-18 (in effect since relationship classification landed; recorded retrospectively)

## Author

Mustafa Aksu

## Context

PS505/PS506 depend on the org's own ComplianceGroup labels, and reach often
crosses relationships (`BillToContact.Email`). Single-target relationships
are resolved: `classification()` follows `FieldDefinition.ReferenceTo` and
loads the target object's labels — tested, and proven live on TechnoStore.
(The spelling trap along the way is documented: a caller qualifying the
path as `Invoice.BillToContact.Email` used to disable resolution silently —
a false clean caused by nothing but spelling; `_rel_root` now accepts both.)

A **polymorphic** lookup (`referenceTo: [Group, User]`) is different in
kind: which object a given row points at is a per-row runtime fact. Static
analysis cannot know it, and every available default is a guess — pick one
target, union all targets, or pick the "most sensitive" target.

## Decision

Fields behind a polymorphic lookup are **deliberately left unclassified**,
and the gap is stated out loud (CLAUDE.md §9.7): a GDPR label behind a
polymorphic lookup is invisible to PS506. No target-guessing, no unioning.

## Consequences

### Positive

- No confidently-wrong classification ever enters a finding: a PS506 that
  named `Owner.Email (GDPR)` because the *User* branch is labelled, on a row
  that points at a *Group*, would be a fabricated proof.
- The rule is simple to state in review: single-target = resolved,
  multi-target = declared hole. Reviewers can audit the boundary in one
  query.

### Negative / Trade-offs

- A real coverage hole: orgs that route personal data behind polymorphic
  lookups (Owner, What/Who on activities) get no label intersection there.
  It is listed in §9 (known gaps) rather than silently absorbed.
- Union-of-targets was the defensible alternative and may deserve a
  revisit as an OPT-IN over-approximation (clearly labelled as such). That
  would be a new ADR; the default must stay guess-free.

## Alternatives Considered

### Alternative A — pick the first/primary referenceTo target

Rejected: arbitrary, and wrong exactly when it matters (mixed-sensitivity
targets).

### Alternative B — union all targets' labels (over-approximate)

Rejected as a *default*: it converts "might be GDPR depending on the row"
into "IS GDPR", which inflates PS506 with unprovable instances and dilutes
the findings that are proven. Severity = proof level (ADR-003) forbids it.

### Alternative C — resolve per-row via live queries

Rejected: per-row queries against production data are exactly what a
zero-credit static reviewer must not do (ADR-009's trust model), and the
result would be data-dependent, breaking determinism.

## References

- Source: CLAUDE.md §7 (cross-object classification + the spelling trap), §9.7
- Related ADRs: ADR-003 (proof discipline), ADR-008 (`n/a` over estimates — same principle for labels)
