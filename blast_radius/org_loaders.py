"""Live loaders: pull everything the analyzer needs from any org via `sf`.

These make the tool org-agnostic - point it at an authenticated org and it reads
the GDPR labels, sharing models, GenAi function targets, and permissions live.
Each is a thin `sf data query` wrapper; nothing here invokes an agent.
"""

from __future__ import annotations

import json
import re
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


def _label_rows(obj: str, target_org):
    # IsCalculated comes along because a FORMULA field's value is computed from other
    # fields, and this analyzer does not resolve which. A user's FLS on the formula
    # therefore does not bound what its VALUE carries - so a formula in the reach is an
    # unresolved reach, whatever its own label says. Measured on the demo's own object:
    # 11 of Invoice's 93 fields are formulas, and the flagship action reads one of them
    # (TotalAmountWithTax).
    return _sf("SELECT QualifiedApiName, ComplianceGroup, SecurityClassification, "
               "IsCalculated "
               f"FROM FieldDefinition WHERE EntityDefinition.QualifiedApiName='{obj}'",
               target_org=target_org)


def _rel_root(field_path: str, objects) -> Optional[str]:
    """The relationship name in a reached field path, or None for a direct field.

    Accepts BOTH spellings the codebase uses. `report._qualify` leaves a relationship
    field alone (`BillToContact.Email`) and prefixes only direct fields
    (`Invoice.Status`), which is what cli._reached_fields passes. But a caller that
    prefixes anyway (`Invoice.BillToContact.Email`) used to disable relationship
    resolution ENTIRELY and without a word: the old code took `split('.')[0]`, got the
    ROOT object, found it in `objects`, and filtered the path out - so every
    cross-object label went missing and PS506 stayed quiet. A silent false clean
    triggered by nothing more than how a caller spells a field."""
    parts = field_path.split(".")
    if len(parts) < 2:
        return None                       # a bare field name: nothing to traverse
    if parts[0] in objects:
        # `Invoice.BillToContact.Email` -> BillToContact; `Invoice.Status` -> direct
        return parts[1] if len(parts) >= 3 else None
    return parts[0]


def _relationship_targets(obj: str, target_org) -> Dict[str, str]:
    """{relationshipName: targetObject} for `obj`'s single-target lookups.

    `ReferenceTo` gives real API names ({'referenceTo': ['Contact']}); the
    `DataType` string looks tempting but carries LABELS ("Lookup(Order Summary)"),
    which would break on any custom object whose label differs from its API name.
    A POLYMORPHIC lookup (referenceTo: ['Group','User']) is deliberately skipped:
    we cannot say which object a given row points at, so the honest answer is to
    leave the field unclassified rather than pick one and be confidently wrong."""
    out: Dict[str, str] = {}
    try:
        rows = _sf("SELECT RelationshipName, ReferenceTo FROM FieldDefinition "
                   f"WHERE EntityDefinition.QualifiedApiName='{obj}' "
                   "AND RelationshipName != null", target_org=target_org)
    except RuntimeError:
        return out                                   # best-effort, never fatal
    for r in rows:
        rel = r.get("RelationshipName")
        refs = (r.get("ReferenceTo") or {}).get("referenceTo") or []
        if rel and len(refs) == 1:
            out[rel] = refs[0]
    return out


def calculated_fields(objects: Iterable[str], target_org: Optional[str] = None) -> set:
    """{'Object.Field'} for every FORMULA field on the reached objects.

    Why this is its own loader and not a label: a formula's value is COMPUTED from
    other fields, and this analyzer does not resolve which. So the running user's FLS
    on the formula does not bound what the formula's VALUE carries - a formula the
    user is allowed can echo a field they are not. That makes a formula in the reach
    an UNRESOLVED reach, whatever its own compliance label says, and it is the one
    channel that can survive even a v67 user-mode read: user mode enforces FLS on the
    formula the user CAN see, not on what it references.

    Raised by an external review. NOT measured here - the fixture that would settle it
    could not be deployed (see CLAUDE.md §9), so this emits an honest unknown rather
    than a leak claim: the statement is about OUR resolution, which is true either way,
    not about the platform's behaviour, which is not.

    It is not hypothetical: 11 of Invoice's 93 fields are formulas, and the flagship
    demo action reads one of them (TotalAmountWithTax)."""
    out = set()
    for obj in objects:
        try:
            rows = _sf("SELECT QualifiedApiName FROM FieldDefinition "
                       f"WHERE EntityDefinition.QualifiedApiName='{obj}' "
                       "AND IsCalculated=true", target_org=target_org)
        except RuntimeError:
            continue                       # best-effort, never fatal
        for r in rows:
            out.add(f"{obj}.{r['QualifiedApiName']}")
    return out


