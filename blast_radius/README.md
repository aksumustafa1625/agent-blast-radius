# Agent Blast Radius

A static, zero-credit tool that computes the **real** data-access surface of a
Salesforce Agentforce agent at the *execution-semantics* layer — and flags every
place that surface exceeds the running user's own permissions, or reaches a field
the org has labelled GDPR / PII.

No agent is ever invoked. Every input is a free metadata read. It runs on every
commit.

---

## The gap it fills

Salesforce tells you to give agents least privilege, and an entire AISPM product
category (AppOmni, Zenity, Security Center) audits agent permissions. **All of it
works at the configuration layer — what the agent is *allowed*.** None of it reads
what the agent's *code* can actually do.

On Salesforce the two differ, because execution mode — not the running user — is
what decides whether an action honors that user:

- whether an action's Apex predates API v67 and still runs system-mode by default,
- whether a `WITH USER_MODE` clause overrides a `without sharing` declaration,
- whether an action is a Flow whose `runInMode` silently grants system context,
- whether a user-mode DML fires a legacy trigger that runs system-mode.

This tool reads that layer, diffs it against the actual running user, and
intersects the gap with the org's own `ComplianceGroup` labels. The headline is
the **Escalation Gap**: the fields the agent's code can reach beyond its user.

## The precedence law (derived empirically, see `../MILESTONE_0_EVIDENCE.md`)

For a plain SOQL/DML operation, execution mode resolves as:

```
1. explicit clause     WITH USER_MODE / SYSTEM_MODE / AccessLevel.*
2. apiVersion default  >= v67 user mode ;  <= v66 system mode
3. class sharing decl  governs record access under system mode
```

Two enforcement axes are tracked separately — `enforces_sharing` (record-level)
and `enforces_fls` (object/field) — each `True` / `False` / `None` (undetermined,
reported honestly, never a silent false-clean). Every clause of this law was
proven by hand in a live org (experiments E1–E6 in `../MILESTONE_0_EVIDENCE.md`,
E8–E16 recorded in `../CLAUDE.md` §2) before it was coded.

## Pipeline

```
metadata ─► reach readers ─────► authority_analyzer ─► report
            apex_introspect      × permission_resolver   Escalation Gap
            flow_introspect      × ComplianceGroup        + findings
            genai_prompt_introspect                       (deterministic,
            agentscript_loader                             fingerprint-bound)
            (agent_analyzer chains a whole agent's actions;
             prompt_flow_analyzer traces data -> prompt)
```

| Module | Role |
|---|---|
| `permission_resolver.py` | effective CRUD/FLS for a running user (union; View-All short-circuits records but **not** FLS) |
| `snapshot_loader.py` | pulls that permission snapshot from a live org via `sf` (profile + permsets + PSG aggregates, muting applied by the platform — E8/E9) |
| `apex_introspect.py` | per-class apiVersion + sharing + per-operation resolved mode (the precedence law); regex extractor, SOSL, sanitizer, async hand-offs |
| `apex_ast.py` + `ast_extract.js` | the real parse tree (ANTLR apex-parser) -> the same IR, plus the Authority Path taint trace |
| `flow_introspect.py` | Flow run context (flow TYPE first, then `runInMode`; no tag = honest unknown) + touched objects/fields |
| `genai_prompt_introspect.py` | prompt-template reach, every version (latent inactive reach = PS513) |
| `agentscript_loader.py` + `agentscript_extract.mjs` | Agent Script source via Salesforce's own parser |
| `prompt_flow_analyzer.py` | PS520/521/522 — the data -> prompt chain, hop by hop |
| `authority_analyzer.py` | the join → PS5xx findings |
| `agent_analyzer.py` | walks an agent (incl. agent-to-agent delegation) → analyses every action |
| `org_loaders.py` / `org_census.py` / `org_health.py` | live `sf` reads: labels, sharing, triggers, COUNT, apiVersion census |
| `report.py` / `report_html.py` | deterministic Markdown + HTML; Escalation Gap, the four-number index, fingerprint |
| `benchmark/` | hand-labelled corpus, mutation gate, runtime oracle, sfge differential |

