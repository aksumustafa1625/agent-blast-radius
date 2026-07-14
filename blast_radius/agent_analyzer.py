"""Agent-level orchestration (Milestone 5).

Chains the whole thing: an agent config (its topics -> actions -> invocation
targets) is walked, each action's Apex class or Flow is located in the source
tree, introspected, and analysed against the running user's permissions and the
org's GDPR labels. The result is the set of ActionSummaries the report renders -
the blast radius of a WHOLE agent, not a single class.

The agent config is a normalized dict (see fixtures/agent_hw_energy.json). In a
live run it comes from a Metadata API retrieve of GenAiPlanner(Bundle) /
GenAiPlugin / GenAiFunction; that retrieval is a thin adapter (like
snapshot_loader), kept out of here so this stays pure and testable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

from apex_introspect import parse_apex
from authority_analyzer import Finding, analyze_apex, analyze_flow
from flow_introspect import parse_flow
from report import ActionSummary, summarize_apex, summarize_flow


@dataclass
class AgentAction:
    name: str
    target_type: str        # apex | flow | standard
    target: str


@dataclass
class AgentConfig:
    name: str
    running_user: str
    channel: Optional[str]
    actions: List[AgentAction]


def parse_agent_config(config: dict) -> AgentConfig:
    actions: List[AgentAction] = []
    for topic in config.get("topics", []):
        for a in topic.get("actions", []):
            actions.append(AgentAction(
                name=a["name"],
                target_type=a.get("invocationTargetType", "standard").lower(),
                target=a.get("invocationTarget", ""),
            ))
    return AgentConfig(
        name=config["agent"],
        running_user=config.get("runningUser", "unknown"),
        channel=config.get("channel"),
        actions=actions,
    )


def _apex_path(root: str, target: str) -> str:
    return os.path.join(root, "classes", target + ".cls")


def _flow_path(root: str, target: str) -> str:
    return os.path.join(root, "flows", target + ".flow-meta.xml")


def analyze_agent(agent: AgentConfig, source_root: str, perms,
                  classification: dict, object_sharing: dict) -> List[ActionSummary]:
    summaries: List[ActionSummary] = []
    for action in agent.actions:
        if action.target_type == "apex":
            path = _apex_path(source_root, action.target)
            if not os.path.exists(path):
                summaries.append(_unresolved(action, "Apex class source not found"))
                continue
            reach = parse_apex(path)
            findings = analyze_apex(reach, perms, classification, object_sharing)
            summaries.append(summarize_apex(reach, findings, name=action.name))

        elif action.target_type == "flow":
            path = _flow_path(source_root, action.target)
            if not os.path.exists(path):
                summaries.append(_unresolved(action, "Flow metadata not found"))
                continue
            reach = parse_flow(path)
            findings = analyze_flow(reach, perms, classification, object_sharing)
            summaries.append(summarize_flow(reach, findings, name=action.name))

        else:
            # Standard / managed-package actions: source not parseable. State it
            # honestly rather than reporting a false clean.
            summaries.append(ActionSummary(
                action.name, "standard", None, False, [], [],
                [Finding("PS507", "INFO", action.name,
                         f"Action target '{action.target}' is a standard/opaque action.",
                         "Its reach is not statically analysable from source.",
                         "Rely on the vendor's documentation / a runtime review.")]))
    return summaries


def _unresolved(action: AgentAction, why: str) -> ActionSummary:
    return ActionSummary(
        action.name, action.target_type, None, False, [], [],
        [Finding("PS504", "WARN", action.name,
                 f"Could not analyse action '{action.name}' -> {action.target}.",
                 why, "Ensure the target source is retrieved before analysis.")])
