"""CRUD/FLS grant snapshot for a running user (Agent Blast Radius, Milestone 1).

This is a *grant snapshot*, not a complete effective-access computation. It is
the additive union of the user's profile and assigned permission sets (a
permission is granted if ANY source grants it). It deliberately does NOT yet
model: permission set groups, muting permission sets, session-based activation,
permission-set licences, restriction/scoping rules, role hierarchy, sharing
rules, teams/territories/queues, manual or Apex-managed shares, or channel-
dependent verified identity. Record visibility is treated as posture, not an
exact runtime computation. Naming it a "grant snapshot" keeps the claim honest.

This module is pure: it operates on a snapshot dict (see fixtures/) so it can be
unit-tested without an org. Loading that snapshot from a live org via
`sf data query` is a separate concern (the loader), kept out of here on purpose.

Correctness decisions that matter (verified against Salesforce semantics):

* **View All Data / Modify All Data short-circuit RECORD-level access only.**
  If the user can view all records, a system-mode read is not a record-level
  escalation. So these grant blanket object CRUD here.
* **They do NOT bypass field-level security.** FLS is enforced independently of
  View/Modify All Data. Field access is therefore the union of *explicit* FLS
  only. This is deliberate and conservative: over-crediting the user on FLS
  would hide exactly the escalation the tool exists to find (a GDPR field the
  running user cannot see).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class ObjectAccess:
    read: bool = False
    create: bool = False
    edit: bool = False
    delete: bool = False
    view_all_records: bool = False    # sees every record of this object
    modify_all_records: bool = False

    def can_see_all_records(self) -> bool:
        return self.view_all_records or self.modify_all_records


@dataclass
class FieldAccess:
    read: bool = False
    edit: bool = False


class EffectivePermissions:
    """Resolved permissions for one running user on one channel."""

    def __init__(self, snapshot: dict):
        self.running_user: str | None = snapshot.get("runningUser")
        self.channel: str | None = snapshot.get("channel")

        sysperm = snapshot.get("systemPermissions") or {}
        self.view_all_data: bool = bool(sysperm.get("ViewAllData"))
        self.modify_all_data: bool = bool(sysperm.get("ModifyAllData"))

        self._objects: Dict[str, ObjectAccess] = {}
        for row in snapshot.get("objectPermissions", []):
            acc = self._objects.setdefault(row["sobjectType"], ObjectAccess())
            acc.read = acc.read or bool(row.get("read"))
            acc.create = acc.create or bool(row.get("create"))
            acc.edit = acc.edit or bool(row.get("edit"))
            acc.delete = acc.delete or bool(row.get("delete"))
            acc.view_all_records = acc.view_all_records or bool(row.get("viewAllRecords"))
            acc.modify_all_records = acc.modify_all_records or bool(row.get("modifyAllRecords"))

        self._fields: Dict[str, FieldAccess] = {}
        for row in snapshot.get("fieldPermissions", []):
            acc = self._fields.setdefault(row["field"], FieldAccess())
            acc.read = acc.read or bool(row.get("read"))
            acc.edit = acc.edit or bool(row.get("edit"))

    # -- object level -------------------------------------------------------

    def object_access(self, sobject: str) -> ObjectAccess:
        base = self._objects.get(sobject, ObjectAccess())
        if not (self.view_all_data or self.modify_all_data):
            return base
        # System super-permissions grant blanket record/CRUD access.
        return ObjectAccess(
            read=base.read or self.view_all_data or self.modify_all_data,
            create=base.create or self.modify_all_data,
            edit=base.edit or self.modify_all_data,
            delete=base.delete or self.modify_all_data,
            view_all_records=True,
            modify_all_records=base.modify_all_records or self.modify_all_data,
        )

    def can_read_object(self, sobject: str) -> bool:
        return self.object_access(sobject).read

    def can_write_object(self, sobject: str) -> bool:
        a = self.object_access(sobject)
        return a.create or a.edit

    def sees_all_records(self, sobject: str) -> bool:
        """True if a system-mode read on this object is NOT a record-level
        escalation, because the user can already see every record."""
        return self.view_all_data or self.modify_all_data or self.object_access(sobject).can_see_all_records()

    # -- field level (FLS is NOT bypassed by View/Modify All Data) ----------

    def field_access(self, field: str) -> FieldAccess:
        return self._fields.get(field, FieldAccess())

    def can_read_field(self, field: str) -> bool:
        return self.field_access(field).read

    def can_edit_field(self, field: str) -> bool:
        return self.field_access(field).edit
