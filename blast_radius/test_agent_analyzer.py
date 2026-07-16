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


class AgentGraphTest(unittest.TestCase):
    """Multi-agent chaining. An agent that invokes another agent inherits that
    agent's whole data surface; reporting the delegation as one opaque box is the
    largest possible under-report in a multi-agent org. The graph is flattened
    BEFORE any reach work, so everything downstream sees the true aggregate."""

    @staticmethod
    def _cfg(name, actions):
        return {"agent": name, "runningUser": "u", "channel": "agent",
                "topics": [{"actions": actions}]}

    @staticmethod
    def _act(n, t, tgt):
        return {"name": n, "invocationTargetType": t, "invocationTarget": tgt}

    def test_chain_is_flattened_transitively_with_attribution(self):
        from agent_analyzer import expand_agent_graph
        world = {"B": self._cfg("B", [self._act("b_read", "apex", "BClass"),
                                      self._act("to_c", "agent", "C")]),
                 "C": self._cfg("C", [self._act("c_read", "apex", "CClass")])}
        a = parse_agent_config(self._cfg("A", [self._act("a_read", "apex", "AClass"),
                                               self._act("to_b", "agent", "B")]))
        actions, edges = expand_agent_graph(a, "root", loader=lambda n: world.get(n))
        names = [x.name for x in actions]
        self.assertIn("a_read", names)
        self.assertIn("B :: b_read", names)      # one hop
        self.assertIn("C :: c_read", names)      # transitive - the whole graph
        self.assertTrue(all(ok for _c, _e, ok, _n in edges))

    def test_unresolved_delegation_is_an_honest_unknown_not_clean(self):
        from agent_analyzer import expand_agent_graph, analyze_agent_graph_edges
        a = parse_agent_config(self._cfg("A", [self._act("to_x", "agent", "Ghost")]))
        actions, edges = expand_agent_graph(a, "root", loader=lambda n: None)
        # the action survives so it is never silently dropped...
        self.assertEqual([x.target_type for x in actions], ["agent"])
        # ...and it is reported as a WARN, because that agent's reach is unknown
        sev = [(f.rule, f.severity) for f in analyze_agent_graph_edges(edges)]
        self.assertEqual(sev, [("PS515", "WARN")])

    def test_cycle_is_reported_not_followed(self):
        from agent_analyzer import expand_agent_graph
        world = {}
        world["A"] = self._cfg("A", [self._act("to_b", "agent", "B")])
        world["B"] = self._cfg("B", [self._act("to_a", "agent", "A")])   # cycle
        a = parse_agent_config(world["A"])
        actions, edges = expand_agent_graph(a, "root", loader=lambda n: world.get(n))
        notes = [n for _c, _e, ok, n in edges if not ok]
        self.assertTrue(any("cycle" in n for n in notes))

    def test_depth_limit_leaves_an_unresolved_edge_not_a_clean_one(self):
        from agent_analyzer import expand_agent_graph, analyze_agent_graph_edges
        world = {c: self._cfg(c, [self._act(f"to_{n}", "agent", n)])
                 for c, n in [("B", "C"), ("C", "D"), ("D", "E")]}
        world["E"] = self._cfg("E", [self._act("e_read", "apex", "EClass")])
        a = parse_agent_config(self._cfg("A", [self._act("to_b", "agent", "B")]))
        _actions, edges = expand_agent_graph(a, "root", loader=lambda n: world.get(n),
                                             max_depth=2)
        unresolved = [n for _c, _e, ok, n in edges if not ok]
        self.assertTrue(any("depth limit" in n for n in unresolved))
        # the truncated edge must WARN, never read as clean
        self.assertIn(("PS515", "WARN"),
                      [(f.rule, f.severity) for f in analyze_agent_graph_edges(edges)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
