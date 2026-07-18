# Agent Blast Radius — Source Layout

A layered pipeline in which the boundaries are rules, not folders: reach
readers feed one precedence core, org facts arrive read-only, and one join
produces every finding. The repo map below is the working truth; the
reasoning behind each boundary lives in [docs/adr/](docs/adr/).

```
agent-blast-radius/
├── blast_radius/
│   ├── cli.py                    entry point: --agent | --agent-script, --org,
│   │                             --permission-set | --running-user,
│   │                             --include-counts, --fail-on, --apex-backend
│   │
│   │  # ---- reach readers (what the code can touch) ----
│   ├── apex_introspect.py        THE precedence core (_resolve/_resolve_dml_fls)
│   │                             + regex extractor + SOSL + sanitizer + async
│   ├── apex_ast.py               subprocess bridge to the real parse tree
│   ├── ast_extract.js            ANTLR apex-parser walker → IR (+ Authority Path taint)
│   ├── flow_introspect.py        Flow XML → runInMode + per-element reach
│   ├── genai_prompt_introspect.py  prompt templates, ALL versions (latent = PS513)
│   ├── agentscript_loader.py     Salesforce's own Agent Script parser → IR
│   ├── agentscript_extract.mjs
│   ├── prompt_flow_analyzer.py   PS520/521/522 — the data → prompt chain
│   │
│   │  # ---- org facts (what the user may / what the org labels) ----
│   ├── snapshot_loader.py        username → profile + permsets (+ PSG aggregate)
│   ├── permission_resolver.py    pure EffectivePermissions over a snapshot
│   ├── org_loaders.py            live sf queries: classification, sharing,
│   │                             triggers, COUNT, god-mode grants, OWD
│   │
│   │  # ---- the join and the output ----
│   ├── authority_analyzer.py     reach × permissions × labels → PS5xx findings
│   ├── report.py / report_html.py  deterministic md + themed html (fingerprint)
│   ├── make_pdf.py               presentation step for the demo
│   ├── org_census.py / org_health.py  whole-org apiVersion debt views
│   ├── verify_deterministic.py   two runs, sha256-diff both outputs
│   │
│   ├── benchmark/                corpus + runner + mutation + runtime oracle
│   │                             + sfge differential (see ADR-005/006)
│   ├── fixtures/                 permission snapshots + apex/prompt fixtures
│   └── test_*.py                 216 unit tests
│
├── sfdx-blast-radius/            sf CLI plugin (linked; `sf blast-radius ...`)
├── docs/adr/                     12 decision records incl. the rejections
├── docs/architecture/            context / container / sequence / data / CI
├── docs/demo/                    rehearsed video recording script
├── MILESTONE_0_EVIDENCE.md       the in-org experiments E1–E13
├── CLAUDE.md                     working context: the law, the discipline,
│                                 the rule table, the paid-for mistakes
└── .github/workflows/            analyze (always) + live-scan (secret-gated)
```

## The rules that make it hold together

1. **Both extraction backends feed the SAME precedence core** (ADR-004).
   Add a reach feature once, in Python, for both paths — or one backend
   gets a blind spot the other doesn't have.
2. **The precedence core is experiment-locked** (ADR-001). It is never
   edited from documentation; a doc-based challenge gets an in-org
   experiment (E1–E13 and counting).
3. **Two axes, never merged** (ADR-002): `enforces_sharing` ≠
   `enforces_fls`, each True/False/None, and "bounded by the user" needs
   both.
4. **The join never fabricates** (ADR-003/008): severity = proof level,
   COUNT = upper bound, sharing-dependent visibility = `n/a`.
5. **The report seals its own producer** (ADR-007): analyzer source hash,
   parser version, backend, per-action apiVersion — plus the inputs.
6. **The console summary is the proof of a run** — reports are written
   after render; a crash in between leaves a healthy-looking stale file.

## Reading order for a new engineer

`README.md` (what and why) → `CLAUDE.md` §2–§3 (the law + the honesty
discipline) → [docs/architecture/](docs/architecture/) (the shape) →
[docs/adr/](docs/adr/) (the decisions) → `MILESTONE_0_EVIDENCE.md` (the
experiments everything cites).
