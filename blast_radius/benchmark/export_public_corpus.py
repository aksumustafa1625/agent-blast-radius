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
    Public material for this project never does (publication rule, held outside
    this repo), so
    those sentences are removed here rather than hand-edited in the corpus - the
    corpus stays honest for internal use, and the export enforces the publication
    rule mechanically. A rule enforced by a script cannot be forgotten; a rule
    enforced by memory can.

    The same treatment for our INTERNAL vocabulary (added 2026-08-19, after an
    external review read v1.0): a customer org's name, our PS5xx rule ids and the
    name of a fixture permission snapshot mean nothing to an outside reader and
    quietly tie the "unnamed" corpus back to one tool. Sentences naming the org are
    dropped; rule ids are replaced by what the rule is about; the snapshot name by
    "the modelled user". The self-check at the end greps the finished files for all
    of it and exits non-zero on a leak.

HOW THE ORG VERDICT IS DERIVED - and the v1.0 defect this replaces
    v1.0 computed `bounded_by_running_user = not expect_read` for EVERY case. That is
    right only for the FLS-axis read cases. A record-axis case carries `expect_rows`,
    a write/publish case carries `expect_write` - neither has `expect_read`, so all
    of them came out "bounded: true", including the v58 cases whose rationale says
    in so many words that the operation LANDS past the user. And the two clean read
    cases that return a field the user IS entitled to came out "bounded: false" and
    "field_returned_to_unentitled_user: true" - the negative control published as an
    escape. Five wrong verdicts out of 21 (counted by diffing the v1.0 and v1.1
    exports), in the one field readers are told to score against. The derivation
    below is per axis, and the README carries an ERRATA section, because a
    benchmark that changes silently is not a benchmark.

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

VERSION = "1.1"
# Published in corpus.json AND in the README, in the same words, because a benchmark
# whose scoring field changes without saying so is not a benchmark. The v1.0 hashes
# are what CHECKSUMS.md of that version sealed; anyone holding a v1.0 copy can see
# that their copy differs and why.
ERRATA = [
    {
        "fixed_in": "1.1",
        "date": "2026-08-19",
        "field": "org_verdict.bounded_by_running_user",
        "defect": (
            "v1.0 derived this field as NOT expect_read for every case. That is "
            "correct only for the field-level-security read cases. The record-axis "
            "cases observe rows (not a field), the write and publish cases observe "
            "whether the DML landed (not a field), and neither carries expect_read - "
            "so all of them were published as bounded:true, including the v58 cases "
            "whose own rationale says the operation lands past the user. The two "
            "read cases that return a field the user IS entitled to (the negative "
            "control) were published as bounded:false and "
            "field_returned_to_unentitled_user:true - the control mislabelled as an "
            "escape. Five of 21 adjudicated cases therefore carried the wrong value "
            "in the one field readers are told to score against."),
        "affected_case_ids": [
            "record-v58-without-plain", "write-v58-plain-insert",
            "publish-v58-bypasses-create", "field-user-can-see-is-clean",
            "field-id-only-is-clean",
        ],
        "change": (
            "bounded_by_running_user is now derived per axis and each org_verdict "
            "carries `axis` plus the raw observation it was derived from. "
            "Additionally two case ids are renamed: `prec-v58-without-systemmode-"
            "clause` -> `prec-v67-without-systemmode-clause` (it was always an api "
            "67.0 case; the old id read as a claim about v58) and `field-untagged-"
            "escalates-ps502` -> `field-untagged-escalates` (the suffix was one "
            "tool's rule number). label_provenance for oracle-settled cases is "
            "spelled `experiment:oracle` everywhere, and rationale text no longer "
            "carries the exporting project's internal vocabulary. No case source, "
            "API version, or measured outcome changed."),
    },
]

# Line-ending discipline for the published tree. The seal is a sha256 over bytes;
# a Windows checkout with autocrlf=true would rewrite every text file to CRLF and
# every hash would then "fail" for a reader who changed nothing. Declaring eol=lf
# in the export makes the bytes the same on every platform.
_GITATTRIBUTES = (
    "# Published benchmark: every text file is LF so the sha256 seal in CHECKSUMS.md\n"
    "# verifies on any platform. Regenerated by export_public_corpus.py.\n"
    "* text=auto eol=lf\n"
    "*.cls text eol=lf\n"
    "*.json text eol=lf\n"
    "*.md text eol=lf\n"
)

