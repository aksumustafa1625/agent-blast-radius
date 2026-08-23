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


def _headline_block(md: str) -> str:
    """The report's first fenced block - the Aksu Index headline. Sliced by
    position on purpose: 'the Index opens the report' is the contract under
    test, so a test that searched for it anywhere would not be testing it."""
    lines = md.splitlines()
    assert lines[0] == "```", "the headline block must open the report"
    end = lines.index("```", 1)
    return "\n".join(lines[1:end])


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

    def test_standalone_html_declares_utf8(self):
        """The bug this guards: a charset-less file:// prints as mojibake in a
        headless engine while looking fine in a lenient browser - the same
        bytes, two verdicts. The em-dash in the title is real UTF-8, so the
        document MUST declare its encoding, or a PDF turns every "—" into "â".
        """
        from report_html import render_html, wrap_document
        doc = wrap_document(render_html("A", "u", "c", self.actions), "T — x")
        self.assertTrue(doc.lstrip().lower().startswith("<!doctype html>"))
        self.assertIn('<meta charset="utf-8">', doc)
        self.assertIn("—", doc)               # the em-dash survives verbatim
        self.assertIn("@media print", doc)          # print rules only on the doc
        # the fragment itself stays a fragment - no wrapper leaked into it
        self.assertNotIn("<!doctype", render_html("A", "u", "c", self.actions).lower())

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
        # 0 proven AND 0 unresolved genuinely is clean - the not-clean sentence
        # must not fire here, or it would cry wolf and stop being read where it
        # matters (the P=0, U>0 case).
        self.assertNotIn("NOT clean", md)


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


class FingerprintBindsTheApiVersionTest(unittest.TestCase):
    """The analysed class's apiVersion binds - it DRIVES the verdict.

    v58 and v67 resolve the same source oppositely (E2/E2b), so two reports whose
    only difference is the apiVersion are two different analyses and must not share a
    fingerprint. It was already bound per action; nothing tested it, so nothing would
    have caught it being dropped - the gap a task spec from an external reviewer
    correctly asked about.

    Bound PER ACTION rather than as one org-wide number, because a real agent's
    actions sit at different versions and a single max would erase exactly the
    difference this tool exists to report.
    """

    def _summary(self, api, name="A"):
        return ActionSummary(name, "apex", api, True, ["X__c"], ["X__c.f"], [])

    def test_a_different_api_version_moves_the_fingerprint(self):
        v58 = fingerprint("ag", "u", "c", [self._summary(58.0)])
        v67 = fingerprint("ag", "u", "c", [self._summary(67.0)])
        self.assertTrue(v58 and v67, "empty fingerprints would pass this vacuously")
        self.assertNotEqual(v58, v67)

    def test_the_same_api_version_reproduces(self):
        a = fingerprint("ag", "u", "c", [self._summary(58.0)])
        b = fingerprint("ag", "u", "c", [self._summary(58.0)])
        self.assertEqual(a, b)

    def test_every_action_carries_its_own_version(self):
        """A mid-migration agent has actions at DIFFERENT versions - that is the whole
        point of the tool - so each one must count, not a single org-wide number.

        The first draft of this test asserted that flipping two same-named actions kept
        the fingerprint stable. It was the TEST that was wrong: actions sort by name, a
        stable sort keeps input order for equal keys, and real action names are unique
        anyway. Asserting a property the code never claimed would have been my
        assumption, not a measurement."""
        mixed = fingerprint("ag", "u", "c",
                            [self._summary(58.0, "A"), self._summary(67.0, "B")])
        both58 = fingerprint("ag", "u", "c",
                             [self._summary(58.0, "A"), self._summary(58.0, "B")])
        self.assertTrue(mixed and both58)
        self.assertNotEqual(mixed, both58, "the second action's version must count too")

    def test_action_order_does_not_matter(self):
        # Same actions, listed the other way round: the same analysis, so the same
        # fingerprint. Otherwise the seal would move for a reason that is not a change.
        a, b = self._summary(58.0, "A"), self._summary(67.0, "B")
        self.assertEqual(fingerprint("ag", "u", "c", [a, b]),
                         fingerprint("ag", "u", "c", [b, a]))


