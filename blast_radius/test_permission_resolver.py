"""Unit tests for permission_resolver (Milestone 1).

Run from the repo root:  python blast_radius/test_permission_resolver.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from permission_resolver import EffectivePermissions  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name: str) -> dict:
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)


class MinimalUserTests(unittest.TestCase):
    """The escalation scenario: user reads the object but not the GDPR field."""

    def setUp(self):
        self.perms = EffectivePermissions(load("user_minimal.json"))

    def test_reads_object(self):
        self.assertTrue(self.perms.can_read_object("Blast_Test__c"))

    def test_reads_granted_field(self):
        self.assertTrue(self.perms.can_read_field("Blast_Test__c.Secret_Data__c"))

    def test_cannot_read_ungranted_gdpr_field(self):
        # This is the field an escalating action could surface to the model.
        self.assertFalse(self.perms.can_read_field("Blast_Test__c.Customer_IBAN__c"))

    def test_no_write(self):
        self.assertFalse(self.perms.can_write_object("Blast_Test__c"))

    def test_not_all_records(self):
        self.assertFalse(self.perms.sees_all_records("Blast_Test__c"))


class ViewAllDataTests(unittest.TestCase):
    """View All Data short-circuits record-level access but NOT field security."""

    def setUp(self):
        self.perms = EffectivePermissions(load("user_viewall.json"))

    def test_sees_all_records(self):
        self.assertTrue(self.perms.sees_all_records("Blast_Test__c"))

    def test_reads_any_object(self):
        self.assertTrue(self.perms.can_read_object("Some_Other__c"))

    def test_fls_not_bypassed_by_view_all(self):
        # The critical conservative rule: ViewAllData does not grant FLS, so an
        # unlabelled/ungranted field is still invisible - the tool must not
        # credit the user with it and thereby hide a real escalation.
        self.assertFalse(self.perms.can_read_field("Blast_Test__c.Customer_IBAN__c"))


class RealSnapshotTests(unittest.TestCase):
    """Loader -> resolver pipeline against a snapshot captured from a live org."""

    def setUp(self):
        self.perms = EffectivePermissions(load("snapshot_admin_real.json"))

    def test_admin_sees_all_records(self):
        # Real admin has ViewAllData/ModifyAllData -> no record-level escalation.
        self.assertTrue(self.perms.sees_all_records("Blast_Test__c"))

    def test_admin_reads_any_object(self):
        self.assertTrue(self.perms.can_read_object("Anything__c"))

    def test_field_read_from_assigned_permset(self):
        # FLS came from the BlastR_Classify permission set in the captured data.
        self.assertTrue(self.perms.can_read_field("Blast_Test__c.Customer_IBAN__c"))


class UnionTests(unittest.TestCase):
    """Effective permission = union across profile + permission sets."""

    def test_union_across_sources(self):
        snap = {
            "objectPermissions": [
                {"parent": "Profile:X", "sobjectType": "Acc__c", "read": True},
                {"parent": "PermSet:Y", "sobjectType": "Acc__c", "create": True},
            ],
            "fieldPermissions": [
                {"parent": "Profile:X", "field": "Acc__c.F__c", "read": False},
                {"parent": "PermSet:Y", "field": "Acc__c.F__c", "read": True},
            ],
        }
        p = EffectivePermissions(snap)
        self.assertTrue(p.can_read_object("Acc__c"))     # granted by profile
        self.assertTrue(p.can_write_object("Acc__c"))    # create granted by perm set
        self.assertTrue(p.can_read_field("Acc__c.F__c")) # read granted by perm set


if __name__ == "__main__":
    unittest.main(verbosity=2)
