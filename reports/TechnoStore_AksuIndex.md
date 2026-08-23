```
==============================================================================
  AKSU INDEX  -  TechnoStore Revenue Assistant
==============================================================================

      6  PROVEN
         fields the agent's code can reach beyond this running user.
         1 of them carries the org's own compliance labels (GDPR/PII).

      0  unproven boundaries      real boundaries we could not prove crossed
      1  unresolved               reach we could not determine at all

  Aksu Index: 6 proven (1 GDPR) · 0 unproven boundaries · 1 unresolved
  (all four numbers ARE the metric - none of them may be quoted alone)

------------------------------------------------------------------------------
  WHAT THE AGENT'S CODE REACHES  vs  WHAT THIS RUNNING USER MAY SEE

      Objects reached by the agent ............. 2
      Fields reached by the agent .............. 8
        of those, readable by this user ........ 2
        beyond this user - the gap ............. 6
           that gap = 6 proven + 0 unproven, the two numbers above

  The Index counts fields, never records. This run does not measure how
  many objects the running user can see, so no user-side object count is
  claimed here.
==============================================================================
```

```
AGENT BLAST RADIUS REPORT - TechnoStore Revenue Assistant
Running user: (hypothetical grant model - permission set: TechnoStore_Revenue_Assistant2098228049_Permissions)   (channel: agent)
Config fingerprint: 9d3ba9d2e6c4      Generated: deterministic
Aksu Index spec v1.0: aksuindex.com
================================================================

ESCALATION GAP ......... 6 fields  /  1 GDPR-labelled   <==

REACH SUMMARY
  Actions analysed ....... 2
  Objects reachable ...... 2
  Fields reachable ....... 8
  System-mode actions .... 2 / 2
  Legacy API (< v67) ..... 2 / 2

CLASSIFICATION COVERAGE
  Reachable fields ....... 6
  Classified (GDPR/PII) .. 2
  Visible, unclassified .. 4
  Not visible to analyzer  0
  Coverage ............... 100%
```

### Record reach (live COUNT — upper bound)

> **The agent's system-mode reads could reach up to 4 records where the running user sees 0 — an upper-bound record gap of 4.** _(measured system-mode objects only)_ The whole measured gap is a CRUD escalation — the running user has no object permission at all, so this is deterministic, not sharing-dependent.

| Object | Read mode | Records in org | User sees | Gap (upper bound) | Cause |
| --- | --- | ---: | ---: | ---: | --- |
| `Invoice` | system | 4 | 0 | ≤ 4 | no object permission (CRUD) |

> _`Records in org` is a live `COUNT()` of the whole object run as the analysis identity. **It is an upper bound, not the agent's result**: query predicates and `LIMIT` are not resolved statically. It is an escalation ceiling only for **system-mode** reads — a **user-mode** read enforces sharing, so the agent is bounded by the running user and the gap is 0 by construction. **CRUD** = the user has no object permission at all (deterministic); **sharing** = the user can read the object but record-level sharing may hide rows, which is data-dependent and shown as `n/a` — never estimated._

> **6 fields can be reached beyond the running user - 1 of them GDPR-labelled.**

## ERROR - 8 finding(s)

- **[PS506] SendPaymentRemindersAction -> Invoice.Stripe_Payment_Status__c**
  - GDPR/PII field Invoice.Stripe_Payment_Status__c is read in system mode and reaches the model, but the running user has no FLS on it.
  - _Why:_ ComplianceGroup GDPR. A field the running user cannot see can reach the LLM and the end user's screen. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Remove the field from the query/output, or enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS502] SendPaymentRemindersAction -> BillToContact.Email**
  - Field BillToContact.Email is read in system mode; the running user has no FLS on it.
  - _Why:_ In system mode Apex ignores FLS, so the field's data can reach the agent. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS502] SendPaymentRemindersAction -> Invoice.BillToContactId**
  - Field Invoice.BillToContactId is read in system mode; the running user has no FLS on it.
  - _Why:_ In system mode Apex ignores FLS, so the field's data can reach the agent. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS502] SendPaymentRemindersAction -> Invoice.BillingAccountId**
  - Field Invoice.BillingAccountId is read in system mode; the running user has no FLS on it.
  - _Why:_ In system mode Apex ignores FLS, so the field's data can reach the agent. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS502] SendPaymentRemindersAction -> Invoice.DocumentNumber**
  - Field Invoice.DocumentNumber is read in system mode; the running user has no FLS on it.
  - _Why:_ In system mode Apex ignores FLS, so the field's data can reach the agent. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS502] SendPaymentRemindersAction -> Invoice.TotalAmountWithTax**
  - Field Invoice.TotalAmountWithTax is read in system mode; the running user has no FLS on it.
  - _Why:_ In system mode Apex ignores FLS, so the field's data can reach the agent. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS503] SendPaymentRemindersAction -> Invoice**
  - update on Invoice in system mode; the running user has no edit permission on this object (dml API v<=66 default).
  - _Why:_ In system mode Apex ignores CRUD, so the action writes an object the running user cannot - a write escalation.
  - _Fix:_ Enforce user mode (`update as user` / AccessLevel.USER_MODE) or grant the permission intentionally and document it.
