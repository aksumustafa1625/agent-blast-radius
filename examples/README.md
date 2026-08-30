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

## Which command produced them, and why yours will look different

Both were run against a **permission set**, not against a person:

```
python blast_radius/cli.py --agent TechnoStore_Revenue_Assistant_v1 \
       --permission-set TechnoStore_Revenue_Assistant2098228049_Permissions --org TechnoStore
python blast_radius/cli.py --agent HW_ServiceAgent_v1 \
       --permission-set HW_ServiceAgent --org HanseWatt
```

`python measure.py` does **not** default to that. It asks the org for the agent's own
`BotDefinition.BotUserId` and models the identity Salesforce actually runs the agent as —
a fact about the agent rather than a hypothesis about a person. So your report's identity
line will read like a username, while these two read
`(hypothetical grant model - permission set: ...)`. Neither is a better number; they answer
slightly different questions, and the report says which one it answered.

The fingerprints differ for the same reason. It seals *what the analysis identity could
see*, so changing the identity changes the seal — that is the mechanism working, not
drifting.

One thing fell out of running both against the same agent, and it is worth recording
because it was not the point of the exercise. TechnoStore measured under the permission-set
model (`fp:6b0359284da3`) and under the agent's real running user (`fp:5d5631253985`)
returns the **same four numbers**: `P:6 C:1 B:0 U:1`. Two independent models of who the
agent is, one Index. **This is one agent in one org** — it is a data point about this
report, not a general claim that the two models agree.
