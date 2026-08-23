# -*- coding: utf-8 -*-
"""PS504 says WHY it could not resolve the reach, and WHOSE job it is.

One honest-unknown covered two very different situations. "Make the query
static" is useless advice for an aggregate select the customer wrote perfectly
well, and "wait for a newer analyzer" is useless advice for a query that is
assembled at runtime. Half of every unresolved list was going to the wrong desk.

Two things are load-bearing here and both are tested as pairs, because a green
assertion on its own cannot tell "the split works" from "the split labels
everything the same way":

  * the OWNER must be the right one - swapping the two fix texts has to go red;
  * the COUNT must not move. The Index's U bucket is defined as the PS504 count
    and the specification is frozen at v1.0, so this change is allowed to make
    the report more useful and is not allowed to make the number different.
"""
import unittest

from authority_analyzer import AccessUnit, _analyze_units, _analyzer_build
from permission_resolver import EffectivePermissions
from report import analyzer_version

PERMS = EffectivePermissions({"runningUser": "svc@example.com", "channel": "agent"})

# The mode-resolution source. It is NOT a reason for the reach being unresolved,
# and PS504 used to print it as if it were - see test_message_names_the_real_reason.
MODE_SOURCE = "API v<=66 system-mode default"


def unit(kind, note, sobject="Invoice"):
    return AccessUnit("read", sobject, [], False, False, False,
                      MODE_SOURCE, None, kind, note)


def ps504(u):
    out = [f for f in _analyze_units("SomeAction", [u], PERMS, {}, {})
           if f.rule == "PS504"]
    assert len(out) == 1, f"expected exactly one PS504, got {len(out)}"
    return out[0]


DYNAMIC = unit("code", "dynamic SOQL - reach cannot be determined statically")
AGGREGATE = unit("analyzer", "aggregate/function select - fields not enumerated")
UNLABELLED = unit(None, None)


class TheOwnerIsNamed(unittest.TestCase):

    def test_a_runtime_query_is_the_customers_to_close(self):
        f = ps504(DYNAMIC)
        self.assertIn("Yours to close", f.fix)
        self.assertIn("assembled at runtime", f.message)

    def test_a_shape_we_do_not_model_is_ours_to_close(self):
        f = ps504(AGGREGATE)
        self.assertIn("Ours to close", f.fix)
        self.assertIn("analyzer does not model", f.message)

    def test_the_two_owners_are_never_both_claimed(self):
        """The paired half. If the fix texts are ever swapped or merged, one of
        these goes red - which a one-sided 'contains the right string' test
        would happily sleep through."""
        self.assertNotIn("Ours to close", ps504(DYNAMIC).fix)
        self.assertNotIn("Yours to close", ps504(AGGREGATE).fix)

    def test_customer_advice_is_absent_from_our_own_limit(self):
        """Telling someone to rewrite an aggregate select is advice that cannot
        work: the query is already static and already correct."""
        f = ps504(AGGREGATE)
        self.assertIn("nothing to change in your code", f.fix)
        self.assertNotIn("WITH USER_MODE", f.fix)

    def test_an_unclassified_cause_claims_no_owner_at_all(self):
        """A wrong owner is worse than none: it sends real work to a desk that
        cannot do it, and it does so in the tool's own confident voice."""
        f = ps504(UNLABELLED)
        self.assertNotIn("Yours to close", f.fix)
        self.assertNotIn("Ours to close", f.fix)
        self.assertIn("not classified", f.message)


class TheAnalyzerLimitIsVersionBound(unittest.TestCase):
    """'This shape is not modelled' is true of a build, not of the world. Left
    unbound, every report ever issued is falsified the day the shape IS modelled
    - so the claim carries the build that made it."""

    def test_the_our_limit_text_names_the_analyzer_build(self):
        self.assertIn(analyzer_version()[:12], ps504(AGGREGATE).why)

    def test_the_build_is_derived_not_hand_maintained(self):
        """A constant someone must remember to bump is the mechanism that lies.
        This one is a digest of the analyzer's own source, so editing a rule
        cannot leave the stated build behind."""
        self.assertEqual(_analyzer_build(), analyzer_version()[:12])

    def test_the_customer_side_text_makes_no_version_claim(self):
        """'No static analysis can do this' is not a statement about our build,
        and dating it would imply a later build might resolve it. It will not."""
        self.assertNotIn(analyzer_version()[:12], ps504(DYNAMIC).why)


