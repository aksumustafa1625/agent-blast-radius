# Errata — the three times I was wrong

A tool that argues for honest measurement has to be honest about its own. These are the
three occasions where this analyzer was wrong, what it claimed, what corrected it, and
what changed as a result.

None of them were found by reading documentation. All three were settled by running code
against a live Salesforce org and reading what the org actually did. That is the whole
method: **the analyzer proposes, the org decides.**

---

## 1 · I treated one boundary as two, and the org showed me it was two

**What I believed.** That "the code runs bounded by the running user" was a single yes-or-no
question. If a class declared `with sharing`, I read that as bounded.

**Why it is wrong.** Salesforce enforces access on **two independent axes**:

| axis | what it controls | what sets it |
|---|---|---|
| record | which rows you can see | the `sharing` keyword, under system mode |
| object + field | whether you may read the object and the field at all | the class's apiVersion, or an explicit mode clause |

So `with sharing` on an API v58 class resolves to **`(sharing enforced, FLS bypassed)`**. It
obeys sharing rules and **skips CRUD and field-level security entirely** — meaning it can
read an object the running user has no permission on whatsoever. "Bounded by the running
user" requires **both** axes to be true, and I had been checking one.

**What corrected me.** A live run against a real org. The report was wrong on screen, on
data I could go and check by hand, and the discrepancy was not subtle once the two axes were
separated.

**What changed.** The two axes are now tracked separately end to end, each with three
possible values — `True`, `False`, and `None` for *undetermined*. A class with no sharing
declaration inherits its caller's context, which is not knowable from that class alone, so
the honest answer is `None`. An unknown is never rounded to safe.

---

## 2 · I fired an ERROR on a finding that was not real

**What the tool claimed.** That calling `Security.stripInaccessible(AccessType.UPDATABLE, ...)`
on a **read** path strips nothing — you asked about update permissions, so the read escapes
unfiltered — and that the escalation therefore stands **proven**. It reported this at
`ERROR`, the severity this tool reserves for things it has proved.

**Why I believed it.** It is a reasonable reading of the API, and it is what the
documentation supports. I labelled the case `platform-doc`: documented semantics, not
measured here.

**What corrected me.** The runtime oracle — a harness that deploys each benchmark case as
real Apex, runs it as the modelled user, and asserts *the analyzer's own prediction*, so a
red test means the analyzer is wrong. It refuted the claim on **both** branches of the
behaviour:

- without object Edit permission, the call **throws** — `No access to entity`
- with it, the field **is stripped**

Neither branch leaves the data exposed. And it generalises: field-level security cannot
grant Edit without Read, so *unreadable ⊆ un-updatable*, and any `AccessType` strips at
least what `READABLE` would have.

**What changed.** The rule was rewritten. The wrong `AccessType` is now reported as a
**reliability bug, not a leak** — it still deserves fixing, but it is not an escalation.

**The lesson that outlived the bug.** A false positive costs credibility in exactly the same
currency a false clean does. If the tool cries wolf once, nothing it says afterwards is
worth much. And *one* measurement is not a rule — probe every branch that could differ
before generalising from it.

---

## 3 · I believed a correct conclusion for three weeks on evidence that did not support it

This is the one worth reading, because the conclusion never changed. Only the evidence did.

**What I claimed.** That an Apex trigger's own DML runs in the mode of the trigger's own
apiVersion — so a v67 trigger is bounded by the running user, and a v58 one is not. This
matters: if it were false, a whole rule would be a false negative in the middle of the
thesis.

**How I "proved" it.** The first version of the experiment wrapped `insert parent` in a
`try/catch`, caught a bare `Exception`, **threw the message away**, and concluded from
*"something threw, and there are no child rows"* that the v67 trigger had run in user mode
and been denied.

**Why that proves nothing.** Two entirely different worlds produce that same observation:

- **(a)** the parent inserted, the trigger ran, the child write was denied, and the throw
  rolled the parent back — what I claimed
- **(b)** the parent insert failed on its own and **the trigger never ran at all**

With no parent count and no error text, the test could not tell them apart. It sat in the
project's working notes, and in a draft of a public post, as settled fact for three weeks.

**What corrected me.** An external reviewer re-asserted the opposite claim, citing the
Summer '26 release notes, and marked it *confirmed against primary sources*. Re-running the
experiment to answer them is what exposed the hole in my own version of it. The re-run added
the controls the first one lacked, and the org answered in full:

```
DmlException: CANNOT_INSERT_UPDATE_ACTIVATE_ENTITY, BlastTestV67Trigger:
execution of AfterInsert caused by:
System.SecurityException: Access to entity 'Casc_Child__c' denied
```

The error names the **child entity** and the **trigger's own line** — so the parent did
reach the trigger, and the trigger's DML is what was denied. World (a), not (b). And the
v58 control ran in the same execution, same child object, same zero-permission user, and
**wrote successfully** — which kills the remaining alternative explanation, that the denial
was about the user rather than the mode.

**What changed.** The test now counts the parent rows and asserts that the error names both
the child entity and the trigger. The claim is also scoped more tightly than before: this
measures the **CRUD axis** of DML the trigger's own body performs. Whether a v67 trigger
enforces sharing or FLS was a separate question, measured separately later.

**The lesson.** Ask of every green experiment: *what else would produce this same
observation?* A test with no control can be right by accident, and an accident is not
evidence. It also means something less comfortable — the reviewer who was wrong about the
platform was right about my method, and I would not have found it without them.

---

## Why this page exists

Publishing the corrections is not modesty. It is the same argument the tool makes about
unknowns: **a silent wrong answer is worse than a stated one.** A report that quietly
overstates costs a reader exactly what a report that quietly understates costs them — their
ability to act on it.

If you think a verdict this tool produces is wrong, [open an issue](https://github.com/aksumustafa1625/agent-blast-radius/issues).
The template asks what your org did, not what a document says — because that is the only
kind of evidence that has ever changed my mind.

---

*Deeper material: the incident-level notes live in [`CLAUDE.md`](../CLAUDE.md) §7, the
decisions they produced are in [`docs/adr/`](adr/), and the corpus that guards against
their recurrence is in [`public-benchmark/`](../public-benchmark/).*
