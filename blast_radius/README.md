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
proven by hand in a live org (experiments E1–E6) before it was coded.

## Pipeline

```
metadata ─► reach readers ─────► authority_analyzer ─► report
            apex_introspect      × permission_resolver   Escalation Gap
            flow_introspect      × ComplianceGroup        + findings
            (agent_analyzer      = PS5xx findings         (deterministic,
             chains a whole                                fingerprint-bound)
             agent's actions)
```

| Module | Role |
|---|---|
| `permission_resolver.py` | effective CRUD/FLS for a running user (union; View-All short-circuits records but **not** FLS) |
| `snapshot_loader.py` | pulls that permission snapshot from a live org via `sf` |
| `apex_introspect.py` | per-class apiVersion + sharing + per-operation resolved mode (the precedence law) |
| `flow_introspect.py` | Flow `runInMode` + touched objects/fields (no Apex parsing) |
| `authority_analyzer.py` | the join → PS5xx findings |
| `agent_analyzer.py` | walks an agent config → analyses every action |
| `report.py` | deterministic Markdown + Escalation Gap headline + two-circle SVG |

## The PS5xx authority rules

| Rule | Sev | Fires when |
|---|---|---|
| PS501 | ERROR | resolved system-mode read on a Private object the user is restricted on |
| PS502 | ERROR | system-mode read of a field with no running-user FLS |
| PS504 | WARN | reach undetermined (dynamic SOQL, unresolved fields) — honest unknown |
| PS505 | WARN | a classified (GDPR/PII) field reaches the model, even if authorized |
| PS506 | ERROR | a GDPR/PII field invisible to the running user reaches the model |
| PS507 | INFO | standard/opaque (managed) action — reach not statically analysable |
| PS510 | ERROR/WARN | Flow runs in System Mode (without / with sharing) |
| PS511 | INFO | custom action class predates API v67 (legacy-semantics surface) |

## Run it

```bash
# tests (44, all green)
python -m unittest discover -s blast_radius -t blast_radius -p "test_*.py"

# whole-agent report against real deployed artifacts
python blast_radius/agent_analyzer.py   # via the generator; see sample_agent_report.md
```

`sample_report.md`, `sample_agent_report.md`, `sample_gap.svg` are checked-in
examples produced from real Apex/Flow deployed in the dev org.

## Honest limitations

- Record-level leakage is qualitative (posture: system-mode on a Private object),
  not an exact record count.
- Static extraction ≠ the Apex compiler: dynamic SOQL, selector indirection and
  metadata-driven queries are flagged as honest-unknown (PS504), never guessed. A
  real AST (ANTLR apex-parser) or Salesforce Code Analyzer is the upgrade path.
- `FieldDefinition.ComplianceGroup` is FLS-gated — the classification scan must
  run as a broad-FLS identity.
- Design-time, not runtime: this bounds the *possible* blast radius from code +
  config; it complements (does not replace) runtime AISPM monitoring.
- The agent config is currently loaded from a normalized dict; binding to a live
  agent's retrieved GenAi metadata is a thin loader adapter.

## Status

Functionally complete end-to-end (single class → whole agent), 44 tests green.
Deferred refinements: Apex DML operations, cross-class/selector follow (PS508),
trigger-cascade wiring (PS509, keyed to trigger apiVersion per E6), and a live
GenAi-metadata loader.
