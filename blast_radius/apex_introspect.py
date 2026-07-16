"""Extract an Apex class's execution-resolved data reach (Agent Blast Radius, M2).

This encodes the precedence law derived empirically in Milestone 0 (E1-E3):

    For a plain SOQL/DML operation, execution mode resolves as
        1. explicit operation clause  (WITH USER_MODE / SYSTEM_MODE /
           SECURITY_ENFORCED, or AccessLevel.* on Database/DML)
        2. apiVersion default         (>= 67 user mode; <= 66 system mode)
        3. class sharing declaration  (governs record access under system mode)

Two enforcement axes are tracked separately, because they behave differently:
    * enforces_sharing -> record-level visibility
    * enforces_fls     -> object/field CRUD + field-level security
Each is True / False / None, where None means "undetermined" (e.g. a class with
no declaration inherits its caller's context - proven in E2). Undetermined is
reported honestly, never silently treated as safe.

Parsing strategy: `parse_apex` uses a REAL parse tree by default - the ANTLR
apex-parser via ast_extract.js (see apex_ast.py) - and falls back to the
disciplined regex extractor below only when Node/the parser package is absent or
a file fails to parse. Both backends emit the same reach; the precedence law
(_resolve / _resolve_dml_fls) resolves execution mode identically regardless of
backend. The regex extractor reads apiVersion from the paired .cls-meta.xml, the
sharing keyword from the class header, and inline `[SELECT ...]` queries with
their mode clauses; dynamic SOQL and subqueries it cannot enumerate are flagged
undetermined (PS504), never guessed. The AST backend resolves these structurally
(correct on multiline queries, subqueries, and SOQL-shaped text in strings or
comments). `parse_apex_source` remains the pure regex entry point (inline source,
no file); `parse_apex(path, backend=...)` selects auto|ast|regex.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

import apex_ast

_CLASS_DECL = re.compile(
    r"\b(?:public|private|global|protected)\b[^;{]*?"
    r"\b(with|without|inherited)\s+sharing\s+class\b",
    re.IGNORECASE,
)
_SOQL = re.compile(r"\[\s*SELECT\b(.*?)\bFROM\b\s+([A-Za-z0-9_]+)(.*?)\]",
                   re.IGNORECASE | re.DOTALL)
_DYNAMIC = re.compile(r"\bDatabase\.(?:query|queryWithBinds|countQuery|getQueryLocator)\s*\(",
                      re.IGNORECASE)
_MODE_CLAUSE = re.compile(r"\bWITH\s+(USER_MODE|SYSTEM_MODE|SECURITY_ENFORCED)\b",
                          re.IGNORECASE)
# SOSL: [FIND 'x' IN ... RETURNING Object(fields WHERE ...), Object2(fields)].
# SOSL obeys the SAME mode precedence as SOQL (system mode bypasses FLS), so a
# pre-v67 SOSL that RETURNs a field the user can't see is a real escalation. A
# SOSL with no RETURNING (or an unparseable one) is honest-unknown -> PS504.
_SOSL = re.compile(r"\[\s*FIND\b(.*?)\]", re.IGNORECASE | re.DOTALL)
_SOSL_RETURNING = re.compile(r"\bRETURNING\b(.*)$", re.IGNORECASE | re.DOTALL)
_SOSL_STOP = re.compile(r"\b(?:WHERE|ORDER\s+BY|LIMIT|OFFSET|USING)\b", re.IGNORECASE)


def _parse_sosl_returning(text: str):
    """Parse a SOSL RETURNING clause into [(object, fields, complete)]. Splits on
    top-level commas so a WHERE/ORDER inside an object group doesn't break it."""
    tokens, depth, buf = [], 0, ""
    for ch in text:
        if ch == "(":
            depth += 1; buf += ch
        elif ch == ")":
            depth -= 1; buf += ch
        elif ch == "," and depth == 0:
            tokens.append(buf); buf = ""
        else:
            buf += ch
    if buf.strip():
        tokens.append(buf)
    out = []
    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        pm = re.match(r"([A-Za-z0-9_]+)\s*\((.*)\)\s*$", tok, re.DOTALL)
        if pm:
            obj = pm.group(1)
            fld_part = _SOSL_STOP.split(pm.group(2))[0]
            fields = [f.strip() for f in fld_part.split(",") if f.strip()]
            out.append((obj, fields, True))
        else:
            om = re.match(r"([A-Za-z0-9_]+)\s*$", tok)
            if om:                       # `RETURNING Object` with no field list -> Id only
                out.append((om.group(1), [], True))
    return out


