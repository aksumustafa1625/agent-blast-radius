"""Tests for apex_introspect: the precedence law, encoded and verified.

Run from the repo root:  python blast_radius/test_apex_introspect.py
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apex_introspect import parse_apex, parse_apex_source  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSES = os.path.join(HERE, "..", "force-app", "main", "default", "classes")
V58 = os.path.join(CLASSES, "BlastRadius_E2_ReaderV58.cls")
V67 = os.path.join(CLASSES, "BlastRadius_E2_ReaderV67.cls")
SRC_ROOT = os.path.join(HERE, "..", "force-app", "main", "default")
DEMO_PUBLISHER = os.path.join(CLASSES, "SendPaymentRemindersAction.cls")


def _write(root: str, name: str, source: str) -> str:
    """Write a class + its meta.xml under `root` and return the .cls path."""
    classes = os.path.join(root, "classes")
    os.makedirs(classes, exist_ok=True)
    path = os.path.join(classes, name + ".cls")
    with open(path, "w", encoding="utf-8") as f:
        f.write(source)
    with open(path + "-meta.xml", "w", encoding="utf-8") as f:
        f.write("""<?xml version="1.0" encoding="UTF-8"?>
<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">
    <apiVersion>58.0</apiVersion>
    <status>Active</status>
</ApexClass>
""")
    return path


def resolved(source: str, api):
    return parse_apex_source(source, api).operations[0].resolved


class RealE2ReadersTest(unittest.TestCase):
    """The centerpiece: identical `without sharing` code resolves oppositely."""

    def test_v58_resolves_to_system_mode(self):
        if not os.path.exists(V58):
            self.skipTest("E2 v58 reader not found")
        r = parse_apex(V58)
        self.assertEqual(r.sharing, "without")
        self.assertEqual(r.api_version, 58.0)
        op = [o for o in r.operations if not o.dynamic][0]
        self.assertEqual(op.sobject, "Blast_Test__c")
        self.assertFalse(op.resolved.enforces_sharing)
        self.assertFalse(op.resolved.enforces_fls)
        self.assertTrue(op.resolved.is_escalation_capable)

    def test_v67_resolves_to_user_mode(self):
        if not os.path.exists(V67):
            self.skipTest("E2 v67 reader not found")
        r = parse_apex(V67)
        self.assertEqual(r.sharing, "without")
        self.assertEqual(r.api_version, 67.0)
        op = [o for o in r.operations if not o.dynamic][0]
        self.assertTrue(op.resolved.enforces_sharing)
        self.assertTrue(op.resolved.enforces_fls)
        self.assertFalse(op.resolved.is_escalation_capable)


class PrecedenceLawTest(unittest.TestCase):
    WITHOUT_PLAIN = "public without sharing class C { void m(){ Object o = [SELECT Id FROM X__c]; } }"
    WITH_PLAIN = "public with sharing class C { void m(){ Object o = [SELECT Id FROM X__c]; } }"
    NO_DECL = "public class C { void m(){ Object o = [SELECT Id FROM X__c]; } }"
    WITHOUT_USERMODE = "public without sharing class C { void m(){ Object o = [SELECT Id FROM X__c WITH USER_MODE]; } }"
    WITH_SYSTEMMODE = "public with sharing class C { void m(){ Object o = [SELECT Id FROM X__c WITH SYSTEM_MODE]; } }"

    def test_without_plain_v58_is_system(self):
        rm = resolved(self.WITHOUT_PLAIN, 58.0)
        self.assertFalse(rm.enforces_sharing)
        self.assertFalse(rm.enforces_fls)

    def test_without_plain_v67_is_user(self):
        rm = resolved(self.WITHOUT_PLAIN, 67.0)
        self.assertTrue(rm.enforces_sharing)
        self.assertTrue(rm.enforces_fls)

    def test_user_mode_overrides_without_sharing(self):
        # E3 encoded: operation clause beats class declaration, any version.
        for api in (58.0, 67.0):
            rm = resolved(self.WITHOUT_USERMODE, api)
            self.assertTrue(rm.enforces_sharing, api)
            self.assertTrue(rm.enforces_fls, api)

    def test_system_mode_clause_disables_both(self):
        rm = resolved(self.WITH_SYSTEMMODE, 67.0)
        self.assertFalse(rm.enforces_sharing)
        self.assertFalse(rm.enforces_fls)

    def test_with_sharing_v58_enforces_record_not_fls(self):
        rm = resolved(self.WITH_PLAIN, 58.0)
        self.assertTrue(rm.enforces_sharing)   # record-level from `with sharing`
        self.assertFalse(rm.enforces_fls)      # FLS still system at v58

    def test_no_declaration_record_access_is_undetermined(self):
        # E2 round 1: a declaration-less class inherits the caller - not system.
        rm = resolved(self.NO_DECL, 58.0)
        self.assertIsNone(rm.enforces_sharing)
        self.assertIsNotNone(rm.note)


class ExtractionTest(unittest.TestCase):
    def test_fields_extracted(self):
        src = "public without sharing class C { void m(){ Object o = [SELECT Id, Name, Customer_IBAN__c FROM Blast_Test__c]; } }"
        op = parse_apex_source(src, 58.0).operations[0]
        self.assertEqual(op.sobject, "Blast_Test__c")
        self.assertEqual(op.fields, ["Id", "Name", "Customer_IBAN__c"])
        self.assertTrue(op.fields_complete)

    def test_dynamic_soql_flagged_not_guessed(self):
        src = "public without sharing class C { void m(){ Object o = Database.query('SELECT ' + x + ' FROM Y__c'); } }"
        r = parse_apex_source(src, 58.0)
        self.assertTrue(r.dynamic_soql)
        dyn = [o for o in r.operations if o.dynamic]
        self.assertEqual(len(dyn), 1)
        self.assertIsNone(dyn[0].resolved.enforces_fls)


if __name__ == "__main__":
    unittest.main(verbosity=2)



class EventPublishReachTest(unittest.TestCase):
    """EventBus.publish is a write with a cascade, not a dead end.

    Regression for a real miss: the demo action published Invoice_Payment_Requested__e
    and the analyzer saw nothing at all - the event never entered the reach, so the
    subscriber could not be queried and the publish produced no finding. It was also
    the class of bug we keep paying for: modelled in the regex path only, it stayed
    invisible under the AST backend, which builds its DML from its own IR. Hence the
    both-backends test below, against the real demo class.
    """

    SRC = """public with sharing class Pub {
        public void go() {
            List<Invoice_Payment_Requested__e> evts = new List<Invoice_Payment_Requested__e>();
            EventBus.publish(evts);
        }
    }"""

    def _publishes(self, reach):
        return [(o.sobject, o.resolved.enforces_fls)
                for o in reach.operations if o.operation == "publish"]

    def test_regex_backend_sees_the_publish(self):
        self.assertEqual(self._publishes(parse_apex_source(self.SRC, 63)),
                         [("Invoice_Payment_Requested__e", False)])

    def test_v67_publish_enforces_fls(self):
        # Publish has no mode clause to override, so it follows the apiVersion default.
        self.assertEqual(self._publishes(parse_apex_source(self.SRC, 67)),
                         [("Invoice_Payment_Requested__e", True)])

    def test_unresolvable_event_type_stays_unknown(self):
        # An untyped publish argument must not be guessed at.
        self.assertEqual(
            self._publishes(parse_apex_source(
                "public class P { void g(){ EventBus.publish(mystery); } }", 63)),
            [(None, False)])

    def test_no_publish_no_op(self):
        self.assertEqual(
            self._publishes(parse_apex_source(
                "public class P { void g(){ Account a; insert a; } }", 63)), [])

    def test_both_backends_agree_on_the_real_demo_class(self):
        ast = parse_apex(DEMO_PUBLISHER, SRC_ROOT, backend="ast")
        rgx = parse_apex(DEMO_PUBLISHER, SRC_ROOT, backend="regex")
        if ast.backend != "ast":
            self.skipTest("AST backend unavailable")
        # The whole point of parsing this once in Python: no backend skew.
        self.assertEqual(self._publishes(ast), self._publishes(rgx))
        self.assertEqual(self._publishes(ast), [("Invoice_Payment_Requested__e", False)])


class ClassFieldDmlTargetTest(unittest.TestCase):
    """A DML target declared as a CLASS FIELD must resolve, on BOTH backends.

    Found by differential, not by reasoning: comparing the two extractors over 104
    real classes from a live org showed the AST backend - the default, and the one
    assumed stronger - reporting `update:None` for `update user;` where the regex
    backend correctly said `update:User`. Its variable-type map walked locals and
    parameters but never FieldDeclarationContext, so a class member had no type and
    the DML degraded to an honest-unknown PS504 instead of a PS503 naming the object.
    5 of 104 classes hit it. The shape below is Salesforce's own MyProfilePageController.
    """

    SRC = """public with sharing class Prof {
        private User user;
        public void save() {
            update user;
        }
    }"""

    def _dml(self, reach):
        return [(o.operation, o.sobject) for o in reach.operations if o.operation == "update"]

    def test_regex_backend(self):
        self.assertEqual(self._dml(parse_apex_source(self.SRC, 58.0)), [("update", "User")])

    def test_both_backends_agree(self):
        with tempfile.TemporaryDirectory() as d:
            classes = os.path.join(d, "classes")
            os.makedirs(classes)
            with open(os.path.join(classes, "Prof.cls"), "w", encoding="utf-8") as f:
                f.write(self.SRC)
            with open(os.path.join(classes, "Prof.cls-meta.xml"), "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
                        '<apiVersion>58.0</apiVersion><status>Active</status></ApexClass>\n')
            path = os.path.join(classes, "Prof.cls")
            ast = parse_apex(path, d, backend="ast")
            if ast.backend != "ast":
                self.skipTest("AST backend unavailable")
            self.assertEqual(self._dml(ast), [("update", "User")])
            self.assertEqual(self._dml(ast), self._dml(parse_apex(path, d, backend="regex")))

    SHADOWED = """public class Prof {
        private User user;
        public void save() {
            Account user = new Account();
            update user;
        }
    }"""

    def test_ast_resolves_shadowing_but_regex_cannot(self):
        """Where the backends genuinely differ - and why AST is the default.

        Apex resolves local > parameter > field, so `update user;` here is an Account.
        The AST path gets it right because it collects locals before fields into a
        first-wins map. The REGEX path cannot: it has no notion of scope at all, only
        document order, and the field is written first. This is not a regression to
        fix - it is the limit of matching text without a parse tree, and it is exactly
        the asymmetry the report's backend note exists to disclose. Asserting the real
        behaviour keeps that honest; asserting the behaviour we wish it had would hide
        a false positive (PS503 against the wrong object) behind a green test.
        """
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "Prof", self.SHADOWED)
            ast = parse_apex(path, d, backend="ast")
            if ast.backend != "ast":
                self.skipTest("AST backend unavailable")
            self.assertEqual(self._dml(ast), [("update", "Account")])
            # Measured, not desired: the regex fallback names the field's type.
            self.assertEqual(self._dml(parse_apex(path, d, backend="regex")),
                             [("update", "User")])
