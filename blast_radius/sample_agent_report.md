```
AGENT BLAST RADIUS REPORT - HW_Energy_Agent
Running user: svc@example.com   (channel: web-unauthenticated)
Config fingerprint: 909350a660e4      Generated: 2026-07-14
================================================================

ESCALATION GAP ......... 1 fields  /  1 GDPR-labelled   <==

REACH SUMMARY
  Actions analysed ....... 3
  Objects reachable ...... 1
  Fields reachable ....... 2
  System-mode actions .... 2 / 3
  Legacy API (< v67) ..... 1 / 3
```

> **1 fields can be reached beyond the running user - 1 of them GDPR-labelled.**

## ERROR - 4 finding(s)

- **[PS501] BlastR System Flow -> Blast_Test__c**
  - Reads Blast_Test__c in system mode; object sharing model is Private (Flow runInMode=SystemModeWithoutSharing).
  - _Why:_ The running user is subject to record-level sharing this action bypasses; it can surface records the user cannot see.
  - _Fix:_ Enforce user mode (with sharing + WITH USER_MODE) or upgrade the class to API v67.
- **[PS501] BlastRadius_E2_ReaderV58 -> Blast_Test__c**
  - Reads Blast_Test__c in system mode; object sharing model is Private (apiVersion<=66 system default).
  - _Why:_ The running user is subject to record-level sharing this action bypasses; it can surface records the user cannot see.
  - _Fix:_ Enforce user mode (with sharing + WITH USER_MODE) or upgrade the class to API v67.
- **[PS506] BlastR System Flow -> Blast_Test__c.Customer_IBAN__c**
  - GDPR/PII field Blast_Test__c.Customer_IBAN__c is read in system mode and returned to the model, but the running user has no FLS on it.
  - _Why:_ ComplianceGroup PII;GDPR. A field the running user cannot see can reach the LLM and the end user's screen.
  - _Fix:_ Remove the field from the query/output, or enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS510] BlastR System Flow (Flow)**
  - Flow runs in System Mode without Sharing.
  - _Why:_ Record-level and FLS enforcement are bypassed by configuration, invisible in the Agent Builder UI.
  - _Fix:_ Set runInMode to DefaultMode unless system context is justified and documented.

## INFO - 1 finding(s)

- **[PS511] BlastRadius_E2_ReaderV58 (API v58.0)**
  - Custom action class predates API v67 (secure-by-default).
  - _Why:_ Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.
  - _Fix:_ Plan a migration to API v67 and re-review.

---
Produced by static analysis. No agent was invoked. 0 Flex Credits.
Bound to fingerprint `909350a660e4`; regenerate if agent config, any analysed Apex/Flow, or permission metadata changes.