def _sosl_operations(source: str, api_version, sharing) -> list:
    ops = []
    for body in _SOSL.findall(source):
        clause_m = _MODE_CLAUSE.search(body)
        resolved = _resolve(clause_m.group(1) if clause_m else None, api_version, sharing)
        ret = _SOSL_RETURNING.search(body)
        if not ret:
            ops.append(ApexOperation(
                operation="read", sobject=None, fields=[], fields_complete=False,
                resolved=resolved,
                note="PS504: SOSL without RETURNING - reach undetermined"))
            continue
        objs = _parse_sosl_returning(ret.group(1))
        if not objs:
            ops.append(ApexOperation(
                operation="read", sobject=None, fields=[], fields_complete=False,
                resolved=resolved, note="PS504: SOSL RETURNING could not be parsed"))
            continue
        for obj, fields, complete in objs:
            ops.append(ApexOperation(
                operation="read", sobject=obj, fields=fields, fields_complete=complete,
                resolved=resolved, note=None if complete else "SOSL RETURNING incomplete"))
    return ops

# DML extraction (for PS509 trigger-cascade). We resolve the target object where
# statically determinable - inline construction or a simple typed variable.
_LIST_DECL = re.compile(r"\bList\s*<\s*([A-Za-z0-9_]+)\s*>\s*([A-Za-z_]\w*)", re.IGNORECASE)
_OBJ_DECL = re.compile(
    r"\b([A-Za-z0-9_]+__c|Account|Contact|Case|Lead|Opportunity|Task|User)\s*(?:\[\s*\])?\s+"
    r"([A-Za-z_]\w*)\s*[=;]", re.IGNORECASE)
_DML = re.compile(
    r"\b(insert|update|upsert|delete|undelete)\s+(?:as\s+(user|system)\s+)?"
    r"(?:new\s+([A-Za-z0-9_]+)\s*\(|([A-Za-z_]\w*))",
    re.IGNORECASE)
_DB_DML = re.compile(
    r"\bDatabase\.(insert|update|upsert|delete|undelete)\s*\(\s*([A-Za-z_]\w*)", re.IGNORECASE)
# Publishing a platform event IS a write: it needs Create on the event object and
# it FIRES THAT EVENT'S TRIGGER - the same cascade DML causes. Modelling it as a
# DML verb means the existing machinery (PS503 write escalation, PS509 legacy
# trigger cascade) applies to the subscriber for free, instead of the publish being
# a dead end that only ever produced an honest-unknown.
_EVENT_PUBLISH = re.compile(r"\bEventBus\s*\.\s*publish\s*\(\s*([A-Za-z_]\w*)", re.IGNORECASE)
_ACCESS_LEVEL = re.compile(r"AccessLevel\.(USER|SYSTEM)_MODE", re.IGNORECASE)
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)


def _strip_comments(source: str) -> str:
    return _COMMENTS.sub(" ", source)


def _variable_types(source: str) -> dict:
    # First-wins: the real declaration is seen before a later `insert as user x`
    # statement (which _OBJ_DECL would otherwise misread as a "User x;" decl).
    types = {}
    for m in _LIST_DECL.finditer(source):
        types.setdefault(m.group(2).lower(), m.group(1))
    for m in _OBJ_DECL.finditer(source):
        types.setdefault(m.group(2).lower(), m.group(1))
    return types


