# Contributing to Agent Blast Radius

This is a portfolio project, but its discipline is the product: a security
analyzer that overclaims once is done. The rules below exist because each
one was paid for — the incident behind a rule is usually named in
`CLAUDE.md` §7. Read that section before your first change.

## Setup

- Python 3.12+ (stdlib only for the core — there is no requirements.txt to
  install for the analyzer itself)
- Node 18+ **optional**: enables the AST backend and the Agent Script path
  (`npm install --prefix blast_radius`); without it the tool degrades
  honestly to the regex backend
- `sf` CLI + an authenticated org for live scans (not needed for tests)

```bash
# tests (AST/Agent-Script suites skip cleanly without Node)
python -m unittest discover -s blast_radius -t blast_radius -p "test_*.py"

# accuracy, not just green tests
python blast_radius/benchmark/run.py
python blast_radius/benchmark/mutate.py

# a live scan
python blast_radius/cli.py --agent <PlannerBundle> --permission-set <PermSet> \
       --org <alias> --include-counts --fail-on ERROR

# determinism proof
python blast_radius/verify_deterministic.py -- --agent <X> --permission-set <Y> --org <alias>
```

## Standing rules

### Semantics

- **Never "fix" the precedence law from documentation** (ADR-001). Two
  reviews tried, both citing real Salesforce docs, both wrong in-org
  (E2b, E13). Answer a doc-claim with an experiment in
  `MILESTONE_0_EVIDENCE.md`, never with an edit.
- **Track both axes** (ADR-002). Any new resolution logic must produce
  `enforces_sharing` AND `enforces_fls`, each True/False/None. `None` is an
  answer; it never silently becomes safe.
- **One measurement is not a rule.** Probe every branch of an axis that
  could differ before generalising (the stripInaccessible lesson).

### Findings

- **Severity = proof level** (ADR-003): ERROR only for what the resolution
  semantics prove; a real-but-unproven boundary is WARN; unknown reach is
  PS504. A false positive costs credibility exactly like a false clean.
- **Never fabricate a number** (ADR-008): COUNT is "up to N"; sharing-
  dependent visibility is `n/a`; no estimates, ever.
- **State where a claim comes from** — the benchmark's `truth:` field is
  the model.

### Extraction

- **Both backends, one core** (ADR-004): parse new reach features once in
  Python and append to both paths. A feature landing in only one backend is
  a bug even if its tests are green.
- **Never write regex/escapes through a shell heredoc** — `\n` arrives as a
  newline and `\b` as a literal backspace that no `print()` will show. Use
  the editor tools; compare patterns with `repr()`, never by eye. (Five
  incidents in one session.)
- Never re-import a module-level name inside a function (it shadows the
  global for the whole function).

### Verification

- **Run BOTH demo orgs after every rule change** — unit tests once missed
  an early `return` that made the PS511 block unreachable; the live run
  caught it instantly.
- **Check the console summary, not the report file** — reports are written
  after render; a crash between leaves a stale file that looks successful.
- **Benchmark expectations are hand-written** (ADR-005), never generated
  from the law under test. New rule ⇒ new corpus case(s) with a `truth:`
  label ⇒ if the claim is org-settleable, add a runtime shape (one shape
  beats ten reasoned labels) ⇒ check the mutation runner still has teeth
  for it.
- **Re-run `benchmark/sfge_diff.py` before repeating its numbers** — it is
  deliberately not in CI (ADR-006), so its headline can go stale silently.

### Environment

- Windows console is cp1252: **ASCII only in CLI output** (`[OK]`, not a
  glyph). PowerShell `$pid` is read-only. Use the `sf` CLI, not MCP tools,
  for deploys.
- Run foreign-org scans from THIS project directory.
- Agent bundle API names may carry a `_v1` suffix the BotDefinition name
  lacks.

### Commits and docs

- Commit messages: what changed **and what it proves / why it was wrong
  before**. Write the message to a file and `git commit -F` it (shell
  quoting has broken commits here).
- **Docs must be measured** — a stale docstring overstating a LIMITATION
  produced a false external CRITICAL once (E8). If you close a gap, delete
  its "known gap" note in the same commit.
- ADR when a decision changes what a finding may claim, rejects an
  alternative, or sets a boundary (see [docs/adr/README.md](docs/adr/README.md)).

## Pull request checklist

- [ ] Unit tests green (241+ as of 2026-08-19; AST suites may skip without Node — that's fine)
- [ ] `benchmark/run.py` still 100% on the corpus; `mutate.py` still catches all mutations
- [ ] New reach feature present in BOTH backends (or the asymmetry is impossible by construction)
- [ ] Both demo orgs re-scanned if a rule changed (HanseWatt stays clean; TechnoStore's findings accounted for)
- [ ] No fabricated numbers; new claims name their proof (`experiment:` / `platform-doc` / `reasoned`)
- [ ] Fingerprint meta-tests green if anything in the sealed set changed
- [ ] CLI output ASCII-only
- [ ] Known-gaps section (§9) updated in the same commit as the gap it describes
