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
import pathlib
import re
import subprocess
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "blast_radius")
sys.path.insert(0, PKG)

BAR = "=" * 74

# What to call the interpreter when printing a command for someone to run. On
# Windows `python` may be the 0-byte Microsoft Store stub that sits on PATH by
# default, and `python3` is that stub even on a correct python.org install; the
# `py` launcher gets its own PATH entry regardless. Elsewhere `python` is often
# absent entirely - Debian and Ubuntu ship python3 and no python. Printing the
# wrong one hands the reader a command their own machine refuses.
PY = "py" if os.name == "nt" else "python3"

# Anomalies worth showing a reader who is debugging, kept rather than swallowed.
_DIAG: list[str] = []


def _sf_json(cmd: str) -> dict | None:
    """Run an sf command and return its JSON only if the CLI reports success.

    The process return code is deliberately not treated as authoritative: on Windows
    `sf` is a .cmd shim that exits 1 even on success - measured on this machine - so
    trusting it reports a working CLI as broken.

    Not authoritative is not the same as ignored, and the difference matters: an error
    from `sf` is *also* valid JSON, so "something parsed" would accept failures as
    results. The success signal is the CLI's own `status` field, and an anomalous
    return code is kept for diagnostics rather than discarded.
    """
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    try:
        d = json.loads(res.stdout)
    except (json.JSONDecodeError, TypeError):
        if res.returncode and (res.stderr or "").strip():
            _DIAG.append(f"{cmd.split(' --')[0]}: rc={res.returncode} {res.stderr.strip()[:160]}")
        return None
    if not isinstance(d, dict) or "status" not in d:
        return None                      # not the shape sf documents; treat as no answer
    if d.get("status") != 0:
        _DIAG.append(f"{cmd.split(' --')[0]}: status={d.get('status')} "
                     f"{str(d.get('message', ''))[:160]}")
        return None
    return d


def _query(soql: str, org: str) -> list[dict] | None:
    """Rows, or None when the org did not answer.

    The distinction is the whole point. Returning [] for both an empty result and
    a failed call made the caller print "this org has no Agentforce agents" for a
    dropped connection, an expired session, a permissions problem, and an org
    where Agentforce is simply not enabled. Four different situations, one
    confident wrong sentence, and the CLI's real message discarded on the way.

    The alias is quoted: an org alias may contain a space, and unquoted it split
    into two arguments and failed every query - surfacing, again, as "no agents".
    """
    d = _sf_json(f'sf data query --query "{soql}" --target-org "{org}" --json')
    if d is None:
        return None
    return ((d or {}).get("result") or {}).get("records") or []


def _resolve_bundle(bot_name: str, org: str) -> tuple[str | None, list[str]]:
    """Map a BotDefinition DeveloperName to the planner bundle the org actually has.

    These names are NOT interchangeable, and assuming they are is what made a
    first run against a stranger's org end in a traceback. Measured on a real
    org: BotDefinition `VS_Eichrecht` against bundles `VS_Eichrecht_v1`, `_v2`
    and `_v3` - while `VS_Phase0_Probe_Classic` carries no suffix at all. So all
    three shapes exist side by side and only the org can say which is which.

    Returns (chosen, all_candidates). Highest version wins, because a bundle is
    versioned upward and the newest is what the agent runs. Nothing is guessed
    when there is no candidate: the caller lists what the org does have.
    """
    d = _sf_json("sf org list metadata --metadata-type GenAiPlannerBundle "
                 f"--target-org \"{org}\" --json")
    names = [r.get("fullName") for r in ((d or {}).get("result") or [])
             if r.get("fullName")]
    if not names:
        return None, []                      # cannot list: let the retrieve try the raw name

    if bot_name in names:
        return bot_name, names

    versioned = []
    for n in names:
        m = re.fullmatch(rf"{re.escape(bot_name)}_v(\d+)", n)
        if m:
            versioned.append((int(m.group(1)), n))
    if versioned:
        return max(versioned)[1], names

    suffixed = [n for n in names if n.startswith(bot_name + "_")]
    if len(suffixed) == 1:
        return suffixed[0], names
    return None, names


