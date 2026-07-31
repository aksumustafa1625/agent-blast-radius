"""Deterministic report renderer + Escalation Gap headline (Milestone 4).

Turns authority findings into the artifact: one number (the Escalation Gap -
fields the agent's code can reach beyond the running user, with the GDPR subset
called out), a reach summary, and the findings grouped by severity. The report
is fingerprint-bound (a sha256 over the analysed inputs) so it is byte
reproducible and STALE-guarded - regenerate when the fingerprint changes.

No wall-clock is read here (determinism): the caller passes `generated`.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

import apex_ast

_SEV_ORDER = {"ERROR": 0, "WARN": 1, "INFO": 2}

# How a record-reach gap arises - kept distinct because they are very different
# claims (see spec v2 §7.2): CRUD is deterministic from metadata; sharing is
# data-dependent and only measurable by running as the user.
_CAUSE_LABEL = {
    "crud": "no object permission (CRUD)",
    "sharing": "record-level sharing",
    None: "—",
}

# Within a severity, surface the highest-value rule first. PS506 (a GDPR/PII-
# labelled field escaping past the running user's FLS into the model) is the
# single most decision-relevant finding for a DPO, so it leads the section; the
# rest keep a stable alphabetical order. Lower number = earlier.
_RULE_ORDER = {"PS506": 0, "PS505": 1, "PS510": 2, "PS501": 3}


def finding_sort_key(af) -> tuple:
    """Stable, deterministic order for (action, finding) pairs: by severity, then
    by rule importance (PS506 first), then rule name, then location."""
    f = af[1]
    return (_SEV_ORDER.get(f.severity, 9), _RULE_ORDER.get(f.rule, 5), f.rule, f.where)


@dataclass
class ActionSummary:
    name: str
    kind: str                       # apex | flow | standard
    api_version: Optional[float]
    system_mode: bool               # runs in system context (escalation-capable)
    objects: List[str]
    fields: List[str]
    findings: List = field(default_factory=list)
    # Which extractor produced this reach. It belongs in the report AND in the
    # fingerprint: the AST backend traces the Authority Path, the regex fallback
    # cannot, so the SAME class can be WARN under one and ERROR under the other.
    # A fingerprint that ignores it would certify two different verdicts as the
    # same analysis. See fingerprint().
    backend: Optional[str] = None


def summarize_flow(reach, findings, name=None) -> ActionSummary:
    objs = sorted({a.sobject for a in reach.accesses if a.sobject})
    flds = sorted({f"{a.sobject}.{fl}" for a in reach.accesses if a.sobject for fl in a.fields})
    return ActionSummary(name or reach.name, "flow", None, reach.runs_in_system_context, objs, flds, findings)


def _qualify(sobject: str, fl: str) -> str:
    """Spell a field the SAME way the analyzer's findings do, so the reachable set
    and the escalation gap subtract cleanly. A relationship field already carries
    its own path (`BillToContact.Email`) and must NOT be re-prefixed with the root
    object; a direct field gets `Object.Field`. Mismatching this is what made the
    concentric-circle counts fail to reconcile (outer != inner + gap)."""
    return fl if "." in fl else f"{sobject}.{fl}"


def summarize_apex(reach, findings, name=None) -> ActionSummary:
    objs = sorted({o.sobject for o in reach.operations if o.sobject})
    flds = sorted({_qualify(o.sobject, fl)
                   for o in reach.operations if o.sobject for fl in o.fields})
    system = any(o.resolved.is_escalation_capable for o in reach.operations if o.operation == "read")
    return ActionSummary(name or reach.class_name, "apex", reach.api_version, system,
                         objs, flds, findings, backend=getattr(reach, "backend", None))


def summarize_prompt(reach, findings, name=None) -> ActionSummary:
    """A GenAiPromptTemplate action: user-mode record merge (no apiVersion, not
    system-mode), reaching the objects/fields the active version pulls."""
    objs = sorted(set(reach.objects))
    flds = sorted(set(reach.fields))
    return ActionSummary(name or reach.name, "prompt", None, False, objs, flds, findings)


def _field_of(where: str) -> str:
    return where.split("-> ")[-1].strip()


def escalation_gap(actions: List[ActionSummary]) -> tuple[set, set]:
    """(fields reachable beyond the user, GDPR-labelled subset)."""
    gap, gdpr = set(), set()
    for a in actions:
        for f in a.findings:
            if f.rule in ("PS502", "PS506"):
                gap.add(_field_of(f.where))
                if f.rule == "PS506":
                    gdpr.add(_field_of(f.where))
    return gap, gdpr


def aksu_index(actions: List[ActionSummary]) -> dict:
    """The public metric (docs/AKSU_INDEX_SPEC.md §3): escalation_gap() split by
    proof level. The circles keep the union — the spec's `gap` IS P ∪ B — but the
    quoted number may not mix them, because severity is the tool's proof claim:
    a WARN inside the proven count would present a boundary we could not prove
    as if we had proven it. GDPR counts only within proven, for the same reason.
    `unresolved` counts PS504 findings — reach we could not determine at all —
    and the spec forbids quoting `proven` without it: an unknown never reads
    as clean."""
    proven, gdpr, boundary = set(), set(), set()
    unresolved = 0
    for a in actions:
        for f in a.findings:
            if f.rule in ("PS502", "PS506"):
                (proven if f.severity == "ERROR" else boundary).add(_field_of(f.where))
                if f.rule == "PS506" and f.severity == "ERROR":
                    gdpr.add(_field_of(f.where))
            elif f.rule == "PS504":
                unresolved += 1
    # A field proven in ANY action is proven — most-severe-wins, the same
    # discipline the analyzer's own dedup applies.
    boundary -= proven
    return {"proven": proven, "gdpr": gdpr, "boundary": boundary,
            "unresolved": unresolved}


def aksu_index_line(ix: dict, ascii_only: bool = False) -> str:
    """Canonical form (spec §1). Always all four numbers — quoting `proven`
    alone while unresolved > 0 is defined by the spec as a violation, so no
    caller gets a shorter form to misquote. ascii_only is for the Windows
    console (cp1252); the md/html files are utf-8 and keep the canonical dot."""
    sep = " / " if ascii_only else " · "
    return (f"Aksu Index: {len(ix['proven'])} proven ({len(ix['gdpr'])} GDPR)"
            f"{sep}{len(ix['boundary'])} unproven boundaries"
            f"{sep}{ix['unresolved']} unresolved")


_STD_FIELDS = {"Id", "Name", "OwnerId", "IsDeleted", "CreatedDate", "CreatedById",
               "LastModifiedDate", "LastModifiedById", "SystemModstamp"}


def classification_coverage(actions: List[ActionSummary], classification: dict,
                            visible_by_object: Optional[dict]) -> dict:
    """How much classification visibility we actually had over the fields the
    agent reaches. `not_visible` are blind spots (FLS-gated), so a '0 GDPR'
    result with not_visible > 0 must not be read as 'clean'."""
    reached = {f for a in actions for f in a.fields}
    classified = visible_unclassified = not_visible = 0
    for full in reached:
        obj, _, short = full.partition(".")
        if short in _STD_FIELDS:
            continue
        if full in classification or short in classification:
            classified += 1
        elif visible_by_object and short in (visible_by_object.get(obj) or set()):
            visible_unclassified += 1
        else:
            not_visible += 1
    total = classified + visible_unclassified + not_visible
    pct = round(100 * (classified + visible_unclassified) / total) if total else 100
    return {"classified": classified, "visible_unclassified": visible_unclassified,
            "not_visible": not_visible, "total": total, "coverage_pct": pct}


def record_reach(counts: Optional[dict]) -> Optional[dict]:
    """Normalize per-object counts into an honest record-reach summary.

    Two rules keep this from overstating (both were real defects once):
      * A **user-mode** read enforces sharing, so the agent is bounded by the
        running user by construction: gap 0, and the object's record count is NOT
        the agent's reach. Such objects are reported as `bounded` and never
        contribute to the escalation aggregate.
      * For a **system-mode** read, the object's `org_total` is an UPPER BOUND
        only - query predicates and LIMIT are not resolved - so the aggregate is
        `upper_bound_total`, never "the agent reaches N records".

    Only MEASURED system-mode rows (user_visible known) enter the gap aggregate;
    sharing-dependent visibility stays `unknown`. Returns None if no counts."""
    if not counts:
        return None
    measured, unknown, bounded = [], [], []
    upper_bound_total = user_total = gap_total = 0
    have_bound = False
    for obj, c in sorted(counts.items()):
        ot = c.get("org_total")
        uv = c.get("user_visible")
        row = {"object": obj, "org_total": ot, "user_visible": uv,
               "gap": c.get("gap"), "note": c.get("note", ""),
               "cause": c.get("cause"), "mode": c.get("mode", "system")}
        if row["mode"] == "user":
            bounded.append(row)                     # no escalation by construction
            continue
        if ot is not None:
            have_bound = True
            upper_bound_total += ot
        if uv is not None and ot is not None:
            user_total += uv
            gap_total += max(ot - uv, 0)
            measured.append(row)
        else:
            unknown.append(row)
    return {"rows": measured + unknown + bounded,
            "measured": measured, "unknown": unknown, "bounded": bounded,
            "upper_bound_total": upper_bound_total if have_bound else None,
            "user_total": user_total, "gap_total": gap_total,
            "has_measured_gap": bool(measured)}


# The code that DECIDES a finding. Rendering is deliberately absent: it changes the
# document, not the analysis, and verify_deterministic.py sha256s the whole document
# anyway.
_ANALYSIS_SOURCES = (
    "apex_introspect.py",        # the precedence law + regex extraction
    "ast_extract.js",            # the parse-tree extraction
    "authority_analyzer.py",     # the rules
    "flow_introspect.py",
    "genai_prompt_introspect.py",
    "prompt_flow_analyzer.py",
    "permission_resolver.py",
    "agentscript_loader.py",
    "snapshot_loader.py",
)


@lru_cache(maxsize=1)
def analyzer_version() -> str:
    """A hash of the analyzer's OWN source, not a hand-maintained version string.

    A number someone has to remember to bump defeats the point: change a rule, forget
    the bump, and the fingerprint still claims the two runs were the same analysis -
    which is the exact lie it exists to prevent. Hashing the code cannot be forgotten.

    It over-invalidates: editing a comment in authority_analyzer.py changes the
    fingerprint although no verdict moved. That direction is the safe one. Two
    identical analyses showing different fingerprints is a false alarm; two DIFFERENT
    analyses sharing one is a false claim of reproducibility, and this project treats
    those as very different sins."""
    h = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for name in _ANALYSIS_SOURCES:          # fixed order - not os.listdir
        h.update(name.encode("utf-8"))
        try:
            with open(os.path.join(here, name), "rb") as f:
                h.update(f.read())
        except OSError:
            # A missing analysis module is itself a different analyzer, so it must
            # change the hash rather than be skipped silently.
            h.update(b"<missing>")
    return h.hexdigest()[:12]


def fingerprint(agent: str, running_user: str, channel: Optional[str],
                actions: List[ActionSummary], coverage: Optional[dict] = None) -> str:
    payload = {
        # The tool is part of its own result. Without these, an analyzer or parser
        # change that moves a verdict produces the SAME fingerprint as the run before
        # it - the fingerprint would be certifying reproducibility it cannot see.
        "analyzer": analyzer_version(),
        "parser": apex_ast.parser_version() or "none",
        # WHAT THE ANALYSIS IDENTITY COULD SEE is an input to the verdict, so it binds
        # too. FieldDefinition is FLS-gated (E4 measured exactly this), so a narrow
        # analysis identity sees fewer labels, produces fewer PS506s, and reports a
        # CLEANER agent. Without this, two runs whose only difference was who ran them
        # could share a fingerprint and disagree about "0 GDPR" - the precise lie the
        # fingerprint exists to prevent, and the twin of the analyzer-hash gap. Caught
        # by an external reviewer; our own E4 had predicted the mechanism.
        "coverage": (None if not coverage else
                     {k: coverage.get(k) for k in
                      ("classified", "visible_unclassified", "not_visible", "total")}),
        "agent": agent, "user": running_user, "channel": channel,
        "actions": [
            {
                "name": a.name, "kind": a.kind, "api": a.api_version,
                "system": a.system_mode,
                # The extractor is part of the analysis, not a detail: the regex
                # fallback cannot trace the Authority Path, so it reports the same
                # class at a different severity. Two runs that disagree on ERROR vs
                # WARN must not share a fingerprint.
                "backend": a.backend,
                "objects": sorted(a.objects), "fields": sorted(a.fields),
                # severity is the tool's confidence claim - a verdict that moves
                # from WARN to ERROR is a different result, so it binds too.
                "findings": sorted(f"{f.rule}:{f.severity}:{f.where}" for f in a.findings),
            }
            for a in sorted(actions, key=lambda x: x.name)
        ],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def render_markdown(agent: str, running_user: str, channel: Optional[str],
                    actions: List[ActionSummary], generated: str = "deterministic",
                    coverage: Optional[dict] = None,
                    counts: Optional[dict] = None,
                    org_health_md: str = "") -> str:
    fp = fingerprint(agent, running_user, channel, actions, coverage)
    gap, gdpr = escalation_gap(actions)
    ix = aksu_index(actions)
    reach = record_reach(counts)

    objects = sorted({o for a in actions for o in a.objects})
    fields = sorted({f for a in actions for f in a.fields})
    system_actions = [a for a in actions if a.system_mode]
    legacy = [a for a in actions if a.api_version is not None and a.api_version < 67]

    all_findings = [(a, f) for a in actions for f in a.findings]
    all_findings.sort(key=finding_sort_key)

    L: List[str] = []
    L.append("```")
    L.append(f"AGENT BLAST RADIUS REPORT - {agent}")
    L.append(f"Running user: {running_user}   (channel: {channel or 'n/a'})")
    L.append(f"Config fingerprint: {fp}      Generated: {generated}")
    L.append("=" * 64)
    L.append("")
    L.append(aksu_index_line(ix))
    if not ix["proven"] and ix["unresolved"]:
        # Spec §4.3 in the report's own voice: 0 proven with unresolved reach
        # is "0 proven, U unresolved" — never "clean".
        L.append("  (0 proven with unresolved reach is NOT clean - unknown never becomes clean)")
    L.append(f"ESCALATION GAP ......... {len(gap)} fields  /  {len(gdpr)} GDPR-labelled"
             + ("   <==" if gap else ""))
    L.append("")
    L.append("REACH SUMMARY")
    L.append(f"  Actions analysed ....... {len(actions)}")
    L.append(f"  Objects reachable ...... {len(objects)}")
    L.append(f"  Fields reachable ....... {len(fields)}")
    L.append(f"  System-mode actions .... {len(system_actions)} / {len(actions)}")
    L.append(f"  Legacy API (< v67) ..... {len(legacy)} / {len(actions)}")
    if coverage:
        L.append("")
        L.append("CLASSIFICATION COVERAGE")
        L.append(f"  Reachable fields ....... {coverage['total']}")
        L.append(f"  Classified (GDPR/PII) .. {coverage['classified']}")
        L.append(f"  Visible, unclassified .. {coverage['visible_unclassified']}")
        L.append(f"  Not visible to analyzer  {coverage['not_visible']}"
                 + ("   <== blind spot" if coverage['not_visible'] else ""))
        L.append(f"  Coverage ............... {coverage['coverage_pct']}%")
    L.append("```")
    L.append("")

    if coverage and coverage["not_visible"]:
        L.append(f"> _Classification coverage {coverage['coverage_pct']}%: "
                 f"{coverage['not_visible']} reachable field(s) are not visible to the "
                 f"analysis identity — a `0 GDPR` result is not proof of safety for those._")
        L.append("")

    if reach:
        L.append("### Record reach (live COUNT — upper bound)")
        L.append("")
        if reach["has_measured_gap"]:
            causes = {r.get("cause") for r in reach["measured"] if r.get("gap")}
            qual = ""
            if causes == {"crud"}:
                qual = " The whole measured gap is a CRUD escalation — the running user has " \
                       "no object permission at all, so this is deterministic, not sharing-dependent."
            L.append(f"> **The agent's system-mode reads could reach up to "
                     f"{reach['upper_bound_total']} records where the running user sees "
                     f"{reach['user_total']} — an upper-bound record gap of "
                     f"{reach['gap_total']}.** _(measured system-mode objects only)_{qual}")
            L.append("")
        elif reach["bounded"] and not reach["unknown"]:
            L.append("> **Every read the agent performs enforces sharing, so the agent is "
                     "bounded by the running user — there is no record escalation.**")
            L.append("")
        L.append("| Object | Read mode | Records in org | User sees | Gap (upper bound) | Cause |")
        L.append("| --- | --- | ---: | ---: | ---: | --- |")
        for r in reach["rows"]:
            ot = "?" if r["org_total"] is None else str(r["org_total"])
            if r["mode"] == "user":
                mode, uv, gp = "user", "_= agent (sharing enforced)_", "0"
            else:
                mode = "system"
                if r["user_visible"] is None:
                    uv, gp = f"_n/a — {r['note']}_", "—"
                else:
                    uv = str(r["user_visible"])
                    gp = f"≤ {r['gap']}" if r["gap"] else "0"
            L.append(f"| `{r['object']}` | {mode} | {ot} | {uv} | {gp} | "
                     f"{_CAUSE_LABEL[r.get('cause')]} |")
        L.append("")
        L.append("> _`Records in org` is a live `COUNT()` of the whole object run as the "
                 "analysis identity. **It is an upper bound, not the agent's result**: query "
                 "predicates and `LIMIT` are not resolved statically. It is an escalation "
                 "ceiling only for **system-mode** reads — a **user-mode** read enforces "
                 "sharing, so the agent is bounded by the running user and the gap is 0 by "
                 "construction. **CRUD** = the user has no object permission at all "
                 "(deterministic); **sharing** = the user can read the object but record-level "
                 "sharing may hide rows, which is data-dependent and shown as `n/a` — never "
                 "estimated._")
        L.append("")

    if gap:
        L.append(f"> **{len(gap)} fields can be reached beyond the running user"
                 f"{f' - {len(gdpr)} of them GDPR-labelled' if gdpr else ''}.**")
        L.append("")

    by_sev = {"ERROR": [], "WARN": [], "INFO": []}
    for a, f in all_findings:
        by_sev.setdefault(f.severity, []).append((a, f))

    for sev in ("ERROR", "WARN", "INFO"):
        items = by_sev.get(sev) or []
        if not items:
            continue
        L.append(f"## {sev} - {len(items)} finding(s)")
        L.append("")
        for a, f in items:
            L.append(f"- **[{f.rule}] {f.where}**")
            L.append(f"  - {f.message}")
            L.append(f"  - _Why:_ {f.why}")
            L.append(f"  - _Fix:_ {f.fix}")
        L.append("")

    if not all_findings:
        L.append("No authority findings. All analysed actions enforce user mode "
                 "end-to-end for the fields and objects they reach.")
        L.append("")

    if org_health_md:
        L.append(org_health_md)
        L.append("")

    L.append("---")
    L.append("Produced by static analysis. No agent was invoked. 0 Flex Credits.")
    # The seal names the TOOL, not just the inputs. A verdict is only reproducible
    # against the tool that made it: change a rule and the same input yields a
    # different verdict, so an auditor told to "regenerate this" with a newer analyzer
    # and handed a matching fingerprint would be reading a false guarantee. The
    # analyzer digest is a hash of the rule/extractor source, so it cannot be forgotten
    # the way a hand-bumped version number can.
    L.append(f"Bound to fingerprint `{fp}`, which seals both the INPUTS (agent config, "
             "the analysed Apex/Flow, the permission snapshot, and what the analysis "
             "identity could see) and the TOOL that produced this verdict "
             f"(analyzer `{analyzer_version()}`, parser "
             f"`{apex_ast.parser_version() or 'none - regex fallback'}`; each analysed "
             "class's own apiVersion is bound per action, since it decides the "
             "verdict). Regenerate if any of these change.")
    # SAY WHAT THE SEAL DOES NOT COVER, on the same page as the seal.
    #
    # An external reviewer put it exactly right: the distinction was "in your head,
    # not in the report". A reader who sees a live COUNT table above a line saying
    # "bound to fingerprint" will reasonably assume the counts are sealed too. They
    # are not - the fingerprint binds the STATIC analysis (and the analyzer's own
    # source), while a COUNT is a measurement of the org at a moment. Two runs a day
    # apart can share a fingerprint and show different counts, and that is correct
    # behaviour, not drift - but only if the document says so.
    if counts:
        L.append("")
        L.append("_The fingerprint seals the **static analysis** — the agent's config, the "
                 "analysed Apex/Flow, the permission snapshot, and the analyzer itself. It "
                 "does **not** cover the live `COUNT()` figures above: those are a "
                 "measurement of the org at the moment of the run. Two runs sharing a "
                 "fingerprint can legitimately show different counts._")
    return "\n".join(L)


def render_svg(agent: str, user_field_count: int, agent_field_count: int,
               gdpr_gap: int) -> str:
    """Two concentric circles: inner = user reach, outer = agent reach, red ring."""
    gap = max(agent_field_count - user_field_count, 0)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="360" height="360" viewBox="0 0 360 360">'
        f'<circle cx="180" cy="180" r="150" fill="#e5484d" fill-opacity="0.15" '
        f'stroke="#e5484d" stroke-width="2"/>'
        f'<circle cx="180" cy="180" r="80" fill="#3b82f6" fill-opacity="0.25" '
        f'stroke="#3b82f6" stroke-width="2"/>'
        f'<text x="180" y="176" text-anchor="middle" font-family="sans-serif" '
        f'font-size="16" fill="#3b82f6">user sees</text>'
        f'<text x="180" y="196" text-anchor="middle" font-family="sans-serif" '
        f'font-size="16" fill="#3b82f6">{user_field_count} fields</text>'
        f'<text x="180" y="70" text-anchor="middle" font-family="sans-serif" '
        f'font-size="15" fill="#e5484d">agent reaches {agent_field_count}</text>'
        f'<text x="180" y="330" text-anchor="middle" font-family="sans-serif" '
        f'font-size="15" fill="#e5484d">Escalation Gap: {gap} ({gdpr_gap} GDPR)</text>'
        f'</svg>'
    )
