# Launch checklist — Tuesday 1 September 2026

Open this file at **11:25**. Work down it. Do not skip a line because it "must be fine".

Three verification failures happened in one evening this week, all of the same shape —
**the check passed while the thing was broken**: a `git push -q` that failed silently, a
`/spec/v1.0` that returned 200 and rendered nothing, and a `grep` whose pattern could not
match a rule spanning two lines. A fourth was found by a reviewer, in the audit that was
supposed to be the careful one.

So the standing question on every line below: **is this check looking at the thing itself,
or at a proxy for it?**

The script at the bottom does the mechanical half. It cannot do the half that needs eyes.

---

## 11:25 — before anything is public

- [ ] Working tree clean in all three repos: `agent-blast-radius`,
      `agentblastradius-landing`, `aksuindex-landing`
- [ ] `python -m unittest discover -s blast_radius -p "test_*.py"` → **OK**
- [ ] `python blast_radius/benchmark/run.py` → **28/28**
- [ ] `git config user.email` in `agent-blast-radius` → the **noreply** address,
      not the personal one. *(This was wrong two days ago and put the personal address
      into every new commit.)*

## 11:30 — the click that everything else multiplies against

- [ ] **Make `agent-blast-radius` public.**
- [ ] Create and push the tag the landing page tells people to clone:
      ```
      git tag -a v1.0.0 -m "First public release"
      git push origin v1.0.0
      ```
      The page says `--branch v1.0.0`. If the tag does not exist, **every visitor's first
      command fails.** This is the single highest-consequence line on this page.
- [ ] Pin three on the profile — analyzer · benchmark · profile README.
      The API cannot do this; it is three clicks in the UI.

## 12:00 — be the first stranger

In a **clean directory**, run the landing page's commands **verbatim**. No fix that is not
in the documentation. Whatever breaks here is what a stranger hits.

```
git clone --branch v1.0.0 --depth 1 https://github.com/aksumustafa1625/agent-blast-radius
cd agent-blast-radius
python measure.py
```

- [ ] The clone succeeds **at the tag**
- [ ] `measure.py` runs with no arguments and prints an Index line
- [ ] The elapsed time is still in the neighbourhood of the **62 seconds** the page claims.
      If it is materially different, change the page — the number is a measurement, not a
      slogan.

## 12:30 — the eyes-only pass

`curl` cannot do any of these. Open a browser.

- [ ] `agentblastradius.com/en` — click **`#reports`**. Does the page actually scroll?
- [ ] Both report links open, and the report **renders** — not merely returns 200
- [ ] Read one report's Index line with your eyes: four numbers, then
      `AKSU:1.0/…/fp:…`, then the specification URL, and **the link is readable** against
      the background. *(It was invisible until Friday.)*
- [ ] `aksuindex.com/spec/v1.0` — styled, not Times New Roman. *(It rendered unstyled for
      days while returning 200.)*
- [ ] The GitHub link on the landing page resolves — in an **incognito window**, so you are
      not seeing it as its owner
- [ ] The profile README renders on the profile page itself

## 12:50 — the last read-through

- [ ] The post contains none of the banned phrases (see below)
- [ ] The post names **Aksu Index** and **Agent Blast Radius**, and opens from the Index
- [ ] Every Index in the post carries **all four numbers and the fingerprint**
- [ ] The post does **not** mention the sfge differential

## 13:00 — publish

- [ ] Post
- [ ] Personal messages to 3–5 named people. A human sentence, not a link. Something like:
      *"You work next to this — same Apex, v58 returns 5 rows, v67 returns 0. Thirty
      seconds: [table]."*
- [ ] Do **not** submit it to Hacker News yourself

## Evening

- [ ] GitHub → Insights → Traffic. **Screenshot it** — the window is 14 days and the data
      evaporates.
- [ ] Note the numbers in `FACTS.md`. The metric is **clones and issues**, not stars.

## Within 48 hours

- [ ] Apex Hours form

---

## Banned phrases

Not style preferences. Each one is either unmeasured, refuted, or reserved.

| never write | why |
|---|---|
| "the world's first" | unmeasured, and Appendix D says the landscape could not be surveyed well enough to claim it |
| "your GDPR solution" | the tool reads whatever `ComplianceGroup` labels **your admins** applied — CCPA, HIPAA and internal policy use the same mechanism |
| "guarantees" / "certifies" | it is explicitly not a certificate |
| "detects leaks" | it measures **reach**, not exfiltration |
| "industry standard" | not mine to declare. Say **open measurement specification** and **reference implementation** |
| "664×" · "300:1" · "57 payloads" | `FACTS.md` rejects all three as unsourced |
| "machine vector" | it is a canonical **result string**; a CVSS vector carries inputs, this carries output |
| "v67 triggers run in user mode" | E13 measured **object CRUD**, E15 the **record axis**. FLS is unmeasured — see `docs/E19_PROTOCOL.md` |
| "8–0 against Salesforce's own tool" | the differential is not the headline, and 2 of the 8 are a severity-discipline difference |

---

## The mechanical half

Run this at **11:35**, after the repo is public and the tag is pushed. It checks what a
script can check. It is not a substitute for 12:30.

```bash
#!/usr/bin/env bash
# docs/LAUNCH_CHECKLIST.md — the automatable half
R=https://github.com/aksumustafa1625/agent-blast-radius
ok(){ printf "  %-52s %s\n" "$1" "$2"; }

ok "repo public"        "$(curl -s -o /dev/null -w '%{http_code}' $R)"           # want 200
ok "tag v1.0.0 exists"  "$(git ls-remote --tags $R v1.0.0 | wc -l)"              # want 1
ok "benchmark public"   "$(curl -s -o /dev/null -w '%{http_code}' https://github.com/aksumustafa1625/agent-authority-benchmark)"
ok "profile README"     "$(curl -s -o /dev/null -w '%{http_code}' https://raw.githubusercontent.com/aksumustafa1625/aksumustafa1625/main/README.md)"

H=$(curl -sL https://agentblastradius.com/en)
ok "site: clone command" "$(echo "$H" | grep -c 'git clone --branch v1.0.0')"
ok "site: canonical str" "$(echo "$H" | grep -c 'AKSU:1.0/P:6/C:1/B:0/U:1/fp:da237145496c')"
ok "site: spec URL"      "$(echo "$H" | grep -c 'aksuindex.com/spec/v1.0')"
ok "site: #reports id"   "$(echo "$H" | grep -c 'id=\"reports\"')"

S=$(curl -sL https://aksuindex.com/spec/v1.0)
ok "spec: stylesheet"    "$(echo "$S" | grep -c 'rel=\"stylesheet\"')"           # want >=1
ok "spec: current digest" "$(echo "$S" | grep -c '257203d65b68')"
ok "spec: stale digests"  "$(echo "$S" | grep -cE 'd3a0cb4d683c|52c669ea07a9')"   # want 0

for u in technostore hansewatt; do
  P=$(curl -sL https://agentblastradius.com/reports/$u-aksu-index.html)
  ok "report $u: canonical string" "$(echo "$P" | grep -c 'AKSU:1.0/')"
  ok "report $u: link is styled"   "$(echo "$P" | grep -c 'abr a{color')"
done

# In a clean directory, from the tag, exactly as the page instructs.
T=$(mktemp -d) && git clone -q --branch v1.0.0 --depth 1 $R "$T" \
  && ok "fresh clone at tag" "ok" || ok "fresh clone at tag" "FAILED"
```

**A zero where a one belongs, or a one where a zero belongs, stops the launch.** Not because
the number matters — because it means something upstream is not what this file thinks it is,
and 13:00 is the worst hour to discover that.
