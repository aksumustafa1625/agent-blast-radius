"""The join: reach x running-user permissions x GDPR labels -> findings (M3).

This is where the pieces meet. For each action's resolved reach (from
apex_introspect / flow_introspect), it diffs against the running user's
effective permissions (permission_resolver) and intersects with the org's own
ComplianceGroup labels, emitting the PS5xx authority findings.

Every reachable field of an action is treated as reaching the model: an
@InvocableMethod's outputs return to the planner (the LLM context) by design,
so `reachable && returned` is the data->model surface (Milestone 0 reasoning).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

_CLASSIFIED_TAGS = ("GDPR", "PII", "HIPAA", "PCI", "CCPA")
_DML_OPS = {"insert", "update", "upsert", "delete", "undelete", "create"}
_SEV_RANK = {"ERROR": 0, "WARN": 1, "INFO": 2}


def dedupe_findings(findings: List["Finding"]) -> List["Finding"]:
    """Collapse findings that state the same fact. One escalation can be detected
    more than once - a class may read the same object in two SOQL statements (e.g.
    a 'find all' branch and a 'find one' branch over identical fields), so each
    field is flagged once per statement. But `Invoice.DocumentNumber has no user
    FLS` is ONE fact regardless of how many queries read it. Key by (rule, where);
    when duplicates disagree on severity keep the most severe, so an ERROR is never
    masked by a WARN. First-seen order is preserved for a stable, deterministic report."""
    best: Dict[tuple, "Finding"] = {}
    order: List[tuple] = []
    for f in findings:
        key = (f.rule, f.where)
        if key not in best:
            best[key] = f
            order.append(key)
        elif _SEV_RANK.get(f.severity, 9) < _SEV_RANK.get(best[key].severity, 9):
            best[key] = f
    return [best[k] for k in order]

# Standard fields that are NOT field-level-security-permissionable: they have no
# FieldPermissions rows and are always readable when the object is accessible.
# Exempting them PREVENTS false positives (without this, can_read_field() returns
# False for Id/Name/audit fields and every read of them would be flagged PS502).
# This is deliberate and the opposite of hiding findings. The proper
# generalization is a metadata describe of each field's `isPermissionable`
# attribute (deferred); this static set covers the universal standard fields.
_ALWAYS_READABLE = {
    "Id", "Name", "OwnerId", "IsDeleted", "CreatedDate", "CreatedById",
    "LastModifiedDate", "LastModifiedById", "SystemModstamp",
}


@dataclass
class Finding:
    rule: str
    severity: str            # ERROR | WARN | INFO
    where: str
    message: str
    why: str
    fix: str


@dataclass
class AccessUnit:
    operation: str
    sobject: Optional[str]
    fields: List[str]
    fields_complete: bool
    enforces_sharing: Optional[bool]
    enforces_fls: Optional[bool]
    source: str
    # Authority Path: {field: 'returned'|'internal'|'undetermined'}. None means
    # the flow was not traced (regex backend / Flow) -> worst case is assumed.
    field_flow: Optional[Dict[str, str]] = None


# -- normalization: apex / flow reach -> AccessUnits --------------------------

def units_from_apex(reach) -> List[AccessUnit]:
    units = []
    for op in reach.operations:
        units.append(AccessUnit(
            op.operation, op.sobject, op.fields, op.fields_complete,
            op.resolved.enforces_sharing, op.resolved.enforces_fls, op.resolved.source,
            getattr(op, "field_flow", None)))
    return units


def units_from_flow(reach) -> List[AccessUnit]:
    system = reach.runs_in_system_context
    units = []
    for a in reach.accesses:
        units.append(AccessUnit(
            a.operation, a.sobject, a.fields, a.fields_complete,
            reach.enforces_sharing,          # record-level from runInMode
            (not system),                    # system context bypasses FLS
            f"Flow runInMode={reach.run_in_mode}"))
    return units


# -- Authority Path -----------------------------------------------------------

def _flow_of(unit: AccessUnit, field: str) -> str:
    """'returned' (proven to reach the model), 'internal' (proven not to), or
    'undetermined' (not traced - the worst case is assumed)."""
    if not unit.field_flow:
        return "undetermined"
    return unit.field_flow.get(field) or unit.field_flow.get(field.split(".")[-1]) \
        or "undetermined"


_PATH_NOTE = {
    "returned": "Authority Path CONFIRMED: the field's value flows to the action's "
                "@InvocableVariable output, so it reaches the model.",
    "undetermined": "Authority Path NOT TRACED (aliased/delegated/dynamic); the "
                    "worst case - that it reaches the model - is assumed.",
    "internal": "Authority Path: the field is read but every use is internal "
                "(predicate/logic); it was NOT observed flowing to the action's output.",
}


# -- classification helper ----------------------------------------------------

def _classified(classification: Dict[str, dict], full: str, short: str) -> Optional[str]:
    entry = classification.get(full) or classification.get(short)
    if not entry:
        return None
    cg = (entry.get("complianceGroup") or "").upper()
    if any(tag in cg for tag in _CLASSIFIED_TAGS):
        return entry.get("complianceGroup")
    return None


# -- core analysis ------------------------------------------------------------

def _analyze_units(action: str, units: List[AccessUnit], perms,
                   classification: Dict[str, dict],
                   object_sharing: Dict[str, str],
                   triggers_by_object: Dict[str, list] = None) -> List[Finding]:
    triggers_by_object = triggers_by_object or {}
    findings: List[Finding] = []
    for u in units:
        # PS508 - cross-class delegation whose chain goes deeper than one level
        if u.operation == "crosslink":
            findings.append(Finding(
                "PS508", "WARN", f"{action} -> {u.sobject}",
                f"Cross-class delegation: {u.source}.",
                "Reach beyond one call level is not resolved; the action's true data surface "
                "may be larger than analysed here.",
                "Review the delegated class chain, or extend analysis depth."))
            continue
        # PS509 - trigger-cascade escalation on a DML target with a legacy trigger
        if u.operation in _DML_OPS and u.sobject:
            for trig in triggers_by_object.get(u.sobject, []):
                av = trig.get("apiVersion")
                if av is not None and av < 67:
                    findings.append(Finding(
                        "PS509", "ERROR", f"{action} -> {u.sobject}",
                        f"DML ({u.operation}) on {u.sobject}, which has an active trigger "
                        f"'{trig.get('name')}' at API v{av} (< v67).",
                        "A pre-v67 trigger's plain DML runs in system mode regardless of the "
                        "initiating action's access level (verified in E6). A clean user-mode "
                        "action can cascade into writes the running user cannot perform.",
                        f"Upgrade trigger '{trig.get('name')}' to API v67+, or enforce user mode "
                        "in its handler / gate the cascade."))
            # PS503 - write escalation: system-mode DML on an object the user can't write
            need = {"insert": "create", "create": "create", "update": "edit",
                    "upsert": "edit", "delete": "delete"}.get(u.operation)
            if need and u.enforces_fls in (False, None):
                oa = perms.object_access(u.sobject)
                allowed = {"create": oa.create, "edit": oa.edit, "delete": oa.delete}[need]
                if not allowed:
                    definite = u.enforces_fls is False
                    findings.append(Finding(
                        "PS503", "ERROR" if definite else "WARN",
                        f"{action} -> {u.sobject}",
                        f"{u.operation} on {u.sobject} in "
                        f"{'system' if definite else 'possibly system'} mode; the running user "
                        f"has no {need} permission on this object ({u.source}).",
                        "In system mode Apex ignores CRUD, so the action writes an object the "
                        "running user cannot - a write escalation.",
                        f"Enforce user mode (`{u.operation} as user` / AccessLevel.USER_MODE) or "
                        "grant the permission intentionally and document it."))
            continue
        if u.operation != "read" or not u.sobject:
            continue

        # PS501 - record-level escalation
        if u.enforces_sharing in (False, None):
            if object_sharing.get(u.sobject) == "Private" and not perms.sees_all_records(u.sobject):
                definite = u.enforces_sharing is False
                findings.append(Finding(
                    "PS501", "ERROR" if definite else "WARN",
                    f"{action} -> {u.sobject}",
                    f"Potential record-scope expansion: reads {u.sobject} in "
                    f"{'system' if definite else 'possibly system'} mode on a Private object ({u.source}).",
                    "The running user is subject to record-level sharing this operation does not "
                    "enforce. Query predicates and application-level ownership checks are NOT "
                    "analyzed statically, so this flags a boundary to review, not a proven leak.",
                    "Enforce user mode (with sharing + WITH USER_MODE) or upgrade the class to API "
                    "v67; if system mode is intended, confirm the query restricts records by owner/input."))

        # field-level: PS506 / PS502 / PS505
        for fld in u.fields:
            short = fld.split(".")[-1]
            if short in _ALWAYS_READABLE:
                continue
            full = fld if "." in fld else f"{u.sobject}.{fld}"
            tag = _classified(classification, full, fld)
            user_sees = perms.can_read_field(full) or perms.can_read_field(fld)
            fls_enforced = u.enforces_fls is True
            beyond_user = (not fls_enforced) and (not user_sees)
            # If FLS is enforced and the user can't see it, user mode BLOCKS the
            # read (a user-mode query on an inaccessible field throws / treats it
            # as absent - verified in experiment E2b, "No such column"). It is not
            # silently stripped (that is Security.stripInaccessible, a separate
            # mechanism). Either way the field does not reach the model.
            reaches_model = (not fls_enforced) or user_sees

            # Authority Path: does the value actually flow to the action's output?
            path = _flow_of(u, fld)
            flows_out = path != "internal"          # 'internal' is PROVEN not to
            reaches_model = reaches_model and flows_out

            if beyond_user and tag:
                # A field only used internally is still a system-mode over-read,
                # but it was not observed reaching the model -> WARN, not ERROR.
                sev = "WARN" if path == "internal" else "ERROR"
                verb = ("is read in system mode and reaches the model"
                        if path == "returned" else
                        "is read in system mode but was not observed reaching the model"
                        if path == "internal" else
                        "is read in system mode and may reach the model")
                findings.append(Finding(
                    "PS506", sev, f"{action} -> {full}",
                    f"GDPR/PII field {full} {verb}, but the running user has no FLS on it.",
                    f"ComplianceGroup {tag}. A field the running user cannot see can reach the "
                    f"LLM and the end user's screen. {_PATH_NOTE[path]}",
                    "Remove the field from the query/output, or enforce FLS "
                    "(WITH USER_MODE / Security.stripInaccessible)."))
            elif beyond_user:
                sev = "WARN" if path == "internal" else "ERROR"
                findings.append(Finding(
                    "PS502", sev, f"{action} -> {full}",
                    f"Field {full} is read in system mode; the running user has no FLS on it.",
                    f"In system mode Apex ignores FLS, so the field's data can reach the agent. "
                    f"{_PATH_NOTE[path]}",
                    "Enforce FLS (WITH USER_MODE / Security.stripInaccessible)."))
            elif tag and reaches_model:
                findings.append(Finding(
                    "PS505", "WARN", f"{action} -> {full}",
                    f"Classified field {full} ({tag}) is reachable and returns to the model.",
                    f"Classified data entering the LLM context is a data-minimization concern "
                    f"even when the running user is authorized to see it. {_PATH_NOTE[path]}",
                    "Confirm this field is required for the action's stated purpose."))

        # PS504 - honest unknown
        if not u.fields_complete:
            findings.append(Finding(
                "PS504", "WARN", f"{action} -> {u.sobject or '?'}",
                f"Reach for this operation could not be fully determined ({u.source}).",
                "A silent false-clean is worse than an honest unknown.",
                "Review manually; consider WITH USER_MODE so runtime enforces access."))
    # one escalation = one finding, even when two SOQL statements read the same field
    return dedupe_findings(findings)


def analyze_apex(reach, perms, classification, object_sharing,
                 triggers_by_object=None) -> List[Finding]:
    findings = _analyze_units(reach.class_name, units_from_apex(reach),
                              perms, classification, object_sharing, triggers_by_object)
    if reach.api_version is not None and reach.api_version < 67:
        findings.append(Finding(
            "PS511", "INFO", f"{reach.class_name} (API v{reach.api_version})",
            "Custom action class predates API v67 (secure-by-default).",
            "Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.",
            "Plan a migration to API v67 and re-review."))
    return findings


def analyze_flow(reach, perms, classification, object_sharing,
                 triggers_by_object=None) -> List[Finding]:
    findings = _analyze_units(reach.name, units_from_flow(reach),
                              perms, classification, object_sharing, triggers_by_object)
    if reach.run_in_mode == "SystemModeWithoutSharing":
        findings.append(Finding(
            "PS510", "ERROR", f"{reach.name} (Flow)",
            "Flow runs in System Mode without Sharing.",
            "Record-level and FLS enforcement are bypassed by configuration, "
            "invisible in the Agent Builder UI.",
            "Set runInMode to DefaultMode unless system context is justified and documented."))
    elif reach.run_in_mode == "SystemModeWithSharing":
        findings.append(Finding(
            "PS510", "WARN", f"{reach.name} (Flow)",
            "Flow runs in System Mode with Sharing (FLS/CRUD not enforced).",
            "Sharing is honored but field- and object-level security are not.",
            "Confirm the flow does not return fields the running user lacks FLS on."))
    return findings


def units_from_prompt(reach) -> List[AccessUnit]:
    """A prompt template's record merge is evaluated in the running user's
    context, so it is FLS- and sharing-enforced (user mode). It is therefore not
    a field escalation by itself - but classified data it pulls still enters the
    model (PS505), and it reaches the model by design."""
    units = []
    for full in reach.fields:                       # "Object.Field"
        obj = full.split(".")[0]
        units.append(AccessUnit("read", obj, [full], True, True, True,
                                "prompt template merge (user mode)"))
    enumerated = {f.split(".")[0] for f in reach.fields}
    for obj in reach.objects:                        # whole-record merge / unenumerated
        if obj not in enumerated or not reach.fields_complete:
            units.append(AccessUnit("read", obj, [], False, True, True,
                                    "prompt template whole-record merge"))
    return units


def analyze_prompt(reach, perms, classification, object_sharing) -> List[Finding]:
    """Findings for a GenAiPromptTemplate action. PS505 covers classified fields
    that reach the model; PS513 covers the latent surface only an INACTIVE
    template version reaches (re-activatable, shipped in the metadata today)."""
    findings = _analyze_units(reach.name, units_from_prompt(reach),
                              perms, classification, object_sharing)

    extra = list(reach.inactive_extra_fields) + [f"{o}.*" for o in reach.inactive_extra_objects]
    if extra:
        classified = [f for f in reach.inactive_extra_fields
                      if _classified(classification, f, f.split(".")[-1])]
        findings.append(Finding(
            "PS513", "ERROR" if classified else "WARN",
            f"{reach.name} (prompt template)",
            f"An inactive version of this prompt template reaches data the active version does "
            f"not: {', '.join(sorted(extra))}.",
            "Old template versions ship in the metadata and can be re-activated without a code "
            "review, so this is a latent data-to-model surface"
            + (f" — including classified field(s): {', '.join(sorted(classified))}" if classified else "")
            + ".",
            "Delete unused template versions, or confirm the inactive version is intended."))
    return findings
