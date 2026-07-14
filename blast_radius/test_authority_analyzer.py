"""Tests for authority_analyzer: the join produces the real findings.

Run from the repo root:  python blast_radius/test_authority_analyzer.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apex_introspect import parse_apex_source  # noqa: E402
from authority_analyzer import analyze_apex, analyze_flow  # noqa: E402
from flow_introspect import parse_flow  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_FLOW = os.path.join(HERE, "..", "force-app", "main", "default", "flows",
                         "BlastR_System_Flow.flow-meta.xml")

CLASSIFICATION = {
    "Blast_Test__c.Customer_IBAN__c": {
        "complianceGroup": "PII;GDPR", "securityClassification": "Confidential"
    }
}
OBJECT_SHARING = {"Blast_Test__c": "Private"}


def load_perms(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))


def rules(findings):
    return {f.rule for f in findings}


class FlowHeadlineTest(unittest.TestCase):
    """The scary-but-true line, produced from real artifacts."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REAL_FLOW):
            raise unittest.SkipTest("real flow not found")
        cls.reach = parse_flow(REAL_FLOW)

    def test_minimal_user_gets_ps506_and_ps510_and_ps501(self):
        perms = load_perms("user_minimal.json")   # no FLS on Customer_IBAN__c
        findings = analyze_flow(self.reach, perms, CLASSIFICATION, OBJECT_SHARING)
        r = rules(findings)
        self.assertIn("PS506", r)   # GDPR field invisible to user reaches model
        self.assertIn("PS510", r)   # system-mode-without-sharing flow
        self.assertIn("PS501", r)   # Private object, record escalation

    def test_no_false_positive_on_id_field(self):
        perms = load_perms("user_minimal.json")
        findings = analyze_flow(self.reach, perms, CLASSIFICATION, OBJECT_SHARING)
        # Id is always readable; it must not produce an FLS finding.
        self.assertFalse(any(f.where.endswith(".Id") for f in findings))

    def test_admin_no_escalation(self):
        perms = load_perms("snapshot_admin_real.json")  # ViewAllData + FLS
        findings = analyze_flow(self.reach, perms, CLASSIFICATION, OBJECT_SHARING)
        r = rules(findings)
        self.assertNotIn("PS506", r)   # admin can see the field
        self.assertNotIn("PS501", r)   # admin sees all records
        self.assertIn("PS510", r)      # the flow's mode is still worth stating


class ApexVersionAwarenessTest(unittest.TestCase):
    """Same field read escalates at v58 but is clean at v67 - no false positive."""

    SRC = ("public without sharing class R { void m(){ "
           "Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c]; } }")

    def test_v58_produces_ps506_and_ps511(self):
        perms = load_perms("user_minimal.json")
        reach = parse_apex_source(self.SRC, 58.0, class_name="R58")
        findings = analyze_apex(reach, perms, CLASSIFICATION, OBJECT_SHARING)
        r = rules(findings)
        self.assertIn("PS506", r)
        self.assertIn("PS511", r)   # legacy API version

    def test_v67_no_ps506(self):
        perms = load_perms("user_minimal.json")
        reach = parse_apex_source(self.SRC, 67.0, class_name="R67")
        findings = analyze_apex(reach, perms, CLASSIFICATION, OBJECT_SHARING)
        r = rules(findings)
        # v67 user-mode default enforces FLS -> no escalation, no false positive.
        self.assertNotIn("PS506", r)
        self.assertNotIn("PS502", r)
        self.assertNotIn("PS511", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
