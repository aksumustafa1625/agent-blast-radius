"""Tests for agent_analyzer: whole-agent orchestration against real artifacts.

Run from the repo root:  python blast_radius/test_agent_analyzer.py
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_analyzer import analyze_agent, parse_agent_config  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = os.path.join(HERE, "..", "force-app", "main", "default")
CLASSIFICATION = {"Blast_Test__c.Customer_IBAN__c":
                  {"complianceGroup": "PII;GDPR", "securityClassification": "Confidential"}}
OBJECT_SHARING = {"Blast_Test__c": "Private"}


def load(name):
    with open(os.path.join(HERE, "fixtures", name), encoding="utf-8") as f:
        return json.load(f)


class AgentOrchestrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = parse_agent_config(load("agent_hw_energy.json"))
        perms = EffectivePermissions(load("user_minimal.json"))
        cls.summaries = analyze_agent(cls.agent, SOURCE_ROOT, perms,
                                      CLASSIFICATION, OBJECT_SHARING)
        cls.by_name = {s.name: s for s in cls.summaries}

    def test_config_parsed(self):
        self.assertEqual(self.agent.name, "HW_Energy_Agent")
        self.assertEqual(len(self.agent.actions), 3)

    def test_three_actions_summarized(self):
        self.assertEqual(len(self.summaries), 3)

    def test_flow_action_escalates(self):
        rules = {f.rule for f in self.by_name["HWGetLatestBill"].findings}
        self.assertIn("PS506", rules)
        self.assertIn("PS510", rules)

    def test_legacy_apex_action_escalates(self):
        rules = {f.rule for f in self.by_name["HWExplainConsumption"].findings}
        self.assertIn("PS501", rules)
        self.assertIn("PS511", rules)

    def test_v67_action_is_clean(self):
        # Version-awareness at the agent level: the v67 action must not escalate.
        rules = {f.rule for f in self.by_name["HWSafeLookup"].findings}
        self.assertNotIn("PS506", rules)
        self.assertNotIn("PS502", rules)
        self.assertNotIn("PS501", rules)
        self.assertNotIn("PS511", rules)


class StandardActionCatalogTest(unittest.TestCase):
    """A catalogued standard action gets its documented channel, not a blanket opaque."""

    def _summary(self, target):
        cfg = {"agent": "A", "runningUser": "u", "channel": "agent",
               "topics": [{"name": "t", "actions": [
                   {"name": "act", "invocationTargetType": "standard", "invocationTarget": target}]}]}
        agent = parse_agent_config(cfg)
        perms = EffectivePermissions(load("user_minimal.json"))
        return analyze_agent(agent, SOURCE_ROOT, perms, {}, {})[0]

    def test_known_knowledge_action_names_its_channel(self):
        s = self._summary("EmployeeCopilot__AnswerQuestionsWithKnowledge")
        f = next(f for f in s.findings if f.rule == "PS507")
        self.assertIn("Knowledge", f.message)               # documented behaviour, not "opaque"
        self.assertIn("data-to-model channel", f.fix)

    def test_unknown_standard_action_stays_generic_opaque(self):
        s = self._summary("Some__RandomManagedAction")
        f = next(f for f in s.findings if f.rule == "PS507")
        self.assertIn("standard/opaque action", f.message)  # honest: still unknown


if __name__ == "__main__":
    unittest.main(verbosity=2)