def classification(objects: Iterable[str], target_org: Optional[str] = None,
                   fields: Optional[Iterable[str]] = None):
    """Returns (labels, visible_by_object).

    labels: {'Object.Field': {complianceGroup, securityClassification}} for
            classified fields.
    visible_by_object: {'Object': {field api names FieldDefinition returned}} -
            the fields VISIBLE to the analysis identity. FieldDefinition is
            FLS-gated, so fields the identity cannot read are absent here; the
            report uses this to distinguish "unclassified" from "not visible to
            the analyzer" (never reporting a blind spot as clean).

    CROSS-OBJECT: a query reaching `BillToContact.Email` really reads Contact.Email,
    but labels were only ever keyed per REACHED object - so the GDPR label sitting
    on Contact.Email was never found and the headline rule (PS506) silently missed
    it. Pass the reached field paths as `fields` and every relationship actually
    used is resolved to its target object, whose labels are ALSO keyed under the
    relationship path ('BillToContact.Email') - the spelling the analyzer already
    looks up. Only relationships the agent really traverses are queried."""
    labels: Dict[str, dict] = {}
    visible: Dict[str, set] = {}
    objects = list(objects)

    def _absorb(rows, prefix: str, mark_visible: Optional[str] = None):
        for r in rows:
            name = r["QualifiedApiName"]
            if mark_visible:
                visible[mark_visible].add(name)
            cg, sc = r.get("ComplianceGroup"), r.get("SecurityClassification")
            if cg or sc:
                labels[f"{prefix}.{name}"] = {
                    "complianceGroup": cg or "", "securityClassification": sc or ""}

    for obj in objects:
        visible[obj] = set()
        _absorb(_label_rows(obj, target_org), obj, mark_visible=obj)

    # Relationship paths the reach actually uses: `BillToContact.Email` where
    # `BillToContact` is not itself a reached object.
    rel_paths = {r for r in (_rel_root(f, objects) for f in (fields or [])) if r}
    if not rel_paths:
        return labels, visible

    rel_map: Dict[str, str] = {}
    for obj in objects:
        for rel, target in _relationship_targets(obj, target_org).items():
            rel_map.setdefault(rel, target)

    for rel in sorted(rel_paths):
        target = rel_map.get(rel)
        if not target:
            continue                    # unresolved or polymorphic -> stays unclassified
        try:
            _absorb(_label_rows(target, target_org), rel)
        except RuntimeError:
            continue                    # not readable by the analysis identity
    return labels, visible


