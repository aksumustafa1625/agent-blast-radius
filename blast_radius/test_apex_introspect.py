"""Tests for apex_introspect: the precedence law, encoded and verified.

Run from the repo root:  python blast_radius/test_apex_introspect.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apex_introspect import parse_apex, parse_apex_source  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSES = os.path.join(HERE, "..", "force-app", "main", "default", "classes")
V58 = os.path.join(CLASSES, "BlastRadius_E2_ReaderV58.cls")
V67 = os.path.join(CLASSES, "BlastRadius_E2_ReaderV67.cls")


def resolved(source: str, api):
    return parse_apex_source(source, api).operations[0].resolved


class RealE2ReadersTest(unittest.TestCase):
    """The centerpiece: identical `without sharing` code resolves oppositely."""

    def test_v58_resolves_to_system_mode(self):
        if not os.path.exists(V58):
            self.skipTest("E2 v58 reader not found")
        r = parse_apex(V58)
        self.assertEqual(r.sharing, "without")
        self.assertEqual(r.api_version, 58.0)
        op = [o for o in r.operations if not o.dynamic][0]
        self.assertEqual(op.sobject, "Blast_Test__c")
        self.assertFalse(op.resolved.enforces_sharing)
        self.assertFalse(op.resolved.enforces_fls)
        self.assertTrue(op.resolved.is_escalation_capable)

    def test_v67_resolves_to_user_mode(self):
        if not os.path.exists(V67):
            self.skipTest("E2 v67 reader not found")
        r = parse_apex(V67)
        self.assertEqual(r.sharing, "without")
        self.assertEqual(r.api_version, 67.0)
        op = [o for o in r.operations if not o.dynamic][0]
        self.assertTrue(op.resolved.enforces_sharing)
        self.assertTrue(op.resolved.enforces_fls)
        self.assertFalse(op.resolved.is_escalation_capable)


class PrecedenceLawTest(unittest.TestCase):
    WITHOUT_PLAIN = "public without sharing class C { void m(){ Object o = [SELECT Id FROM X__c]; } }"
    WITH_PLAIN = "public with sharing class C { void m(){ Object o = [SELECT Id FROM X__c]; } }"
    NO_DECL = "public class C { void m(){ Object o = [SELECT Id FROM X__c]; } }"
    WITHOUT_USERMODE = "public without sharing class C { void m(){ Object o = [SELECT Id FROM X__c WITH USER_MODE]; } }"
    WITH_SYSTEMMODE = "public with sharing class C { void m(){ Object o = [SELECT Id FROM X__c WITH SYSTEM_MODE]; } }"

    def test_without_plain_v58_is_system(self):
        rm = resolved(self.WITHOUT_PLAIN, 58.0)
        self.assertFalse(rm.enforces_sharing)
        self.assertFalse(rm.enforces_fls)

    def test_without_plain_v67_is_user(self):
        rm = resolved(self.WITHOUT_PLAIN, 67.0)
        self.assertTrue(rm.enforces_sharing)
        self.assertTrue(rm.enforces_fls)

    def test_user_mode_overrides_without_sharing(self):
        # E3 encoded: operation clause beats class declaration, any version.
        for api in (58.0, 67.0):
            rm = resolved(self.WITHOUT_USERMODE, api)
            self.assertTrue(rm.enforces_sharing, api)
            self.assertTrue(rm.enforces_fls, api)

    def test_system_mode_clause_disables_both(self):
        rm = resolved(self.WITH_SYSTEMMODE, 67.0)
        self.assertFalse(rm.enforces_sharing)
        self.assertFalse(rm.enforces_fls)

    def test_with_sharing_v58_enforces_record_not_fls(self):
        rm = resolved(self.WITH_PLAIN, 58.0)
        self.assertTrue(rm.enforces_sharing)   # record-level from `with sharing`
        self.assertFalse(rm.enforces_fls)      # FLS still system at v58

    def test_no_declaration_record_access_is_undetermined(self):
        # E2 round 1: a declaration-less class inherits the caller - not system.
        rm = resolved(self.NO_DECL, 58.0)
        self.assertIsNone(rm.enforces_sharing)
        self.assertIsNotNone(rm.note)


class ExtractionTest(unittest.TestCase):
    def test_fields_extracted(self):
        src = "public without sharing class C { void m(){ Object o = [SELECT Id, Name, Customer_IBAN__c FROM Blast_Test__c]; } }"
        op = parse_apex_source(src, 58.0).operations[0]
        self.assertEqual(op.sobject, "Blast_Test__c")
        self.assertEqual(op.fields, ["Id", "Name", "Customer_IBAN__c"])
        self.assertTrue(op.fields_complete)

    def test_dynamic_soql_flagged_not_guessed(self):
        src = "public without sharing class C { void m(){ Object o = Database.query('SELECT ' + x + ' FROM Y__c'); } }"
        r = parse_apex_source(src, 58.0)
        self.assertTrue(r.dynamic_soql)
        dyn = [o for o in r.operations if o.dynamic]
        self.assertEqual(len(dyn), 1)
        self.assertIsNone(dyn[0].resolved.enforces_fls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
