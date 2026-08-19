"""Tests for flow_introspect, run against the real deployed Flow.

Run from the repo root:  python blast_radius/test_flow_introspect.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from authority_analyzer import analyze_flow  # noqa: E402
from flow_introspect import parse_flow, resolve_mode  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_FLOW = os.path.join(
    HERE, "..", "force-app", "main", "default", "flows",
    "BlastR_System_Flow.flow-meta.xml",
)

CLASSIFICATION = {"Blast_Test__c.Customer_IBAN__c":
                  {"complianceGroup": "PII;GDPR", "securityClassification": "Confidential"}}
OBJECT_SHARING = {"Blast_Test__c": "Private"}


def _perms(name="user_minimal.json"):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))


def _flow_xml(process_type="AutoLaunchedFlow", run_in_mode=None, trigger_type=None):
    """A minimal flow that reads the GDPR field on the Private fixture object.
    Only the three context-bearing elements vary between cases."""
    mode = f"    <runInMode>{run_in_mode}</runInMode>\n" if run_in_mode else ""
    trig = f"        <triggerType>{trigger_type}</triggerType>\n" if trigger_type else ""
    obj = "        <object>Blast_Test__c</object>\n" if trigger_type else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Flow xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        "    <apiVersion>63.0</apiVersion>\n"
        "    <label>Fixture Flow</label>\n"
        f"    <processType>{process_type}</processType>\n"
        "    <recordLookups>\n"
        "        <name>Get_Rows</name>\n"
        "        <object>Blast_Test__c</object>\n"
        "        <queriedFields>Id</queriedFields>\n"
        "        <queriedFields>Customer_IBAN__c</queriedFields>\n"
        "    </recordLookups>\n"
        f"{mode}"
        "    <start>\n"
        f"{obj}{trig}"
        "        <connector><targetReference>Get_Rows</targetReference></connector>\n"
        "    </start>\n"
        "    <status>Active</status>\n"
        "</Flow>\n")


def _write(tmpdir, name, xml):
    path = os.path.join(tmpdir, name + ".flow-meta.xml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return path


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

    def test_no_trigger_type(self):
        self.assertIsNone(self.reach.trigger_type)


class ModeResolutionLawTest(unittest.TestCase):
    """The flow-context law in isolation: TYPE first, then tag, then unknown.

    Before 2026-08-19 `process_type` was read and never used, and the no-tag
    default was user mode with sharing - so a record-triggered flow resolved to
    CLEAN on both axes. That is the silent false clean CLAUDE.md §3 exists to
    prevent; it was found by an external mechanism audit, not by us. The type
    branch is platform-doc (flowtest's own ordering + the Flow Run Context
    docs), NOT yet measured in-org, and the tests say exactly that."""

    def test_record_triggered_no_tag_is_system_without_sharing(self):
        for trig in ("RecordAfterSave", "RecordBeforeSave", "RecordBeforeDelete"):
            system, sharing, src = resolve_mode("AutoLaunchedFlow", trig, None)
            self.assertTrue(system, trig)
            self.assertFalse(sharing, trig)
            self.assertIn("platform-doc", src)

    def test_scheduled_and_platform_event_are_system_without_sharing(self):
        for trig in ("Scheduled", "PlatformEvent"):
            system, sharing, _ = resolve_mode("AutoLaunchedFlow", trig, None)
            self.assertEqual((system, sharing), (True, False), trig)

    def test_process_builder_types_are_system_without_sharing(self):
        for pt in ("Workflow", "CustomEvent"):
            system, sharing, _ = resolve_mode(pt, None, None)
            self.assertEqual((system, sharing), (True, False), pt)

    def test_type_beats_a_safer_tag_and_says_so(self):
        # Trusting a DefaultMode tag on a record-triggered flow would be the false
        # clean in its purest form; whether the platform honours one is unmeasured.
        system, sharing, src = resolve_mode("AutoLaunchedFlow", "RecordAfterSave", "DefaultMode")
        self.assertEqual((system, sharing), (True, False))
        self.assertIn("DefaultMode", src)
        self.assertIn("not trusted", src)

    def test_autolaunched_no_tag_is_undetermined_not_user_mode(self):
        system, sharing, src = resolve_mode("AutoLaunchedFlow", None, None)
        self.assertIsNone(system)
        self.assertIsNone(sharing)
        self.assertIn("undetermined", src)

    def test_invocable_process_no_tag_is_undetermined(self):
        # flowtest maps it to DefaultMode; the docs say processes run in system
        # context; this project has measured neither, so it is neither.
        system, sharing, _ = resolve_mode("InvocableProcess", None, None)
        self.assertIsNone(system)
        self.assertIsNone(sharing)

    def test_explicit_tag_still_wins_on_a_selectable_type(self):
        self.assertEqual(resolve_mode("AutoLaunchedFlow", None, "SystemModeWithoutSharing")[:2],
                         (True, False))
        self.assertEqual(resolve_mode("AutoLaunchedFlow", None, "SystemModeWithSharing")[:2],
                         (True, True))
        self.assertEqual(resolve_mode("AutoLaunchedFlow", None, "DefaultMode")[:2],
                         (False, True))
        self.assertEqual(resolve_mode("Flow", None, "DefaultMode")[:2], (False, True))

    def test_unknown_tag_value_is_undetermined(self):
        system, sharing, src = resolve_mode("AutoLaunchedFlow", None, "SomethingNew")
        self.assertIsNone(system)
        self.assertIn("unrecognised", src)


class FlowContextVerdictTest(unittest.TestCase):
    """End to end through parse_flow -> analyze_flow, for a user with no FLS on
    the GDPR field and no record access beyond sharing on a Private object."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.perms = _perms()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _analyse(self, name, **kw):
        reach = parse_flow(_write(self.tmp.name, name, _flow_xml(**kw)))
        return reach, analyze_flow(reach, self.perms, CLASSIFICATION, OBJECT_SHARING)

    def test_record_triggered_no_tag_fires_ps510_error_and_ps506(self):
        reach, findings = self._analyse("rt", trigger_type="RecordAfterSave")
        self.assertEqual(reach.trigger_type, "RecordAfterSave")
        self.assertTrue(reach.runs_in_system_context)
        self.assertFalse(reach.enforces_sharing)
        self.assertFalse(reach.enforces_fls)
        by_rule = {f.rule: f for f in findings}
        self.assertIn("PS510", by_rule)
        self.assertEqual(by_rule["PS510"].severity, "ERROR")
        self.assertIn("platform-doc", by_rule["PS510"].message)   # provenance stated
        self.assertIn("PS506", by_rule)                            # GDPR field escapes
        self.assertIn("PS501", by_rule)                            # Private object, no sharing
        self.assertNotIn("PS504", by_rule)                         # nothing is unknown here

    def test_autolaunched_no_tag_is_ps504_not_clean_and_not_proven(self):
        reach, findings = self._analyse("al")
        self.assertIsNone(reach.runs_in_system_context)
        self.assertIsNone(reach.enforces_fls)
        self.assertTrue(reach.is_escalation_capable)     # worst case in the summary
        by_rule = {f.rule: f for f in findings}
        self.assertIn("PS504", by_rule, "an undetermined context must be said out loud")
        self.assertEqual(by_rule["PS504"].severity, "WARN")
        self.assertNotIn("PS510", by_rule)               # no mode was proven
        # The GDPR field the user cannot see is a BOUNDARY (WARN), never a proven
        # escalation (ERROR) and never silently dropped (absent).
        self.assertIn("PS506", by_rule)
        self.assertEqual(by_rule["PS506"].severity, "WARN")
        self.assertIn("possibly system", by_rule["PS506"].message)
        self.assertIn("PS501", by_rule)
        self.assertEqual(by_rule["PS501"].severity, "WARN")

    def test_explicit_tag_on_autolaunched_is_honored(self):
        # Without sharing -> the headline ERROR, as before this change.
        _, f1 = self._analyse("sws", run_in_mode="SystemModeWithoutSharing")
        r1 = {f.rule: f for f in f1}
        self.assertEqual(r1["PS510"].severity, "ERROR")
        self.assertEqual(r1["PS506"].severity, "ERROR")
        self.assertNotIn("PS504", r1)
        # With sharing -> WARN on the flow, FLS still bypassed so PS506 still ERROR.
        _, f2 = self._analyse("ss", run_in_mode="SystemModeWithSharing")
        r2 = {f.rule: f for f in f2}
        self.assertEqual(r2["PS510"].severity, "WARN")
        self.assertIn("PS506", r2)
        self.assertNotIn("PS501", r2)                    # sharing enforced
        # DefaultMode -> user context: FLS enforced, the read is bounded.
        reach3, f3 = self._analyse("dm", run_in_mode="DefaultMode")
        self.assertFalse(reach3.is_escalation_capable)
        r3 = {f.rule for f in f3}
        self.assertNotIn("PS510", r3)
        self.assertNotIn("PS506", r3)
        self.assertNotIn("PS502", r3)
        self.assertNotIn("PS504", r3)

    def test_admin_still_sees_the_mode_but_no_escalation(self):
        reach = parse_flow(_write(self.tmp.name, "rt_admin",
                                  _flow_xml(trigger_type="RecordAfterSave")))
        findings = analyze_flow(reach, _perms("snapshot_admin_real.json"),
                                CLASSIFICATION, OBJECT_SHARING)
        r = {f.rule for f in findings}
        self.assertIn("PS510", r)
        self.assertNotIn("PS506", r)
        self.assertNotIn("PS501", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
