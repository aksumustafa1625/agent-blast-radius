"""Load a permission snapshot for a running user from a live org.

Thin adapter over the Salesforce CLI: runs SOQL and shapes the result into the
dict that permission_resolver.EffectivePermissions consumes. Kept separate from
the resolver so the resolver stays pure and unit-testable.

Effective permissions come from the union of the user's profile and every
assigned permission set. In Salesforce a profile is itself a permission set
(IsOwnedByProfile = true), and PermissionSetAssignment returns that row too, so
querying assignments captures both.

Permission set GROUPS are covered by this same query - VERIFIED in-org (E8, see
below), not assumed. An earlier version of this docstring claimed they were "a
later refinement, not yet expanded here"; that was wrong, and it misled an
external reviewer into filing a critical finding against a gap that does not
exist. The measurement:

  * Every PermissionSetGroup has a platform-computed aggregate PermissionSet
    (Type = 'Group', PermissionSetGroupId set).
  * A group assignment's PermissionSetAssignment.PermissionSetId points at THAT
    aggregate - so `SELECT PermissionSetId FROM PermissionSetAssignment` already
    returns it alongside the plain permission sets.
  * The aggregate carries the group's computed ObjectPermissions/FieldPermissions:
    on TechnoStore's assigned AgentforceServiceAgentUserPsg, the aggregate's
    ObjectPermissions equalled the union of its component permission sets exactly
    (nothing missing, nothing extra).

MUTING permission sets ride the same aggregate - now MEASURED too (E9), where it
used to say "architectural, not measured". A muting set was built in the lab org:
a component granting FLS read on Blast_Test__c.Customer_IBAN__c, a muter removing
it, both in one group. The result:

  * component  -> FieldPermissions.PermissionsRead = true
  * aggregate  -> NO FieldPermissions row at all

So the aggregate applies muting, and reading it is enough. The org confirms it at
runtime (BlastRadius_E9_Muting.cls): as the assigned user, WITH USER_MODE the read
is BLOCKED ("No such column") while a pre-v67 class still reads the value - i.e.
the muted GDPR field escapes exactly as PS506 reports.

This mattered in the dangerous direction. Had the aggregate NOT reflected muting,
we would have credited the user with a permission they lack, concluded "the user
can already see this field", and stayed silent about a real escalation - a false
clean, the worst outcome this tool can produce.

Usage:
    python blast_radius/snapshot_loader.py <username> [sobject1 sobject2 ...]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from org_loaders import soql_str  # noqa: E402  - one escaper for every WHERE clause


def _sf_query(soql: str, tooling: bool = False,
              target_org: Optional[str] = None) -> List[Dict[str, Any]]:
    """Query the org, and the ORG means the one asked for.

    `--target-org` was missing entirely, so every permission fact came from
    whatever the machine's DEFAULT org happened to be. With `--org` pointing
    somewhere else the run died on `No user found with username ...` - naming
    the right user, looked for in the wrong org - and the site's own
    locked-laptop workaround (`measure.py --org <alias>`) could never produce a
    report. The sibling branch in cli.py, snapshot_from_permset, always passed
    it; this half never did.

    The alias is quoted because an org alias may contain a space.
    """
    cmd = f'sf data query --query "{soql}" --json'
    if tooling:
        cmd += " --use-tooling-api"
    if target_org:
        cmd += f' --target-org "{target_org}"'
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
    return "(" + ",".join("'" + soql_str(i) + "'" for i in ids) + ")"


def build_snapshot(
    username: str,
    sobjects: Optional[List[str]] = None,
    channel: Optional[str] = None,
    target_org: Optional[str] = None,
) -> dict:
    """Return a permission snapshot for `username`, optionally restricted to a
    set of sobjects (only the objects an agent's actions touch).

    `target_org` is not optional in any meaningful sense - omitting it silently
    measures the machine's default org. It carries a default only so the
    module's own __main__ demo keeps working."""
    users = _sf_query(
        f"SELECT Id FROM User WHERE Username = '{soql_str(username)}' LIMIT 1",
        target_org=target_org,
    )
    if not users:
        raise ValueError(f"No user found with username {username!r}")
    user_id = users[0]["Id"]

    assignments = _sf_query(
        f"SELECT PermissionSetId FROM PermissionSetAssignment WHERE AssigneeId = '{soql_str(user_id)}'",
        target_org=target_org,
    )
    ps_ids = [r["PermissionSetId"] for r in assignments]
    if not ps_ids:
        raise RuntimeError("No permission sets resolved for user (unexpected)")

    perm_sets = _sf_query(
        "SELECT PermissionsViewAllData, PermissionsModifyAllData "
        f"FROM PermissionSet WHERE Id IN {_in_clause(ps_ids)}",
        target_org=target_org,
    )
    view_all = any(bool(r["PermissionsViewAllData"]) for r in perm_sets)
    modify_all = any(bool(r["PermissionsModifyAllData"]) for r in perm_sets)

    obj_filter = ""
    fld_filter = ""
    if sobjects:
        quoted = _in_clause(sobjects)
        obj_filter = f" AND SobjectType IN {quoted}"
        fld_filter = f" AND SobjectType IN {quoted}"

    obj_rows = _sf_query(
        "SELECT Parent.Name, SobjectType, PermissionsRead, PermissionsCreate, "
        "PermissionsEdit, PermissionsDelete, PermissionsViewAllRecords, "
        "PermissionsModifyAllRecords FROM ObjectPermissions "
        f"WHERE ParentId IN {_in_clause(ps_ids)}{obj_filter}",
        target_org=target_org,
    )
    fld_rows = _sf_query(
        "SELECT Parent.Name, SobjectType, Field, PermissionsRead, PermissionsEdit "
        f"FROM FieldPermissions WHERE ParentId IN {_in_clause(ps_ids)}{fld_filter}",
        target_org=target_org,
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
