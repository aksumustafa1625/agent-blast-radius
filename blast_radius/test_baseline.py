# -*- coding: utf-8 -*-
"""The baseline gate: does it actually fail when it should?

A gate that never goes red is decoration. Every test here is paired - the same
mechanism is shown passing on one input and failing on another - because a green
assertion alone cannot tell "the gate works" from "the gate is asleep".

The case that matters most is `test_moving_findings_into_unresolved_still_fails`.
A ratchet on the proven count alone is gameable in the direction that matters:
make a query dynamic, the finding moves from proven to unresolved, the headline
FALLS, and the org is now less understood than before. That has to fail, and it
is the reason every bucket is ratcheted and coverage may not drop.
"""
import io
import json
import os
import tempfile
import unittest

import baseline as B


AGENT = "HW Energy Agent"
USER = "(hypothetical grant model - permission set: HW_ServiceAgent)"
ANALYZER = "d3a0cb4d683c"


def ix(proven=6, gdpr=1, boundary=0, unresolved=1):
    """aksu_index() returns sets for three buckets; only their size is stored."""
    return {"proven": set(range(proven)), "gdpr": set(range(gdpr)),
            "boundary": set(range(boundary)), "unresolved": unresolved}


def rc(resolved=1, total=2):
    return {"resolved": resolved, "total": total,
            "unresolved_actions": total - resolved,
            "pct": round(100.0 * resolved / total) if total else 100}


def base(agent=AGENT, running_user=USER, analyzer=ANALYZER):
    """A baseline payload in the shape write() produces, without touching disk."""
    return {
        "schema": B.SCHEMA, "agent": agent, "running_user": running_user,
        "analyzer": analyzer, "fingerprint": "ffff",
        "index": B.counts(ix()),
        "coverage": {"resolved": rc()["resolved"], "total": rc()["total"],
                     "pct": rc()["pct"]},
    }


def cmp_(b, i, r, agent=AGENT, user=USER, analyzer=ANALYZER):
    return B.compare(b, i, r, agent=agent, running_user=user, analyzer=analyzer)


class TheGateHolds(unittest.TestCase):

    def test_unchanged_passes(self):
        self.assertTrue(cmp_(base(), ix(), rc()).ok)

    def test_every_bucket_is_ratcheted(self):
        """Not just proven - each of the four fails on its own."""
        for kw in ({"proven": 7}, {"gdpr": 2}, {"boundary": 1}, {"unresolved": 2}):
            with self.subTest(**kw):
                v = cmp_(base(), ix(**kw), rc())
                self.assertFalse(v.ok, f"{kw} should have failed the gate")
                self.assertTrue(v.blocking)

    def test_improvement_passes_and_is_reported(self):
        v = cmp_(base(), ix(proven=4), rc())
        self.assertTrue(v.ok)
        self.assertTrue(any(b == "proven" for b, _o, _n in v.improved))

    def test_moving_findings_into_unresolved_still_fails(self):
        """THE gaming case: proven drops, unresolved rises, coverage falls.

        The headline number improves 6 -> 4 and a naive ratchet would go green
        while the agent became LESS understood. Both the unresolved rise and the
        coverage drop have to block it."""
        v = cmp_(base(), ix(proven=4, unresolved=3), rc(resolved=0, total=2))
        self.assertFalse(v.ok)
        blocked = {b for b, _o, _n in v.blocking}
        self.assertIn("unresolved", blocked)
        self.assertIn("coverage", blocked)

    def test_coverage_alone_can_fail_the_gate(self):
        """Buckets identical, but less of the agent could be resolved."""
        v = cmp_(base(), ix(), rc(resolved=0, total=2))
        self.assertFalse(v.ok)
        self.assertIn("coverage", {b for b, _o, _n in v.blocking})

    def test_coverage_rising_is_an_improvement_not_a_failure(self):
        v = cmp_(base(), ix(), rc(resolved=2, total=2))
        self.assertTrue(v.ok)
        self.assertIn("coverage", {b for b, _o, _n in v.improved})


class TheGateRefusesMeaninglessComparisons(unittest.TestCase):

    def test_different_agent_is_a_mismatch_not_a_regression(self):
        """Spec section 2: one Index describes one (agent, running user) pair.
        Reporting 'worse' across two different pairs would be a fabricated
        comparison, which is the one thing this tool may not produce."""
        v = cmp_(base(), ix(), rc(), agent="Some Other Agent")
        self.assertFalse(v.ok)
        self.assertIsNotNone(v.mismatch)
        self.assertFalse(v.blocking, "a mismatch is not a list of regressions")

    def test_different_running_user_is_a_mismatch(self):
        v = cmp_(base(), ix(), rc(), user="someone.else@example.com")
        self.assertFalse(v.ok)
        self.assertIsNotNone(v.mismatch)

    def test_analyzer_change_is_flagged_but_does_not_block_on_its_own(self):
        """Spec section 4.6 - comparable only under the same tool version. The
        run is still shown (a team mid-upgrade wants to see movement) but the
        verdict says a rise may be the analyzer resolving MORE."""
        v = cmp_(base(), ix(), rc(), analyzer="different-digest")
        self.assertTrue(v.stale_analyzer)
        self.assertTrue(v.ok, "a version change alone is not a regression")

    def test_analyzer_change_does_not_hide_a_real_regression(self):
        v = cmp_(base(), ix(proven=9), rc(), analyzer="different-digest")
        self.assertTrue(v.stale_analyzer)
        self.assertFalse(v.ok)


class RoundTrip(unittest.TestCase):

    def test_written_baseline_reads_back_and_passes_against_itself(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.json")
            B.write(p, ix(), rc(), agent=AGENT, running_user=USER,
                    analyzer=ANALYZER, fingerprint="ffff")
            loaded = B.load(p)
            self.assertEqual(loaded["schema"], B.SCHEMA)
            self.assertTrue(cmp_(loaded, ix(), rc()).ok)

    def test_missing_baseline_returns_none_rather_than_raising(self):
        self.assertIsNone(B.load(os.path.join(tempfile.gettempdir(), "no-such.json")))

    def test_written_file_is_stable_json(self):
        """CI diffs this file. Key order must not wander between runs."""
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.json"), os.path.join(d, "b.json")
            for p in (a, b):
                B.write(p, ix(), rc(), agent=AGENT, running_user=USER,
                        analyzer=ANALYZER, fingerprint="ffff")
            self.assertEqual(io.open(a, encoding="utf-8").read(),
                             io.open(b, encoding="utf-8").read())


class TheOutputSaysWhichWay(unittest.TestCase):

    def test_coverage_is_described_as_falling_not_rising(self):
        v = cmp_(base(), ix(), rc(resolved=0, total=2))
        out = B.render(v, base(), ix(), rc(resolved=0, total=2))
        self.assertIn("resolution coverage % fell", out)
        self.assertNotIn("resolution coverage % rose", out)

    def test_a_bucket_is_described_as_rising(self):
        v = cmp_(base(), ix(proven=7), rc())
        out = B.render(v, base(), ix(proven=7), rc())
        self.assertIn("proven rose", out)

    def test_render_is_ascii_for_the_windows_console(self):
        v = cmp_(base(), ix(proven=7), rc())
        out = B.render(v, base(), ix(proven=7), rc())
        out.encode("ascii")  # raises if not


if __name__ == "__main__":
    unittest.main()
