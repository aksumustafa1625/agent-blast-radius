"""Load a real agent config from retrieved GenAi metadata (Milestone 5, live).

The thin adapter that replaces the hand-written fixture: it reads the metadata
`sf agent create` / a Metadata API retrieve leaves in the project -
GenAiPlannerBundle -> GenAiPlugin (topics) -> GenAiFunction (actions) - and
produces the normalized dict that agent_analyzer.parse_agent_config consumes.

TWO planner-bundle shapes exist in the wild and both are handled:

1. Agent Builder / `sf agent create` (separate plugin + function files):
     genAiPlannerBundles/<name>/<name>.genAiPlannerBundle
         <masterLabel>                     agent name
         <genAiPlugins><genAiPluginName>   -> topic developer names
     genAiPlugins/<developerName>.genAiPlugin-meta.xml
         <genAiFunctions><functionName>    -> action function names
     genAiFunctions/<functionName>.genAiFunction-meta.xml   (custom actions)
         <invocationTarget> / <invocationTargetType>  -> apex | flow
   Custom GenAiFunctions do not reliably retrieve to a file, so a `resolver`
   map (built from GenAiFunctionDefinition via the Tooling API) fills the gap.

2. Compiled from an Agent Script authoring bundle (`sf agent publish`) - topics
   and actions are INLINE in the planner bundle:
     <localTopics>
         <masterLabel> / <localDeveloperName>
         <localActionLinks><functionName>   -> actions used by the topic
         <localActions>
             <localDeveloperName>           -> action name
             <invocationTarget> / <invocationTargetType>  -> apex | flow
   Here the target is in the file, so no Tooling API lookup is needed at all.

Missing this second shape used to yield ZERO actions and therefore a silent
"no findings" - a false clean, the one outcome this tool exists to prevent. An
action whose target cannot be resolved by any route is reported as an opaque
standard/managed target (PS507), never as clean.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Optional

NS = "{http://soap.sforce.com/2006/04/metadata}"


def _norm_kind(ttype: str) -> Optional[str]:
    """Invocation target type -> a source-analysable kind, or None if opaque.
    apex / flow are read from source; a prompt template is read declaratively;
    an agent target is another agent whose own graph we expand."""
    t = (ttype or "").lower()
    if t in ("apex", "flow"):
        return t
    if "prompt" in t:                 # promptTemplate / prompt
        return "prompt"
    if t in ("agent", "agentforce", "botdefinition", "planner"):
        return "agent"                # agent-to-agent delegation
    return None


def _resolve_function(source_root: str, function_name: str,
                      resolver: Optional[dict] = None) -> dict:
    # 1. local genAiFunction file (if it retrieved to disk)
    path = os.path.join(source_root, "genAiFunctions", function_name + ".genAiFunction-meta.xml")
    if os.path.exists(path):
        root = ET.parse(path).getroot()
        target = root.findtext(f"{NS}invocationTarget")
        kind = _norm_kind(root.findtext(f"{NS}invocationTargetType"))
        if target and kind:
            return {"name": function_name, "invocationTargetType": kind, "invocationTarget": target}
    # 2. resolver map (e.g. built from GenAiFunctionDefinition via the Tooling API,
    #    since custom GenAiFunctions do not always retrieve to a file)
    if resolver and function_name in resolver:
        r = resolver[function_name]
        return {"name": function_name, "invocationTargetType": r["type"], "invocationTarget": r["target"]}
    # 3. standard / managed / opaque
    return {"name": function_name, "invocationTargetType": "standard", "invocationTarget": function_name}


def _plugin(source_root: str, plugin_name: str, resolver: Optional[dict] = None) -> dict:
    path = os.path.join(source_root, "genAiPlugins", plugin_name + ".genAiPlugin-meta.xml")
    if not os.path.exists(path):
        return {"name": plugin_name, "actions": []}
    root = ET.parse(path).getroot()
    label = root.findtext(f"{NS}masterLabel") or plugin_name
    actions = [
        _resolve_function(source_root, gf.findtext(f"{NS}functionName"), resolver)
        for gf in root.findall(f"{NS}genAiFunctions")
        if gf.findtext(f"{NS}functionName")
    ]
    return {"name": label, "actions": actions}


def _local_topic(topic_el) -> dict:
    """Shape 2: a topic whose actions are inline in the planner bundle (an agent
    compiled from Agent Script). The invocation target is right here - no
    Tooling API round trip."""
    label = (topic_el.findtext(f"{NS}masterLabel")
             or topic_el.findtext(f"{NS}localDeveloperName") or "topic")

    actions = []
    declared = set()
    for act in topic_el.findall(f"{NS}localActions"):
        name = (act.findtext(f"{NS}localDeveloperName")
                or act.findtext(f"{NS}developerName") or "action")
        target = act.findtext(f"{NS}invocationTarget")
        kind = _norm_kind(act.findtext(f"{NS}invocationTargetType"))
        full = act.findtext(f"{NS}fullName") or act.findtext(f"{NS}developerName")
        if full:
            declared.add(full)
        if target and kind:
            actions.append({"name": name, "invocationTargetType": kind,
                            "invocationTarget": target})
        else:
            # e.g. @utils.escalate / a standard action: not analysable from source.
            actions.append({"name": name, "invocationTargetType": "standard",
                            "invocationTarget": target or name})

    # Linked functions with no inline definition are opaque, never silently clean.
    for link in topic_el.findall(f"{NS}localActionLinks"):
        fname = link.findtext(f"{NS}functionName")
        if fname and fname not in declared:
            actions.append({"name": fname, "invocationTargetType": "standard",
                            "invocationTarget": fname})

    return {"name": label, "actions": actions}


def load_agent_config(source_root: str, bundle_name: str,
                      running_user: str = "unknown", channel: Optional[str] = None,
                      resolver: Optional[dict] = None) -> dict:
    bpath = os.path.join(source_root, "genAiPlannerBundles", bundle_name,
                         bundle_name + ".genAiPlannerBundle")
    root = ET.parse(bpath).getroot()
    agent = root.findtext(f"{NS}masterLabel") or bundle_name

    # Shape 1: referenced GenAiPlugin files.
    topics = [
        _plugin(source_root, gp.findtext(f"{NS}genAiPluginName"), resolver)
        for gp in root.findall(f"{NS}genAiPlugins")
        if gp.findtext(f"{NS}genAiPluginName")
    ]
    # Shape 2: topics inlined by the Agent Script compiler.
    topics += [_local_topic(t) for t in root.findall(f"{NS}localTopics")]

    return {"agent": agent, "runningUser": running_user, "channel": channel, "topics": topics}


if __name__ == "__main__":
    import json
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "force-app/main/default"
    bundle = sys.argv[2] if len(sys.argv) > 2 else "HealthRecord_Assistant"
    print(json.dumps(load_agent_config(root, bundle, running_user="hr-agent-runtime-user",
                                       channel="agent"), indent=2))
