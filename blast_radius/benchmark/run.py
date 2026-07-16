"""Agent Authority Benchmark v1 - the runner.

Measures the analyzer against the hand-labelled corpus and reports per-rule
precision / recall, not a test count. Run from the repo root:

    python blast_radius/benchmark/run.py            # table + exit code
    python blast_radius/benchmark/run.py --json     # machine-readable

Exit 1 on any mismatch, so CI catches an accuracy regression the same way it
catches a broken test.

Reading the output honestly:
  * Precision = of the findings we raised, how many were supposed to be there
    (1.0 means no false positives on this corpus).
  * Recall    = of the findings that should exist, how many we raised
    (1.0 means no false negatives on this corpus).
  * "on this corpus" is the whole caveat. These numbers describe the labelled
    cases, not the world. The label-strength table underneath is the honest
    counterweight: a score carried by `reasoned` labels only proves the analyzer
    agrees with its author.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # blast_radius/
sys.path.insert(0, HERE)

from apex_introspect import parse_apex_source       # noqa: E402
from authority_analyzer import analyze_apex         # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402
from corpus import CASES, GRADED, GDPR, SHARING     # noqa: E402


def _perms():
    path = os.path.join(os.path.dirname(HERE), "fixtures", "user_minimal.json")
    with open(path, encoding="utf-8") as f:
        return EffectivePermissions(json.load(f))


def run_case(case, perms):
    reach = parse_apex_source(case["apex"], case["api"], case["id"])
    findings = analyze_apex(reach, perms, GDPR, SHARING, case.get("triggers") or {})
    actual = {f.rule for f in findings} & GRADED
    sev = {f.rule: f.severity for f in findings}

    expected = set(case["expect"])
    tp = sorted(actual & expected)
    fp = sorted(actual - expected)      # cried wolf
    fn = sorted(expected - actual)      # missed a real one

    # severity is a separate claim: "how sure are we", graded only when declared
    sev_bad = []
    for rule, want in (case.get("expect_severity") or {}).items():
        got = sev.get(rule)
        if got != want:
            sev_bad.append(f"{rule}: want {want}, got {got or 'not raised'}")

    return {"id": case["id"], "truth": case["truth"], "tp": tp, "fp": fp, "fn": fn,
            "sev_bad": sev_bad, "ok": not (fp or fn or sev_bad)}


def summarise(results):
    per_rule = {}
    for r in results:
        for rule in r["tp"]:
            per_rule.setdefault(rule, {"tp": 0, "fp": 0, "fn": 0})["tp"] += 1
        for rule in r["fp"]:
            per_rule.setdefault(rule, {"tp": 0, "fp": 0, "fn": 0})["fp"] += 1
        for rule in r["fn"]:
            per_rule.setdefault(rule, {"tp": 0, "fp": 0, "fn": 0})["fn"] += 1
    for rule, c in per_rule.items():
        p_den, r_den = c["tp"] + c["fp"], c["tp"] + c["fn"]
        c["precision"] = c["tp"] / p_den if p_den else None
        c["recall"] = c["tp"] / r_den if r_den else None
    return per_rule


def _pct(v):
    return "  n/a" if v is None else f"{v * 100:5.1f}%"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    perms = _perms()
    results = [run_case(c, perms) for c in CASES]
    per_rule = summarise(results)

    if "--json" in argv:
        print(json.dumps({"results": results, "per_rule": per_rule}, indent=2))
        return 0 if all(r["ok"] for r in results) else 1

    failures = [r for r in results if not r["ok"]]
    print("=" * 74)
    print("AGENT AUTHORITY BENCHMARK v1")
    print("=" * 74)
    print(f"cases: {len(results)}   passed: {len(results) - len(failures)}   "
          f"failed: {len(failures)}")
    print()
    print(f"{'RULE':<8}{'TP':>4}{'FP':>4}{'FN':>4}   {'PRECISION':>9} {'RECALL':>8}")
    print("-" * 74)
    for rule in sorted(per_rule):
        c = per_rule[rule]
        print(f"{rule:<8}{c['tp']:>4}{c['fp']:>4}{c['fn']:>4}   "
              f"{_pct(c['precision']):>9} {_pct(c['recall']):>8}")

    # Label strength - the honest counterweight to the numbers above.
    print()
    strength = {}
    for r in results:
        kind = r["truth"].split(":")[0]
        strength[kind] = strength.get(kind, 0) + 1
    print("LABEL STRENGTH (where the ground truth comes from)")
    for kind in sorted(strength):
        note = {"experiment": "measured in a real org - strong",
                "sfge": "independent engine agrees",
                "platform-doc": "documented semantics, not measured here",
                "reasoned": "author's reasoning - proves CONSISTENCY, not correctness"}
        print(f"  {kind:<14}{strength[kind]:>3}   {note.get(kind, '')}")

    if failures:
        print()
        print("FAILURES")
        for r in failures:
            print(f"  [{r['id']}]  truth={r['truth']}")
            if r["fp"]:
                print(f"     FALSE POSITIVE (cried wolf): {', '.join(r['fp'])}")
            if r["fn"]:
                print(f"     FALSE NEGATIVE (missed):     {', '.join(r['fn'])}")
            for s in r["sev_bad"]:
                print(f"     SEVERITY: {s}")
    print("=" * 74)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
