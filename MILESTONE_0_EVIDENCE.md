# Agent Blast Radius — Milestone 0 Evidence

> **What this is:** the hand-run, in-org proof that the Agent Blast Radius thesis
> is true *and* that every metadata input the tool needs is readable for free.
> Nothing here is a claim on paper — each line was executed in a real org and the
> result recorded. No agent was invoked; zero Flex Credits were spent.

**Org:** Developer Edition, `HospitalOrg` (`ORG-LAB-B`), API v67.0
**Date:** 2026-07-14
**Method:** self-contained Apex fixtures (own object, own minimal user via
`System.runAs`) deployed with the Salesforce CLI; results read from
`sf apex run test` / `sf data query`. No real org users or data were touched.

---

## Executive summary

Six experiments, all cleared. The thesis — *an agent's real data reach is
decided by its code's execution semantics, not by the running user's
permissions* — holds, and three widely-assumed shortcuts were proven **wrong**,
each of which would have made a naive scanner emit false results.

| # | Question | Result | Verdict |
|---|---|---|---|
| **E1** | Can `without sharing` code read what the user cannot? | system-mode **5**, user-mode **0** (CRUD *and* record-sharing layers) | Mechanism real → green light |
| **E2** | Does the class API version change the default? | same code: v58 **5**, v67 **0** | apiVersion is a first-class input |
| **E3** | Will we false-positive on safe code? | same `without sharing` class: plain **5**, `WITH USER_MODE` **0** | Operation mode wins → no false positive |
| **E4** | Are the org's GDPR labels free to read? | `ComplianceGroup = PII;GDPR`, `SecurityClassification = Confidential` | DPO feature has a data source |
| **E5** | Can we analyze Flows without parsing Apex? | `runInMode`, object and fields all declarative | Flow actions in scope, cheaply |
| **E6** | Are trigger cascades a hidden vector? | legacy (v58) trigger escalates even a clean user-mode action | PS509 real, keyed to trigger apiVersion |

---

## The precedence law (derived empirically, not from docs)

For a **plain** (unqualified) SOQL/DML operation, the execution mode resolves in
this order — confirmed by E1/E2/E3:

```
1. Explicit operation clause   WITH USER_MODE / WITH SYSTEM_MODE / AccessLevel.*
2. apiVersion default          API >= 67  -> USER_MODE
                               API <= 66  -> SYSTEM_MODE
3. Class sharing declaration   governs record-level access only under SYSTEM_MODE
```

The analyzer MUST resolve per-operation and apiVersion-aware. Flagging
`without sharing` without checking (1) and (2) produces false positives that
would destroy the tool's credibility.

---

## Three assumptions the experiments proved WRONG

