# 02 — Container Diagram (C4 Level 2)

## Purpose

The module pipeline: reach readers on the left, org facts on the right, the
authority join in the middle. The load-bearing rule is that **both Apex
extraction backends feed the SAME precedence core** (ADR-004) — a reach
feature added to one path only creates a backend-specific blind spot.

## Diagram

```mermaid
graph TB
    CLI["cli.py<br/><i>--agent | --agent-script, --org,<br/>--permission-set | --running-user,<br/>--include-counts, --fail-on, --apex-backend</i>"]

    subgraph Reach["Reach readers (what the code can touch)"]
        AS["agentscript_loader.py + agentscript_extract.mjs<br/><i>Salesforce's own parser → IR</i>"]
        AI["apex_introspect.py<br/><i>THE precedence core (_resolve/_resolve_dml_fls)<br/>+ regex extractor + SOSL + sanitizer + async</i>"]
        AST["apex_ast.py + ast_extract.js<br/><i>ANTLR parse tree → IR<br/>+ Authority Path taint</i>"]
        FLOW["flow_introspect.py<br/><i>Flow XML → runInMode + per-element reach</i>"]
        PROMPT["genai_prompt_introspect.py<br/><i>prompt templates, ALL versions (PS513)</i>"]
        PFA["prompt_flow_analyzer.py<br/><i>PS520/521/522 — data → prompt chain</i>"]
    end

    subgraph OrgFacts["Org facts (what the user may / what the org labels)"]
        SNAP["snapshot_loader.py<br/><i>username → profile + permsets (+ PSG aggregate)</i>"]
        PERM["permission_resolver.py<br/><i>pure EffectivePermissions over a snapshot</i>"]
        OL["org_loaders.py<br/><i>classification, sharing models, triggers,<br/>COUNT, god-mode grants, OWD (live sf, read-only)</i>"]
    end

    AA["authority_analyzer.py<br/><b>the join: reach × permissions × labels → PS5xx findings</b>"]

    subgraph Out["Output"]
        REP["report.py / report_html.py<br/><i>deterministic md + themed html,<br/>fingerprint-bound (tool + inputs)</i>"]
        HEALTH["org_health.py / org_census.py<br/><i>'beyond this agent' footer + whole-org apiVersion census</i>"]
        VD["verify_deterministic.py<br/><i>two runs, sha256 diff</i>"]
    end

    CLI --> Reach
    AS --> AI
    AST --> AI
    AI --> AA
    FLOW --> AA
    PROMPT --> AA
    PFA --> AA
    SNAP --> PERM --> AA
    OL --> AA
    AA --> REP
    HEALTH --> REP
    REP -.-> VD

    style AI fill:#003F7F,stroke:#001E3D,color:#fff,stroke-width:3px
    style AA fill:#8E44AD,stroke:#5E2D73,color:#fff,stroke-width:2px
```

## Layer rules

| Component | May | Must never | Why |
|---|---|---|---|
| Extraction backends (regex / AST) | emit IR | apply their own precedence interpretation | one law, one place (ADR-004) |
| `apex_introspect` core | resolve mode per the law | be "fixed" from documentation | ADR-001: experiments only |
| `permission_resolver` | pure computation over a snapshot | live queries | testability; snapshots are fixtures |
| `org_loaders` | read-only live SOQL | any write; any agent invocation | ADR-009 |
| `authority_analyzer` | join + emit findings | fabricate a number or estimate visibility | ADR-003/008; the rule table IS this file |
| `report*` | render + fingerprint | be trusted over the console summary | reports are written after render — check the console line |

## The benchmark sits outside the pipeline

`benchmark/` (corpus, runner, mutation, runtime oracle, sfge differential)
consumes the analyzer as a black box — labels are hand-written, never
generated from the law under test (ADR-005), and the oracle's ground truth
is the org itself.

## Drill-down

- One scan in time order: [03 — Sequence](03-sequence.md)
- What flows between the stages: [04 — Data Model](04-data-model.md)
