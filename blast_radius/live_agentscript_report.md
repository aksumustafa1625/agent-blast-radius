```
AGENT BLAST RADIUS REPORT - HealthRecord_Assistant_AS
Running user: (permission set: HR_Agent_Minimal)   (channel: agent)
Config fingerprint: 96299c990aa7      Generated: deterministic
================================================================

ESCALATION GAP ......... 1 fields  /  1 GDPR-labelled   <==

REACH SUMMARY
  Actions analysed ....... 1
  Objects reachable ...... 1
  Fields reachable ....... 2
  System-mode actions .... 1 / 1
  Legacy API (< v67) ..... 1 / 1

CLASSIFICATION COVERAGE
  Reachable fields ....... 2
  Classified (GDPR/PII) .. 1
  Visible, unclassified .. 1
  Not visible to analyzer  0
  Coverage ............... 100%
```

> **1 fields can be reached beyond the running user - 1 of them GDPR-labelled.**

## ERROR - 3 finding(s)

- **[PS501] GetHealthRecordSummary -> HealthRecord__c**
  - Potential record-scope expansion: reads HealthRecord__c in system mode on a Private object (apiVersion<=66 system default).
  - _Why:_ The running user is subject to record-level sharing this operation does not enforce. Query predicates and application-level ownership checks are NOT analyzed statically, so this flags a boundary to review, not a proven leak.
  - _Fix:_ Enforce user mode (with sharing + WITH USER_MODE) or upgrade the class to API v67; if system mode is intended, confirm the query restricts records by owner/input.
- **[PS506] GetHealthRecordSummary -> HealthRecord__c.Diagnosis__c**
  - GDPR/PII field HealthRecord__c.Diagnosis__c is read in system mode and reaches the model, but the running user has no FLS on it.
  - _Why:_ ComplianceGroup PII;HIPAA;GDPR. A field the running user cannot see can reach the LLM and the end user's screen. Authority Path CONFIRMED: the field's value flows to the action's @InvocableVariable output, so it reaches the model.
  - _Fix:_ Remove the field from the query/output, or enforce FLS (WITH USER_MODE / Security.stripInaccessible).
- **[PS522] get_health_record -> HealthRecord__c.Diagnosis__c**
  - GDPR/PII field HealthRecord__c.Diagnosis__c is interpolated into the model's prompt at line 125, and the running user has no FLS on it.
  - _Why:_ ComplianceGroup PII;HIPAA;GDPR. Traced end to end: HealthRecord__c.Diagnosis__c -> @outputs.summary (Apex) -> @variables.record_summary (line 128) -> prompt (line 125). This is not inferred reachability - every hop is a node in the parse tree.
  - _Fix:_ Remove {! @variables.record_summary } from the instructions, drop the field from the action's output, or enforce FLS in the Apex.

## INFO - 2 finding(s)

- **[PS511] GetHealthRecordSummary (API v58.0)**
  - Custom action class predates API v67 (secure-by-default).
  - _Why:_ Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.
  - _Fix:_ Plan a migration to API v67 and re-review.
- **[PS520] get_health_record -> HealthRecord__c.Patient_Name__c**
  - Action data reaches the prompt: HealthRecord__c.Patient_Name__c is interpolated at line 125.
  - _Why:_ A data->prompt path exists. Traced: HealthRecord__c.Patient_Name__c -> @outputs.summary (Apex) -> @variables.record_summary (line 128) -> prompt (line 125).
  - _Fix:_ No action needed; listed so the agent's prompt surface is visible.

---
Produced by static analysis. No agent was invoked. 0 Flex Credits.
Bound to fingerprint `96299c990aa7`; regenerate if agent config, any analysed Apex/Flow, or permission metadata changes.