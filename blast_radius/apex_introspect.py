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

Parsing strategy (honest about its limits): this is a disciplined extractor, not
the Apex compiler. It reads apiVersion from the paired .cls-meta.xml, the sharing
keyword from the class header, and inline `[SELECT ... ]` queries with their mode
clauses. Dynamic SOQL (`Database.query` on a built string) and subqueries are
flagged as undetermined (PS504), never guessed. A real AST (ANTLR apex-parser)
or Salesforce Code Analyzer is the documented upgrade path.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

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


@dataclass
class ApexReach:
    class_name: str
    api_version: Optional[float]
    sharing: str                       # with | without | inherited | none
    operations: List[ApexOperation] = field(default_factory=list)
    dynamic_soql: bool = False


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
    src = "apiVersion<=66 system default" if api_version is not None else "apiVersion unknown (assumed legacy)"
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

    return reach


def parse_apex(cls_path: str) -> ApexReach:
    source = open(cls_path, encoding="utf-8").read()
    name = os.path.basename(cls_path).replace(".cls", "")
    return parse_apex_source(source, _read_api_version(cls_path), class_name=name)


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
