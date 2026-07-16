"""Tests for the real-AST Apex backend (apex-parser via ast_extract.js).

Two things are proven here:
  1. PARITY  - on the real demo class the AST backend resolves the same reach and
     escalation the verified regex path does (so switching backend is safe).
  2. SUPERIORITY - on a subquery the regex extractor grabs the inner FROM and
     misidentifies the object; the AST backend gets the parent object right and
     also captures the subquery. This is the concrete reason for the migration.

All AST tests skip cleanly when Node / apex-parser is not installed, so the suite
stays green in a Python-only environment (the tool falls back to regex there).

Run from the repo root:  python blast_radius/test_apex_ast.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_ast  # noqa: E402
from apex_introspect import parse_apex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSES = os.path.join(HERE, "..", "force-app", "main", "default", "classes")
REAL_ESCALATING = os.path.join(CLASSES, "GetHealthRecordSummary.cls")   # v58 without sharing
REAL_SAFE = os.path.join(CLASSES, "GetHealthRecordSummarySafe.cls")     # v67 with sharing + USER_MODE
SUBQUERY = os.path.join(HERE, "fixtures", "ast_cases", "classes", "SubqueryDemo.cls")

AST = apex_ast.ast_available()


@unittest.skipUnless(AST, "AST backend (node + apex-parser) not available")
class AstAvailabilityTest(unittest.TestCase):
    def test_backend_reports_ast(self):
        reach = parse_apex(SUBQUERY, backend="ast")
        self.assertEqual(reach.backend, "ast")


@unittest.skipUnless(AST and os.path.exists(REAL_ESCALATING), "AST or demo class unavailable")
class ParityTest(unittest.TestCase):
    """The AST backend reproduces the regex backend's verified result."""

    def _reads(self, reach):
        return sorted((o.sobject, tuple(o.fields),
                       o.resolved.enforces_sharing, o.resolved.enforces_fls)
                      for o in reach.operations if o.operation == "read")

    def test_escalating_class_matches_regex(self):
        ast = parse_apex(REAL_ESCALATING, backend="ast")
        rx = parse_apex(REAL_ESCALATING, backend="regex")
        self.assertEqual(self._reads(ast), self._reads(rx))
        # and the substance: v58 without-sharing plain read is escalation-capable
        op = next(o for o in ast.operations if o.operation == "read")
        self.assertEqual(op.sobject, "HealthRecord__c")
        self.assertIn("Diagnosis__c", op.fields)
        self.assertTrue(op.resolved.is_escalation_capable)

    def test_safe_class_matches_regex_and_is_clean(self):
        ast = parse_apex(REAL_SAFE, backend="ast")
        rx = parse_apex(REAL_SAFE, backend="regex")
        self.assertEqual(self._reads(ast), self._reads(rx))
        op = next(o for o in ast.operations if o.operation == "read")
        # WITH USER_MODE -> both axes enforced -> not escalation-capable
        self.assertFalse(op.resolved.is_escalation_capable)


@unittest.skipUnless(AST and os.path.exists(SUBQUERY), "AST or fixture unavailable")
class SuperiorityTest(unittest.TestCase):
    """Where the AST is strictly more correct than the regex extractor."""

    def _objects(self, backend):
        reach = parse_apex(SUBQUERY, backend=backend)
        return {o.sobject for o in reach.operations if o.operation == "read"}

    def test_regex_misidentifies_object_on_subquery(self):
        # The regex grabs the subquery's FROM (Contacts) and misses the parent.
        regex_objs = self._objects("regex")
        self.assertNotIn("Account", regex_objs)

    def test_ast_gets_parent_object_and_subquery(self):
        ast_objs = self._objects("ast")
        self.assertIn("Account", ast_objs)      # correct parent object
        self.assertIn("Contacts", ast_objs)     # subquery child reach also captured

    def test_ast_reads_parent_fields(self):
        reach = parse_apex(SUBQUERY, backend="ast")
        acct = next(o for o in reach.operations
                    if o.operation == "read" and o.sobject == "Account")
        self.assertEqual(acct.fields, ["Id", "Name"])
        self.assertTrue(acct.fields_complete)


INTERNAL_ONLY = os.path.join(HERE, "fixtures", "ast_cases", "classes", "InternalOnlyDemo.cls")
ALIAS = os.path.join(HERE, "fixtures", "ast_cases", "classes", "AliasDemo.cls")

_CLASSIFY = {"HealthRecord__c.Diagnosis__c": {"complianceGroup": "GDPR;PII"}}


def _minimal_perms():
    import json
    from permission_resolver import EffectivePermissions
    with open(os.path.join(HERE, "fixtures", "user_minimal.json"), encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))   # no FLS on Diagnosis__c


def _flow(path, field, backend="ast"):
    reach = parse_apex(path, backend=backend)
    op = next(o for o in reach.operations
              if o.operation == "read" and field in o.fields)
    return (op.field_flow or {}).get(field)


def _ps506(path, backend="ast"):
    from authority_analyzer import analyze_apex
    reach = parse_apex(path, backend=backend)
    findings = analyze_apex(reach, _minimal_perms(), _CLASSIFY, {})
    return next((f for f in findings if f.rule == "PS506"), None)


@unittest.skipUnless(AST, "AST backend not available")
class AuthorityPathTest(unittest.TestCase):
    """Source->sink taint: is the field PROVEN to reach the model, or only assumed?"""

    def test_returned_field_is_confirmed(self):
        # recs[0].Diagnosis__c flows into r.summary (an @InvocableVariable) -> proven.
        self.assertEqual(_flow(REAL_ESCALATING, "Diagnosis__c"), "returned")
        f = _ps506(REAL_ESCALATING)
        self.assertEqual(f.severity, "ERROR")
        self.assertIn("CONFIRMED", f.why)

    def test_internal_only_field_is_not_a_model_leak(self):
        # Diagnosis__c is read but used ONLY in an if-predicate; Patient_Name__c
        # is the one that reaches the output. Precision win: PS506 downgrades.
        self.assertEqual(_flow(INTERNAL_ONLY, "Diagnosis__c"), "internal")
        self.assertEqual(_flow(INTERNAL_ONLY, "Patient_Name__c"), "returned")
        f = _ps506(INTERNAL_ONLY)
        self.assertEqual(f.severity, "WARN")            # downgraded, not silenced
        self.assertIn("not observed reaching the model", f.message)

    def test_aliased_field_stays_worst_case(self):
        # `String d = recs[0].Diagnosis__c; r.summary = d;` - the flow is real but
        # not traced. SOUNDNESS: it must NOT be downgraded to internal.
        self.assertEqual(_flow(ALIAS, "Diagnosis__c"), "undetermined")
        f = _ps506(ALIAS)
        self.assertEqual(f.severity, "ERROR")
        self.assertIn("NOT TRACED", f.why)

    def test_regex_backend_has_no_flow_and_stays_worst_case(self):
        # The fallback backend cannot trace flow -> worst case, never a downgrade.
        self.assertIsNone(_flow(INTERNAL_ONLY, "Diagnosis__c", backend="regex"))
        self.assertEqual(_ps506(INTERNAL_ONLY, backend="regex").severity, "ERROR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
