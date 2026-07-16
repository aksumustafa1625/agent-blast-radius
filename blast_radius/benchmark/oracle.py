"""Runtime oracle - let the ORG judge the analyzer.

THE PROBLEM THIS SOLVES
    The benchmark reports 100% precision/recall, and that number is nearly
    worthless on its own: most of its labels are `reasoned`, which means the
    analyzer agrees with the person who wrote the analyzer. A benchmark whose
    ground truth comes from the same mind as the implementation measures
    consistency, not correctness.

THE IDEA
    The analyzer PREDICTS; the org JUDGES. For every case marked `runtime` in the
    corpus, this deploys the same shape as real Apex, runs it in the real org AS
    THE MODELLED USER, and asks the only question that settles it:

        does that field actually come back, or not?

    The generated test ASSERTS THE ANALYZER'S OWN PREDICTION. So a failing test is
    not a broken test - it is the org saying the analyzer is wrong. That is the
    whole point, and it is the only label upgrade worth having:
    `reasoned` / `platform-doc`  ->  `experiment:runtime`.

WHAT IT NEEDS
    An org carrying the Milestone 0 fixture: Blast_Test__c with Customer_IBAN__c.
    The test creates its own throwaway user and permission set (object read, and
    deliberately NO field permission on Customer_IBAN__c), exactly like the E2b
    experiment this generalises.

    python blast_radius/benchmark/oracle.py --org HospitalOrg
    python blast_radius/benchmark/oracle.py --org HospitalOrg --keep   # keep sources

Exit 1 if the org disagrees with the analyzer about any case.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from corpus import CASES                              # noqa: E402

TEST_CLASS = "BR_Oracle_Test"
_OBJECT = "Blast_Test__c"
_FIELD = "Customer_IBAN__c"
# The one field the negative control grants FLS on. Seeded with a value so a
# passing control reads back real data, not a null that would pass either way.
_FIELD_VISIBLE = "Secret_Data__c"


def _ident(case_id: str) -> str:
    """A legal, stable Apex identifier for a case id.

    Apex caps identifiers at 40 characters, and the generated class name adds a
    `BR_Or_` prefix on top - so a descriptive case id like
    `sanitizer-readable-used-caps-severity` overflows and the deploy fails. Long
    ids keep a readable head plus a hash of the FULL id, so the name stays short,
    unique, and deterministic (the same case always generates the same class)."""
    ident = re.sub(r"[^A-Za-z0-9]", "_", case_id)
    if len(ident) <= 28:
        return ident
    digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:6]
    return f"{ident[:21]}_{digest}"


def runtime_cases():
    return [c for c in CASES if c.get("runtime")]


def case_decl(case) -> str:
    """The class's sharing declaration, e.g. `without sharing ` (or empty)."""
    return "" if case["runtime"]["sharing"] == "none" else f"{case['runtime']['sharing']} sharing "


def case_body(case) -> str:
    """The Apex statements a case measures, indented for a method body.

    Public because the sfge differential (sfge_diff.py) generates the SAME code for
    the other engine. If it built its own variant, the differential would compare two
    engines on two different programs and prove nothing about either."""
    rt = case["runtime"]
    clause = f" {rt['clause']}" if rt["clause"] else ""
    if rt.get("kind") == "write":
        # DML takes `as user`/`as system`, not a WITH clause - a different syntax
        # for the same precedence rule, which is part of what this measures.
        return rt.get("body") or (
            f"            insert{clause} new {_OBJECT}(Name = 'oracle-write');\n"
            f"            return 'WROTE=ok';")
    return rt.get("body") or f"""            List<{_OBJECT}> r = [SELECT {_FIELD} FROM {_OBJECT}{clause} LIMIT 1];
            if (r.isEmpty()) return 'NO_ROWS';
            return 'READ=' + r[0].{_FIELD};"""


