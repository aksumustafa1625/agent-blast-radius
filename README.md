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

Searching the **compiled** agent artifact for that chain found **zero** occurrences — it
survives only in the Agent Script source. So for the compiled forms tested, a
metadata-based scanner has nothing to read.

> **Honest framing.** A reference implementation built on my own initiative, not client
> work. The analyzer, the in-org experiments, the **140 unit tests**, the accuracy
> benchmark, the live agent *authored in Agent Script and published to the org*, and the
> reports against four real orgs are all real, produced at zero Flex Credits. The
> health-records domain is fictional demo data. This is **not a certificate** — it is an
> agent-scoped security review accelerator that produces evidence for a DPIA.
>
> Full case study: **[mustafaaksu.dev/en/projects/agent-blast-radius](https://mustafaaksu.dev/en/projects/agent-blast-radius)**

---

## Measured against Salesforce's own Graph Engine

Salesforce ships **sfge**, a data-flow engine with an `ApexFlsViolation` rule — the closest
technical neighbour to this tool. Both were run on the same code:

| case | sfge | Agent Blast Radius | ground truth |
|---|---|---|---|
| v63 `without sharing`, plain SOQL | flags ✔ | PS502/503/506 ✔ | escalation (E1/E2) |
| **v67 plain SOQL** | **flags — false positive** | **clean ✔** | FLS *is* enforced (**E2b**, measured in-org) |

On the legacy class the two engines **agree**, which independently corroborates the finding.
On v67 — the default every org is migrating to — **sfge is version-blind and cries wolf,
while this tool correctly stays silent**, because its precedence law was established by
experiment rather than by "flag unless an explicit check is present".

That is the whole thesis, measured rather than asserted.

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

[`MILESTONE_0_EVIDENCE.md`](MILESTONE_0_EVIDENCE.md) documents hand-run, in-org experiments
(self-contained fixtures, `System.runAs`, zero credits) that established:

```
1. explicit clause      WITH USER_MODE / SYSTEM_MODE / AccessLevel.*
2. apiVersion default   >= v67 user mode ; <= v66 system mode
3. sharing declaration  governs record access only under system mode
```

…and disproved three widely-assumed shortcuts along the way:

1. a **missing** sharing declaration is *not* `without sharing` (it inherits the caller);
2. v67's user-mode default **overrides even an explicit `without sharing`** for plain operations;
3. a trigger's DML mode follows the **trigger's own apiVersion**, not the action's access level.

Two axes are tracked separately, which is the distinction most reviews get wrong:
`with sharing` at v58 enforces the **record** axis but still **bypasses CRUD/FLS** — so
"bounded by the running user" requires *both*.

## Accuracy — not a test count

*"140 tests green"* is not an accuracy claim. A test suite proves the code does what its
author expected. [`blast_radius/benchmark/`](blast_radius/benchmark/) measures how often that
expectation is **right**:

```
cases: 23   passed: 23        PS501…PS514 → 100% precision, 100% recall
mutation score: 8/8 caught
```

Read honestly — and the runner prints this **under** the score:

- **Label strength.** Every case names where its ground truth comes from: `experiment:` (6,
  measured in a real org), `platform-doc` (10), `reasoned` (7 — the author's reasoning,
  which proves *consistency*, not correctness). **Only 6 of 23 are org-measured.** That
  ratio is the benchmark's real quality metric.
- **Mutation score.** A benchmark that passes on day one may just agree with the code beside
  it, so `mutate.py` breaks the analyzer on purpose — one semantic at a time — and checks the
  corpus notices. An **escape is a finding**. 8/8 caught, including *"ignore apiVersion"* —
  the exact mistake sfge makes.
- Expectations are **hand-written, never generated from the law under test** (that would be a
  mirror, not an oracle).

Both run in CI and fail the build, so an accuracy regression is caught like a broken test.

## The pipeline

```
agent config ─► reach readers ─────► authority_analyzer ─► report
  .agent  (Agent Script,   apex_introspect   × permission_resolver   Escalation Gap
           official parser)  ← real Apex AST × ComplianceGroup labels  + PS5xx findings
  or GenAi metadata        flow_introspect                            (deterministic,
                           genai_prompt_introspect                     fingerprint-bound)
```

Apex reach is read from a **real parse tree** (ANTLR `apex-parser`), with the regex extractor
kept as an honest fallback when Node is absent. An `.agent` file is read with **Salesforce's
own open-source parser**. Both input paths are supported, because Agent Builder agents still
compile to GenAiPlugin metadata.

Reach covers Apex (SOQL, **SOSL**, DML, dynamic queries, one-level delegation), Flow
`runInMode`, prompt templates (**every version** — a field only an *inactive* version reaches
is latent, PS513), and standard-action channels. `Security.stripInaccessible` is modelled as
the real sanitizer it is; async/event/callout hand-offs are surfaced as explicit unknown
edges rather than silently dropped.

Full rule table (PS501–PS514, PS520–522) and module map in
[`blast_radius/`](blast_radius/) and [`CLAUDE.md`](CLAUDE.md).

## Run it

```bash
# 140 unit tests (AST/Agent-Script suites skip cleanly without Node)
python -m unittest discover -s blast_radius -t blast_radius -p "test_*.py"

# accuracy, not just green tests
python blast_radius/benchmark/run.py
python blast_radius/benchmark/mutate.py

# audit any authenticated org's agent — GenAi metadata path
python blast_radius/cli.py --agent <PlannerBundle> --permission-set <PermSet> \
       --org <alias> --include-counts --fail-on ERROR

# …or the Agent Script path, which additionally proves the data → prompt chain
python blast_radius/cli.py --agent-script path/to/My_Agent.agent --permission-set <PermSet>

# whole-org API-version census (how much of the org still defaults to system mode)
python blast_radius/org_census.py --org <alias>

# prove determinism: two runs, byte-identical output
python blast_radius/verify_deterministic.py -- --agent <X> --permission-set <Y> --org <alias>
```

## What it found, across four real orgs

**HospitalOrg** runs **HealthRecord Assistant AS** — a real Agentforce agent *authored in
Agent Script*, validated by Salesforce's own compiler and published with `sf agent publish`.
One line justifies the tool:

> **Escalation Gap: 1 field — 1 GDPR-labelled.**

A pre-v67 action reads a Private object in system mode (**PS501**);
`HealthRecord__c.Diagnosis__c` — `ComplianceGroup: PII;GDPR;HIPAA` — is read past the running
user's FLS (**PS506**); the value is *traced* into the prompt at a specific line (**PS522**).
The safe twin (v67 + `USER_MODE`) reports clean — no false positive.

**HanseWatt** (10/10 classes at v67) comes back **clean** — the tool stays quiet on a
modern org. **TechnoStore** is the opposite and the more common case: **106 classes + 7
triggers, 100% pre-v67**, a 6-field escalation gap with a GDPR field reaching the model, and
a build-failing gate. The report's *Org health* footer ties the two together: the org-wide
pre-v67 debt is the *root cause* of that agent's blast radius — at v67 the gap would be zero.

## What external review changed

Two independent technical reviews were commissioned against the project brief. Their findings
were verified **against the code**, not accepted — and the outcome is the part worth reading:

**Three of this tool's own headline numbers were wrong, and it now says so:**

- *"HanseWatt: the agent reaches 31 records where the user sees 0"* — **false**. Those classes
  are v67, so the agent is bounded by its user; there is no record escalation. The record
  count was mode-blind, and predicate-blind besides (the org `COUNT()` is an **upper bound** —
  `WHERE`/`LIMIT` are not resolved). Both fixed; the report now says *"could reach up to N"*.
- *"TechnoStore's legacy trigger: ERROR"* — **unproven**. Its body performs no DML. PS509 is
  now proof-based: ERROR only when the trigger's own body writes something the user can't.
- Our flagship demo action publishes a **platform event** whose subscriber was never analysed.
  Now reported as PS514 rather than silently dropped.

**And one review's CRITICAL finding was refuted by measurement** (E8): Permission Set Groups
*are* handled — a group assignment points at the platform-computed aggregate permission set,
whose permissions equalled the union of its components exactly. **A stale docstring claiming
otherwise is what produced the false finding** — documentation that overstates *limitations*
costs credibility exactly like documentation that overstates capability.

Also closed from that review: SOSL was a silent blind spot (and dynamic SOQL was quietly
producing no honest-unknown at all); `stripInaccessible` was unmodelled, so correct code was
flagged. Full detail in [`PROJECT_STATE_AND_REVIEW_BRIEF.md`](PROJECT_STATE_AND_REVIEW_BRIEF.md),
Appendix AD.

For a security tool, finding your own claims wrong is the point.

## An upstream find

Wiring Salesforce's official Agent Script SDK in surfaced a packaging bug: the main entry of
`@sf-agentscript/agentforce` (npm `latest`) cannot be imported at all — it is compiled against
a newer `@sf-agentscript/language` than its own manifest pins, and three published packages are
affected. Reported with a reproduction and root-cause analysis
([issue #71](https://github.com/salesforce/agentscript/issues/71)) and fixed upstream with a
post-publish smoke test that installs every published package into a clean directory and
imports it ([PR #72](https://github.com/salesforce/agentscript/pull/72)).

## Where it stands

**Done:** the precedence law (experiment-established), both extraction backends over one
shared core, Authority Path taint, the Agent Script data→prompt proof, org-agnostic CLI + sf
plugin + CI gate, org census and org-health, the accuracy benchmark with mutation testing,
and four real orgs scanned.

**Open, in priority order** — stated plainly rather than buried:

1. **Benchmark v2** — a *runtime oracle*: deploy each fixture, execute as the modelled user,
   record the outcome. Moving one case from `reasoned` to `experiment:` is worth more than ten
   new reasoned cases. Then a systematic sfge differential over the whole corpus.
2. **Inter-procedural taint** — aliases and helper returns are `undetermined` today.
3. **Async reach** is flagged (PS514) but not followed.
4. Muting permission sets, the entry-point matrix, backend-confidence in severity, and
   relationship/polymorphic field classification.

## Related projects

- **[Prüfstand](https://github.com/aksumustafa1625/hansewatt-pruefstand)** — the behavioral
  half: a red-team corpus + deterministic verifier for what an agent *does*. Blast Radius is
  the authority half: what its code *could reach*. Together they bound an agent from both sides.
- **[hospital-org-mcp](https://github.com/aksumustafa1625/hospital-org-mcp)** — the org this
  lab lives in was itself built by an AI agent loop over six MCP deployment tools.

---

*Author: **Mustafa Aksu** — Salesforce Developer & ISV Partner (Agentforce · MCP · Data 360).
Portfolio: [mustafaaksu.dev](https://mustafaaksu.dev) · Licensed MIT.*
