# Running Agent Blast Radius against another org

A practical runbook for pointing the tool at an org you did not build — a
customer's sandbox, a partner's scratch org, a Salesforce engineer's demo org.

---

## 1. What the tool does to their org: nothing

This matters more than anything else in the conversation, so lead with it.

**The analysis is read-only.** It performs exactly three kinds of operation:

| operation | what it is |
|---|---|
| `sf data query` (SOQL / Tooling) | reads `ObjectPermissions`, `FieldPermissions`, `FieldDefinition.ComplianceGroup`, `EntityDefinition.InternalSharingModel`, `ApexTrigger`, `GenAiFunctionDefinition` |
| `sf project retrieve` | reads the agent's metadata and **only the Apex classes / Flows its actions actually invoke** — not the whole org |
| local file reads | parses the retrieved `.cls` / `.flow-meta.xml` / `.agent` on your machine |

**It never writes, deploys, or invokes anything.** No `sf project deploy`, no DML,
no agent conversation, **zero Agentforce Flex Credits**. `--include-counts` adds
`SELECT COUNT(Id)` queries — still read-only.

**No data leaves the machine it runs on.** The tool is a local CLI; the report is
written to local files. Nothing is uploaded anywhere.

If they ask *"what's the blast radius of your blast-radius tool?"* — that table is
the answer.

---

## 2. What you need from them

**A connected user.** That's it. But *which* user matters, and being straight about
this is what makes the result trustworthy:

- **Metadata read** (retrieve) and **Tooling API** access.
- **FLS on the fields you want classified.** `FieldDefinition` is itself
  FLS-gated: it only returns fields the querying identity can read. A field your
  analysis user cannot see is invisible to the scan — so a `0 GDPR findings`
  result from a narrow user is *not* proof of safety. The tool measures this
  honestly and prints **classification coverage %**, flagging every reachable
  field it could not see. Ideally the analysis user is a System Administrator, or
  has a broad read-only permission set.
- Nothing else. No admin *write* rights are needed.

**And, separately: the running user you want to model.** This is the identity the
agent runs as — the thing the whole report is a diff against. Give it as either:

```
--permission-set HR_Agent_Minimal      # model the agent's intended grant
--running-user  svc-agent@acme.com     # or model a real user
```

---

## 3. The run

```bash
# 0. one-time
npm install --prefix blast_radius        # the two parsers (Apex AST + Agent Script)

# 1. connect to their org
sf org login web --alias theirOrg

# 2. run it
python blast_radius/cli.py \
    --agent  <GenAiPlannerBundle API name> \
    --permission-set <the agent's permission set> \
    --org theirOrg \
    --include-counts \
    --fail-on ERROR
```

That single command retrieves the agent, resolves each action to its Apex class or
Flow, pulls **just those** sources, parses them on a real parse tree, loads the
running user's permissions and the org's own GDPR labels, and writes
`report.md` + `report.html`.

**If their agent is authored in Agent Script**, point at the `.agent` file instead
— this is the path that additionally proves the data → prompt chain (PS52x):

```bash
python blast_radius/cli.py \
    --agent-script force-app/main/default/aiAuthoringBundles/<Bundle>/<Bundle>.agent \
    --permission-set <permset> --org theirOrg --include-counts
```

Don't know the agent's API name? `sf data query --query "SELECT DeveloperName,
MasterLabel FROM BotDefinition" --target-org theirOrg`.

---

## 4. What to expect in an org you didn't build — honestly

Say these *before* you run, not after. They are the difference between a demo and
a sales pitch.

- **`ComplianceGroup` may be empty.** Most orgs never populate it. Then there is
  no GDPR intersection to make — but PS501 (record-scope expansion), PS502/PS503
  (field/write escalation), PS509 (trigger cascade), PS510 (Flow system mode) and
  PS511 (legacy API) still fire on execution semantics alone. And the coverage line
  tells them the truth: *"0 GDPR findings, because 0 fields are labelled."* That is
  itself a finding worth having.
- **Managed-package and standard actions are opaque.** `EmployeeCopilot__*`, an
  `externalService://` target, a managed class with no source — the tool reports
  **PS507**, an honest unknown. It never calls an unreadable action clean.
- **Unusual Apex will produce PS504.** Dynamic SOQL, a metadata-driven query, a
  reach it cannot determine — flagged as undetermined, never guessed.
- **Record counts.** `--include-counts` reports the agent's system-mode reach as a
  real `COUNT()`. The user-side number is only given when it is defensible (no
  object read → 0; public OWD or view-all → all). On a Private object it prints
  **`n/a — run as the user to measure`** rather than inventing a figure.
- **PS522 needs Agent Script.** The data → prompt chain does not survive
  compilation (measured: zero occurrences in the compiled metadata). On a classic
  Agent Builder agent you get the reach findings, not the prompt proof.

---

## 5. How to run the meeting

**Show yours first, then theirs.** It removes all risk from the first five minutes
and it makes the second five minutes credible.

1. **On my org (2 min).** A live agent authored in Agent Script, a v58
   `without sharing` action, a field labelled `PII;GDPR;HIPAA` that the running
   user has no FLS on. The report:

   > Escalation Gap: **1 field, 1 GDPR-labelled**
   > **PS522** — `HealthRecord__c.Diagnosis__c` is interpolated into the model's
   > prompt at **line 125**, and the running user has no FLS on it.
   > Traced: `Diagnosis__c → @outputs.summary → @variables.record_summary
   > (line 128) → prompt (line 125)`.

   Then show the *safe twin* of the same action (v67 + `WITH USER_MODE`) coming
   back clean — that is the part that proves it is not a `without sharing` grep.

2. **On their org (5 min).** They authorize a sandbox. `sf org login web`, one
   command, read-only, zero credits. Read the findings out loud, including the
   honest unknowns.

3. **The CI story (1 min).** `--fail-on ERROR` exits non-zero; the GitHub Action
   comments the Escalation Gap on the pull request and fails the build. The point
   is not the report — it is that a developer who adds an escalating action never
   gets it merged.

**If it finds nothing in their org**, that is a *good* outcome and you should say
so plainly: their actions enforce user mode end-to-end. Show them the coverage
line proving the scan could actually see the fields. A tool that only ever finds
problems is not a tool, it is a prop.

---

## 6. Prerequisites on your machine

- **Python 3.12+** — the analyzer.
- **Node 20+** — the two parsers (`npm install --prefix blast_radius`). Without
  it, Apex falls back to the regex extractor (less accurate, still honest) and the
  Agent Script path is unavailable. The run header always states which backend ran.
- **Salesforce CLI (`sf`)** — the data layer.
- A **DX project directory** (`sfdx-project.json`) to retrieve into.
