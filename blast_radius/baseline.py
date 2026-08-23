# -*- coding: utf-8 -*-
"""Baseline gate: turn the Aksu Index into something a team can keep in CI.

WHY A RATCHET AND NOT A THRESHOLD
`--fail-on ERROR` asks "is this perfect?". On a legacy org the answer is no on
day one and no on every build after, so the team deletes the gate - the failure
mode CLAUDE.md section 9.9 already names: "A CI gate nobody can silence gets
switched off." A ratchet asks the question a team can actually act on: "is this
worse than last time?" It passes at 6 and fails at 7, so the gate survives and
the number can only travel downwards.

WHY THE GATE IS ON ALL FOUR NUMBERS
Gating on P alone is gameable, and gameable in the direction that matters. Make a
query dynamic and its finding moves from P to U: the headline drops, the gate
goes green, and the org is LESS understood than before, not safer. So every
bucket is ratcheted - a rise in U fails exactly like a rise in P. This is the CI
form of the specification's own rule that P may never be quoted alone.

WHY THE ANALYZER VERSION IS RECORDED
Spec section 4.6: "A number is comparable only under the same tool version." Two
numbers produced by different analyzers are not a trend, they are two different
measurements. When the analyzer digest changes the gate says so and asks for a
re-baseline rather than silently comparing across versions.
"""
from __future__ import annotations

import io
import json
import os
from typing import Optional

SCHEMA = "aksuindex-baseline/1"

# Every bucket is ratcheted. The order is the order they are reported in.
BUCKETS = ("proven", "gdpr", "boundary", "unresolved")

# Coverage ratchets the other way: it may not FALL. Buckets rising and coverage
# falling are the same event seen from two sides, and a team that makes code
# less analysable to quiet the gate trips this one even if the buckets hold.

_LABEL = {
    "proven": "proven",
    "gdpr": "regulated (within proven)",
    "boundary": "unproven boundaries",
    "unresolved": "unresolved",
    "coverage": "resolution coverage %",
}


def counts(ix: dict) -> dict:
    """The four numbers as plain ints. aksu_index() returns sets for three of
    them; a baseline stores counts, because the gate is about the measurement
    and not about which particular field moved."""
    return {
        "proven": len(ix["proven"]),
        "gdpr": len(ix["gdpr"]),
        "boundary": len(ix["boundary"]),
        "unresolved": int(ix["unresolved"]),
    }


def write(path: str, ix: dict, rc: dict, *, agent: str, running_user: str,
          analyzer: str, fingerprint: str) -> dict:
    """Record the current measurement as the line not to cross.

    The agent and running user are stored because the Index describes exactly
    one (agent, running user) pair (spec section 2). Comparing a baseline taken
    for one pair against a run for another would be meaningless, so the gate
    refuses it rather than reporting a difference that is really a mismatch.
    """
    payload = {
        "schema": SCHEMA,
        "agent": agent,
        "running_user": running_user,
        "analyzer": analyzer,
        "fingerprint": fingerprint,
        "index": counts(ix),
        "coverage": {"resolved": int(rc["resolved"]), "total": int(rc["total"]),
                     "pct": int(rc["pct"])},
    }
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return payload


def load(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Verdict:
    """The result of comparing a run against a baseline.

    `ok` is the gate. `blocking` is why. `mismatch` and `stale_analyzer` are
    conditions under which a comparison should not be made at all - reported
    rather than silently resolved either way.
    """

    def __init__(self):
        self.ok = True
        self.blocking: list = []      # (bucket, was, now)
        self.improved: list = []      # (bucket, was, now)
        self.mismatch: Optional[str] = None
        self.stale_analyzer = False


def compare(base: dict, ix: dict, rc: dict, *, agent: str, running_user: str,
            analyzer: str) -> Verdict:
    v = Verdict()
    now = counts(ix)

    if base.get("agent") != agent or base.get("running_user") != running_user:
        # Not a regression - a different measurement. Saying "worse" here would
        # be a fabricated comparison, which is the one thing this tool may not do.
        v.mismatch = (
            f"baseline is for ({base.get('agent')!r}, {base.get('running_user')!r}) "
            f"but this run is ({agent!r}, {running_user!r}). "
            "One Index describes one agent and one running user (spec section 2)."
        )
        v.ok = False
        return v

    if base.get("analyzer") != analyzer:
        # Spec section 4.6. The run still gets compared - a team mid-upgrade still
        # wants to see movement - but the verdict says the comparison is across
        # tool versions, so a rise may be the analyzer resolving MORE rather than
        # the code getting worse.
        v.stale_analyzer = True

    was = base.get("index", {})
    for b in BUCKETS:
        old, new = int(was.get(b, 0)), now[b]
        if new > old:
            v.blocking.append((b, old, new))
        elif new < old:
            v.improved.append((b, old, new))
    old_cov = int((base.get("coverage") or {}).get("pct", 100))
    if int(rc["pct"]) < old_cov:
        v.blocking.append(("coverage", old_cov, int(rc["pct"])))
    elif int(rc["pct"]) > old_cov:
        v.improved.append(("coverage", old_cov, int(rc["pct"])))

    if v.blocking:
        v.ok = False
    return v


def render(v: Verdict, base: dict, ix: dict, rc: dict) -> str:
    """Console output. ASCII only - the Windows console is cp1252."""
    L = []
    if v.mismatch:
        L.append("BASELINE MISMATCH: " + v.mismatch)
        return "\n".join(L)

    was, now = base.get("index", {}), counts(ix)
    L.append("AKSU INDEX vs BASELINE")
    for b in BUCKETS:
        old, new = int(was.get(b, 0)), now[b]
        arrow = "  " if new == old else ("UP" if new > old else "down")
        L.append("  {:<26} {:>3} -> {:<3} {}".format(_LABEL[b], old, new, arrow))
    oc, nc = int((base.get("coverage") or {}).get("pct", 100)), int(rc["pct"])
    L.append("  {:<26} {:>3} -> {:<3} {}".format(
        _LABEL["coverage"], oc, nc, "  " if nc == oc else ("DOWN" if nc < oc else "up")))

    if v.stale_analyzer:
        L.append("")
        L.append("  NOTE: the analyzer changed since this baseline was written.")
        L.append("  A number is comparable only under the same tool version")
        L.append("  (spec 4.6), so a rise here may be the analyzer resolving more")
        L.append("  rather than the code getting worse. Re-baseline once reviewed.")

    L.append("")
    if v.blocking:
        L.append("FAILED: the Aksu Index got worse.")
        for b, old, new in v.blocking:
            verb = "fell" if b == "coverage" else "rose"
            L.append("  {} {} {} -> {}".format(_LABEL[b], verb, old, new))
        L.append("")
        L.append("  Every bucket is ratcheted, not just proven. A finding that")
        L.append("  moves from proven to unresolved is not an improvement: the")
        L.append("  reach stopped being understood, which is why unresolved")
        L.append("  fails the same way proven does - and why coverage may not fall.")
        L.append("  Fix it, or re-baseline deliberately with --write-baseline.")
    elif v.improved:
        L.append("PASSED: no bucket rose.")
        for b, old, new in v.improved:
            verb = "rose" if b == "coverage" else "fell"
            L.append("  {} {} {} -> {}".format(_LABEL[b], verb, old, new))
        L.append("  Re-baseline with --write-baseline to hold the new line.")
    else:
        L.append("PASSED: unchanged.")
    return "\n".join(L)
