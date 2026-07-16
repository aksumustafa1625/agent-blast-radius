```
AGENT BLAST RADIUS REPORT - HealthRecord Assistant
Running user: (permission set: HR_Agent_Minimal)   (channel: agent)
Config fingerprint: c4ca85da3d2b      Generated: deterministic
================================================================

ESCALATION GAP ......... 1 fields  /  1 GDPR-labelled   <==

REACH SUMMARY
  Actions analysed ....... 5
  Objects reachable ...... 1
  Fields reachable ....... 2
  System-mode actions .... 1 / 5
  Legacy API (< v67) ..... 1 / 5

CLASSIFICATION COVERAGE
  Reachable fields ....... 2
  Classified (GDPR/PII) .. 1
  Visible, unclassified .. 1
  Not visible to analyzer  0
  Coverage ............... 100%
```

> **1 fields can be reached beyond the running user - 1 of them GDPR-labelled.**

## ERROR - 2 finding(s)

- **[PS501] GetHealthRecordSummary -> HealthRecord__c**
  - Potential record-scope expansion: reads HealthRecord__c in system mode on a Private object (apiVersion<=66 system default).
  - _Why:_ The running user is subject to record-level sharing this operation does not enforce. Query predicates and application-level ownership checks are NOT analyzed statically, so this flags a boundary to review, not a proven leak.
  - _Fix:_ Enforce user mode (with sharing + WITH USER_MODE) or upgrade the class to API v67; if system mode is intended, confirm the query restricts records by owner/input.
- **[PS506] GetHealthRecordSummary -> HealthRecord__c.Diagnosis__c**
  - GDPR/PII field HealthRecord__c.Diagnosis__c is read in system mode and returned to the model, but the running user has no FLS on it.
  - _Why:_ ComplianceGroup PII;HIPAA;GDPR. A field the running user cannot see can reach the LLM and the end user's screen.
  - _Fix:_ Remove the field from the query/output, or enforce FLS (WITH USER_MODE / Security.stripInaccessible).

## INFO - 5 finding(s)

- **[PS507] EmployeeCopilot__AnswerQuestionsWithKnowledge**
  - Action target 'EmployeeCopilot__AnswerQuestionsWithKnowledge' is a standard/opaque action.
  - _Why:_ Its reach is not statically analysable from source.
  - _Fix:_ Rely on the vendor's documentation / a runtime review.
- **[PS507] EmployeeCopilot__AnswerQuestionsWithKnowledge**
  - Action target 'EmployeeCopilot__AnswerQuestionsWithKnowledge' is a standard/opaque action.
  - _Why:_ Its reach is not statically analysable from source.
  - _Fix:_ Rely on the vendor's documentation / a runtime review.
- **[PS507] EmployeeCopilot__GetRecordDetails**
  - Action target 'EmployeeCopilot__GetRecordDetails' is a standard/opaque action.
  - _Why:_ Its reach is not statically analysable from source.
  - _Fix:_ Rely on the vendor's documentation / a runtime review.
- **[PS507] EmployeeCopilot__SummarizeRecord**
  - Action target 'EmployeeCopilot__SummarizeRecord' is a standard/opaque action.
  - _Why:_ Its reach is not statically analysable from source.
  - _Fix:_ Rely on the vendor's documentation / a runtime review.
- **[PS511] GetHealthRecordSummary (API v58.0)**
  - Custom action class predates API v67 (secure-by-default).
  - _Why:_ Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.
  - _Fix:_ Plan a migration to API v67 and re-review.

---
Produced by static analysis. No agent was invoked. 0 Flex Credits.
Bound to fingerprint `c4ca85da3d2b`; regenerate if agent config, any analysed Apex/Flow, or permission metadata changes.