# CLAUDE.md — working context for Agent Blast Radius

This file is for whoever (or whatever) picks this repo up next. It is not marketing;
it is the map, the semantics you must not get wrong, the discipline that makes the
tool worth anything, and the mistakes already paid for. Read the discipline section
before changing a rule.

---

## 0. WHERE WE ARE — read this before anything (updated 2026-08-04)

### 0.0 THE STRATEGIC POSTURE — this governs every other decision

**Plan A is the maintainer's FDE role at Salesforce.** Decided 2026-08-04 after four
independent launch reviews (`docs/LAUNCH_ROUND5_DECISION_2026-08-04.md` §10).

The commercial launch is **not cancelled — it is re-aimed.** Same artifacts, published
for a different purpose:

| commercial launch (on hold) | technical reputation (live) |
|---|---|
| "buy this" | "I found this, measured it, here is the proof" |
| early-access list, price, 5 pilots | **no CTA at all** |
| entity, DPA, commercial Impressum, urgent trademark | **none of it needed** |
| competes with Plan A (Nebentätigkeit, IP clauses) | **serves Plan A directly** |

**Why this was easy: it is not a fork, it is a sequence.** If the FDE role happens,
technical reputation is what gets him hired. If it does not, he has built exactly the
distribution and credibility the commercial launch was missing — the one gap all four
reviewers named. A strategy correct in both futures needs no choosing between.

**Publishing order is load-bearing — reversed, it reads as selling and damages Plan A:**

```
1. FINDING       v58 = 5 records, v67 = 0.  No product name, no link, no CTA.
2. METHOD        E13 + our own stripInaccessible false positive, together.
3. CONTRIBUTION  the public benchmark — corpus + org verdicts, open.
4. TOOL          only if interest arrives. Still no selling.
```

**Hard rules while Plan A is live** (`LAUNCH_ROUND5_DECISION` §10.3, §10.6):

- ❌ **The sfge differential appears in NO public material.** Round 5 said "not the
  headline"; with Salesforce as the employer target it became "never published". It
  stays in the repo and the briefing for anyone who asks privately. Enforced
  mechanically by `export_public_corpus.py`, which strips such sentences and then greps
  its own output — a rule in a script cannot be forgotten.
- ❌ No price, no early-access list, no pilot offer, no SLA, no roadmap promise.
- 🔒 **Never say the tool is free or will remain free.** That single sentence is what
  keeps the commercial path open if side-activity approval comes, or if Plan A doesn't.
- ✅ **The platform is the hero, and the measurement genuinely supports that**:
  Salesforce got this right at v67 (secure-by-default). The gap we measure is not a
  platform defect — it is how much customer code has caught up. E13 is the ideal
  story: a claim said v67 triggers always run in system mode; the org showed the
  platform is *safer* than the claim.

### 0.1 What is ready and waiting for the maintainer

| artifact | state |
|---|---|
| `docs/POSTS_TECHNICAL_REPUTATION_2026-08.md` | Post 1 + Post 2 written, ready to publish |
| `docs/REPRO_v58_v67.md` | the shareable experiment recipe — the reply to "show me" |
| `public-benchmark/` | 21 org-adjudicated cases + 7 labelled unadjudicable, sha256-committed, **tool unnamed** |
| `reports/TechnoStore_AksuIndex.*` | a real report, md/html/pdf |
| `docs/AKSU_INDEX_SPEC.md` | v1.0 approved, freezes at first public reference |
| `site/aksuindex/` | written, **not deployed** — and no longer urgent |

**Maintainer's next step:** read Post 1, approve or edit, publish Monday 08:00 DACH.
Then put `public-benchmark/` in its own public GitHub repo — for an FDE application a
GitHub profile *is* the CV, and what stands there says "measures the platform, and
publishes his own errors".

### 0.2 Engineering work still open (was §0 before the pivot — now second priority)

**Make the Aksu Index the FIRST thing a reader sees.** *(Clarified by the
maintainer 2026-07-31: this is not an org-level rollup — it is about prominence.
Whoever opens the report should meet the Index immediately.)*

Where it sits today, in `report_html.py`:

| order | element | line |
|---|---|---|
| 1 | eyebrow "Agent Blast Radius Report" | 627 |
| 2 | `<h1>` agent name | 628 |
| 3 | `<p class="sub">` static/zero-credit blurb | 629 |
| 4 | **the Index — as `<p class="sub">`, i.e. small subtitle text** | **635** |
| 5 | stakeholder summary, API posture, backend note | 631–641 |
| 6 | the visual hero: `.gapnum` at 64px + the circles | 654–657 |

So the eye currently lands on the **gap number**, and the Index reads as a caption.
It should be the other way round: **the Index is the product's public metric and the
report is its distribution vehicle** (§6.1).

Target: a dedicated Index band directly under the `<h1>` — the four numbers large and
unmissable, P dominant, C/B/U legible beside it, and the "NOT clean" sentence attached
whenever P = 0 while U > 0. Keep `.gapnum` and the circles; they explain the number
rather than compete with it. **The four numbers must stay together** — no layout may
present P alone (spec §1, and `aksu_index_line()` deliberately offers no shorter form).
Do the md report too: today it is line 7 inside the ASCII block, which is fine for a
terminal but should still read as the headline rather than as one row among the reach
summary.

**Group the remediation list by FIX, not by finding.** Measured on the real
TechnoStore report: 12 action items, of which **6 are the identical fix in the
identical class** (`SendPaymentRemindersAction` → "Enforce FLS"). The customer reads
6 jobs; it is **one line of code** that closes all six. Target shape:

```
▸ Add WITH USER_MODE to SendPaymentRemindersAction
  → closes 6 findings (1 regulated)          [PS502 ×5, PS506 ×1]
```

This changes **no verdict and no count** — the same findings, an honest workload
table instead of an inflated one. Today's version overstates the work, which is both
wrong and (in a sales conversation) weaker than the truth. `_remediation()` in
`report_html.py` and the md writer in `report.py` both need it, plus tests.

---

## 1. What this is, in one paragraph

**Agent Blast Radius** is a static, zero-credit analyzer for Salesforce Agentforce
agents. It answers one question mechanically: *given this agent and this running
user, which objects, fields and records can the code behind the agent actually
reach — and where does that exceed what the user is allowed to see?* It does this by
resolving Apex/Flow **execution semantics** (apiVersion, sharing declaration, mode
clauses), diffing the result against the running user's **effective permissions**,
intersecting with the org's own **ComplianceGroup (GDPR/PII) labels**, and — on the
Agent Script path — **tracing the data → prompt chain hop by hop**. No agent is
invoked. No Flex Credits are spent. No data leaves the machine.

It is **not** a certificate. Position it as an *agent-scoped security review
accelerator* that produces evidence for a DPIA / security review.

---

## 2. The precedence law — the heart of the tool

For a plain SOQL/DML operation, execution mode resolves in this order:

1. **Explicit operation clause** — `WITH USER_MODE` / `WITH SYSTEM_MODE` /
   `AccessLevel.*` / `as user` / `as system`. Beats everything.
2. **apiVersion default** — **≥ v67 → user mode**, **≤ v66 → system mode**.
3. **Class sharing declaration** — governs the **record** axis only, and only under
   system mode.

### Two axes, tracked separately. This is the distinction reviewers get wrong.

| axis | means | set by |
|---|---|---|
| `enforces_sharing` | record-level visibility | sharing keyword (under system mode), or user mode |
| `enforces_fls` | object CRUD **and** field-level security | apiVersion default / explicit clause |