def _reader_source(case) -> str:
    """The Apex under test. Most cases only vary the sharing declaration and the
    mode clause, so the body is generated; a case may supply its own `body` when
    the thing being measured is not the query itself but what happens to the data
    afterwards (e.g. whether stripInaccessible really removes the field, or whether
    discarding its decision really leaves the original readable - the two platform
    premises PS512 rests on).

    Two kinds, because the tool tracks two axes and they need different evidence.
    A `read` case measures FLS: whether a field the user has no permission on can
    still escape. A `write` case measures object CRUD: the user holds no Create, so
    whether the insert lands is exactly what execution mode decides. They cannot
    share a running user - under Private OWD a read case has to own its row to see
    it at all, and owning it requires the very Create a write case must not have.
    """
    rt = case["runtime"]
    kind = rt.get("kind", "read")
    decl = case_decl(case)
    body = case_body(case)
    if kind == "write":
        predicts = "WRITEABLE past" if rt["expect_write"] else "OUT OF REACH of"
    else:
        predicts = "READABLE past" if rt["expect_read"] else "OUT OF REACH of"
    return f"""/* Generated by benchmark/oracle.py for case `{case['id']}`. Do not edit.
 * The analyzer's model of the platform predicts this {kind} is
 * {predicts} the running user. The org decides.
 */
public {decl}class BR_Or_{_ident(case['id'])} {{
    public String run() {{
        try {{
{body}
        }} catch (Exception e) {{
            String m = e.getMessage();
            return 'BLOCKED=' + (m.length() > 60 ? m.substring(0, 60) : m);
        }}
    }}
}}
"""


def _meta(api: float) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            f'    <apiVersion>{api:.1f}</apiVersion>\n'
            '    <status>Active</status>\n</ApexClass>\n')


