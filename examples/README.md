# Two published measurements

These are the reports the analyzer wrote against two real orgs, kept here as evidence
rather than as samples: the file, not a picture of it, with the date it was produced and
the fingerprint that seals it.

| org | Index | fingerprint |
|---|---|---|
| TechnoStore — 113/113 Apex files pre-v67 | `6 proven (1 regulated) · 0 unproven boundaries · 1 unresolved` | `6b0359284da3` |
| HanseWatt — 182/219 pre-v67, yet all nine agent actions at v67 | `0 proven (0 regulated) · 0 unproven boundaries · 2 unresolved` | `d80158fbbaa8` |

Read them together. That is the pair the whole argument rests on: **you do not have to
modernise the whole org, only the part the agent touches** — and HanseWatt's report says
`0 proven` while refusing to call itself clean, because two of its operations could not be
resolved at all.

**They are not in `reports/`.** That folder belongs to whoever runs this: your own
measurement lands there and nothing else does, so you never have to work out which of nine
files is yours.

Both were produced under analyzer digest `f0f9842e7305`, which a fresh clone reproduces —
check it with `python -c "import sys;sys.path.insert(0,'blast_radius');from report import
analyzer_version;print(analyzer_version())"`. If it disagrees with the footers here, one of
us has a modified tool, and the report tells you which.
