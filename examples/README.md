# Two published measurements

These are the reports the analyzer wrote against two real orgs, kept here as evidence
rather than as samples: the file, not a picture of it, with the date it was produced and
the fingerprint that seals it.

| org | Index | fingerprint |
|---|---|---|
| TechnoStore — 113/113 Apex files pre-v67 | `6 proven (1 regulated) · 0 unproven boundaries · 1 unresolved` | `da237145496c` |
| HanseWatt — 182/219 pre-v67, yet all nine agent actions at v67 | `0 proven (0 regulated) · 0 unproven boundaries · 7 unresolved` | `422e6dc9f85d` |

Read them together. That is the pair the whole argument rests on: **you do not have to
modernise the whole org, only the part the agent touches** — and HanseWatt's report says
`0 proven` while refusing to call itself clean, because seven of its operations could not
be resolved at all.

**They are not in `reports/`.** That folder belongs to whoever runs this: your own
measurement lands there and nothing else does, so you never have to work out which of nine
files is yours.

Both were produced under analyzer digest `257203d65b68`, which a fresh clone reproduces —
check it with:

```
python -c "import sys;sys.path.insert(0,'blast_radius');from report import analyzer_version;print(analyzer_version())"
```

If it disagrees with the footers here, one of us has a modified tool, and the report tells
you which.

## Which command produced them, and why yours will look different

Both were run against a **permission set**, not against a person. On Windows use `py`; on
macOS and Linux use `python3`:

```
py blast_radius/cli.py --agent TechnoStore_Revenue_Assistant_v1 --permission-set TechnoStore_Revenue_Assistant2098228049_Permissions --org TechnoStore --include-counts
py blast_radius/cli.py --agent HW_Energy_Agent --permission-set HW_ServiceAgent --org hansewatt --include-counts
```

`measure.py` does **not** default to that. It asks the org for the agent's own
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
model (`fp:da237145496c`) and under the agent's real running user (`fp:c4ac1f440182`)
returns the **same four numbers**: `P:6 C:1 B:0 U:1`. Two independent models of who the
agent is, one Index. **This is one agent in one org** — it is a data point about this
report, not a general claim that the two models agree.

## Why these numbers are not the ones published on 30 August

Both reports were regenerated on 2026-08-31 against a corrected analyzer, and one of the
two Indexes moved. It is worth saying exactly which, and why, rather than quietly swapping
the files.

**TechnoStore did not move.** `P:6 C:1 B:0 U:1` before and after, every finding identical,
byte-for-byte apart from the seal. Only the fingerprint changed, from `6b0359284da3` — which
is the fingerprint doing its job: the tool changed, so the seal must, even though the
measurement did not.

**HanseWatt moved, from `U:2` to `U:7`.** Its nine actions hold almost no SOQL of their own;
the queries live in a service layer — `HWBillingService`, `HWCustomerService`,
`HWKnowledgeService` and four more. The analyzer followed delegated classes only if they
happened to be on disk, and it never retrieved them, so on this repository they were absent
and the follow skipped them **in silence**. The report then said less was unresolved than
truly was. Those seven classes are now retrieved and read, and the honest count is seven.

`P` stayed at `0` through both builds, so the claim the pair exists to make is unchanged.
What changed is the size of the admission beside it — which is the direction this tool is
supposed to fail in, and the reason a `0` here has never been allowed to read as clean.
