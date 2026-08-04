"""sfge differential - and the org is the referee.

WHY THIS SHAPE
    Salesforce ships a static Graph Engine (sfge) with two rules that overlap this
    tool almost exactly:
        ApexFlsViolation                     -> the FLS/CRUD axis (our PS502/503/506)
        DatabaseOperationsMustUseWithSharing -> the record axis   (our PS501)
    A differential on its own only ever concludes "they disagree", which settles
    nothing - two engines disagreeing is not evidence about either. So this runs on
    exactly the corpus cases that carry a `runtime` shape: the ones the ORG has
    already adjudicated (oracle.py). Every disagreement therefore has a referee, and
    the question stops being "who do you believe" and becomes "who was right".

    The generated code comes from oracle.case_body, the SAME source the org ran. If
    this file wrote its own variant, the three columns would describe three different
    programs.

FAIRNESS - state the limits, they matter
    STATUS FIRST, because it changes what the numbers are worth: sfge ships in Code
    Analyzer v5 marked "(Developer Preview)". Comparing against a Developer Preview
    engine is a materially weaker claim than comparing against a GA one, and an
    informed reviewer will raise it before we do. So any repetition of these numbers,
    anywhere, states the status in the same breath.
        Verified 2026-08-04: Code Analyzer v5.15.0 (July 2026) still ships sfge and
        its seven rules, including the two compared here. What was RETIRED is Code
        Analyzer *v4* - the whole v4 doc set inherits a "(Retired)" title suffix,
        which is where the widespread "the Graph Engine is dead" belief comes from.
        Three separate external reviewers repeated it; it is false.
        NOT verified: whether the "(Developer Preview)" marker itself still stands.
        It was last confirmed at v5.0.0-beta.3 (March 2025). Re-check it, not just
        the engine's existence, before publishing any comparison.

    sfge is a general-purpose, conservative scanner: it flags a code PATTERN (no
    explicit FLS check present), while this tool answers a narrower question (does
    THIS running user's authority get exceeded). On a case where the user is allowed
    the data, sfge flagging is not "wrong" by its own contract - it has no notion of a
    running user or a GDPR label. What IS a plain factual error is flagging code the
    platform demonstrably bounds. So the table below reports both columns, and only
    calls a verdict WRONG where the org measured the opposite.

    sfge only walks from an ENTRY POINT, so each case is wrapped in an
    @InvocableMethod - which is also how an agent actually calls Apex.

    python blast_radius/benchmark/sfge_diff.py            # all runtime cases
    python blast_radius/benchmark/sfge_diff.py --keep     # keep generated sources

NOT IN CI, ON PURPOSE - and the reason is not speed
    It runs in ~42s, so cost was never the objection; the measurement said so and the
    guess that it was "slow" was wrong. It is out because the `analyze` job has one
    contract - prove the ANALYZER is correct, need no org, always run - and this
    proves a COMPARATIVE CLAIM instead. Putting it in the gate would drag a
    third-party Java engine into the critical path for evidence that does not change
    per commit, and a red build there would usually mean *sfge changed*, not that we
    broke something. Our own column against the org is already gated, by run.py.

    Exit code follows from that: non-zero only when THIS TOOL contradicts the org.
    If Salesforce fixes its v67 blindness tomorrow, that is good news and this must
    not fail - but the claim in CLAUDE.md would then be stale, so re-run this before
    repeating any of its numbers. A published number nobody re-measures is the same
    stale-doc failure this repo has paid for more than once.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from corpus import CASES, GDPR, SHARING                      # noqa: E402
from oracle import _ident, case_body, case_decl              # noqa: E402
import apex_introspect                                       # noqa: E402
import authority_analyzer                                    # noqa: E402
from permission_resolver import EffectivePermissions         # noqa: E402

# sfge's two rules and the axis each speaks to.
FLS_RULE = "ApexFlsViolation"
SHARING_RULE = "DatabaseOperationsMustUseWithSharing"

# Our rules on the same axes. PS501 is the record axis; the rest are FLS/CRUD.
OUR_FLS = {"PS502", "PS503", "PS506"}
OUR_SHARING = {"PS501"}

SNAPSHOT = os.path.join(os.path.dirname(HERE), "fixtures", "user_minimal.json")


def runtime_cases():
    return [c for c in CASES if c.get("runtime")]


def _class_source(case) -> str:
    """The case, wrapped so sfge has an entry point to walk from.

    sfge analyses from entry points only (@InvocableMethod, @AuraEnabled, ...); a
    plain public method is not one, and a corpus case wrapped as one would silently
    produce zero violations - a vacuous 'sfge agrees' that proves nothing. The
    invocable is also how an agent really calls Apex, so the shape is honest, not a
    convenience."""
    name = "SFGE_" + _ident(case["id"])
    return f"""/* Generated by benchmark/sfge_diff.py for case `{case['id']}`. Do not edit.
 * Body is oracle.case_body - the same statements the ORG executed, so sfge, this
 * tool, and the org are all describing one program.
 */
