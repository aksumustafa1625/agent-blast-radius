"""Tests for org_loaders pure logic: honest user-visible record derivation.

Only the non-org part is tested here (the `sf` COUNT() query needs a live org).
The rule under test: a user-visible record count is produced ONLY when it is
defensible from posture; otherwise it is None (never fabricated).

Run from the repo root:  python blast_radius/test_org_loaders.py
"""

import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from org_loaders import (OrgQueryError, _rel_root, _derive_user_visible,  # noqa: E402
                         _sf, _trigger_handler_refs)
from permission_resolver import ObjectAccess  # noqa: E402


class _Res:
    """Stand-in for subprocess.run's CompletedProcess."""

    def __init__(self, stdout, stderr=""):
        self.stdout, self.stderr = stdout, stderr


class TestOrgQueryErrorAlwaysNamesACause(unittest.TestCase):
    """A failed org read must say WHY, or it cannot be acted on.

    Observed live: sf returned status != 0 carrying `"message": ""`, and the
    CLI printed a [FAIL] that named no cause at all. `.get(key, default)` only
    defaults when the KEY is absent, so an empty string sailed through. These
    pin the fallback and, just as importantly, pin that a REAL message is
    still passed through verbatim - it is the only place the failure names the
    endpoint that did not answer.
    """

    def _raise_from(self, payload, stderr=""):
        with patch("subprocess.run", return_value=_Res(json.dumps(payload), stderr)):
            with self.assertRaises(OrgQueryError) as cm:
                _sf("SELECT Id FROM Account")
        return str(cm.exception)

    def test_empty_message_still_names_a_cause(self):
        msg = self._raise_from({"status": 1, "message": "", "name": "GatewayTimeout"},
                               stderr="upstream timed out")
        self.assertIn("GatewayTimeout", msg)
        self.assertIn("upstream timed out", msg)
        self.assertIn("SELECT Id FROM Account", msg)

    def test_absent_message_still_names_a_cause(self):
        msg = self._raise_from({"status": 1})
        self.assertIn("status 1", msg)
        self.assertIn("(empty)", msg)

    def test_a_real_message_is_preserved_verbatim(self):
        """The negative control: the fallback must not paraphrase sf's own
        message, which carries the endpoint and the network reason."""
        real = ("request to https://x.my.salesforce.com/services/data/v67.0/query "
                "failed, reason: connect ECONNREFUSED")
        self.assertEqual(self._raise_from({"status": 1, "message": real}), real)

    def test_non_json_output_is_an_org_query_error_not_a_crash(self):
        with patch("subprocess.run", return_value=_Res("<html>proxy error</html>", "")):
            with self.assertRaises(OrgQueryError):
                _sf("SELECT Id FROM Account")


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


class RelationshipRootTest(unittest.TestCase):
    """Which relationship a reached field path traverses - both spellings.

    `report._qualify` leaves a relationship field alone (`BillToContact.Email`) and
    prefixes only direct fields, which is what cli._reached_fields passes. A caller
    that prefixed anyway (`Invoice.BillToContact.Email`) used to disable relationship
    resolution ENTIRELY and silently: the old code read `split('.')[0]`, got the root
    object, found it among the reached objects, and dropped the path - so the target
    object's GDPR labels were never loaded and PS506 stayed quiet. A false clean
    caused by nothing but how a caller spells a field.
    """

    OBJECTS = {"Invoice", "Account"}

    def test_unqualified_relationship_path(self):
        self.assertEqual(_rel_root("BillToContact.Email", self.OBJECTS), "BillToContact")

    def test_qualified_relationship_path_resolves_the_same(self):
        self.assertEqual(_rel_root("Invoice.BillToContact.Email", self.OBJECTS),
                         "BillToContact")

    def test_a_direct_field_traverses_nothing(self):
        self.assertIsNone(_rel_root("Invoice.Status", self.OBJECTS))
        self.assertIsNone(_rel_root("Status", self.OBJECTS))

    def test_a_relationship_on_another_reached_object(self):
        self.assertEqual(_rel_root("Account.Owner.Name", self.OBJECTS), "Owner")