# Sentences naming a third-party engine - or a customer org - are dropped from
# published rationale. Whole sentences, because half a sentence reads as a claim.
_DROP_SENTENCE = re.compile(
    r"(?:^|(?<=[.!?]))[^.!?]*\b(?:sfge|graph engine|appendix ad|technostore)\b[^.!?]*[.!?]\s*",
    re.IGNORECASE)

# Our rule ids, replaced by what each rule is ABOUT, so a rationale that says
# "(so no PS501)" still explains itself to a reader who has never seen our table.
_RULE_NOUN = {
    "PS501": "record-scope finding",
    "PS502": "untagged-field finding",
    "PS503": "write finding",
    "PS504": "honest-unknown finding",
    "PS505": "data-minimisation finding",
    "PS506": "labelled-field finding",
    "PS509": "trigger-cascade finding",
    "PS512": "sanitizer-misuse finding",
    "PS514": "hand-off finding",
}
_RULE_ID = re.compile(r"\bPS5\d\d\b")


def _rule_words(text: str) -> str:
    """Replace each rule id with its noun, with an article that fits where it sits:
    "(so no PS501)" -> "(so no record-scope finding)"; "PS512 depends" at a sentence
    start -> "A sanitizer-misuse finding depends"; "and PS503 applies" -> "and a
    write finding applies"."""
    def one(m: re.Match) -> str:
        noun = _RULE_NOUN.get(m.group(0), "finding")
        before = text[:m.start()]
        if re.search(r"\bno\s+$", before):
            return noun
        article = "an" if noun[0] in "aeiou" else "a"
        if re.search(r"(?:^|[.!?]\s+)$", before):
            article = article.capitalize()
        return f"{article} {noun}"
    return _RULE_ID.sub(one, text)
# The fixture permission snapshot's file name is internal vocabulary too.
_SNAPSHOT = [(re.compile(r"\bin user_minimal\b"), "for the modelled user"),
             (re.compile(r"\buser_minimal\b"), "the modelled user")]
# What the self-check greps the FINISHED files for. Kept next to the substitutions
# so adding one without the other is visibly odd. The rule-id half is
# case-SENSITIVE on purpose: the ERRATA must be allowed to name the retired
# lowercase id `...-ps502` verbatim (an erratum that cannot say what it corrects
# is useless), while every prose use of a rule id is uppercase and still caught.
_INTERNAL = [re.compile(r"sfge|graph engine|technostore|user_minimal", re.IGNORECASE),
             re.compile(r"\bPS5\d\d\b")]


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
    cleaned = _DROP_SENTENCE.sub("", text or "").strip()
    cleaned = _rule_words(cleaned)
    for pat, repl in _SNAPSHOT:
        cleaned = pat.sub(repl, cleaned)
    return _neutralise(re.sub(r"\s+", " ", cleaned))


