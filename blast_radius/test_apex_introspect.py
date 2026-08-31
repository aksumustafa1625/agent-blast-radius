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

    def test_inline_constructed_event_resolves(self):
        """`EventBus.publish(new X__e(...))` - at least as common as publishing a list.

        The pattern matched only a bare name, so `new` itself became the operand, the
        event resolved to None and PS503 never fired. Found by the corpus case written
        to settle the publish premise: the feature's own test found the hole in it.
        """
        self.assertEqual(
            self._publishes(parse_apex_source(
                "public with sharing class C { void m(){ "
                "EventBus.publish(new Blast_Event__e(Note__c='x')); } }", 58)),
            [("Blast_Event__e", False)])

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

    def test_ast_resolves_shadowing_and_regex_admits_it_cannot(self):
        """Where the backends genuinely differ - and why AST is the default.

        Apex resolves local > parameter > field, so `update user;` here is an Account.
        The AST path gets it right; the REGEX path cannot, because it has no notion of
        scope at all - that limit is the whole reason AST is the default, and no fix
        without a parse tree exists.

        What it must NOT do is name the WRONG object. This test used to assert exactly
        that (regex reported `User`, the field's type), written down as an honest
        record of a limitation. It was worse than a limitation: PS503 would accuse the
        running user over an object the code never touches. Since a name declared with
        two types is now dropped as ambiguous, the fallback says None -> PS504's honest
        unknown. The limit is unchanged; the lie is gone.
        """
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "Prof", self.SHADOWED)
            ast = parse_apex(path, d, backend="ast")
            if ast.backend != "ast":
                self.skipTest("AST backend unavailable")
            self.assertEqual(self._dml(ast), [("update", "Account")])
            regex = self._dml(parse_apex(path, d, backend="regex"))
            self.assertEqual(regex, [("update", None)], "regex must not guess a type")
            self.assertNotIn(("update", "User"), regex, "the field's type is not in scope")


class SubqueryAndBindScanTest(unittest.TestCase):
    r"""The regex path must find the TOP-LEVEL FROM, not the subquery's.

    Found by differential over 104 real classes: `_SOQL` matched
    `SELECT (.*?) FROM (\w+)` non-greedily, so a multiline query with a child
    subquery resolved to the CHILD's FROM and the outer object disappeared from the
    reach entirely. A read we never see is a read we never check - a false clean,
    which is worse than any honest unknown.
    """

    def _reads(self, src, api=58.0):
        return [(o.sobject, o.fields_complete)
                for o in parse_apex_source(src, api).operations if o.operation == "read"]

    def test_outer_object_survives_a_subquery(self):
        src = ("public without sharing class C { void m(){ Object o = ["
               "SELECT Id, Name, (SELECT Id, Email FROM Contacts) FROM Account "
               "WHERE Id = :accId]; } }")
        reads = dict(self._reads(src))
        self.assertIn("Account", reads)     # the outer object - this used to vanish
        self.assertIn("Contacts", reads)    # and the subquery is a read of its own

    def test_outer_field_list_is_complete_once_subqueries_are_lifted(self):
        src = ("public without sharing class C { void m(){ Object o = ["
               "SELECT Id, Customer_IBAN__c, (SELECT Id FROM Contacts) FROM Account]; } }")
        ops = [o for o in parse_apex_source(src, 58.0).operations
               if o.operation == "read" and o.sobject == "Account"]
        self.assertEqual(ops[0].fields, ["Id", "Customer_IBAN__c"])
        self.assertTrue(ops[0].fields_complete)

    def test_a_bind_that_indexes_a_list_does_not_close_the_query_early(self):
        # `\[...\]` stopped at the FIRST `]`, which is the one in `ids[0]`, mangling
        # the query. Depth counting keeps it whole.
        src = ("public without sharing class C { void m(){ Object o = ["
               "SELECT Customer_IBAN__c FROM Blast_Test__c WHERE Id = :ids[0]]; } }")
        self.assertEqual(self._reads(src), [("Blast_Test__c", True)])

    def test_the_mode_clause_covers_subqueries_too(self):
        # WITH USER_MODE governs the whole query, so the child read is bounded as well.
        src = ("public without sharing class C { void m(){ Object o = ["
               "SELECT Id, (SELECT Id FROM Contacts) FROM Account WITH USER_MODE]; } }")
        for o in parse_apex_source(src, 58.0).operations:
            self.assertTrue(o.resolved.enforces_fls, o.sobject)
            self.assertTrue(o.resolved.enforces_sharing, o.sobject)

    def test_an_aggregate_is_still_not_enumerated(self):
        # Non-subquery parens must survive: _parse_select_fields reads them to decide
        # it must NOT enumerate an aggregate select.
        src = "public without sharing class C { void m(){ Object o = [SELECT COUNT(Id) FROM Account]; } }"
        self.assertEqual(self._reads(src), [("Account", False)])