- **[PS503] SendPaymentRemindersAction -> Invoice_Payment_Requested__e**
  - publish on Invoice_Payment_Requested__e in system mode; the running user has no create permission on this object (EventBus.publish API v<=66 default).
  - _Why:_ In system mode Apex ignores CRUD, so the action writes an object the running user cannot - a write escalation.
  - _Fix:_ Enforce user mode (`publish as user` / AccessLevel.USER_MODE) or grant the permission intentionally and document it.

## WARN - 4 finding(s)

- **[PS504] GetRevenueSummaryAction -> Invoice**
  - Reach for this operation could not be fully determined - this analyzer does not model the shape (aggregate/function select - fields not enumerated).
  - _Why:_ A silent false-clean is worse than an honest unknown, so this is counted as unresolved rather than passed. This one is OUR limit, not a property of your code: the reach is written out in the source and analyzer build 65e31fb90c7c does not model this shape. Stated as of that build - a later one may resolve it, and this report is not falsified when it does.
  - _Fix:_ Ours to close - there is nothing to change in your code. Review this operation by hand, or re-run on an analyzer build that models the shape.
- **[PS509] SendPaymentRemindersAction -> Invoice**
  - DML (update) on Invoice fires trigger 'InvoiceTrigger' at API v60 (< v67) — a legacy cascade boundary, but no escalating write was proven.
  - _Why:_ A pre-v67 trigger runs its DML in system mode, so this is a real boundary to review; however no DML was observed in its own body (it may delegate to a handler, or perform none), so this is flagged as a boundary rather than a proven escalation.
  - _Fix:_ Review what 'InvoiceTrigger' writes downstream; upgrade it to API v67+ to remove the legacy default entirely.
- **[PS514] SendPaymentRemindersAction (platform event: Invoice_Payment_Requested__e)**
  - This action publishes Invoice_Payment_Requested__e. The publish is analysed as a write; any Flow, process, or external subscriber is NOT.
  - _Why:_ No Apex subscriber trigger exists on it, but a platform event can also be consumed by a Flow, a process, or an off-platform subscriber, each running in its own transaction as a different user. Publishing is how an agent starts work it could not do inline, so the true blast radius can be larger than this report. An honest unknown edge, not a proven leak.
  - _Fix:_ List the subscribers of Invoice_Payment_Requested__e (Flow, process, and external) and review each as its own entry point.
- **[PS516] SendPaymentRemindersAction -> Invoice.TotalAmountWithTax**
  - This field is a FORMULA; the fields it reads are not resolved here.
  - _Why:_ A formula's value is computed from other fields, so the running user's FLS on THIS field does not bound what its value carries - a formula they are allowed can echo one they are not. Unlike every other reach, this is not settled by user mode: a v67 read enforces FLS on the formula, not on its inputs. Reported as an unresolved reach, not as a proven leak - what the platform does here is not measured.
  - _Fix:_ Open Invoice.TotalAmountWithTax's formula and check whether any field it references is invisible to this user or carries a compliance label.

## INFO - 2 finding(s)

- **[PS511] GetRevenueSummaryAction (API v63.0)**
  - Custom action class predates API v67 (secure-by-default).
  - _Why:_ Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.
  - _Fix:_ Plan a migration to API v67 and re-review.
- **[PS511] SendPaymentRemindersAction (API v63.0)**
  - Custom action class predates API v67 (secure-by-default).
  - _Why:_ Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.
  - _Fix:_ Plan a migration to API v67 and re-review.

## Org health — beyond this agent

_Whole-org signals that don't concern TechnoStore Revenue Assistant directly, but anyone securing this org should know. Static Tooling-API reads — zero credits._

> **Why this matters for TechnoStore Revenue Assistant:** an agent reaches only what its code reaches, and that boundary is the Apex **API version**. v67+ defaults to the running user's mode (reaches nothing the user can't); pre-v67 defaults to system mode (reaches *past* the user). That is exactly the **6-field escalation** above — TechnoStore Revenue Assistant's pre-v67 code reads fields its user can't. At v67 that gap would be **0**.
>
> This agent's own action code: **2** of 2 class(es) are pre-v67.

- **113/113 of your own Apex files are pre-v67** (100% system-mode by default) — the same latent escalation this report proves for the agent's classes sits in every other legacy file.
- **2 permission set(s) grant *Modify All Data*** — overrides all sharing and FLS for whoever holds them.
- 1 permission set(s) grant *View All Data* only.
- Every custom object defaults to **Private** sharing — a healthy baseline.

---
Produced by static analysis. No agent was invoked. 0 Flex Credits.
Bound to fingerprint `9d3ba9d2e6c4`, which seals both the INPUTS (agent config, the analysed Apex/Flow, the permission snapshot, and what the analysis identity could see) and the TOOL that produced this verdict (analyzer `65e31fb90c7c`, parser `5.1.0`; each analysed class's own apiVersion is bound per action, since it decides the verdict). Regenerate if any of these change.

_The fingerprint seals the **static analysis** — the agent's config, the analysed Apex/Flow, the permission snapshot, and the analyzer itself. It does **not** cover the live `COUNT()` figures above: those are a measurement of the org at the moment of the run. Two runs sharing a fingerprint can legitimately show different counts._