"""Tests for authority_analyzer: the join produces the real findings.

Run from the repo root:  python blast_radius/test_authority_analyzer.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apex_introspect import parse_apex, parse_apex_source  # noqa: E402
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


class TriggerCascadeTest(unittest.TestCase):
    """PS509: a DML on an object with a pre-v67 active trigger cascades."""

    INLINE = "public with sharing class C { void m(){ insert new Casc_Parent__c(Name='x'); } }"
    VAR = ("public with sharing class C { void m(){ "
           "List<Casc_Parent__c> items = new List<Casc_Parent__c>(); insert items; } }")

    def _rules(self, src, triggers):
        perms = load_perms("user_minimal.json")
        reach = parse_apex_source(src, 67.0, class_name="C")
        return {f.rule for f in analyze_apex(reach, perms, {}, {}, triggers)}

    def test_legacy_trigger_flags_ps509(self):
        triggers = {"Casc_Parent__c": [{"name": "CascParentTrigger", "apiVersion": 58}]}
        self.assertIn("PS509", self._rules(self.INLINE, triggers))

    def test_v67_trigger_no_ps509(self):
        triggers = {"Casc_Parent__c": [{"name": "CascParentTrigger", "apiVersion": 67}]}
        self.assertNotIn("PS509", self._rules(self.INLINE, triggers))

    def test_typed_variable_dml_resolves_object(self):
        triggers = {"Casc_Parent__c": [{"name": "T", "apiVersion": 58}]}
        self.assertIn("PS509", self._rules(self.VAR, triggers))

    def test_no_active_trigger_no_ps509(self):
        self.assertNotIn("PS509", self._rules(self.INLINE, {}))


class WriteEscalationTest(unittest.TestCase):
    """PS503: system-mode DML on an object the running user cannot write."""

    def _rules(self, src, api):
        perms = load_perms("user_minimal.json")  # no create/edit anywhere
        reach = parse_apex_source(src, api, class_name="C")
        return {f.rule for f in analyze_apex(reach, perms, {}, {}, {})}

    def test_system_mode_insert_without_create_flags_ps503(self):
        src = "public class C { void m(){ insert new Widget__c(Name='x'); } }"
        self.assertIn("PS503", self._rules(src, 58.0))

    def test_as_user_insert_no_ps503(self):
        # `insert as user` enforces the user's CRUD -> not an escalation.
        src = "public class C { void m(){ insert as user new Widget__c(Name='x'); } }"
        self.assertNotIn("PS503", self._rules(src, 58.0))

    def test_v67_plain_insert_no_ps503(self):
        # v67 database default is user mode -> CRUD enforced, no escalation.
        src = "public class C { void m(){ insert new Widget__c(Name='x'); } }"
        self.assertNotIn("PS503", self._rules(src, 67.0))


class SelectorFollowTest(unittest.TestCase):
    """PS508: reach lives in a delegated selector class, not the action."""

    ROOT = os.path.join(HERE, "fixtures", "apex_selector")
    SVC = os.path.join(ROOT, "classes", "HR_ServiceDemo.cls")

    def test_without_follow_the_reach_is_missed(self):
        # The action itself has no SOQL; without following, it looks clean.
        reach = parse_apex(self.SVC)
        self.assertFalse(any(o.sobject == "Blast_Test__c" for o in reach.operations))

    def test_follow_merges_selector_reach(self):
        reach = parse_apex(self.SVC, source_root=self.ROOT)
        reads = [o for o in reach.operations if o.sobject == "Blast_Test__c"]
        self.assertTrue(any("Customer_IBAN__c" in o.fields for o in reads))

    def test_follow_catches_the_escalation(self):
        perms = load_perms("user_minimal.json")
        reach = parse_apex(self.SVC, source_root=self.ROOT)
        rules = {f.rule for f in analyze_apex(
            reach, perms,
            {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR;PII"}},
            {"Blast_Test__c": "Private"}, {})}
        self.assertIn("PS506", rules)

    def test_deeper_chain_flags_ps508(self):
        perms = load_perms("user_minimal.json")
        reach = parse_apex(self.SVC, source_root=self.ROOT)
        rules = {f.rule for f in analyze_apex(reach, perms, {}, {}, {})}
        self.assertIn("PS508", rules)


class BeforeAfterFixTest(unittest.TestCase):
    """The tool doesn't just FIND escalations - it VERIFIES the fix. Mirrors the
    real SendPaymentRemindersAction before/after: adding WITH USER_MODE to a
    legacy read collapses the field-escalation gap to zero, while a genuinely
    separate issue (had there been one) would honestly remain."""

    GDPR = {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR;PII"}}
    SHARING = {"Blast_Test__c": "Private"}

    def _gap(self, src):
        from report import summarize_apex, escalation_gap
        perms = load_perms("user_minimal.json")
        reach = parse_apex_source(src, 58.0, class_name="Pay")
        findings = analyze_apex(reach, perms, self.GDPR, self.SHARING)
        gap, _ = escalation_gap([summarize_apex(reach, findings, "Pay")])
        return gap

    def test_fix_collapses_the_gap(self):
        before = ("public without sharing class Pay { void m(){ "
                  "Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c]; } }")
        after = ("public without sharing class Pay { void m(){ "
                 "Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c WITH USER_MODE]; } }")
        self.assertGreater(len(self._gap(before)), 0, "before-fix must show a gap")
        self.assertEqual(len(self._gap(after)), 0, "after WITH USER_MODE the gap must be 0")


class PrecedenceTest(unittest.TestCase):
    """The credibility fixture (spec v2 §12): the tool must NOT cry wolf. These
    encode the precedence law - (1) explicit operation clause > (2) apiVersion
    default > (3) sharing declaration - and prove the tool stays silent exactly
    where a naive 'without sharing => escalation' scanner would false-positive.
    A false positive here is the single defect that would discredit the tool."""

    GDPR = {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR;PII"}}
    SHARING = {"Blast_Test__c": "Private"}
    ESCALATIONS = {"PS501", "PS502", "PS503", "PS506"}

    def _rules(self, src, api, perms_file="user_minimal.json"):
        perms = load_perms(perms_file)
        reach = parse_apex_source(src, api, class_name="P")
        return {f.rule for f in analyze_apex(reach, perms, self.GDPR, self.SHARING)}

    def test_user_mode_clause_overrides_without_sharing(self):
        # `without sharing` but the QUERY is WITH USER_MODE -> operation clause wins,
        # FLS is enforced -> NO escalation. (PS511 legacy-inventory is fine/honest.)
        src = ("public without sharing class P { void m(){ "
               "Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c WITH USER_MODE]; } }")
        self.assertFalse(self._rules(src, 58.0) & self.ESCALATIONS,
                         "WITH USER_MODE must suppress escalation despite 'without sharing'")

    def test_v67_no_declaration_is_clean(self):
        # v67 default is user mode even with NO sharing declaration -> clean.
        src = "public class P { void m(){ Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c]; } }"
        r = self._rules(src, 67.0)
        self.assertFalse(r & self.ESCALATIONS)
        self.assertNotIn("PS511", r)   # v67 is not legacy

    def test_explicit_without_sharing_legacy_does_fire(self):
        # The genuine escalation: legacy `without sharing`, plain SOQL, GDPR field
        # the user can't see -> PS506 MUST fire (proving we don't under-report).
        src = ("public without sharing class P { void m(){ "
               "Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c]; } }")
        self.assertIn("PS506", self._rules(src, 58.0))

    def test_view_all_data_clears_record_escalation_but_not_fls(self):
        # THE subtle one. 'View All Data' bypasses record-level sharing but NOT
        # field-level security - they are separate controls (a MAD/VAD user with
        # no FLS on a field genuinely cannot see it). So against a system-mode
        # read of a Private object:
        #   - PS501 (record-scope) must NOT fire - VAD already sees all records.
        #   - PS506 (a GDPR field the user has no FLS on) MUST still fire - real.
        # This is exactly where a naive 'VAD => clean' shortcut would UNDER-report.
        src = ("public without sharing class P { void m(){ "
               "Object o = [SELECT Customer_IBAN__c FROM Blast_Test__c]; } }")
        r = self._rules(src, 58.0, perms_file="user_viewall.json")
        self.assertNotIn("PS501", r, "VAD sees all records -> no record-scope escalation")
        self.assertIn("PS506", r, "VAD does NOT override FLS -> the field still escalates")


class FindingDedupeTest(unittest.TestCase):
    """P1: one escalation is one finding. A class may read the same object in two
    SOQL statements (a 'find all' branch + a 'find one' branch over identical
    columns), which detects each field twice - but it is the same fact and must
    be reported once. When duplicates disagree on severity, the ERROR must win."""

    def test_duplicates_collapse_and_severity_is_preserved(self):
        from authority_analyzer import Finding, dedupe_findings
        warn = Finding("PS502", "WARN", "A -> X.f", "m", "w", "fix")
        err = Finding("PS502", "ERROR", "A -> X.f", "m", "w", "fix")
        other = Finding("PS502", "ERROR", "A -> X.g", "m", "w", "fix")
        out = dedupe_findings([warn, err, other])
        keys = [(f.rule, f.where) for f in out]
        self.assertEqual(len(keys), len(set(keys)), "duplicate findings survived dedupe")
        self.assertEqual(len(out), 2)
        collapsed = next(f for f in out if f.where == "A -> X.f")
        self.assertEqual(collapsed.severity, "ERROR", "an ERROR was masked by a WARN")

    def test_analyzer_emits_each_field_once_for_duplicate_reads(self):
        # Two identical read units over the same field (as a double-SOQL class
        # produces) must yield a single PS502 for that field.
        from authority_analyzer import AccessUnit, _analyze_units

        class _Res:
            enforces_sharing = False
            enforces_fls = False
            source = "test"
            is_escalation_capable = True

        def unit():
            return AccessUnit("read", "Blast_Test__c", ["Customer_IBAN__c"], True,
                              False, False, "test SOQL", None)

        perms = load_perms("user_minimal.json")
        findings = _analyze_units("A", [unit(), unit()], perms,
                                  {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR"}},
                                  {"Blast_Test__c": "Private"}, {})
        keys = [(f.rule, f.where) for f in findings]
        self.assertEqual(len(keys), len(set(keys)), "duplicate reads produced duplicate findings")


if __name__ == "__main__":
    unittest.main(verbosity=2)
