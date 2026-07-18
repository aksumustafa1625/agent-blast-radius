# ADR-009: Zero credits — the agent is never invoked, and one unmeasurable cell stays `None`

## Status

**Accepted**

## Date

2026-07-18 (founding constraint; recorded retrospectively)

## Author

Mustafa Aksu

## Context

Invoking an Agentforce agent consumes Flex Credits, and a security tool that
costs credits per scan will not be run on every commit — it will be run once
a quarter, which is to say it will not be run. The tool's entire positioning
("static, zero-credit, runs in CI, fails the build") depends on never
calling the agent. But the constraint has a price, and it surfaces at one
specific point: the entry-point matrix. A declaration-less pre-v67 invocable
inherits its *caller's* sharing context (E2/E10) — and the agent's own entry
point (an invocable with NO calling Apex class) cannot be measured without
either invoking the agent (credits) or authenticating as the fixture user.
A Flow proxy would measure Flow→invocable and drag in the Flow's own
`runInMode` — answering a question nobody asked.

## Decision

The agent is **never** invoked. All facts come from metadata, source,
permissions, labels, and zero-credit SOQL. Where that leaves a semantic
genuinely unmeasurable — `enforces_sharing` for a declaration-less pre-v67
class at the agent's own entry point — the answer stays **`None`
(undetermined), reported as such**, rather than being guessed or measured
through a proxy that changes the question.

## Consequences

### Positive

- The cost model enables the use case: every-commit scans, CI gates,
  scanning orgs you'd never get invoke rights on (the four-real-orgs proof
  surface exists because scans were free).
- The unmeasured cell is *stated* (CLAUDE.md §9.4), which converts a silent
  blind spot into a documented boundary with a known price of closure.
- "No data leaves the machine / no agent behaviour is triggered" is a real
  security property for orgs under review.

### Negative / Trade-offs

- One cell of the entry-point matrix stays open indefinitely; reviewers ask,
  and the answer is this ADR plus E10's three-way control experiment (which
  closed every cell a caller CAN reach).
- Behavioral questions are permanently out of scope — that is Prüfstand's
  half of the system, by design (the two tools bound an agent from both
  sides).

## Alternatives Considered

### Alternative A — invoke the agent once per scan for ground truth

Rejected: breaks the cost model AND the trust model (a scanner that
triggers agent behaviour in a production org is a different risk class).

### Alternative B — measure the open cell via a Flow proxy

Rejected: measures Flow→invocable, which has its own `runInMode` semantics —
the result would be attributed to a path the agent does not take.

### Alternative C — authenticate as the fixture user to run the invocable directly

Rejected for the tool (fine for the oracle's controlled fixtures): scans of
foreign orgs cannot assume user credentials, and the tool's claims must not
depend on a privilege most users won't have.

## References

- Source: CLAUDE.md §1 (positioning), §9.4 (entry-point matrix), MILESTONE_0 E10
- Related ADRs: ADR-002 (`None` semantics), ADR-005 (the oracle runs as the modelled user — in ITS fixtures, where credentials are by construction)
