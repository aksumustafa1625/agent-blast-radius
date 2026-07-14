"""Tests for flow_introspect, run against the real deployed Flow.

Run from the repo root:  python blast_radius/test_flow_introspect.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flow_introspect import parse_flow  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_FLOW = os.path.join(
    HERE, "..", "force-app", "main", "default", "flows",
    "BlastR_System_Flow.flow-meta.xml",
)


class RealSystemFlowTests(unittest.TestCase):
    """BlastR_System_Flow: SystemModeWithoutSharing, reads a GDPR field."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REAL_FLOW):
            raise unittest.SkipTest(f"flow not found: {REAL_FLOW}")
        cls.reach = parse_flow(REAL_FLOW)

    def test_run_in_mode(self):
        self.assertEqual(self.reach.run_in_mode, "SystemModeWithoutSharing")

    def test_is_system_context(self):
        self.assertTrue(self.reach.runs_in_system_context)

    def test_does_not_enforce_sharing(self):
        self.assertFalse(self.reach.enforces_sharing)

    def test_severity_hint_is_error(self):
        self.assertEqual(self.reach.severity_hint, "ERROR")

    def test_reads_blast_test_with_gdpr_field(self):
        reads = [a for a in self.reach.accesses if a.operation == "read"]
        self.assertEqual(len(reads), 1)
        acc = reads[0]
        self.assertEqual(acc.sobject, "Blast_Test__c")
        self.assertIn("Customer_IBAN__c", acc.fields)
        self.assertTrue(acc.fields_complete)


class ProcessTypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REAL_FLOW):
            raise unittest.SkipTest(f"flow not found: {REAL_FLOW}")
        cls.reach = parse_flow(REAL_FLOW)

    def test_process_type(self):
        self.assertEqual(self.reach.process_type, "AutoLaunchedFlow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
