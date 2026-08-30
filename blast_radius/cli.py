"""Agent Blast Radius - one command, any org.

Point it at an authenticated org + an agent, and it pulls the agent config,
Apex/Flow reach, the running user's permissions, the org's compliance labels and
sharing models - all live - and writes the deterministic report.

    python blast_radius/cli.py --agent HealthRecord_Assistant --permission-set HR_Agent_Minimal
    python blast_radius/cli.py --agent My_Agent --running-user svc@acme.com --org acmeOrg

Requires the Salesforce CLI (`sf`) authenticated to the target org. No agent is
invoked; zero Flex Credits.
"""

from __future__ import annotations

import argparse
from datetime import date as _date
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import org_loaders  # noqa: E402
from agent_analyzer import (analyze_agent, expand_agent_graph,  # noqa: E402
                            parse_agent_config)
from agent_metadata_loader import (AgentBundleNotFound,  # noqa: E402
                                   load_agent_config)
from apex_introspect import parse_apex  # noqa: E402
from flow_introspect import parse_flow  # noqa: E402
from permission_resolver import EffectivePermissions  # noqa: E402
import baseline as baseline_mod  # noqa: E402
from report import (aksu_index, aksu_index_line,  # noqa: E402
                    classification_coverage, escalation_gap,
                    render_markdown, resolution_coverage,
                    resolution_coverage_line, analyzer_version, fingerprint)
from report_html import render_html, wrap_document  # noqa: E402
from snapshot_loader import build_snapshot  # noqa: E402


def _sf_retrieve(metadata: list, target_org) -> bool:
    if not metadata:
        return True
    cmd = "sf project retrieve start " + " ".join(f'--metadata "{m}"' for m in metadata)
    if target_org:
        cmd += f" --target-org {target_org}"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    return res.returncode == 0


def _retrieve(agent: str, target_org):
    _sf_retrieve([f"GenAiPlannerBundle:{agent}", "GenAiPlugin"], target_org)


def _retrieve_action_sources(agent, source_root: str, target_org):
    """Pull ONLY the Apex classes / Flows this agent's actions actually invoke.

    Without this the tool is useless against an org whose source is not already
    checked out locally: the action targets resolve, but there is no .cls to
    read, so every action becomes an honest 'source not found' (PS504). We
    deliberately do not retrieve the whole org - just the reachable targets."""
    want = []
    for a in agent.actions:
        if a.target_type == "apex":
            if not os.path.exists(os.path.join(source_root, "classes", a.target + ".cls")):
                want.append(f"ApexClass:{a.target}")
        elif a.target_type == "flow":
            if not os.path.exists(os.path.join(source_root, "flows",
                                               a.target + ".flow-meta.xml")):
                want.append(f"Flow:{a.target}")
    if want:
        print(f"retrieving action sources: {', '.join(want)}")
        _sf_retrieve(want, target_org)


def _reached_objects(agent, source_root: str, backend: str = "auto",
                     read_only: bool = False):
    """Objects the agent's actions touch. `read_only=True` returns only objects
    the code READS - the ones where "reaches N records" is a meaningful record
    count. A create/insert target is a write, not a read of N records, so it is
    excluded from record-reach to keep that headline honest."""
    objects = set()
    for action in agent.actions:
        if action.target_type == "apex":
            path = os.path.join(source_root, "classes", action.target + ".cls")
            if os.path.exists(path):
                for o in parse_apex(path, source_root, backend=backend).operations:
                    if o.sobject and (not read_only or o.operation == "read"):
                        objects.add(o.sobject)
        elif action.target_type == "flow":
            path = os.path.join(source_root, "flows", action.target + ".flow-meta.xml")
            if os.path.exists(path):
                for a in parse_flow(path).accesses:
                    if a.sobject and (not read_only or a.operation == "read"):
                        objects.add(a.sobject)
    return objects


def _reached_fields(agent, source_root: str, backend: str = "auto"):
    """Field paths the agent reads, spelled exactly as the analyzer and its findings
    spell them (report._qualify): a relationship field keeps its own path
    (`BillToContact.Email`), a direct field gets `Object.Field`.

    Needed BEFORE classification runs, because a relationship path is the only clue
    that the agent traverses into another object - and that object's compliance labels
    have to be loaded for PS506 to see them."""
    from report import _qualify
    fields = set()
    for action in agent.actions:
        if action.target_type == "apex":
            path = os.path.join(source_root, "classes", action.target + ".cls")
            if os.path.exists(path):
                for o in parse_apex(path, source_root, backend=backend).operations:
                    if o.sobject:
                        for f in o.fields:
                            fields.add(_qualify(o.sobject, f))
        elif action.target_type == "flow":
            path = os.path.join(source_root, "flows", action.target + ".flow-meta.xml")
            if os.path.exists(path):
                for a in parse_flow(path).accesses:
                    if a.sobject:
                        for f in a.fields:
                            fields.add(_qualify(a.sobject, f))
    return fields


