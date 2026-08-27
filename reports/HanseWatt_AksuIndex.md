```
==============================================================================
  AKSU INDEX  -  HW Energy Agent
==============================================================================

      0  PROVEN
         no field is PROVEN reachable beyond this running user.

!!----------------------------------------------------------------------------
!! (0 proven with unresolved reach is NOT clean - unknown never becomes clean)
!! Read this as "0 proven, 2 unresolved", never as a pass.
!!----------------------------------------------------------------------------

      0  unproven boundaries      real boundaries we could not prove crossed
      2  unresolved               reach we could not determine at all

  Aksu Index: 0 proven (0 GDPR) · 0 unproven boundaries · 2 unresolved
  (all four numbers ARE the metric - none of them may be quoted alone)

------------------------------------------------------------------------------
  WHAT THE AGENT'S CODE REACHES  vs  WHAT THIS RUNNING USER MAY SEE

      Objects reached by the agent ............. 4
      Fields reached by the agent .............. 4
        of those, readable by this user ........ 4
        beyond this user - the gap ............. 0
           that gap = 0 proven + 0 unproven, the two numbers above

  The Index counts fields, never records. This run does not measure how
  many objects the running user can see, so no user-side object count is
  claimed here.
==============================================================================
```

```
AGENT BLAST RADIUS REPORT - HW Energy Agent
Running user: (hypothetical grant model - permission set: HW_ServiceAgent)   (channel: agent)
Config fingerprint: ca8d728bfeb2      Generated: deterministic
Aksu Index spec v1.0: aksuindex.com
================================================================

ESCALATION GAP ......... 0 fields  /  0 GDPR-labelled

REACH SUMMARY
  Actions analysed ....... 9
  Objects reachable ...... 4
  Fields reachable ....... 4
  System-mode actions .... 2 / 9
  Legacy API (< v67) ..... 0 / 9

CLASSIFICATION COVERAGE
  Reachable fields ....... 1
  Classified (GDPR/PII) .. 0
  Visible, unclassified .. 1
  Not visible to analyzer  0
  Coverage ............... 100%
```

### Record reach (live COUNT — upper bound)

> **Every read the agent performs enforces sharing, so the agent is bounded by the running user — there is no record escalation.**

| Object | Read mode | Records in org | User sees | Gap (upper bound) | Cause |
| --- | --- | ---: | ---: | ---: | --- |
| `Case` | user | 33 | _= agent (sharing enforced)_ | 0 | — |
| `Tariff_Change_Request__c` | user | ? | _= agent (sharing enforced)_ | 0 | — |

> _`Records in org` is a live `COUNT()` of the whole object run as the analysis identity. **It is an upper bound, not the agent's result**: query predicates and `LIMIT` are not resolved statically. It is an escalation ceiling only for **system-mode** reads — a **user-mode** read enforces sharing, so the agent is bounded by the running user and the gap is 0 by construction. **CRUD** = the user has no object permission at all (deterministic); **sharing** = the user can read the object but record-level sharing may hide rows, which is data-dependent and shown as `n/a` — never estimated._

## WARN - 3 finding(s)

- **[PS504] HWConfirmTariffChangeAction -> ?**
  - Reach for this operation could not be fully determined - the query is assembled at runtime (dynamic SOQL - reach cannot be determined statically).
  - _Why:_ A silent false-clean is worse than an honest unknown, so this is counted as unresolved rather than passed. The query does not exist until runtime, so no static analysis - this one or any other - can enumerate what it reaches. It stays unresolved until the code changes.
  - _Fix:_ Yours to close: make the query static, or add WITH USER_MODE so the runtime enforces this user's access whatever the query resolves to.
- **[PS504] HWProposeTariffChangeAction -> ?**
  - Reach for this operation could not be fully determined - the query is assembled at runtime (dynamic SOQL - reach cannot be determined statically).
  - _Why:_ A silent false-clean is worse than an honest unknown, so this is counted as unresolved rather than passed. The query does not exist until runtime, so no static analysis - this one or any other - can enumerate what it reaches. It stays unresolved until the code changes.
  - _Fix:_ Yours to close: make the query static, or add WITH USER_MODE so the runtime enforces this user's access whatever the query resolves to.
- **[PS514] HWConfirmTariffChangeAction (platform event: Tariff_Change_Requested__e)**
  - This action publishes Tariff_Change_Requested__e. The publish is analysed as a write; any Flow, process, or external subscriber is NOT.
  - _Why:_ No Apex subscriber trigger exists on it, but a platform event can also be consumed by a Flow, a process, or an off-platform subscriber, each running in its own transaction as a different user. Publishing is how an agent starts work it could not do inline, so the true blast radius can be larger than this report. An honest unknown edge, not a proven leak.
  - _Fix:_ List the subscribers of Tariff_Change_Requested__e (Flow, process, and external) and review each as its own entry point.

## Org health — beyond this agent

_Whole-org signals that don't concern HW Energy Agent directly, but anyone securing this org should know. Static Tooling-API reads — zero credits._

> **Why this matters for HW Energy Agent:** **0 proven** escalation — but 2 operations could not be resolved at all, so this is **not** clean: an unknown never becomes clean. And if the code is still pre-v67, even that zero rests on the code explicitly opting in (`WITH USER_MODE`), not the platform default.

- **182/219 of your own Apex files are pre-v67** (83% system-mode by default) — the same latent escalation this report proves for the agent's classes sits in every other legacy file.
- **1 permission set(s) grant *Modify All Data*** — overrides all sharing and FLS for whoever holds them.
- 3 permission set(s) grant *View All Data* only.
- Every custom object defaults to **Private** sharing — a healthy baseline.

---
Produced by static analysis. No agent was invoked. 0 Flex Credits.
Bound to fingerprint `ca8d728bfeb2`, which seals both the INPUTS (agent config, the analysed Apex/Flow, the permission snapshot, and what the analysis identity could see) and the TOOL that produced this verdict (analyzer `65e31fb90c7c`, parser `5.1.0`; each analysed class's own apiVersion is bound per action, since it decides the verdict). Regenerate if any of these change.

_The fingerprint seals the **static analysis** — the agent's config, the analysed Apex/Flow, the permission snapshot, and the analyzer itself. It does **not** cover the live `COUNT()` figures above: those are a measurement of the org at the moment of the run. Two runs sharing a fingerprint can legitimately show different counts._