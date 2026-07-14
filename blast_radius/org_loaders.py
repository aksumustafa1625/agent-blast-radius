"""Live loaders: pull everything the analyzer needs from any org via `sf`.

These make the tool org-agnostic - point it at an authenticated org and it reads
the GDPR labels, sharing models, GenAi function targets, and permissions live.
Each is a thin `sf data query` wrapper; nothing here invokes an agent.
"""

from __future__ import annotations

import json
import subprocess
from typing import Dict, Iterable, List, Optional


def _sf(query: str, tooling: bool = False, target_org: Optional[str] = None) -> List[dict]:
    cmd = f'sf data query --query "{query}" --json'
    if tooling:
        cmd += " --use-tooling-api"
    if target_org:
        cmd += f" --target-org {target_org}"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"sf did not return JSON:\n{res.stdout}\n{res.stderr}")
    if data.get("status") != 0:
        raise RuntimeError(data.get("message", "sf query failed"))
    return data["result"]["records"]


def _in(values: Iterable[str]) -> str:
    return "(" + ",".join("'" + v + "'" for v in values) + ")"


def function_resolver(target_org: Optional[str] = None) -> Dict[str, dict]:
    """Map each GenAiFunction developerName to its Apex/Flow invocation target.

    Custom GenAiFunctions don't reliably retrieve to a file, so resolve the
    action -> Apex class (by name) through the Tooling API."""
    funcs = _sf("SELECT DeveloperName, InvocationTarget, InvocationTargetType "
                "FROM GenAiFunctionDefinition", tooling=True, target_org=target_org)
    apex_ids = [f["InvocationTarget"] for f in funcs
                if f.get("InvocationTargetType") == "apex" and f.get("InvocationTarget")]
    id_to_name: Dict[str, str] = {}
    if apex_ids:
        for c in _sf(f"SELECT Id, Name FROM ApexClass WHERE Id IN {_in(apex_ids)}",
                     tooling=True, target_org=target_org):
            id_to_name[c["Id"]] = c["Name"]
    resolver: Dict[str, dict] = {}
    for f in funcs:
        ttype = (f.get("InvocationTargetType") or "").lower()
        target = f.get("InvocationTarget")
        if ttype == "apex" and target in id_to_name:
            resolver[f["DeveloperName"]] = {"type": "apex", "target": id_to_name[target]}
        elif ttype == "flow" and target:
            resolver[f["DeveloperName"]] = {"type": "flow", "target": target}
    return resolver


def classification(objects: Iterable[str], target_org: Optional[str] = None) -> Dict[str, dict]:
    """{'Object.Field': {complianceGroup, securityClassification}} for classified
    fields on the given objects. FieldDefinition is FLS-gated: run as an identity
    with broad field read, or classified fields stay invisible."""
    out: Dict[str, dict] = {}
    for obj in objects:
        rows = _sf("SELECT QualifiedApiName, ComplianceGroup, SecurityClassification "
                   f"FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName='{obj}'",
                   target_org=target_org)
        for r in rows:
            cg, sc = r.get("ComplianceGroup"), r.get("SecurityClassification")
            if cg or sc:
                out[f"{obj}.{r['QualifiedApiName']}"] = {
                    "complianceGroup": cg or "", "securityClassification": sc or ""}
    return out


def sharing(objects: Iterable[str], target_org: Optional[str] = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for obj in objects:
        rows = _sf("SELECT QualifiedApiName, InternalSharingModel "
                   f"FROM EntityDefinition WHERE QualifiedApiName='{obj}'", target_org=target_org)
        for r in rows:
            out[obj] = r.get("InternalSharingModel")
    return out


def snapshot_from_permset(permset: str, objects: Iterable[str],
                          target_org: Optional[str] = None) -> dict:
    """Model a running user whose access on the given objects comes from one
    permission set (the agent's intended minimal grant)."""
    objs = list(objects)
    obj_filter = f" AND SobjectType IN {_in(objs)}" if objs else ""
    ops = _sf("SELECT SobjectType, PermissionsRead, PermissionsCreate, PermissionsEdit, "
              "PermissionsDelete, PermissionsViewAllRecords, PermissionsModifyAllRecords "
              f"FROM ObjectPermissions WHERE Parent.Name='{permset}'{obj_filter}",
              target_org=target_org)
    fps = _sf("SELECT Field, PermissionsRead, PermissionsEdit "
              f"FROM FieldPermissions WHERE Parent.Name='{permset}'{obj_filter}",
              target_org=target_org)
    ps = _sf("SELECT PermissionsViewAllData, PermissionsModifyAllData "
             f"FROM PermissionSet WHERE Name='{permset}' LIMIT 1", target_org=target_org)
    return {
        "runningUser": f"(permission set: {permset})",
        "channel": "agent",
        "systemPermissions": {
            "ViewAllData": bool(ps and ps[0].get("PermissionsViewAllData")),
            "ModifyAllData": bool(ps and ps[0].get("PermissionsModifyAllData")),
        },
        "objectPermissions": [{
            "parent": f"PermSet:{permset}", "sobjectType": r["SobjectType"],
            "read": bool(r["PermissionsRead"]), "create": bool(r["PermissionsCreate"]),
            "edit": bool(r["PermissionsEdit"]), "delete": bool(r["PermissionsDelete"]),
            "viewAllRecords": bool(r["PermissionsViewAllRecords"]),
            "modifyAllRecords": bool(r["PermissionsModifyAllRecords"]),
        } for r in ops],
        "fieldPermissions": [{
            "parent": f"PermSet:{permset}", "field": r["Field"],
            "read": bool(r["PermissionsRead"]), "edit": bool(r["PermissionsEdit"]),
        } for r in fps],
    }
