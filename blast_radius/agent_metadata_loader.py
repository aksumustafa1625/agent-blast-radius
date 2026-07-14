"""Load a real agent config from retrieved GenAi metadata (Milestone 5, live).

The thin adapter that replaces the hand-written fixture: it reads the metadata
`sf agent create` / a Metadata API retrieve leaves in the project -
GenAiPlannerBundle -> GenAiPlugin (topics) -> GenAiFunction (actions) - and
produces the normalized dict that agent_analyzer.parse_agent_config consumes.

Structure (observed from a real created agent):
  genAiPlannerBundles/<name>/<name>.genAiPlannerBundle
      <masterLabel>            agent name
      <genAiPlugins><genAiPluginName>   -> topic developer names
  genAiPlugins/<developerName>.genAiPlugin-meta.xml
      <masterLabel>            topic label
      <genAiFunctions><functionName>    -> action function names
  genAiFunctions/<functionName>.genAiFunction-meta.xml   (custom actions)
      <invocationTarget> / <invocationTargetType>  -> apex | flow

A function with no local genAiFunction file is a standard/managed action
(e.g. EmployeeCopilot__*): reported honestly as an opaque target, not clean.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Optional

NS = "{http://soap.sforce.com/2006/04/metadata}"


def _resolve_function(source_root: str, function_name: str,
                      resolver: Optional[dict] = None) -> dict:
    # 1. local genAiFunction file (if it retrieved to disk)
    path = os.path.join(source_root, "genAiFunctions", function_name + ".genAiFunction-meta.xml")
    if os.path.exists(path):
        root = ET.parse(path).getroot()
        target = root.findtext(f"{NS}invocationTarget")
        ttype = (root.findtext(f"{NS}invocationTargetType") or "").lower()
        if target and ttype in ("apex", "flow"):
            return {"name": function_name, "invocationTargetType": ttype, "invocationTarget": target}
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


def load_agent_config(source_root: str, bundle_name: str,
                      running_user: str = "unknown", channel: Optional[str] = None,
                      resolver: Optional[dict] = None) -> dict:
    bpath = os.path.join(source_root, "genAiPlannerBundles", bundle_name,
                         bundle_name + ".genAiPlannerBundle")
    root = ET.parse(bpath).getroot()
    agent = root.findtext(f"{NS}masterLabel") or bundle_name
    topics = [
        _plugin(source_root, gp.findtext(f"{NS}genAiPluginName"), resolver)
        for gp in root.findall(f"{NS}genAiPlugins")
        if gp.findtext(f"{NS}genAiPluginName")
    ]
    return {"agent": agent, "runningUser": running_user, "channel": channel, "topics": topics}


if __name__ == "__main__":
    import json
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "force-app/main/default"
    bundle = sys.argv[2] if len(sys.argv) > 2 else "HealthRecord_Assistant"
    print(json.dumps(load_agent_config(root, bundle, running_user="hr-agent-runtime-user",
                                       channel="agent"), indent=2))