def _record_modes(agent, source_root: str, backend: str = "auto"):
    """{object: 'user'|'system'} for the objects the agent READS.

    This is what makes the record-reach headline honest: a read that is bounded by
    the running user has no record escalation, so the org's record count says
    nothing about the agent's reach and must not be presented as one.

    'user' requires BOTH axes to be enforced (enforces_sharing AND enforces_fls) -
    i.e. a genuine user-mode read. Enforcing only one is NOT bounded:
      * `with sharing` at v<=66 gives (sharing=True, fls=False) - the query filters
        by sharing rules but BYPASSES CRUD/FLS, so it can read an object the user
        has no permission on at all. That is a real escalation ceiling.
      * v67+ / WITH USER_MODE gives (True, True) - genuinely bounded.
    Any undetermined axis, or any single system-mode read, makes the object
    'system' (worst case wins)."""
    modes: dict = {}

    def _note(obj, enforces_sharing, enforces_fls):
        bounded = (enforces_sharing is True) and (enforces_fls is True)
        this = "user" if bounded else "system"
        if modes.get(obj) == "system" or this == "system":
            modes[obj] = "system"
        else:
            modes[obj] = "user"

    for action in agent.actions:
        if action.target_type == "apex":
            path = os.path.join(source_root, "classes", action.target + ".cls")
            if os.path.exists(path):
                for o in parse_apex(path, source_root, backend=backend).operations:
                    if o.sobject and o.operation == "read":
                        _note(o.sobject, o.resolved.enforces_sharing, o.resolved.enforces_fls)
        elif action.target_type == "flow":
            path = os.path.join(source_root, "flows", action.target + ".flow-meta.xml")
            if os.path.exists(path):
                fr = parse_flow(path)
                for a in fr.accesses:
                    if a.sobject and a.operation == "read":
                        _note(a.sobject, fr.enforces_sharing, fr.enforces_fls)
    return modes


