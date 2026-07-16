"""Org-wide API-version census — a companion view to Agent Blast Radius.

Blast Radius answers a *scoped* question: "what can THIS agent reach, and does
its code escalate past the running user?" — so it only inspects the handful of
Apex classes the agent actually invokes.

This census answers a different, org-hygiene question: across EVERY Apex class
and trigger in the org, how many still run on a pre-v67 API version? A class
written before API v67 defaults to **system mode** — its SOQL and DML silently
bypass the running user's sharing and field-level security unless the code adds
an explicit ``WITH USER_MODE`` / ``as user`` clause. So the share of pre-v67
code is the single best org-level risk signal, and exactly the number a
security review or an "is it worth migrating?" business case needs.

Run standalone:

    python blast_radius/org_census.py --org TechnoStore --out census
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Dict, List

from org_loaders import _sf
from report_html import _CSS, _esc

# API version at/after which the platform runs Apex DB ops in user mode by
# default (secure-by-default). Below this, system mode is the default.
SECURE_DEFAULT = 67


@dataclass
class TypeCensus:
    label: str                      # e.g. "Apex classes"
    total: int                      # all records incl. managed packages
    local_total: int                # customer-owned (no namespace) — editable
    local_legacy: int               # local records below SECURE_DEFAULT
    managed_total: int              # installed-package records (read-only)
    versions: Dict[float, int] = field(default_factory=dict)  # local, by version

    @property
    def local_safe(self) -> int:
        return self.local_total - self.local_legacy


def _api(rec) -> float:
    try:
        return round(float(rec.get("ApiVersion") or 0), 1)
    except (TypeError, ValueError):
        return 0.0


def census_type(label: str, sobject: str, target_org) -> TypeCensus:
    """Query one metadata type and split local (editable) vs managed."""
    rows = _sf(f"SELECT ApiVersion, NamespacePrefix FROM {sobject}",
               tooling=True, target_org=target_org)
    local = [r for r in rows if not r.get("NamespacePrefix")]
    managed = [r for r in rows if r.get("NamespacePrefix")]
    versions: Dict[float, int] = {}
    legacy = 0
    for r in local:
        v = _api(r)
        versions[v] = versions.get(v, 0) + 1
        if v < SECURE_DEFAULT:
            legacy += 1
    return TypeCensus(label, len(rows), len(local), legacy, len(managed),
                      dict(sorted(versions.items())))


def run_census(target_org) -> List[TypeCensus]:
    """Census every Apex-bearing metadata type that carries per-file api semantics."""
    return [
        census_type("Apex classes", "ApexClass", target_org),
        census_type("Apex triggers", "ApexTrigger", target_org),
    ]


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

_HIST_CSS = """
<style>
  .abr .census-hero{display:flex; gap:20px; align-items:stretch; flex-wrap:wrap;
    background:var(--surface); border:1px solid var(--line); border-radius:16px;
    padding:24px; margin:20px 0}
  .abr .census-hero.err{border-color:color-mix(in srgb,var(--warn) 55%,var(--line));
    background:color-mix(in srgb,var(--warn) 5%,var(--surface))}
  .abr .census-hero.ok{border-color:color-mix(in srgb,var(--proof,#1a9d6b) 45%,var(--line))}
  .abr .hist{margin:6px 0 4px}
  .abr .hist .row{display:flex; align-items:center; gap:12px; margin:5px 0;
    font-size:13px; font-variant-numeric:tabular-nums}
  .abr .hist .vlab{font-family:var(--mono); width:52px; color:var(--ink); text-align:right}
  .abr .hist .track{flex:1; height:15px; border-radius:6px; overflow:hidden;
    background:color-mix(in srgb,var(--line) 45%,transparent)}
  .abr .hist .fill{height:100%; border-radius:6px}
  .abr .hist .fill.legacy{background:var(--warn)}
  .abr .hist .fill.safe{background:var(--proof,#1a9d6b)}
  .abr .hist .cnt{width:44px; color:var(--muted)}
  .abr .censnote{font-size:13px; color:var(--muted); margin:10px 0 0;
    border-top:1px solid var(--line); padding-top:10px}
  .abr .censnote b{color:var(--ink)}
</style>"""


def _bar(pct_safe: float, has_safe: bool, has_legacy: bool) -> str:
    return ('<div class="pbar">'
            + (f'<i class="safe" style="width:{pct_safe:g}%"></i>' if has_safe else '')
            + (f'<i class="legacy" style="width:{100 - pct_safe:g}%"></i>' if has_legacy else '')
            + '</div>')


def _histogram(versions: Dict[float, int]) -> str:
    if not versions:
        return ""
    mx = max(versions.values())
    rows = ['<div class="hist">']
    for v, n in sorted(versions.items()):
        w = round(100 * n / mx)
        cls = "safe" if v >= SECURE_DEFAULT else "legacy"
        vlab = f"v{v:g}" if v >= 1 else "none"
        rows.append(f'<div class="row"><span class="vlab">{vlab}</span>'
                    f'<span class="track"><i class="fill {cls}" style="width:{w}%"></i></span>'
                    f'<span class="cnt">{n}</span></div>')
    rows.append('</div>')
    return "\n".join(rows)


def render_html(org: str, censuses: List[TypeCensus], generated: str) -> str:
    local_total = sum(c.local_total for c in censuses)
    local_legacy = sum(c.local_legacy for c in censuses)
    local_safe = local_total - local_legacy
    managed_total = sum(c.managed_total for c in censuses)
    grand_total = sum(c.total for c in censuses)
    pct_legacy = round(100 * local_legacy / local_total) if local_total else 0
    pct_safe = 100 - pct_legacy
    level = "err" if local_legacy else "ok"

    p: List[str] = [f'<title>API-Version Census — {_esc(org)}</title>', _CSS, _HIST_CSS,
                    '<div class="abr">']
    p.append(
        '<div class="bar">'
        f'<span><b>ORG</b> {_esc(org)}</span>'
        f'<span><b>SCOPE</b> every Apex class &amp; trigger</span>'
        f'<span><b>GENERATED</b> {_esc(generated)}</span></div>')
    p.append('<p class="eyebrow">Org-wide API-version census</p>')
    p.append(f'<h1>{_esc(org)}</h1>')
    p.append('<p class="sub">A companion to the agent blast-radius report: not what one '
             'agent can reach, but how much of the whole org&rsquo;s Apex still runs on a '
             'pre-v67 (system-mode-by-default) API version.</p>')

    # headline hero: your own editable code, split safe vs legacy
    p.append(f'<div class="census-hero {level}">')
    p.append(
        '<div class="ptotal" style="border-right:1px solid var(--line);'
        'padding-right:22px;display:flex;flex-direction:column;justify-content:center;'
        'align-items:center;text-align:center;min-width:120px">'
        f'<b style="font-size:46px;line-height:1;font-weight:800">{local_total}</b>'
        '<span style="font-size:11px;letter-spacing:.05em;text-transform:uppercase;'
        'color:var(--muted);margin-top:6px">your own<br>Apex files</span></div>')
    p.append('<div style="flex:1;min-width:240px;display:flex;flex-direction:column;'
             'justify-content:center;gap:12px">')
    p.append('<div class="psplit" style="display:flex;gap:12px;flex-wrap:wrap">'
             f'<div class="pseg safe" style="flex:1;min-width:150px"><b>{local_safe}</b>'
             '<span>at API v67+ — secure-by-default (user mode)</span></div>'
             f'<div class="pseg legacy" style="flex:1;min-width:150px"><b>{local_legacy}</b>'
             '<span>pre-v67 — system-mode default, sharing/FLS bypassed unless the code '
             'opts in</span></div></div>')
    p.append(_bar(pct_safe, local_safe > 0, local_legacy > 0))
    p.append(f'<div style="font-size:13px;color:var(--muted)"><b style="color:var(--ink)">'
             f'{pct_legacy}%</b> of your own Apex is still pre-v67.</div>')
    p.append('</div></div>')

    # per-type breakdown + histograms
    for c in censuses:
        if c.local_total == 0 and c.managed_total == 0:
            continue
        p.append(f'<p class="eyebrow">{_esc(c.label)}</p>')
        p.append('<div class="stats">')
        for n, k, flag in [
            (c.local_total, "Your own (editable)", False),
            (c.local_legacy, "pre-v67 (legacy)", c.local_legacy > 0),
            (c.local_safe, "v67+ (secure)", False),
            (c.managed_total, "Managed (read-only)", False),
        ]:
            p.append(f'<div class="stat{" flag" if flag else ""}">'
                     f'<div class="n">{_esc(n)}</div><div class="k">{_esc(k)}</div></div>')
        p.append('</div>')
        hist = _histogram(c.versions)
        if hist:
            p.append(hist)

    # why it matters + managed note
    p.append('<p class="censnote"><b>Why this matters:</b> a class or trigger written before '
             'API v67 defaults to <b>system mode</b> — its SOQL and DML bypass the running '
             'user&rsquo;s sharing and field-level security unless the code adds an explicit '
             '<code>WITH USER_MODE</code> / <code>as user</code> clause. Raising the file&rsquo;s '
             'apiVersion flips that default, which is why legacy code tends to stay legacy: the '
             'risk is invisible and permanent until each file is reviewed. The blast-radius '
             'report proves which of these actually reach an agent; this census sizes the '
             'whole backlog.</p>')
    if managed_total:
        p.append(f'<p class="censnote">The {managed_total} managed (installed-package) file(s) '
                 'are excluded from the headline — you cannot edit them — but they still run in '
                 'the org, so a pre-v67 managed package can escalate exactly the same way. '
                 'Treat them as vendor risk, not backlog.</p>')

    p.append(f'<div class="foot">Grand total across all namespaces: {grand_total} Apex file(s). '
             'Static Tooling-API census — zero credits, no records read.</div>')
    p.append('</div>')
    return "\n".join(p)


def render_md(org: str, censuses: List[TypeCensus], generated: str) -> str:
    local_total = sum(c.local_total for c in censuses)
    local_legacy = sum(c.local_legacy for c in censuses)
    pct = round(100 * local_legacy / local_total) if local_total else 0
    out = [f"# API-Version Census — {org}", "",
           f"_Generated {generated}. Scope: every Apex class & trigger in the org._", "",
           f"**{local_legacy} of {local_total} of your own Apex files ({pct}%) are pre-v67** "
           "(system-mode by default).", ""]
    for c in censuses:
        if not (c.local_total or c.managed_total):
            continue
        out.append(f"## {c.label}")
        out.append(f"- Your own (editable): **{c.local_total}** — "
                   f"pre-v67 **{c.local_legacy}**, v67+ **{c.local_safe}**")
        out.append(f"- Managed (read-only): {c.managed_total}")
        if c.versions:
            dist = ", ".join(f"v{v:g}: {n}" for v, n in sorted(c.versions.items()))
            out.append(f"- By version (your own): {dist}")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Org-wide Apex API-version census.")
    ap.add_argument("--org", default=None, help="sf target org alias (default org if omitted)")
    ap.add_argument("--out", default="census", help="output basename (writes .html and .md)")
    ap.add_argument("--generated", default="static census",
                    help="label stamped as the generation time")
    ap.add_argument("--fail-on-legacy", type=int, default=None, metavar="PCT",
                    help="exit non-zero if the pre-v67 share of your own Apex is >= PCT")
    args = ap.parse_args(argv)

    censuses = run_census(args.org)
    local_total = sum(c.local_total for c in censuses)
    local_legacy = sum(c.local_legacy for c in censuses)
    pct = round(100 * local_legacy / local_total) if local_total else 0

    html = render_html(args.org or "(default org)", censuses, args.generated)
    md = render_md(args.org or "(default org)", censuses, args.generated)
    with open(f"{args.out}.html", "w", encoding="utf-8") as f:
        f.write(html)
    with open(f"{args.out}.md", "w", encoding="utf-8") as f:
        f.write(md)

    print("=" * 60)
    print(f"ORG API-VERSION CENSUS: {args.org or '(default org)'}")
    for c in censuses:
        print(f"  {c.label}: {c.local_total} yours "
              f"({c.local_legacy} pre-v67, {c.local_safe} v67+), {c.managed_total} managed")
    print(f"  YOUR OWN APEX: {local_legacy}/{local_total} pre-v67 ({pct}%)")
    print(f"reports written: {args.out}.md , {args.out}.html")
    print("=" * 60)

    if args.fail_on_legacy is not None and pct >= args.fail_on_legacy:
        print(f"FAILED: {pct}% pre-v67 >= threshold {args.fail_on_legacy}%.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
