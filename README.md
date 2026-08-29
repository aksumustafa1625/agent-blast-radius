# Agent Blast Radius

**A static, zero-credit analyzer that computes the *real* data-access surface of a
Salesforce Agentforce agent — at the execution-semantics layer — and flags every place
that surface exceeds the running user's own permissions or reaches a field the org has
labelled as regulated.**

What it reports is the **[Aksu Index](https://aksuindex.com/en)** — four numbers for one
agent and one running user:

```
Aksu Index: 6 proven (1 regulated) · 0 unproven boundaries · 1 unresolved
```

**proven** — fields the code demonstrably reaches past the user · **regulated** — the subset
carrying the org's own compliance labels · **unproven boundaries** — a real boundary the
analysis could not prove was crossed · **unresolved** — reach it could not determine at all.

Quoting the proven number alone while unresolved is above zero is a **violation of the
specification**, and no API here returns fewer than four numbers. An unknown never reads as
clean. The Index is defined by a **[public specification](https://aksuindex.com/en)** and
licensed CC BY 4.0, precisely so a number carrying its name can be checked by someone who
did not produce it — including against this tool.

No agent is ever invoked; no Flex Credits are consumed; it runs on every commit and can fail
the build when the number gets worse.

And on an agent authored in Salesforce's open-source **Agent Script**, it does not stop at
*reachability* — it follows the value all the way into the prompt:

```
[PS522] Regulated field HealthRecord__c.Diagnosis__c is interpolated into the
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
> work. The analyzer, the in-org experiments, the **307 unit tests**, the accuracy
> benchmark, the live agent *authored in Agent Script and published to the org*, and the
> reports against four real orgs are all real, produced at zero Flex Credits. The
> health-records domain is fictional demo data. This is **not a certificate** — it is an
> agent-scoped security review accelerator that produces evidence for a DPIA.
>
> Full case study: **[mustafaaksu.dev/en/projects/agent-blast-radius](https://mustafaaksu.dev/en/projects/agent-blast-radius)**

**Everything this README claims is published and checkable:**

| | |
|---|---|
| The specification, CC BY 4.0 | **[aksuindex.com](https://aksuindex.com/en)** |
| The benchmark — 28 cases, 21 adjudicated by a live org, sha256-sealed, CC BY 4.0 | **[agent-authority-benchmark](https://github.com/aksumustafa1625/agent-authority-benchmark)** |
| Two real reports, as the analyzer wrote them | **[TechnoStore](https://agentblastradius.com/reports/technostore-aksu-index.html)** · **[HanseWatt](https://agentblastradius.com/reports/hansewatt-aksu-index.html)** |
| What the tool refuses to say, and why | **[agentblastradius.com](https://agentblastradius.com/en)** |

Run your own analyzer against that corpus and publish the score. That is what it is for, and
no permission is needed.

---

## Measured against Salesforce's own Graph Engine

Salesforce ships **sfge**, a data-flow engine whose two rules overlap this tool almost
exactly — the closest technical neighbour it has. Two engines disagreeing proves nothing
about either, so [`benchmark/sfge_diff.py`](blast_radius/benchmark/sfge_diff.py) runs both on
**exactly the cases a real org has already adjudicated**, generating the *same statements the
org executed*. Every disagreement has a referee:

```
Each case scored on the axis its own runtime shape adjudicates:
   sfge contradicts the org on                 8/21
   Agent Blast Radius contradicts the org on   0/21    (WARN = "did not assert")
   ...and on sfge's own binary scale           2/21    (any finding = an assertion)
```

Scored **both ways** on purpose: a sceptic can fairly say a three-level scale against a
binary engine is not the same scale, and publishing only the flattering number would be
selective reporting. The result holds either way.

**The 8 are not one thing**, and the run says which: **apiVersion blindness** on both axes
(v67 read ×2, v67 write, v67 record — sfge gives no credit for secure-by-default, and the
platform bounds that code); **SOSL** (`ApexFlsViolation` never walks a `RETURNING`, so sfge
*misses* an escape the org hands over); and two **sanitizer** rows where this tool doesn't
claim "clean" either — it says WARN.

**This is not "sfge is bad."** It is a general-purpose, deliberately conservative scanner
answering a different question — *"is an FLS check present?"* — with no notion of a running
user or a compliance label. The supportable claim is narrow: for *this* question — what can this
agent reach as *this* user — a version-aware, user-scoped analysis is measurably more
precise, and **the org is what says so**.

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

*"307 tests green"* is not an accuracy claim. A test suite proves the code does what its
author expected. [`blast_radius/benchmark/`](blast_radius/benchmark/) measures how often that
expectation is **right**:

```
cases: 28   passed: 28        PS501…PS514 → 100% precision, 100% recall
mutation score: 8/8 caught
label strength: 21 experiment · 3 platform-doc · 4 reasoned
```

Read honestly — and the runner prints this **under** the score:

- **The analyzer predicts; the ORG judges.** [`oracle.py`](blast_radius/benchmark/oracle.py)
  deploys each case as real Apex, runs it **as the modelled user**, and asserts *the
  analyzer's own prediction* — so a red test means the analyzer is wrong. It is the only
  ground truth that doesn't share a mind with the implementation. **21 of 28 cases carry a
  shape; all 21 agree.** It has a **negative control** (grant FLS on one field and read it
  under the same enforcement that blocks the other — if that ever goes red, every other
  green is vacuous), and it has already **caught a real false positive** in this tool.
- **Label strength.** Every case names where its ground truth comes from: `experiment:` (21,
  measured in a real org), `platform-doc` (3), `reasoned` (4 — the author's reasoning, which
  proves *consistency*, not correctness). That ratio is the benchmark's real quality metric;
  it was 6/10/7 before the oracle existed.
- **Not every case can be settled by an org, and the corpus says which.** PS504's *"we do not
  know"* and PS514's *"we flag what we do not follow"* assert what the **analyzer** must
  report, not what the platform does — an org cannot measure the absence of our knowledge.
  Counting those as gaps would overstate what is missing.
- **Mutation score.** A benchmark that passes on day one may just agree with the code beside
  it, so `mutate.py` breaks the analyzer on purpose — one semantic at a time — and checks the
  corpus notices. An **escape is a finding**. 8/8 caught, including *"ignore apiVersion"* —
  the exact mistake sfge makes.
- Expectations are **hand-written, never generated from the law under test** (that would be a
  mirror, not an oracle).

The benchmark and the mutation score **run in CI and fail the build**, so an accuracy
regression is caught like a broken test. The sfge differential deliberately does **not** —
not for speed (measured: 42s), but because the gate's job is to prove *this analyzer*
correct, while the differential proves a *comparative claim* that doesn't change per commit;
gating it would put a third-party engine in the critical path and go red when **sfge**
changes. It exits non-zero only if **this tool** contradicts the org.

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

## What it needs from your org

A security tool that opens with "grant me System Administrator" has already lost
the argument. Here is everything the analyzer reads, so you can decide rather than
trust.

**It only ever reads.** No record is written, no agent is invoked, no Flex Credit
is spent, and nothing is transmitted anywhere — the analysis runs on your machine
against your own authenticated session, and there is no server to transmit to.

| what it reads | why |
|---|---|
| `ApexClass`, `ApexTrigger` | the source behind the agent's actions, and their apiVersion |
| `GenAiFunctionDefinition` | which Apex or Flow each action actually invokes |
| `EntityDefinition`, `FieldDefinition` | field metadata and the org's own `ComplianceGroup` labels |
| `ObjectPermissions`, `FieldPermissions` | what the running user is allowed to see |
| `PermissionSet`, `PermissionSetAssignment` | how that permission is composed, groups and muting included |
| `User` | resolving the agent's own running user from `BotDefinition.BotUserId` |

Plus a metadata retrieve of the agent bundle, and — only with `--include-counts`
— a `COUNT()` per reached object, which returns a number and never a record.

**The permissions those imply:** `API Enabled`, `View Setup and Configuration`
(the permission objects above are setup entities), and read on the objects the
agent's own actions touch. **This list is derived from the queries the analyzer
makes, not measured by running it as a restricted user** — if you run it under a
narrower identity and something fails, that is a finding and the report will say
so rather than going quiet.

**One trap, and it is measured.** `FieldDefinition` is itself FLS-gated (E4). An
analysis identity too narrow to read it will silently see fewer compliance labels
— so a `0 regulated` result would mean "I could not look", not "nothing is
labelled". The report prints its own classification coverage for exactly this
reason: a blind spot is reported as a blind spot, never as a clean result.

## Run it

```bash
# 307 tests. In a fresh clone, before `npm install`, 32 of them skip cleanly -
# the AST and Agent-Script suites need Node - and the run still reports OK.
# (Measured in a fresh clone. Keep the clone path short: on Windows a checkout
# nested past ~240 characters makes 5 more skip, because os.path.exists fails
# on the long path rather than because anything is wrong.)
python -m unittest discover -s blast_radius -p "test_*.py"

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

> **Escalation Gap: 1 field — 1 regulated.**

A pre-v67 action reads a Private object in system mode (**PS501**);
`HealthRecord__c.Diagnosis__c` — `ComplianceGroup: PII;GDPR;HIPAA` — is read past the running
user's FLS (**PS506**); the value is *traced* into the prompt at a specific line (**PS522**).
The safe twin (v67 + `USER_MODE`) reports clean — no false positive.

**HanseWatt** reports `0 proven (0 regulated) · 0 unproven boundaries · 2 unresolved`.
Read that carefully, because the tool insists on it: **it is not clean.** Zero proven beside
two unresolved means zero proven and two unresolved, and the report prints that caveat
unprompted — in the author's own demonstration org.

It is also the most instructive measurement in the project. The **org** is **182 of 219 Apex
files pre-v67 — 83% legacy** — yet all **nine** of its agent's actions are v67. So the
actionable sentence is not *"modernise your org"*; it is that **you cannot know which part
matters until it is measured, and it is a far smaller part than you fear.**

**TechnoStore** is the opposite and the more common case: **113 Apex files, 100% pre-v67**,
reporting `6 proven (1 regulated) · 0 unproven boundaries · 1 unresolved` with a
regulated field reaching the model, and a build-failing gate. The report's *Org health* footer ties the two together: the org-wide
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
- Our flagship demo action publishes a **platform event** that the analyzer could not see at
  all. Publishing needs Create on the event and **fires that event's trigger** — the same
  cascade plain DML causes — so it is now modelled as a **write**, and PS503/PS509 apply to it.
  On TechnoStore that surfaced a **new ERROR**: the agent publishes an event the running user
  has no Create on, and that event drives MuleSoft and a customer email — work the user could
  not start. The premise underneath it did not stay believed: **E11** measured it in-org
  (v58 publish lands without Create; v67 is blocked). What is still *not* followed — a Flow,
  process, or off-platform subscriber — is what PS514 now names precisely.

**And one review's CRITICAL finding was refuted by measurement** (E8): Permission Set Groups
*are* handled — a group assignment points at the platform-computed aggregate permission set,
whose permissions equalled the union of its components exactly. **A stale docstring claiming
otherwise is what produced the false finding** — documentation that overstates *limitations*
costs credibility exactly like documentation that overstates capability.

That lesson has a sequel worth stating, because it kept happening: **four more "known gaps"
turned out to be already-closed** once anyone measured them — aliasing in the Authority Path,
`@future`/queueable reach, cross-object classification, and the entry-point result E2 had
asserted without a control. Each was a note telling the next reader to go rebuild something
that worked. **E8's untested edge became E9** (muting: the aggregate applies it — measured,
and it mattered in the dangerous direction, since crediting a user with a permission they
lack is how a static analyzer produces a false *clean*).

Also closed from that review: SOSL was a silent blind spot (and dynamic SOQL was quietly
producing no honest-unknown at all); `stripInaccessible` was unmodelled, so correct code was
flagged. Full detail in [`CLAUDE.md`](CLAUDE.md),
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
shared core, Authority Path taint (incl. helper hops, the `for (X x : [SELECT …])` loop and
named-argument constructors), the Agent Script data→prompt proof, org-agnostic CLI + sf
plugin + CI gate, org census and org-health, the accuracy benchmark with mutation testing,
the **runtime oracle** (21 of 28 cases, the org judges) and the refereed sfge differential,
permission-set groups and **muting** (E8/E9, measured), cross-object classification, and
four real orgs scanned.

**Open, in priority order** — the maintained list is [`CLAUDE.md` §9](CLAUDE.md); this is
its short form as of 2026-08-19, stated plainly rather than buried:

1. **Flow run context by flow type** — a record-/schedule-triggered flow or a Process
   Builder process now resolves to system context without sharing (the flow TYPE is read
   first, as Salesforce's own flowtest does; a tag-less autolaunched flow is an honest
   unknown, never clean). That resolution is **`platform-doc`, not yet measured in-org** —
   the measurement is the next experiment.
2. **Four v67 documentation claims that touch the precedence law and are unmeasured** —
   cross-version inheritance contamination, FLS inside a v67 trigger body, and a v67
   trigger with an explicit `WITH SYSTEM_MODE` (which E15 showed bypasses sharing and which
   PS509 cannot see today).
3. **Inter-procedural taint** — a whole record handed to an unmodelled callee, and an
   invocable returning `List<String>` with no output wrapper to trace into, stay
   `undetermined` (measured: 44% of real agent-action verdicts, down from 66%).
4. **Async reach** — Queueable/Batch/`@future` and the platform-event publish are followed;
   Flow, process and off-platform subscribers are not, and PS514 names exactly which.
5. Formula-field inputs (PS516 stays a statement about *our* resolution until E12 can be
   deployed), polymorphic lookups (deliberately unclassified), restriction rules (not
   modelled, so the gap is a **lower** bound), and a suppression/baseline mechanism.

## Documentation

| Document | What it answers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Source layout + the rules that keep two backends honest over one core |
| [docs/adr/](docs/adr/) | **13 Architecture Decision Records** — incl. why the sfge differential is not in CI, why there is no `schema_version`, and why PS516 is not (yet) a leak claim |
| [docs/architecture/](docs/architecture/) | Mermaid views: context, container, scan sequence, data model, CI contracts |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Standing rules: experiment-locked semantics, severity discipline, both-orgs verification, PR checklist |
| [SECURITY.md](SECURITY.md) | Read-only trust model, analysis-identity honesty, what a report should be trusted to mean |
| [MILESTONE_0_EVIDENCE.md](MILESTONE_0_EVIDENCE.md) | The first six in-org experiments (E1–E6), written up in full; E8–E16 are recorded in `CLAUDE.md` §2 with their probe classes under `force-app/` |
| [docs/demo/](docs/demo/) | The rehearsed demo recording script with its on-camera liveness experiment |
| [CLAUDE.md](CLAUDE.md) | Working context: the precedence law, the rule table, the mistakes already paid for |

## Related projects

- **Prüfstand** *(private)* — the behavioral
  half: a red-team corpus + deterministic verifier for what an agent *does*. Blast Radius is
  the authority half: what its code *could reach*. Together they bound an agent from both sides.
- **[hospital-org-mcp](https://github.com/aksumustafa1625/hospital-org-mcp)** — the org this
  lab lives in was itself built by an AI agent loop over six MCP deployment tools.

---

*Author: **Mustafa Aksu** — Salesforce Developer & ISV Partner (Agentforce · MCP · Data 360).
Portfolio: [mustafaaksu.dev](https://mustafaaksu.dev) · Licensed MIT.*
