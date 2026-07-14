"""Read a Flow's execution mode and data reach from its metadata XML.

Flow run context is declarative (proven readable in Milestone 0 / E5), so this
needs no Apex parsing. It extracts:
  * runInMode  -> the execution context the analyzer resolves against
  * per-element object/field access for record lookups, creates, updates, deletes

Where a field list cannot be determined statically (fields taken from a record
variable, or automatic output with no explicit queried fields), the access is
marked incomplete with a note - never silently reported as clean.

The "autolaunched flow invoked from Apex runs system-mode-without-sharing
regardless of runInMode" rule is a CALLER-context rule; it is applied by the
analyzer that wires actions to targets, not here. This module reports the
flow's own declared mode.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

NS = "{http://soap.sforce.com/2006/04/metadata}"

# runInMode value -> (runs in system context?, enforces sharing?)
_SYSTEM_MODES = {
    "SystemModeWithoutSharing": (True, False),
    "SystemModeWithSharing": (True, True),
    "DefaultMode": (False, True),
}


@dataclass
class FlowAccess:
    element: str
    operation: str          # read | create | update | delete
    sobject: Optional[str]
    fields: List[str] = field(default_factory=list)
    fields_complete: bool = True
    note: Optional[str] = None


@dataclass
class FlowReach:
    name: str
    process_type: Optional[str]
    run_in_mode: Optional[str]
    accesses: List[FlowAccess] = field(default_factory=list)

    @property
    def runs_in_system_context(self) -> bool:
        return _SYSTEM_MODES.get(self.run_in_mode, (False, True))[0]

    @property
    def enforces_sharing(self) -> bool:
        return _SYSTEM_MODES.get(self.run_in_mode, (False, True))[1]

    @property
    def severity_hint(self) -> str:
        """Standalone hint; the analyzer refines it against the running user."""
        if self.run_in_mode == "SystemModeWithoutSharing":
            return "ERROR"      # bypasses sharing AND FLS/CRUD
        if self.run_in_mode == "SystemModeWithSharing":
            return "WARN"       # system CRUD/FLS, sharing still enforced
        if self.run_in_mode in (None, "DefaultMode"):
            return "REVIEW"     # user mode when run directly, but caller can flip it
        return "REVIEW"


def _lookup_fields(el) -> tuple[List[str], bool, Optional[str]]:
    queried = [q.text for q in el.findall(f"{NS}queriedFields") if q.text]
    if queried:
        return queried, True, None
    if el.findtext(f"{NS}storeOutputAutomatically") == "true":
        return [], False, "storeOutputAutomatically: all fields retrieved"
    output = [a.findtext(f"{NS}field") for a in el.findall(f"{NS}outputAssignments")]
    output = [f for f in output if f]
    if output:
        return output, True, None
    return [], False, "queried fields undetermined"


def _dml_fields(el) -> tuple[List[str], bool, Optional[str]]:
    assigned = [a.findtext(f"{NS}field") for a in el.findall(f"{NS}inputAssignments")]
    assigned = [f for f in assigned if f]
    if assigned:
        return assigned, True, None
    input_ref = el.findtext(f"{NS}inputReference")
    if input_ref:
        return [], False, f"fields from record variable {input_ref!r} - undetermined"
    return [], False, "assigned fields undetermined"


def parse_flow(path: str) -> FlowReach:
    root = ET.parse(path).getroot()
    reach = FlowReach(
        name=root.findtext(f"{NS}label") or os.path.basename(path),
        process_type=root.findtext(f"{NS}processType"),
        run_in_mode=root.findtext(f"{NS}runInMode"),
    )

    for el in root.findall(f"{NS}recordLookups"):
        fields, complete, note = _lookup_fields(el)
        reach.accesses.append(FlowAccess(
            el.findtext(f"{NS}name"), "read", el.findtext(f"{NS}object"),
            fields, complete, note))

    for tag, op in ((f"{NS}recordCreates", "create"), (f"{NS}recordUpdates", "update")):
        for el in root.findall(tag):
            obj = el.findtext(f"{NS}object")
            fields, complete, note = _dml_fields(el)
            if obj is None:
                complete, note = False, "object from record variable - undetermined"
            reach.accesses.append(FlowAccess(
                el.findtext(f"{NS}name"), op, obj, fields, complete, note))

    for el in root.findall(f"{NS}recordDeletes"):
        reach.accesses.append(FlowAccess(
            el.findtext(f"{NS}name"), "delete", el.findtext(f"{NS}object"), [], True, None))

    return reach


if __name__ == "__main__":
    import sys
    r = parse_flow(sys.argv[1])
    print(f"{r.name}  [{r.process_type}]  runInMode={r.run_in_mode}  "
          f"system={r.runs_in_system_context} sharing={r.enforces_sharing} "
          f"hint={r.severity_hint}")
    for a in r.accesses:
        flag = "" if a.fields_complete else "  (INCOMPLETE)"
        print(f"  {a.operation:6} {a.sobject}  fields={a.fields}{flag}"
              + (f"  # {a.note}" if a.note else ""))