def _verdict(case: dict) -> dict | None:
    """What the ORG did - the only field an outside analyzer should be scored on.

    One universal key, `bounded_by_running_user`, derived PER AXIS from the shape
    the oracle actually ran, plus the raw observation for that axis so a reader can
    check the derivation rather than trust it:

      read   (FLS axis)        bounded  <=>  NOT (field came back AND user not entitled)
      record (sharing axis)    bounded  <=>  rows the user holds no share on did NOT come back
      write  (object CRUD)     bounded  <=>  the insert / publish did NOT land
    """
    rt = case.get("runtime")
    if not rt:
        return None
    kind = rt.get("kind", "read")
    entitled = bool(rt.get("entitled", False))
    out = {
        "axis": {"read": "field-level security", "record": "record sharing",
                 "write": "object CRUD"}[kind],
        "sharing_declaration": rt.get("sharing") or "none",
        "mode_clause": rt.get("clause"),
    }
    if kind == "read":
        returned = bool(rt.get("expect_read"))
        escaped = returned and not entitled
        out.update({
            "field_returned": returned,
            "user_is_entitled": entitled,
            # The escape is BOTH facts: the data came back AND the user had no right
            # to it. A returned field the user IS entitled to is the negative control
            # working, not an escape - v1.0 published it as one.
            "field_returned_to_unentitled_user": escaped,
            "bounded_by_running_user": not escaped,
        })
    elif kind == "record":
        rows = bool(rt.get("expect_rows"))
        out.update({
            "user_is_entitled": entitled,      # FLS on the field is granted on purpose
            "rows_without_share_returned": rows,
            "bounded_by_running_user": not rows,
        })
    elif kind == "write":
        landed = bool(rt.get("expect_write"))
        src = (rt.get("body") or "") + (case.get("apex") or "")
        out.update({
            "operation": "publish" if "EventBus.publish" in src else "insert",
            "user_is_entitled": False,          # the writer holds no Create at all
            "write_landed_without_permission": landed,
            "bounded_by_running_user": not landed,
        })
    else:                                       # a new kind must be modelled, not guessed
        raise SystemExit(f"[FAIL] unknown runtime kind {kind!r} in {case['id']}")
    return out


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
        "version": VERSION,
        "errata": ERRATA,
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
            "real Salesforce org actually did - not an opinion, and not ours. "
            "org_verdict.axis says WHICH axis the case adjudicates (field-level "
            "security, record sharing, or object CRUD); the raw observation for "
            "that axis is published next to it so the derivation can be checked."),
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

    with open(os.path.join(OUT, ".gitattributes"), "w", encoding="utf-8", newline="\n") as f:
        f.write(_GITATTRIBUTES)

    # Stale case files from a renamed or removed case would otherwise survive in the
    # published tree (and in the seal) forever. Only our own output pattern is touched.
    live = {f"{c['id']}.cls" for c in CASES if c.get("apex")}
    for name in sorted(os.listdir(os.path.join(OUT, "cases"))):
        if name.endswith(".cls") and name not in live:
            os.remove(os.path.join(OUT, "cases", name))
            print(f"     removed stale case file: cases/{name}")

    # The old seal describes the previous export. Drop it before checking, so the
    # walk below cannot pass by reading a stale file instead of the new one.
    sums_path = os.path.join(OUT, "CHECKSUMS.md")
    if os.path.exists(sums_path):
        os.remove(sums_path)

    # Grep the FINISHED FILES, not the in-memory strings. A check that reads what it
    # just wrote catches a path that skipped _neutralise(); a check that re-reads the
    # variable it already sanitised only proves the sanitiser ran where we remembered
    # to call it. Non-zero exit, because a warning nobody reads is not a gate. The
    # hand-written README.md is walked too: it is published, so it is checked.
    branded, internal = [], []
    for root, _dirs, files in os.walk(OUT):
        for name in sorted(files):
            fp = os.path.join(root, name)
            with open(fp, encoding="utf-8") as f:
                text = f.read()
            rel = os.path.relpath(fp, OUT)
            if _BRAND.search(text):
                branded.append(rel)
            if any(p.search(text) for p in _INTERNAL):
                internal.append(rel)
    if branded:
        print("[FAIL] the tool's name leaked into published files: "
              + ", ".join(branded))
        print("       Add the fixture to _RENAME above. The corpus is published with "
              "the tool unnamed (publication rule); a lab identifier "
              "carrying 'blast' is a soft brand plant, which is the same mistake "
              "already corrected once in a launch image.")
        sys.exit(1)
    print("     tool-name leaks in published files: none")
    if internal:
        print("[FAIL] internal vocabulary (engine name, customer org, PS5xx rule id, "
              "fixture snapshot name) leaked into: " + ", ".join(internal))
        sys.exit(1)
    print("     internal-vocabulary leaks in published files: none")

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
        "sha256 of the published corpus and of every case source, so a later version",
        "cannot be quietly substituted and no case can be tuned after the fact without",
        "the hash moving.",
        "",
        "Verify, from this directory (public-benchmark/):",
        "",
        "    grep -E '^    [0-9a-f]{64}  ' CHECKSUMS.md | sed 's/^ *//' | sha256sum -c",
        "",
        "or one file at a time:",
        "",
        "    sha256sum corpus.json                        # Linux / macOS",
        "    Get-FileHash corpus.json -Algorithm SHA256   # Windows",
        "",
        "Every line below is `<sha256>  <path relative to this directory>` - the exact",
        "format `sha256sum -c` reads, so the one-liner needs no path surgery. A Windows",
        "checkout verifies too: the published .gitattributes pins every text file to LF,",
        "and the seal is over LF bytes.",
        "",
        "Corpus:",
        "",
        f"    {sha(corpus)}  corpus.json",
        "",
        "Case sources:",
        "",
    ]
    for name in sorted(os.listdir(cases_dir)):
        lines.append(f"    {sha(os.path.join(cases_dir, name))}  cases/{name}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
