# 03 — Sequence: one scan, end to end

## Purpose

What `python blast_radius/cli.py --agent X --permission-set Y --org Z
--include-counts` actually does, in order — and where the two things a
reader must know about live: the fingerprint's scope, and why the console
summary (not the report file) is the proof of a run.

## Diagram

```mermaid
sequenceDiagram
    actor Op as Operator / CI
    participant CLI as cli.py
    participant Org as Salesforce org<br/>(read-only sf CLI)
    participant Ext as extraction<br/>(AST → regex fallback)
    participant Core as precedence core<br/>(apex_introspect)
    participant AA as authority_analyzer
    participant Rep as report md + html

    Op->>CLI: --agent | --agent-script, --permission-set, --org
    CLI->>Org: retrieve agent metadata / read .agent source
    CLI->>CLI: resolve agent config (actions, channels)
    CLI->>Ext: extract reach per action (SOQL/SOSL/DML/dynamic/async)
    Ext->>Core: IR (both backends land here)
    Core->>Core: resolve per operation:<br/>1 explicit clause › 2 apiVersion › 3 sharing decl<br/>→ (enforces_sharing, enforces_fls) each T/F/None
    CLI->>Org: classifications (ComplianceGroup), sharing models,<br/>triggers, permissions (+PSG aggregate), OWD
    opt --include-counts
        CLI->>Org: live COUNT() per reached object<br/>(upper bound - ADR-008)
    end
    CLI->>AA: reach × EffectivePermissions × labels
    AA->>AA: PS501..PS522 findings<br/>(severity = proof level - ADR-003)
    AA->>Rep: render md + html; fingerprint seals<br/>TOOL (analyzer hash, parser, backend,<br/>per-action apiVersion) + INPUTS - ADR-007
    Rep-->>Op: console summary line<br/>(ESCALATION GAP, ERROR/WARN/INFO, exit code via --fail-on)
```

## Two facts about the tail of the run

1. **Reports are written AFTER render, and the summary prints after that.**
   A crash between the two leaves a stale report on disk that looks like a
   successful run — this has hidden two bugs at once before. The console
   summary line is the proof; the file is a by-product.
2. **The fingerprint deliberately excludes the live COUNTs** (they measure
   the org at run time). Two runs sharing a fingerprint with different
   counts is *correct behaviour* — and the demo's liveness proof.

## Determinism harness

`verify_deterministic.py -- <same args>` runs the CLI twice and
sha256-diffs both outputs (md and html). Proven live: byte-identical.
