# sfdx-blast-radius

A Salesforce CLI plugin that computes the **blast radius** of an Agentforce
agent — its real data-access surface at the execution-semantics layer — and
flags where that surface exceeds the running user or reaches GDPR/PII-labelled
fields. Static, zero-credit, no agent invocation.

The command is a thin Node/oclif wrapper over the Python engine in
[`../blast_radius/`](../blast_radius/README.md); it shells out to
`blast_radius/cli.py`.

## Requirements

- Salesforce CLI (`sf`)
- Python 3.10+ on `PATH` (override with `BLAST_RADIUS_PYTHON`)
- Run from the root of a Salesforce DX project (so `force-app` is reachable)

## Install (local / development)

```bash
cd sfdx-blast-radius
npm install
cd ..
sf plugins link ./sfdx-blast-radius
```

`sf plugins` should then list `sfdx-blast-radius (link)`.

## Usage

```bash
# model the running user as a permission set
sf blast-radius report --agent HealthRecord_Assistant --permission-set HR_Agent_Minimal

# or as a real user, against a specific org
sf blast-radius report --agent My_Agent --running-user svc@acme.com --target-org acmeOrg
```

| Flag | Meaning |
|---|---|
| `-a, --agent` | GenAiPlannerBundle API name (required) |
| `-o, --target-org` | Org alias/username (default org if omitted) |
| `-u, --running-user` | Username to model as the running user |
| `-p, --permission-set` | Model the running user as this permission set |
| `--source-root` | Path to `force-app/main/default` |
| `--no-retrieve` | Skip retrieving agent metadata (use local) |
| `--out` | Output path prefix for the `.md` / `.html` reports |

## What it does

1. Retrieves the agent's GenAi metadata (planner → topics → actions).
2. Resolves each action to its Apex class / Flow (via the Tooling API).
3. Reads the running user's effective CRUD/FLS, the org's `ComplianceGroup`
   labels, and object sharing models — all live.
4. Diffs the code's resolved reach against the user and writes a deterministic
   Markdown + HTML report headed by the **Escalation Gap**.

## Auditing another org

```bash
sf org login web --alias customerOrg
sf org assign permset --name <broad_FLS_permset> --target-org customerOrg   # so classification is visible
sf blast-radius report --agent <Agent_API_Name> --permission-set <RunningUser_PermSet> --target-org customerOrg
```
