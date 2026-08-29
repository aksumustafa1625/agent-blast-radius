# ADR-001: Prove the precedence law in-org before coding it — answer doc-claims with experiments

## Status

**Accepted**

## Date

2026-07-18 (in effect since Milestone 0; recorded retrospectively)

## Author

Mustafa Aksu

## Context

The entire product is one resolution rule: for a plain SOQL/DML operation,
execution mode resolves as (1) explicit clause, (2) apiVersion default
(≥ v67 user mode), (3) sharing declaration — record axis only, under system
mode. A naive scanner that flags `without sharing` without this precedence
produces false positives that destroy its own credibility. And Salesforce's
own documentation is not a safe source: docs describe *intent*, the org
describes *behaviour*, and only one of them is what a customer runs.

This is not hypothetical. Two external reviews, citing real Salesforce
documentation, proposed "fixes" that would have broken correct code:
- "v67 `without sharing` must be record-bypassing" → **E2b** disproved it in-org.
- "Summer '26: triggers always run in system mode" → **E13** disproved it
  in-org, on Summer '26, the same week the claim was raised.

## Decision

Every load-bearing semantic is established by a hand-run, in-org experiment
**before** it is coded (Milestone 0, E1–E13 in `MILESTONE_0_EVIDENCE.md`),
and any documentation-based challenge to the law is answered with a new
experiment — never with an edit. The experiment record (self-contained
fixtures, `System.runAs`, zero credits) is part of the repo.

## Consequences

### Positive

- The precedence core has ground truth that does not share a mind with the
  implementation; reviews citing docs can be adjudicated in hours.
- Three widely-assumed shortcuts were disproved before they could become
  bugs (missing declaration ≠ `without sharing`; v67 default beats explicit
  `without sharing` for plain ops; trigger mode follows the trigger's own
  apiVersion).
- E13 exists because E6's v67 half was only a docstring assertion — now a
  platform regression would be *caught*, not believed.

### Negative / Trade-offs

- Experiments cost real org time, and each one must be designed with
  controls (E10 exists because E2's round 1 had none — a 0 could have meant
  "nothing to see").
- One measurement is not a rule: the stripInaccessible false positive came
  from generalising a single branch. Probe every branch of an axis that
  could differ.

## Alternatives Considered

### Alternative A — implement from Salesforce documentation

Rejected by two direct counterexamples (above). Docs lag, generalise, and
sometimes describe planned behaviour.

### Alternative B — implement from community consensus / other scanners

Rejected: sfge itself is apiVersion-blind (8/21 contradictions against the
org). Consensus encodes the exact shortcuts E2/E2b/E6 disproved.

## References

- Source: CLAUDE.md §2 (the law + the E-table + the double warning), MILESTONE_0_EVIDENCE.md
- Related ADRs: ADR-002 (what the axes are), ADR-005 (the same philosophy for accuracy), ADR-011 (the cost of believing a doc)
