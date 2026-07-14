# Agent Blast Radius

**A static, zero-credit analyzer that computes the *real* data-access surface of a
Salesforce Agentforce agent — at the execution-semantics layer — and flags every place
that surface exceeds the running user's own permissions or reaches a field the org has
labelled GDPR / PII.**

The headline number is the **Escalation Gap**: the fields the agent's *code* can reach
beyond its *user*. No agent is ever invoked; every input is a free metadata read; it runs
on every commit.

> **Honest framing.** This is a reference implementation built on my own initiative, not
> client work. The analyzer, the six in-org experiments, the 47 unit tests, and the live
> report against the deployed HealthRecord Assistant agent are all real, produced in a
> Developer Edition org at zero Flex Credits. The health-records domain is fictional demo
> data. Record-level leakage is reported as posture, not exact counts; dynamic SOQL is an
> honest unknown, never a silent pass.
>
> Full case study: **[mustafaaksu.dev/en/projects/agent-blast-radius](https://mustafaaksu.dev/en/projects/agent-blast-radius)**

---

## The gap this fills

Salesforce says: give agents least privilege. A whole product category (AISPM — AppOmni,
Zenity, Security Center) audits agent permissions. **All of it works at the configuration
layer: what the agent is *allowed*.** None of it reads what the agent's *code* can actually
do. On Salesforce the two genuinely differ, because execution mode — not the running user —
decides whether an action honors that user:

- an action's Apex may predate API v67 and still run **system mode by default**;
- a `WITH USER_MODE` clause **overrides** a `without sharing` declaration;
- a Flow's `runInMode` can silently grant system context;
- a clean user-mode DML can fire a **legacy trigger** that escalates anyway.

A naive scanner that flags `without sharing` without understanding this precedence produces
false positives that destroy its own credibility. So the precedence law was **proven before
it was coded**.

## The evidence-first method

[`MILESTONE_0_EVIDENCE.md`](MILESTONE_0_EVIDENCE.md) documents six hand-run, in-org
experiments (self-contained fixtures, `System.runAs`, zero credits) that established:

```
1. explicit clause      WITH USER_MODE / SYSTEM_MODE / AccessLevel.*
2. apiVersion default   >= v67 user mode ; <= v66 system mode
3. sharing declaration  governs record access only under system mode
```

…and disproved three widely-assumed shortcuts along the way:

1. a **missing** sharing declaration is *not* `without sharing` (it inherits the caller);
2. v67's user-mode default **overrides even an explicit `without sharing`** for plain operations;
3. a trigger's DML mode follows the **trigger's own apiVersion**, not the action's access level.

The experiment fixtures (`BlastRadius_E1…E6`, `Blast_Test__c`, the cascade trigger pair)
are deployed metadata in this repo — the proof is re-runnable.

## The pipeline

```
metadata ─► reach readers ─────► authority_analyzer ─► report
            apex_introspect      × permission_resolver   Escalation Gap
            flow_introspect      × ComplianceGroup        + PS5xx findings
            agent_metadata_loader  labels                 (deterministic,
                                                           fingerprint-bound)
```

All in [`blast_radius/`](blast_radius/) — see its [README](blast_radius/README.md) for the
module map and the PS5xx rule table (PS501 system-mode read on a Private object, PS506
GDPR field past the user's FLS, PS504 honest-unknown, PS510 Flow system mode, …).

## Run it

```bash
# 47 unit tests — all green
python -m unittest discover -s blast_radius -t blast_radius -p "test_*.py"

# the live agent report (Markdown + HTML dashboard)
# see blast_radius/live_agent_report.md / .html — committed evidence
```

## What the live run found

Pointed at the deployed **HealthRecord Assistant** agent (its GenAi metadata is in
`force-app/`), the report needs one line to justify the tool:

> **Escalation Gap: 1 field — 1 GDPR-labelled.**

A pre-v67 action class reads a Private object in system mode (**PS501**), and
`HealthRecord__c.Diagnosis__c` — `ComplianceGroup: PII;GDPR;HIPAA` — reaches the model
although the running user has **no field-level access** to it (**PS506**). The safe twin
(`GetHealthRecordSummarySafe`, v67 + USER_MODE) shows the same feature with a clean report.

## Related projects

- **[Prüfstand](https://github.com/aksumustafa1625/hansewatt-pruefstand)** — the behavioral
  half: a red-team corpus + deterministic verifier for what an agent *does*. Blast Radius is
  the authority half: what its code *could reach*. Together they bound an agent from both sides.
- **[hospital-org-mcp](https://github.com/aksumustafa1625/hospital-org-mcp)** — the org this
  lab lives in was itself built by an AI agent loop over six MCP deployment tools.

---

*Author: **Mustafa Aksu** — Salesforce Developer & ISV Partner (Agentforce · MCP · Data 360).
Portfolio: [mustafaaksu.dev](https://mustafaaksu.dev) · Licensed MIT.*