class TheNumberDoesNotMove(unittest.TestCase):
    """Spec 3.1 defines U as the PS504 count and the spec is frozen at v1.0.
    This change is allowed to say more about each finding; it is not allowed to
    produce a different number for the same org."""

    def test_every_cause_still_reports_under_the_frozen_rule_id(self):
        for u in (DYNAMIC, AGGREGATE, UNLABELLED):
            with self.subTest(kind=u.unresolved_kind):
                self.assertEqual(ps504(u).rule, "PS504")

    def test_one_finding_per_action_and_object_however_many_causes(self):
        """dedupe_findings keys on (rule, where) and always did. Two unresolved
        reads of the same object were one finding before this change and must
        stay one after it, or the same org gets a different U."""
        found = [f for f in _analyze_units("A", [DYNAMIC, AGGREGATE, UNLABELLED],
                                           PERMS, {}, {}) if f.rule == "PS504"]
        self.assertEqual(len(found), 1)

    def test_distinct_objects_still_count_separately(self):
        found = [f for f in _analyze_units(
            "A", [DYNAMIC, unit("analyzer", "aggregate", sobject="Account")],
            PERMS, {}, {}) if f.rule == "PS504"]
        self.assertEqual(len(found), 2)

    def test_severity_is_unchanged(self):
        for u in (DYNAMIC, AGGREGATE, UNLABELLED):
            with self.subTest(kind=u.unresolved_kind):
                self.assertEqual(ps504(u).severity, "WARN")


class TwoCausesOnOneObjectKeepBothOwners(unittest.TestCase):
    """The trap this split walked into. dedupe_findings keys on (rule, where) and
    keeps whichever finding arrived FIRST. That was harmless while every PS504
    said the same generic sentence - collapsing two identical statements loses
    nothing. The moment a PS504 names an owner it stops being harmless: the
    second cause vanishes and its work is attributed, confidently, to the other
    party. So the causes merge into the one finding instead of racing for it."""

    def _merged(self, first, second):
        found = [f for f in _analyze_units("A", [first, second], PERMS, {}, {})
                 if f.rule == "PS504"]
        self.assertEqual(len(found), 1, "merging must not add a finding")
        return found[0]

    def test_both_owners_survive_the_merge(self):
        f = self._merged(DYNAMIC, AGGREGATE)
        self.assertIn("Yours to close", f.fix)
        self.assertIn("Ours to close", f.fix)

    def test_both_reasons_survive_the_merge(self):
        f = self._merged(DYNAMIC, AGGREGATE)
        self.assertIn("assembled at runtime", f.message)
        self.assertIn("does not model the shape", f.message)

    def test_the_merge_does_not_depend_on_arrival_order(self):
        """The bug being prevented is order-sensitive by construction, so the
        test has to be run both ways round or it can pass on the lucky order."""
        a, b = self._merged(DYNAMIC, AGGREGATE), self._merged(AGGREGATE, DYNAMIC)
        for f in (a, b):
            self.assertIn("Yours to close", f.fix)
            self.assertIn("Ours to close", f.fix)

    def test_the_same_cause_twice_is_not_duplicated(self):
        """Two dynamic queries on one object are one fact, not two. Repeating
        the owner sentence would read as two separate jobs."""
        f = self._merged(DYNAMIC, unit("code", "another dynamic query"))
        self.assertEqual(f.fix.count("Yours to close"), 1)


