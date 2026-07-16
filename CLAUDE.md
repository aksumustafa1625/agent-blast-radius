# CLAUDE.md — working context for Agent Blast Radius

This file is for whoever (or whatever) picks this repo up next. It is not marketing;
it is the map, the semantics you must not get wrong, the discipline that makes the
tool worth anything, and the mistakes already paid for. Read the discipline section
before changing a rule.

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
| **E13** | **A v67 trigger IS bounded by the running user — the most dangerous review claim, refuted in-org.** A reviewer cited Summer '26 (*"Apex Triggers ... will now always run in system mode across all API versions"*); if true, PS509 fires only below v67 and would be a **false negative in the middle of the thesis**. Measured today, on Summer '26: a **v67** trigger writing `Casc_Child__c` for a user with no Create → **BLOCKED, 0 rows written** (`BlastRadius_E13_TriggerMode.cls`). E6 stands. It was worth doing because E6's v67 half was only *"verified separately in Milestone 0"* — a docstring assertion with no test to catch a platform change. Now there is one. |
| **E11** | **The publish premise, measured** — it was `platform-doc` while a LIVE TechnoStore ERROR already rested on it. A user with **no ObjectPermissions row at all** on `Blast_Event__e`: **v58 publish LANDS** (`WROTE=ok` — the Create bypass is real, so modelling publish as a write and applying PS503 is right), **v67 publish BLOCKED**. The `SaveResult` is read rather than trusting a throw — whether user mode throws or returns a failure was exactly the thing not to assume. Writing the case found a hole in the feature: `EventBus.publish(new X__e(...))` resolved to None, so PS503 never fired on an inline-constructed event. |
| **E10** | **"No declaration" enforces sharing — now with controls.** Three pre-v67 invocables differing only in the declaration, same caller, same user, same admin-owned rows on a Private object: `without sharing` → **5**, no declaration → **0**, `with sharing` → **0**. Confirms E2's round 1, which had **no control** (0 alone could have meant the user had nothing to see). **Only one cell of the matrix**: the caller here is Apex. The agent's own entry point (an invocable with *no* calling Apex class) stays unmeasured — so `enforces_sharing=None` for a declaration-less pre-v67 class is still the honest answer. |

**Do not "fix" the precedence law from documentation.** This has now happened
**twice**, from two different reviews, both citing real Salesforce docs:
- v67 `without sharing` "must be record-bypassing" → **E2b** disproved it in-org.
- v67 triggers "always run in system mode" (Summer '26 release notes) → **E13**
  disproved it in-org, on Summer '26.
Both would have broken correct code. Documentation describes intent; the org
describes behaviour, and only one of them is what your customer runs. **Answer a
doc-based claim with an experiment, never with an edit** — and note that both
reviewers were doing exactly the right thing by raising them.

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
  report.py / report_html.py  deterministic md + themed html
  verify_deterministic.py   runs the CLI twice, sha256-diffs both outputs
  benchmark/                corpus.py + run.py + mutate.py + oracle.py (runtime
                            oracle: deploys each case, the ORG judges) + README.md
  fixtures/                 permission snapshots + apex/prompt fixtures
  test_*.py                 162 tests
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
- Windows: console is cp1252 — **use ASCII in CLI output** (`[OK]`, not `✔`).
  PowerShell `$pid` is read-only. Use `sf` CLI, not the MCP tools, for deploys.
- **Run foreign-org scans from THIS DX project dir**, not the other org's folder.
- Agent bundle API names may carry a `_v1` suffix the BotDefinition name lacks
  (e.g. `TechnoStore_Revenue_Assistant_v1`).

---

## 8. Proof surface — what backs the claims

- **162 unit tests.**
- **Agent Authority Benchmark v1** (`blast_radius/benchmark/`): 23 hand-labelled
  cases → **100% precision/recall on this corpus**, and **8/8 mutation score**
  (break the analyzer on purpose; the corpus catches it).
- **Runtime oracle** (`benchmark/oracle.py --org <alias>`): **the analyzer predicts,
  the org judges.** It deploys each case with a `runtime` shape as real Apex, runs it
  as the modelled user, and asserts *the analyzer's own prediction* — so a red test
  means the analyzer is wrong, which is the only ground truth not sharing a mind with
  the implementation. **15 of 23 cases have a shape; all 15 agree.** It has already
  caught a real false positive (see §7). Both axes are covered: `kind:"read"` measures
  FLS, `kind:"write"` measures object CRUD as a user holding no Create.
  Adding a runtime shape to a `reasoned` case beats adding ten new reasoned cases.
- **Label strength** (the benchmark's real quality metric, printed every run):
  **21 experiment / 3 platform-doc / 4 reasoned** (was 11/6/6). Honest limits: the mutations are
  the author's, and 5 labels still only prove consistency, not correctness.
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
  the analyzer itself: a sha256 of the rule/extractor source plus the parser version,
  so a rule change cannot silently reuse an old fingerprint.
- **Four real orgs**: HospitalOrg (lab + live agent), HanseWatt (all v67 → clean),
  TechnoStore (106 classes + 7 triggers, **100% pre-v67** → the legacy demo),
  Urla (no agent).
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
5. **Backend confidence** — **the premise was wrong, and reading the disagreements
   closed them.** This used to read "regex findings should carry lower severity than
   AST ones". A differential over 104 real classes refuted it (neither backend
   dominates), and then every contradiction it found turned out to be a bug in one
   backend or the other. All fixed. **Identical ops 62 → 82 of 104; OVERCLAIM,
   MISSED and NOISE all 0.**
   **What remains is only DEGRADED (22 of 104): regex says `None` where AST resolves**
   — an honest PS504 instead of a PS503. That is not a TODO, it is the shape of the
   fallback: regex has **no scope** and cannot get one without a parse tree, which is
   *why* AST is the default and what the report's backend note discloses.</p>
   The bugs it found are worth remembering, all measured on live code (§7):
   the AST's missing `FieldDeclarationContext`; the regex's subquery `FROM`; DML
   straight on a query (`delete [SELECT ...]` — **both** backends); a name declared
   with two types resolving to the wrong object; and comments-before-strings
   corrupting a URL and erasing a real `update`.
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
- The brief `PROJECT_STATE_AND_REVIEW_BRIEF.md` (~2100 lines) is the exhaustive
  reference; `REVIEW_REQUEST_PROMPT.md` is the paste-ready external-review prompt.
- Commit messages: what changed **and what it proves/why it was wrong before**.
