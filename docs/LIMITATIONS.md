# Limitations

Two sections, and the order is deliberate.

An **undetected escalation path** is a route by which a real agent exceeds its running user
and this tool says nothing. A **known limit** is a boundary the tool declares and refuses to
claim past. Filing the first under the second would put "a real leak we cannot see" beside
"we do not parse managed packages", and those are different statements about a security
tool.

Every entry carries the same four fields, so a reader can tell a plan from an apology:

| field | what it answers |
|---|---|
| **Status** | open · fixed *(date)* · measured *(experiment)* |
| **Found by** | me · an external audit · the runtime oracle · a reviewer |
| **Next measurement** | the experiment that closes it — or *"none, deliberately out of scope"* |
| **Covered by** | the test or rule that keeps it honest today |

The maintained working list is [`CLAUDE.md` §9](../CLAUDE.md). This file is the reader's
version of it.

---

## Undetected escalation paths

### A v67 trigger with an explicit `WITH SYSTEM_MODE` in its body

- **Status:** open
- **Found by:** the E15 measurement, by accident, while measuring something else
- **Next measurement:** none needed — E15 already measured it (`SYS=5`). This is a rule gap,
  not a knowledge gap.
- **Covered by:** nothing. PS509 fires only when `apiVersion < 67` **and** the trigger
  carries no mode clause, so this trigger is invisible to it.

E15 showed that `WITH SYSTEM_MODE` inside a v67 trigger body returns all rows — the ambient
context is still `without sharing`, and the explicit clause re-opens it. That is a real
escalation the report does not mention. It is listed first because it is the only item in
this document where the tool is silent about something it has already been shown.

### A trigger's own SOQL reads never enter the reach

- **Status:** open
- **Found by:** me, while writing up E15
- **Next measurement:** [`docs/E19_PROTOCOL.md`](E19_PROTOCOL.md) — trigger-body FLS
- **Covered by:** nothing today

This one **understates** rather than overstates, which is the safer direction — but it stops
being safe if E19 returns "value": a v67 trigger that reads a regulated field the user
cannot see would then be a silent false clean. Until E19 runs, trigger-body SOQL should
enter the reach with `enforces_fls = None` and a PS504 owned by the analyzer, rather than be
left out.

### Cross-version inheritance contamination

- **Status:** open, and **probably unmodelled** rather than merely unmeasured
- **Found by:** a documentation review, 2026-08-04
- **Next measurement:** deploy a pre-v67 class with a v67+ ancestor and read as a restricted
  user
- **Covered by:** nothing

The v67 Apex Developer Guide states that a class in an inheritance chain runs `with sharing`
if *any* class in that chain is saved at v67 or later. **That is not expressible in a
per-class apiVersion lookup**, which is exactly what `_resolve()` does. Interim position:
where an inheritance chain is detected, emit PS504 with `unresolved_kind = analyzer` and the
cause *"inheritance chain not resolved"*, so the gap becomes a counted U rather than a
silent assumption.

### Flow run context, resolved from documentation rather than measurement

- **Status:** fixed in code 2026-08-19, provenance `platform-doc` — **still unmeasured in-org**
- **Found by:** an external mechanism audit, 2026-08-10. Not by me.
- **Next measurement:** deploy a record-triggered flow with no `runInMode` tag that reads a
  field the running user lacks FLS on, fire it as that user, and see whether the field comes
  back
- **Covered by:** 13 tests in `test_flow_introspect.py`; a tag-less autolaunched flow
  resolves to `None` on both axes and fires PS504, so it is never reported clean

`flow_introspect.py` captured the flow's process type and used it in no verdict path — a
record-triggered flow with no tag resolved to *user mode with sharing enforced*, which is
the silent false clean the honesty discipline exists to prevent. The resolution order now
follows Salesforce's own flowtest engine: type first, then the tag. **"Fixed" is not
"measured", and this entry stays here until it is.**

---

## Known limits

### It counts fields, not records

- **Status:** by design (ADR-008, ADR-013)
- **Next measurement:** none — deliberately out of scope
- **Covered by:** the report labels every record number an upper bound and prints `n/a` where
  visibility is sharing-dependent

Predicates and `LIMIT` are not resolved, so a record count is *"could reach up to N"*, never
*"reaches N"*.

### The field gap is a lower bound

- **Status:** open
- **Found by:** an external reviewer, who caught the docs calling this *conservative*
- **Next measurement:** model restriction and scoping rules
- **Covered by:** stated on the landing page and in every report

Restriction and scoping rules **reduce** what a user can see and are not modelled, so the
tool may believe a user is more privileged than they are. The direction matters: this makes
the gap a **lower** bound, not an upper one. It is optimistic, not conservative.

### Formula and roll-up field inputs

- **Status:** open — **E12 is blocked**, not merely unrun
- **Found by:** an external review
- **Next measurement:** E12, once the fixture can be deployed
- **Covered by:** PS516, worded as a statement about *our* resolution rather than a leak
  claim (ADR-011)