class AksuIndexTest(unittest.TestCase):
    """The public metric (docs/AKSU_INDEX_SPEC.md) — the split IS the point.

    escalation_gap() mixes ERROR and WARN into one set, which is right for the
    concentric circles (the spec's gap is the union) and wrong for a quoted
    number: severity is the tool's proof claim, so the Index must never count a
    boundary it could not prove inside 'proven'. These tests pin the partition,
    the GDPR-within-proven rule, the unresolved counter, and the canonical line
    every report carries."""

    @staticmethod
    def _f(rule, sev, field):
        from authority_analyzer import Finding
        return Finding(rule, sev, f"A -> {field}", "m", "w", "x")

    def _action(self, findings):
        return ActionSummary("A", "apex", 58.0, True, ["X"], [], findings)

    def test_error_and_warn_land_in_different_buckets(self):
        from report import aksu_index
        ix = aksu_index([self._action([self._f("PS502", "ERROR", "X.A__c"),
                                       self._f("PS502", "WARN", "X.B__c")])])
        self.assertEqual(ix["proven"], {"X.A__c"})
        self.assertEqual(ix["boundary"], {"X.B__c"})

    def test_gdpr_counts_only_within_proven(self):
        # A WARN PS506 is a real boundary we could not prove crossed — quoting it
        # as a proven GDPR escalation would be the exact overclaim the spec forbids.
        from report import aksu_index
        ix = aksu_index([self._action([self._f("PS506", "WARN", "X.Iban__c")])])
        self.assertEqual(ix["gdpr"], set())
        self.assertEqual(ix["boundary"], {"X.Iban__c"})
        ix2 = aksu_index([self._action([self._f("PS506", "ERROR", "X.Iban__c")])])
        self.assertEqual(ix2["gdpr"], {"X.Iban__c"})
        self.assertEqual(ix2["proven"], {"X.Iban__c"})

    def test_most_severe_wins_across_actions(self):
        # Proven in ANY action = proven; the same field must not appear in both
        # buckets or the four numbers would double-count.
        from report import aksu_index
        ix = aksu_index([self._action([self._f("PS502", "WARN", "X.A__c")]),
                         self._action([self._f("PS502", "ERROR", "X.A__c")])])
        self.assertEqual(ix["proven"], {"X.A__c"})
        self.assertEqual(ix["boundary"], set())

    def test_unresolved_counts_ps504(self):
        from report import aksu_index
        ix = aksu_index([self._action([self._f("PS504", "WARN", "?"),
                                       self._f("PS504", "WARN", "?2")])])
        self.assertEqual(ix["unresolved"], 2)
        self.assertEqual(ix["proven"], set())

    def test_union_reconciles_with_escalation_gap(self):
        # The circles and the Index describe the same reality: gap == P ∪ B.
        from report import aksu_index
        findings = [self._f("PS502", "ERROR", "X.A__c"),
                    self._f("PS506", "WARN", "X.B__c")]
        gap, _ = escalation_gap([self._action(findings)])
        ix = aksu_index([self._action(findings)])
        self.assertEqual(gap, ix["proven"] | ix["boundary"])

    def test_canonical_line_in_markdown(self):
        md = render_markdown("A", "u", "c",
                             [self._action([self._f("PS506", "ERROR", "X.Iban__c"),
                                            self._f("PS504", "WARN", "?")])])
        self.assertIn("Aksu Index: 1 proven (1 GDPR) · 0 unproven boundaries · 1 unresolved", md)

    def test_zero_proven_with_unresolved_is_not_clean(self):
        # Spec §4.3: "Index = 0 with U > 0 is not clean" — the report must say so
        # in its own voice, not leave a bare 0 to be quoted as a pass. The
        # sentence has to sit inside the headline block, attached to the zero it
        # qualifies: a caveat further down the document is a footnote, and the
        # whole point of the headline is that it is read on its own.
        md = render_markdown("A", "u", "c",
                             [self._action([self._f("PS504", "WARN", "?")])])
        self.assertIn("Aksu Index: 0 proven (0 GDPR) · 0 unproven boundaries · 1 unresolved", md)
        self.assertIn("NOT clean", md)
        head = _headline_block(md)
        self.assertIn("NOT clean", head)
        # ...and it must follow the zero it qualifies, not precede it
        self.assertLess(head.index("0  PROVEN"), head.index("NOT clean"))


