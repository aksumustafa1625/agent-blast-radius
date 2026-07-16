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


class StripInaccessibleSanitizerTest(unittest.TestCase):
    """Security.stripInaccessible is the platform's real FLS sanitizer. Ignoring it
    flags correct code (false positive); trusting it blindly would hide a real leak
    (false negative). The rule: it never CLEARS a finding - it caps severity at WARN
    and says the path is unproven - and a discarded/wrong-AccessType decision is
    itself a finding (PS512)."""

    GDPR = {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR;PII"}}
    SHARING = {"Blast_Test__c": "Private"}
    QUERY = "List<Blast_Test__c> recs = [SELECT Customer_IBAN__c FROM Blast_Test__c];"

    def _find(self, body):
        perms = load_perms("user_minimal.json")
        src = "public without sharing class X { void m(){ %s } }" % body
        return {(f.rule, f.severity) for f in
                analyze_apex(parse_apex_source(src, 58.0, "X"), perms, self.GDPR, self.SHARING)}

    def test_without_sanitizer_the_escalation_is_proven(self):
        r = self._find(self.QUERY)
        self.assertIn(("PS506", "ERROR"), r)
        self.assertNotIn("PS512", {rule for rule, _ in r})

    def test_readable_sanitizer_caps_severity_but_never_clears(self):
        r = self._find(self.QUERY + " List<Blast_Test__c> safe = "
                       "Security.stripInaccessible(AccessType.READABLE, recs).getRecords();")
        self.assertIn(("PS506", "WARN"), r)          # unproven, not clean
        self.assertNotIn(("PS506", "ERROR"), r)      # no longer asserted as proven

    def test_discarded_decision_is_a_no_op_bug(self):
        r = self._find(self.QUERY + " Security.stripInaccessible(AccessType.READABLE, recs);")
        self.assertIn(("PS512", "ERROR"), r)         # the sanitizer does nothing
        self.assertIn(("PS506", "ERROR"), r)         # so the escalation stays proven

    def test_wrong_access_type_errs_safe_and_is_not_a_proven_leak(self):
        """The wrong AccessType is a bug, not a leak - and this test used to say the
        opposite. It asserted PS506 ERROR on the belief that "UPDATABLE strips nothing
        on a read". The runtime oracle refuted that in a live org on both branches:
        without object Edit stripInaccessible THROWS, with it the field is STRIPPED.
        FLS cannot grant Edit without Read, so unreadable implies un-updatable and any
        used decision removes at least what READABLE would. WARN, not ERROR, because
        we still cannot prove which list reaches the sink (see the class docstring)."""
        r = self._find(self.QUERY + " List<Blast_Test__c> s = "
                       "Security.stripInaccessible(AccessType.UPDATABLE, recs).getRecords();")
        self.assertIn(("PS512", "WARN"), r)
        self.assertIn(("PS506", "WARN"), r)
        self.assertNotIn(("PS506", "ERROR"), r)


class AsyncHandoffTest(unittest.TestCase):
    """PS514: async/event/callout work leaves the analysed transaction. Silently
    dropping it is the worst false negative a security tool can have - the agent's
    real reach can grow after the hand-off - so each is an explicit unknown edge."""

    def _rules(self, body):
        perms = load_perms("user_minimal.json")
        src = "public with sharing class X { void m(){ %s } }" % body
        return {(f.rule, f.severity) for f in
                analyze_apex(parse_apex_source(src, 67.0, "X"), perms, {}, {})}

    def test_platform_event_publish_is_flagged(self):
        self.assertIn(("PS514", "WARN"), self._rules("EventBus.publish(events);"))

    def test_queueable_and_batch_are_flagged(self):
        self.assertIn(("PS514", "WARN"), self._rules("System.enqueueJob(new J());"))
        self.assertIn(("PS514", "WARN"), self._rules("Database.executeBatch(new B());"))

    def test_callout_is_flagged(self):
        self.assertIn(("PS514", "WARN"), self._rules("HttpRequest req = new HttpRequest();"))

    def test_plain_action_has_no_handoff(self):
        r = self._rules("Integer i = 1;")
        self.assertNotIn("PS514", {rule for rule, _ in r})

    def test_real_action_publishing_an_event_is_caught(self):
        # Our own flagship demo class hands off to a platform event whose
        # subscriber this analyzer does not follow - it must say so.
        path = os.path.join(HERE, "..", "force-app", "main", "default", "classes",
                            "SendPaymentRemindersAction.cls")
        if not os.path.exists(path):
            self.skipTest("TechnoStore demo class not present")
        from apex_introspect import parse_apex
        self.assertIn("platform event", parse_apex(path).async_handoffs)


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


class SoslAndDynamicReadTest(unittest.TestCase):
    """Reads whose object/fields aren't fully known must never be silently clean.
    SOSL was previously not modeled at all (a blind spot); dynamic SOQL and
    RETURNING-less SOSL must both surface PS504."""

    GDPR = {"Blast_Test__c.Customer_IBAN__c": {"complianceGroup": "GDPR;PII"}}
    SHARING = {"Blast_Test__c": "Private"}

    def _rules(self, src, api):
        perms = load_perms("user_minimal.json")
        return {f.rule for f in analyze_apex(parse_apex_source(src, api, "X"),
                                             perms, self.GDPR, self.SHARING)}

    def test_dynamic_soql_surfaces_ps504(self):
        # Regression: a dynamic query with an unknown object must still warn.
        r = self._rules("public class D { void m(){ List<SObject> x = Database.query(q); } }", 58.0)
        self.assertIn("PS504", r)

    def test_sosl_without_returning_is_ps504(self):
        r = self._rules("public class S { void m(){ var x = [FIND :q IN ALL FIELDS]; } }", 58.0)
        self.assertIn("PS504", r)

    def test_sosl_returning_gdpr_field_v58_fires_ps506(self):
        src = ("public without sharing class S { void m(){ "
               "var x = [FIND :q IN ALL FIELDS RETURNING Blast_Test__c(Customer_IBAN__c)]; } }")
        self.assertIn("PS506", self._rules(src, 58.0))

    def test_sosl_returning_gdpr_field_v67_is_clean(self):
        src = ("public without sharing class S { void m(){ "
               "var x = [FIND :q IN ALL FIELDS RETURNING Blast_Test__c(Customer_IBAN__c)]; } }")
        self.assertNotIn("PS506", self._rules(src, 67.0))
        self.assertNotIn("PS502", self._rules(src, 67.0))


class CrossObjectClassificationTest(unittest.TestCase):
    """A query reaching `BillToContact.Email` really reads Contact.Email. Labels
    were only ever keyed per REACHED object, so a GDPR label sitting on Contact
    was structurally invisible and PS506 - the headline rule - silently missed it.
    The loader now aliases the target object's labels under the relationship path;
    these lock the analyzer half of that contract."""

    SRC = ("public with sharing class X { void m(){ List<Invoice> r = "
           "[SELECT DocumentNumber, BillToContact.Email FROM Invoice]; } }")

    def _rules(self, classification):
        perms = load_perms("user_minimal.json")
        reach = parse_apex_source(self.SRC, 58.0, "X")
        return {(f.rule, f.where.split("-> ")[-1])
                for f in analyze_apex(reach, perms, classification, {})}

    def test_relationship_field_keeps_its_own_path(self):
        # The spelling matters: the label lookup and the finding must agree.
        reach = parse_apex_source(self.SRC, 58.0, "X")
        read = [o for o in reach.operations if o.operation == "read"][0]
        self.assertIn("BillToContact.Email", read.fields)

    def test_unlabelled_cross_object_field_is_ps502_not_ps506(self):
        # Honest: TechnoStore's Contact.Email is SecurityClassification=Confidential
        # but has NO ComplianceGroup, so the untagged rule is the right answer.
        r = self._rules({})
        self.assertIn(("PS502", "BillToContact.Email"), r)
        self.assertNotIn(("PS506", "BillToContact.Email"), r)

    def test_labelled_cross_object_field_now_reaches_ps506(self):
        # This is what was structurally impossible before: the GDPR label lives on
        # Contact, the query says BillToContact.
        r = self._rules({"BillToContact.Email": {"complianceGroup": "GDPR;PII"}})
        self.assertIn(("PS506", "BillToContact.Email"), r)
        self.assertNotIn(("PS502", "BillToContact.Email"), r)
        # the direct field on the queried object is unaffected
        self.assertIn(("PS502", "Invoice.DocumentNumber"), r)


class PolymorphicSelectTest(unittest.TestCase):
    """A TYPEOF select defeated BOTH extractors: each returned mangled tokens
    ("TYPEOF What WHEN Account THEN Name") *and* claimed fields_complete, so no
    PS504 fired and one backend even raised PS502 on a nonsense field name. That
    is the worst failure this tool can have - a silent false-clean dressed as a
    full parse. It must be an honest unknown instead."""

    SRC = ("public without sharing class T { void m(){ List<Task> r = [SELECT Id, "
           "TYPEOF What WHEN Account THEN Name, Industry WHEN Opportunity THEN "
           "Amount END FROM Task]; } }")

    def test_typeof_is_an_honest_unknown_not_a_full_parse(self):
        perms = load_perms("user_minimal.json")
        reach = parse_apex_source(self.SRC, 58.0, "T")
        op = [o for o in reach.operations if o.operation == "read"][0]
        self.assertFalse(op.fields_complete, "a TYPEOF select must not claim completeness")
        self.assertEqual(op.fields, ["Id"], "mangled branch tokens must be dropped")
        rules = {f.rule for f in analyze_apex(reach, perms, {}, {})}
        self.assertIn("PS504", rules)
        self.assertNotIn("PS502", rules)   # never flag a nonsense field name

    def test_real_field_names_are_not_mistaken_for_polymorphic(self):
        from apex_introspect import _is_polymorphic_token
        for fld in ("TypeOfWork__c", "Amendment__c", "Whence__c", "Trend__c",
                    "Id", "Customer_IBAN__c"):
            self.assertFalse(_is_polymorphic_token(fld), fld)

    def test_the_signature_needs_both_when_and_then(self):
        from apex_introspect import _is_polymorphic_token
        self.assertTrue(_is_polymorphic_token("TYPEOF What WHEN Account THEN Name"))
        self.assertTrue(_is_polymorphic_token("TYPEOFWhatWHENAccountTHENName,Industry"))
        self.assertTrue(_is_polymorphic_token("Industry WHEN Opportunity THEN Amount END"))


class TriggerHandlerDelegationTest(unittest.TestCase):
    """PS509 must not be fooled by a v67 trigger that delegates its DML to a
    pre-v67 handler class - the DML runs in the handler's (system) mode."""

    SRC = "public with sharing class C { void m(){ insert as user new Casc_Parent__c(Name='x'); } }"

    def _ps509(self, trig):
        perms = load_perms("user_minimal.json")
        fs = analyze_apex(parse_apex_source(self.SRC, 67.0, "C"), perms, {}, {},
                          {"Casc_Parent__c": [trig]})
        return [(f.severity) for f in fs if f.rule == "PS509"]

    def test_v67_trigger_pre_v67_handler_warns(self):
        self.assertEqual(self._ps509(
            {"name": "T", "apiVersion": 67, "handler_min_api": 60.0}), ["WARN"])

    def test_v67_trigger_v67_handler_is_clean(self):
        self.assertEqual(self._ps509(
            {"name": "T", "apiVersion": 67, "handler_min_api": 67.0}), [])

    def test_legacy_trigger_without_a_proven_write_is_only_a_boundary(self):
        # Severity = proof level. A legacy trigger's mere existence is a boundary,
        # not an escalation: it may perform no DML at all. Claiming ERROR here was
        # the false positive an independent review flagged.
        self.assertEqual(self._ps509(
            {"name": "T", "apiVersion": 58, "handler_min_api": None, "dml_ops": []}), ["WARN"])

    def test_legacy_trigger_with_a_proven_escalating_write_errors(self):
        # Its own body inserts an object the running user cannot create -> proven.
        self.assertEqual(self._ps509(
            {"name": "T", "apiVersion": 58, "handler_min_api": None,
             "dml_ops": [("insert", "Casc_Child__c")]}), ["ERROR"])

    def test_legacy_trigger_writing_what_the_user_may_write_is_not_an_escalation(self):
        perms_snap = {
            "runningUser": "u", "channel": "agent",
            "systemPermissions": {"ViewAllData": False, "ModifyAllData": False},
            "objectPermissions": [{"parent": "PermSet:X", "sobjectType": "Casc_Child__c",
                                   "read": True, "create": True, "edit": True, "delete": True,
                                   "viewAllRecords": False, "modifyAllRecords": False}],
            "fieldPermissions": [],
        }
        perms = EffectivePermissions(perms_snap)
        fs = analyze_apex(parse_apex_source(self.SRC, 67.0, "C"), perms, {}, {},
                          {"Casc_Parent__c": [{"name": "T", "apiVersion": 58,
                                               "handler_min_api": None,
                                               "dml_ops": [("insert", "Casc_Child__c")]}]})
        self.assertEqual([f.severity for f in fs if f.rule == "PS509"], ["WARN"])


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


class FormulaFieldReachTest(unittest.TestCase):
    """PS516: a formula in the reach is an UNRESOLVED reach, not a proven leak.

    Raised by an external review, and concrete rather than hypothetical: 11 of
    Invoice's 93 fields are formulas and the flagship demo action reads one of them
    (TotalAmountWithTax). A formula's value is computed from other fields this
    analyzer does not resolve, so the running user's FLS on the formula does not bound
    what its value carries.

    It is the one channel a v67 read does not close - user mode enforces FLS on the
    formula the user CAN see, not on its inputs - which is why the test below fires it
    at v67, where every other rule stays quiet.

    Deliberately WARN and worded as OUR limit. Whether a formula really carries a
    field's value past FLS is a claim about the PLATFORM, and it is NOT measured: the
    fixture that would settle it could not be deployed (the deploy reports success and
    the field never appears). Claiming the leak would be the believed-premise mistake
    this tool has already been caught making once today.
    """

    SRC = ("public with sharing class C { void m(){ "
           "List<Invoice> r = [SELECT Total__c, Status FROM Invoice]; } }")

    def _find(self, api, calculated):
        reach = parse_apex_source(self.SRC, api)
        return {(f.rule, f.where.split("-> ")[-1])
                for f in analyze_apex(reach, load_perms("user_minimal.json"), {}, {}, {},
                                      calculated=calculated)}

    def test_formula_field_is_flagged_even_when_the_read_is_bounded(self):
        # v67: user mode enforces FLS, so nothing else fires - and PS516 still must,
        # because user mode never looked at what the formula reads.
        r = self._find(67.0, {"Invoice.Total__c"})
        self.assertIn(("PS516", "Invoice.Total__c"), r)

    def test_a_plain_field_is_not_flagged(self):
        r = self._find(67.0, {"Invoice.Total__c"})
        self.assertNotIn(("PS516", "Invoice.Status"), r)

    def test_nothing_fires_when_no_field_is_a_formula(self):
        self.assertEqual({f for f in self._find(67.0, set()) if f[0] == "PS516"}, set())

    def test_it_is_a_warning_not_a_proven_leak(self):
        reach = parse_apex_source(self.SRC, 67.0)
        fs = [f for f in analyze_apex(reach, load_perms("user_minimal.json"), {}, {}, {},
                                      calculated={"Invoice.Total__c"})
              if f.rule == "PS516"]
        self.assertEqual([f.severity for f in fs], ["WARN"],
                         "the platform behaviour is unmeasured; ERROR would claim proof")