1. **"No sharing declaration" ≠ "without sharing".** A declaration-less class
   inherits the caller's sharing context. In E2 round 1, declaration-less
   classes at v58 *and* v67 both returned 0, while E1's *explicit* `without
   sharing` class returned 5. → the analyzer must not treat a missing
   declaration as system mode.

2. **v67's user-mode default overrides even an explicit `without sharing`** for
   plain operations. Same code, v58 = 5 (escalation), v67 = 0 (safe). → a
   version-blind scanner cries wolf on modern code.

3. **A trigger's DML mode follows the *trigger's* API version, not the action's
   access level.** A perfectly clean user-mode action still escalated through a
   v58 trigger. → PS509 must key on the trigger's apiVersion.

---

## Experiment detail

### E1 — the mechanism (kill-shot)
- **Fixture:** `Blast_Test__c` (OWD Private), `BlastRadius_E1_Test`.
- **Setup:** 5 records owned by admin; a Standard-User `runAs` identity.
- **Scenario A (CRUD):** user has no object permission → system-mode read 5,
  user-mode read 0.
- **Scenario B (record sharing):** user granted object+field read, but records
  owned by another user under Private OWD → system-mode 5, user-mode 0.
- **Result:** both methods PASS. The gap between 5 and 0 *is* the Escalation Gap.
- **Interview line:** *"Same user, same Private object — a `without sharing`
  action returns every record, a `with sharing` + `USER_MODE` action returns
  none. That gap is what the tool measures."*

### E2 — the apiVersion flip
- **Fixture:** `BlastRadius_E2_ReaderV58` / `...V67` (identical bodies), `BlastRadius_E2_Test`.
- **Round 1 (no declaration):** v58 = 0, v67 = 0 → revealed "no declaration ≠
  without sharing".
- **Round 2 (explicit `without sharing`):** v58 = 5, v67 = 0 → PASS.
- **Interview line:** *"Summer '26 flipped the Apex default to secure-by-default,
  but only for v67+ code. I confirmed a v58 and a v67 class with identical
  bodies behave oppositely. That's why per-class API version is a first-class
  input."*

### E3 — precedence (the anti-false-positive proof)
- **Fixture:** `BlastRadius_E3_Test` — one `without sharing` class, two queries.
- **Result:** plain query 5, `WITH USER_MODE` query 0 → PASS.
- **Interview line:** *"The hard part isn't finding escalations — it's not
  flagging safe code. `WITH USER_MODE` overrides `without sharing`, and the
  resolver encodes exactly that, so it never cries wolf."*

### E4 — GDPR labels are free (the DPO feature)
- **Setup:** tagged `Blast_Test__c.Customer_IBAN__c` via field metadata
  `<complianceGroup>PII;GDPR</complianceGroup>` +
  `<securityClassification>Confidential</securityClassification>`.
- **Result:** `SELECT QualifiedApiName, ComplianceGroup, SecurityClassification
  FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName='Blast_Test__c'
  AND QualifiedApiName='Customer_IBAN__c'` → `PII;GDPR` / `Confidential`.
- **Two constraints discovered:** (1) `FieldDefinition` queries must be bounded
  per `EntityDefinition`; (2) **`FieldDefinition` is FLS-gated** — it only
  returns fields the querying identity can read. Fields deployed via Metadata
  API get no automatic FLS, so a permission set granting field read had to be
  assigned before the labels appeared. → the classification scan must run as a
  broad-FLS identity, otherwise it misses exactly the fields the running user
  cannot see (the most important ones).
- **Interview line:** *"I don't guess what's sensitive — I read the org's own
  legal labels via `FieldDefinition.ComplianceGroup`, for free."*

### E5 — Flow run context is declarative
- **Setup:** deployed autolaunched Flow `BlastR_System_Flow`,
  `runInMode = SystemModeWithoutSharing`, reading
  `Blast_Test__c.Customer_IBAN__c`.
- **Result:** Salesforce's own deploy message returned:
  *"...configured to run in System Mode without Sharing. This system context
  grants all running users the permission to view and edit all data in your
  org... can lead to unsafe data access."* The retrieved metadata exposes
  `runInMode`, `processType`, `<object>` and `<queriedFields>` — all static.
- **Note:** this Flow reaches the GDPR-tagged field in system mode, tying E5 to
  E4.
- **Interview line:** *"Most real agent actions are Flows. Flow run context is
  declarative — I read it straight from metadata — so the tool covers actions
  AISPM tools miss, without executing anything."*

### E6 — trigger-cascade (PS509)
- **Fixture:** `Casc_Parent__c` / `Casc_Child__c`, `CascParentTrigger`
  (after-insert, writes a child), `BlastRadius_E6_Test`. User can create the
  parent, has no access to the child.
- **Four data points:**

  | Trigger apiVersion | Action mode | Child written? |
  |---|---|---|
  | v67 | user | no (blocked) |
  | v67 | system | no (blocked) |
  | v58 | user | **yes (escalation)** |
  | v58 | system | **yes (escalation)** |

- **Finding:** a trigger's plain DML runs in the mode of the *trigger's own API
  version*, independent of the initiating action's access level. A clean
  user-mode action still escalates through a legacy trigger.
- **Interview line:** *"v67 made new triggers user-mode by default, but a legacy
  trigger still runs system-mode DML — so a spotless user-mode action can write
  a field the user can't touch, via a trigger it fires. The action looks clean;
  the cascade isn't."*

---

## Org fixtures produced (the laboratory)

- Objects: `Blast_Test__c` (Private OWD; fields `Secret_Data__c`,
  `Customer_IBAN__c` tagged PII;GDPR/Confidential), `Casc_Parent__c`,
  `Casc_Child__c`.
- Trigger: `CascParentTrigger` (currently API v58 for the escalation case).
- Flow: `BlastR_System_Flow` (SystemModeWithoutSharing).
- Permission sets: `BlastR_Read`, `BlastR_E2_Read`, `BlastR_E3_Read`,
  `BlastR_E6`, `BlastR_Classify`.
- Test classes: `BlastRadius_E1_Test`, `BlastRadius_E2_Test`
  (+ `ReaderV58`/`ReaderV67`), `BlastRadius_E3_Test`, `BlastRadius_E6_Test`.

## Zero-credit data layer — confirmed readable for free

`ObjectPermissions`, `FieldPermissions`, `PermissionSetAssignment`,
`FieldDefinition.ComplianceGroup` / `.SecurityClassification`,
`EntityDefinition.InternalSharingModel`, Flow `runInMode`, per-class
`ApexClass.ApiVersion` — all returned usable data via `sf data query` /
metadata retrieve. No agent invocation anywhere.

## Milestone 0 exit checklist

- [x] E1 pass — escalation mechanism real (5 vs 0)
- [x] E2 pass — v58 vs v67 defaults differ
- [x] E3 pass — `WITH USER_MODE` beats `without sharing`
- [x] E4 pass — metadata inputs return, including ComplianceGroup
- [x] E5 pass — Flow `runInMode` readable and predictive
- [x] E6 recorded — PS509 confirmed real, scoped to trigger apiVersion
- [x] Evidence filed for the portfolio (this document)
- [x] Extra-permission needs noted (FieldDefinition FLS-gating → §E4)

**Promoted to Milestone 1: the permission resolver.**