def sharing(objects: Iterable[str], target_org: Optional[str] = None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for obj in objects:
        rows = _sf("SELECT QualifiedApiName, InternalSharingModel "
                   f"FROM EntityDefinition WHERE QualifiedApiName='{obj}'", target_org=target_org)
        for r in rows:
            out[obj] = r.get("InternalSharingModel")
    return out


_TRIGGER_REF = re.compile(r"\bnew\s+([A-Z][A-Za-z0-9_]*)\s*\(|\b([A-Z][A-Za-z0-9_]*)\s*\.")


def _trigger_handler_refs(body: Optional[str]) -> set:
    """Class names a trigger references (its handler classes). Best-effort regex:
    `new X(` or `X.method(`. Used to catch DML that the trigger delegates."""
    if not body:
        return set()
    names = set()
    for m in _TRIGGER_REF.finditer(body):
        n = m.group(1) or m.group(2)
        if n:
            names.add(n)
    return names


def active_triggers(objects: Iterable[str], target_org: Optional[str] = None) -> Dict[str, list]:
    """{'Object': [{name, apiVersion, handler_min_api}]} of active Apex triggers on
    the given objects. Used by PS509: a pre-v67 trigger's plain DML runs system mode
    regardless of the initiating action's access level (E6). `handler_min_api` is the
    minimum apiVersion among the classes the trigger DELEGATES to (its handler),
    because a v67 trigger that hands the DML to a pre-v67 handler still escalates -
    the DML runs in the handler class's mode, which the trigger's own version hides."""
    objs = set(objects)
    if not objs:
        return {}
    rows = _sf("SELECT Name, ApiVersion, Body, EntityDefinition.QualifiedApiName "
               "FROM ApexTrigger WHERE Status = 'Active'", tooling=True, target_org=target_org)
    rows = [r for r in rows if (r.get("EntityDefinition") or {}).get("QualifiedApiName") in objs]

    # one batch lookup of every referenced handler class's apiVersion
    refs: set = set()
    for r in rows:
        refs |= _trigger_handler_refs(r.get("Body"))
    class_api: Dict[str, float] = {}
    if refs:
        try:
            crows = _sf("SELECT Name, ApiVersion FROM ApexClass WHERE Name IN "
                        + _in(sorted(refs)), tooling=True, target_org=target_org)
            for c in crows:
                if c.get("ApiVersion") is not None:
                    class_api[c["Name"]] = float(c["ApiVersion"])
        except RuntimeError:
            pass                                   # handler follow is best-effort

    out: Dict[str, list] = {}
    for r in rows:
        obj = (r.get("EntityDefinition") or {}).get("QualifiedApiName")
        av = r.get("ApiVersion")
        handler_versions = [class_api[n] for n in _trigger_handler_refs(r.get("Body"))
                            if n in class_api]
        out.setdefault(obj, []).append({
            "name": r.get("Name"),
            "apiVersion": int(av) if av is not None else None,
            "handler_min_api": min(handler_versions) if handler_versions else None,
            # The cascade's actual write sink, read from the trigger's own body.
            # Without this, PS509 can only say "a legacy trigger exists"; with it we
            # can say whether that trigger really performs DML the user cannot.
            "dml_ops": _trigger_dml_ops(r.get("Body")),
        })
    return out


def _trigger_dml_ops(body: Optional[str]) -> list:
    """[(verb, object)] the trigger's own body performs. Empty means no DML was
    observed IN THE TRIGGER (it may still delegate to a handler - that is what
    handler_min_api covers), so PS509 must not claim a proven cascade."""
    if not body:
        return []
    try:
        from apex_introspect import _dml_operations, _strip_comments
        return [(verb, obj) for verb, obj, _mode in _dml_operations(_strip_comments(body))
                if obj]
    except Exception:
        return []


# Org-wide-default sharing models under which a user with object Read sees every
# record. Private / ControlledByParent make record visibility ownership- and
# sharing-dependent, which cannot be measured without running AS the user.
_PUBLIC_MODELS = {"Read", "ReadWrite", "FullAccess"}


def _derive_user_visible(system_total, sharing_model, obj_access):
    """Records the running user can see, derived HONESTLY from posture only.

    Returns (user_visible:int|None, note, cause). `None` visible means genuinely
    unmeasurable from outside the user's session - never a fabricated number.
    `cause` names WHY a gap exists so the report never conflates the two very
    different escalations:
      'crud'    - the user has no object-read at all (CRUD/FLS escalation:
                  deterministic from metadata).
      'sharing' - the user CAN read the object but record-level sharing may hide
                  rows (data-dependent; only measurable by running as the user).
      None      - no gap / fully visible.
    """
    if not obj_access.read:
        return 0, "no object read", "crud"
    if obj_access.can_see_all_records():
        return system_total, "sees all records (view/modify all)", None
    if sharing_model in _PUBLIC_MODELS:
        return system_total, f"OWD {sharing_model} - user with read sees all", None
    if sharing_model is None:
        return None, "sharing model unknown", "sharing"
    return (None, f"OWD {sharing_model} - record-sharing dependent (run as the user to measure)",
            "sharing")


def record_counts(objects: Iterable[str], sharing: Dict[str, str], perms,
                  target_org: Optional[str] = None,
                  modes: Optional[Dict[str, str]] = None) -> Dict[str, dict]:
    """Per-object record numbers for the record-reach section.

    HONESTY CONTRACT (two things this must never claim):

    1. `org_total` is a live `COUNT()` of the WHOLE object. It is NOT what the
       agent's query returns - query predicates and LIMIT are not resolved - so it
       is only ever an UPPER BOUND, never "the agent reaches N records".
    2. It is only an escalation ceiling at all when the read runs in **system
       mode**. `modes[obj] == 'user'` means every read of that object enforces
       sharing, so the agent is bounded by the running user BY CONSTRUCTION: the
       record gap is 0 and `org_total` says nothing about the agent's reach.

    `user_visible` is derived from the running user's posture (see
    _derive_user_visible) and is left None when it cannot be measured honestly.
    NO number here is ever fabricated.
    """
    modes = modes or {}
    out: Dict[str, dict] = {}
    for obj in objects:
        mode = modes.get(obj, "system")      # unknown mode -> worst case
        entry = {"org_total": None, "user_visible": None, "note": "", "gap": None,
                 "cause": None, "mode": mode}
        try:
            rows = _sf(f"SELECT COUNT(Id) c FROM {obj}", target_org=target_org)
            entry["org_total"] = int(rows[0]["c"]) if rows else 0
        except (RuntimeError, KeyError, ValueError, TypeError):
            entry["note"] = "count unavailable (object not queryable by the analysis identity)"
            out[obj] = entry
            continue

        if mode == "user":
            # Sharing is enforced on every read of this object -> the agent sees
            # exactly what the running user sees. No record escalation exists, and
            # the org total is NOT the agent's reach.
            entry["gap"] = 0
            entry["note"] = "user-mode read - the agent is bounded by the running user"
            out[obj] = entry
            continue

        visible, note, cause = _derive_user_visible(
            entry["org_total"], sharing.get(obj), perms.object_access(obj))
        entry["user_visible"] = visible
        entry["note"] = note
        entry["cause"] = cause
        if visible is not None and entry["org_total"] is not None:
            entry["gap"] = max(entry["org_total"] - visible, 0)
        out[obj] = entry
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
