"""Deterministic report renderer + Escalation Gap headline (Milestone 4).

Turns authority findings into the artifact: one number (the Escalation Gap -
fields the agent's code can reach beyond the running user, with the GDPR subset
called out), a reach summary, and the findings grouped by severity. The report
is fingerprint-bound (a sha256 over the analysed inputs) so it is byte
reproducible and STALE-guarded - regenerate when the fingerprint changes.

No wall-clock is read here (determinism): the caller passes `generated`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import List, Optional

_SEV_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}


@dataclass
class ActionSummary:
    name: str
    kind: str                       # apex | flow | standard
    api_version: Optional[float]
    system_mode: bool               # runs in system context (escalation-capable)
    objects: List[str]
    fields: List[str]
    findings: List = field(default_factory=list)


def summarize_flow(reach, findings, name=None) -> ActionSummary:
    objs = sorted({a.sobject for a in reach.accesses if a.sobject})
    flds = sorted({f"{a.sobject}.{fl}" for a in reach.accesses if a.sobject for fl in a.fields})
    return ActionSummary(name or reach.name, "flow", None, reach.runs_in_system_context, objs, flds, findings)


def summarize_apex(reach, findings, name=None) -> ActionSummary:
    objs = sorted({o.sobject for o in reach.operations if o.sobject})
    flds = sorted({f"{o.sobject}.{fl}" for o in reach.operations if o.sobject for fl in o.fields})
    system = any(o.resolved.is_escalation_capable for o in reach.operations)
    return ActionSummary(name or reach.class_name, "apex", reach.api_version, system, objs, flds, findings)


def _field_of(where: str) -> str:
    return where.split("-> ")[-1].strip()


def escalation_gap(actions: List[ActionSummary]) -> tuple[set, set]:
    """(fields reachable beyond the user, GDPR-labelled subset)."""
    gap, gdpr = set(), set()
    for a in actions:
        for f in a.findings:
            if f.rule in ("PS502", "PS506"):
                gap.add(_field_of(f.where))
                if f.rule == "PS506":
                    gdpr.add(_field_of(f.where))
    return gap, gdpr


def fingerprint(agent: str, running_user: str, channel: Optional[str],
                actions: List[ActionSummary]) -> str:
    payload = {
        "agent": agent, "user": running_user, "channel": channel,
        "actions": [
            {
                "name": a.name, "kind": a.kind, "api": a.api_version,
                "system": a.system_mode,
                "objects": sorted(a.objects), "fields": sorted(a.fields),
                "findings": sorted(f"{f.rule}:{f.where}" for f in a.findings),
            }
            for a in sorted(actions, key=lambda x: x.name)
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def render_markdown(agent: str, running_user: str, channel: Optional[str],
                    actions: List[ActionSummary], generated: str = "deterministic") -> str:
    fp = fingerprint(agent, running_user, channel, actions)
    gap, gdpr = escalation_gap(actions)

    objects = sorted({o for a in actions for o in a.objects})
    fields = sorted({f for a in actions for f in a.fields})
    system_actions = [a for a in actions if a.system_mode]
    legacy = [a for a in actions if a.api_version is not None and a.api_version < 67]

    all_findings = [(a, f) for a in actions for f in a.findings]
    all_findings.sort(key=lambda af: (_SEV_ORDER.get(af[1].severity, 9), af[1].rule, af[1].where))

    L: List[str] = []
    L.append("```")
    L.append(f"AGENT BLAST RADIUS REPORT - {agent}")
    L.append(f"Running user: {running_user}   (channel: {channel or 'n/a'})")
    L.append(f"Config fingerprint: {fp}      Generated: {generated}")
    L.append("=" * 64)
    L.append("")
    L.append(f"ESCALATION GAP ......... {len(gap)} fields  /  {len(gdpr)} GDPR-labelled"
             + ("   <==" if gap else ""))
    L.append("")
    L.append("REACH SUMMARY")
    L.append(f"  Actions analysed ....... {len(actions)}")
    L.append(f"  Objects reachable ...... {len(objects)}")
    L.append(f"  Fields reachable ....... {len(fields)}")
    L.append(f"  System-mode actions .... {len(system_actions)} / {len(actions)}")
    L.append(f"  Legacy API (< v67) ..... {len(legacy)} / {len(actions)}")
    L.append("```")
    L.append("")

    if gap:
        L.append(f"> **{len(gap)} fields can be reached beyond the running user"
                 f"{f' - {len(gdpr)} of them GDPR-labelled' if gdpr else ''}.**")
        L.append("")

    by_sev = {"ERROR": [], "WARN": [], "INFO": []}
    for a, f in all_findings:
        by_sev.setdefault(f.severity, []).append((a, f))

    for sev in ("ERROR", "WARN", "INFO"):
        items = by_sev.get(sev) or []
        if not items:
            continue
        L.append(f"## {sev} - {len(items)} finding(s)")
        L.append("")
        for a, f in items:
            L.append(f"- **[{f.rule}] {f.where}**")
            L.append(f"  - {f.message}")
            L.append(f"  - _Why:_ {f.why}")
            L.append(f"  - _Fix:_ {f.fix}")
        L.append("")

    if not all_findings:
        L.append("No authority findings. All analysed actions enforce user mode "
                 "end-to-end for the fields and objects they reach.")
        L.append("")

    L.append("---")
    L.append("Produced by static analysis. No agent was invoked. 0 Flex Credits.")
    L.append(f"Bound to fingerprint `{fp}`; regenerate if agent config, any analysed "
             "Apex/Flow, or permission metadata changes.")
    return "\n".join(L)


def render_svg(agent: str, user_field_count: int, agent_field_count: int,
               gdpr_gap: int) -> str:
    """Two concentric circles: inner = user reach, outer = agent reach, red ring."""
    gap = max(agent_field_count - user_field_count, 0)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">'
        f'<circle cx="180" cy="180" r="150" fill="#e5484d" fill-opacity="0.15" '
        f'stroke="#e5484d" stroke-width="2"/>'
        f'<circle cx="180" cy="180" r="80" fill="#3b82f6" fill-opacity="0.25" '
        f'stroke="#3b82f6" stroke-width="2"/>'
        f'<text x="180" y="176" text-anchor="middle" font-family="sans-serif" '
        f'font-size="16" fill="#3b82f6">user sees</text>'
        f'<text x="180" y="196" text-anchor="middle" font-family="sans-serif" '
        f'font-size="16" fill="#3b82f6">{user_field_count} fields</text>'
        f'<text x="180" y="70" text-anchor="middle" font-family="sans-serif" '
        f'font-size="15" fill="#e5484d">agent reaches {agent_field_count}</text>'
        f'<text x="180" y="330" text-anchor="middle" font-family="sans-serif" '
        f'font-size="15" fill="#e5484d">Escalation Gap: {gap} ({gdpr_gap} GDPR)</text>'
        f'</svg>'
    )
