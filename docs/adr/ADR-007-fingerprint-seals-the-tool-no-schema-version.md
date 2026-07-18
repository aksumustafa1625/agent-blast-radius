# ADR-007: The fingerprint seals the tool itself; a `schema_version` constant is rejected

## Status

**Accepted** (records the rejection of a task-spec proposal)

## Date

2026-07-18 (fingerprint hardening shipped; recorded retrospectively)

## Author

Mustafa Aksu

## Context

The report footer carries a config fingerprint so a verdict can be tied to
what produced it. Originally it sealed only the *inputs* (agent config,
analysed Apex/Flow, permission snapshot). But a verdict is only reproducible
against **the tool that made it**: the same inputs through a changed rule
set yield a different report with the same "fingerprint" — a silent
provenance lie. A task spec proposed the conventional fix: add a
`schema_version` constant, bumped when the rules change.

## Decision

The fingerprint seals the **tool as well as the inputs**: a sha256 of the
rule/extractor source (`analyzer`), the parser version, what the analysis
identity could see (`coverage`), the chosen `backend`, and each analysed
class's own apiVersion per action (it decides the verdict). Meta-tests pin
every field, and the control was verified to fail (drop a field → the test
goes red). **`schema_version` was deliberately NOT added**: the rule schema
*is* `authority_analyzer.py`, which the analyzer digest already hashes — a
separate constant would be redundant AND hand-maintained. Someone changes a
rule, forgets the bump, and the constant lies; that is the exact failure the
digest exists to prevent. Same reason `analyzer` is a hash, not a
`__version__` string.

## Consequences

### Positive

- "Two reports share a fingerprint" now means what a reader assumes it
  means: same inputs, same rules, same parser, same backend. The footer
  says so explicitly instead of leaving it implicit.
- The mechanism cannot be forgotten — hashing is automatic; bumping is not.
- Per-action apiVersion binding closes the subtle case: the same class text
  at a different apiVersion is a different verdict, and the seal knows.

### Negative / Trade-offs

- Any source change to the rules — even a comment — changes the analyzer
  digest, so fingerprints churn more often than a semantic version would.
  Accepted: false "same tool" is dangerous, false "different tool" is just
  a re-run.
- The live COUNT figures are explicitly OUTSIDE the seal (they measure the
  org at run time — ADR-008); the footer states this so two same-fingerprint
  runs may legitimately show different counts.

## Alternatives Considered

### Alternative A — `schema_version` constant (the task-spec proposal)

Rejected: trades a mechanism that cannot be forgotten for one that can.

### Alternative B — semantic version string maintained by release discipline

Rejected for the same reason at lower frequency; this repo has already paid
for docs that drifted from code (E8's stale docstring → a false external
CRITICAL). Provenance must not depend on memory.

## References

- Source: CLAUDE.md §9.5 (the closed backend-confidence item), §8 (determinism paragraph)
- Related ADRs: ADR-004 (backend in the seal), ADR-008 (what the seal deliberately excludes)
