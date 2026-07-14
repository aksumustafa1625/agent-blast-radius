"""Load a permission snapshot for a running user from a live org.

Thin adapter over the Salesforce CLI: runs SOQL and shapes the result into the
dict that permission_resolver.EffectivePermissions consumes. Kept separate from
the resolver so the resolver stays pure and unit-testable.

Effective permissions come from the union of the user's profile and every
assigned permission set. In Salesforce a profile is itself a permission set
(IsOwnedByProfile = true), and PermissionSetAssignment returns that row too, so
querying assignments captures both. Permission set GROUPS are a later
refinement (their aggregate permission set is not yet expanded here).

Usage:
    python blast_radius/snapshot_loader.py <username> [sobject1 sobject2 ...]
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Dict, List, Optional


def _sf_query(soql: str, tooling: bool = False) -> List[Dict[str, Any]]:
    cmd = f'sf data query --query "{soql}" --json'
    if tooling:
        cmd += " --use-tooling-api"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"sf did not return JSON:\n{res.stdout}\n{res.stderr}")
    if data.get("status") != 0:
        raise RuntimeError(data.get("message", "sf query failed"))
    return data["result"]["records"]


def _in_clause(ids: List[str]) -> str:
    return "(" + ",".join("'" + i + "'" for i in ids) + ")"


def build_snapshot(
    username: str,
    sobjects: Optional[List[str]] = None,
    channel: Optional[str] = None,
) -> dict:
    """Return a permission snapshot for `username`, optionally restricted to a
    set of sobjects (only the objects an agent's actions touch)."""
    users = _sf_query(
        f"SELECT Id FROM User WHERE Username = '{username}' LIMIT 1"
    )
    if not users:
        raise ValueError(f"No user found with username {username!r}")
    user_id = users[0]["Id"]

    assignments = _sf_query(
        f"SELECT PermissionSetId FROM PermissionSetAssignment WHERE AssigneeId = '{user_id}'"
    )
    ps_ids = [r["PermissionSetId"] for r in assignments]
    if not ps_ids:
        raise RuntimeError("No permission sets resolved for user (unexpected)")

    perm_sets = _sf_query(
        "SELECT PermissionsViewAllData, PermissionsModifyAllData "
        f"FROM PermissionSet WHERE Id IN {_in_clause(ps_ids)}"
    )
    view_all = any(bool(r["PermissionsViewAllData"]) for r in perm_sets)
    modify_all = any(bool(r["PermissionsModifyAllData"]) for r in perm_sets)

    obj_filter = ""
    fld_filter = ""
    if sobjects:
        quoted = "(" + ",".join("'" + s + "'" for s in sobjects) + ")"
        obj_filter = f" AND SobjectType IN {quoted}"
        fld_filter = f" AND SobjectType IN {quoted}"

    obj_rows = _sf_query(
        "SELECT Parent.Name, SobjectType, PermissionsRead, PermissionsCreate, "
        "PermissionsEdit, PermissionsDelete, PermissionsViewAllRecords, "
        "PermissionsModifyAllRecords FROM ObjectPermissions "
        f"WHERE ParentId IN {_in_clause(ps_ids)}{obj_filter}"
    )
    fld_rows = _sf_query(
        "SELECT Parent.Name, SobjectType, Field, PermissionsRead, PermissionsEdit "
        f"FROM FieldPermissions WHERE ParentId IN {_in_clause(ps_ids)}{fld_filter}"
    )

    return {
        "runningUser": username,
        "channel": channel,
        "systemPermissions": {"ViewAllData": view_all, "ModifyAllData": modify_all},
        "objectPermissions": [
            {
                "parent": (r.get("Parent") or {}).get("Name"),
                "sobjectType": r["SobjectType"],
                "read": bool(r["PermissionsRead"]),
                "create": bool(r["PermissionsCreate"]),
                "edit": bool(r["PermissionsEdit"]),
                "delete": bool(r["PermissionsDelete"]),
                "viewAllRecords": bool(r["PermissionsViewAllRecords"]),
                "modifyAllRecords": bool(r["PermissionsModifyAllRecords"]),
            }
            for r in obj_rows
        ],
        "fieldPermissions": [
            {
                "parent": (r.get("Parent") or {}).get("Name"),
                "field": r["Field"],
                "read": bool(r["PermissionsRead"]),
                "edit": bool(r["PermissionsEdit"]),
            }
            for r in fld_rows
        ],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python snapshot_loader.py <username> [sobject ...]")
        sys.exit(2)
    uname = sys.argv[1]
    objs = sys.argv[2:] or None
    print(json.dumps(build_snapshot(uname, sobjects=objs), indent=2))