class AksuIndexHeadlineTest(unittest.TestCase):
    """The Index is the report's RESULT, so it is the report's first screen —
    CLAUDE.md §0.1. These pin the layout contract, not the prose: whoever
    reflows this block keeps the four numbers together, C inside P, the P=0/U>0
    caveat attached, and the reach comparison honest."""

    @staticmethod
    def _f(rule, sev, field):
        from authority_analyzer import Finding
        return Finding(rule, sev, f"A -> {field}", "m", "w", "x")

    def _md(self):
        return render_markdown(
            "Demo Agent", "u", "c",
            [ActionSummary("A", "apex", 58.0, True, ["X", "Y"],
                           ["X.A__c", "X.Iban__c", "X.Ok__c"],
                           [self._f("PS506", "ERROR", "X.Iban__c"),
                            self._f("PS502", "ERROR", "X.A__c"),
                            self._f("PS502", "WARN", "Y.B__c"),
                            self._f("PS504", "WARN", "?")])])

    def test_index_is_the_first_thing_in_the_report(self):
        md = self._md()
        self.assertEqual(md.splitlines()[0], "```")
        self.assertIn("AKSU INDEX", "\n".join(md.splitlines()[:4]))
        # and it precedes everything that used to outrank it
        for later in ("AGENT BLAST RADIUS REPORT", "REACH SUMMARY",
                      "ESCALATION GAP", "Config fingerprint"):
            self.assertLess(md.index("AKSU INDEX"), md.index(later), later)

    def test_all_four_numbers_are_in_the_headline_block(self):
        # Spec §1: P alone is a violation. There is no branch of the headline
        # that prints fewer than four, so assert all four AND the canonical line
        # that makes the block quotable in one piece.
        head = _headline_block(self._md())
        self.assertIn("2  PROVEN", head)
        self.assertIn("1 of them carries", head)          # C, expressed inside P
        self.assertIn("1  unproven boundaries", head)
        self.assertIn("1  unresolved", head)
        self.assertIn("Aksu Index: 2 proven (1 GDPR) · 1 unproven boundaries · 1 unresolved",
                      head)
        self.assertIn("none of them may be quoted alone", head)

    def test_classified_is_rendered_inside_proven_never_added_to_it(self):
        # C ⊆ P. The headline must never read as P + C, so the C number is only
        # ever spoken as a subset ("N of them ...") of the P line above it.
        head = _headline_block(self._md())
        self.assertLess(head.index("2  PROVEN"), head.index("1 of them carries"))
        self.assertNotIn("1  classified", head)
        self.assertNotIn("1  GDPR ", head)

    def test_reach_comparison_sits_under_the_index_and_reconciles(self):
        # The maintainer's ask: the Index, then what the agent reaches vs what
        # this user may see. outer = inner + gap (spec §3) must hold in the
        # PRINTED numbers, not just in the sets.
        head = _headline_block(self._md())
        self.assertLess(head.index("PROVEN"), head.index("WHAT THE AGENT'S CODE REACHES"))
        self.assertIn("Objects reached by the agent ............. 2", head)
        self.assertIn("Fields reached by the agent .............. 4", head)   # 3 | gap
        self.assertIn("of those, readable by this user ........ 1", head)
        self.assertIn("beyond this user - the gap ............. 3", head)
        self.assertIn("that gap = 2 proven + 1 unproven", head)

    def test_no_user_side_object_count_is_invented(self):
        # How many objects the running user can see is not computed by this run.
        # Deriving it from the field names would be wrong twice over (a
        # relationship path is not an object name), so the report says so.
        head = _headline_block(self._md())
        self.assertIn("does not measure how", head)
        self.assertIn("no user-side object count is", head)
        self.assertIn("counts fields, never records", head)

    def test_no_ratio_score_or_grade_is_introduced(self):
        # Spec §3 has no division and no threshold; a percentage in the headline
        # would read as a grade the Index does not define.
        head = _headline_block(self._md())
        self.assertNotIn("%", head)
        self.assertNotIn("/ 4", head)

    def test_headline_fits_a_fixed_width_terminal(self):
        # It is read in a console before it is read in a browser: an 80-column
        # wrap would break the frame and could push a number onto its own line.
        # The agent-name line is the one exception and deliberately so - the
        # report never truncates an identifier, and that line carries no number.
        long_name = "A Very Long Agent Name That Nobody Would Ever Type But Someone Will"
        for md in (self._md(),
                   render_markdown(long_name, "u", "c", [], counts=None)):
            for ln in _headline_block(md).splitlines():
                if "AKSU INDEX" in ln:
                    continue
                self.assertLessEqual(len(ln), 78, ln)
        self.assertIn(long_name, render_markdown(long_name, "u", "c", []))

    def test_ascii_form_for_the_console(self):
        # Windows console is cp1252 — the ASCII form must carry no middle dot.
        from report import aksu_index, aksu_index_line
        line = aksu_index_line(aksu_index([]), ascii_only=True)
        self.assertNotIn("·", line)
        self.assertIn("Aksu Index: 0 proven (0 GDPR) / 0 unproven boundaries / 0 unresolved", line)