def _dml_operations(source: str) -> list:
    """(verb, sobject_or_None, mode) for each DML statement. mode is
    'user'/'system' from `as user/system` or `AccessLevel.*`, else None."""
    types = _variable_types(source)
    out = []
    for m in _DML.finditer(source):
        verb = m.group(1).lower()
        mode = (m.group(2) or "").lower() or None
        obj = m.group(3) or types.get((m.group(4) or "").lower())
        out.append((verb, obj, mode))
    for m in _DB_DML.finditer(source):
        al = _ACCESS_LEVEL.search(source[m.end():m.end() + 100])
        mode = al.group(1).lower() if al else None
        out.append((m.group(1).lower(), types.get(m.group(2).lower()), mode))
    return out


def _resolve_dml_fls(mode, api_version) -> Optional[bool]:
    """Whether a DML operation enforces the user's CRUD/FLS (the write axis)."""
    if mode == "user":
        return True
    if mode == "system":
        return False
    if api_version is not None and api_version >= 67:
        return True
    return False


@dataclass
class ResolvedMode:
    enforces_sharing: Optional[bool]   # record-level; None = undetermined
    enforces_fls: Optional[bool]       # object/field CRUD + FLS
    source: str
    note: Optional[str] = None

    @property
    def is_escalation_capable(self) -> bool:
        """True if either axis is not enforced (or is unknown) - i.e. the code
        may reach beyond the running user."""
        return self.enforces_sharing in (False, None) or self.enforces_fls in (False, None)


@dataclass
class ApexOperation:
    operation: str                     # 'read' (SOQL); DML kinds later
    sobject: Optional[str]
    fields: List[str]
    fields_complete: bool
    resolved: ResolvedMode
    dynamic: bool = False
    note: Optional[str] = None
    # Authority Path (AST backend only): {field: 'returned'|'internal'|'undetermined'}
    # - whether the field's VALUE actually flows to the @InvocableMethod output
    # (the model). None (regex backend) means "not traced" -> worst case applies.
    field_flow: Optional[dict] = None
    # {field: [output field names]} - WHICH @InvocableVariable the value lands in
    # ('*' = the whole record/return value leaves). This names the sink, which is
    # what lets the Agent Script layer join it to `set @variables.x = @outputs.y`.
    field_sinks: Optional[dict] = None


@dataclass
class ApexReach:
    class_name: str
    api_version: Optional[float]
    sharing: str                       # with | without | inherited | none
    operations: List[ApexOperation] = field(default_factory=list)
    dynamic_soql: bool = False
    backend: str = "regex"             # "ast" when parsed via the real parse tree
    referenced: Optional[List[str]] = None
    # Security.stripInaccessible: the real FLS sanitizer. See _sanitizer().
    sanitizer: Optional[dict] = None
    # async/event/callout hand-offs that leave the analysed transaction (PS514).
    async_handoffs: List[str] = field(default_factory=list)


# Security.stripInaccessible(AccessType.READABLE, recs) is the platform's real FLS
# sanitizer: it returns an SObjectAccessDecision whose .getRecords() are stripped of
# fields the running user cannot see. Ignoring it produces false positives on
# correctly-written code (a common AppExchange pattern). But it only sanitizes if
# (a) the AccessType matches the operation and (b) the code actually USES the
# decision's records instead of the original list - discarding the return is a
# well-known no-op bug.
_STRIP_INACCESSIBLE = re.compile(
    r"\bSecurity\s*\.\s*stripInaccessible\s*\(\s*AccessType\s*\.\s*(\w+)", re.IGNORECASE)
_GET_RECORDS = re.compile(r"\.\s*getRecords\s*\(", re.IGNORECASE)