## The PS5xx authority rules

The authoritative table, with the severity discipline behind it (ERROR = proven,
WARN = a real boundary not proven, INFO = inventory), is `../CLAUDE.md` §5.
Short form:

| Rule | Sev | Fires when |
|---|---|---|
| PS501 | ERROR/WARN | potential record-scope expansion: system-mode read on a Private object the user is restricted on |
| PS502 | ERROR/WARN | field read in system mode; user has no FLS |
| PS503 | ERROR/WARN | system-mode DML on an object the user cannot write |
| PS504 | WARN | honest unknown: dynamic SOQL, SOSL without RETURNING, unresolved reach, undetermined Flow context |
| PS505 | WARN | a classified field reaches the model although the user IS allowed it |
| PS506 | ERROR/WARN | a GDPR/PII-labelled field invisible to the running user reaches the model |
| PS507 | WARN | standard/opaque action; documented channel named when catalogued |
| PS508 | WARN | delegation chain deeper than one level |
| PS509 | ERROR/WARN | trigger cascade — ERROR only when the trigger's own body performs DML the user cannot |
| PS510 | ERROR/WARN | Flow in system context (without / with sharing), by tag or by flow type |
| PS511 | INFO | pre-v67 class inventory |
| PS512 | ERROR/WARN | `stripInaccessible` decision discarded / wrong AccessType on a read |
| PS513 | ERROR/WARN | latent reach in an inactive prompt-template version |
| PS514 | WARN | async / platform-event / callout hand-off |
| PS515 | INFO/WARN | agent-to-agent delegation (WARN when the sub-agent is unresolved) |
| PS516 | WARN | a formula field in the reach (its inputs are not resolved) |
| PS520/521/522 | INFO/WARN/ERROR | the traced data -> prompt chain |

## Run it

```bash
# tests (241 defined in 12 files; Node-dependent suites skip cleanly without node_modules)
python -m unittest discover -s blast_radius -p "test_*.py"

# benchmark + mutation gate (no org needed)
python blast_radius/benchmark/run.py
python blast_radius/benchmark/mutate.py

# a report for a real agent (needs an authenticated sf org)
python blast_radius/cli.py --agent <GenAiPlannerBundle> --org <alias> --running-user <user>
```

`sample_report.md`, `sample_agent_report.md`, `sample_gap.svg` are checked-in
examples produced from real Apex/Flow deployed in the dev org.

## Honest limitations

The current, maintained list is `../CLAUDE.md` §9 — read that, not this. The
standing ones:

- `COUNT()` is an upper bound, never a measurement; sharing-dependent record
  reach is `n/a`, never estimated.
- Static extraction ≠ the Apex compiler: dynamic SOQL, SOSL without RETURNING and
  unresolved reach are flagged as honest-unknown (PS504), never guessed. The AST
  backend is the default; the regex backend has no scope and says `None` where the
  AST resolves.
- `FieldDefinition.ComplianceGroup` is FLS-gated — the classification scan must
  run as a broad-FLS identity, and what it could see is sealed into the fingerprint.
- Flow context by flow TYPE (record-triggered / scheduled / process -> system
  without sharing) is `platform-doc`, not yet measured in-org.
- Design-time, not runtime: this bounds the *possible* blast radius from code +
  config; it complements (does not replace) runtime AISPM monitoring.

## Status

Functionally complete end-to-end (single class → whole agent, classic bundle or
Agent Script). 307 tests; benchmark 28/28 with an 8/8 mutation score; runtime
oracle on 21 of 28 cases. What is still open is listed, in priority order, in
`../CLAUDE.md` §9 — this file does not keep a second copy of that list.
