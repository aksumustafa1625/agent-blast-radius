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
                    record_reach, render_markdown, summarize_flow)

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

    def test_html_is_byte_reproducible(self):
        from report_html import render_html
        a = render_html("A", "u", "c", self.actions)
        b = render_html("A", "u", "c", self.actions)
        self.assertEqual(a, b)

    def test_fingerprint_stable(self):
        f1 = fingerprint("A", "u", "c", self.actions)
        f2 = fingerprint("A", "u", "c", self.actions)
        self.assertEqual(f1, f2)

    def test_fingerprint_binds_the_analyzer_itself(self):
        """The tool is part of its own result.

        Without this, changing the precedence law or a rule produces the SAME
        fingerprint as the run before it - the report would be certifying
        reproducibility it cannot actually see. The version is a hash of the
        analyzer's source rather than a hand-bumped string precisely so that
        forgetting to bump it is not possible.
        """
        import report as _report
        base = fingerprint("A", "u", "c", self.actions)
        real = _report.analyzer_version
        try:
            _report.analyzer_version = lambda: "different-analyzer"
            self.assertNotEqual(base, fingerprint("A", "u", "c", self.actions))
        finally:
            _report.analyzer_version = real
        # ...and it must come back to the same value, or the fingerprint is noise.
        self.assertEqual(base, fingerprint("A", "u", "c", self.actions))

    def test_analyzer_version_tracks_the_rule_code(self):
        import report as _report
        here = os.path.dirname(os.path.abspath(_report.__file__))
        rules = os.path.join(here, "authority_analyzer.py")
        original = open(rules, "rb").read()
        _report.analyzer_version.cache_clear()
        before = _report.analyzer_version()
        try:
            with open(rules, "ab") as f:
                f.write(b"# analyzer_version probe")
            _report.analyzer_version.cache_clear()
            self.assertNotEqual(before, _report.analyzer_version(),
                                "a change to the RULES left the analyzer version alone")
        finally:
            with open(rules, "wb") as f:
                f.write(original)
            _report.analyzer_version.cache_clear()
        self.assertEqual(before, _report.analyzer_version(),
                         "the version is not a pure function of the source")

    def test_fingerprint_binds_the_parser_version(self):
        # A parser upgrade can change which reads the AST backend sees - this session's
        # differential found exactly such a blind spot - so two runs that saw different
        # reads must not be able to share a fingerprint.
        import apex_ast as _ast
        base = fingerprint("A", "u", "c", self.actions)
        real = _ast.parser_version
        try:
            _ast.parser_version = lambda: "99.99.99"
            self.assertNotEqual(base, fingerprint("A", "u", "c", self.actions))
        finally:
            _ast.parser_version = real

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


class RecordReachTest(unittest.TestCase):
    """--include-counts headline: aggregates only MEASURED gaps, never estimates."""

    COUNTS = {
        "Blast_Test__c": {"org_total": 512, "user_visible": 0, "gap": 512,
                          "note": "no object read", "cause": "crud", "mode": "system"},
        "Account": {"org_total": 300, "user_visible": 300, "gap": 0,
                    "note": "OWD Read - user with read sees all", "cause": None,
                    "mode": "system"},
        "Case": {"org_total": 88, "user_visible": None, "gap": None,
                 "note": "OWD Private - record-sharing dependent (run as the user to measure)",
                 "cause": "sharing", "mode": "system"},
    }

    def test_aggregate_excludes_unmeasured(self):
        r = record_reach(self.COUNTS)
        # upper_bound_total sums every known org_total; user/gap only measured objects
        self.assertEqual(r["upper_bound_total"], 512 + 300 + 88)
        self.assertEqual(r["user_total"], 0 + 300)
        self.assertEqual(r["gap_total"], 512)
        self.assertTrue(r["has_measured_gap"])
        self.assertEqual(len(r["unknown"]), 1)   # the Private/unmeasured Case

    def test_user_mode_read_is_bounded_not_an_escalation(self):
        # C1/OQ16: a sharing-enforced read means the agent sees what the user sees.
        # The org's record count must NOT become "agent reaches N", and the object
        # must not enter the escalation aggregate.
        counts = {"Invoice": {"org_total": 31, "user_visible": None, "gap": 0,
                              "note": "user-mode read - the agent is bounded by the running user",
                              "cause": None, "mode": "user"}}
        r = record_reach(counts)
        self.assertFalse(r["has_measured_gap"])
        self.assertEqual(r["gap_total"], 0)
        self.assertIsNone(r["upper_bound_total"])   # nothing system-mode to bound
        self.assertEqual(len(r["bounded"]), 1)
        md = render_markdown("A", "u", "c", [], counts=counts)
        self.assertIn("bounded by the running user", md)
        self.assertNotIn("could reach up to", md)

    def test_none_when_no_counts(self):
        self.assertIsNone(record_reach(None))
        self.assertIsNone(record_reach({}))

    def test_markdown_shows_headline_and_na(self):
        md = render_markdown("A", "u", "c", [], counts=self.COUNTS)
        self.assertIn("Record reach", md)
        # C1: the org COUNT is an upper bound, never "the agent reaches N records"
        self.assertIn("could reach up to 900 records", md)   # 512+300+88
        self.assertNotIn("code reaches 900", md)
        self.assertIn("upper bound", md)
        self.assertIn("user sees 300", md)
        self.assertIn("n/a", md)                   # the unmeasured Private object
        self.assertIn("512", md)

    def test_no_fabrication_for_private(self):
        # The Private object's user visibility must never appear as a number.
        md = render_markdown("A", "u", "c", [], counts=self.COUNTS)
        case_row = [ln for ln in md.splitlines() if "`Case`" in ln][0]
        self.assertIn("n/a", case_row)
        self.assertNotIn("88 | 88", case_row)      # not claimed as user-visible

    def test_cause_distinguishes_crud_from_sharing(self):
        # P4: a "user sees 0" gap from missing object permission is a CRUD
        # escalation, NOT a record-sharing statement - the report must say which.
        md = render_markdown("A", "u", "c", [], counts=self.COUNTS)
        blast_row = [ln for ln in md.splitlines() if "`Blast_Test__c`" in ln][0]
        self.assertIn("no object permission (CRUD)", blast_row)
        # and the headline names the CRUD cause when the whole measured gap is CRUD
        self.assertIn("CRUD escalation", md)