# A polymorphic select - `TYPEOF What WHEN Account THEN Name, Industry WHEN
# Opportunity THEN Amount END` - defeats BOTH extractors: each returns mangled
# tokens ("TYPEOF What WHEN Account THEN Name") AND claims fields_complete, so no
# PS504 fires. That is the worst failure mode this tool can have: a silent
# false-clean dressed as a full parse. The branch fields belong to polymorphic
# RELATED objects (Account.Industry, Opportunity.Amount), which we cannot key to
# the queried object anyway, so the honest answer is "not resolved" - never a
# guess, and never nonsense field names that would produce nonsense findings.
# Signature: the token carries BOTH `WHEN` and `THEN`. That is TYPEOF syntax and
# nothing else - it matches the regex extractor's split tokens ("TYPEOF What WHEN
# Account THEN Name") AND the AST extractor's space-stripped one
# ("TYPEOFWhatWHENAccountTHENName,..."), while a real field such as
# `TypeOfWork__c` carries neither. Keying on "TYPEOF" alone would flag that field.
def _is_polymorphic_token(f: str) -> bool:
    u = (f or "").upper()
    return "WHEN" in u and "THEN" in u


def _flag_polymorphic(reach) -> None:
    for op in reach.operations:
        if not op.fields:
            continue
        garbage = [f for f in op.fields if _is_polymorphic_token(f)]
        if not garbage:
            continue
        op.fields = [f for f in op.fields if f not in garbage]
        op.fields_complete = False
        op.note = ("PS504: polymorphic TYPEOF select - the branch fields belong to "
                   "related objects and are not resolved")


def _event_publish_ops(source: str, api_version, sharing) -> list:
    """`EventBus.publish(evts)` -> a write of the event object.

    Publishing needs Create on the event and FIRES THAT EVENT'S TRIGGER, so it is a
    write with a cascade - which means PS503 and PS509 already know how to reason
    about it, and the subscriber stops being a dead end. Modelled here rather than
    in either extractor so both backends get it (the AST path builds DML from its
    own IR and would otherwise miss this entirely).

    The event type comes from the publish argument's declared type; an unresolvable
    one yields sobject=None, which stays an honest unknown rather than a guess."""
    types = _variable_types(source)
    ops = []
    for m in _EVENT_PUBLISH.finditer(source):
        obj = types.get(m.group(1).lower())
        ops.append(ApexOperation(
            operation="publish", sobject=obj, fields=[], fields_complete=True,
            resolved=ResolvedMode(None, _resolve_dml_fls(None, api_version),
                                  "EventBus.publish " + ("v>=67 user default"
                                  if (api_version or 0) >= 67 else "API v<=66 default")),
            note=None if obj else "platform event type undetermined"))
    return ops


def _sanitizer(source: str) -> Optional[dict]:
    """Detect Security.stripInaccessible usage in a class.

    Returns {access_types: [...], read_sanitized: bool, result_used: bool} or None.
    This is deliberately CLASS-scoped, not path-scoped: proving that the sanitized
    list (and not the original) is what reaches the sink needs alias tracking we do
    not have. So this never clears a finding - it only lets the analyzer report an
    honest 'sanitizer present, path not proven' instead of a proven escalation."""
    types = [m.group(1).upper() for m in _STRIP_INACCESSIBLE.finditer(source)]
    if not types:
        return None
    return {
        "access_types": sorted(set(types)),
        # only READABLE strips fields on a READ path
        "read_sanitized": "READABLE" in types,
        # the decision's records must actually be used, else the call is a no-op
        "result_used": bool(_GET_RECORDS.search(source)),
    }


