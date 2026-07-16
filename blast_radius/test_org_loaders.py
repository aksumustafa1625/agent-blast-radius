"""Tests for org_loaders pure logic: honest user-visible record derivation.

Only the non-org part is tested here (the `sf` COUNT() query needs a live org).
The rule under test: a user-visible record count is produced ONLY when it is
defensible from posture; otherwise it is None (never fabricated).

Run from the repo root:  python blast_radius/test_org_loaders.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from org_loaders import _derive_user_visible, _trigger_handler_refs  # noqa: E402
from permission_resolver import ObjectAccess  # noqa: E402


class TriggerHandlerRefsTest(unittest.TestCase):
    """PS509 handler follow: extract the classes a trigger delegates to."""

    def test_extracts_new_and_static_refs(self):
        body = ("trigger T on Invoice (after insert) { "
                "InvoiceHandler.handle(Trigger.new); "
                "new BillingService().post(); }")
        refs = _trigger_handler_refs(body)
        self.assertIn("InvoiceHandler", refs)
        self.assertIn("BillingService", refs)

    def test_empty_body_is_safe(self):
        self.assertEqual(_trigger_handler_refs(None), set())
        self.assertEqual(_trigger_handler_refs(""), set())


class DeriveUserVisibleTest(unittest.TestCase):
    def test_no_read_sees_zero(self):
        v, note, cause = _derive_user_visible(512, "Private", ObjectAccess(read=False))
        self.assertEqual(v, 0)
        self.assertIn("no object read", note)
        self.assertEqual(cause, "crud")   # missing object perm, not sharing

    def test_view_all_records_sees_all(self):
        oa = ObjectAccess(read=True, view_all_records=True)
        v, note, cause = _derive_user_visible(512, "Private", oa)
        self.assertEqual(v, 512)
        self.assertIn("view/modify all", note)
        self.assertIsNone(cause)          # no gap

    def test_public_owd_with_read_sees_all(self):
        v, note, cause = _derive_user_visible(300, "Read", ObjectAccess(read=True))
        self.assertEqual(v, 300)
        self.assertIn("Read", note)
        self.assertIsNone(cause)

    def test_private_with_read_is_unmeasurable(self):
        # The whole honesty point: read + Private OWD + no view-all -> unknown.
        v, note, cause = _derive_user_visible(512, "Private", ObjectAccess(read=True))
        self.assertIsNone(v)
        self.assertIn("run as the user", note)
        self.assertEqual(cause, "sharing")   # has object read; gap is record-level

    def test_controlled_by_parent_is_unmeasurable(self):
        v, _, cause = _derive_user_visible(512, "ControlledByParent", ObjectAccess(read=True))
        self.assertIsNone(v)
        self.assertEqual(cause, "sharing")

    def test_unknown_sharing_is_unmeasurable(self):
        v, note, cause = _derive_user_visible(512, None, ObjectAccess(read=True))
        self.assertIsNone(v)
        self.assertIn("unknown", note)
        self.assertEqual(cause, "sharing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