def main():
    ap = argparse.ArgumentParser(description="Compute an Agentforce agent's blast radius.")
    ap.add_argument("--agent", default=None, help="GenAiPlannerBundle API name")
    ap.add_argument("--agent-script", default=None, metavar="PATH",
                    help="path to an Agent Script .agent authoring bundle file; reads the "
                         "action targets (apex://, flow://) straight from the file - no "
                         "Tooling API lookup. Alternative to --agent.")
    ap.add_argument("--org", default=None, help="sf target org alias/username (default org if omitted)")
    ap.add_argument("--running-user", default=None, help="username to model as the running user")
    ap.add_argument("--permission-set", default=None, help="model the running user as this permission set")
    ap.add_argument("--source-root", default=os.path.join("force-app", "main", "default"))
    ap.add_argument("--channel", default="agent")
    ap.add_argument("--out", default=os.path.join("blast_radius", "report"))
    ap.add_argument("--no-retrieve", action="store_true", help="skip retrieving agent metadata")
    ap.add_argument("--include-counts", action="store_true",
                    help="run live COUNT() queries for a real record-reach headline "
                         "(user sees N vs agent reaches M records); never fabricates numbers")
    ap.add_argument("--apex-backend", choices=["auto", "ast", "regex"], default="auto",
                    help="Apex reach extractor: 'auto' uses the real AST (apex-parser) "
                         "and falls back to regex; 'ast' forces it; 'regex' forces the fallback")
    ap.add_argument("--fail-on", choices=["ERROR", "WARN", "none"], default="none",
                    help="exit non-zero if any finding is at or above this severity (for CI gates)")
    ap.add_argument("--require-ast", action="store_true",
                    help="refuse the regex fallback: exit non-zero if any Apex action "
                         "could not be read from a real parse tree. The fallback cannot "
                         "trace the Authority Path, so its findings are weaker evidence - "
                         "use this for a production gate")
    # A report with no date cannot be told from a report made in March, and the
    # reader has no way to ask. It is an INPUT the operator states, never a clock
    # read at render time: a wall-clock stamp would make two runs of the same
    # analysis differ byte for byte and take the determinism proof with it. It is
    # also deliberately OUTSIDE the fingerprint - the same analysis captured on two
    # dates is the same analysis, and a caption must not change the seal.
    ap.add_argument("--snapshot-date", metavar="YYYY-MM-DD",
                    help="date the org data was captured, printed on the report. "
                         "Omitted, the report says 'deterministic' as before")
    ap.add_argument("--baseline", metavar="PATH",
                    help="compare this run against a recorded baseline and exit "
                         "non-zero if ANY of the four numbers rose. This is the "
                         "gate a team can keep: --fail-on asks 'is it perfect', "
                         "which a legacy org fails forever until someone deletes "
                         "the gate; --baseline asks 'is it worse than last time'")
    ap.add_argument("--write-baseline", metavar="PATH",
                    help="record this run's four numbers as the line not to cross. "
                         "Run it once to adopt the current state, then again "
                         "whenever an improvement should be held")
    ap.add_argument("--no-org-health", action="store_true",
                    help="skip the whole-org health section (API-version debt, god-mode "
                         "grants, permissive OWD) appended to the foot of the report")
    args = ap.parse_args()

    if not args.running_user and not args.permission_set:
        ap.error("provide --running-user or --permission-set")
    if not args.agent and not args.agent_script:
        ap.error("provide --agent (metadata) or --agent-script (.agent file)")

    root = args.source_root
    # Two very different identity models, and the report must not blur them:
    #   --running-user   real effective access (profile + every assigned permission
    #                    set, INCLUDING permission set groups via their computed
    #                    aggregate - verified in E8, see snapshot_loader).
    #   --permission-set a HYPOTHETICAL user holding exactly this one permission set
    #                    and nothing else. Useful for "what would a minimally-granted
    #                    agent user see", but it is a model, not a person: it has no
    #                    profile, no other permission sets, no group.
    ru_label = (args.running_user or
                f"(hypothetical grant model - permission set: {args.permission_set})")

    script_ir = None
    if args.agent_script:
        # Agent Script path: the action targets are IN the file. No retrieve,
        # no Tooling API lookup. The IR also carries the data->prompt chain
        # (@outputs -> @variables -> {! }) that PS52x traces.
        import agentscript_loader
        print(f"reading Agent Script: {args.agent_script}")
        script_ir = agentscript_loader.extract(args.agent_script)
        cfg = agentscript_loader.to_analyzer_config(script_ir, running_user=ru_label,
                                                    channel=args.channel)
        for scheme, name, line in agentscript_loader.reached_targets(script_ir):
            print(f"  action target: {scheme}://{name}  (line {line})")
    else:
        if not args.no_retrieve:
            print("retrieving agent metadata ...")
            _retrieve(args.agent, args.org)
        print("resolving agent config ...")
        resolver = org_loaders.function_resolver(args.org)
        try:
            cfg = load_agent_config(root, args.agent, running_user=ru_label,
                                    channel=args.channel, resolver=resolver)
        except AgentBundleNotFound as e:
            # The message names what was expected, what is present, and how to
            # ask the org for the right name. A traceback here would say "this
            # tool is broken" when the truth is "that is not the name the org
            # uses" - and this is the first thing a stranger hits.
            print()
            print(str(e))
            print()
            sys.exit(2)
    agent = parse_agent_config(cfg)

    # Flatten any agent-to-agent delegation FIRST, so everything after this point
    # (source retrieve, reach, record modes, classification, counts, analysis) sees
    # the whole graph's actions rather than one opaque "calls another agent" box.
    def _sub_agent_cfg(name):
        try:
            return load_agent_config(root, name, running_user=ru_label,
                                     channel=args.channel, resolver=resolver)
        except Exception:
            return None                    # unresolved -> stays a PS515 unknown

    expanded, graph_edges = expand_agent_graph(
        agent, root, loader=_sub_agent_cfg if not args.agent_script else None)
    if graph_edges:
        agent.actions = expanded
        merged = sum(1 for _c, _e, ok, _n in graph_edges if ok)
        print(f"agent graph: {len(graph_edges)} delegation(s), {merged} expanded "
              f"-> {len(expanded)} action(s) total")

    # The action targets are known now; pull just their source if it isn't local.
    if not args.no_retrieve:
        _retrieve_action_sources(agent, root, args.org)

    import apex_ast
    if args.apex_backend in ("auto", "ast"):
        if apex_ast.ast_available():
            backend_note = "ast (real parse tree)" if args.apex_backend == "ast" \
                else "ast (auto; regex fallback ready)"
        else:
            backend_note = "regex (AST backend unavailable: node/apex-parser not found)"
    else:
        backend_note = "regex (forced)"
    print(f"apex extractor: {backend_note}")

    objects = _reached_objects(agent, root, args.apex_backend)
    print(f"objects reached: {sorted(objects) or '(none - opaque actions only)'}")

    print("loading classifications, sharing models, permissions ...")
    # Pass the reached field paths too: a relationship path (BillToContact.Email)
    # is what tells the loader to resolve that relationship and pull the TARGET
    # object's compliance labels - without it, PS506 silently misses every cross-object
    # personal field the agent reads.
    classification, visible = org_loaders.classification(
        objects, args.org, fields=_reached_fields(agent, root, args.apex_backend))
    # Which reached fields are FORMULAS. Their inputs are not resolved, so the user's
    # FLS on the formula does not bound what its value carries - the one channel a v67
    # user-mode read does not close. PS516 reports it as an unresolved reach.
    calculated = org_loaders.calculated_fields(objects, args.org)
    sharing = org_loaders.sharing(objects, args.org)
    triggers = org_loaders.active_triggers(objects, args.org)
    if args.permission_set:
        snapshot = org_loaders.snapshot_from_permset(args.permission_set, objects, args.org)
    else:
        snapshot = build_snapshot(args.running_user, sobjects=list(objects), channel=args.channel)
    perms = EffectivePermissions(snapshot)

    summaries = analyze_agent(agent, root, perms, classification, sharing, triggers,
                              apex_backend=args.apex_backend, script_ir=script_ir,
                              graph_edges=graph_edges, calculated=calculated)
    coverage = classification_coverage(summaries, classification, visible)

    # An evidence-grade gate. The regex fallback cannot trace the Authority Path,
    # so it holds every field at worst case: the same class reads WARN under the AST
    # and ERROR under regex. A production gate may reasonably refuse the weaker read
    # rather than act on it.
    if args.require_ast:
        weak = sorted(s.name for s in summaries
                      if s.kind == "apex" and s.backend not in (None, "ast"))
        if weak:
            print(f"FAILED --require-ast: {len(weak)} action(s) fell back to the regex "
                  f"extractor ({', '.join(weak)}). Their findings are weaker evidence. "
                  f"Install Node and run `npm install --prefix blast_radius`.")
            sys.exit(2)

    counts = None
    if args.include_counts:
        print("counting records (live COUNT queries) ...")
        # Record-reach is a READ concept: "how many records can the code read
        # beyond the user". A create/insert target is not a read of N records, so
        # count only the objects the code actually READS - honest by construction.
        read_objects = _reached_objects(agent, root, args.apex_backend, read_only=True)
        # Per-object record-axis mode: a user-mode (sharing-enforced) read is bounded
        # by the running user, so the org's record count is NOT the agent's reach.
        modes = _record_modes(agent, root, args.apex_backend)
        counts = org_loaders.record_counts(read_objects, sharing, perms, args.org, modes=modes)

    # org health: whole-org signals (API-version debt, god-mode grants, OWD) that
    # don't concern THIS agent but a reviewer of the org should see. Live mode only
    # (needs Tooling/Data API); skipped for --agent-script / --no-retrieve local runs.
    org_health_html = org_health_md = ""
    if not args.no_org_health and not args.agent_script:
        try:
            import org_health
            print("gathering org health (whole-org signals) ...")
            health = org_health.gather_org_health(args.org)
            # tie the org-wide posture back to THIS agent: its escalation gap and
            # how much of its OWN action code is the pre-v67 root cause
            gap_fields, _ = escalation_gap(summaries)
            apex_actions = [s for s in summaries if s.api_version is not None]
            legacy_actions = [s for s in apex_actions if s.api_version < 67]
            # The footer must not contradict the Index band. A gap of 0 with
            # unresolved reach is "0 proven, N unresolved", never "stays within
            # its user" - spec section 4.3, and the reason PS504 exists.
            ctx = dict(gap_n=len(gap_fields), agent_legacy=len(legacy_actions),
                       agent_apex_total=len(apex_actions),
                       unresolved=aksu_index(summaries)["unresolved"])
            org_health_html = org_health.render_health_section(health, agent.name, **ctx)
            org_health_md = org_health.render_health_md(health, agent.name, **ctx)
        except Exception as e:
            print(f"  (org health skipped: {e})")

    stamp = "deterministic"
    if args.snapshot_date:
        # Validate rather than print whatever arrived. A malformed date on a
        # security report is worse than no date: it reads as precision.
        try:
            y, m, d = (int(x) for x in args.snapshot_date.split("-"))
            _date(y, m, d)
            stamp = f"measured {args.snapshot_date}"
        except (ValueError, TypeError):
            print(f"  [!] --snapshot-date '{args.snapshot_date}' is not YYYY-MM-DD; "
                  "the report will not carry a date")

    md = render_markdown(agent.name, agent.running_user, agent.channel, summaries,
                         generated=stamp,
                         coverage=coverage, counts=counts, org_health_md=org_health_md)
    html = render_html(agent.name, agent.running_user, agent.channel, summaries,
                       generated=stamp,
                       coverage=coverage, counts=counts, org_health=org_health_html)
    with open(args.out + ".md", "w", encoding="utf-8") as f:
        f.write(md)
    # The .html on disk is a standalone file (opened in a browser, printed to
    # PDF), so it gets the full-document wrapper - charset + print rules. The
    # fragment render_html returns stays a fragment for embedders.
    with open(args.out + ".html", "w", encoding="utf-8") as f:
        f.write(wrap_document(html, f"Agent Blast Radius - {agent.name}"))

    gap, gdpr = escalation_gap(summaries)
    print("\n" + "=" * 60)
    print(f"AGENT: {agent.name}   RUNNING USER: {agent.running_user}")
    # ASCII form on purpose: the Windows console is cp1252.
    print(aksu_index_line(aksu_index(summaries), ascii_only=True).upper())
    print(f"ESCALATION GAP: {len(gap)} field(s), {len(gdpr)} regulated")
    if counts:
        from report import record_reach
        rr = record_reach(counts)
        if rr and rr["has_measured_gap"]:
            print(f"RECORD REACH: system-mode reads could reach UP TO "
                  f"{rr['upper_bound_total']} records, user sees {rr['user_total']} "
                  f"(upper-bound gap {rr['gap_total']}; predicates/LIMIT not resolved)")
        elif rr and rr["bounded"] and not rr["unknown"]:
            print("RECORD REACH: every RESOLVED read enforces sharing - bounded by the "
                  "running user on those reads (no proven record escalation)")
    findings = [f for s in summaries for f in s.findings]
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for sev in ("ERROR", "WARN", "INFO"):
        n = sum(1 for f in findings if f.severity == sev)
        if n:
            print(f"  {sev}: {n}")
    print(f"reports written: {args.out}.md , {args.out}.html")
    print("=" * 60)

    ix = aksu_index(summaries)
    rc = resolution_coverage(summaries)
    print(resolution_coverage_line(rc, ascii_only=True).upper())

    # The baseline gate runs BEFORE --fail-on. A team adopting this on a legacy
    # org wants "did today make it worse", and would never see that answer if an
    # absolute threshold had already exited on findings that were there yesterday.
    if args.baseline or args.write_baseline:
        av = analyzer_version()
        fp = fingerprint(agent.name, agent.running_user, agent.channel, summaries)
        if args.baseline:
            base = baseline_mod.load(args.baseline)
            if base is None:
                print()
                print(f"No baseline at {args.baseline} - nothing to compare against.")
                print("Write one with --write-baseline to start the ratchet.")
            else:
                v = baseline_mod.compare(base, ix, rc, agent=agent.name,
                                         running_user=agent.running_user, analyzer=av)
                print()
                print(baseline_mod.render(v, base, ix, rc))
                if not v.ok:
                    sys.exit(1)
        if args.write_baseline:
            baseline_mod.write(args.write_baseline, ix, rc, agent=agent.name,
                               running_user=agent.running_user, analyzer=av,
                               fingerprint=fp)
            print()
            print(f"baseline written: {args.write_baseline}")

    if args.fail_on != "none":
        threshold = order[args.fail_on]
        blocking = [f for f in findings if order.get(f.severity, 9) <= threshold]
        if blocking:
            print(f"FAILED: {len(blocking)} finding(s) at or above {args.fail_on}.")
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except org_loaders.OrgQueryError as e:
        # This tool reads a live org; when the org does not answer there is
        # nothing to analyse, and the honest end is a failed READ - not a
        # traceback (which reads as "the analyzer is broken") and not a report
        # (a report built on a missing read would be a false clean, the one
        # outcome this project treats as worse than no answer at all).
        print(f"\n[FAIL] The org did not answer. No report was written.\n"
              f"       {e}\n"
              f"       Check: network, VPN/proxy, and `sf org display "
              f"--target-org <alias>`.", file=sys.stderr)
        sys.exit(2)