class TheReasonIsTheRealOne(unittest.TestCase):

    def test_message_names_the_real_reason(self):
        """The old message printed the MODE resolution's origin - true, but an
        answer to a different question, and it read like the reason. A reader of
        the TechnoStore report was told an aggregate select could not be resolved
        'because API v<=66 system-mode default', which explains nothing."""
        f = ps504(AGGREGATE)
        self.assertIn("aggregate/function select", f.message)
        self.assertNotIn(MODE_SOURCE, f.message)

    def test_mode_source_is_still_used_when_there_is_no_better_reason(self):
        """Falling back to it is fine; presenting it as the cause was not."""
        self.assertIn(MODE_SOURCE, ps504(UNLABELLED).message)


class TheExtractorLabelsWhatItGivesUpOn(unittest.TestCase):
    """The split is only as good as the labelling upstream. An unlabelled cause
    is honest but useless, so the shapes we actually give up on are pinned."""

    def test_aggregate_select_is_labelled_as_our_limit(self):
        from apex_introspect import _parse_select_fields
        _f, complete, _note, kind = _parse_select_fields("COUNT(Id) cnt, SUM(Amount) t")
        self.assertFalse(complete)
        self.assertEqual(kind, "analyzer")

    def test_a_plain_field_list_is_not_labelled_at_all(self):
        from apex_introspect import _parse_select_fields
        fields, complete, _note, kind = _parse_select_fields("Id, Name, Amount__c")
        self.assertTrue(complete)
        self.assertIsNone(kind, "a resolved read must carry no unresolved cause")
        self.assertEqual(fields, ["Id", "Name", "Amount__c"])

    def test_bare_count_is_resolved_and_not_an_unknown(self):
        """COUNT() returns no field data, so there is nothing unresolved about
        it. Labelling it would inflate U with a row that hides nothing."""
        from apex_introspect import _parse_select_fields
        _f, complete, _note, kind = _parse_select_fields("COUNT()")
        self.assertTrue(complete)
        self.assertIsNone(kind)


class BothBackendsAgreeOnTheOwner(unittest.TestCase):
    """The failure mode CLAUDE.md names by hand: add a reach feature on one
    extractor and the other quietly lacks it. Here that would show up as the
    same class reporting 'ours to close' under one backend and no owner at all
    under the other - the AST backend is the default, so the regex path is the
    one that silently rots. Skipped rather than faked when Node is absent."""

    SOURCE = (
        "public without sharing class AggDemo {\n"
        "  @InvocableMethod\n"
        "  public static void run() {\n"
        "    AggregateResult[] r = [SELECT COUNT(Id) c, SUM(Amount) t FROM Invoice];\n"
        "  }\n"
        "}\n")

    def _kinds(self, backend):
        import os
        import tempfile
        from apex_introspect import parse_apex
        with tempfile.TemporaryDirectory() as d:
            classes = os.path.join(d, "classes")
            os.makedirs(classes)
            cls = os.path.join(classes, "AggDemo.cls")
            with open(cls, "w", encoding="utf-8") as fh:
                fh.write(self.SOURCE)
            with open(cls + "-meta.xml", "w", encoding="utf-8") as fh:
                fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                         '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">'
                         '<apiVersion>58.0</apiVersion><status>Active</status>'
                         '</ApexClass>\n')
            reach = parse_apex(cls, d, backend=backend)
            return (reach.backend,
                    [o.unresolved_kind for o in reach.operations
                     if not o.fields_complete])

    def test_regex_backend_labels_the_aggregate_as_ours(self):
        _b, kinds = self._kinds("regex")
        self.assertEqual(kinds, ["analyzer"])

    def test_ast_backend_labels_it_the_same_way(self):
        backend, kinds = self._kinds("ast")
        if backend != "ast":
            self.skipTest("Node/AST backend unavailable - nothing to compare")
        self.assertEqual(kinds, ["analyzer"])

    def test_the_two_backends_do_not_disagree(self):
        ast_backend, ast_kinds = self._kinds("ast")
        if ast_backend != "ast":
            self.skipTest("Node/AST backend unavailable - nothing to compare")
        self.assertEqual(ast_kinds, self._kinds("regex")[1])


if __name__ == "__main__":
    unittest.main()