11 of Invoice's 93 fields are formulas and the flagship demo action reads one. Whether a
formula carries a value past the running user's FLS is **not known** — the fixture that
would settle it reports *"Succeeded, 4 components, 0 errors"* and the field never appears,
via neither the data API nor Tooling. PS516 is not upgraded to a leak claim until it is
measured; believing a well-established platform behaviour is exactly how the
`stripInaccessible` false positive happened.

### An `AgentforceOrchestrator` agent has never been measured

`BotDefinition.Type` has four values. Three are handled and measured:
`ExternalCopilot` (a service agent, which has its own running user in `BotUserId`),
`InternalCopilot` (an employee agent, which runs as whoever is logged in — so the
tool refuses to invent a single running user and asks for one), and `Bot` (a
classic Einstein Bot, which has no planner bundle and is skipped rather than
measured).

The fourth, `AgentforceOrchestrator`, is **not measured**. None of the six orgs
available to this project has one, so nothing here can say whether an orchestrator
carries a `BotUserId`, whether it has a planner bundle of its own, or what its
actions look like. `measure.py` will treat one as a service agent, and the outcome
is one of three, all of them honest: it resolves and produces a report about the
orchestrator's own actions; or the planner bundle does not resolve and the tool
lists what the org actually has; or there is no `BotUserId` and it falls back to a
permission set while saying, at the point of the claim, that the identity was
chosen arbitrarily and is not the agent's.

**What IS handled is the thing orchestration is for.** An agent invoking another
agent (`agentforce://X`) is walked as a graph: every reachable agent's actions are
spliced into one action list before any reach or permission work happens, so the
report covers the aggregate blast radius rather than reporting the sub-agent as one
opaque action. A delegation that cannot be resolved stays a `PS515` **WARN**, never
silently dropped and never read as clean; a cycle stops at the repeat and is
reported; and the walk is depth-bounded, with the bound itself reported rather than
pretending the reach ends there.

So the gap is narrow and specific: the *type* is unmeasured, the *pattern* is
covered. If you have an org with an orchestrator, that is the measurement this
project would most like to be sent.

### Polymorphic lookups stay unclassified

- **Status:** by design (ADR-012)
- **Next measurement:** none — we cannot know which object a given row points at
- **Covered by:** single-target relationships **are** resolved and tested

It is still a coverage hole: a regulated field behind a polymorphic lookup is invisible to
PS506. Deliberate and honest beats confidently wrong.

### Inter-procedural taint

- **Status:** open, and much narrower than it used to read
- **Found by:** me, by labelling every give-up and ranking them over real agent actions
- **Next measurement:** model the remaining three shapes
- **Covered by:** `undetermined` verdicts, which never read as clean

Aliases, ternaries, string concatenation and helper hops all trace. What remains: a whole
record handed to an unmodelled callee (15), an invocable returning `List<String>` with no
`@InvocableVariable` wrapper to trace into (18), and a whole record reassigned (11).
Measured on real agent actions: undetermined **66% → 44%**, returned **14% → 34%**.

### Async reach

- **Status:** partly open
- **Next measurement:** follow Flow, process and off-platform subscribers
- **Covered by:** PS514, which names exactly which edge is unfollowed

Queueable, Batch and `@future` merge via the one-level class-ref follow — measured, not
assumed. `EventBus.publish` is modelled as a DML verb, so the event enters the reach.

### Suppression is half built

- **Status:** the ratchet exists; per-finding silencing does not
- **Covered by:** 16 tests in `test_baseline.py`

`--baseline` asks *"is it worse than last time"* rather than *"is it zero"*, and every bucket
ratchets — so moving a finding from proven into unresolved by making a query dynamic breaks
the gate too. There is no way to silence one reviewed PS501. If it is built, the honest shape
is sfge's: an inline directive **with a reason**, and unreasoned suppressions listed in the
report.

### Opaque today

- **Status:** open
- **Next measurement:** none scheduled

Managed-package internals · Knowledge and Data Cloud retrieval.

---

## Four v67 documentation claims, unmeasured

Listed as **experiments to run, never as edits to make**. Documentation has lost to the org
four times in this project; the response to a doc-based claim is a measurement.

| claim | status |
|---|---|
| v67 + no sharing declaration → `with sharing` | unmeasured for v67 (E10 measured pre-v67). `_resolve()` already sets both axes True at v67, so no practical difference is expected — but expectation is not measurement. |
| cross-version inheritance contamination | see above — unmeasured **and** unmodelled |
| the record axis inside a v67 trigger body | **measured — E15, closed cleanly** |
| FLS inside a v67 trigger | unmeasured here. A Stack Exchange commenter reports measuring it; that is their org, not this one. [`E19_PROTOCOL.md`](E19_PROTOCOL.md) |

**Experiment queue:** E15b → v67 no-declaration → E19 (trigger FLS) → E17 (encrypted fields)
→ E18 (system-mode callouts) → the Flow measurement.