def _test_source(cases) -> str:
    methods = []
    for i, c in enumerate(cases):
        name = _ident(c["id"])
        rt = c["runtime"]
        # The tool's entire premise is that the same code has a different blast
        # radius for a different user, so the oracle has to be able to vary one.
        # Object Edit is the axis that matters for the stripInaccessible cases.
        perms = rt.get("perms") or {}
        wedit = redit = "true" if perms.get("edit") else "false"
        # Fields this case's user IS granted read on. Everything else stays invisible.
        grants = "new List<String>{%s}" % ", ".join(
            f"'{f}'" for f in (perms.get("read_fields") or []))
        if rt.get("kind") == "write":
            # No seed row: the insert IS the measurement. This user deliberately
            # holds no Create, so a landing insert is the escalation itself.
            check = (f"        System.assert(v.startsWith('WROTE='),\n"
                     f"            'ANALYZER PREDICTED ESCALATION (the write lands although the "
                     f"user has no Create) but the org said: ' + v);"
                     if rt["expect_write"] else
                     f"        System.assert(v.startsWith('BLOCKED='),\n"
                     f"            'ANALYZER PREDICTED THE WRITE IS BLOCKED (CRUD enforced) "
                     f"but the org said: ' + v);")
            methods.append(f"""
    @isTest
    static void {name}() {{
        User usr = setup('W{i}', false, {wedit}, {grants});
        String v;
        System.runAs(usr) {{
            v = new BR_Or_{name}().run();
        }}
{check}
    }}""")
            continue
        # The assertion IS the analyzer's prediction. Failing means the org
        # disagrees with the analyzer - which is exactly what we want to hear.
        if rt["expect_read"]:
            check = (f"        System.assert(v.startsWith('READ='),\n"
                     f"            'ANALYZER PREDICTED ESCALATION (the field escapes past the "
                     f"running user) but the org said: ' + v);")
        else:
            check = (f"        System.assert(v.startsWith('BLOCKED='),\n"
                     f"            'ANALYZER PREDICTED THE FIELD IS OUT OF REACH (FLS enforced) "
                     f"but the org said: ' + v);")
        # SOSL returns NOTHING inside an Apex test unless the search results are
        # fixed first. Without this the case would read 'NO_ROWS' and quietly prove
        # nothing at all - the sort of vacuous green that makes a suite worthless.
        seed = ("            Test.setFixedSearchResults(new List<Id>{ rec.Id });\n"
                if rt.get("fixed_search") else "")
        methods.append(f"""
    @isTest
    static void {name}() {{
        User usr = setup('T{i}', true, {redit}, {grants});
        String v;
        System.runAs(usr) {{
            {_OBJECT} rec = new {_OBJECT}(Name = 'oracle', {_FIELD} = 'SECRET-IBAN',
                {_FIELD_VISIBLE} = 'VISIBLE-DATA');
            insert rec;
{seed}            v = new BR_Or_{name}().run();
        }}
{check}
        System.assertNotEquals('NO_ROWS', v,
            'the oracle proved nothing: no row reached the query');
    }}""")

    return f"""/* Generated by benchmark/oracle.py. Do not edit.
 *
 * Every assertion here is the ANALYZER'S OWN PREDICTION about the real org. A
 * failure is not a broken test - it is the org telling us the analyzer is wrong.
 * That is the only ground truth worth having.
 *
 * The user is deliberately minimal: READ on {_OBJECT}, and NO field permission on
 * {_FIELD}. So the field is out of the user's reach unless execution mode puts it
 * back in - which is precisely the thing under test.
 *
 * Write cases get their own user with canCreate=false, because their whole claim is
 * about a missing Create. A read case cannot use that user: {_OBJECT} is Private, so
 * the row has to be owned by the reader to be visible at all, and owning it means
 * inserting it - which needs the Create a write case must not have.
 */
@isTest
private class {TEST_CLASS} {{

    private static User setup(String tag, Boolean canCreate, Boolean canEdit,
                             List<String> readableFields) {{
        User usr;
        System.runAs(new User(Id = UserInfo.getUserId())) {{
            Profile p = [SELECT Id FROM Profile WHERE Name = 'Standard User' LIMIT 1];
            String suffix = String.valueOf(System.now().getTime()) + tag;
            usr = new User(
                FirstName = 'Blast', LastName = 'Oracle' + tag,
                Email = 'blast.oracle@example.com',
                Username = 'blast.oracle.' + suffix + '@blastradius.example.com',
                Alias = 'bo' + tag, ProfileId = p.Id,
                TimeZoneSidKey = 'Europe/Berlin', LocaleSidKey = 'en_US',
                EmailEncodingKey = 'UTF-8', LanguageLocaleKey = 'en_US');
            insert usr;
            PermissionSet ps = new PermissionSet(Name = 'BR_Oracle_' + tag,
                                                 Label = 'BR Oracle ' + tag);
            insert ps;
            insert new ObjectPermissions(ParentId = ps.Id, SobjectType = '{_OBJECT}',
                PermissionsRead = true, PermissionsCreate = canCreate,
                PermissionsEdit = canEdit);
            // Granted per case. A case that grants nothing leaves every field
            // invisible - which is the point for the escalation cases, and exactly
            // why at least one case must grant something (see the negative control).
            List<FieldPermissions> fps = new List<FieldPermissions>();
            for (String fld : readableFields) {{
                fps.add(new FieldPermissions(ParentId = ps.Id, SobjectType = '{_OBJECT}',
                    Field = '{_OBJECT}.' + fld, PermissionsRead = true));
            }}
            if (!fps.isEmpty()) insert fps;
            insert new PermissionSetAssignment(AssigneeId = usr.Id, PermissionSetId = ps.Id);
        }}
        return usr;
    }}
{''.join(methods)}
}}
"""


def _run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=cwd)