# Async / event hand-offs. Each of these ENDS the analysable transaction: the work
# continues in a separate execution context whose reach this analyzer does not
# follow. Silently ignoring them is the worst kind of false negative for a security
# tool - the agent's real blast radius can grow after the hand-off - so each is
# surfaced as an explicit honest-unknown edge (PS514) rather than dropped.
_ASYNC_HANDOFFS = [
    ("platform event", re.compile(r"\bEventBus\s*\.\s*publish\s*\(", re.IGNORECASE)),
    ("@future method", re.compile(r"@future\b", re.IGNORECASE)),
    ("Queueable job", re.compile(r"\bSystem\s*\.\s*enqueueJob\s*\(", re.IGNORECASE)),
    ("Batch job", re.compile(r"\bDatabase\s*\.\s*executeBatch\s*\(", re.IGNORECASE)),
    ("scheduled job", re.compile(r"\bSystem\s*\.\s*schedule(?:Batch)?\s*\(", re.IGNORECASE)),
    ("HTTP callout", re.compile(r"\bnew\s+HttpRequest\s*\(|\bHttp\s*\(\s*\)\s*\.\s*send\s*\(",
                               re.IGNORECASE)),
]


def _async_handoffs(source: str) -> List[str]:
    """Kinds of async/event/callout hand-off this class performs. Each one is a
    boundary where the agent's reach may continue in a context we do not analyse."""
    return [label for label, rx in _ASYNC_HANDOFFS if rx.search(source)]


def _sharing_record_default(sharing: str) -> tuple[Optional[bool], Optional[str]]:
    """Record-level enforcement implied by the sharing keyword under system mode."""
    if sharing == "with":
        return True, None
    if sharing == "without":
        return False, None
    # 'inherited' or 'none' -> depends on the caller's context (E2)
    return None, f"record sharing depends on caller ({sharing} declaration)"


def _resolve(clause: Optional[str], api_version: Optional[float], sharing: str) -> ResolvedMode:
    clause = clause.upper() if clause else None

    if clause == "USER_MODE":
        return ResolvedMode(True, True, "WITH USER_MODE")
    if clause == "SYSTEM_MODE":
        return ResolvedMode(False, False, "WITH SYSTEM_MODE")
    if clause == "SECURITY_ENFORCED":
        rec, note = _sharing_record_default(sharing)
        return ResolvedMode(rec, True, "WITH SECURITY_ENFORCED", note)

    # No explicit clause -> apiVersion default.
    if api_version is not None and api_version >= 67:
        return ResolvedMode(True, True, "apiVersion>=67 user-mode default")

    # api <= 66 (or unknown, treated as legacy): system mode for FLS; record
    # access follows the sharing keyword.
    rec, note = _sharing_record_default(sharing)
    src = "API v<=66 system-mode default" if api_version is not None else "apiVersion unknown (assumed legacy)"
    return ResolvedMode(rec, False, src, note)


def _parse_select_fields(select_clause: str) -> tuple[List[str], bool, Optional[str]]:
    sc = select_clause.strip()
    if re.search(r"\bSELECT\b", sc, re.IGNORECASE):
        return [], False, "subquery present - field list incomplete"
    if re.fullmatch(r"COUNT\s*\(\s*\)", sc, re.IGNORECASE):
        return [], True, "COUNT() - no field data returned"
    if "(" in sc:
        return [], False, "aggregate/function select - fields not enumerated"
    fields = [f.strip() for f in sc.split(",") if f.strip()]
    return fields, True, None


def _read_api_version(cls_path: str) -> Optional[float]:
    meta = cls_path + "-meta.xml"
    if os.path.exists(meta):
        m = re.search(r"<apiVersion>([\d.]+)</apiVersion>",
                      open(meta, encoding="utf-8").read())
        if m:
            return float(m.group(1))
    return None


