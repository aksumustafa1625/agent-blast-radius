# Agent Blast Radius

**A static, zero-credit analyzer that computes the *real* data-access surface of a
Salesforce Agentforce agent — at the execution-semantics layer — and flags every place
that surface exceeds the running user's own permissions or reaches a field the org has
labelled GDPR / PII.**

The headline number is the **Escalation Gap**: the fields the agent's *code* can reach
beyond its *user*. No agent is ever invoked; no Flex Credits are consumed; it runs on
every commit and fails the build on ERROR.

And on an agent authored in Salesforce's open-source **Agent Script**, it does not stop at
*reachability* — it follows the value all the way into the prompt:

```
[PS522] GDPR/PII field HealthRecord__c.Diagnosis__c is interpolated into the
        model's prompt at line 125, and the running user has no FLS on it.

  Traced:  HealthRecord__c.Diagnosis__c
             → @outputs.summary            (Apex: SOQL → @InvocableVariable)
             → @variables.record_summary   (.agent line 128)
             → prompt                      (.agent line 125)

  This is not inferred reachability — every hop is a node in a parse tree.
```

That path is **provably absent from the compiled agent metadata** (searched in full:
zero occurrences), so a metadata-based scanner cannot produce it at all.

> **Honest framing.** A reference implementation built on my own initiative, not client
> work. The analyzer, the in-org experiments, the **97 unit tests**, the live agent
> *authored in Agent Script and published to the org*, and the report against it are all
> real, produced in a Developer Edition org at zero Flex Credits. The health-records domain
> is fictional demo data. Record counts are live `COUNT()` queries and are reported as
> `n/a` — never estimated — when record visibility is sharing-dependent. Dynamic SOQL, an
> untraceable data flow, and an opaque managed action are all *honest unknowns*, never a
> silent pass.
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
agent config ─► reach readers ─────► authority_analyzer ─► report
  .agent  (Agent Script,   apex_introspect   × permission_resolver   Escalation Gap
           official parser)  ← real Apex AST × ComplianceGroup labels  + PS5xx findings
  or GenAi metadata        flow_introspect                            (deterministic,
                                                                       fingerprint-bound)
```

Apex reach is read from a **real parse tree** (ANTLR `apex-parser`), with the regex
extractor kept as an honest fallback when Node is absent. An `.agent` file is read with
**Salesforce's own open-source parser** — so the action's `apex://` target is resolved
straight from the file, with no Tooling API lookup. Both input paths are supported, because
Agent Builder agents still compile to GenAiPlugin metadata.

All in [`blast_radius/`](blast_radius/) — module map and the full PS5xx rule table there
(PS501 record-scope expansion, PS506 GDPR field past the user's FLS, PS522 the traced
prompt interpolation, PS504 honest-unknown, PS510 Flow system mode, …).

## Run it

```bash
# 97 unit tests — all green (AST/Agent-Script suites skip cleanly without Node)
python -m unittest discover -s blast_radius -t blast_radius -p "test_*.py"

# audit any authenticated org's agent — GenAi metadata path
python blast_radius/cli.py --agent <PlannerBundle> --permission-set <PermSet>

# …or the Agent Script path, which additionally proves the data → prompt chain
python blast_radius/cli.py --agent-script path/to/My_Agent.agent \
       --permission-set <PermSet> --include-counts --fail-on ERROR
```

## What the live run found

The org runs **HealthRecord Assistant AS** — a real Agentforce agent *authored in Agent
Script*, compiled by Salesforce's own validator and published with `sf agent publish`. The
report needs one line to justify the tool:

> **Escalation Gap: 1 field — 1 GDPR-labelled.**

A pre-v67 action class reads a Private object in system mode (**PS501**);
`HealthRecord__c.Diagnosis__c` — `ComplianceGroup: PII;GDPR;HIPAA` — is read past the
running user's FLS (**PS506**); and the value is *traced* into the model's prompt at a
specific line (**PS522**). The safe twin (`GetHealthRecordSummarySafe`, v67 + `USER_MODE`)
shows the same feature with a clean report — no false positive.

Run against the same live agent, the metadata path and the Agent Script path agree on
PS501/PS506/PS511. Only the Agent Script path can produce PS522 — because the data→prompt
chain does not survive compilation.

## An upstream find

Wiring Salesforce's official Agent Script SDK in surfaced a packaging bug: the main entry
of `@sf-agentscript/agentforce` (npm `latest`) cannot be imported at all — it is compiled
against a newer `@sf-agentscript/language` than its own manifest pins, and three published
packages are affected. Reported with a reproduction and root-cause analysis
([issue #71](https://github.com/salesforce/agentscript/issues/71)) and fixed upstream with a
post-publish smoke test that installs every published package into a clean directory and
imports it ([PR #72](https://github.com/salesforce/agentscript/pull/72)).

## Related projects

- **[Prüfstand](https://github.com/aksumustafa1625/hansewatt-pruefstand)** — the behavioral
  half: a red-team corpus + deterministic verifier for what an agent *does*. Blast Radius is
  the authority half: what its code *could reach*. Together they bound an agent from both sides.
- **[hospital-org-mcp](https://github.com/aksumustafa1625/hospital-org-mcp)** — the org this
  lab lives in was itself built by an AI agent loop over six MCP deployment tools.

---

*Author: **Mustafa Aksu** — Salesforce Developer & ISV Partner (Agentforce · MCP · Data 360).
Portfolio: [mustafaaksu.dev](https://mustafaaksu.dev) · Licensed MIT.*
