"""The join: reach x running-user permissions x the org's compliance labels -> findings (M3).

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


def _analyzer_build() -> str:
    """The digest of the analyzer's own source, for the version-bound half of
    PS504. Imported lazily because `report` is a heavier module than the rules
    need, and it is deliberately NOT a hand-maintained constant: a version string
    someone must remember to bump is exactly the mechanism that lies (see the
    docstring on report.analyzer_version)."""
    try:
        from report import analyzer_version
        return analyzer_version()[:12]
    except Exception:
        return "unknown"


# PS504 has one severity and one count, but three different people close it. Which
# one is not cosmetic: "make the query static" is useless advice for an aggregate
# select the customer wrote correctly, and "wait for a new analyzer" is useless
# advice for a query assembled at runtime. One undifferentiated honest-unknown
# sends half of them to the wrong desk, so the cause and its OWNER are stated.
#
# The 'analyzer' text is bound to the analyzer build on purpose. "This shape is
# not modelled" is true of a build, not of the world; unbound, every report ever
# issued would be falsified the day the shape IS modelled. Bound, an old report
# stays exactly as true as it was the day it was produced.
_UNRESOLVED_PREAMBLE = (
    "A silent false-clean is worse than an honest unknown, so this is counted as "
    "unresolved rather than passed.")

_UNRESOLVED_WHY = {
    "code": (
        "The query does not exist until runtime, so no static analysis - this one "
        "or any other - can enumerate what it reaches. It stays unresolved until "
        "the code changes."),
    "analyzer": (
        "This one is OUR limit, not a property of your code: the reach is written "
        "out in the source and analyzer build {build} does not model this shape. "
        "Stated as of that build - a later one may resolve it, and this report is "
        "not falsified when it does."),
}

_UNRESOLVED_FIX = {
    "code": ("Yours to close: make the query static, or add WITH USER_MODE so the "
             "runtime enforces this user's access whatever the query resolves to."),
    "analyzer": ("Ours to close - there is nothing to change in your code. Review "
                 "this operation by hand, or re-run on an analyzer build that "
                 "models the shape."),
}

_UNRESOLVED_CAUSE = {
    "code": "the query is assembled at runtime",
    "analyzer": "this analyzer does not model the shape",
}

_UNCLASSIFIED_WHY = (
    "Which side this one belongs to is not classified, so no owner is claimed "
    "for it.")
_UNCLASSIFIED_FIX = (
    "Review manually; consider WITH USER_MODE so runtime enforces access.")


def _ps504(where: str, causes) -> Finding:
    """One PS504 for one (action, object), naming every cause behind it.

    `causes` is an ordered, kind-deduplicated list of (kind, reason).

    Why this merges instead of letting dedupe_findings pick one: that function
    keys on (rule, where) and keeps whichever arrived first, which was harmless
    while every PS504 said the same generic sentence. Now that a PS504 names an
    OWNER, dropping the second cause would attribute one party's work to the
    other in the tool's own confident voice - the fabricated attribution this
    rule exists to avoid. Merging keeps the count identical (still one finding
    per action and object, so the Index's U bucket is untouched and the frozen
    specification still describes it) while telling the truth about both.
    """
    build = _analyzer_build()
    labels = [_UNRESOLVED_CAUSE.get(k, "cause not classified") for k, _r in causes]
    # Some extractor notes are written as "PS504: ..." for their own logs. The
    # finding already carries the rule id, so repeating it inside the reason reads
    # like a second finding.
    reasons = "; ".join(r.split("PS504: ", 1)[-1] for _k, r in causes if r)
    message = ("Reach for this operation could not be fully determined - "
               + " and ".join(labels) + (f" ({reasons})." if reasons else "."))
    # The preamble is the same sentence for every cause, so it is said once even
    # when two causes merge - repeating it reads like two separate verdicts.
    why = " ".join([_UNRESOLVED_PREAMBLE] +
                   [_UNRESOLVED_WHY[k].format(build=build) if k in _UNRESOLVED_WHY
                    else _UNCLASSIFIED_WHY for k, _r in causes])
    fix = " ".join(_UNRESOLVED_FIX.get(k, _UNCLASSIFIED_FIX) for k, _r in causes)
    return Finding("PS504", "WARN", where, message, why, fix)

_CLASSIFIED_TAGS = ("GDPR", "PII", "HIPAA", "PCI", "CCPA")
# `publish` is here on purpose: publishing a platform event needs Create on the
# event object and fires that event's trigger, so it is a write with a cascade -
# exactly what PS503 and PS509 already reason about.
_DML_OPS = {"insert", "update", "upsert", "delete", "undelete", "create", "publish"}
# Which object permission a DML verb requires (shared by PS503 and PS509).
_DML_NEED = {"insert": "create", "create": "create", "update": "edit",
             "upsert": "edit", "delete": "delete", "publish": "create"}
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
    # PS520/521/522 only: the traced data->prompt hops, structured so the report can
    # DRAW the path instead of only describing it. Keys: field, action, output,
    # variable, set_line, prompt_line, tag, user_sees. None for every other rule.
    chain: Optional[dict] = None


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
    # 'code' | 'analyzer' | None - who has to act on this unresolved reach.
    # Only meaningful when fields_complete is False.
    unresolved_kind: Optional[str] = None
    # The extractor's own reason ("aggregate/function select - fields not
    # enumerated"). PS504 used to print `source` here, which is the MODE
    # resolution's origin ("API v<=66 system-mode default") - true, but not an
    # answer to "why could you not resolve the reach", and it read like one.
    note: Optional[str] = None


# -- normalization: apex / flow reach -> AccessUnits --------------------------

def units_from_apex(reach) -> List[AccessUnit]:
    units = []
    for op in reach.operations:
        units.append(AccessUnit(
            op.operation, op.sobject, op.fields, op.fields_complete,
            op.resolved.enforces_sharing, op.resolved.enforces_fls, op.resolved.source,
            getattr(op, "field_flow", None),
            getattr(op, "unresolved_kind", None),
            getattr(op, "note", None)))
    return units


def units_from_flow(reach) -> List[AccessUnit]:
    # Both axes come from the flow's RESOLVED context (type first, then the
    # runInMode tag - see flow_introspect.resolve_mode). Either may be None: a
    # flow whose context the caller decides is an honest unknown on both axes,
    # and None is what makes PS501/PS503 say "possibly" and the field rules cap
    # at WARN instead of claiming a proven escalation - or a clean.
    units = []
    for a in reach.accesses:
        units.append(AccessUnit(
            a.operation, a.sobject, a.fields, a.fields_complete,
            reach.enforces_sharing,          # record-level axis
            reach.enforces_fls,              # CRUD/FLS axis (system bypasses it)
            reach.mode_source))
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
                   triggers_by_object: Dict[str, list] = None,
                   sanitizer: Dict = None,
                   calculated: set = None) -> List[Finding]:
    triggers_by_object = triggers_by_object or {}
    findings: List[Finding] = []
    # where -> (index in `findings`, [(kind, reason), ...]). See _ps504: two causes
    # on the same object must merge into the one finding dedupe would have kept,
    # not silently lose whichever arrived second.
    ps504_at: Dict[str, tuple] = {}

    # Security.stripInaccessible is the platform's real FLS sanitizer. We cannot
    # prove WHICH list reaches the sink without alias tracking, so it never clears
    # a finding - it moves it from "proven escalation" to "sanitizer present, path
    # not proven" (severity = proof level, the same discipline as path=='internal').
    #
    # The gate is result_used ALONE, not read_sanitized. It used to require
    # AccessType.READABLE, which made us claim a proven escalation whenever a
    # developer used UPDATABLE/CREATABLE on a read path. The runtime oracle refuted
    # that in-org, on both branches of the only axis that could differ:
    #   user without object Edit -> the call THROWS ("No access to entity")
    #   user with object Edit    -> the field IS stripped ("row was retrieved via
    #                               SOQL without querying the requested field")
    # It generalises: Salesforce FLS cannot grant Edit without Read, so
    # "not readable" is a subset of "not updatable"/"not creatable" - any AccessType
    # strips at least what READABLE would. So a used decision never lets the field
    # through, whatever the AccessType, and claiming otherwise was a false positive.
    strips_reads = bool(sanitizer and sanitizer.get("result_used"))
    if sanitizer and not sanitizer.get("result_used"):
        # A stripInaccessible whose SObjectAccessDecision is never read is a no-op:
        # the original, unsanitized records are what the code goes on to use.
        findings.append(Finding(
            "PS512", "ERROR", f"{action} (Security.stripInaccessible)",
            "Security.stripInaccessible is called but its SObjectAccessDecision is "
            "never read (no .getRecords()), so nothing is actually sanitized.",
            "stripInaccessible does not mutate the list you pass in - it RETURNS a "
            "decision holding sanitized copies. Discarding it leaves the original, "
            "unsanitized records in use, so the code looks protected but is not.",
            "Use the returned decision: "
            "`List<X> safe = Security.stripInaccessible(AccessType.READABLE, recs).getRecords();` "
            "and pass `safe` onward."))
    elif sanitizer and not sanitizer.get("read_sanitized"):
        # Measured, not assumed - and the opposite of what this rule used to say.
        # The wrong AccessType on a read path is a RELIABILITY bug, not a leak: the
        # oracle showed it either throws outright or over-strips. Calling it a leak
        # was a false positive; calling it harmless would be the mirror error.
        findings.append(Finding(
            "PS512", "WARN", f"{action} (Security.stripInaccessible)",
            f"Security.stripInaccessible is used with AccessType "
            f"{'/'.join(sanitizer.get('access_types') or [])} on a READ path, which is "
            "the wrong check for this data - though it errs safe.",
            "Measured in-org: a CREATABLE/UPDATABLE decision does NOT leak the field. "
            "It throws outright ('No access to entity') when the running user lacks "
            "object Edit, and otherwise strips the field anyway - Salesforce cannot "
            "grant Edit without Read, so anything unreadable is also un-updatable. "
            "The risk is an action that breaks, or quietly drops fields the user was "
            "entitled to see, not one that leaks.",
            "Use AccessType.READABLE for records the action returns, so the check "
            "matches the intent and only unreadable fields are removed."))
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
                hav = trig.get("handler_min_api")
                if av is not None and av < 67:
                    # Severity = proof level. A legacy trigger's mere EXISTENCE is a
                    # boundary, not an escalation: it may not perform DML at all, or
                    # may write only what the user could write anyway. Claim ERROR
                    # only when the trigger's own body performs DML on an object the
                    # running user has no permission for - that is the proven cascade.
                    escalating = []
                    for verb, tobj in (trig.get("dml_ops") or []):
                        need = _DML_NEED.get(verb)
                        if not need:
                            continue
                        oa = perms.object_access(tobj)
                        if not {"create": oa.create, "edit": oa.edit, "delete": oa.delete}[need]:
                            escalating.append(f"{verb} {tobj}")
                    if escalating:
                        findings.append(Finding(
                            "PS509", "ERROR", f"{action} -> {u.sobject}",
                            f"DML ({u.operation}) on {u.sobject} fires trigger "
                            f"'{trig.get('name')}' (API v{av} < v67), whose own body performs "
                            f"{', '.join(escalating)} — which the running user cannot.",
                            "A pre-v67 trigger's plain DML runs in system mode regardless of the "
                            "initiating action's access level (verified in E6). A clean user-mode "
                            "action cascades into a write the running user cannot perform. The "
                            "write sink was read from the trigger's own body, so this is proven, "
                            "not inferred from the version alone.",
                            f"Upgrade trigger '{trig.get('name')}' to API v67+, enforce user mode "
                            "in it (`insert as user`), or gate the cascade."))
                    else:
                        observed = trig.get("dml_ops")
                        why = ("its body performs DML the running user could perform anyway"
                               if observed else
                               "no DML was observed in its own body (it may delegate to a "
                               "handler, or perform none)")
                        findings.append(Finding(
                            "PS509", "WARN", f"{action} -> {u.sobject}",
                            f"DML ({u.operation}) on {u.sobject} fires trigger "
                            f"'{trig.get('name')}' at API v{av} (< v67) — a legacy cascade "
                            "boundary, but no escalating write was proven.",
                            f"A pre-v67 trigger runs its DML in system mode, so this is a real "
                            f"boundary to review; however {why}, so this is flagged as a boundary "
                            "rather than a proven escalation.",
                            f"Review what '{trig.get('name')}' writes downstream; upgrade it to "
                            "API v67+ to remove the legacy default entirely."))
                elif hav is not None and hav < 67:
                    # The trigger itself is v67+, but it DELEGATES to a pre-v67 handler
                    # class. If that handler performs the DML, it runs in system mode
                    # regardless of the trigger's version - the trigger version hides it.
                    findings.append(Finding(
                        "PS509", "WARN", f"{action} -> {u.sobject}",
                        f"DML ({u.operation}) on {u.sobject}: the active trigger "
                        f"'{trig.get('name')}' is v{av if av is not None else '?'} but delegates "
                        f"to a pre-v67 handler class (v{hav:g}).",
                        "A v67 trigger looks safe, but a handler class it calls runs its own DML "
                        "in the handler's mode; a pre-v67 handler defaults to system mode, so the "
                        "cascade can still escalate. The trigger's own version hides this.",
                        f"Verify which class performs the DML; upgrade the pre-v67 handler to "
                        "API v67+ or enforce user mode in it."))
            # PS503 - write escalation: system-mode DML on an object the user can't write
            need = _DML_NEED.get(u.operation)
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
        # PS504 - honest unknown: an incomplete read (dynamic SOQL, SOSL without
        # RETURNING, unresolved reach) is surfaced even when the object itself is
        # unknown, so it is never silently dropped. Fires before the sobject guard
        # below (an op with no known object would otherwise be skipped entirely).
        # PS516 - a FORMULA field in the reach is an unresolved reach.
        #
        # A formula's value is COMPUTED from other fields, and this analyzer does not
        # resolve which. So the user's FLS on the formula does NOT bound what its value
        # carries: a formula the user is allowed can echo a field they are not. It is the
        # one channel that can survive a v67 user-mode read - user mode enforces FLS on
        # the formula the user CAN see, not on what it references, which is why this is
        # reported even when the read is otherwise bounded.
        #
        # WARN, and worded as OUR limit, not as a leak. Whether a formula actually
        # carries a field's value past FLS is a claim about the PLATFORM that is not
        # measured here (the fixture that would settle it could not be deployed - see
        # CLAUDE.md §9). "We do not resolve what this formula reads" is true either way.
        # Claiming the leak would be exactly the believed-premise mistake this tool has
        # already been caught making.
        if u.operation == "read" and calculated:
            for fld in u.fields:
                full = fld if "." in fld else f"{u.sobject}.{fld}"
                if full not in calculated:
                    continue
                findings.append(Finding(
                    "PS516", "WARN", f"{action} -> {full}",
                    "This field is a FORMULA; the fields it reads are not resolved here.",
                    "A formula's value is computed from other fields, so the running "
                    "user's FLS on THIS field does not bound what its value carries - a "
                    "formula they are allowed can echo one they are not. Unlike every "
                    "other reach, this is not settled by user mode: a v67 read enforces "
                    "FLS on the formula, not on its inputs. Reported as an unresolved "
                    "reach, not as a proven leak - what the platform does here is not "
                    "measured.",
                    f"Open {full}'s formula and check whether any field it references is "
                    "invisible to this user or carries a compliance label."))

        if u.operation == "read" and not u.fields_complete:
            # The rule id stays PS504 and the count stays identical - the Index's U
            # bucket is defined as the PS504 count (spec 3.1) and that definition is
            # frozen. What changes is that the report now says WHY it could not be
            # resolved and WHOSE job it is, which moves no verdict and no number.
            where = f"{action} -> {u.sobject or '?'}"
            cause = (u.unresolved_kind, u.note or u.source)
            slot = ps504_at.get(where)
            if slot is None:
                ps504_at[where] = (len(findings), [cause])
                findings.append(_ps504(where, [cause]))
            elif u.unresolved_kind not in {k for k, _r in slot[1]}:
                # A second, DIFFERENT cause on the same object. Rewrite the finding
                # in place rather than appending: appending would raise U for this
                # org, and the number is what the specification froze.
                idx, causes = slot
                causes.append(cause)
                findings[idx] = _ps504(where, causes)

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
            # None = the operation's run context is undetermined (a Flow whose
            # caller decides it). Not clean - the field may escape - but not
            # PROVEN either, so below it caps the severity at WARN and the
            # message says "possibly", exactly as PS501/PS503 already do.
            fls_unknown = u.enforces_fls is None
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

            # A READABLE stripInaccessible whose records are used may already strip
            # this field. We cannot prove the sanitized list (not the original) is
            # what flows to the sink, so this is an honest unknown, not a clean:
            # it caps the severity at WARN and says so, instead of asserting a
            # proven escalation on code that is probably correct.
            san_note = (" This class calls Security.stripInaccessible(READABLE) and uses the "
                        "result, which may already strip this field; the analyzer cannot prove "
                        "whether the sanitized list or the original reaches the output, so this "
                        "is reported as unproven rather than clean." if strips_reads else "")

            mode_note = (" The run context of this operation is UNDETERMINED (see its "
                         "PS504), so this is an unproven boundary, not a proven "
                         "escalation." if fls_unknown else "")
            mode_word = "possibly system" if fls_unknown else "system"

            if beyond_user and tag:
                # A field only used internally is still a system-mode over-read,
                # but it was not observed reaching the model -> WARN, not ERROR.
                sev = "WARN" if (path == "internal" or strips_reads or fls_unknown) else "ERROR"
                verb = (f"is read in {mode_word} mode and reaches the model"
                        if path == "returned" else
                        f"is read in {mode_word} mode but was not observed reaching the model"
                        if path == "internal" else
                        f"is read in {mode_word} mode and may reach the model")
                findings.append(Finding(
                    "PS506", sev, f"{action} -> {full}",
                    f"Regulated field {full} {verb}, but the running user has no FLS on it.",
                    f"ComplianceGroup {tag}. A field the running user cannot see can reach the "
                    f"LLM and the end user's screen. {_PATH_NOTE[path]}{san_note}{mode_note}",
                    "Remove the field from the query/output, or enforce FLS "
                    "(WITH USER_MODE / Security.stripInaccessible)."))
            elif beyond_user:
                sev = "WARN" if (path == "internal" or strips_reads or fls_unknown) else "ERROR"
                findings.append(Finding(
                    "PS502", sev, f"{action} -> {full}",
                    f"Field {full} is read in {mode_word} mode; the running user has no FLS on it.",
                    f"In system mode Apex ignores FLS, so the field's data can reach the agent. "
                    f"{_PATH_NOTE[path]}{san_note}{mode_note}",
                    "Enforce FLS (WITH USER_MODE / Security.stripInaccessible)."))
            elif tag and reaches_model:
                findings.append(Finding(
                    "PS505", "WARN", f"{action} -> {full}",
                    f"Classified field {full} ({tag}) is reachable and returns to the model.",
                    f"Classified data entering the LLM context is a data-minimization concern "
                    f"even when the running user is authorized to see it. {_PATH_NOTE[path]}",
                    "Confirm this field is required for the action's stated purpose."))
    # one escalation = one finding, even when two SOQL statements read the same field
    return dedupe_findings(findings)


def analyze_apex(reach, perms, classification, object_sharing,
                 triggers_by_object=None, calculated=None) -> List[Finding]:
    findings = _analyze_units(reach.class_name, units_from_apex(reach),
                              perms, classification, object_sharing, triggers_by_object,
                              sanitizer=getattr(reach, "sanitizer", None),
                              calculated=calculated)

    # PS514 - async/event/callout hand-off: the transaction ends here and the work
    # continues in a context this analyzer does not follow. The agent's real blast
    # radius may be LARGER than this report. Never silently dropped.
    # A platform event is the one hand-off we now partly follow: the publish itself
    # is modelled as a write (PS503) and an APEX subscriber trigger is analysed like
    # any other cascade (PS509). Say exactly that, and scope the unknown to what is
    # genuinely still unfollowed - a Flow/process subscriber or an external consumer.
    # A blanket "not analysed" here would overstate our own blindness, which is the
    # same honesty failure as understating it.
    events = sorted({op.sobject for op in reach.operations
                     if op.operation == "publish" and op.sobject})
    for kind in getattr(reach, "async_handoffs", []) or []:
        if kind == "platform event" and events:
            named = ", ".join(events)
            has_apex_sub = any((triggers_by_object or {}).get(e) for e in events)
            covered = ("Its Apex subscriber trigger IS analysed above"
                       if has_apex_sub else
                       "No Apex subscriber trigger exists on it")
            findings.append(Finding(
                "PS514", "WARN", f"{reach.class_name} (platform event: {named})",
                f"This action publishes {named}. The publish is analysed as a write; "
                "any Flow, process, or external subscriber is NOT.",
                f"{covered}, but a platform event can also be consumed by a Flow, a "
                "process, or an off-platform subscriber, each running in its own "
                "transaction as a different user. Publishing is how an agent starts "
                "work it could not do inline, so the true blast radius can be larger "
                "than this report. An honest unknown edge, not a proven leak.",
                f"List the subscribers of {named} (Flow, process, and external) and "
                "review each as its own entry point."))
            continue
        findings.append(Finding(
            "PS514", "WARN", f"{reach.class_name} ({kind})",
            f"This action hands off to a {kind}; the reach of that separate execution "
            "context is NOT analysed here.",
            "Async and event-driven work runs in its own transaction, often in system "
            "mode and under a different user, so the agent's true data surface can be "
            "larger than the reach shown in this report. This is an honest unknown "
            "edge, not a proven leak.",
            f"Review what the {kind} does downstream (subscriber, job, or endpoint) and "
            "scan the classes it invokes as their own entry points."))

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
    # PS510 is keyed on the RESOLVED context, not on the runInMode tag alone. A
    # record-triggered flow or a Process Builder process has no tag and still runs
    # in system context without sharing (flow_introspect.resolve_mode; platform-doc,
    # unmeasured in-org). Keying on the tag was how such a flow used to resolve to
    # user mode with sharing - a silent false clean.
    system, sharing, source = reach.mode
    by_tag = source.startswith("Flow runInMode=")     # vs. decided by the flow's type
    if system is True and sharing is False:
        findings.append(Finding(
            "PS510", "ERROR", f"{reach.name} (Flow)",
            "Flow runs in System Mode without Sharing."
            + ("" if by_tag else f" ({source})"),
            "Record-level and FLS enforcement are bypassed by configuration, "
            "invisible in the Agent Builder UI."
            + ("" if by_tag else
               " This is the platform's rule for this flow type, not a tag the author "
               "set, so there is no tag to change; it is stated as documented "
               "(platform-doc) and has not yet been measured in-org by this project."),
            "Set runInMode to DefaultMode unless system context is justified and documented."
            if by_tag else
            "Review every record element against the running user; a triggered flow "
            "cannot be switched to user context, so move the agent-facing read into an "
            "autolaunched flow or a v67 Apex action that runs as the user."))
    elif system is True:
        findings.append(Finding(
            "PS510", "WARN", f"{reach.name} (Flow)",
            "Flow runs in System Mode with Sharing (FLS/CRUD not enforced).",
            "Sharing is honored but field- and object-level security are not.",
            "Confirm the flow does not return fields the running user lacks FLS on."))
    elif system is None:
        # Honest unknown: no tag, and the type's context is decided by whoever
        # calls it. Said out loud (PS504) so it can never be read as clean; the
        # per-field PS502/PS506 above are capped at WARN for the same reason.
        findings.append(Finding(
            "PS504", "WARN", f"{reach.name} (Flow run context)",
            f"The run context of this Flow could not be determined ({source}).",
            "Without a runInMode tag an autolaunched flow runs in the context of its "
            "caller - user context from a user, the caller's own context from Apex, "
            "system context from a process. Which one the agent's invocation "
            "produces is not established here, so every read and write in this flow "
            "is reported as possibly system mode. A silent false-clean is worse than "
            "an honest unknown.",
            "Yours to close: set runInMode explicitly (DefaultMode to run as the "
            "user) so the context is declared in the metadata rather than inherited."))
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
            # 'code': a whole-record merge names no fields anywhere in the source -
            # what it carries is decided by the template's own configuration, not by
            # anything a better extractor could read out of it.
            units.append(AccessUnit("read", obj, [], False, True, True,
                                    "prompt template whole-record merge",
                                    None, "code",
                                    "whole-record merge - no field list in the template"))
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