def parse_apex_source(source: str, api_version: Optional[float],
                      class_name: str = "<source>") -> ApexReach:
    source = _strip_comments(source)
    m = _CLASS_DECL.search(source)
    sharing = m.group(1).lower() if m else "none"

    reach = ApexReach(class_name=class_name, api_version=api_version, sharing=sharing)
    reach.dynamic_soql = bool(_DYNAMIC.search(source))

    for sel, obj, tail in _SOQL.findall(source):
        clause_m = _MODE_CLAUSE.search(sel + tail)
        clause = clause_m.group(1) if clause_m else None
        fields, complete, fnote = _parse_select_fields(sel)
        reach.operations.append(ApexOperation(
            operation="read",
            sobject=obj,
            fields=fields,
            fields_complete=complete,
            resolved=_resolve(clause, api_version, sharing),
            note=fnote,
        ))

    if reach.dynamic_soql:
        reach.operations.append(ApexOperation(
            operation="read", sobject=None, fields=[], fields_complete=False,
            resolved=ResolvedMode(None, None, "dynamic SOQL", "reach undetermined"),
            dynamic=True, note="PS504: dynamic SOQL - reach cannot be determined statically",
        ))

    for verb, obj, mode in _dml_operations(source):
        reach.operations.append(ApexOperation(
            operation=verb, sobject=obj, fields=[], fields_complete=True,
            resolved=ResolvedMode(None, _resolve_dml_fls(mode, api_version),
                                  "dml " + (mode or ("v>=67 user default"
                                            if (api_version or 0) >= 67 else "API v<=66 default"))),
            note=None if obj else "DML target object undetermined"))

    reach.operations.extend(_sosl_operations(source, api_version, sharing))
    reach.operations.extend(_event_publish_ops(source, api_version, sharing))
    reach.sanitizer = _sanitizer(source)
    reach.async_handoffs = _async_handoffs(source)
    _flag_polymorphic(reach)
    return reach


def _reach_from_ir(ir: dict, api_version: Optional[float],
                   class_name: str = None) -> ApexReach:
    """Build an ApexReach from the AST extractor's IR, applying the SAME
    precedence law (_resolve / _resolve_dml_fls) the regex path uses. Extraction
    differs by backend; resolution is identical and shared."""
    sharing = ir.get("sharing", "none")
    reach = ApexReach(class_name=ir.get("class_name") or class_name or "<ast>",
                      api_version=api_version, sharing=sharing, backend="ast",
                      referenced=ir.get("referenced_classes"))
    reach.dynamic_soql = bool(ir.get("dynamic_soql"))
    for op in ir.get("operations", []):
        kind = op.get("operation")
        if kind == "read":
            reach.operations.append(ApexOperation(
                operation="read", sobject=op.get("sobject"),
                fields=op.get("fields") or [],
                fields_complete=bool(op.get("fields_complete")),
                resolved=_resolve(op.get("mode"), api_version, sharing),
                note=op.get("note"), field_flow=op.get("field_flow"),
                field_sinks=op.get("field_sinks")))
        else:  # a DML verb
            mode = op.get("mode")
            src = "dml " + (mode or ("v>=67 user default"
                            if (api_version or 0) >= 67 else "API v<=66 default"))
            reach.operations.append(ApexOperation(
                operation=kind, sobject=op.get("sobject"), fields=[],
                fields_complete=True,
                resolved=ResolvedMode(None, _resolve_dml_fls(mode, api_version), src),
                note=op.get("note")))
    if reach.dynamic_soql:
        reach.operations.append(ApexOperation(
            operation="read", sobject=None, fields=[], fields_complete=False,
            resolved=ResolvedMode(None, None, "dynamic SOQL", "reach undetermined"),
            dynamic=True, note="PS504: dynamic SOQL - reach cannot be determined statically"))
    return reach


