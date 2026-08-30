# FACTS — the one place a published number comes from

Every figure this project states in public — the README, both websites, a talk, a
post, a CV — is quoted from here. Nowhere else.

**Why this file exists.** This project's whole argument is that a number which
travels without its derivation drifts. Lighthouse changed how a score was computed
while keeping its name, and roughly half the web's scores moved five points or more
in a day with nothing changed on any site. We then did the domestic version of the
same thing: the sfge differential circulated as `8/21` in one document and `7/19`
in another for weeks; the test count appeared as 241, 279, 303 and 307 in different
files at the same time; the C bucket printed as `GDPR` in a report while both
websites said `regulated`. Five separate reviewers repeated one of those figures
back to us, which felt like confirmation and was not — the source was still one
document, and it was wrong.

So: one file, every number measured rather than remembered, and the command that
reproduces it printed beside it. A figure with no command in this table has no
business in a sentence.

**Measured 2026-08-29; the analyzer digest and both report fingerprints re-measured
2026-08-30.** Re-run the commands before quoting; if a number here disagrees with a
document, this file is right and the document is stale.

**The digest changed on 2026-08-30 and no code did.** `52c669ea07a9` was published here,
on the specification page and inside both reports, and it was the digest of a working tree
where two analysis sources sat CRLF while the repository and every clone held them LF.
`analyzer_version()` hashes bytes, so the number that identified the tool existed on one
machine only. A reader running the tool from a fresh clone got `f0f9842e7305` in the footer
and reported the mismatch. The measurement never moved - both Index results are unchanged -
but every fingerprint sealed with the old digest was unreproducible, which is the one thing
this file exists to prevent. `test_digest_reproducible.py` now fails if any analysis source
carries a CR.

---

## The analyzer

| figure | value | reproduce |
|---|---:|---|
| Unit tests | **307** | `python -m unittest discover -s blast_radius -p "test_*.py"` |
| …of which skip in a fresh clone (no `npm install`) | **32** | same command, before `npm install` |
| Benchmark cases passed | **28 / 28** | `python blast_radius/benchmark/run.py` |
| Mutation score | **8 / 8** | `python blast_radius/benchmark/mutate.py` |
| Architecture decision records | **13** | `ls docs/adr/ADR-*.md` |
| In-org experiments | **E1 – E16** | `CLAUDE.md` §2 |
| Analyzer digest | **`f0f9842e7305`** | `python -c "import sys;sys.path.insert(0,'blast_radius');from report import analyzer_version;print(analyzer_version()[:12])"` |

The skip count is measured in a fresh clone at a **short path**. On Windows a
checkout nested past roughly 240 characters makes five more tests skip, because
`os.path.exists` fails on the long path rather than because anything is wrong.

## The corpus

| figure | value | reproduce |
|---|---:|---|
| Corpus version | **1.1** | `public-benchmark/corpus.json` → `version` |
| Cases adjudicated by a live org | **21** | `org_adjudicated_cases` |
| Cases no org can settle | **7** | `not_adjudicable_cases` |
| Total published cases | **28** | the two above |
| Measured on | **Salesforce Summer '26** | `measured_on` |

## The sfge differential

| figure | value |
|---|---:|
| sfge contradicts the org | **8 / 21** |
| Agent Blast Radius contradicts the org | **0 / 21** |
| …on sfge's own binary scale | **2 / 21** |

Reproduce: `python blast_radius/benchmark/sfge_diff.py` — needs Java and Salesforce
Code Analyzer. Last measured **2026-08-29** against **Code Analyzer 5.15.0**,
corpus **v1.1**.

**Never quote this without the corpus version and the date.** It was `7/19` in nine
documents for weeks: `runtime_cases()` returns every case carrying a runtime shape,
which is 21, and the documents were quoting a different set. The tool also printed
a hardcoded "the 6 are not one thing" twenty lines under its own computed 8. Both
are fixed; the discipline that failed is the one this file exists to enforce.

Composition of the 8: **4 apiVersion** (v67 read ×2, v67 record, v67 write) ·
**1 SOSL** · **1 platform-event publish** · **2 sanitizer**.

**State its status in the same breath:** sfge is `(Developer Preview)` in Code
Analyzer v5 — a differential against a preview engine is a weaker claim than
against a GA one, and a reviewer will say so first if we do not.

## The two published reports

| org | Index | report fingerprint |
|---|---|---|
| TechnoStore | see `reports/TechnoStore_AksuIndex.md` | printed in the report |
| HanseWatt | see `reports/HanseWatt_AksuIndex.md` | printed in the report |

Both carry their own canonical result string. Quote the string, not a number lifted
out of it — and never quote `proven` alone while `unresolved` is greater than zero,
which the specification defines as a violation.

## Calibration figures used in strategy documents

| figure | value | status |
|---|---:|---|
| Most-starred **independent** Salesforce security tool (`NetSPI/ForceHound`) | **48** | verified 2026-08-29 via the GitHub API |
| `SalesforceAIResearch/agentforce-adlc` | **101** | verified 2026-08-29 — Salesforce's own, which is why the row above says *independent* |

The unqualified claim "the most-starred Salesforce security tool has 48 stars" is
**wrong** and must not be repeated: a Salesforce-published repository in the same
space has more than twice that. The qualifier is the claim.

## Figures deliberately NOT recorded here

These circulated in strategy research and are **not** verified from a primary
source. They may be directionally right; none of them may be published as a number.

- **664×** — the attribution-payload spread across seven specifications. A
  correlation over n=7, not a causal finding, and re-counted by nobody outside this
  project. Use the mechanism in planning; never put the multiplier in a sentence.
- **300:1** — OpenSSF Scorecard versus the Best Practices Badge. The two programmes
  have different denominators and different user behaviour.
- **"SquireX — 61+ SAST rules"** and **"NTT, 340,000 repositories, 17.5%"** — both
  appeared in an external review; neither could be found at any source.
- **"57 adversarial payloads"** attributed to `agentforce-adlc` — not found in the
  repository. What *is* verified: seven security categories, an OWASP LLM Top 10
  assessment, and an A–F letter grade.
- **Apex Hours subscriber count** — measured between 108k and 119k depending on the
  source; "122k" appears in older notes and is not confirmed.