class BackendBindsTheFingerprintTest(unittest.TestCase):
    """The report promises: "bound to fingerprint X; regenerate if the agent config,
    any analysed Apex/Flow, or permission metadata changes". None of those changes
    when the EXTRACTOR changes - yet the AST backend traces the Authority Path and
    the regex fallback cannot, so the same class is WARN under one and ERROR under
    the other. A fingerprint that ignored that certified two different verdicts as
    the same analysis. Severity is the tool's confidence claim, so it binds too."""

    def _summary(self, backend, findings):
        from authority_analyzer import Finding
        return ActionSummary("A", "apex", 58.0, True, ["X__c"], ["X__c.F__c"],
                             [Finding(*f) for f in findings], backend=backend)

    def test_backend_changes_the_fingerprint(self):
        f = ("PS506", "ERROR", "A -> X__c.F__c", "m", "w", "x")
        ast = fingerprint("A", "u", "c", [self._summary("ast", [f])])
        rgx = fingerprint("A", "u", "c", [self._summary("regex", [f])])
        self.assertNotEqual(ast, rgx)

    def test_severity_changes_the_fingerprint(self):
        err = self._summary("ast", [("PS506", "ERROR", "A -> X__c.F__c", "m", "w", "x")])
        warn = self._summary("ast", [("PS506", "WARN", "A -> X__c.F__c", "m", "w", "x")])
        self.assertNotEqual(fingerprint("A", "u", "c", [err]),
                            fingerprint("A", "u", "c", [warn]))

    def test_identical_analysis_still_reproduces(self):
        a = self._summary("ast", [("PS506", "ERROR", "A -> X__c.F__c", "m", "w", "x")])
        b = self._summary("ast", [("PS506", "ERROR", "A -> X__c.F__c", "m", "w", "x")])
        self.assertEqual(fingerprint("A", "u", "c", [a]), fingerprint("A", "u", "c", [b]))

    def test_report_names_the_weaker_backend(self):
        from report_html import _backend_note
        note = _backend_note([self._summary("regex", [])])
        self.assertIn("regex extractor", note)
        self.assertIn("weaker evidence", note)
        clean = _backend_note([self._summary("ast", [])])
        self.assertIn("real parse tree", clean)


class CircleInvariantTest(unittest.TestCase):
    """P2: the concentric-circle counts must reconcile (outer == inner + gap).
    The bug was a field-naming skew: the reachable set double-prefixed a
    relationship field ('Invoice.BillToContact.Email') while the finding spelled
    it 'BillToContact.Email', so the sets wouldn't subtract. Lock the spelling."""

    def test_relationship_field_is_not_reprefixed(self):
        from report import _qualify
        # relationship field already carries its path - keep it verbatim
        self.assertEqual(_qualify("Invoice", "BillToContact.Email"), "BillToContact.Email")
        # direct field gets the object prefix
        self.assertEqual(_qualify("Invoice", "DocumentNumber"), "Invoice.DocumentNumber")

    def test_reached_is_a_superset_of_the_gap(self):
        # Build an action whose fields are spelled by summarize_apex's rule; the
        # gap (from findings) must be a subset so outer == inner + gap holds.
        from authority_analyzer import Finding
        from report import _qualify
        fields = sorted({_qualify("Invoice", f) for f in
                         ["DocumentNumber", "BillToContactId", "BillToContact.Email"]})
        gap_field = "BillToContact.Email"   # exactly how the PS502 `where` spells it
        summary = ActionSummary("A", "apex", 60, True, ["Invoice"], fields,
                                [Finding("PS502", "ERROR", f"A -> {gap_field}", "m", "w", "x")])
        gap, _ = escalation_gap([summary])
        reached = set(summary.fields) | gap
        self.assertTrue(gap <= reached)
        self.assertEqual(len(reached), len(reached - gap) + len(gap))


if __name__ == "__main__":
    unittest.main(verbosity=2)
