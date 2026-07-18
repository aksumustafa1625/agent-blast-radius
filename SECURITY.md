# Security Model

What Agent Blast Radius touches, what it never touches, and what its output
should be trusted to mean. Written to be honest about boundaries — this
tool's own §9 discipline ("say the gaps out loud") applies to its security
posture too.

## What the tool does to an org

**Read-only, zero-credit, zero-invocation.** Every org interaction is a
metadata retrieve or a SOQL/Tooling query through the locally installed
`sf` CLI:

- Agent metadata (GenAiPlannerBundle / BotDefinition), Apex class bodies,
  Flow XML, prompt templates
- Permissions: profile, permission sets, PSG aggregates (muting included),
  ObjectPermissions/FieldPermissions, OWD, "god-mode" grants
- `FieldDefinition.ComplianceGroup` labels (bounded per EntityDefinition)
- Optional live `COUNT()` per reached object (`--include-counts`)

It never performs DML, never deploys (the benchmark's runtime oracle is a
separate, deliberate tool for fixture orgs), and **never invokes an agent**
(ADR-009) — a scan cannot trigger agent behaviour, spend Flex Credits, or
generate model traffic in the scanned org.

## Credentials

None stored. The tool shells out to `sf` and inherits the operator's own
authenticated session. No token, auth URL, or session id ever appears in
reports, fixtures, or this repo. CI's live-scan job authenticates via a
repository-secret JWT and skips cleanly (job-level) when no secret exists.

## Data handling

- **Nothing leaves the machine.** Reports are local files; there is no
  telemetry, no upload, no external service in the analysis path.
- Reports contain org-derived metadata: object/field names, permission
  facts, classification labels, record counts, and code excerpts in
  finding evidence. **Treat a report as sensitive as the org it describes**
  — it is a map of where data over-exposure is possible.
- Demo data in this repo (HealthRecord etc.) is fictional; the four scanned
  orgs are developer orgs.

## Analysis-identity honesty (a real trust boundary)

The scan sees the org **through the analysis identity's own permissions**:
`FieldDefinition` is FLS-gated, so a narrow identity silently misses
classification labels (measured — E4). The tool handles this by **sealing
what the identity could see into the fingerprint** (`coverage`, ADR-007)
and disclosing it, rather than pretending completeness. Reviewers should
scan with an identity that can read the metadata being judged.

## Output integrity

- **Determinism**: same inputs + same tool → byte-identical md/html
  (`verify_deterministic.py`; proven live). Tampering is detectable by
  re-running.
- **The fingerprint seals the tool AND the inputs** (ADR-007): analyzer
  source hash, parser version, backend, per-action apiVersion, permission
  snapshot, coverage. A verdict is only reproducible against the tool that
  made it, and the footer says so.
- Live COUNT figures are explicitly outside the seal (ADR-008) — they are a
  measurement of the org at run time.

## What this tool's output is NOT

- **Not a certificate.** It is an agent-scoped security review accelerator
  producing evidence for a DPIA/security review (the legal filing layer is
  the sibling project, Aktenlage).
- **Not a claim of complete coverage.** The open edges are enumerated, not
  implied away: Flow/process/off-platform event subscribers (PS514), formula
  field inputs (PS516/ADR-011), polymorphic lookups (ADR-012),
  managed-package internals, Knowledge/Data Cloud retrieval. Restriction
  rules are not modelled, so **the escalation gap is a LOWER bound** — the
  tool may think the user sees more than they do, never less.

## Reporting a vulnerability

If you find a way to make this tool produce a **false clean** — a scan that
should fire and doesn't, a fingerprint that matches across a semantic
change, a determinism break — please open a GitHub issue or contact the
maintainer. A silent false-clean is the highest-severity bug this project
recognises; it outranks everything, including crashes.
