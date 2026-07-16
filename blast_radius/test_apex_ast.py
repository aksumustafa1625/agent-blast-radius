"""Tests for the real-AST Apex backend (apex-parser via ast_extract.js).

Two things are proven here:
  1. PARITY  - on the real demo class the AST backend resolves the same reach and
     escalation the verified regex path does (so switching backend is safe).
  2. SUPERIORITY - on a subquery the regex extractor grabs the inner FROM and
     misidentifies the object; the AST backend gets the parent object right and
     also captures the subquery. This is the concrete reason for the migration.

All AST tests skip cleanly when Node / apex-parser is not installed, so the suite
stays green in a Python-only environment (the tool falls back to regex there).

Run from the repo root:  python blast_radius/test_apex_ast.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apex_ast  # noqa: E402
from apex_introspect import parse_apex  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSES = os.path.join(HERE, "..", "force-app", "main", "default", "classes")
REAL_ESCALATING = os.path.join(CLASSES, "GetHealthRecordSummary.cls")   # v58 without sharing
REAL_SAFE = os.path.join(CLASSES, "GetHealthRecordSummarySafe.cls")     # v67 with sharing + USER_MODE
SUBQUERY = os.path.join(HERE, "fixtures", "ast_cases", "classes", "SubqueryDemo.cls")

AST = apex_ast.ast_available()


@unittest.skipUnless(AST, "AST backend (node + apex-parser) not available")
class AstAvailabilityTest(unittest.TestCase):
    def test_backend_reports_ast(self):
        reach = parse_apex(SUBQUERY, backend="ast")
        self.assertEqual(reach.backend, "ast")


@unittest.skipUnless(AST and os.path.exists(REAL_ESCALATING), "AST or demo class unavailable")
class ParityTest(unittest.TestCase):
    """The AST backend reproduces the regex backend's verified result."""

    def _reads(self, reach):
        return sorted((o.sobject, tuple(o.fields),
                       o.resolved.enforces_sharing, o.resolved.enforces_fls)
                      for o in reach.operations if o.operation == "read")

    def test_escalating_class_matches_regex(self):
        ast = parse_apex(REAL_ESCALATING, backend="ast")
        rx = parse_apex(REAL_ESCALATING, backend="regex")
        self.assertEqual(self._reads(ast), self._reads(rx))
        # and the substance: v58 without-sharing plain read is escalation-capable
        op = next(o for o in ast.operations if o.operation == "read")
        self.assertEqual(op.sobject, "HealthRecord__c")
        self.assertIn("Diagnosis__c", op.fields)
        self.assertTrue(op.resolved.is_escalation_capable)

    def test_safe_class_matches_regex_and_is_clean(self):
        ast = parse_apex(REAL_SAFE, backend="ast")
        rx = parse_apex(REAL_SAFE, backend="regex")
        self.assertEqual(self._reads(ast), self._reads(rx))
        op = next(o for o in ast.operations if o.operation == "read")
        # WITH USER_MODE -> both axes enforced -> not escalation-capable
        self.assertFalse(op.resolved.is_escalation_capable)


@unittest.skipUnless(AST and os.path.exists(SUBQUERY), "AST or fixture unavailable")
class SuperiorityTest(unittest.TestCase):
    """Where the backends differ - kept honest by measurement, not by assumption.

    This class used to assert that the regex extractor MISIDENTIFIES a subquery's
    parent: it grabbed the subquery's FROM and lost the outer object, and that was
    written down as the AST's superiority. A differential over 104 real classes
    showed what that cost - an `Order` read vanishing from the reach, i.e. a false
    clean - so the regex path now lifts subqueries out and finds the top-level FROM.
    Both backends get the parent right, and this test says so.

    The AST's real advantages are elsewhere, and they are the ones a regex cannot
    have at all: scope (a local shadowing a field), and knowing that SOQL-shaped text
    inside a string is not a query. Claiming an advantage the tool no longer has is
    the same failure as hiding one it does.
    """

    def _objects(self, backend):
        reach = parse_apex(SUBQUERY, backend=backend)
        return {o.sobject for o in reach.operations if o.operation == "read"}

    def test_both_backends_get_the_parent_object_and_the_subquery(self):
        for backend in ("ast", "regex"):
            objs = self._objects(backend)
            self.assertIn("Account", objs, f"{backend} lost the parent object")
            self.assertIn("Contacts", objs, f"{backend} lost the subquery")

    def test_ast_gets_parent_object_and_subquery(self):
        ast_objs = self._objects("ast")
        self.assertIn("Account", ast_objs)      # correct parent object
        self.assertIn("Contacts", ast_objs)     # subquery child reach also captured

    def test_ast_reads_parent_fields(self):
        reach = parse_apex(SUBQUERY, backend="ast")
        acct = next(o for o in reach.operations
                    if o.operation == "read" and o.sobject == "Account")
        self.assertEqual(acct.fields, ["Id", "Name"])
        self.assertTrue(acct.fields_complete)