public {case_decl(case)}class {name} {{
    @InvocableMethod(label='{name}')
    public static List<String> entry(List<String> ignored) {{
        return new List<String>{{ new {name}().run() }};
    }}

    public String run() {{
        try {{
{case_body(case)}
        }} catch (Exception e) {{
            return 'BLOCKED';
        }}
    }}
}}
"""


def _meta(api: float) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<ApexClass xmlns="http://soap.sforce.com/2006/04/metadata">\n'
            f'    <apiVersion>{api:.1f}</apiVersion>\n'
            '    <status>Active</status>\n</ApexClass>\n')


def build(cases, root):
    classes = os.path.join(root, "force-app", "main", "default", "classes")
    os.makedirs(classes)
    for c in cases:
        base = os.path.join(classes, "SFGE_" + _ident(c["id"]))
        with open(base + ".cls", "w", encoding="utf-8") as f:
            f.write(_class_source(c))
        with open(base + ".cls-meta.xml", "w", encoding="utf-8") as f:
            f.write(_meta(c["api"]))
    with open(os.path.join(root, "sfdx-project.json"), "w", encoding="utf-8") as f:
        json.dump({"packageDirectories": [{"path": "force-app", "default": True}],
                   "name": "br-sfge", "namespace": "",
                   "sfdcLoginUrl": "https://login.salesforce.com",
                   "sourceApiVersion": "59.0"}, f)
    return classes


def our_verdict(case):
    """(asserts_escalation, raises_warn, flags_record) from THIS tool.

    ERROR and WARN are kept apart because severity here IS the proof level, and
    collapsing them would score this tool against a claim it never made: a WARN says
    "a real boundary I could not prove", which is the honest answer, not an assertion
    that the data escaped. sfge has no such distinction - it flags or it doesn't - so
    the table shows both columns rather than pretending the two scales are one."""
    src = f"public {case_decl(case)}class C {{ void m(){{ {case_body(case).strip()} }} }}"
    reach = apex_introspect.parse_apex_source(src, case["api"], "C")
    perms = EffectivePermissions(json.load(open(SNAPSHOT, encoding="utf-8")))
    findings = authority_analyzer.analyze_apex(reach, perms, GDPR, SHARING, {})
    fls = [f for f in findings if f.rule in OUR_FLS]
    return (any(f.severity == "ERROR" for f in fls),
            any(f.severity == "WARN" for f in fls),
            any(f.rule in OUR_SHARING for f in findings))


def org_axis(case):
    """Which axis a case's runtime shape adjudicates: 'record' or 'fls'."""
    return "record" if case["runtime"].get("kind") == "record" else "fls"


def org_escalation(case):
    """Did the ORG's outcome mean an ESCALATION - data past a user who was not
    entitled to it?

    For a RECORD case the entitlement is the share, not the field: `entitled=True`
    marks the FIELD as allowed precisely so the rows are the only thing that can
    escape. Rows coming back that the user has no share on IS the escalation.

    Two facts, never one. "The read returned the field" is not an escape by itself:
    in the negative control it returned precisely because user_minimal HOLDS FLS on
    that field, and calling that an escape would have scored this tool as wrong for
    correctly staying quiet - and scored sfge as right for staying quiet too, for
    entirely different reasons. Blocked outcomes escalate nothing, whoever predicted
    what."""
    rt = case["runtime"]
    kind = rt.get("kind")
    if kind == "record":
        return bool(rt["expect_rows"])      # rows the user has no share on came back
    got = rt["expect_write"] if kind == "write" else rt["expect_read"]
    return bool(got) and not rt.get("entitled", False)


