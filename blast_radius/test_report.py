"""Tests for report: deterministic, fingerprint-bound, correct headline.

Run from the repo root:  python blast_radius/test_report.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from authority_analyzer import analyze_flow  # noqa: E402
from flow_introspect import parse_flow  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402
from report import (ActionSummary, escalation_gap, fingerprint,  # noqa: E402
                    render_markdown, summarize_flow)

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_FLOW = os.path.join(HERE, "..", "force-app", "main", "default", "flows",
                         "BlastR_System_Flow.flow-meta.xml")
CLASSIFICATION = {"Blast_Test__c.Customer_IBAN__c":
                  {"complianceGroup": "PII;GDPR", "securityClassification": "Confidential"}}
OBJECT_SHARING = {"Blast_Test__c": "Private"}


def _minimal_perms():
    with open(os.path.join(HERE, "fixtures", "user_minimal.json"), encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))


def _flow_action():
    reach = parse_flow(REAL_FLOW)
    findings = analyze_flow(reach, _minimal_perms(), CLASSIFICATION, OBJECT_SHARING)
    return summarize_flow(reach, findings)


class HeadlineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REAL_FLOW):
            raise unittest.SkipTest("real flow not found")
        cls.actions = [_flow_action()]

    def test_escalation_gap_counts_gdpr_field(self):
        gap, gdpr = escalation_gap(self.actions)
        self.assertIn("Blast_Test__c.Customer_IBAN__c", gap)
        self.assertIn("Blast_Test__c.Customer_IBAN__c", gdpr)

    def test_report_contains_headline_and_findings(self):
        md = render_markdown("HW_Energy_Agent", "svc@example.com",
                             "web-unauthenticated", self.actions)
        self.assertIn("ESCALATION GAP", md)
        self.assertIn("PS506", md)
        self.assertIn("PS510", md)
        self.assertIn("0 Flex Credits", md)


class DeterminismTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REAL_FLOW):
            raise unittest.SkipTest("real flow not found")
        cls.actions = [_flow_action()]

    def test_report_is_byte_reproducible(self):
        a = render_markdown("A", "u", "c", self.actions)
        b = render_markdown("A", "u", "c", self.actions)
        self.assertEqual(a, b)

    def test_fingerprint_stable(self):
        f1 = fingerprint("A", "u", "c", self.actions)
        f2 = fingerprint("A", "u", "c", self.actions)
        self.assertEqual(f1, f2)

    def test_fingerprint_changes_when_findings_change(self):
        base = fingerprint("A", "u", "c", self.actions)
        stripped = ActionSummary(
            self.actions[0].name, self.actions[0].kind, self.actions[0].api_version,
            self.actions[0].system_mode, self.actions[0].objects, self.actions[0].fields,
            self.actions[0].findings[:-1])
        self.assertNotEqual(base, fingerprint("A", "u", "c", [stripped]))


class CleanReportTest(unittest.TestCase):
    def test_no_findings_reports_clean(self):
        clean = ActionSummary("CleanAction", "apex", 67.0, False,
                              ["Blast_Test__c"], ["Blast_Test__c.Secret_Data__c"], [])
        md = render_markdown("Agent", "user", "in-app", [clean])
        self.assertIn("No authority findings", md)
        self.assertIn("ESCALATION GAP ......... 0 fields", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
