"""Load an agent from a Salesforce Agent Script (.agent) authoring bundle.

This is the second input path (the first is GenAiPlanner/GenAiPlugin metadata via
agent_metadata_loader). Both feed the SAME normalized config that
agent_analyzer.parse_agent_config consumes, so the analyzer is untouched.

Why this path is better where it exists: an Agent Script agent declares each
action's invocation target in the file - `target: "apex://GetHealthRecordSummary"`.
That retires the tool's most fragile input: resolving a custom GenAiFunction to
its Apex class through a Tooling API lookup (GenAiFunctionDefinition ->
InvocationTarget Id -> ApexClass.Name). Here the target is a parsed string with a
line and column, read by Salesforce's own open-source parser.

Honest scope: Agent Builder agents still compile to GenAiPlugin metadata, so both
paths stay supported. Non-apex/flow schemes (standardInvocableAction://,
externalService://, agentforce://, prompt://, api://) are NOT source-analysable
and are passed through as opaque -> PS507, never as a silent clean.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPT = os.path.join(_HERE, "agentscript_extract.mjs")
_PARSER_PKG = os.path.join(_HERE, "node_modules", "@sf-agentscript", "parser")

_NODE = os.environ.get("BLAST_RADIUS_NODE") or shutil.which("node")

_available_cache: Optional[bool] = None


class AgentScriptError(RuntimeError):
    """Parsing/loading the .agent failed - report honestly, never a false clean."""


def agentscript_available() -> bool:
    """True if the official parser bridge can actually run (node genuinely
    launches + the extractor + @sf-agentscript/parser are present)."""
    global _available_cache
    if _available_cache is not None:
        return _available_cache
    _available_cache = False
    if _NODE and os.path.exists(_SCRIPT) and os.path.isdir(_PARSER_PKG):
        try:
            r = subprocess.run([_NODE, "--version"], capture_output=True,
                               text=True, timeout=10)
            _available_cache = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _available_cache = False
    return _available_cache


def extract(agent_path: str, timeout: float = 60.0) -> dict:
    """Parse one .agent file via Salesforce's own parser -> normalized IR dict."""
    if not agentscript_available():
        raise AgentScriptError(
            "Agent Script backend unavailable (node or @sf-agentscript/parser missing). "
            "Run `npm install` in blast_radius/.")
    res = subprocess.run(
        [_NODE, _SCRIPT, os.path.abspath(agent_path)], cwd=_HERE,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout)
    if not res.stdout.strip():
        raise AgentScriptError(f"extractor produced no output: {res.stderr.strip()}")
    data = json.loads(res.stdout)
    if "error" in data:
        raise AgentScriptError(f"Agent Script parse failed: {data['error']}")
    return data


# Schemes whose source we can actually introspect. Everything else is opaque.
# `prompt://` is a GenAiPromptTemplate - read declaratively for its record merge.
# `agentforce://X` is an agent invoking ANOTHER agent. Left as "standard" it
# collapsed into a generic opaque PS507 — which hid the sub-agent's entire blast
# radius, the single largest under-report possible in a multi-agent org. It gets
# its own kind so the graph can be expanded (see agent_analyzer.expand_agent_graph).
_SOURCE_SCHEMES = {"apex": "apex", "flow": "flow", "prompt": "prompt",
                   "agentforce": "agent"}


def to_analyzer_config(ir: dict, running_user: str, channel: str = "agent") -> dict:
    """IR -> the config dict agent_analyzer.parse_agent_config already expects.

    The analyzer is not modified: an Agent Script agent and a metadata agent
    become the same shape, so every PS5xx rule applies to both."""
    topics = []
    for t in ir.get("topics", []):
        actions = []
        for a in t.get("actions", []):
            scheme = (a.get("scheme") or "").strip()
            kind = _SOURCE_SCHEMES.get(scheme, "standard")   # unknown -> opaque (PS507)
            actions.append({
                "name": a.get("local_name") or a.get("target_name") or "?",
                "invocationTargetType": kind,
                "invocationTarget": a.get("target_name") or a.get("target") or "",
            })
        if actions:
            topics.append({"name": t.get("name"), "actions": actions})
    return {
        "agent": ir.get("agent_name") or "(agent script)",
        "runningUser": running_user,
        "channel": channel,
        "topics": topics,
    }


def reached_targets(ir: dict) -> list:
    """(scheme, name, line) for every action target - the Tooling-API-free bind."""
    return [(a.get("scheme"), a.get("target_name"), a.get("line"))
            for t in ir.get("topics", []) for a in t.get("actions", [])]
