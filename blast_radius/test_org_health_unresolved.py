# -*- coding: utf-8 -*-
"""The org-health footer must never contradict the Aksu Index band above it.

Found by an adversarial verification pass on 2026-08-20: the band correctly said
"0 proven ... 2 unresolved - NOT clean" for HW Energy Agent while the footer of the
same document said the agent "currently stays within its user (gap 0)". Both
sentences were about the same run. Spec section 4.3 settles it - a zero next to
unresolved reach is "0 proven, N unresolved", never a pass - so the footer was the
one that had to change.

The earlier assertion that claimed to catch this could not: it matched
"the agent stays within its user" while the shipped string is "...Agent *currently*
stays within its user", and it ran against a fixture in which the footer never
rendered at all. These tests assert on the real renderers instead.
"""
import unittest

import org_health
from org_health import OrgHealth, render_health_section, render_health_md


def _health():
    """Minimal OrgHealth with enough set that has_any is True and it renders."""
    return OrgHealth(god_mad=1, god_vad=0, owd_permissive=2, owd_models={"Read": 2})


class FooterMustNotContradictTheBand(unittest.TestCase):

    def test_html_zero_gap_with_unresolved_is_not_a_pass(self):
        html = render_health_section(_health(), "HW Energy Agent", gap_n=0,
                                     agent_legacy=0, agent_apex_total=9, unresolved=2)
        self.assertIn("0 proven", html)
        self.assertIn("2 operations", html)
        self.assertIn("not</b> a clean result", html)
        self.assertIn("an unknown never becomes clean", html)
        # The exact sentence this test exists to keep out, matched loosely enough
        # that a re-worded variant ("currently stays within") cannot slip past.
        self.assertNotIn("stays within its user", html)
        self.assertIn('orgframe warn', html)

    def test_md_zero_gap_with_unresolved_is_not_a_pass(self):
        md = render_health_md(_health(), "HW Energy Agent", gap_n=0,
                              agent_legacy=0, agent_apex_total=9, unresolved=2)
        self.assertIn("**0 proven**", md)
        self.assertIn("2 operations", md)
        self.assertIn("not** clean", md)
        self.assertNotIn("stays within its user", md)

    def test_singular_when_one_unresolved(self):
        for render in (render_health_section, render_health_md):
            out = render(_health(), "A", gap_n=0, agent_legacy=0,
                         agent_apex_total=2, unresolved=1)
            self.assertIn("1 operation ", out, render.__name__)
            self.assertNotIn("1 operations", out, render.__name__)

    def test_a_true_zero_still_reads_as_bounded(self):
        """U == 0 is the one case where "stays within its user" is honest."""
        html = render_health_section(_health(), "A", gap_n=0, agent_legacy=0,
                                     agent_apex_total=9, unresolved=0)
        self.assertIn("stays within its user", html)
        self.assertIn('orgframe ok', html)
        self.assertNotIn("not</b> a clean result", html)

    def test_a_real_gap_still_wins_over_the_unresolved_wording(self):
        """A proven escalation is the headline even when reach is also unresolved."""
        html = render_health_section(_health(), "A", gap_n=6, agent_legacy=2,
                                     agent_apex_total=2, unresolved=1)
        self.assertIn("6-field escalation", html)
        self.assertIn('orgframe err', html)
        self.assertNotIn("0 proven", html)

    def test_unresolved_defaults_to_zero_so_callers_need_not_pass_it(self):
        """Back-compat: the parameter was added after the renderers shipped."""
        html = render_health_section(_health(), "A", gap_n=0, agent_legacy=0,
                                     agent_apex_total=1)
        self.assertIn("stays within its user", html)

    def test_the_warn_class_is_actually_styled(self):
        """A class with no CSS rule renders unstyled and reads as a pass."""
        self.assertIn(".abr .orgframe.warn{", org_health._HEALTH_CSS)


if __name__ == "__main__":
    unittest.main()
