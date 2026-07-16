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
from authority_analyzer import Finding, analyze_apex, analyze_flow, analyze_prompt
from flow_introspect import parse_flow
from genai_prompt_introspect import parse_prompt_template
from prompt_flow_analyzer import analyze_prompt_flow
from report import ActionSummary, summarize_apex, summarize_flow, summarize_prompt


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


# Documented behaviour of common standard/managed actions. Source is not
# parseable, but the behaviour IS documented, so we can name the data-to-model
# channel instead of a blanket "opaque". Honest: only well-known actions are
# catalogued; anything else stays a generic PS507. Keyed by the action's API
# name (matched by suffix so a namespace prefix does not matter).
_STANDARD_CATALOG = {
    "AnswerQuestionsWithKnowledge": {
        "what": "retrieves Salesforce Knowledge article content and returns it to the model",
        "governed": "the running user's Knowledge (Knowledge__kav) access and data categories",
        "channel": "a retrieval/RAG data channel",
    },
    "GetRecordDetails": {
        "what": "reads the fields of the record in context and returns them to the model",
        "governed": "the running user's field-level security on that record's object "
                    "(the object is determined at runtime, so it cannot be enumerated here)",
        "channel": "a record-to-model channel",
    },
    "SummarizeRecord": {
        "what": "reads the record in context and returns a summary to the model",
        "governed": "the running user's FLS on that record's object (determined at runtime)",
        "channel": "a record-to-model channel",
    },
    "QueryRecords": {
        "what": "runs a query the planner composes and returns matching records to the model",
        "governed": "the running user's object and field access (the query is built at runtime)",
        "channel": "a dynamic query-to-model channel",
    },
}


def _catalog_entry(action):
    for suffix, info in _STANDARD_CATALOG.items():
        if (action.target or "").endswith(suffix) or (action.name or "").endswith(suffix):
            return info
    return None


def _apex_path(root: str, target: str) -> str:
    return os.path.join(root, "classes", target + ".cls")


def _flow_path(root: str, target: str) -> str:
    return os.path.join(root, "flows", target + ".flow-meta.xml")


def _prompt_path(root: str, target: str) -> str:
    return os.path.join(root, "genAiPromptTemplates",
                        target + ".genAiPromptTemplate-meta.xml")


def analyze_agent(agent: AgentConfig, source_root: str, perms,
                  classification: dict, object_sharing: dict,
                  triggers_by_object: dict = None,
                  apex_backend: str = "auto",
                  script_ir: dict = None) -> List[ActionSummary]:
    """`script_ir` (Agent Script only) closes the last hop of the Authority Path:
    it lets PS52x prove an Apex field is interpolated into the model's prompt."""
    summaries: List[ActionSummary] = []
    for action in agent.actions:
        if action.target_type == "apex":
            path = _apex_path(source_root, action.target)
            if not os.path.exists(path):
                summaries.append(_unresolved(action, "Apex class source not found"))
                continue
            reach = parse_apex(path, source_root, backend=apex_backend)
            findings = analyze_apex(reach, perms, classification, object_sharing, triggers_by_object)
            if script_ir:
                findings = findings + analyze_prompt_flow(
                    action.name, reach, perms, classification, script_ir)
            summaries.append(summarize_apex(reach, findings, name=action.name))

        elif action.target_type == "flow":
            path = _flow_path(source_root, action.target)
            if not os.path.exists(path):
                summaries.append(_unresolved(action, "Flow metadata not found"))
                continue
            reach = parse_flow(path)
            findings = analyze_flow(reach, perms, classification, object_sharing, triggers_by_object)
            summaries.append(summarize_flow(reach, findings, name=action.name))

        elif action.target_type == "prompt":
            path = _prompt_path(source_root, action.target)
            if not os.path.exists(path):
                summaries.append(_unresolved(action, "Prompt template metadata not found"))
                continue
            reach = parse_prompt_template(path)
            findings = analyze_prompt(reach, perms, classification, object_sharing)
            summaries.append(summarize_prompt(reach, findings, name=action.name))

        else:
            # Standard / managed-package actions: source not parseable. State it
            # honestly rather than reporting a false clean. For catalogued actions
            # we name the documented data-to-model channel; otherwise a generic PS507.
            info = _catalog_entry(action)
            if info:
                finding = Finding(
                    "PS507", "INFO", action.name,
                    f"Standard action '{action.target}' {info['what']} — {info['channel']}.",
                    f"Its exact reach is not enumerable from source, but the behaviour is "
                    f"documented: access is governed by {info['governed']}, not by this analyzer.",
                    "Confirm that access is scoped correctly; treat this as a known "
                    "data-to-model channel, not a blind spot.")
            else:
                finding = Finding(
                    "PS507", "INFO", action.name,
                    f"Action target '{action.target}' is a standard/opaque action.",
                    "Its reach is not statically analysable from source.",
                    "Rely on the vendor's documentation / a runtime review.")
            summaries.append(ActionSummary(
                action.name, "standard", None, False, [], [], [finding]))
    return summaries


def _unresolved(action: AgentAction, why: str) -> ActionSummary:
    return ActionSummary(
        action.name, action.target_type, None, False, [], [],
        [Finding("PS504", "WARN", action.name,
                 f"Could not analyse action '{action.name}' -> {action.target}.",
                 why, "Ensure the target source is retrieved before analysis.")])