def _fail(msg: str, *fix: str) -> int:
    print(f"  {msg}")
    if fix:
        print()
        for line in fix:
            print(f"      {line}")
    # Collected anomalies are printed here or they are not collected at all - a
    # decision that is recorded and never read is the no-op PS512 flags in other
    # people's code.
    if _DIAG:
        print()
        print("  What the CLI actually said:")
        for line in _DIAG:
            print(f"      {line}")
    print()
    return 2


def main() -> int:
    print()
    print(BAR)
    print("  AGENT BLAST RADIUS")
    print(BAR)
    print()

    # `--org` is the one argument worth taking. Everything else this script works
    # out for itself, but WHICH org is the one thing it cannot: a person whose
    # laptop blocks the browser login flow already has an alias authenticated and
    # no way to make it the default without changing their config. Refusing it
    # would also have made the published page wrong, since it recommends exactly
    # this.
    argv = sys.argv[1:]
    org_arg = None
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--org" and i + 1 < len(argv):
            org_arg = argv[i + 1]
            i += 2
            continue
        if argv[i].startswith("--org="):
            org_arg = argv[i].split("=", 1)[1]
            i += 1
            continue
        rest.append(argv[i])
        i += 1

    # Anything else is refused rather than ignored. Silently dropping a flag
    # someone typed produces a complete, confident report about something they
    # did not ask for, with nothing anywhere saying so.
    unknown = [a for a in rest if a != "--no-open"]
    if unknown:
        return _fail(f"measure.py does not take {' '.join(unknown)}.",
                     f"{PY} measure.py                  # this org's first agent",
                     f"{PY} measure.py --org <alias>    # a specific org",
                     "",
                     "For anything else - another agent, another running user -",
                     "the full CLI takes it:",
                     "",
                     f"{PY} blast_radius/cli.py --help")

    probe = subprocess.run("sf --version", shell=True, capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
    if "@salesforce/cli" not in (probe.stdout or "") + (probe.stderr or ""):
        return _fail("The Salesforce CLI is not on PATH.",
                     "npm install --global @salesforce/cli",
                     "sf org login web --set-default")

    d = _sf_json("sf org display --json" if not org_arg
                 else f'sf org display --target-org "{org_arg}" --json')
    user = ((d or {}).get("result") or {}).get("username")
    if not user:
        if org_arg:
            return _fail(f"No org is authenticated under the alias {org_arg}.",
                         "sf org list          # the aliases this machine has",
                         "sf org login web --set-default")
        return _fail("No default org is set.",
                     "sf org login web --set-default",
                     "",
                     "Already logged in to an org under an alias?",
                     "    python measure.py --org <alias>",
                     "",
                     "A sandbox or a free Developer Edition is fine.",
                     "Nothing is written to it.")
    org = org_arg or ((d or {}).get("result") or {}).get("alias") or user
    print(f"  Org: {org}")

    bots = _query("SELECT DeveloperName, MasterLabel, Type, BotUserId FROM BotDefinition "
                  "ORDER BY DeveloperName", org)
    # None is the query failing; [] is the org answering that it has none. Saying
    # "no agents" for the first is a diagnosis, and it is the wrong one - the
    # commonest cause is that BotDefinition does not exist because Agentforce was
    # never enabled, which is a thing to switch on rather than an absence.
    if bots is None:
        return _fail("Could not ask this org for its agents.",
                     f'sf org display --target-org "{org}"',
                     "",
                     "If BotDefinition is not available, Agentforce may not be",
                     "enabled in this org - that is a setting, not an absence.")
    # BotDefinition holds classic Einstein Bots alongside Agentforce agents. A
    # classic bot has no planner bundle, so measuring one ends in "no bundle
    # matching ..." - and if it merely sorted first alphabetically, an org with a
    # perfectly good Agentforce agent would be reported as having nothing to
    # measure. Skip them for selection rather than stopping on them.
    classic = [b for b in bots if (b.get("Type") or "") == "Bot"]
    bots = [b for b in bots if (b.get("Type") or "") != "Bot"]

    if not bots:
        if classic:
            print(f"  This org has {len(classic)} classic Einstein Bot(s) and no")
            print("  Agentforce agent. A classic bot has no planner bundle and no")
            print("  Apex action surface of the kind this measures.")
        else:
            print("  This org has no Agentforce agents, so there is nothing to measure.")
        print()
        print("  The 28-case corpus needs no org at all, if you would rather see")
        print("  the shape of the measurement first:")
        print("      https://github.com/aksumustafa1625/agent-authority-benchmark")
        print()
        return 1

    if classic:
        print(f"  Skipping {len(classic)} classic Einstein Bot(s) - not Agentforce.")

    if len(bots) > 1:
        print(f"  Agents: {len(bots)}")
        for i, b in enumerate(bots, 1):
            print(f"      {i}. {b['DeveloperName']}")
        print()
        # The BUNDLE name, not this list, is what --agent takes, and they differ
        # (VS_Eichrecht is VS_Eichrecht_v3 on disk). Printing agent names beside
        # a flag that rejects them sends the reader into an error.
        print("  Measuring the first. To pick another, list the planner bundles")
        print(f"  with:  sf org list metadata --metadata-type GenAiPlannerBundle "
              f'--target-org "{org}"')
        print("  and pass one to blast_radius/cli.py with --agent.")

    bot = bots[0]
    bot_name = bot["DeveloperName"]
    kind = bot.get("Type") or ""

    # The agent's name and its planner bundle's name are different things, and
    # the CLI needs the second. Ask the org rather than assume they match.
    agent, candidates = _resolve_bundle(bot_name, org)
    if agent is None and candidates:
        print()
        print(f"  The org has no planner bundle matching '{bot_name}'.")
        print("  What it does have:")
        print()
        for c in candidates:
            print(f"      {c}")
        print()
        print("  Pick one and pass it explicitly:")
        print()
        print(f"      {PY} blast_radius/cli.py --agent <name> --org {org} "
              f"--running-user <username>")
        print()
        return 2
    agent = agent or bot_name

    # Agentforce has two running-user models and only one of them has a single
    # running user. An EMPLOYEE agent (InternalCopilot) runs in the context of
    # whoever is logged in, so "the agent's own running user" is not a fact about
    # it - it is a category error, and measuring against a BotUserId that happens
    # to be populated would aim a confident number at the wrong identity.
    #
    # Measured 2026-08-29 on both demo orgs: Type=ExternalCopilot, BotUserId set.
    # What an InternalCopilot carries in BotUserId is NOT measured here, which is
    # exactly why this branches on the type rather than on whether the field is
    # populated.
    employee_agent = kind == "InternalCopilot"


    # Three outcomes, not two. `rows is None` is the lookup FAILING; `[]` is the
    # org answering that the id resolves to nothing. Collapsing them into "no
    # BotUserId" printed a falsehood - "this agent has no BotUserId of its own" -
    # and then measured a real agent against an arbitrary permission set, in the
    # tool's ordinary confident voice, with a number at the end of it.
    running_user = None
    lookup_failed = False
    if bot.get("BotUserId") and not employee_agent:
        rows = _query(f"SELECT Username FROM User WHERE Id = '{bot['BotUserId']}'", org)
        if rows is None:
            lookup_failed = True
        elif rows:
            running_user = rows[0]["Username"]
        else:
            lookup_failed = True          # the id is set but resolves to no row

    print()
    print(f"  Agent:        {bot_name}")
    if agent != bot_name:
        print(f"  Planner bundle: {agent}   (the org's name for it)")
    if kind:
        print(f"  Agent type:   {kind}")
    # BotDefinition.Type has four values and only three have ever been measured.
    # An orchestrator is treated as a service agent here, which may well be right -
    # but no org available to this project has one, so saying nothing would let a
    # reader assume the type was considered and cleared. It was not.
    if kind == "AgentforceOrchestrator":
        print("                An orchestrator has never been measured by this tool.")
        print("                It is handled as a service agent below; if that is")
        print("                wrong, the run will say so rather than guess.")
        print("                Agent-to-agent delegation itself IS analysed - see")
        print("                PS515 and docs/LIMITATIONS.md.")

    if employee_agent:
        print()
        print("  This is an employee agent. It runs in the context of each logged-in")
        print("  user, so there is no single running user to measure it against -")
        print("  every employee is a different one. Pick a representative identity:")
        print()
        # One line, no backslash continuation. A POSIX continuation is a parser
        # error in Windows PowerShell, and this tool exists mostly for people on
        # Windows - printing a command their own shell refuses is the same defect
        # that shipped '&&' in the published quickstart.
        print(f"      {PY} blast_radius/cli.py --agent {agent} "
              f"--running-user <username> --org {org}")
        print()
        return 2

    if running_user:
        print(f"  Running user: {running_user}   (the agent's own, from BotUserId)")
        who = ["--running-user", running_user]
    else:
        # Type != 'Group' excludes Permission Set Group AGGREGATES. They satisfy
        # IsCustom = true, and the one Agentforce installs sorts first
        # alphabetically, so the "custom set an admin made" this was meant to find
        # was in fact the same Salesforce-shipped boilerplate in every org tested.
        sets = _query("SELECT Name FROM PermissionSet WHERE IsOwnedByProfile = false "
                      "AND IsCustom = true AND Type != 'Group' ORDER BY Name", org)
        if sets is None:
            return _fail("Could not ask this org for its permission sets.",
                         f'sf org display --target-org "{org}"')
        if not sets:
            return _fail("This agent has no running user set, and the org has no "
                         "custom permission set to model one with.",
                         f"{PY} blast_radius/cli.py --agent {agent} "
                         f"--running-user <username> --org {org}")
        chosen = sets[0]["Name"]
        if lookup_failed:
            print(f"  Running user: COULD NOT BE RESOLVED.")
            print(f"                This agent's BotUserId is {bot['BotUserId']}, but")
            print( "                the lookup for it did not come back.")
        else:
            print("  Running user: this agent has no BotUserId of its own.")
        print(f"                Modelling a hypothetical user holding only")
        print(f"                {chosen}")
        # Say that it was picked arbitrarily. Without this the number reads as a
        # measurement of somebody, and it is a measurement of nobody: the set was
        # chosen because it sorts first, out of however many the org has.
        print(f"                - chosen only because it sorts first of "
              f"{len(sets)} custom set(s).")
        print( "                It is NOT this agent's identity. For a real number:")
        print(f"                    {PY} blast_radius/cli.py --agent {agent} "
              f"--running-user <username> --org {org}")
        who = ["--permission-set", chosen]
    print()
    print("  Reading metadata. No agent is invoked and no Flex Credits are spent.")
    print()

    # Named for the PAIR, not the org. The Index is defined for one agent and
    # one running user, and an org holds several agents - VoltStreamDev has
    # three. A per-org filename would let the second agent's report overwrite
    # the first's, which is the defect this replaced one level up: the CLI's
    # default put every run in blast_radius/report.md, inside the source package,
    # overwritten by whatever ran next.
    #
    # The bundle name is used rather than the agent's label because a label
    # carries spaces ("VoltStream Eichrecht") and a bundle name is already a
    # safe API name.
    def _slug(x):
        return re.sub(r"[^A-Za-z0-9_.-]", "_", x)
    # The org prefix exists to keep two orgs' reports apart. When the bundle name
    # already begins with the org's - which is common, because people name agents
    # after the company - prefixing produces
    # TechnoStore_TechnoStore_Revenue_Assistant_v1, which says the same word twice
    # and reads as a bug. Drop the prefix when it is already there.
    stem = _slug(agent)
    if not stem.lower().startswith(_slug(org).lower()):
        stem = f"{_slug(org)}_{stem}"
    out = os.path.join("reports", stem)
    cmd = [sys.executable, os.path.join(PKG, "cli.py"),
           "--agent", agent, *who, "--org", org, "--out", out]
    # The child writes straight to the terminal while this process's prints sit
    # in a buffer, so anything that pipes the output - a log, a CI job - gets the
    # header AFTER the result it introduces. Interactive runs hide it; the one
    # place it shows is the one place someone reads the transcript later.
    sys.stdout.flush()
    rc = subprocess.run(cmd, cwd=HERE).returncode

    html = os.path.join(HERE, out + ".html")
    print()
    print(BAR)

    # The child's exit code is the only thing that knows whether a report exists.
    # This block used to print "Your report: ..." unconditionally, so a run that
    # ended in a traceback still signed off with a filename and the reassurance
    # that it was safely on disk. That is the §7 failure exactly - a summary line
    # that reports success it did not verify - and it is worse here than in the
    # analyzer, because this is the first thing a new reader ever sees the tool say.
    if rc != 0 or not os.path.exists(html):
        print("  The run did not finish, so there is no report.")
        print()
        print("  The traceback above is the whole of what went wrong - nothing is")
        print("  hidden and nothing was sent anywhere. If it is not obvious, paste it")
        print("  into an issue and it will be enough to reproduce:")
        print("      https://github.com/aksumustafa1625/agent-blast-radius/issues")
        if _DIAG:
            print()
            print("  What the CLI said along the way:")
            for line in _DIAG:
                print(f"      {line}")
        print(BAR)
        print()
        return rc or 1

    # Absolute, because the path is only relative to the repository and the
    # reader may not be standing in it. And the org is named: a report is about
    # one org and one agent, and "which org was that" should not need recall.
    print(f"  Your report ({org} / {agent}):")
    print(f"      {os.path.join(HERE, out)}.html")
    print(f"      {os.path.join(HERE, out)}.md")
    print("  It is yours and it stays here - nothing was uploaded.")

    # Open it. The alternative is telling someone to navigate to the reports
    # folder and pick the right file out of it - a file-manager errand standing
    # between a person and the thing they just waited two minutes for. Failure
    # to open is not failure to measure, so it never changes the exit code: the
    # path is printed either way, and --no-open exists for CI, where launching a
    # browser would be wrong behaviour rather than a missing nicety.
    if "--no-open" not in sys.argv:
        try:
            # pathlib, not string surgery. `"file:///" + path` is right on Windows,
            # where the path starts with a drive letter, and wrong everywhere else:
            # a POSIX path already begins with a slash, so it produced
            # file:////home/... - four slashes and a malformed URI. as_uri() knows
            # which platform it is on, which the concatenation could not.
            webbrowser.open(pathlib.Path(html).as_uri())
            print("  Opening it in your browser now.")
        except Exception as e:                       # noqa: BLE001 - any failure is cosmetic
            _DIAG.append(f"could not open the report automatically: {e}")
            print("  (Could not open a browser here - the path above is the file.)")

    print()
    print("  The same measurement again, whenever you want it:")
    print()
    # One line and --out included. The backslash continuation this used to print
    # is a parser error in Windows PowerShell, and without --out the repeat run
    # wrote into the source package instead of beside the report it is repeating.
    print(f"      {PY} blast_radius/cli.py --agent {agent} "
          f"{who[0]} {who[1]} --org {org} --out {out}")
    print(BAR)
    print()
    return rc


if __name__ == "__main__":
    sys.exit(main())
