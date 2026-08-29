# -*- coding: utf-8 -*-
"""One command, no arguments, no prior knowledge: measure an agent in this org.

    python measure.py

The analyzer needs an agent's API name and a running user. Neither is something
anyone knows by heart, so a README opening with

    python blast_radius/cli.py --agent <PlannerBundle> --permission-set <PermSet>

hands a stranger two placeholders and no way to fill them. That gap is the whole
distance between reading about this tool and running it.

This file closes it by asking the org instead of asking the reader: the default
org, its agents, and - the part that removes the last question - each agent's OWN
running user, which is `BotDefinition.BotUserId` and is therefore a fact rather
than a guess. Modelling the agent against the identity Salesforce actually runs it
as is also the only default that means anything; a permission set the reader
picked from a list is a hypothesis about a person who may not exist.

It writes nothing to the org, invokes no agent and spends no Flex Credits. Every
number still comes from cli.py, unchanged - this only works out its arguments.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "blast_radius")
sys.path.insert(0, PKG)

BAR = "=" * 74


def _sf_json(cmd: str) -> dict | None:
    """Run an sf command and return its JSON, or None.

    The return code is deliberately ignored: on Windows `sf` is a .cmd shim that
    exits 1 even on success - measured on this machine - so trusting it reports a
    working CLI as broken. Whether JSON came back is the fact that matters.
    """
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    try:
        d = json.loads(res.stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    return d if d.get("status") == 0 else None


def _query(soql: str, org: str) -> list[dict]:
    d = _sf_json(f'sf data query --query "{soql}" --target-org {org} --json')
    return ((d or {}).get("result") or {}).get("records") or []


def _fail(msg: str, *fix: str) -> int:
    print(f"  {msg}")
    if fix:
        print()
        for line in fix:
            print(f"      {line}")
    print()
    return 2


def main() -> int:
    print()
    print(BAR)
    print("  AGENT BLAST RADIUS")
    print(BAR)
    print()

    probe = subprocess.run("sf --version", shell=True, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    if "@salesforce/cli" not in (probe.stdout or "") + (probe.stderr or ""):
        return _fail("The Salesforce CLI is not on PATH.",
                     "npm install --global @salesforce/cli",
                     "sf org login web --set-default")

    d = _sf_json("sf org display --json")
    user = ((d or {}).get("result") or {}).get("username")
    if not user:
        return _fail("No default org is set.",
                     "sf org login web --set-default",
                     "",
                     "A sandbox or a free Developer Edition is fine.",
                     "Nothing is written to it.")
    org = ((d or {}).get("result") or {}).get("alias") or user
    print(f"  Org: {org}")

    bots = _query("SELECT DeveloperName, MasterLabel, BotUserId FROM BotDefinition "
                  "ORDER BY DeveloperName", org)
    if not bots:
        print("  This org has no Agentforce agents, so there is nothing to measure.")
        print()
        print("  The 28-case corpus needs no org at all, if you would rather see")
        print("  the shape of the measurement first:")
        print("      https://github.com/aksumustafa1625/agent-authority-benchmark")
        print()
        return 1

    if len(bots) > 1:
        print(f"  Agents: {len(bots)}")
        for i, b in enumerate(bots, 1):
            print(f"      {i}. {b['DeveloperName']}")
        print()
        print(f"  Measuring the first. To pick another, pass --agent <name> to")
        print(f"  blast_radius/cli.py.")

    bot = bots[0]
    agent = bot["DeveloperName"]

    running_user = None
    if bot.get("BotUserId"):
        rows = _query(f"SELECT Username FROM User WHERE Id = '{bot['BotUserId']}'", org)
        if rows:
            running_user = rows[0]["Username"]

    print()
    print(f"  Agent:        {agent}")
    if running_user:
        print(f"  Running user: {running_user}   (the agent's own, from BotUserId)")
        who = ["--running-user", running_user]
    else:
        sets = _query("SELECT Name FROM PermissionSet WHERE IsOwnedByProfile = false "
                      "AND IsCustom = true ORDER BY Name LIMIT 1", org)
        if not sets:
            return _fail("This agent has no running user set, and the org has no "
                         "custom permission set to model one with.",
                         "python blast_radius/cli.py --agent " + agent +
                         " --running-user <username>")
        print(f"  Running user: modelled as permission set {sets[0]['Name']}")
        print("                (this agent has no BotUserId of its own)")
        who = ["--permission-set", sets[0]["Name"]]
    print()
    print("  Reading metadata. No agent is invoked and no Flex Credits are spent.")
    print()

    cmd = [sys.executable, os.path.join(PKG, "cli.py"),
           "--agent", agent, *who, "--org", org]
    rc = subprocess.run(cmd, cwd=HERE).returncode

    print()
    print(BAR)
    print("  The same measurement again, whenever you want it:")
    print()
    print(f"      python blast_radius/cli.py --agent {agent} \\")
    print(f"             {who[0]} {who[1]} --org {org}")
    print(BAR)
    print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
