"""Tests for PS52x: the Apex Authority Path joined to the Agent Script prompt.

The claim under test is the strong one: not "this field can reach the model" but
"this field is interpolated into the prompt, at this line". Every hop has to be
present - a missing hop must produce NO finding, or the proof is worthless.

Run from the repo root:  python blast_radius/test_prompt_flow_analyzer.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apex_introspect import ApexOperation, ApexReach, ResolvedMode  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402
from prompt_flow_analyzer import analyze_prompt_flow  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

GDPR = {"HealthRecord__c.Diagnosis__c": {"complianceGroup": "GDPR;PII;HIPAA"}}

# The shape agentscript_extract.mjs produces for the real bundle: the action's
# output is bound to a variable, and that variable is interpolated in the prompt.
SCRIPT_IR = {
    "agent_name": "A",
    "topics": [{
        "name": "access_patient_health_records",
        "actions": [{"local_name": "get_health_record", "scheme": "apex",
                     "target_name": "GetHealthRecordSummary", "line": 114}],
        "bindings": [{"local_name": "get_health_record",
                      "sets": [{"target": "@variables.record_summary",
                                "variable": "record_summary",
                                "source": "@outputs.summary",
                                "from_output": "summary", "line": 128}]}],
        "interpolations": [{"ref": "@variables.record_summary", "line": 125}],
    }],
}


def _perms(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))


def _perms_seeing_diagnosis():
    """A running user who DOES have FLS on the GDPR field (so it is not an
    escalation - but the field still enters the prompt)."""
    return EffectivePermissions({
        "runningUser": "sees-diagnosis",
        "channel": "agent",
        "systemPermissions": {},
        "objectPermissions": [{"parent": "ps", "sobjectType": "HealthRecord__c",
                               "read": True}],
        "fieldPermissions": [
            {"parent": "ps", "field": "HealthRecord__c.Diagnosis__c", "read": True},
            {"parent": "ps", "field": "HealthRecord__c.Patient_Name__c", "read": True},
        ],
    })


def _reach(flow, sinks):
    """One system-mode read of HealthRecord__c with the given Authority Path."""
    op = ApexOperation(
        operation="read", sobject="HealthRecord__c",
        fields=["Patient_Name__c", "Diagnosis__c"], fields_complete=True,
        resolved=ResolvedMode(False, False, "v58 system default"),
        field_flow=flow, field_sinks=sinks)
    return ApexReach(class_name="GetHealthRecordSummary", api_version=58.0,
                     sharing="without", operations=[op], backend="ast")


RETURNED = {"Patient_Name__c": "returned", "Diagnosis__c": "returned"}
SINKS = {"Patient_Name__c": ["summary"], "Diagnosis__c": ["summary"]}


def _rules(findings):
    return {f.rule for f in findings}


class ChainCompleteTest(unittest.TestCase):
    """All hops present: column -> output -> variable -> prompt."""

    def test_ps522_when_user_cannot_see_the_gdpr_field(self):
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, SINKS),
                                _perms("user_minimal.json"), GDPR, SCRIPT_IR)
        ps522 = next(x for x in f if x.rule == "PS522")
        self.assertEqual(ps522.severity, "ERROR")
        self.assertIn("Diagnosis__c", ps522.where)
        # the finding must carry the traced path, not a vague claim
        self.assertIn("@outputs.summary", ps522.why)
        self.assertIn("@variables.record_summary", ps522.why)
        self.assertIn("prompt (line 125)", ps522.why)

    def test_ps521_when_the_user_can_see_it(self):
        # The user HAS FLS -> not an escalation, but classified data still enters
        # the prompt: a data-minimization WARN, not an ERROR.
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, SINKS),
                                _perms_seeing_diagnosis(), GDPR, SCRIPT_IR)
        self.assertNotIn("PS522", _rules(f))
        ps521 = next(x for x in f if x.rule == "PS521")
        self.assertEqual(ps521.severity, "WARN")
        self.assertIn("Diagnosis__c", ps521.where)

    def test_ps520_for_an_unclassified_field(self):
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, SINKS),
                                _perms("user_minimal.json"), GDPR, SCRIPT_IR)
        # Patient_Name__c is not classified -> INFO, the prompt surface is listed
        info = [x for x in f if x.rule == "PS520"]
        self.assertTrue(any("Patient_Name__c" in x.where for x in info))


class ChainBrokenTest(unittest.TestCase):
    """A missing hop must produce NO finding - otherwise the 'proof' is a guess."""

    def test_internal_field_never_reaches_the_prompt(self):
        # The Apex taint PROVED Diagnosis__c never leaves the method.
        flow = {"Patient_Name__c": "returned", "Diagnosis__c": "internal"}
        sinks = {"Patient_Name__c": ["summary"]}
        f = analyze_prompt_flow("get_health_record", _reach(flow, sinks),
                                _perms("user_minimal.json"), GDPR, SCRIPT_IR)
        self.assertFalse(any("Diagnosis__c" in x.where for x in f))

    def test_output_not_bound_to_a_variable_produces_nothing(self):
        ir = json.loads(json.dumps(SCRIPT_IR))
        ir["topics"][0]["bindings"][0]["sets"] = []          # no `set @variables.x = ...`
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, SINKS),
                                _perms("user_minimal.json"), GDPR, ir)
        self.assertEqual(f, [])

    def test_variable_never_interpolated_produces_nothing(self):
        ir = json.loads(json.dumps(SCRIPT_IR))
        ir["topics"][0]["interpolations"] = []              # variable set but never in prompt
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, SINKS),
                                _perms("user_minimal.json"), GDPR, ir)
        self.assertEqual(f, [])

    def test_field_lands_in_a_different_output(self):
        # Diagnosis__c flows to an output the agent never puts in the prompt.
        sinks = {"Patient_Name__c": ["summary"], "Diagnosis__c": ["debug_note"]}
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, sinks),
                                _perms("user_minimal.json"), GDPR, SCRIPT_IR)
        self.assertFalse(any("Diagnosis__c" in x.where for x in f))

    def test_unknown_action_produces_nothing(self):
        f = analyze_prompt_flow("some_other_action", _reach(RETURNED, SINKS),
                                _perms("user_minimal.json"), GDPR, SCRIPT_IR)
        self.assertEqual(f, [])


class WholeRecordTest(unittest.TestCase):
    """`return recs;` - the whole record leaves, so every field is worst-cased."""

    def test_star_sink_reaches_any_interpolated_output(self):
        sinks = {"Patient_Name__c": ["*"], "Diagnosis__c": ["*"]}
        f = analyze_prompt_flow("get_health_record", _reach(RETURNED, sinks),
                                _perms("user_minimal.json"), GDPR, SCRIPT_IR)
        self.assertIn("PS522", _rules(f))


if __name__ == "__main__":
    unittest.main(verbosity=2)
