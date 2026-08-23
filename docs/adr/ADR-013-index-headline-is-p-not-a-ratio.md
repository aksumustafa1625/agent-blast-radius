# ADR-013 — The Index headline is P, not a ratio

**Status:** Accepted · 2026-08-19
**Supersedes nothing. Constrains:** `docs/AKSU_INDEX_SPEC.md` §1, §3, §8; `report_html.py`,
`report.py` (rendering only).

## Context

The Aksu Index had a prominence problem, not a definition problem. `CLAUDE.md` §0.1 recorded it:
in the HTML report the Index rendered as `<p class="sub">` — small subtitle text below the `<h1>` —
while the 64px `.gapnum` took the eye. A reader opening a report named after the Index could not
find the Index. The same held in the md report, where it sat as line 7 inside the ASCII block,
reading as one row of the reach summary.

Fixing that raised a second question, and the two are easy to conflate: **what is the headline
number?**

A ratio was proposed — `Effective Access Surface / Declared Access Surface`, rendered as a single
decimal (4.0, 2.1, 1.0), with 1.0 meaning the agent stays inside its running user. It reached a
draft public post before being caught. Its appeal is real: one number travels, it is comparable
across orgs of different sizes, and "Index" leads a reader to expect a scalar.

It is computable from quantities the tool already holds, because the spec's §3 concentric model
gives `outer = inner + gap`. On the two committed reports it would read:

| org | outer | gap | inner | ratio |
|---|---|---|---|---|
| TechnoStore | 8 | 6 | 2 | **4.0** |
| HanseWatt | 4 | 0 | 4 | **1.0** |

## Decision

**The headline is P — the count of fields proven reachable beyond the running user — rendered
large, first, and always with C, B and U beside it. No ratio is reported, quoted or displayed
anywhere in a report, and none is stored.**

*Precision, because the first draft of this line overstated it:* `_circle_svg()` does divide —
it holds a local `inner_n / outer_n` to size the concentric circles. That is drawing geometry,
never a figure the report prints, and the distinction is the whole point: a ratio may exist as
pixels, never as a number a reader could quote.

The Index band moves directly under the `<h1>`; `.gapnum` and the concentric circles stay, below
it, as explanation. Spec §3 is unchanged, so this ships under **v1.0** and the specification can be
published and frozen as written.

## Why the ratio was rejected

1. **It converts a false clean into a good score.** HanseWatt measures
   `0 proven · 0 unproven boundaries · 2 unresolved`, and the tool prints
   *"0 proven with unresolved reach is NOT clean — unknown never becomes clean"* about it. Its
   ratio is **1.0**: a perfect reading for an agent the analyzer explicitly refuses to call clean.
   The ratio has no term for U, so it cannot express the one thing §3 of `CLAUDE.md` exists to
   protect. This alone is disqualifying.
2. **It mixes proof levels.** `gap` is `P ∪ B`. Folding them into one scalar contradicts
   `CLAUDE.md` §6.1 — *"the quoted number may never mix them, because severity is the tool's proof
   claim"* — and spec §1, which forbids any form shorter than all four numbers.
3. **It is undefined where it matters most.** `inner = 0` — an agent reaching only fields its user
   cannot see — is a division by zero, and that is not a corner case: it is the narrowly
   permissioned service user, the worst real finding the tool can produce.
4. **It erases magnitude.** 2/1 and 200/100 both read 2.0. The most useful sentence this project
   produces (§6.4 — *modernise only the part the agent touches*) depends on the size of that part,
   which a ratio discards.
5. **P already travels.** "This agent's Aksu Index is 6" is a single number, quotable and
   actionable, and unlike 4.0 it names something a DPO can act on. The prominence problem never
   required a new metric — only bigger type.

## Consequences

- The band renders four numbers as one visual object. **C is rendered inside P**, never as a peer
  tile that could read as `P + C`.
- When `P = 0` and `U > 0`, the not-clean statement renders inside the band, adjacent to the zero,
  and may not be styled as a pass. This is the design's primary test case, not an edge case.
- Beneath the numbers sits the agent-versus-user reach comparison (what the code can reach, what
  this user can see, and the gap). It uses only measured quantities; where a user-side count is not
  computed, it is omitted rather than estimated.
- Because §3 is untouched, existing reports remain comparable and the fingerprint keeps its meaning.
- **If a ratio is ever wanted, it is a separate named figure, not the Index** — and it would need a
  defined answer for `inner = 0` and a rule keeping U visible beside it. Spec §8 would make it a new
  major version published side by side, never a silent redefinition.

## Note on how this was caught

The ratio was not proposed from the spec; it was invented by an assistant drafting a launch post,
phrased confidently, and would have been published as the metric's **first public reference** —
the moment §8 freezes the definition permanently. It was caught by reading the specification
instead of the draft, and confirmed by grepping: the word *ratio* appears zero times in
`AKSU_INDEX_SPEC.md`. The same discipline §2 of `CLAUDE.md` applies to platform claims applies to
claims about our own metric: **check it against the artifact, not against a confident sentence.**