class TextThatIsNotCodeTest(unittest.TestCase):
    """A regex has to be told that a string is not code. Both halves cost a real bug.

    Found by differential over 104 live classes, where these were the ONLY remaining
    contradictions between the backends. Fixing them took identical ops 62 -> 82 of
    104 and drove OVERCLAIM, MISSED and NOISE all to zero: the only asymmetry left is
    regex admitting it does not know where the AST resolves, which is honest.
    """

    def _ops(self, src, api=58.0):
        return [(o.operation, o.sobject)
                for o in parse_apex_source(src, api).operations if o.operation != "read"]

    def test_dml_shaped_text_in_a_string_is_not_an_operation(self):
        # `'insert failed'` produced a phantom insert:None - an op describing no
        # statement, which then read as an honest unknown nobody could act on.
        self.assertEqual(
            self._ops("public class C { void m(){ throw new E('insert failed'); } }"), [])

    def test_publish_shaped_text_in_a_string_is_not_an_operation(self):
        self.assertEqual(self._ops(
            "public class C { void m(){ System.debug('EventBus.publish Foo__e'); } }"), [])

    def test_a_url_in_a_string_does_not_eat_the_rest_of_the_line(self):
        """THE ONE THAT MATTERS: `'https://x'` contains `//`.

        Blanking comments before strings ate the rest of that line INCLUDING the
        closing quote, leaving an odd number of quotes; every later quote then paired
        with the wrong partner, so the "strings" became the gaps BETWEEN strings and
        real code was blanked. Measured: it silently erased `update ordersToUpdate;`
        from a live class - a write made invisible by the pass meant to remove noise.
        """
        src = ("public class C { void m(){ "
               "String u = 'https://api.example.com/v1'; Account a; insert a; } }")
        self.assertEqual(self._ops(src), [("insert", "Account")])

    def test_an_escaped_quote_does_not_end_the_string(self):
        # The Apex reads:  String s = 'it\'s here: insert nonsense';
        # Taken as the terminator, the scanner would fall out of the literal mid-string
        # and read `insert nonsense` as a statement.
        src = ("public class C { void m(){ "
               r"String s = 'it\'s here: insert nonsense';"
               " Account a; insert a; } }")
        self.assertEqual(self._ops(src), [("insert", "Account")])

    def test_an_unterminated_string_blanks_the_rest_rather_than_misreading_it(self):
        # Malformed input should lose reach, never invent it - the honest direction.
        src = "public class C { void m(){ String s = 'oops; insert junk; } }"
        self.assertEqual(self._ops(src), [])

    def test_real_code_after_a_block_comment_survives(self):
        src = "public class C { void m(){ /* insert junk */ Account a; insert a; } }"
        self.assertEqual(self._ops(src), [("insert", "Account")])


class DmlOnQueryTest(unittest.TestCase):
    """`delete [SELECT Id FROM X];` - DML straight on a query, no variable between.

    The pattern expected a name or `new X(`, so this write was invisible: only the
    READ was reported and PS503/PS509 never saw the delete. A write we cannot see is
    a write we cannot check. Idiomatic in cleanup and test teardown, and found on
    real code - the AST had the same blind spot, resolving the verb but not the object.
    """

    def _ops(self, src, api=58.0):
        return [(o.operation, o.sobject, o.resolved.enforces_fls)
                for o in parse_apex_source(src, api).operations if o.operation != "read"]

    def test_delete_on_a_query_resolves_the_object(self):
        self.assertEqual(
            self._ops("public class C { void m(){ delete [SELECT Id FROM Blast_Test__c]; } }"),
            [("delete", "Blast_Test__c", False)])

    def test_the_clause_still_beats_the_version(self):
        # `as user` on DML-over-query obeys the same precedence law as anywhere else.
        self.assertEqual(
            self._ops("public class C { void m(){ update as user [SELECT Id FROM Account]; } }"),
            [("update", "Account", True)])

    def test_a_subquery_cannot_hijack_the_target(self):
        # The same depth scanner the reads use: the DML target is the OUTER object.
        self.assertEqual(
            self._ops("public class C { void m(){ delete [SELECT Id, (SELECT Id FROM Contacts) "
                      "FROM Account]; } }"),
            [("delete", "Account", False)])


