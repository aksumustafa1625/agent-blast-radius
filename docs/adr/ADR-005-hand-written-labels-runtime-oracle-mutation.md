# ADR-005: Hand-written benchmark labels, a runtime oracle, and a mutation gate

## Status

**Accepted**

## Date

2026-07-18 (benchmark v1 + oracle + mutation in effect; recorded retrospectively)

## Author

Mustafa Aksu

## Context

"216 tests green" proves the code does what its author expected — it says
nothing about whether the expectation is *right*. An accuracy benchmark
needs ground truth, and the tempting shortcut is to generate expected
verdicts from the resolution law itself. That is a mirror, not an oracle:
it would agree with every bug the law shares. A second risk compounds it —
a benchmark written next to the code may pass simply because it encodes the
same assumptions, and nothing would ever notice.

## Decision

Three mechanisms, layered:

1. **Labels are hand-written, never generated from the law under test**, and
   every case names where its truth comes from (`experiment:` /
   `platform-doc` / `reasoned`). The label-strength ratio (currently
   21/3/4) is printed on every run — it is the benchmark's real quality
   metric.
2. **A runtime oracle** (`benchmark/oracle.py`): each case with a runtime
   shape is deployed as real Apex and executed **as the modelled user**; the
   org's outcome is asserted against *the analyzer's own prediction*. A red
   test means the analyzer is wrong — the only ground truth that does not
   share a mind with the implementation. It has a negative control
   (verified to fail), and it has already caught a real false positive
   (stripInaccessible).
3. **A mutation gate** (`benchmark/mutate.py`): break the analyzer on
   purpose, one semantic at a time; the corpus must notice. An escape is a
   finding. 8/8 caught — including "ignore apiVersion", the exact mistake
   sfge makes.

Benchmark + mutation run in CI and fail the build.

## Consequences

### Positive

- Accuracy regressions are caught like broken tests, and the accuracy claim
  ("100% precision/recall on this corpus") is reproducible by anyone.
- Moving one case from `reasoned` to `experiment:` is worth more than ten
  new reasoned cases, and the printed ratio keeps that incentive visible.
- The oracle settles reviewer disputes mechanically: deploy, run, read.

### Negative / Trade-offs

- Not every case can have a shape: PS504/PS514 assert what *the analyzer
  reports*, not what the platform does — an org cannot measure the absence
  of our knowledge. The corpus docstring records which claims are
  oracle-settleable so the gap is not overstated.
- The mutations are the author's; 5 labels still prove consistency, not
  correctness. Stated in §8 rather than hidden.
- Oracle runs need a real org and deploy rights — deliberately not a CI
  requirement (the `analyze` job stays org-free).

## Alternatives Considered

### Alternative A — generate expectations from the resolution law

Rejected: a mirror. Every shared bug scores 100%.

### Alternative B — more unit tests instead of a benchmark

Rejected: unit tests and the corpus answer different questions (does the
code match intent vs. does intent match the platform). The PS511 block
unreachable-code bug passed unit tests and was caught by a live run.

## References

- Source: CLAUDE.md §8 (proof surface), benchmark/README.md, §7 (mirror-not-oracle rule)
- Related ADRs: ADR-001 (same philosophy, semantics layer), ADR-006 (what deliberately stays OUT of CI)
