"""Export the labelled corpus as a language-neutral public benchmark.

WHY A SEPARATE EXPORT RATHER THAN "PUBLISH corpus.py"
    corpus.py speaks OUR vocabulary. Its `expect` field holds PS5xx rule ids, which
    mean something only inside this analyzer, so publishing it verbatim would invite
    people to score themselves against our naming rather than against the platform.
    The part that is universally meaningful is the part the ORG adjudicated:

        given this Apex, at this API version, executed as this user
        -> does the field actually come back?

    That question has one right answer, it was measured in a real org, and anyone's
    analyzer can be scored against it. So the public artifact carries the source, the
    execution conditions, the org's verdict and the provenance of each label - and
    deliberately drops our rule ids from the graded surface.

WHAT IS STRIPPED, AND WHY
    Rationale text occasionally names a third-party engine while explaining a case.
    Public material for this project never does (LAUNCH_ROUND5_DECISION 10.3), so
    those sentences are removed here rather than hand-edited in the corpus - the
    corpus stays honest for internal use, and the export enforces the publication
    rule mechanically. A rule enforced by a script cannot be forgotten; a rule
    enforced by memory can.

WHAT IS RENAMED, AND WHY IT IS NOT COSMETIC
    The lab fixtures are called Blast_Test__c and Blast_Event__e. "Blast" is a
    fragment of the tool's own name, so shipping those identifiers into a corpus
    whose whole point is that the tool is NOT named would be a soft brand plant -
    the same mistake caught in a launch image and corrected in REPRO_v58_v67.md.
    The maintainer found that one; this makes the next one impossible to forget.

    The rename is honest because the identifier is arbitrary: what the org
    adjudicated was a shape - a Private-OWD object, a field the user holds no FLS
    on, and a negative-control field they do hold. Rename the object and the org
    returns the same verdict. Nothing measured depends on the string, which is
    exactly why it is safe to change and pointless to keep.

    Published names match REPRO_v58_v67.md, so a reader following the recipe and a
    reader running the corpus build the same fixture instead of two half-matching
    ones.

Run:  python blast_radius/benchmark/export_public_corpus.py
Out:  public-benchmark/corpus.json  +  cases/<id>.cls
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from corpus import CASES  # noqa: E402

OUT = os.path.join(ROOT, "public-benchmark")

# Sentences naming a third-party engine are dropped from published rationale.
_THIRD_PARTY = re.compile(
    r"(?:^|(?<=[.!?]))[^.!?]*\b(?:sfge|graph engine|appendix ad)\b[^.!?]*[.!?]\s*",
    re.IGNORECASE)


# Lab fixture names carry a fragment of the tool's name. Applied to EVERY published
# string - apex, rationale, fixture - so no path can bypass it by being added later.
_RENAME = {
    "Blast_Test__c": "Sharing_Test__c",
    "Blast_Event__e": "Sharing_Event__e",
}
# The self-check below greps the finished output. It matches the bare word too, not
# just the identifiers, so a NEW fixture named Blast_Anything__c fails the build
# instead of shipping.
_BRAND = re.compile(r"blast", re.IGNORECASE)


def _neutralise(text: str) -> str:
    for lab, public in _RENAME.items():
        text = text.replace(lab, public)
    return text


def _public_why(text: str) -> str:
    cleaned = _THIRD_PARTY.sub("", text or "").strip()
    return _neutralise(re.sub(r"\s+", " ", cleaned))


def _verdict(case: dict) -> dict | None:
    """What the ORG did - the only field an outside analyzer should be scored on."""
    rt = case.get("runtime")
    if not rt:
        return None
    return {
        "sharing_declaration": rt.get("sharing") or "none",
        "mode_clause": rt.get("clause"),
        # expect_read=True means the field came back although the user was NOT
        # entitled to it - i.e. the platform did not bound the read.
        "field_returned_to_unentitled_user": bool(rt.get("expect_read")),
        "bounded_by_running_user": not bool(rt.get("expect_read")),
        "user_is_entitled": bool(rt.get("entitled", False)),
    }


def main() -> None:
    os.makedirs(os.path.join(OUT, "cases"), exist_ok=True)
    adjudicated, unresolvable = [], []

    for c in CASES:
        entry = {
            "id": c["id"],
            "api_version": c.get("api"),
            "source_file": f"cases/{c['id']}.cls",
            "label_provenance": c.get("truth"),
            "rationale": _public_why(c.get("why", "")),
        }
        v = _verdict(c)
        if v:
            entry["org_verdict"] = v
            adjudicated.append(entry)
        else:
            # No runtime shape: these assert what an ANALYZER must REPORT, not what
            # the platform does, so no org can adjudicate them. Published separately
            # and labelled, because counting them as gaps would overstate what is
            # missing and counting them as measured would overstate what is proven.
            entry["why_no_org_verdict"] = (
                "This case asserts what an analyzer should report (an honest unknown, "
                "or a hand-off it does not follow), not platform behaviour. An org "
                "cannot measure the absence of an analyzer's knowledge.")
            unresolvable.append(entry)

        apex = c.get("apex")
        if apex:
            with open(os.path.join(OUT, "cases", f"{c['id']}.cls"), "w",
                      encoding="utf-8", newline="\n") as f:
                f.write(_neutralise(apex.rstrip()) + "\n")

    payload = {
        "benchmark": "Agent Authority Benchmark",
        "version": "1.0",
        "measured_on": "Salesforce Summer '26",
        "fixture": {
            "object": "Sharing_Test__c",
            "org_wide_default": "Private",
            "field_under_test": "Customer_IBAN__c",
            "name_is_arbitrary": (
                "The object name carries nothing. What the org adjudicated is the "
                "SHAPE: a Private-OWD object, a field the running user holds no FLS "
                "on, and a control field they do hold. Build it under any name and "
                "the verdicts reproduce. These names match the repro recipe so both "
                "routes build the same fixture."),
            "running_user": (
                "Object READ on Sharing_Test__c, and deliberately NO field permission "
                "on Customer_IBAN__c. No create/edit/delete anywhere."),
            "negative_control": (
                "Secret_Data__c is a field the user IS entitled to, seeded with a real "
                "value, so a successful read cannot be a null that would have passed "
                "either way. An escape means the data came back AND the user was not "
                "entitled - both facts, never one."),
        },
        "how_to_use": (
            "Run your own analyzer over cases/<id>.cls at the stated api_version, "
            "modelling the running user described in `fixture`. Then compare your "
            "verdict to org_verdict.bounded_by_running_user. That field is what a "
            "real Salesforce org actually did - not an opinion, and not ours."),
        "counts": {
            "total": len(CASES),
            "org_adjudicated": len(adjudicated),
            "not_adjudicable": len(unresolvable),
        },
        "org_adjudicated_cases": adjudicated,
        "not_adjudicable_cases": unresolvable,
    }

    path = os.path.join(OUT, "corpus.json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"[OK] {path}")
    print(f"     {len(adjudicated)} org-adjudicated, {len(unresolvable)} not adjudicable, "
          f"{len(CASES)} total")
    leaked = [c["id"] for c in adjudicated + unresolvable
              if re.search(r"sfge|graph engine", c["rationale"], re.IGNORECASE)]
    print("     third-party engine mentions in published text: "
          + (", ".join(leaked) if leaked else "none"))

    # The old seal describes the previous export. Drop it before checking, so the
    # walk below cannot pass by reading a stale file instead of the new one.
    sums_path = os.path.join(OUT, "CHECKSUMS.md")
    if os.path.exists(sums_path):
        os.remove(sums_path)

    # Grep the FINISHED FILES, not the in-memory strings. A check that reads what it
    # just wrote catches a path that skipped _neutralise(); a check that re-reads the
    # variable it already sanitised only proves the sanitiser ran where we remembered
    # to call it. Non-zero exit, because a warning nobody reads is not a gate.
    branded = []
    for root, _dirs, files in os.walk(OUT):
        for name in sorted(files):
            fp = os.path.join(root, name)
            with open(fp, encoding="utf-8") as f:
                if _BRAND.search(f.read()):
                    branded.append(os.path.relpath(fp, OUT))
    if branded:
        print("[FAIL] the tool's name leaked into published files: "
              + ", ".join(branded))
        print("       Add the fixture to _RENAME above. The corpus is published with "
              "the tool unnamed (LAUNCH_ROUND5_DECISION 10.3); a lab identifier "
              "carrying 'blast' is a soft brand plant, which is the same mistake "
              "already corrected once in a launch image.")
        sys.exit(1)
    print("     tool-name leaks in published files: none")

    _write_checksums(sums_path)
    print(f"[OK] {sums_path}")


def _write_checksums(path: str) -> None:
    """Seal the export. Generated, never hand-written - README.md tells readers that
    an author who can edit the corpus silently has not published a benchmark, and a
    hand-maintained hash list is exactly that: it drifts the first time someone
    regenerates the corpus and forgets the seal. Writing it here means the seal
    cannot describe a different export than the one on disk."""
    import hashlib

    def sha(fp: str) -> str:
        with open(fp, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    corpus = os.path.join(os.path.dirname(path), "corpus.json")
    cases_dir = os.path.join(os.path.dirname(path), "cases")
    lines = [
        "# Integrity",
        "",
        "sha256 of the published corpus, so a later version cannot be quietly "
        "substituted",
        "and no case can be tuned after the fact without the hash moving.",
        "",
        f"    corpus.json  {sha(corpus)}",
        "",
        "Verify:",
        "",
        "    sha256sum corpus.json                    # Linux / macOS",
        "    Get-FileHash corpus.json -Algorithm SHA256   # Windows",
        "",
        "Case sources:",
        "",
    ]
    for name in sorted(os.listdir(cases_dir)):
        lines.append(f"    {sha(os.path.join(cases_dir, name))}  {name}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
