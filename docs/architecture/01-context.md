# 01 — System Context (C4 Level 1)

## Purpose

Where Agent Blast Radius sits: what it reads, who consumes its output, and
which boundaries it never crosses (no agent invocation, no data egress).

## Diagram

```mermaid
graph TB
    %% ============ Actors ============
    SecArch(["Security architect / reviewer<br/><i>reads the report, gates the build</i>"])
    CI(["CI pipeline<br/><i>--fail-on ERROR on every commit</i>"])

    %% ============ The system ============
    BR["<b>Agent Blast Radius</b><br/>static, zero-credit authority analysis<br/><i>execution semantics × permissions × GDPR labels</i>"]

    %% ============ Inputs ============
    Org["Salesforce org<br/><i>metadata, permissions,<br/>ComplianceGroup labels, OWD, COUNT()</i>"]
    AgentSrc[".agent source<br/><i>Agent Script, parsed with<br/>Salesforce's own parser</i>"]
    GenAi["GenAiPlannerBundle metadata<br/><i>compiled Agent Builder agents</i>"]

    %% ============ Siblings ============
    Pruefstand["Prüfstand<br/><i>behavioral half:<br/>what the agent DOES</i>"]
    Aktenlage["Aktenlage<br/><i>legal output layer:<br/>files the evidence (Art. 26)</i>"]

    Org -->|"read-only sf CLI<br/>zero Flex Credits"| BR
    AgentSrc --> BR
    GenAi --> BR
    BR -->|"deterministic report md+html<br/>Escalation Gap + PS5xx findings<br/>fingerprint-bound"| SecArch
    BR -->|"exit code via --fail-on"| CI
    BR -->|"report consumed as sealed evidence<br/>(blast_radius_bridge)"| Aktenlage
    Pruefstand -.->|"bounds the same agent<br/>from the behavior side"| SecArch

    style BR fill:#003F7F,stroke:#001E3D,color:#fff,stroke-width:3px
    style Aktenlage fill:#28B463,stroke:#1D7E45,color:#fff
    style Pruefstand fill:#B9770E,stroke:#7E5109,color:#fff
```

## Key observations

1. **The agent is never invoked** (ADR-009): every arrow into the tool is
   metadata, source, or zero-credit SOQL. No Flex Credits, no triggered
   behaviour, no data leaving the machine.
2. **Two agent input paths, one analysis**: Agent Script source (with the
   data→prompt taint proof, PS520–522) and compiled GenAi metadata converge
   on the same IR (ADR-010, ADR-004).
3. **The question is user-scoped**: not "what can this org's code do" but
   "what can THIS agent reach as THIS running user" — reach × effective
   permissions × the org's own GDPR labels. The composition is the novelty.
4. **Downstream, the report is evidence**: Aktenlage seals it by hash and
   renders the legal case file; the fingerprint (ADR-007) is what makes that
   hand-off auditable.

## Drill-down

Inside the tool: [02 — Container Diagram](02-container.md).