def _parse_file(cls_path: str, backend: str = "auto") -> ApexReach:
    """Parse one .cls into an ApexReach (no cross-class follow). backend:
    'auto' tries the AST and falls back to regex; 'ast' forces AST (raises on
    failure); 'regex' forces the regex extractor."""
    api = _read_api_version(cls_path)
    name = os.path.basename(cls_path).replace(".cls", "")
    if backend in ("auto", "ast") and apex_ast.ast_available():
        try:
            reach = _reach_from_ir(apex_ast.extract_ir(cls_path), api, name)
            # SOSL and the stripInaccessible sanitizer are not walked by the AST
            # extractor; read them from the source so neither backend has a silent
            # blind spot (parsed once, in Python, and shared by both paths).
            with open(cls_path, encoding="utf-8") as f:
                src = _strip_comments(f.read())
            reach.operations.extend(_sosl_operations(src, api, reach.sharing))
            reach.operations.extend(_event_publish_ops(src, api, reach.sharing))
            reach.sanitizer = _sanitizer(src)
            reach.async_handoffs = _async_handoffs(src)
            _flag_polymorphic(reach)
            return reach
        except Exception:
            if backend == "ast":
                raise
            # auto: fall through to the regex extractor
    with open(cls_path, encoding="utf-8") as f:
        return parse_apex_source(f.read(), api, class_name=name)


# Referenced local class names: `new ClassName(` or `ClassName.method(`.
_CLASS_REF = re.compile(r"\bnew\s+([A-Z][A-Za-z0-9_]*)\s*\(|\b([A-Z][A-Za-z0-9_]*)\.\w+\s*\(")


def _referenced_classes(source: str) -> set:
    names = set()
    for m in _CLASS_REF.finditer(source):
        names.add(m.group(1) or m.group(2))
    return {n for n in names if n}


def _refs_of(reach: ApexReach, cls_path: str) -> set:
    """Referenced local class names: from the AST IR when available, else regex."""
    if reach.referenced is not None:
        return {c for c in reach.referenced if c}
    with open(cls_path, encoding="utf-8") as f:
        return _referenced_classes(_strip_comments(f.read()))


def _follow_one_level(reach: ApexReach, source_root: str, own_name: str,
                      own_path: str, backend: str = "auto"):
    """fflib/selector reality: the query usually lives in a delegated class, not
    the action. Follow ONE level - parse referenced local classes and merge their
    reach into this action. Delegation that itself delegates further is flagged
    PS508 (a crosslink marker), never silently dropped."""
    classes_dir = os.path.join(source_root, "classes")
    for cname in sorted(_refs_of(reach, own_path)):
        if cname == own_name:
            continue
        cpath = os.path.join(classes_dir, cname + ".cls")
        if not os.path.exists(cpath):
            continue  # standard/managed/absent class - not analysable from source
        sub = _parse_file(cpath, backend)
        reach.operations.extend(sub.operations)  # attribute the selector's reach to the action
        deeper = sorted({c for c in _refs_of(sub, cpath)
                         if c not in (cname, own_name)
                         and os.path.exists(os.path.join(classes_dir, c + ".cls"))})
        if deeper:
            reach.operations.append(ApexOperation(
                operation="crosslink", sobject=cname, fields=[], fields_complete=False,
                resolved=ResolvedMode(None, None,
                                      f"{cname} delegates further to {', '.join(deeper)}"),
                note="PS508: call chain beyond one level not followed"))


def parse_apex(cls_path: str, source_root: str = None, backend: str = "auto") -> ApexReach:
    reach = _parse_file(cls_path, backend)
    if source_root:
        _follow_one_level(reach, source_root, reach.class_name, cls_path, backend)
    return reach


if __name__ == "__main__":
    import sys
    r = parse_apex(sys.argv[1])
    print(f"{r.class_name}  api=v{r.api_version}  sharing={r.sharing}  "
          f"dynamic={r.dynamic_soql}")
    for op in r.operations:
        rm = op.resolved
        print(f"  {op.operation} {op.sobject} fields={op.fields} "
              f"-> sharing={rm.enforces_sharing} fls={rm.enforces_fls} "
              f"[{rm.source}] escalation_capable={rm.is_escalation_capable}"
              + (f"  # {op.note}" if op.note else ""))
