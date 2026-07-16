# Agent Authority Benchmark v1

**Why:** "140 tests green" is not an accuracy claim. A test suite proves the code does
what its author expected. This measures how often that expectation is *right* — per
rule, against labels written to be independent of the implementation.

An external technical review named this the single highest-leverage next step, and it
is the only thing that turns *deterministic* into *deterministic **and** correct*.

```bash
python blast_radius/benchmark/run.py       # per-rule precision / recall
python blast_radius/benchmark/mutate.py    # does the corpus detect a broken analyzer?
```
Both run in CI and fail the build, so an accuracy regression is caught like a broken test.

## Current result

```
cases: 23   passed: 23   failed: 0
RULE      TP  FP  FN   PRECISION   RECALL
PS501      7   0   0      100.0%   100.0%
PS502      1   0   0      100.0%   100.0%
PS503      1   0   0      100.0%   100.0%
PS504      2   0   0      100.0%   100.0%
PS506      7   0   0      100.0%   100.0%
PS512      2   0   0      100.0%   100.0%
PS514      3   0   0      100.0%   100.0%

mutation score: 8/8 caught
```

## How to read that honestly

**100% is not the headline. These two things are:**

**1. Label strength.** A benchmark is only as good as where its ground truth comes from.
Every case carries a `truth` field:

| `truth` | count | what it's worth |
|---|---|---|
| `experiment:EN` | 6 | **Measured in a real org** (Milestone 0). The strong labels. |
| `platform-doc` | 10 | Documented Salesforce semantics, not measured here. |
| `reasoned` | 7 | The author's reasoning. **Proves consistency, not correctness** — it shares a mind with the implementation. |

Only 6 of 23 labels are org-measured. A score carried by `reasoned` labels mostly proves
the analyzer agrees with its author, which is worth very little. That is why the runner
prints this table under the numbers rather than hiding it.

**2. Mutation score — the corpus's own test.** A benchmark that passes on day one may
just be agreeing with the code next to it. So `mutate.py` breaks the analyzer on purpose,
one semantic at a time, and checks the benchmark notices:

- `caught` — the corpus constrains that semantic.
- `ESCAPED` — the analyzer was broken and the benchmark still passed. **That is a blind
  spot in the corpus, and it is the real output of the file.** An escape is a finding.

8/8 caught today, including *"ignore apiVersion (treat every class as v58)"* — the exact
false positive Salesforce's own Graph Engine makes on v67 plain SOQL (see Appendix AD of
the review brief).

## Honest limits of v1

- **23 cases, not 100+.** The review asked for 100–200. This is a working harness with a
  real corpus, not the finished benchmark.
- **The mutations are also the author's.** 8/8 measures sensitivity to the breaks I
  thought of.
- **No runtime oracle yet.** The strongest possible label is "we ran it in an org and
  measured the outcome" — only 6 cases have that. The Milestone 0 experiments are the
  template for adding more.
- **Only the single sfge probe** (Appendix AD) so far, not a systematic differential.

## What v2 needs, in order

1. **Runtime oracle** — extend the E1–E7 pattern: deploy each fixture, execute as the
   modelled user, record what actually happened. Every case moved from `reasoned` to
   `experiment:` is worth more than ten new `reasoned` cases.
2. **Systematic sfge differential** — run both engines over the whole corpus and triage
   every disagreement. Each one teaches something about one engine or the other.
3. **Breadth** — Flow, Agent Script, relationship/polymorphic fields, PSG/muting,
   managed-package actions, async chains.
4. **Report `unknown` rate**, not just precision/recall: the share of cases where the
   tool honestly says "I can't tell" is a product quality metric in its own right.

## Adding a case

```python
dict(id="prec-v67-without-plain", api=67.0, apex=_cls(_READ, "without"),
     expect=set(),                       # the exact graded rules that must fire
     truth="experiment:E2,E2b",          # WHERE the label comes from - be honest
     why="Same `without sharing` source at v67 is SAFE: E2 measured v67=0 records, "
         "E2b measured the field read BLOCKED. Version-blind flagging here is wrong.")
```

`expect_severity={"PS506": "WARN"}` grades the confidence claim separately from the
finding itself — severity in this tool means *proof level*, so it is worth grading.

Ungraded rules (`GRADED` in `corpus.py`) are ignored: PS511 is legacy-API inventory and
PS507/PS508 are honest-unknown markers, so counting them would flatter the score.