def build(cases, root):
    classes = os.path.join(root, "force-app", "main", "default", "classes")
    os.makedirs(classes)
    for c in cases:
        base = os.path.join(classes, f"BR_Or_{_ident(c['id'])}")
        with open(base + ".cls", "w", encoding="utf-8") as f:
            f.write(_reader_source(c))
        with open(base + ".cls-meta.xml", "w", encoding="utf-8") as f:
            f.write(_meta(c["api"]))
    with open(os.path.join(classes, TEST_CLASS + ".cls"), "w", encoding="utf-8") as f:
        f.write(_test_source(cases))
    with open(os.path.join(classes, TEST_CLASS + ".cls-meta.xml"), "w", encoding="utf-8") as f:
        f.write(_meta(59.0))          # the test harness's own version is irrelevant
    with open(os.path.join(root, "sfdx-project.json"), "w", encoding="utf-8") as f:
        json.dump({"packageDirectories": [{"path": "force-app", "default": True}],
                   "name": "br-oracle", "namespace": "",
                   "sfdcLoginUrl": "https://login.salesforce.com",
                   "sourceApiVersion": "59.0"}, f)
    return classes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Runtime oracle: let the org judge the analyzer.")
    ap.add_argument("--org", required=True, help="sf target org alias (needs the Blast_Test__c fixture)")
    ap.add_argument("--keep", action="store_true", help="keep the generated sources")
    args = ap.parse_args(argv)

    cases = runtime_cases()
    print("=" * 74)
    print("RUNTIME ORACLE - the analyzer predicts, the org judges")
    print("=" * 74)
    print(f"cases with a runtime shape: {len(cases)}   org: {args.org}")
    for c in cases:
        rt = c["runtime"]
        if rt.get("kind") == "write":
            want = ("write LANDS without Create" if rt["expect_write"]
                    else "write BLOCKED (CRUD enforced)")
        else:
            want = ("field READABLE past the user" if rt["expect_read"]
                    else "field OUT OF REACH (FLS enforced)")
        print(f"  {c['id']:38} api v{c['api']:g}  predicts: {want}")

    root = tempfile.mkdtemp(prefix="br_oracle_")
    try:
        build(cases, root)
        print("\ndeploying generated Apex ...")
        r = _run(f'sf project deploy start --source-dir force-app --target-org {args.org} --json',
                 cwd=root)
        if r.returncode != 0:
            print("DEPLOY FAILED - the oracle cannot judge without it:")
            print((r.stdout or r.stderr)[:1200])
            return 1

        print(f"running {TEST_CLASS} as the modelled user ...\n")
        r = _run(f'sf apex run test --class-names {TEST_CLASS} --synchronous --json '
                 f'--target-org {args.org}', cwd=root)
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            print("could not read test results:")
            print((r.stdout or r.stderr)[:1200])
            return 1

        results = (data.get("result") or {}).get("tests") or []
        by_case = {}
        for t in results:
            by_case[t.get("MethodName")] = t
        disagreements = []
        print(f"{'CASE':<40}{'ORG SAYS':<12}{'LABEL':<10}")
        print("-" * 74)
        for c in cases:
            t = by_case.get(_ident(c["id"]))
            if not t:
                verdict, note = "not run", ""
                disagreements.append((c, "the oracle never ran this case"))
            elif t.get("Outcome") == "Pass":
                verdict, note = "agrees", ""
            else:
                verdict = "DISAGREES"
                note = (t.get("Message") or "").strip()
                disagreements.append((c, note))
            upgrade = "experiment:runtime" if verdict == "agrees" else c["truth"]
            print(f"{c['id']:<40}{verdict:<12}{upgrade:<10}")

        print("-" * 74)
        if disagreements:
            print(f"\nTHE ORG DISAGREES WITH THE ANALYZER on {len(disagreements)} case(s).")
            print("That is a real finding: the label was wrong, or the analyzer is.\n")
            for c, note in disagreements:
                print(f"  [{c['id']}]  label was: {c['truth']}")
                print(f"     why we believed it: {c['why'][:150]}")
                if note:
                    print(f"     org: {note[:200]}")
        else:
            print(f"\nThe org agrees with the analyzer on all {len(cases)} runtime cases.")
            print("Those labels are measured, not reasoned - the only kind worth having.")
        print("=" * 74)
        return 1 if disagreements else 0
    finally:
        if args.keep:
            print(f"\ngenerated sources kept at: {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
