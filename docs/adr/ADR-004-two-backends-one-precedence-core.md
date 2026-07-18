# ADR-004: Two extraction backends, one precedence core — and equal severity for both

## Status

**Accepted**

## Date

2026-07-18 (layout since the AST backend landed; severity question settled by differential; recorded retrospectively)

## Author

Mustafa Aksu

## Context

Apex reach can be extracted two ways: a real parse tree (ANTLR `apex-parser`
via Node) or a regex extractor (pure Python). Node cannot be assumed on
every machine that runs a scan, so both must exist. The dangerous design
would be two *analyses* — each backend applying its own interpretation of
the precedence law — because they would drift, and a blind spot in one would
be invisible to users of the other. A second question followed: should
regex-sourced findings carry lower severity, since regex is "less reliable"?

## Decision

Both backends emit the same intermediate representation and feed the SAME
precedence core (`_resolve`/`_resolve_dml_fls`). When adding a reach
feature, prefer parsing it once in Python and appending to both paths (SOSL,
the sanitizer, and async hand-offs are all done this way). The AST backend
is the default; regex is the honest fallback. **Findings carry equal
severity from either backend** — the "regex should be downgraded" premise
was refuted by a differential over 104 real classes: neither backend
dominated, every contradiction found was a bug in one of them (all fixed;
OVERCLAIM/MISSED/NOISE all 0), and the residual disagreement is regex
honestly answering `None` where the AST resolves (DEGRADED 22/104).

## Consequences

### Positive

- The law lives in exactly one place; a precedence fix benefits both paths
  simultaneously and cannot half-land.
- The differential doubles as a permanent cross-check: any future backend
  contradiction is a bug by definition, not a severity judgement call.
- Degradation is honest: without Node the tool says which scope information
  it lost (`None`), instead of silently narrowing findings.

### Negative / Trade-offs

- Regex has **no scope** and cannot get one without a parse tree — that
  structural limit is disclosed in the report's backend note rather than
  patched around.
- Every new reach feature costs a "did both paths get it?" check; skipping
  it recreates the exact blind-spot asymmetry this ADR exists to prevent
  (the regex subquery false clean was one such escape, since fixed).

## Alternatives Considered

### Alternative A — AST only (require Node)

Rejected: a zero-credit analyzer that fails to install on a locked-down
review machine is a zero-value analyzer that day. Degrade, don't refuse.

### Alternative B — severity discount for regex findings

Rejected by measurement (the 104-class differential above). A discount
would have encoded a belief the data contradicts — and trained users to
dismiss findings that were exactly as proven as their AST twins.

## References

- Source: CLAUDE.md §4 (the shared-core rule), §9.5 (backend confidence — CLOSED)
- Related ADRs: ADR-003 (severity is proof, and both backends prove equally), ADR-007 (the backend is part of the fingerprint)
