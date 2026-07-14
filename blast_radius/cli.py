"""Agent Blast Radius - one command, any org.

Point it at an authenticated org + an agent, and it pulls the agent config,
Apex/Flow reach, the running user's permissions, the org's GDPR labels and
sharing models - all live - and writes the deterministic report.

    python blast_radius/cli.py --agent HealthRecord_Assistant --permission-set HR_Agent_Minimal
    python blast_radius/cli.py --agent My_Agent --running-user svc@acme.com --org acmeOrg

Requires the Salesforce CLI (`sf`) authenticated to the target org. No agent is
invoked; zero Flex Credits.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import org_loaders  # noqa: E402
from agent_analyzer import analyze_agent, parse_agent_config  # noqa: E402
from agent_metadata_loader import load_agent_config  # noqa: E402
from apex_introspect import parse_apex  # noqa: E402
from flow_introspect import parse_flow  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402
from report import escalation_gap, render_markdown, summarize_apex, summarize_flow  # noqa: E402
from report_html import render_html  # noqa: E402
from snapshot_loader import build_snapshot  # noqa: E402


def _retrieve(agent: str, target_org):
    cmd = f'sf project retrieve start --metadata "GenAiPlannerBundle:{agent}" --metadata "GenAiPlugin"'
    if target_org:
        cmd += f" --target-org {target_org}"
    subprocess.run(cmd, shell=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")


def _reached_objects(agent, source_root: str):
    objects = set()
    for action in agent.actions:
        if action.target_type == "apex":
            path = os.path.join(source_root, "classes", action.target + ".cls")
            if os.path.exists(path):
                objects.update(o.sobject for o in parse_apex(path).operations if o.sobject)
        elif action.target_type == "flow":
            path = os.path.join(source_root, "flows", action.target + ".flow-meta.xml")
            if os.path.exists(path):
                objects.update(a.sobject for a in parse_flow(path).accesses if a.sobject)
    return objects


def main():
    ap = argparse.ArgumentParser(description="Compute an Agentforce agent's blast radius.")
    ap.add_argument("--agent", required=True, help="GenAiPlannerBundle API name")
    ap.add_argument("--org", default=None, help="sf target org alias/username (default org if omitted)")
    ap.add_argument("--running-user", default=None, help="username to model as the running user")
    ap.add_argument("--permission-set", default=None, help="model the running user as this permission set")
    ap.add_argument("--source-root", default=os.path.join("force-app", "main", "default"))
    ap.add_argument("--channel", default="agent")
    ap.add_argument("--out", default=os.path.join("blast_radius", "report"))
    ap.add_argument("--no-retrieve", action="store_true", help="skip retrieving agent metadata")
    args = ap.parse_args()

    if not args.running_user and not args.permission_set:
        ap.error("provide --running-user or --permission-set")

    root = args.source_root
    if not args.no_retrieve:
        print("retrieving agent metadata ...")
        _retrieve(args.agent, args.org)

    print("resolving agent config ...")
    resolver = org_loaders.function_resolver(args.org)
    ru_label = args.running_user or f"(permission set: {args.permission_set})"
    cfg = load_agent_config(root, args.agent, running_user=ru_label,
                            channel=args.channel, resolver=resolver)
    agent = parse_agent_config(cfg)

    objects = _reached_objects(agent, root)
    print(f"objects reached: {sorted(objects) or '(none - opaque actions only)'}")

    print("loading classifications, sharing models, permissions ...")
    classification = org_loaders.classification(objects, args.org)
    sharing = org_loaders.sharing(objects, args.org)
    if args.permission_set:
        snapshot = org_loaders.snapshot_from_permset(args.permission_set, objects, args.org)
    else:
        snapshot = build_snapshot(args.running_user, sobjects=list(objects), channel=args.channel)
    perms = EffectivePermissions(snapshot)

    summaries = analyze_agent(agent, root, perms, classification, sharing)

    md = render_markdown(agent.name, agent.running_user, agent.channel, summaries)
    html = render_html(agent.name, agent.running_user, agent.channel, summaries)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    with open(args.out + ".html", "w", encoding="utf-8") as f:
        f.write(html)

    gap, gdpr = escalation_gap(summaries)
    print("\n" + "=" * 60)
    print(f"AGENT: {agent.name}   RUNNING USER: {agent.running_user}")
    print(f"ESCALATION GAP: {len(gap)} field(s), {len(gdpr)} GDPR-labelled")
    findings = [f for s in summaries for f in s.findings]
    for sev in ("ERROR", "WARN", "INFO"):
        n = sum(1 for f in findings if f.severity == sev)
        if n:
            print(f"  {sev}: {n}")
    print(f"reports written: {args.out}.md , {args.out}.html")
    print("=" * 60)


if __name__ == "__main__":
    main()
