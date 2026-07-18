# ADR-010: Agent Script is read with Salesforce's own parser — which surfaced an upstream bug

## Status

**Accepted**

## Date

2026-07-18 (in effect since the Agent Script path landed; recorded retrospectively)

## Author

Mustafa Aksu

## Context

The Agent Script path is where the tool's headline differentiator lives:
PS522 traces a value hop by hop from a SOQL read through `@outputs` and
`@variables` into the prompt — a proof that requires a real parse tree of
the `.agent` source. Hand-rolling a parser for a young, evolving language
would mean chasing syntax changes forever and defending every parse
disagreement. Salesforce open-sourced the language tooling
(`@sf-agentscript/*`), so the obvious move is to consume it — except the
obvious package is broken: the main entry of `@sf-agentscript/agentforce`
(npm `latest`) cannot be imported at all (compiled against a newer
`@sf-agentscript/language` than its own manifest pins; three published
packages affected). Two external reviews proposed building on exactly that
package.

## Decision

Parse `.agent` sources with **Salesforce's own parser** —
`@sf-agentscript/parser` (pinned ^4.0.1), bridged via
`agentscript_loader.py` / `agentscript_extract.mjs` into the same IR the
GenAi-metadata path produces. The upstream packaging bug was not worked
around silently: it was reported with a reproduction and root cause
(salesforce/agentscript issue #71) and fixed upstream with a post-publish
smoke test (PR #72).

## Consequences

### Positive

- Parse-tree fidelity is the vendor's own: `sf agent validate` and this
  tool read the language through the same grammar lineage (E7 validated the
  `apex://` syntax vendor-side).
- PS520/521/522 hops are nodes in a real parse tree — "this is not inferred
  reachability" is literally true, which is what makes the PS522 claim
  defensible.
- The upstream contribution cuts both ways: the dependency is healthier,
  and the project has evidence it reads its dependencies rather than
  wrapping them blind.
- Both agent input paths (Agent Script source, compiled GenAi metadata)
  converge on one IR, so the analyzer core stays input-agnostic.

### Negative / Trade-offs

- Node becomes a requirement for the Agent Script path specifically (the
  Apex regex fallback does not cover .agent parsing — no tree, no taint
  chain).
- Version pinning matters more than usual: the upstream ecosystem has
  already shipped one import-breaking release; the pin plus the sibling
  bridge's S9 staleness check are the mitigation.
- The PS522 compiled-artifact claim must stay measured: searching the
  compiled agent found ZERO occurrences of the chain — say "compiled
  metadata did not preserve it in the forms we tested", never
  "structurally impossible for all time".

## Alternatives Considered

### Alternative A — build on `@sf-agentscript/agentforce` (two reviews proposed it)

Rejected by measurement: its main entry does not import (issue #71). One
review found it broken at 2.5.31 and proposed it anyway.

### Alternative B — hand-rolled parser / regex over .agent source

Rejected: a taint chain hop-by-hop into a prompt is exactly the claim that
cannot rest on regex; one mis-parse and PS522's "every hop is a parse-tree
node" sentence becomes false advertising.

## References

- Source: README (An upstream find), CLAUDE.md §6.2 (PS522 framing)
- Upstream: salesforce/agentscript issue #71, PR #72
- Related ADRs: ADR-004 (one core, two inputs), ADR-011 (measured-claims discipline)