class AmbiguousVariableTypeTest(unittest.TestCase):
    """A name declared with two types must resolve to None, not to one of them.

    This path has no scope, so `Order upd` in one method and `Account upd` in another
    are one entry to it. First-wins named the WRONG object on a DML - measured on
    SapInboundEventDispatcher, where an `update:Order` was reported as `update:Account`.
    That is worse than naming none: PS503 would accuse the running user over an object
    the code never touches. Unknown beats confidently wrong.
    """

    def test_same_name_two_types_yields_no_object(self):
        src = ("public class C {"
               " void a(){ Order upd = new Order(); update upd; }"
               " void b(){ Account upd = new Account(); update upd; } }")
        objs = {o.sobject for o in parse_apex_source(src, 58.0).operations
                if o.operation == "update"}
        self.assertEqual(objs, {None}, "an ambiguous name must not be guessed")

    def test_an_unambiguous_name_still_resolves(self):
        src = "public class C { void a(){ Account acc = new Account(); update acc; } }"
        self.assertEqual([o.sobject for o in parse_apex_source(src, 58.0).operations
                          if o.operation == "update"], ["Account"])


class SecurityEnforcedAxesTest(unittest.TestCase):
    """`WITH SECURITY_ENFORCED` enforces FLS/CRUD but NOT sharing - both axes pinned.

    An external reviewer flagged this as credibility-critical and was half right: the
    behaviour was already correct, but nothing tested it, so nothing would catch it
    drifting. The clause is not a mode switch - it settles ONE axis and leaves the
    record axis exactly where the declaration left it, which is why `no declaration +
    SECURITY_ENFORCED` must stay undetermined rather than being rounded to safe.
    """

    def _axes(self, decl, api=58.0):
        d = "" if decl == "none" else decl + " sharing "
        src = ("public %sclass C { void m(){ Object o = "
               "[SELECT Customer_IBAN__c FROM Blast_Test__c WITH SECURITY_ENFORCED]; } }" % d)
        r = parse_apex_source(src, api).operations[0].resolved
        return (r.enforces_sharing, r.enforces_fls)

    def test_it_enforces_the_fls_axis_whatever_the_declaration(self):
        for decl in ("with", "without", "none"):
            self.assertTrue(self._axes(decl)[1], f"{decl}: FLS must be enforced")

    def test_it_leaves_the_record_axis_to_the_declaration(self):
        self.assertTrue(self._axes("with")[0])       # `with sharing` still filters
        self.assertFalse(self._axes("without")[0])   # it does NOT rescue the record axis
        self.assertIsNone(self._axes("none")[0])     # inherited: honestly undetermined

    def test_it_does_not_pretend_to_be_user_mode(self):
        # The trap: reading SECURITY_ENFORCED as "user mode" would clear the record
        # axis on a `without sharing` class and hide a real PS501.
        self.assertEqual(self._axes("without"), (False, True))


class ArrayDeclaredDmlTargetTest(unittest.TestCase):
    """`Invoice[] x` is a list declaration, and its DML target must resolve.

    Raised by an external review ("typed DML inference may break in some edges") and
    it was right: _OBJ_DECL only knows a fixed set of standard objects, Invoice is not
    among them, so `Invoice[] x = ...; insert x;` gave sobject=None and a provable
    PS503 degraded to an honest-unknown PS504. `X[] y` is unambiguously a list-of-X,
    so the type can be taken from ANY name here - unlike a bare `X y`, where a regex
    cannot tell an sObject from an Apex class and must not guess.

    The AST backend already got this right, which is exactly why it showed up as a
    DEGRADED row in the differential rather than as a wrong answer.
    """

    def _dml(self, body, api=58.0):
        return [(o.operation, o.sobject)
                for o in parse_apex_source("public class C { void m(){ %s } }" % body, api).operations
                if o.operation != "read"]

    def test_array_declaration_resolves(self):
        self.assertEqual(self._dml("Invoice[] x = new Invoice[0]; insert x;"),
                         [("insert", "Invoice")])

    def test_generic_list_still_resolves(self):
        self.assertEqual(self._dml("List<Invoice> x = new List<Invoice>(); insert x;"),
                         [("insert", "Invoice")])

    def test_an_untyped_sobject_is_still_not_guessed(self):
        # `SObject` names no object. Unknown beats confidently wrong.
        self.assertEqual(self._dml("SObject x = new Account(); insert x;"),
                         [("insert", None)])