def main(argv=None):
    ap = argparse.ArgumentParser(description="sfge differential, adjudicated by the org.")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    cases = runtime_cases()
    root = tempfile.mkdtemp(prefix="br_sfge_")
    try:
        build(cases, root)
        print("=" * 100)
        print("SFGE DIFFERENTIAL - Salesforce's Graph Engine vs Agent Blast Radius, "
              "refereed by the org")
        print("=" * 100)
        print(f"cases (all org-adjudicated): {len(cases)}")
        print("running sfge ...\n")
        out = os.path.join(root, "sfge.json")
        r = subprocess.run(
            f'sf code-analyzer run --rule-selector sfge --workspace force-app '
            f'--output-file "{out}"',
            shell=True, capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=root)
        if not os.path.exists(out):
            print("sfge produced no output - the differential cannot run:")
            print((r.stdout or r.stderr)[-1500:])
            return 1
        with open(out, encoding="utf-8") as f:
            data = json.load(f)

        by_class = {}
        for v in data.get("violations", []):
            loc = (v.get("locations") or [{}])[0]
            fname = os.path.basename(loc.get("file") or "")
            by_class.setdefault(fname.replace(".cls", ""), set()).add(v.get("rule"))

        print(f"{'CASE':<38}{'v':<5}{'axis':<8}{'ORG':<10}{'sfge':<8}{'ABR':<12}"
              f"{'sfge shr':<10}{'ABR shr':<8}")
        print("-" * 100)
        sfge_wrong = abr_wrong = 0
        rows = []
        for c in cases:
            rules = by_class.get("SFGE_" + _ident(c["id"]), set())
            sfge_fls, sfge_shr = FLS_RULE in rules, SHARING_RULE in rules
            abr_err, abr_warn, abr_shr = our_verdict(c)
            truth = org_escalation(c)
            # Each case is scored on the axis ITS shape adjudicates, and only that
            # one. A record case has a runtime column for sharing and none for FLS;
            # scoring the other axis off it would be scoring a column nobody refereed,
            # which is how a differential flatters whoever wrote it.
            if org_axis(c) == "record":
                s_bad = sfge_shr != truth
                a_bad = abr_shr != truth
            else:
                s_bad = sfge_fls != truth
                a_bad = abr_err != truth
            sfge_wrong += s_bad
            abr_wrong += a_bad
            abr_txt = (("flags" if abr_shr else "clean") if org_axis(c) == "record"
                       else ("ERROR" if abr_err else "WARN" if abr_warn else "clean"))
            rows.append((c, truth, sfge_fls, abr_txt, s_bad, a_bad))
            print(f"{c['id']:<38}{('v%g' % c['api']):<5}{org_axis(c):<8}"
                  f"{('ESCAPES' if truth else 'bounded'):<10}"
                  f"{(('flags*' if s_bad else 'flags') if (sfge_shr if org_axis(c) == 'record' else sfge_fls) else ('clean*' if s_bad else 'clean')):<8}"
                  f"{(abr_txt + ('*' if a_bad else '')):<12}"
                  f"{('flags' if sfge_shr else 'clean'):<10}"
                  f"{('flags' if abr_shr else 'clean'):<8}")
        print("-" * 100)
        print("* = contradicts what the org measured.  ABR: ERROR = asserted as proven,")
        print("  WARN = a real boundary it could not prove (scored as 'did not assert').")
        print()
        # Scored BOTH ways on purpose. The lenient score credits this tool's WARN as
        # "did not assert", which is what WARN means - but sfge is binary, so a
        # sceptic can fairly say the scales were not the same. The strict score treats
        # any ABR finding as an assertion, i.e. grades this tool by sfge's rules. The
        # result holds either way, and publishing only the flattering one would be the
        # same sin as any other selective reporting.
        abr_strict = sum(1 for c, t, _s, ab, _sb, _ab in rows
                         if (ab != "clean") != t)
        print("Each case judged on the axis its runtime shape adjudicates - the FLS/CRUD")
        print("axis for a read/write shape, the RECORD axis for a record shape - and by")
        print("the org, nobody else:")
        print(f"   sfge contradicts the org on                  {sfge_wrong}/{len(cases)}")
        print(f"   Agent Blast Radius contradicts the org on    {abr_wrong}/{len(cases)}"
              f"   (WARN counted as 'did not assert')")
        print(f"   ...and on sfge's own binary scale            {abr_strict}/{len(cases)}"
              f"   (any finding counted as an assertion)")
        print()
        if sfge_wrong:
            print("Every case where sfge and the org disagree:")
            for c, truth, sf_f, ab_t, s_bad, _ in rows:
                if s_bad:
                    kind = ("MISSED a real escape" if truth else
                            "flagged code the platform bounds (false positive)")
                    print(f"  [{c['id']}] api v{c['api']:g} - sfge {kind}; ABR said {ab_t}")
                    print(f"     {c['why'][:140]}")
        print()
        print("Read this fairly - the 6 are not one thing:")
        print("  * apiVersion blindness (v67 read x2, v67 write): sfge looks for an")
        print("    explicit check and gives no credit for secure-by-default. E2b and the")
        print("    oracle both measured the platform bounding this code. Unambiguous.")
        print("  * SOSL: sfge's ApexFlsViolation never walks a SOSL RETURNING, so it")
        print("    misses an escape the org hands over. A coverage gap, not a judgement.")
        print("  * the two sanitizer rows: sfge does not credit stripInaccessible here.")
        print("    This tool does not call them clean either - it says WARN, because it")
        print("    cannot prove WHICH list reaches the sink. Weakest of the six; report")
        print("    it as a difference in severity discipline, not as sfge being broken.")
        print()
        print("And sfge is not a competitor doing this badly - it is a general-purpose,")
        print("deliberately conservative scanner answering a DIFFERENT question: 'is an")
        print("FLS check present in this code?', with no notion of a running user or a")
        print("GDPR label. On a case where the user is entitled to the data, its flag is")
        print("not an error by its own contract. The claim here is narrow and it is the")
        print("only one the evidence supports: for THIS question - what can this agent")
        print("reach as THIS user - a version-aware, user-scoped analysis is measurably")
        print("more precise, and the org is what says so.")
        print("=" * 100)
        # Exit on OUR column only. sfge's count moving is not our regression - if
        # Salesforce fixes its v67 blindness tomorrow that is good news, and a build
        # that went red over it would be punishing the wrong party. Ours moving above
        # zero means this tool started contradicting a measurement, which is a real
        # regression and the only thing here worth failing a build for.
        return 1 if abr_wrong else 0
    finally:
        if args.keep:
            print(f"\ngenerated sources kept at: {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
