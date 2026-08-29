# Agent Authority Benchmark v1

**Why:** "307 tests green" is not an accuracy claim. A test suite proves the code does
what its author expected. This measures how often that expectation is *right* — per
rule, against labels written to be independent of the implementation.

An external technical review named this the single highest-leverage next step, and it
is the only thing that turns *deterministic* into *deterministic **and** correct*.

```bash
python blast_radius/benchmark/run.py                    # per-rule precision / recall
python blast_radius/benchmark/mutate.py                 # does the corpus detect a broken analyzer?
python blast_radius/benchmark/oracle.py --org <alias>   # let the ORG judge the analyzer
```
`run.py` and `mutate.py` run in CI and fail the build, so an accuracy regression is caught
like a broken test. `oracle.py` needs a live org, so it runs on demand.

## The runtime oracle — the org decides, not the author

The weakness of any hand-labelled benchmark is that its labels come from the same mind
as the implementation. `oracle.py` removes that: for every case carrying a `runtime`
shape it deploys the same Apex into a real org, runs it **as the modelled user**, and
asks the only question that settles it — *does that field actually come back?*

**The generated test asserts the analyzer's own prediction.** So a failing test is not a
broken test; it is the org saying the analyzer is wrong. That is the point.

```
RUNTIME ORACLE - the analyzer predicts, the org judges
cases with a runtime shape: 10   org: HospitalOrg

CASE                                    ORG SAYS    LABEL
prec-v58-without-plain                  agrees      experiment:oracle
prec-v67-without-plain                  agrees      experiment:oracle
prec-v58-without-usermode-clause        agrees      experiment:oracle
prec-v67-no-declaration                 agrees      experiment:oracle
prec-v58-with-sharing-plain             agrees      experiment:oracle
prec-v67-without-systemmode-clause      agrees      experiment:oracle
sanitizer-readable-used-caps-severity   agrees      experiment:oracle
sanitizer-discarded-is-a-bug            agrees      experiment:oracle
sosl-returning-gdpr-v58                 agrees      experiment:oracle
sosl-returning-gdpr-v67                 agrees      experiment:oracle
```
*(Output of the FIRST oracle run, kept as the shape of the report; the corpus now
carries 21 runtime shapes and stores the earned label as `experiment:oracle` — the
string the oracle prints and the string in `corpus.py` are the same on purpose, so
a grep for either finds both.)*

It has already paid for itself twice.

**`prec-v67-without-systemmode-clause`** (id corrected 2026-08-19; it was always an api=67.0 case) was labelled `platform-doc` — believed from the
documentation, never measured. The oracle settled it live, so that label is now **earned**.

**PS512 rests entirely on two claims about the platform**, and a rule is only as good as
its premises. So the oracle settles both rather than trusting a docs reading: that
`stripInaccessible(READABLE)` really removes a field the user cannot see (the org says
**BLOCKED** — so capping severity at WARN is conservative, not wrong), and that
*discarding* its decision really leaves the original readable (the org says **READ** — so
the no-op bug PS512 reports is real). A case may supply its own `body` for exactly this:
when the thing being measured is not the query but what happens to the data afterwards.

It needs an org carrying the Milestone 0 fixture (`Blast_Test__c` with
`Customer_IBAN__c`). The test builds its own throwaway user and permission set — object
read, and deliberately **no** field permission on the regulated field — so the field is out of
the user's reach unless execution mode puts it back, which is exactly the thing under test.

**Adding a `runtime` shape to a `reasoned` case is worth more than ten new reasoned cases.**

## Current result

```
cases: 28   passed: 28   failed: 0
RULE      TP  FP  FN   PRECISION   RECALL
PS501      8   0   0      100.0%   100.0%
PS502      1   0   0      100.0%   100.0%
PS503      2   0   0      100.0%   100.0%
PS504      2   0   0      100.0%   100.0%
PS506      7   0   0      100.0%   100.0%
PS512      2   0   0      100.0%   100.0%
PS514      5   0   0      100.0%   100.0%

mutation score: 8/8 caught
```
*(run.py + mutate.py output, 2026-08-19. The numbers live in the tool — re-run
before quoting; this block is a mirror, not the source.)*

## How to read that honestly

**100% is not the headline. These two things are:**

**1. Label strength.** A benchmark is only as good as where its ground truth comes from.
Every case carries a `truth` field:

| `truth` | count | what it's worth |
|---|---|---|
| `experiment:*` | 21 | **Measured in a real org** — Milestone 0 (`experiment:E*`), or settled by `oracle.py` (`experiment:oracle`). The strong labels. |
| `platform-doc` | 3 | Documented Salesforce semantics, not measured here. |
| `reasoned` | 4 | The author's reasoning. **Proves consistency, not correctness** — it shares a mind with the implementation. |

*(Counted from `corpus.py` on 2026-08-19 and printed by every `run.py` run; an earlier
revision of this table said 11 / 6 / 6 of 23 — two generations of numbers in one file,
which is exactly the staleness this project keeps paying for.)*

21 of 28 labels are org-measured; the 7 that are not include six no oracle can ever
settle (see "Honest limits" below). A score carried by `reasoned` labels mostly proves
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

- **28 cases, not 100+.** The review asked for 100–200. This is a working harness with a
  real corpus, not the finished benchmark.
- **The mutations are also the author's.** 8/8 measures sensitivity to the breaks I
  thought of.
- **21 of 28 cases have a runtime shape**, and the org agrees on all 21. Of the other 7,
  **six can never have one** - PS504's "we do not know" and PS514's "we flag what we do
  not follow" assert what the ANALYZER must report, not what the platform does, and an
  org cannot measure the absence of our knowledge. That is a limit of the method, not a
  to-do; counting them as gaps would overstate what is missing.
- **The oracle needs a specific fixture** (`Blast_Test__c`, `Blast_Event__e`, and the
  muting group), so it runs on demand rather than in CI.

## What v2 needs, in order

Items 1 and 2 are **done**, and both are struck through rather than deleted: what they
turned into is the useful part.

1. ~~**More runtime shapes.**~~ **Done.** `oracle.py` settles **21 of 28**, and the org
   agrees on all 21. It grew a **negative control** (grant FLS on one field, read it
   under the same enforcement that blocks the other - without it, "everything is
   BLOCKED" could just mean a broken fixture), per-case `perms`, and a third axis
   (`kind:"record"`). It has **caught a real false positive** in this tool. The list
   used to say "the other 13 have no shape"; six of those can never have one, and the
   corpus docstring says which.
2. ~~**Systematic sfge differential.**~~ **Done** (`sfge_diff.py`). The design point is
   the refereeing: it runs on exactly the org-adjudicated cases and generates the SAME
   statements the org executed, so a disagreement has an answer instead of being two
   engines shouting. **sfge 8/21 wrong, this tool 0/21** (2/21 on sfge's own binary
   scale - reported because publishing only the flattering scale is selective
   reporting).
3. **Breadth** - Flow, Agent Script, polymorphic fields, managed-package actions. (PSG
   and muting are covered and measured: E8/E9.)
4. **Report `unknown` rate**, not just precision/recall: the share of cases where the
   tool honestly says "I can't tell" is a product quality metric in its own right.
5. **More cases.** 28 is a working harness, not the 100-200 a reviewer asked for. But
   note what the last stretch actually taught: **every case added to settle a belief
   found a bug in the thing it was testing.** Depth per case has been worth more than
   count.

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


## sfge_diff.py - Salesforce's own Graph Engine, refereed by the org

    python blast_radius/benchmark/sfge_diff.py          # needs no org; sfge is local
    python blast_radius/benchmark/sfge_diff.py --keep   # keep the generated Apex

A differential on its own concludes "they disagree", which settles nothing. So this
runs on exactly the cases carrying a `runtime` shape - the ones oracle.py has already
had the ORG adjudicate - and generates the SAME statements the org executed
(`oracle.case_body`), so sfge, this tool, and the org all describe one program.

Two sfge rules map onto ours: `ApexFlsViolation` -> PS502/503/506 (FLS/CRUD), and
`DatabaseOperationsMustUseWithSharing` -> PS501 (record). Only the FLS/CRUD axis is
SCORED, because only it has a runtime column; the record axis is printed. Scoring a
column nobody refereed is how a differential flatters whoever wrote it.

The score is printed on BOTH scales: ours (WARN = "a boundary I could not prove", so
it is not an assertion) and sfge's binary one (any finding = an assertion). It holds
either way, and reporting only the flattering number would be the same sin as any
other selective reporting.
