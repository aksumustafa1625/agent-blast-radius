"""Tests for the GenAiPromptTemplate reach reader (the data->model channel #3).

Covers the honest cases:
  - a primitive/string-input template reads NO org field (never invented reach);
  - an sObject-input template reaches that object and its merged fields;
  - EVERY version in the file is parsed, and fields only an INACTIVE version
    reaches are surfaced as a latent, re-activatable risk.

Run from the repo root:  python blast_radius/test_genai_prompt_introspect.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from genai_prompt_introspect import parse_prompt_template  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
MULTI = os.path.join(HERE, "fixtures", "prompt_templates", "CaseSummary.genAiPromptTemplate-meta.xml")
REAL_STRING = os.path.join(
    HERE, "..", "..", "Urla Shoes", "force-app", "main", "default",
    "genAiPromptTemplates", "DocumentClassification.genAiPromptTemplate-meta.xml")


class StringInputTest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(REAL_STRING), "real Urla template not present")
    def test_primitive_input_reaches_no_org_field(self):
        r = parse_prompt_template(REAL_STRING)
        self.assertEqual(r.objects, [])
        self.assertEqual(r.fields, [])
        self.assertIn("no record input", r.note)   # honest: reads nothing, says so
        self.assertTrue(r.reaches_model)            # the value still enters the model


class SObjectReachTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = parse_prompt_template(MULTI)

    def test_active_version_reach(self):
        self.assertEqual(self.r.objects, ["Case"])
        self.assertIn("Case.Subject", self.r.fields)
        self.assertIn("Case.Priority", self.r.fields)

    def test_active_does_not_include_the_removed_fields(self):
        # the sensitive fields were removed in the active version
        self.assertNotIn("Case.Reporter_SSN__c", self.r.fields)
        self.assertNotIn("Case.Internal_Notes__c", self.r.fields)


class AllVersionsTest(unittest.TestCase):
    """The question: does it find every version and flag the latent surface?"""

    @classmethod
    def setUpClass(cls):
        cls.r = parse_prompt_template(MULTI)

    def test_every_version_is_parsed(self):
        self.assertEqual(len(self.r.versions), 2)
        ids = {v.identifier for v in self.r.versions}
        self.assertEqual(ids, {"CaseSummary_1", "CaseSummary_2"})

    def test_exactly_one_active(self):
        active = [v for v in self.r.versions if v.active]
        self.assertEqual([v.identifier for v in active], ["CaseSummary_2"])

    def test_inactive_only_fields_are_flagged_as_latent(self):
        # SSN + internal notes are reachable ONLY by the inactive v1 -> latent risk
        self.assertIn("Case.Reporter_SSN__c", self.r.inactive_extra_fields)
        self.assertIn("Case.Internal_Notes__c", self.r.inactive_extra_fields)
        self.assertIn("inactive version", self.r.note)


class AnalyzePromptTest(unittest.TestCase):
    """The join: a latent inactive-version field that is GDPR-classified -> PS513 ERROR."""

    @classmethod
    def setUpClass(cls):
        import json
        from permission_resolver import EffectivePermissions
        with open(os.path.join(HERE, "fixtures", "user_minimal.json"), encoding="utf-8") as f:
            cls.perms = EffectivePermissions(json.load(f))
        cls.reach = parse_prompt_template(MULTI)

    def _rules(self, findings):
        return {f.rule for f in findings}

    def test_latent_classified_field_is_ps513_error(self):
        from authority_analyzer import analyze_prompt
        classification = {"Case.Reporter_SSN__c": {"complianceGroup": "GDPR;PII"}}
        findings = analyze_prompt(self.reach, self.perms, classification, {"Case": "Private"})
        ps513 = next(f for f in findings if f.rule == "PS513")
        self.assertEqual(ps513.severity, "ERROR")           # classified in the latent version
        self.assertIn("Reporter_SSN__c", ps513.why)

    def test_latent_unclassified_is_ps513_warn(self):
        from authority_analyzer import analyze_prompt
        findings = analyze_prompt(self.reach, self.perms, {}, {"Case": "Private"})
        ps513 = next(f for f in findings if f.rule == "PS513")
        self.assertEqual(ps513.severity, "WARN")            # latent but nothing classified

    def test_no_ps506_because_prompt_merge_is_user_mode(self):
        # A prompt template merge respects FLS -> the active field is not a field
        # escalation even though the running user lacks FLS on it.
        from authority_analyzer import analyze_prompt
        classification = {"Case.Subject": {"complianceGroup": "GDPR"}}
        findings = analyze_prompt(self.reach, self.perms, classification, {"Case": "Private"})
        self.assertNotIn("PS506", self._rules(findings))     # user-mode merge, not escalation


if __name__ == "__main__":
    unittest.main(verbosity=2)
