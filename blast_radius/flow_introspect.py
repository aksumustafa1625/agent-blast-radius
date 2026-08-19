"""Read a Flow's execution mode and data reach from its metadata XML.

Flow run context is declarative (proven readable in Milestone 0 / E5), so this
needs no Apex parsing. It extracts:
  * the run context -> resolved from the flow's TYPE first, then its runInMode
  * per-element object/field access for record lookups, creates, updates, deletes

Where a field list cannot be determined statically (fields taken from a record
variable, or automatic output with no explicit queried fields), the access is
marked incomplete with a note - never silently reported as clean.

The "autolaunched flow invoked from Apex runs system-mode-without-sharing
regardless of runInMode" rule is a CALLER-context rule; it is applied by the
analyzer that wires actions to targets, not here. This module reports the
flow's own declared mode.

MODE RESOLUTION ORDER (mirrors Salesforce's own flowtest engine,
code-analyzer-flow-engine/FlowScanner/flow_parser/parse.py, which branches on
the flow TYPE first and only then reads the runInMode tag):

  1. flow TYPE - a record-/schedule-/platform-event-triggered flow, and a
     Process Builder process, run in system context without sharing by
     platform rule; the author cannot choose otherwise, so the runInMode tag
     (if one is even present) does not decide.
  2. runInMode tag - for a flow type whose context IS author-selectable
     (autolaunched without a trigger, screen flow), an explicit tag wins.
  3. no tag - the context is decided by the CALLER, which this module cannot
     see. That is an honest UNKNOWN (None on both axes), never user mode.

Step 1 is `platform-doc` provenance: it is what the Flow Run Context
documentation states and what flowtest encodes, and it is NOT yet measured in
an org by this project (the fixture for it - a record-triggered flow with no
runInMode tag, run as a user who cannot see a field it reads - is listed in
CLAUDE.md §9). Before 2026-08-19 this module read `processType` and never
used it, so a record-triggered flow with no tag resolved to user mode with
sharing - the silent false clean CLAUDE.md §3 exists to prevent, found by an
external mechanism audit. Step 3 used to resolve to user mode too.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

NS = "{http://soap.sforce.com/2006/04/metadata}"

# runInMode value -> (runs in system context?, enforces sharing?)
_SYSTEM_MODES = {
    "SystemModeWithoutSharing": (True, False),
    "SystemModeWithSharing": (True, True),
    "DefaultMode": (False, True),
}

# start/triggerType values that make an AutoLaunchedFlow a TRIGGERED flow. A
# triggered flow's context is fixed by the platform (system without sharing);
# the runInMode tag is not offered for it in Flow Builder. platform-doc.
_TRIGGERED = {
    "RecordAfterSave", "RecordBeforeSave", "RecordBeforeDelete",
    "Scheduled", "PlatformEvent",
}

# processType values that ARE a Process Builder process (record-change process
# and platform-event process). Processes run in system context. platform-doc.
# `InvocableProcess` is deliberately NOT here: flowtest maps it to DefaultMode,
# the docs say processes run in system context, and this project has measured
# neither - so it falls to step 3 (undetermined), which is never clean.
_SYSTEM_PROCESS_TYPES = {"Workflow", "CustomEvent"}

# Resolved run context: (runs in system context?, enforces sharing?), each
# True / False / None, plus the human-readable source the findings quote.
Mode = Tuple[Optional[bool], Optional[bool], str]


def resolve_mode(process_type: Optional[str], trigger_type: Optional[str],
                 run_in_mode: Optional[str]) -> Mode:
    """The flow-context law. TYPE first, then tag, then honest unknown.

    Kept as a free function so the ordering can be tested without an XML file
    and so a future in-org measurement can be pointed at one place."""
    # 1. TYPE decides. A triggered flow or a process runs system-without-sharing
    #    by platform rule. If a tag is nonetheless present, say so rather than
    #    trust it: trusting a DefaultMode tag on a record-triggered flow would be
    #    the false clean in its purest form, and whether the platform honours
    #    such a tag is exactly what is not measured.
    if trigger_type in _TRIGGERED or process_type in _SYSTEM_PROCESS_TYPES:
        what = (f"triggerType={trigger_type}" if trigger_type in _TRIGGERED
                else f"processType={process_type}")
        note = (f"Flow {what}: system context without sharing by platform rule "
                f"(platform-doc, not yet measured in-org)")
        if run_in_mode:
            note += (f"; the runInMode={run_in_mode} tag present is not author-"
                     "selectable for this flow type and is not trusted here")
        return True, False, note
    # 2. An explicit tag on a type whose context is author-selectable.
    if run_in_mode in _SYSTEM_MODES:
        system, sharing = _SYSTEM_MODES[run_in_mode]
        return system, sharing, f"Flow runInMode={run_in_mode}"
    if run_in_mode:
        # A value this module does not know. Not clean, not asserted.
        return None, None, (f"Flow runInMode={run_in_mode}: unrecognised value, "
                            "run context undetermined")
    # 3. No tag: the caller decides (user context when run by a user, the
    #    caller's context from Apex, system context from a process). Unknown.
    return None, None, (f"Flow processType={process_type}, no runInMode tag: run "
                        "context is decided by the caller and is undetermined here")


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
    trigger_type: Optional[str] = None      # start/triggerType, if any

    @property
    def mode(self) -> Mode:
        return resolve_mode(self.process_type, self.trigger_type, self.run_in_mode)

    @property
    def runs_in_system_context(self) -> Optional[bool]:
        """True / False / None (undetermined - never treated as user mode)."""
        return self.mode[0]

    @property
    def enforces_sharing(self) -> Optional[bool]:
        return self.mode[1]

    @property
    def enforces_fls(self) -> Optional[bool]:
        """System context bypasses CRUD/FLS; user context enforces it; an
        undetermined context stays undetermined on this axis too."""
        system = self.mode[0]
        return None if system is None else (not system)

    @property
    def mode_source(self) -> str:
        return self.mode[2]

    @property
    def mode_undetermined(self) -> bool:
        return self.mode[0] is None

    @property
    def is_escalation_capable(self) -> bool:
        """Worst case: anything not proven user-mode-with-sharing counts."""
        system, sharing, _ = self.mode
        return system is not False or sharing is not True

    @property
    def severity_hint(self) -> str:
        """Standalone hint; the analyzer refines it against the running user."""
        system, sharing, _ = self.mode
        if system is True and sharing is False:
            return "ERROR"      # bypasses sharing AND FLS/CRUD
        if system is True:
            return "WARN"       # system CRUD/FLS, sharing still enforced
        return "REVIEW"         # user mode by tag (caller can flip it), or unknown


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
        trigger_type=root.findtext(f"{NS}start/{NS}triggerType"),
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
    print(f"{r.name}  [{r.process_type}]  triggerType={r.trigger_type}  "
          f"runInMode={r.run_in_mode}  system={r.runs_in_system_context} "
          f"sharing={r.enforces_sharing} hint={r.severity_hint}")
    print(f"  mode source: {r.mode_source}")
    for a in r.accesses:
        flag = "" if a.fields_complete else "  (INCOMPLETE)"
        print(f"  {a.operation:6} {a.sobject}  fields={a.fields}{flag}"
              + (f"  # {a.note}" if a.note else ""))