Each is `True` / `False` / **`None` = undetermined** (a class with no declaration
inherits its caller's context — proven in E2). Undetermined is reported honestly,
never silently treated as safe.

**The trap:** `with sharing` at v58 gives `(sharing=True, fls=False)`. It filters by
sharing rules but **bypasses CRUD/FLS**, so it can read an object the user has no
permission on at all. "Bounded by the running user" requires **BOTH** axes True. I
got this wrong once and the live TechnoStore run caught it — see §7.

### Facts that are MEASURED, not assumed (Milestone 0, real org)

| id | what it proved |
|---|---|
| **E1** | The escalation is real: system-mode read = 5 records, user-mode = 0, at both the CRUD layer and the record-sharing layer. |
| **E2** | Same `without sharing` source: **v58 = 5 records, v67 = 0**. Also: *no declaration ≠ without sharing* (a declaration-less class inherits the caller). |
| **E2b** | The two-axis proof at v67: record axis enforced (0 rows) **and** FLS enforced (read **BLOCKED**, "No such column"). FLS is **blocked/throws**, not silently stripped. |
| **E3** | `WITH USER_MODE` on a `without sharing` class → 0. Operation clause beats the declaration. |
| **E4** | `FieldDefinition.ComplianceGroup` is readable free — but the query must be **bounded per EntityDefinition**, and **FieldDefinition is FLS-gated** (a narrow analysis identity silently misses labels). |
| **E5** | Flow `runInMode` is declarative/static → Flow actions analysable without Apex parsing. |
| **E6** | A trigger's DML runs in the mode of the **trigger's OWN apiVersion**, independent of the initiating action. |
| **E7** | Agent Script `apex://` syntax is vendor-validated (`sf agent validate` → success). |
| **E8** | **Permission Set Groups are already handled**: every PSG has a platform-computed aggregate `PermissionSet` (`Type='Group'`); a group assignment's `PermissionSetAssignment.PermissionSetId` points at it; the aggregate's ObjectPermissions **equalled the union of its components exactly**. |
| **E9** | **Muting is handled, and now measured** (it was E8's untested edge). A muter removing FLS on a field its component grants: the **component still shows `PermissionsRead=true`, the aggregate has NO row** — so reading the aggregate applies muting. Runtime agrees (`BlastRadius_E9_Muting.cls`): `WITH USER_MODE` → **BLOCKED**, while a pre-v67 class still reads the value — the muted GDPR field escapes exactly as PS506 says. Platform constraint worth knowing: **muting Read alone is rejected** (mute Edit too), and a rejected muting set deploys **empty**, which makes any muting test vacuously green. |
| **E13** | **A v67 trigger's own DML IS bounded by the running user — the most dangerous review claim, refuted in-org twice.** A reviewer cited Summer '26 (*"Apex Triggers ... will now always run in system mode across all API versions"*); if true, PS509 fires only below v67 and would be a **false negative in the middle of the thesis**. Measured on Summer '26: a **v67** trigger writing `Casc_Child__c` for a user with no Create → **BLOCKED** (`BlastRadius_E13_TriggerMode.cls`). E6 stands. **Re-measured 2026-08-04 with the controls the first version lacked** (see §7 — the first version caught a bare Exception, discarded the message, and could not distinguish "trigger denied" from "parent insert failed before the trigger ran"). The org's verbatim answer: `DmlException: CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY, BlastTestV67Trigger: execution of AfterInsert caused by: System.SecurityException: Access to entity 'Casc_Child__c' denied` — the error names the **child entity** and the **trigger's own line**, so the parent did reach the trigger and the trigger's DML is what was denied. **Scope, do not widen it:** this measures the **CRUD axis** of DML the trigger's own body performs. Whether a v67 trigger enforces sharing or FLS is **not measured**. |
| **E11** | **The publish premise, measured** — it was `platform-doc` while a LIVE TechnoStore ERROR already rested on it. A user with **no ObjectPermissions row at all** on `Blast_Event__e`: **v58 publish LANDS** (`WROTE=ok` — the Create bypass is real, so modelling publish as a write and applying PS503 is right), **v67 publish BLOCKED**. The `SaveResult` is read rather than trusting a throw — whether user mode throws or returns a failure was exactly the thing not to assume. Writing the case found a hole in the feature: `EventBus.publish(new X__e(...))` resolved to None, so PS503 never fired on an inline-constructed event. |
| **E10** | **"No declaration" enforces sharing — now with controls.** Three pre-v67 invocables differing only in the declaration, same caller, same user, same admin-owned rows on a Private object: `without sharing` → **5**, no declaration → **0**, `with sharing` → **0**. Confirms E2's round 1, which had **no control** (0 alone could have meant the user had nothing to see). **Only one cell of the matrix**: the caller here is Apex. The agent's own entry point (an invocable with *no* calling Apex class) stays unmeasured — so `enforces_sharing=None` for a declaration-less pre-v67 class is still the honest answer. |

**Do not "fix" the precedence law from documentation.** This has now happened
**three times**, from independent reviews, all citing real Salesforce sources:
- v67 `without sharing` "must be record-bypassing" → **E2b** disproved it in-org.
- v67 triggers "always run in system mode" (Summer '26 release notes) → **E13**
  disproved it in-org, on Summer '26.
- The same trigger claim again, this time marked **CONFIRMED against primary
  sources** in a verified external brief (2026-08-04) → **E13 re-run with proper
  controls** disproved it again, and the org named the child entity and the
  trigger's own line in the exception.
All three would have broken correct code. Documentation describes intent; the org
describes behaviour, and only one of them is what your customer runs. **Answer a
doc-based claim with an experiment, never with an edit** — and note that every
reviewer was doing exactly the right thing by raising them.

**But the third one earned its own lesson, because the challenge was right about
the METHOD even though it was wrong about the platform** — see §7's entry on E13's
missing control. A claim you have already refuted is still worth re-testing when
someone credible re-asserts it: the re-test is what found the flaw in our own
experiment.

---

## 3. The honesty discipline — the whole product

This is the part that makes the tool credible. Breaking it is worse than shipping
fewer features.

- **A silent false-clean is worse than an honest unknown.** Unknown never becomes
  clean. `PS504` exists for exactly this.
- **Severity = proof level.** Not impact. `ERROR` = proven; `WARN` = a real boundary
  that we could not prove. Every rule follows this:
  - Authority Path `returned` → ERROR; `internal` (proven not to leave) → WARN;
    `undetermined` → worst case (ERROR).
  - `stripInaccessible` present but path unprovable → caps at WARN, never clears.
  - A legacy trigger with no observed DML → WARN, not ERROR.
- **Never fabricate a number.** Record visibility that is sharing-dependent is `n/a`
  ("run as the user to measure"), never estimated.
- **Never present an upper bound as a measurement.** The org `COUNT()` is an
  **upper bound** — predicates and `LIMIT` are not resolved. Say "could reach up to
  N", never "reaches N".
- **State where a claim comes from.** The benchmark's `truth` field
  (`experiment:` / `platform-doc` / `reasoned`) is the model for this.
- **Docs that overstate LIMITATIONS cost credibility too.** A stale docstring
  claiming PSG wasn't handled became an external CRITICAL finding against a gap that
  did not exist (see E8). Keep docs measured.
- **Writing your own position WORSE than it is costs exactly what writing it better
  does.** The launch review prompt told four reviewers "zero audience built, starting
  from nothing" and "not on AppExchange". Both were false: there is a 13,000-member
  community (adjacent topic, but warm), and an AppExchange security review has already
  been passed once with a sibling product, so a listing is a second one on an existing
  path. Three of the four reviewers then built a "you have no distribution" diagnosis
  partly on that false ground. **An external review can only be as good as the ground
  you hand it** — false modesty produces confidently wrong advice, and it is not
  humility, it is an inaccurate input.

---

## 4. Repo map

```
blast_radius/
  cli.py                    entry point. --agent | --agent-script, --org,
                            --permission-set | --running-user, --include-counts,
                            --fail-on, --apex-backend, --no-org-health
  apex_introspect.py        THE precedence law (_resolve/_resolve_dml_fls) + regex
                            extractor (depth-scanned SOQL: subqueries are reads of
                            their own) + SOSL + sanitizer + async hand-offs
  apex_ast.py               subprocess bridge to the real parse tree
  ast_extract.js            ANTLR apex-parser walker -> IR (+ Authority Path taint)
  flow_introspect.py        Flow XML -> runInMode + per-element reach
  genai_prompt_introspect.py  prompt templates, ALL versions (latent = PS513)
  agentscript_loader.py     Salesforce's own Agent Script parser -> IR
  agentscript_extract.mjs
  prompt_flow_analyzer.py   PS520/521/522 — the data -> prompt chain
  authority_analyzer.py     the join: reach x permissions x labels -> findings
  permission_resolver.py    pure EffectivePermissions over a snapshot
  snapshot_loader.py        username -> profile + permsets (+ PSG via aggregate)
  org_loaders.py            live sf queries (classification, sharing, triggers,
                            COUNT, permsets, god-mode grants, OWD)
  org_census.py             standalone whole-org apiVersion census
  org_health.py             "beyond this agent" report footer
  report.py / report_html.py  deterministic md + themed html; report.py also owns
                            aksu_index() / aksu_index_line() — the public metric
  make_pdf.py               html -> pdf via headless Edge. PRESENTATION ONLY:
                            never part of the analysis, cannot change a verdict
  verify_deterministic.py   runs the CLI twice, sha256-diffs both outputs
  benchmark/                corpus.py + run.py + mutate.py + oracle.py (runtime
                            oracle: deploys each case, the ORG judges) + README.md
  fixtures/                 permission snapshots + apex/prompt fixtures
  test_*.py                 224 tests in 12 files
public-benchmark/         THE PUBLIC ARTIFACT. corpus.json (21 org-adjudicated
                          cases + 7 labelled unadjudicable) + cases/*.cls +
                          CHECKSUMS.md. Generated by benchmark/export_public_corpus.py,
                          which strips third-party engine mentions and greps its own
                          output. The tool is NOT named anywhere in it (§0.0).
docs/LAUNCH_ROUND5_DECISION_2026-08-04.md
                          4 launch reviews + the Plan A decision. §10 is the posture.
docs/POSTS_TECHNICAL_REPUTATION_2026-08.md
                          Post 1-4, written, awaiting the maintainer
docs/REPRO_v58_v67.md     the shareable experiment — the answer to "show me"
docs/AKSU_INDEX_SPEC.md              the public metric, v1.0, frozen at first
                                     public reference (§8 of the spec)
docs/AKSU_INDEX_TECHNICAL_BRIEFING.{html,pdf}
                                     ~1950-line briefing, TR then EN, written to
                                     be ARGUED with: 22 hard questions answered
site/aksuindex/           aksuindex.com — index/legal/privacy, one self-contained
                          file each, zero external dependencies
reports/                  committed real runs (TechnoStore_AksuIndex.md/html/pdf)
```

**Both extraction backends feed the SAME precedence core.** When adding a reach
feature, prefer parsing it **once in Python** and appending to both paths (this is
how SOSL, the sanitizer, and async hand-offs are done) — otherwise the AST path
gets a blind spot the regex path doesn't have, or vice versa.

---

## 5. The rules

| rule | severity | fires when |
|---|---|---|
| PS501 | ERROR/WARN | Potential record-scope expansion (system mode + Private OWD). "Potential" is deliberate: predicates aren't analysed. |
| PS502 | ERROR/WARN | Field read in system mode; user has no FLS. |
| PS503 | ERROR/WARN | System-mode DML on an object the user can't write. |
| PS504 | WARN | **Honest unknown** — dynamic SOQL, SOSL without RETURNING, unresolved reach. Fires even when the object is unknown. |
| PS505 | WARN | Classified field reaches the model although the user IS allowed it (data minimisation). |
| PS506 | ERROR/WARN | **The headline.** GDPR/PII-labelled field, invisible to the user, reaches the model. Sorted first in the report. |
| PS507 | WARN | Opaque/standard action; names the documented channel when catalogued. |
| PS508 | WARN | Delegation chain deeper than one level. |
| PS509 | ERROR/WARN | Trigger cascade. **ERROR only when the trigger's own body performs DML the user can't** (read from the Body). Legacy trigger alone = WARN. |
| PS510 | ERROR/WARN | Flow in system mode. |
| PS511 | INFO | Pre-v67 class inventory. |
| PS512 | ERROR/WARN | `stripInaccessible` decision discarded (no-op bug) / wrong AccessType for a read. |
| PS513 | ERROR/WARN | Latent reach in an INACTIVE prompt-template version. |
| PS514 | WARN | Async/event/callout hand-off. For a platform event the publish IS analysed (a write, cascade via PS509); the open edge is a Flow/process/external subscriber. |
| PS515 | INFO/WARN | Agent-to-agent delegation. INFO when the sub-agent was expanded into this report; **WARN when unresolved** — that agent's surface is genuinely not analysed, so the report UNDERSTATES the blast radius. (Was missing from this table until 2026-07-31; found by grepping the rule literals while writing the briefing.) |
| PS516 | WARN | **A FORMULA field in the reach.** Its inputs aren't resolved, so the user's FLS on the formula doesn't bound what its value carries — **the one channel a v67 user-mode read does not close** (user mode enforces FLS on the formula the user CAN see, not on its inputs). Worded as OUR limit, not a leak: the platform behaviour is **not measured** (see §9). |
| PS520/521/**522** | INFO/WARN/**ERROR** | The data → prompt chain, traced hop by hop. **PS522 is the differentiator.** |

---

## 6. The differentiators (state them precisely, not broadly)

1. **Version-aware precedence — and the org, not us, says so.** The sfge differential
   is now **systematic**, not two hand-run cases: `benchmark/sfge_diff.py` generates
   the SAME statements the oracle ran (`oracle.case_body`) for all **19 org-adjudicated
   cases**, so every disagreement has a referee. **Each case is scored on the axis its
   own runtime shape adjudicates** — never on an unrefereed column:
   **sfge contradicts the org on 7/19; Agent Blast Radius on 0/19** — and **2/19 even
   when scored on sfge's own binary scale** (any finding = an assertion). Run it both
   ways; publishing only the flattering score is selective reporting.
   The 7 are **not one thing** — say which:
   - **apiVersion blindness, BOTH axes** (v67 read ×2, v67 write, **v67 record**): sfge
     wants an explicit check and gives no credit for secure-by-default. The platform
     bounds this code (E2b + E2 + oracle). Unambiguous, and the case the whole market
     is migrating toward. The record row is `DatabaseOperationsMustUseWithSharing` on
     v67 `without sharing` — it used to be printed-not-scored; the `kind:"record"`
     shapes gave it a referee and the org confirmed it.
   - **SOSL**: `ApexFlsViolation` never walks a `RETURNING`, so sfge **misses an escape
     the org hands over** — a false *negative*, new here and not in Appendix AD.
   - **the 2 sanitizer rows**: weakest of the six. We don't call them clean either — we
     say **WARN**. Report as a severity-discipline difference, not sfge being broken.
   **Never state this as "sfge is bad."** It is a general-purpose, deliberately
   conservative scanner answering *"is an FLS check present?"*, with no notion of a
   running user or a GDPR label. The supportable claim is narrow: for *this* question
   — what can this agent reach as *this* user — a version-aware, user-scoped analysis
   is measurably more precise. **Strongest competitive evidence in the project, and it
   is measured, not asserted.**
2. **PS522 — the traced data→prompt chain.** Searching the *compiled* agent artifact
   found **0** occurrences of the chain (`record_summary`, `{!`, `set @variables`,
   `@outputs`) — it exists only in Agent Script source. Say: *"a proof for the
   patterns supported by the parse tree, which compiled metadata did not preserve in
   the forms we tested."* **Do not** say "structurally impossible for all time".
3. **Agent-scoped, user-scoped, label-intersecting.** Individually these exist
   (CRUD/FLS scanners, permission explorers, DLP). The composition is the novelty.
4. **"Modernise only what the agent touches."** Measured on two real orgs the same
   day: TechnoStore's agent is 2/2 pre-v67 → **Index 6**; HanseWatt's org is **83%
   legacy** yet its agent's 9 actions are all v67 → **Index 0**. The actionable
   claim is therefore not "migrate your org" but *"you cannot know which part matters
   until it is measured — and it is a far smaller part than you fear."* This is the
   most useful sentence the tool produces for a customer, and it is measured.

---

## 6.1 The Aksu Index — the public metric (spec: `docs/AKSU_INDEX_SPEC.md`)

The market-facing name for what the tool computes. **The term is public; the
measurement is the product** — the specification is published precisely so a number
can be checked by people who did not produce it (the FICO shape: everyone quotes the
score, one company computes it).

```
Aksu Index: 6 proven (1 regulated) · 0 unproven boundaries · 1 unresolved
```

| bucket | source | rule |
|---|---|---|
| **P** proven | PS502/PS506 at **ERROR** | the headline number |
| **C** classified | the **subset of P** carrying the org's own labels | never added to P — it is already inside it |
| **B** unproven boundaries | PS502/PS506 at **WARN** | **never** merged into P |
| **U** unresolved | PS504 count | printed, never dropped |

- **`aksu_index()` splits `escalation_gap()`; it does not replace it.** The concentric
  circles keep the union (the spec defines the gap as P ∪ B); the *quoted number* may
  never mix them, because severity is the tool's proof claim.
- **Quoting P alone while U > 0 is defined as a spec violation** — enforced by
  construction: **no API returns fewer than all four numbers**.
- Most-severe-wins across actions, so a field cannot land in two buckets.
- Spec **v1.0 approved 2026-07-31** and **freezes at first public reference**. After
  that, any change to the formula or the non-claims is a **new major version published
  side by side** — an existing number is never silently redefined.
- Domains held: **aksuindex.com + aksuindex.de**. Landing page in `site/aksuindex/`.
  Say **"regulated"**, not "GDPR": the tool reads whatever `ComplianceGroup` labels the
  org's own admins applied, so CCPA/HIPAA/internal policy use the identical mechanism.
  Calling it a GDPR tool describes a regime-agnostic feature as one customer's use of it.
- **The strategy is NPS-shaped, not FICO-shaped** — corrected by four independent
  launch reviews (`docs/LAUNCH_ROUND5_DECISION_2026-08-04.md`). FICO's formula is a
  trade secret whose adoption was manufactured by a 1995 mortgage mandate; we have an
  open method and no mandating institution. The models that actually fit are NPS (open
  method + **protected mark** + monetised instrument) and MITRE ATT&CK (free framework,
  paid evaluations). The precedent to fear is **Apdex**: open spec, no retained asset,
  publisher captured nothing. So the to-do list is not "protect the formula" but
  **register the mark, publish a recurring reference artifact, sell the instrument** —
  and the trademark filing was missing from the plan entirely until all four reviewers
  named it independently.

---

## 7. Mistakes already paid for — do not repeat

- **A `platform-doc` label is a belief, not a measurement — and one of them was
  false.** PS512/PS506 claimed `stripInaccessible(AccessType.UPDATABLE)` on a read
  path "strips nothing, so the escalation stays proven", and fired **ERROR** on it.
  The runtime oracle refuted it in-org on **both** branches: without object Edit the
  call **throws** (`No access to entity`); with it, the field is **stripped**. It
  generalises — FLS cannot grant Edit without Read, so *unreadable ⊆ un-updatable*,
  and any AccessType strips at least what READABLE would. The wrong AccessType is a
  **reliability bug, not a leak**. Two lessons: **a false positive costs credibility
  exactly like a false clean does**, and *one* measurement is not a rule — probe every
  branch of the axis that could differ before generalising.
- **Don't grade one axis with the other axis's evidence.** `write-v67-plain-is-clean`
  was labelled `experiment:E2`, but E2 only ever **read** (5 rows vs 0). It never
  wrote, so it could not speak for DML's default. Borrowed evidence reads as measured
  and isn't.
- **A measurement without a control can be right for the wrong reason — and E13 was.**
  E13's first version wrapped `insert parent` in `try/catch`, caught a bare
  `Exception`, threw the message away, and concluded from *"something threw and there
  are no child rows"* that a v67 trigger ran in user mode. Two different worlds produce
  that same observation: **(a)** the parent inserted, the trigger ran in user mode, the
  child write was denied, and the throw rolled the parent back; **(b)** the parent
  insert failed on its own and the trigger never ran at all. With no parent count and
  no error message, the test could not tell them apart. The conclusion happened to be
  correct — the 2026-08-04 re-run proved it — but **for three weeks it was believed on
  evidence that did not support it**, and it sat in `CLAUDE.md` and in a draft public
  post as settled fact. The fix is now in the test: count the parent (an after-insert
  trigger that throws rolls it back, so `parents=0` is what "the trigger ran and was
  denied" looks like) and assert the error names **both** the child entity and the
  trigger. **Ask of every green experiment: what else would produce this same
  observation?** The runtime oracle has a negative control for exactly this reason;
  E13 did not, and nobody noticed until an external brief forced a re-read.

- **Reports are written AFTER render.** A render crash leaves a **stale report on
  disk** that looks like a successful run. Always check the console summary line,
  not the file. (This hid two bugs at once: a `KeyError` on a renamed key, and an
  `UnboundLocalError` from re-importing `escalation_gap` inside a function.)
- **Never re-import a module-level name inside a function** — it shadows the global
  for the whole function and explodes on any path that skips the import.
- **Run BOTH demo orgs after every rule change.** Unit tests missed an early
  `return` that made the PS511 block unreachable; the live run caught it instantly.
- **Don't generate benchmark expectations from the law under test** — that's a
  mirror, not an oracle. Labels are hand-written with a `truth` field.
- **`--permission-set` is not a person.** It models a hypothetical user holding
  exactly one set — no profile, no other sets, no group. The report says so.
- **Cross-object fields ARE classified — this note used to say they weren't.** It
  told the next reader to "pick a direct field for PS506 demos", i.e. to avoid a
  feature that works: `classification(fields=...)` resolves a relationship through
  `FieldDefinition.ReferenceTo` and loads the target object's labels (tested in
  `test_authority_analyzer`). On TechnoStore, `BillToContact.Email` comes back
  classified `Confidential` — it just carries no complianceGroup, because the ORG
  never tagged it GDPR. That is the org's data, not a gap.
  **The real trap is the spelling.** `classification` takes fields as `_qualify`
  spells them: a relationship path unqualified (`BillToContact.Email`). Passing
  `Invoice.BillToContact.Email` used to disable relationship resolution silently —
  a false clean caused by nothing but a caller's spelling. `_rel_root` now accepts
  both. **Still genuinely open: POLYMORPHIC lookups** (`referenceTo: [Group, User]`),
  deliberately skipped — we cannot say which object a row points at, so the honest
  answer is to leave it unclassified rather than pick one and be confidently wrong.
- **Relationship fields must not be re-prefixed.** `_qualify()` keeps
  `BillToContact.Email` verbatim and only prefixes direct fields. Getting this wrong
  broke the concentric-circle invariant (`outer == inner + gap`).
- **Never write regex/escapes through a shell heredoc.** It cost five incidents in one
  session: `
` arrives as a real newline, and `` arrives as a real **backspace
  (0x08)**. The last one is the nastiest — `_ARRAY_DECL` silently matched nothing while
  `print(pattern)` rendered it as identical to a working pattern, because a control
  character does not display. Only `repr()` exposed it. **Use the Write/Edit tools for
  anything containing a backslash, and compare patterns with `repr`, never by eye.**
- Windows: console is cp1252 — **use ASCII in CLI output** (`[OK]`, not `✔`).
  PowerShell `$pid` is read-only. Use `sf` CLI, not the MCP tools, for deploys.
- **Run foreign-org scans from THIS DX project dir**, not the other org's folder.
- Agent bundle API names may carry a `_v1` suffix the BotDefinition name lacks
  (e.g. `TechnoStore_Revenue_Assistant_v1`).

---

## 8. Proof surface — what backs the claims

- **224 unit tests** in 12 files.
- **Agent Authority Benchmark v1** (`blast_radius/benchmark/`): **28 hand-labelled
  cases → 28 passed** — 100% precision/recall on this corpus, and **8/8 mutation
  score** (break the analyzer on purpose; the corpus catches it).
  **Re-run before quoting these numbers.** On 2026-07-31 this section still said "23
  cases" while `run.py` reported 28 — a stale number in the one document whose job is
  to stop stale numbers. The counts live in the tool; this file only mirrors them.
- **Runtime oracle** (`benchmark/oracle.py --org <alias>`): **the analyzer predicts,
  the org judges.** It deploys each case with a `runtime` shape as real Apex, runs it
  as the modelled user, and asserts *the analyzer's own prediction* — so a red test
  means the analyzer is wrong, which is the only ground truth not sharing a mind with
  the implementation. It has already caught a real false positive (see §7). Both axes
  are covered: `kind:"read"` measures FLS, `kind:"write"` measures object CRUD as a
  user holding no Create. It also carries a **negative control**: a field the user IS
  entitled to is seeded with a real value, so a passing read cannot be a null that
  would have passed either way — escalation means *the data came back AND the user was
  not entitled*, never one of the two.
  Adding a runtime shape to a `reasoned` case beats adding ten new reasoned cases.
- **Label strength** (the benchmark's real quality metric, printed every run):
  **21 experiment / 3 platform-doc / 4 reasoned**. Honest limits: the mutations are
  the author's, and 4 labels still only prove consistency, not correctness.
- **sfge differential** (`benchmark/sfge_diff.py`, needs no org): Salesforce's own
  Graph Engine vs this tool over the 19 org-adjudicated cases — **7/19 vs 0/19**
  (2/19 on sfge's binary scale). It compares two rules to ours: `ApexFlsViolation`
  ↔ PS502/503/506, `DatabaseOperationsMustUseWithSharing` ↔ PS501. **Both axes now have
  a referee**: `kind:"record"` shapes seed rows owned by the ADMIN on a Private object
  and grant the user FLS, so sharing is the only thing that can hide them. Each case is
  scored on the axis its own shape adjudicates and no other — scoring an unrefereed
  column is how a differential flatters whoever wrote it.
- **Determinism**: proven live — two runs, byte-identical md+html (same sha256).
  The fingerprint binds the **static analysis**, not the live COUNTs — and it binds
  **the tool that produced it**: a sha256 of the rule/extractor source, the parser
  version, what the analysis identity could see, the backend, and each class's own
  apiVersion per action. A verdict is only reproducible against the tool that made it,
  and the report footer now says so rather than leaving it implicit. Meta-tests pin
  every field, and the control was **verified to fail**: drop a field from the payload
  and the test that claims to catch it goes red.
- **Four real orgs**: HospitalOrg (lab + live agent), TechnoStore (**113/113 Apex
  files pre-v67** → the legacy demo), HanseWatt, Urla (no agent).
  **HanseWatt is NOT "an all-v67 org" — that shorthand was wrong and the numbers
  refuted it on 2026-07-31.** Measured: its *agent's actions* are 0/9 pre-v67 (hence
  Index 0), while the *org* is **182/219 pre-v67 (83% legacy)**. This is a far better
  story than the one it replaced, and it is the product's core sales insight: **you do
  not have to modernise the whole org — only the part the agent touches**, which is
  exactly the part nobody currently measures.
- **CI**: `analyze` job (tests + benchmark + mutation) **needs no org and always
  runs**; `live-scan` skips cleanly unless org secrets exist. **`sfge_diff` is
  deliberately NOT in CI** — not for speed (measured: 42s), but because the gate's
  contract is to prove the *analyzer* correct, while the differential proves a
  *comparative claim* that doesn't change per commit; gating it would put a
  third-party Java engine in the critical path and go red when *sfge* changes. It
  exits non-zero only if **this tool** contradicts the org. **Re-run it before
  repeating its numbers** — if sfge fixes its v67 blindness, our headline goes stale
  and nothing else would tell us.

---

## 9. Known gaps — say these out loud

Fixed already: SOSL, dynamic-SOQL PS504, PS509 handler + proof, record-reach
semantics, stripInaccessible, async hand-offs incl. `EventBus.publish`, PSG (E8),
muting (E9), the runtime oracle + its negative control, the systematic sfge
differential, the AST's class-field DML target, the regex subquery false clean, and
the fingerprint binding the analyzer's own source hash + parser version.

**Still open, in rough priority:**
1. **Benchmark v2.** The **runtime oracle is built** (`benchmark/oracle.py`) and
   settles **21 of 28** cases; it has already caught a real false positive (§7), and
   it has a negative control so its greens aren't vacuous. The **systematic sfge
   differential is done** (§6, §8). The **record axis now has a runtime column** too
   (`kind:"record"`), which confirmed the second sfge false positive. What's left: the
   4 `reasoned` labels a shape could still reach.
   **Don't count all 7 shapeless cases as gaps** — the corpus docstring records which
   claims no oracle can ever settle (PS504/PS514 assert what *we* report, not what the
   platform does).
2. **Inter-procedural taint** — **measured, and much narrower than it read.** The
   claim "aliases/helper returns are undetermined" was already false: aliases,
   ternaries, string concat and helper hops all trace. What was actually blind, found
   by labelling every give-up and RANKING them over real agent actions:
   - **`for (X x : [SELECT ...])`** — Apex's most idiomatic query, and the single
     biggest cause (**71 of 198** verdicts). **Fixed**: the loop variable is the
     record variable.
   - **`new X(Field__c = rec.Y)`** — the named argument parses *identically* to a
     reassignment, so the trace gave up. **Fixed**, with field-level tracking: only
     the field that received the value counts, or we would report `returned` naming a
     sink the value never reaches (a fabricated proof — worse than the unknown it
     replaces).
   **Result on real agent actions: undetermined 66% → 44%, returned 14% → 34%.**
   Still open, in rank order: `whole-record → unmodelled callee` (15), `NO output-type
   class` (18 — an invocable returning `List<String>` has no `@InvocableVariable`
   wrapper to trace into), `whole-record reassigned` (11).
3. **Async reach** — mostly followed now; what remains is narrower than it looks.
   Queueable/Batch/`@future` reach already merges via the one-level class-ref follow
   (`new SecretJob()` matches `_CLASS_REF`) — measured, not assumed. `EventBus.publish`
   is modelled as a DML verb, so the event enters the reach and PS503/PS509 apply to it
   for free. **Still unfollowed: Flow, process, and off-platform subscribers**, plus the
   scheduled/callout kinds. PS514 states precisely which of these is the open edge —
   don't let it drift back to a blanket "not analysed".
4. **Entry-point matrix** — partly closed by **E10**, and the remaining cell may not
   be reachable at all. E10 measured what E2 asserted without a control: three pre-v67
   invocables differing only in the declaration, same caller, same user, same
   admin-owned rows → `without sharing`=5, **no declaration=0**, `with sharing`=0. So
   a declaration-less class inherits its caller and enforces sharing.
   **The cells are not equally relevant.** An agent invokes an `@InvocableMethod`, so
   LWC/REST/anonymous never touch an agent's blast radius. The one that does — an
   invocable with **no calling Apex class** — can't be measured without invoking the
   agent (Flex Credits, the thing this tool exists to avoid) or authenticating as the
   fixture user; a Flow proxy would measure Flow→invocable and drag in the Flow's own
   `runInMode`, answering a question nobody asked. Until then `enforces_sharing=None`
   for a declaration-less pre-v67 class is **the right answer**, not a placeholder.
5. **Backend confidence — CLOSED.** Both halves are done and measured, so this is
   here as a record, not a task. *Severity:* the premise ("regex findings should carry
   lower severity") was **refuted** by a differential over 104 real classes — neither
   backend dominates, every contradiction it found was a bug in one of them, and all
   are fixed (identical ops 62→82/104; OVERCLAIM, MISSED, NOISE all **0**). *Fingerprint:*
   it now seals the **tool**, not just the inputs — `analyzer` (a sha256 of the rule and
   extractor source), `parser`, `coverage` (what the analysis identity could see), the
   `backend`, and each analysed class's own `apiVersion` **per action**.
   **`schema_version` was deliberately NOT added**, though a task spec asked for it: the
   rule schema *is* `authority_analyzer.py`, which the analyzer digest already hashes,
   so a separate constant would be redundant **and hand-maintained** — someone changes a
   rule, forgets to bump it, and the constant lies. That is the exact failure the digest
   exists to prevent; adding it would trade a mechanism that cannot be forgotten for one
   that can. Same reason `analyzer` is a hash rather than a `__version__` string.
   **What actually remains** is not a TODO: regex has **no scope** and cannot get one
   without a parse tree — that is *why* AST is the default and what the report's backend
   note discloses. Residual disagreement is **DEGRADED 22/104**: regex honestly says
   `None` where AST resolves.
6. **Formula/roll-up field inputs — E12 is BLOCKED, and say so.** An external review
   raised it and it is real *and concrete*: **11 of Invoice's 93 fields are formulas,
   and the flagship demo action reads one** (`TotalAmountWithTax`). PS516 now reports
   it as an unresolved reach — a statement about OUR resolution, which is true whatever
   the platform does. **What is NOT known:** whether a formula actually carries a
   field's value past the running user's FLS. The fixture that would settle it
   (`IBAN_Echo__c`, a Text formula echoing `Customer_IBAN__c`) **could not be
   deployed**: `sf project deploy start` reports *Succeeded, 4 components, 0 errors*
   and the field never appears — not via the data API, not via Tooling. Unresolved.
   **Do not upgrade PS516 to a leak claim until that is measured** — believing a
   well-established platform behaviour is exactly how the `stripInaccessible` false
   positive happened, and that one was "well-established" too.
7. **Polymorphic classification** — a lookup with more than one `referenceTo` target
   is skipped, so its fields stay unclassified. Deliberate and honest (we cannot know
   which object a given row points at), but it IS a coverage hole: a GDPR field behind
   a polymorphic lookup is invisible to PS506. Single-target relationships **are**
   resolved (§7).
8. **Restriction/scoping rules — and the direction matters.** They REDUCE what the
   user sees, so not modelling them makes the tool think the user is MORE privileged
   than they are → **the escalation gap is a LOWER bound, not an upper one**. An
   external reviewer caught the docs classifying this as a *conservative* limitation;
   it is the opposite — optimistic. Muting is no longer in this bucket (E9 measured
   the aggregate applies it).
9. **No suppression / baseline.** There is no way to silence a reviewed PS501 or
   PS507. A CI gate nobody can silence gets switched off — a real product risk, raised
   by an external review and not yet addressed. If it is built, the honest shape is
   sfge's: an inline directive **with a reason**, and unreasoned suppressions listed in
   the report.
10. Managed-package internals, Knowledge/Data Cloud retrieval — opaque today.

---

## 10. Conventions

- Python 3.12, stdlib only. Node is optional (AST backend degrades to regex).
- Run tests: `python -m unittest discover -s blast_radius -p "test_*.py"`
- Run benchmark: `python blast_radius/benchmark/run.py` and `mutate.py`
- Comments explain **why / the constraint**, never what the next line does.
- Decision records live in `docs/adr/` (12 ADRs, incl. the deliberate
  rejections). A change that alters what a finding may claim, rejects an
  alternative, or sets a boundary gets an ADR; an incident-level lesson goes
  into §7 here instead.
- The brief `PROJECT_STATE_AND_REVIEW_BRIEF.md` (~2100 lines) is the exhaustive
  reference; `REVIEW_REQUEST_PROMPT.md` is the paste-ready external-review prompt.
- Commit messages: what changed **and what it proves/why it was wrong before**.
