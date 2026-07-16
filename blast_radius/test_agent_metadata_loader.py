"""Tests for agent_metadata_loader against the real retrieved agent metadata.

Run from the repo root:  python blast_radius/test_agent_metadata_loader.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_metadata_loader import load_agent_config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = os.path.join(HERE, "..", "force-app", "main", "default")
BUNDLE = "HealthRecord_Assistant"
BUNDLE_PATH = os.path.join(SOURCE_ROOT, "genAiPlannerBundles", BUNDLE, BUNDLE + ".genAiPlannerBundle")

# Resolver as built live from the Tooling API (GenAiFunctionDefinition -> ApexClass).
RESOLVER = {
    "Get_Health_Record_Summary_179dL000004cqrJ": {"type": "apex", "target": "GetHealthRecordSummary"}
}


class RealAgentMetadataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(BUNDLE_PATH):
            raise unittest.SkipTest("real agent bundle not retrieved")
        cls.cfg = load_agent_config(SOURCE_ROOT, BUNDLE, running_user="hr-agent-runtime-user",
                                    channel="agent", resolver=RESOLVER)

    def test_agent_name_and_topics(self):
        self.assertEqual(self.cfg["agent"], "HealthRecord Assistant")
        self.assertTrue(len(self.cfg["topics"]) >= 2)

    def test_custom_function_resolves_to_apex_class(self):
        all_actions = [a for t in self.cfg["topics"] for a in t["actions"]]
        apex = [a for a in all_actions if a["invocationTargetType"] == "apex"]
        self.assertTrue(any(a["invocationTarget"] == "GetHealthRecordSummary" for a in apex))

    def test_standard_actions_marked_opaque(self):
        all_actions = [a for t in self.cfg["topics"] for a in t["actions"]]
        std = [a for a in all_actions if a["invocationTargetType"] == "standard"]
        self.assertTrue(any("EmployeeCopilot" in a["invocationTarget"] for a in std))


AS_BUNDLE = "HealthRecord_Assistant_AS_v1"
AS_BUNDLE_PATH = os.path.join(SOURCE_ROOT, "genAiPlannerBundles", AS_BUNDLE,
                              AS_BUNDLE + ".genAiPlannerBundle")


class AgentScriptCompiledBundleTest(unittest.TestCase):
    """Regression: an agent compiled from Agent Script inlines its topics and
    actions in the planner bundle (<localTopics>/<localActions>) instead of
    referencing separate GenAiPlugin files. The loader used to see zero actions
    there and report 'no findings' - a FALSE CLEAN, the one outcome this tool
    exists to prevent."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(AS_BUNDLE_PATH):
            raise unittest.SkipTest("Agent Script agent not published/retrieved")
        cls.cfg = load_agent_config(SOURCE_ROOT, AS_BUNDLE,
                                    running_user="hr-agent-runtime-user", channel="agent")

    def test_inline_topics_are_found(self):
        self.assertTrue(self.cfg["topics"], "no topics parsed from the compiled bundle")

    def test_inline_apex_action_resolves_without_any_tooling_lookup(self):
        # No resolver was passed: the target is inline in the planner bundle.
        actions = [a for t in self.cfg["topics"] for a in t["actions"]]
        apex = [a for a in actions if a["invocationTargetType"] == "apex"]
        self.assertTrue(any(a["invocationTarget"] == "GetHealthRecordSummary" for a in apex),
                        f"apex action not resolved; got {actions}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