class StaleClassFromAnotherOrgTest(unittest.TestCase):
    """A .cls on disk is not evidence that THIS org has that class.

    `_follow_one_level` read the folder, so a class left behind by an earlier run
    against a different org was merged into the next org's report - unretrieved,
    unmentioned, and able to invent findings about code the org does not run. The
    live path now passes the org's own answer to `SELECT Name FROM ApexClass` as
    an allowlist; a local run passes None and keeps trusting the folder, because
    there is no org to ask.
    """

    ACTION = ("public with sharing class Act {\n"
              "  public static void go() { Helper.load(); }\n"
              "}\n")
    HELPER = ("public without sharing class Helper {\n"
              "  public static void load() {\n"
              "    List<Secret__c> s = [SELECT Id, Ssn__c FROM Secret__c];\n"
              "  }\n"
              "}\n")

    def _root(self, d):
        classes = os.path.join(d, "classes")
        os.makedirs(classes, exist_ok=True)
        for name, body in (("Act", self.ACTION), ("Helper", self.HELPER)):
            with open(os.path.join(classes, name + ".cls"), "w", encoding="utf-8") as f:
                f.write(body)
            with open(os.path.join(classes, name + ".cls-meta.xml"), "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">'
                        '<apiVersion>58.0</apiVersion><status>Active</status></ApexClass>\n')
        return classes

    def _objects(self, reach):
        return {o.sobject for o in reach.operations if o.sobject}

    def test_no_allowlist_follows_the_folder(self):
        with tempfile.TemporaryDirectory() as d:
            classes = self._root(d)
            reach = parse_apex(os.path.join(classes, "Act.cls"), d, backend="regex")
            self.assertIn("Secret__c", self._objects(reach))

    def test_a_class_the_org_denies_is_not_followed(self):
        # The org was asked and does not have Helper. The file is residue.
        with tempfile.TemporaryDirectory() as d:
            classes = self._root(d)
            reach = parse_apex(os.path.join(classes, "Act.cls"), d, backend="regex",
                               allowed={"Act"})
            self.assertNotIn("Secret__c", self._objects(reach),
                             "a class the org does not have was merged into the reach")

    def test_a_class_the_org_confirms_is_still_followed(self):
        # The allowlist must not become a way to lose real reach.
        with tempfile.TemporaryDirectory() as d:
            classes = self._root(d)
            reach = parse_apex(os.path.join(classes, "Act.cls"), d, backend="regex",
                               allowed={"Act", "Helper"})
            self.assertIn("Secret__c", self._objects(reach))


class CrosslinkIsNotAnObjectTest(unittest.TestCase):
    """PS508's marker must not be counted as a reachable object.

    `crosslink` borrows the `sobject` slot to carry the name of a CLASS that
    delegates further. The first report that ever exercised the selector follow
    therefore announced that the agent reaches seven objects, one of them called
    `HWTariffService` - a latent presentation bug only a working feature could
    expose. The filter belongs here, in the one function every caller shares:
    cli.py had grown its own copy and the report kept the bug.
    """

    def _summary(self, ops):
        from report import summarize_apex

        class _R:
            class_name = "Act"
            api_version = 58.0
            backend = "regex"
            operations = ops
        return summarize_apex(_R(), [])

    def _op(self, kind, sobject, fields=()):
        from apex_introspect import ApexOperation, ResolvedMode
        return ApexOperation(operation=kind, sobject=sobject, fields=list(fields),
                             fields_complete=True,
                             resolved=ResolvedMode(None, None, "test"))

    def test_a_crosslink_marker_is_not_a_reachable_object(self):
        s = self._summary([self._op("read", "Invoice", ["Total__c"]),
                           self._op("crosslink", "HWTariffService")])
        self.assertEqual(s.objects, ["Invoice"])

    def test_a_real_read_still_counts(self):
        s = self._summary([self._op("read", "Invoice", ["Total__c"])])
        self.assertEqual(s.objects, ["Invoice"])
        self.assertEqual(s.fields, ["Invoice.Total__c"])