class AksuBandHtmlTest(unittest.TestCase):
    """The HTML Index band — prominence AND the spec's non-negotiables.

    Until this class existed, NOTHING pinned the Aksu Index into the HTML
    report at all: the canonical line shipped as a 14px caption and the spec
    §4.3 'not clean' sentence was absent from the HTML path entirely, so a
    P=0/U>0 report rendered a bare zero above a green 'stays within its user'
    panel. Every assertion below is a rule from docs/AKSU_INDEX_SPEC.md, not a
    styling preference."""

    @staticmethod
    def _f(rule, sev, field):
        from authority_analyzer import Finding
        return Finding(rule, sev, f"A -> {field}", "m", "w", "x")

    def _html(self, findings, fields=("X.A__c", "X.B__c", "X.C__c")):
        from report_html import render_html
        act = ActionSummary("A", "apex", 58.0, True, ["X"], list(fields), findings)
        return render_html("A", "u", "c", [act])

    @staticmethod
    def _band(html):
        return html[html.index('<section class="aksu'):html.index("</section>")]

    def test_index_comes_before_the_prose_and_the_gap_number(self):
        # The whole point of the change: a reader opening a report named after
        # the Index must meet the Index, not a caption under a 64px gap number.
        html = self._html([self._f("PS502", "ERROR", "X.A__c")])
        i_band = html.index('<section class="aksu')
        self.assertLess(i_band, html.index('class="plain'))     # stakeholder prose
        self.assertLess(i_band, html.index('class="gapnum"'))   # the old visual hero
        self.assertLess(i_band, html.index('class="posture'))   # API-version band

    def test_all_four_numbers_live_in_one_element(self):
        # Spec §1: quoting proven alone while unresolved > 0 is a violation. The
        # enforcement is structural — there is no crop of this band, and no page
        # break through it, that yields P by itself.
        band = self._band(self._html([self._f("PS502", "ERROR", "X.A__c"),
                                      self._f("PS506", "ERROR", "X.B__c"),
                                      self._f("PS502", "WARN", "X.C__c"),
                                      self._f("PS504", "WARN", "?")]))
        self.assertIn("proven", band)
        self.assertIn("regulated", band)
        self.assertIn("unproven boundaries", band)
        self.assertIn("unresolved", band)
        self.assertIn("Aksu Index: 2 proven (1 GDPR) · 1 unproven boundaries · 1 unresolved",
                      band)

    def test_classified_is_rendered_inside_proven_not_beside_it(self):
        # C ⊆ P. It must never read as a fourth peer the eye adds to P.
        band = self._band(self._html([self._f("PS506", "ERROR", "X.A__c")]))
        self.assertIn("Counted <b>inside</b>", band)
        # and it sits within the P column, not in the B/U column pair
        p_col = band[band.index('<div class="apn">'):band.index('<div class="aside">')]
        self.assertIn("regulated", p_col)

    def test_zero_proven_with_unresolved_is_not_a_pass(self):
        # The HanseWatt shape. A big green zero here would be the exact
        # false-clean the whole project exists to prevent.
        html = self._html([self._f("PS504", "WARN", "?"),
                           self._f("PS504", "WARN", "?2")])
        band = self._band(html)
        self.assertIn('<section class="aksu unproven"', html)
        self.assertNotIn('aksu clear', html)
        self.assertIn("NOT clean", band)
        self.assertIn("unknown never becomes clean", band)
        self.assertIn("2 reach paths could not be resolved", band)
        # ...and nothing further down the page may contradict the band
        self.assertIn("No field escalation proven", html)
        self.assertNotIn("the agent stays within its user", html)
        self.assertNotIn("mostly clean", html)

    def test_a_truly_clean_report_may_read_clean(self):
        html = self._html([])
        self.assertIn('<section class="aksu clear"', html)
        self.assertNotIn("NOT clean", html)
        self.assertIn("No field escalation — the agent stays within its user.", html)

    def test_reach_comparison_sits_under_the_numbers(self):
        band = self._band(self._html([self._f("PS502", "ERROR", "X.A__c")]))
        self.assertIn("fields the agent&rsquo;s code reaches", band)
        self.assertIn("of those, this user could read anyway", band)
        self.assertIn("the gap between them", band)
        self.assertLess(band.index('class="apbig"'), band.index('class="areach"'))

    def test_no_user_side_object_count_is_invented(self):
        # The renderers never receive EffectivePermissions, so the set of
        # objects the running user can see is genuinely not computed. Say so;
        # do not derive a plausible number from field-name prefixes (a
        # relationship path puts a relationship name, not an SObject, in front
        # of the dot — CLAUDE.md §7).
        band = self._band(self._html([self._f("PS502", "ERROR", "X.A__c")]))
        self.assertIn("does not compute the set of objects the running user can see", band)

    def test_band_states_no_ratio_or_grade(self):
        # Spec has no division and no threshold; a percentage in the headline
        # band would invent one.
        band = self._band(self._html([self._f("PS502", "ERROR", "X.A__c"),
                                      self._f("PS504", "WARN", "?")]))
        self.assertNotIn("%", band)
