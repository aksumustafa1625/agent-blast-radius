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


def expand_agent_graph(agent: AgentConfig, source_root: str, loader=None,
                       max_depth: int = 3):
    """Flatten an agent-to-agent graph into ONE action list.

    An agent can invoke another agent (`agentforce://X`). Analysing only the
    entry agent reports the sub-agent as a single opaque action and hides its
    entire data surface — in a multi-agent org that is the largest possible
    under-report. So the graph is walked and every reachable agent's actions are
    spliced in, renamed `SubAgent :: action`, BEFORE any reach/permission work
    happens. Everything downstream (reach, record modes, analysis, report) then
    operates on the true aggregate blast radius with no changes.

    Honest by construction:
      * a delegation we CANNOT resolve stays an `agent` action -> PS515 unknown,
        never silently dropped and never silently treated as clean;
      * a cycle (A -> B -> A) stops at the repeat and is reported, not followed;
      * `max_depth` bounds the walk; hitting it leaves the edge unresolved (PS515)
        rather than pretending the reach ends there.

    `loader(name) -> config dict | None` resolves a sub-agent's config. Returns
    (actions, edges) where edges is [(caller, callee, resolved: bool, note)].
    """
    edges = []
    out: List[AgentAction] = []
    visited = {agent.name}

    def _walk(cfg: AgentConfig, depth: int, prefix: str):
        for act in cfg.actions:
            if act.target_type != "agent":
                out.append(AgentAction(name=f"{prefix}{act.name}",
                                       target_type=act.target_type,
                                       target=act.target) if prefix else act)
                continue

            callee = act.target or act.name
            if callee in visited:
                edges.append((cfg.name, callee, False, "cycle - already analysed"))
                out.append(act)                       # keep it -> PS515
                continue
            if depth >= max_depth:
                edges.append((cfg.name, callee, False,
                              f"depth limit {max_depth} reached"))
                out.append(act)
                continue
            sub_cfg = None
            if loader:
                try:
                    raw = loader(callee)
                    sub_cfg = parse_agent_config(raw) if raw else None
                except Exception as e:                # noqa: BLE001 - stay honest
                    edges.append((cfg.name, callee, False, f"load failed: {e}"))
                    out.append(act)
                    continue
            if not sub_cfg:
                edges.append((cfg.name, callee, False, "config not found locally"))
                out.append(act)                       # unresolved -> PS515
                continue

            visited.add(callee)
            edges.append((cfg.name, callee, True, "expanded"))
            _walk(sub_cfg, depth + 1, f"{callee} :: ")

    _walk(agent, 0, "")
    return out, edges


def analyze_agent_graph_edges(edges) -> List[Finding]:
    """PS515 for every agent-to-agent delegation. An expanded edge is INFO (its
    reach is already merged into this report); an unresolved one is a WARN
    honest-unknown, because that agent's data surface is genuinely not analysed."""
    findings = []
    for caller, callee, resolved, note in edges:
        if resolved:
            findings.append(Finding(
                "PS515", "INFO", f"{caller} -> agent {callee}",
                f"Delegates to agent '{callee}', whose actions are expanded into this "
                "report.",
                "An agent that invokes another agent inherits that agent's data reach. "
                "The findings below therefore cover the whole graph, not just the entry "
                "agent — action names are prefixed with the agent they came from.",
                "Confirm the delegation is intended; the sub-agent's escalations are "
                "this agent's escalations too."))
        else:
            findings.append(Finding(
                "PS515", "WARN", f"{caller} -> agent {callee}",
                f"Delegates to agent '{callee}', whose reach was NOT analysed ({note}).",
                "That agent runs with its own actions and its own data surface. This "
                "report therefore UNDERSTATES the true blast radius by whatever that "
                "agent can reach. This is an honest unknown, not a clean result.",
                f"Scan '{callee}' as its own entry point, or make its config available "
                "locally so the graph can be expanded."))
    return findings


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
                  script_ir: dict = None,
                  graph_edges=None,
                  calculated: set = None,
                  apex_allowed: set = None) -> List[ActionSummary]:
    """`script_ir` (Agent Script only) closes the last hop of the Authority Path:
    it lets PS52x prove an Apex field is interpolated into the model's prompt.

    `graph_edges` (from expand_agent_graph) carries the agent-to-agent delegations,
    reported as PS515 — INFO when the sub-agent's actions were merged in, WARN when
    its reach could not be analysed and this report therefore understates."""
    summaries: List[ActionSummary] = []

    if graph_edges:
        summaries.append(ActionSummary(
            f"{agent.name} (agent graph)", "agent", None, False, [], [],
            analyze_agent_graph_edges(graph_edges)))

    for action in agent.actions:
        # An `agent` target that survived expansion is one we could NOT resolve;
        # PS515 above already reports it honestly, so it must not also fall through
        # to the generic opaque PS507 and be double-counted as a mystery action.
        if action.target_type == "agent":
            continue

        if action.target_type == "apex":
            path = _apex_path(source_root, action.target)
            if not os.path.exists(path):
                summaries.append(_unresolved(action, "Apex class source not found"))
                continue
            reach = parse_apex(path, source_root, backend=apex_backend,
                               allowed=apex_allowed)
            findings = analyze_apex(reach, perms, classification, object_sharing,
                                    triggers_by_object, calculated=calculated)
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
                 f"Could not analyse action '{action.name}' -> {action.target} - the "
                 "source never reached the scan.",
                 why,
                 # A third owner again: not the code's shape and not the analyzer's
                 # model, but what the scan was given. Naming it matters because the
                 # other two are not actionable here - there is nothing to rewrite
                 # and nothing to wait for, only a retrieval to redo.
                 "The scan's to close: retrieve the target source (and check the "
                 "analysis identity can see it) before re-running.")])