INTERNAL_ONLY = os.path.join(HERE, "fixtures", "ast_cases", "classes", "InternalOnlyDemo.cls")
ALIAS = os.path.join(HERE, "fixtures", "ast_cases", "classes", "AliasDemo.cls")

_CLASSIFY = {"HealthRecord__c.Diagnosis__c": {"complianceGroup": "GDPR;PII"}}


def _minimal_perms():
    import json
    from permission_resolver import EffectivePermissions
    with open(os.path.join(HERE, "fixtures", "user_minimal.json"), encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))   # no FLS on Diagnosis__c


def _flow(path, field, backend="ast"):
    reach = parse_apex(path, backend=backend)
    op = next(o for o in reach.operations
              if o.operation == "read" and field in o.fields)
    return (op.field_flow or {}).get(field)


def _ps506(path, backend="ast"):
    from authority_analyzer import analyze_apex
    reach = parse_apex(path, backend=backend)
    findings = analyze_apex(reach, _minimal_perms(), _CLASSIFY, {})
    return next((f for f in findings if f.rule == "PS506"), None)


@unittest.skipUnless(AST, "AST backend not available")
class AuthorityPathTest(unittest.TestCase):
    """Source->sink taint: is the field PROVEN to reach the model, or only assumed?"""

    def test_returned_field_is_confirmed(self):
        # recs[0].Diagnosis__c flows into r.summary (an @InvocableVariable) -> proven.
        self.assertEqual(_flow(REAL_ESCALATING, "Diagnosis__c"), "returned")
        f = _ps506(REAL_ESCALATING)
        self.assertEqual(f.severity, "ERROR")
        self.assertIn("CONFIRMED", f.why)

    def test_internal_only_field_is_not_a_model_leak(self):
        # Diagnosis__c is read but used ONLY in an if-predicate; Patient_Name__c
        # is the one that reaches the output. Precision win: PS506 downgrades.
        self.assertEqual(_flow(INTERNAL_ONLY, "Diagnosis__c"), "internal")
        self.assertEqual(_flow(INTERNAL_ONLY, "Patient_Name__c"), "returned")
        f = _ps506(INTERNAL_ONLY)
        self.assertEqual(f.severity, "WARN")            # downgraded, not silenced
        self.assertIn("not observed reaching the model", f.message)

    def test_aliased_field_is_now_traced_through_the_local(self):
        # `String d = recs[0].Diagnosis__c; r.summary = d;` used to stop the trace:
        # the alias made it 'undetermined' = worst case. The flow was always real,
        # we just could not see it. Following the alias forward through its uses
        # now PROVES it, and names the sink - so the verdict is stronger evidence,
        # not a downgrade: still ERROR, but "CONFIRMED" instead of "NOT TRACED".
        self.assertEqual(_flow(ALIAS, "Diagnosis__c"), "returned")
        f = _ps506(ALIAS)
        self.assertEqual(f.severity, "ERROR")
        self.assertIn("CONFIRMED", f.why)

    def test_alias_tracking_soundness_boundaries(self):
        """The alias trace may only ever make the verdict MORE precise. The one
        way it could hurt is concluding 'internal' when a use was missed - a
        silent false-clean. These lock the boundaries it must respect."""
        import tempfile, textwrap
        src = textwrap.dedent("""
            public without sharing class AliasEdge {
                public class Resp {
                    @InvocableVariable public String summary;
                    @InvocableVariable public List<String> items;
                }
                @InvocableMethod(label='p')
                public static List<Resp> run(List<String> ids) {
                    List<Resp> out = new List<Resp>();
                    Resp r = new Resp();
                    List<HealthRecord__c> recs = [SELECT A__c, B__c, C__c, D__c, E__c
                                                  FROM HealthRecord__c];
                    String a = recs[0].A__c;
                    if (ids.size() > 0) { r.summary = a; }
                    String b = recs[0].B__c;
                    for (String i : ids) { r.items.add(b); }
                    String c1 = recs[0].C__c;
                    String c2 = c1;
                    r.summary = c2;
                    String d = recs[0].D__c;
                    System.debug(d);
                    String e = recs[0].E__c;
                    out.add(r);
                    return out;
                }
            }
        """).strip()
        with tempfile.TemporaryDirectory() as tmp:
            classes = os.path.join(tmp, "classes")
            os.makedirs(classes)
            path = os.path.join(classes, "AliasEdge.cls")
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            with open(path + "-meta.xml", "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?><ApexClass '
                        'xmlns="http://soap.sforce.com/2006/04/metadata">'
                        '<apiVersion>58.0</apiVersion><status>Active</status></ApexClass>')
            reach = parse_apex(path, tmp, backend="ast")
        op = [o for o in reach.operations if o.operation == "read"][0]
        flow = op.field_flow or {}
        # a sink inside a nested if is still a sink
        self.assertEqual(flow.get("A__c"), "returned")
        # so is a collection add inside a loop
        self.assertEqual(flow.get("B__c"), "returned")
        # an alias of an alias is followed to the sink
        self.assertEqual(flow.get("C__c"), "returned")
        # escaping into an unmodelled method must STAY worst case
        self.assertEqual(flow.get("D__c"), "undetermined")
        # declared and provably never used -> internal is correct, not a guess
        self.assertEqual(flow.get("E__c"), "internal")

    def test_inter_procedural_taint_through_a_helper(self):
        """`helper(rec.Field)` used to end the trace -> undetermined -> worst case.
        Selector/DAO style sends most real reads through exactly that shape, so the
        noise landed where good code lives. Follow the value INTO the callee, but
        only ever tighten a verdict we can prove - anything unseen stays worst case."""
        import tempfile, textwrap
        src = textwrap.dedent("""
            public without sharing class IPEdge {
                public class Resp { @InvocableVariable public String summary; }
                @InvocableMethod(label='p')
                public static List<Resp> run(List<String> ids) {
                    List<Resp> out = new List<Resp>();
                    Resp r = new Resp();
                    List<HealthRecord__c> recs = [SELECT A__c, B__c, C__c, D__c, E__c
                                                  FROM HealthRecord__c];
                    r.summary = passthrough(recs[0].A__c);
                    checkOnly(recs[0].B__c);
                    fill(r, recs[0].C__c);
                    System.debug(recs[0].D__c);
                    recurse(recs[0].E__c);
                    out.add(r);
                    return out;
                }
                private static String passthrough(String v) { return v; }
                private static void checkOnly(String v) { if (v == null) { Integer x = 1; } }
                private static void fill(Resp target, String v) { target.summary = v; }
                private static String recurse(String v) { return recurse(v); }
            }
        """).strip()
        with tempfile.TemporaryDirectory() as tmp:
            classes = os.path.join(tmp, "classes")
            os.makedirs(classes)
            path = os.path.join(classes, "IPEdge.cls")
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            with open(path + "-meta.xml", "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?><ApexClass '
                        'xmlns="http://soap.sforce.com/2006/04/metadata">'
                        '<apiVersion>58.0</apiVersion><status>Active</status></ApexClass>')
            reach = parse_apex(path, tmp, backend="ast")
        flow = ([o for o in reach.operations if o.operation == "read"][0].field_flow) or {}
        # the helper returns it and the result is sunk -> proven
        self.assertEqual(flow.get("A__c"), "returned")
        # the helper only reads it in a predicate; every use seen -> proven internal
        self.assertEqual(flow.get("B__c"), "internal")
        # the helper writes it onto an output object passed IN -> proven
        self.assertEqual(flow.get("C__c"), "returned")
        # an unmodelled/external method must STAY worst case
        self.assertEqual(flow.get("D__c"), "undetermined")
        # recursion must terminate at worst case, never loop or guess
        self.assertEqual(flow.get("E__c"), "undetermined")

    def test_call_argument_index_ignores_the_commas(self):
        """The parser names its terminal class `De`, not `TerminalNodeImpl`, so a
        naive filter counted the comma as an argument and shifted every index by
        one - mapping the value onto the WRONG parameter. That is precisely how a
        bogus `internal` could be produced, so it is locked here."""
        import tempfile, textwrap
        src = textwrap.dedent("""
            public without sharing class ArgIdx {
                public class Resp { @InvocableVariable public String summary; }
                @InvocableMethod(label='p')
                public static List<Resp> run(List<String> ids) {
                    List<Resp> out = new List<Resp>();
                    Resp r = new Resp();
                    List<HealthRecord__c> recs = [SELECT Z__c FROM HealthRecord__c];
                    // Z__c is the THIRD argument; only a correct index reaches `c`
                    r.summary = pick('a', 'b', recs[0].Z__c);
                    out.add(r);
                    return out;
                }
                private static String pick(String a, String b, String c) { return c; }
            }
        """).strip()
        with tempfile.TemporaryDirectory() as tmp:
            classes = os.path.join(tmp, "classes")
            os.makedirs(classes)
            path = os.path.join(classes, "ArgIdx.cls")
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
            with open(path + "-meta.xml", "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?><ApexClass '
                        'xmlns="http://soap.sforce.com/2006/04/metadata">'
                        '<apiVersion>58.0</apiVersion><status>Active</status></ApexClass>')
            reach = parse_apex(path, tmp, backend="ast")
        flow = ([o for o in reach.operations if o.operation == "read"][0].field_flow) or {}
        self.assertEqual(flow.get("Z__c"), "returned")

    def test_regex_backend_has_no_flow_and_stays_worst_case(self):
        # The fallback backend cannot trace flow -> worst case, never a downgrade.
        self.assertIsNone(_flow(INTERNAL_ONLY, "Diagnosis__c", backend="regex"))
        self.assertEqual(_ps506(INTERNAL_ONLY, backend="regex").severity, "ERROR")


if __name__ == "__main__":
    unittest.main(verbosity=2)
