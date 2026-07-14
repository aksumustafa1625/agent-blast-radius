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

# Fields that are not FLS-controlled (always readable when the object is), so
# flagging them as "invisible to the user" would be a false positive.
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


# -- normalization: apex / flow reach -> AccessUnits --------------------------

def units_from_apex(reach) -> List[AccessUnit]:
    units = []
    for op in reach.operations:
        units.append(AccessUnit(
            op.operation, op.sobject, op.fields, op.fields_complete,
            op.resolved.enforces_sharing, op.resolved.enforces_fls, op.resolved.source))
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
                   object_sharing: Dict[str, str]) -> List[Finding]:
    findings: List[Finding] = []
    for u in units:
        if u.operation != "read" or not u.sobject:
            continue

        # PS501 - record-level escalation
        if u.enforces_sharing in (False, None):
            if object_sharing.get(u.sobject) == "Private" and not perms.sees_all_records(u.sobject):
                definite = u.enforces_sharing is False
                findings.append(Finding(
                    "PS501", "ERROR" if definite else "WARN",
                    f"{action} -> {u.sobject}",
                    f"Reads {u.sobject} in {'system' if definite else 'possibly system'} mode; "
                    f"object sharing model is Private ({u.source}).",
                    "The running user is subject to record-level sharing this action bypasses; "
                    "it can surface records the user cannot see.",
                    "Enforce user mode (with sharing + WITH USER_MODE) or upgrade the class to API v67."))

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
            # If FLS is enforced and the user can't see it, user mode strips the
            # field - it never reaches the model.
            reaches_model = (not fls_enforced) or user_sees

            if beyond_user and tag:
                findings.append(Finding(
                    "PS506", "ERROR", f"{action} -> {full}",
                    f"GDPR/PII field {full} is read in system mode and returned to the model, "
                    f"but the running user has no FLS on it.",
                    f"ComplianceGroup {tag}. A field the running user cannot see can reach the "
                    "LLM and the end user's screen.",
                    "Remove the field from the query/output, or enforce FLS "
                    "(WITH USER_MODE / Security.stripInaccessible)."))
            elif beyond_user:
                findings.append(Finding(
                    "PS502", "ERROR", f"{action} -> {full}",
                    f"Field {full} is read in system mode; the running user has no FLS on it.",
                    "In system mode Apex ignores FLS, so the field's data can reach the agent.",
                    "Enforce FLS (WITH USER_MODE / Security.stripInaccessible)."))
            elif tag and reaches_model:
                findings.append(Finding(
                    "PS505", "WARN", f"{action} -> {full}",
                    f"Classified field {full} ({tag}) is reachable and returns to the model.",
                    "Classified data entering the LLM context is a data-minimization concern "
                    "even when the running user is authorized to see it.",
                    "Confirm this field is required for the action's stated purpose."))

        # PS504 - honest unknown
        if not u.fields_complete:
            findings.append(Finding(
                "PS504", "WARN", f"{action} -> {u.sobject or '?'}",
                f"Reach for this operation could not be fully determined ({u.source}).",
                "A silent false-clean is worse than an honest unknown.",
                "Review manually; consider WITH USER_MODE so runtime enforces access."))
    return findings


def analyze_apex(reach, perms, classification, object_sharing) -> List[Finding]:
    findings = _analyze_units(reach.class_name, units_from_apex(reach),
                              perms, classification, object_sharing)
    if reach.api_version is not None and reach.api_version < 67:
        findings.append(Finding(
            "PS511", "INFO", f"{reach.class_name} (API v{reach.api_version})",
            "Custom action class predates API v67 (secure-by-default).",
            "Pre-v67 classes keep legacy execution semantics indefinitely until upgraded.",
            "Plan a migration to API v67 and re-review."))
    return findings


def analyze_flow(reach, perms, classification, object_sharing) -> List[Finding]:
    findings = _analyze_units(reach.name, units_from_flow(reach),
                              perms, classification, object_sharing)
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
