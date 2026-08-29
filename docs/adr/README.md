# Architecture Decision Records

Concise, immutable records of the significant decisions behind **Agent Blast
Radius**. Format: [Michael Nygard ADR](https://github.com/joelparkerhenderson/architecture-decision-record/blob/main/templates/decision-record-template-by-michael-nygard/index.md)
with light extensions (**Alternatives Considered** + **References**).

> **Provenance note.** These ADRs were written retrospectively once the
> documentation layer was added, distilling decisions that were made — and
> already recorded in prose — across Milestone 0 to the present
> (`CLAUDE.md`, `README.md`,
> `MILESTONE_0_EVIDENCE.md`). Each ADR names its source. Stating this openly
> is cheaper than the alternative: this project has already paid twice for
> documentation that did not match reality (a stale docstring produced an
> external CRITICAL finding against a gap that did not exist).

## Why ADRs, here specifically

This tool's credibility rests on discipline, and most of that discipline is
counter-intuitive at first contact ("why is a WARN sometimes the *correct*
final answer?", "why is the differential NOT in CI?", "why no version
constant?"). Every one of those questions has been asked by an external
reviewer already. The ADRs are the standing answers — with the alternatives
that were live at the time and the measurement that killed them.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [001](ADR-001-prove-the-law-in-org-before-coding-it.md) | Prove the precedence law in-org before coding it — answer doc-claims with experiments | Accepted | 2026-07-18 |
| [002](ADR-002-two-axis-authority-model.md) | Two axes, tracked separately: record sharing ≠ CRUD/FLS, and `None` stays honest | Accepted | 2026-07-18 |
| [003](ADR-003-severity-equals-proof-level.md) | Severity = proof level, not impact | Accepted | 2026-07-18 |
| [004](ADR-004-two-backends-one-precedence-core.md) | Two extraction backends, one precedence core — and equal severity for both | Accepted | 2026-07-18 |
| [005](ADR-005-hand-written-labels-runtime-oracle-mutation.md) | Hand-written benchmark labels, a runtime oracle, and a mutation gate | Accepted | 2026-07-18 |
| [006](ADR-006-sfge-differential-not-in-ci.md) | The sfge differential is deliberately NOT in CI | Accepted | 2026-07-18 |
| [007](ADR-007-fingerprint-seals-the-tool-no-schema-version.md) | The fingerprint seals the tool itself; a `schema_version` constant is rejected | Accepted | 2026-07-18 |
| [008](ADR-008-count-is-an-upper-bound.md) | The live COUNT is an upper bound, never a measurement — and `n/a` beats an estimate | Accepted | 2026-07-18 |
| [009](ADR-009-zero-credit-constraint.md) | Zero credits: the agent is never invoked, and one unmeasurable cell stays `None` | Accepted | 2026-07-18 |
| [010](ADR-010-agent-script-via-salesforce-own-parser.md) | Agent Script is read with Salesforce's own parser — which surfaced an upstream bug | Accepted | 2026-07-18 |
| [011](ADR-011-ps516-worded-as-our-limit-not-a-leak.md) | PS516 (formula fields) is worded as OUR limit, not a platform leak, until measured | Accepted | 2026-07-18 |
| [012](ADR-012-polymorphic-lookups-stay-unclassified.md) | Polymorphic lookups stay unclassified — an honest hole over a confident guess | Accepted | 2026-07-18 |

## Lifecycle and template

Proposed → Accepted → Deprecated / Superseded by ADR-NNN; an Accepted ADR is
immutable — supersede, don't edit. When writing a new ADR, copy the skeleton
from any ADR here (Status / Date / Author / Context / Decision / Consequences /
Alternatives Considered / References).

Write an ADR when a decision changes what a finding may claim, rejects a
viable alternative, or sets a boundary future work must respect. Skip it for
reversible implementation detail — `CLAUDE.md` §7 ("mistakes already paid
for") covers incident-level lessons.

## Related documentation

- [Architecture views](../architecture/) — context / container / sequence / data model / CI
- [CLAUDE.md](../../CLAUDE.md) — the working map, the precedence law, the paid-for mistakes
- [CLAUDE.md](../../CLAUDE.md) — the working context and the exhaustive reference
- [MILESTONE_0_EVIDENCE.md](../../MILESTONE_0_EVIDENCE.md) — the in-org experiments E1–E6 in full; E8–E16, which the ADRs also cite, are recorded in `CLAUDE.md` §2 with their probe classes under `force-app/`
