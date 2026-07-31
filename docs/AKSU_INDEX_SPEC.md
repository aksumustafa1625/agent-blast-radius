# The Aksu Index — Specification

**Version: 1.0** — approved by the maintainer on 31 July 2026 (the four load-bearing
choices: pair-scoped, fields-only, four-bucket reporting, GDPR callout). Freezes
permanently at first public reference, and is never silently redefined after
that (§8).

---

## 1. One-sentence definition

> **The Aksu Index of an (agent, running user) pair is the number of distinct fields
> the code behind the agent has been *proven* able to reach beyond what that user is
> allowed to see — always reported together with what could not be resolved.**

Canonical short form:

```
Aksu Index: 6 proven (2 GDPR) · 3 unproven boundaries · 1 unresolved
```

Quoting the proven number alone while unresolved > 0 is a violation of this
specification. An unknown never reads as clean.

## 2. Scope — what one Index describes

One Index describes exactly **one agent × one running user**, at one moment, under
one tool version. It is not an org score.

- **Agent**: an Agentforce agent — its actions, the Apex/Flow/prompt-template chain
  behind them, and (on the Agent Script path) the traced data → prompt chain.
- **Running user**: a real user's effective permissions — profile, permission sets,
  permission set groups (via the platform-computed aggregate, muting applied). A
  hypothetical holder of a single permission set may be substituted, but the report
  must label it as a hypothesis, not a person.
- Org-level views (e.g., "worst pair in the org") are *derived* rollups and must be
  labelled as such.

## 3. Formal definition

Let, for the (agent, user) pair:

- **outer** = the set of qualified fields (`Object.Field`; relationship paths kept
  verbatim) reachable by the agent's resolved code chain. "Resolved" means execution
  semantics are computed per operation under the precedence law: explicit mode
  clause ▸ apiVersion default (≥ v67 → user mode) ▸ sharing declaration (record
  axis, system mode only).
- **inner** = the subset of *outer* the running user could read anyway under their
  effective permissions.
- **gap** = outer \ inner, restricted to operations proven to execute **not bounded
  by the running user** (the FLS axis resolved False).

Invariant, enforced by the tool: `outer = inner + gap` (the concentric circles).

The Index then reports four disjoint quantities:

| bucket | meaning | evidence level |
|---|---|---|
| **P — proven** | fields in *gap* whose escalation is proven (ERROR findings, PS502/PS506) | proven |
| **C — classified** | subset of P carrying the org's own compliance labels (GDPR/PII — PS506) | proven |
| **B — unproven boundaries** | same rules at WARN: a real boundary the analysis could not prove crossed (e.g., a sanitizer present but the path unprovable) | bounded, unproven |
| **U — unresolved** | reach that could not be determined at all: dynamic SOQL, SOSL without RETURNING, undetermined sharing context (PS504) | honest unknown |

**P is the headline number. C is why it matters. B and U are why the headline can
be trusted** — they are printed, never absorbed into P and never dropped.

## 4. What the Index deliberately does NOT claim

1. **It counts fields, never records.** Record-level visibility is
   sharing-dependent; the honest answer is "run as the user to measure", so the
   record axis is disclosed in prose (PS501) and never as a number in the Index.
2. **Org row counts are context, not the Index.** A `COUNT()` is an upper bound —
   "could reach up to N rows", never "reaches N".
3. **Index = 0 with U > 0 is not clean.** It is "0 proven, U unresolved", and must
   be said that way.
4. **It measures authority, not behaviour.** The Index says what the code chain
   *can* reach as built — not what the agent has done in any conversation.
5. **It is not a certificate.** It is evidence for a security review / DPIA,
   produced statically, with zero agent invocations and zero Flex Credits.
6. **It is version-bound.** A number is comparable only under the same tool
   version; the report's fingerprint (a sha256 over the rule/extractor source,
   parser version, analysis coverage, backend, and each class's own apiVersion)
   says exactly which tool produced it.

## 5. Method (summary)

1. **Resolve execution semantics** per operation — the precedence law above, on
   both axes separately: `enforces_fls` (object CRUD + field security) and
   `enforces_sharing` (record visibility). Each is True / False / **None =
   undetermined**, and None is reported, never assumed safe.
2. **Extract reach** — SOQL (subqueries are reads of their own), SOSL, DML,
   async hand-offs (Queueable/Batch/@future, `EventBus.publish` as a write),
   trigger cascades, Flow `runInMode`, prompt-template merges — via two backends
   (AST and regex) feeding the same precedence core.
3. **Resolve the user** — effective permissions from a snapshot: profile +
   permission sets + PSG aggregates (muting measured to apply).
4. **Intersect with the org's own compliance labels**
   (`FieldDefinition.ComplianceGroup`), including single-target relationship
   fields; polymorphic lookups are honestly skipped.
5. **Subtract and classify** into P / C / B / U per §3.

## 6. Evidence discipline

Every claim the Index rests on carries its evidence class — `experiment` (measured
in a real org), `platform-doc`, or `reasoned` — and severity equals proof level:
ERROR only for the proven. The precedence law itself is backed by in-org
experiments (E1–E13), a 23-case labelled benchmark (100% precision/recall, 8/8
mutation score), and a runtime oracle in which **the org, not the author, judges**
the analyzer's predictions.

## 7. Reproducibility

Same org state + same running user + same tool version ⇒ **byte-identical
reports** (proven live: two runs, equal sha256). To verify a Index someone quotes:
run the tool twice on the same inputs, hash both outputs, compare fingerprints.
The live `COUNT()` context lines are outside the deterministic fingerprint and say
so.

## 8. Freeze and versioning policy

- This specification freezes at its first public reference. After that, any change
  to §3 (the formula) or §4 (the non-claims) is a **new major version, published
  side by side** — an existing number is never silently redefined.
- The tool fingerprint identifies which specification version produced a number.
- Extensions that only *add* reporting (new sub-buckets, new labels) are minor
  versions and must not change P/C/B/U for an unchanged input.

## 9. Worked grounding (real measurements, real orgs)

- **The escalation is real**: the same read, system mode vs user mode — 5 records
  vs 0, at both the CRUD and the sharing layer (E1).
- **The version cliff is real**: identical `without sharing` source — v58 reads 5,
  v67 reads 0, and at v67 the FLS read is BLOCKED, not silently stripped (E2, E2b).
- **Both ends of the scale exist in production**: one measured org is 100% pre-v67
  across 106 classes (a large legacy gap surface); another is all-v67 and reports
  clean. Near-zero is achievable and *measured*, not hypothetical.
- **The headline case is real**: a GDPR-labelled field, invisible to the running
  user, reaching the model (PS506) — found by intersection with the org's own
  compliance labels, not by our opinion of what is sensitive.

---

*Specification draft — Aksu Software. The Index is computed by Agent Blast Radius;
the methodology above is public precisely so that the number can be checked by
people who did not produce it.*
