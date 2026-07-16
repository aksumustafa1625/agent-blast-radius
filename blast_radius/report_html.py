"""Colorful, theme-aware HTML report with the two-circle Escalation Gap visual.

Renders the same ActionSummaries as report.render_markdown into a self-contained
HTML fragment (inline <style> + content, no <html>/<head>/<body>) suitable for
publishing as an Artifact or printing to PDF from the browser.

The centerpiece is two concentric circles: the inner (blue) is what the running
user can see, the outer (red) is what the agent's code can reach; the red ring
between them is the Escalation Gap.
"""

from __future__ import annotations

import html
import math
from typing import List

from report import (ActionSummary, escalation_gap, fingerprint, record_reach,
                    finding_sort_key, _CAUSE_LABEL)

_SEV = {"ERROR": "error", "WARN": "warn", "INFO": "info"}

_CSS = """
<style>
  .abr { --bg:#f5f8fa; --surface:#ffffff; --ink:#0f1720; --muted:#5c6b7a;
    --line:#e3e9ef; --accent:#0e8f9c; --user:#3b6fe0; --gap:#e5484d;
    --error:#d93a3f; --warn:#b5720a; --info:#64748b; --proof:#1a9d6b;
    --mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    color:var(--ink); background:var(--bg); font-family:var(--sans);
    line-height:1.55; max-width:900px; margin:0 auto; padding:32px 22px 64px;
    -webkit-font-smoothing:antialiased; }
  @media (prefers-color-scheme:dark){ .abr{
    --bg:#0b1016; --surface:#141d26; --ink:#e6edf3; --muted:#8b9aa8;
    --line:#223041; --accent:#22b8cf; --user:#6aa0ff; --gap:#ff6b72;
    --error:#ff6169; --warn:#e6a12b; --info:#8b9aa8; --proof:#2dd4a0; } }
  :root[data-theme="dark"] .abr{
    --bg:#0b1016; --surface:#141d26; --ink:#e6edf3; --muted:#8b9aa8;
    --line:#223041; --accent:#22b8cf; --user:#6aa0ff; --gap:#ff6b72;
    --error:#ff6169; --warn:#e6a12b; --info:#8b9aa8; --proof:#2dd4a0; }
  :root[data-theme="light"] .abr{
    --bg:#f5f8fa; --surface:#ffffff; --ink:#0f1720; --muted:#5c6b7a;
    --line:#e3e9ef; --accent:#0e8f9c; --user:#3b6fe0; --gap:#e5484d;
    --error:#d93a3f; --warn:#b5720a; --info:#64748b; --proof:#1a9d6b; }
  .abr *{box-sizing:border-box}
  .abr .bar{font-family:var(--mono); font-size:12.5px; color:var(--muted);
    border:1px solid var(--line); border-radius:8px; background:var(--surface);
    padding:12px 16px; display:flex; flex-wrap:wrap; gap:4px 22px; align-items:baseline}
  .abr .bar b{color:var(--ink); font-weight:600}
  .abr .eyebrow{font-family:var(--mono); text-transform:uppercase;
    letter-spacing:.14em; font-size:11px; color:var(--accent); margin:26px 0 6px}
  .abr h1{font-family:var(--mono); font-size:23px; letter-spacing:-.01em;
    font-weight:650; margin:6px 0 2px; text-wrap:balance}
  .abr .sub{color:var(--muted); font-size:14px; margin:0}
  .abr .hero{display:grid; grid-template-columns:1.1fr .9fr; gap:26px;
    align-items:center; background:var(--surface); border:1px solid var(--line);
    border-radius:16px; padding:26px; margin:22px 0}
  @media(max-width:640px){.abr .hero{grid-template-columns:1fr}}
  .abr .gapnum{font-family:var(--mono); font-size:64px; font-weight:700;
    line-height:1; color:var(--gap); font-variant-numeric:tabular-nums}
  .abr .gaplabel{font-size:14px; color:var(--muted); margin-top:6px; max-width:34ch}
  .abr .gaplabel b{color:var(--ink)}
  .abr svg text{font-family:var(--mono)}
  .abr .c-outer-label{fill:var(--gap)}
  .abr .c-inner-label{fill:var(--user)}
  .abr .c-gap-label{fill:var(--gap)}
  .abr .c-num{font-weight:600; font-size:18px; letter-spacing:.01em}
  .abr .c-big{font-weight:700; font-size:38px; letter-spacing:.01em}
  .abr .c-cap{font-size:10px; letter-spacing:.16em}
  .abr .legend{display:flex; gap:18px; flex-wrap:wrap; font-size:12px;
    color:var(--muted); margin-top:2px}
  .abr .legend span{display:inline-flex; align-items:center; gap:7px}
  .abr .dot{width:11px; height:11px; border-radius:50%; display:inline-block}
  .abr .stats{display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
    gap:12px; margin:8px 0 30px}
  .abr .stat{background:var(--surface); border:1px solid var(--line);
    border-radius:11px; padding:14px 16px}
  .abr .stat .n{font-family:var(--mono); font-size:24px; font-weight:650;
    font-variant-numeric:tabular-nums}
  .abr .stat .k{font-size:11.5px; color:var(--muted); text-transform:uppercase;
    letter-spacing:.08em; margin-top:2px}
  .abr .stat.flag .n{color:var(--gap)}
  .abr h2{font-family:var(--mono); font-size:13px; text-transform:uppercase;
    letter-spacing:.1em; color:var(--muted); margin:26px 0 12px;
    display:flex; align-items:center; gap:9px}
  .abr h2 .count{color:var(--ink)}
  .abr .find{border:1px solid var(--line); border-left-width:4px;
    border-radius:10px; background:var(--surface); padding:15px 17px; margin:10px 0}
  .abr .find.error{border-left-color:var(--error)}
  .abr .find.warn{border-left-color:var(--warn)}
  .abr .find.info{border-left-color:var(--info)}
  .abr .find .top{display:flex; align-items:center; gap:10px; flex-wrap:wrap;
    margin-bottom:6px}
  .abr .rule{font-family:var(--mono); font-size:11.5px; font-weight:650;
    padding:2px 8px; border-radius:6px; letter-spacing:.03em}
  .abr .find.error .rule{background:color-mix(in srgb,var(--error) 15%,transparent); color:var(--error)}
  .abr .find.warn .rule{background:color-mix(in srgb,var(--warn) 16%,transparent); color:var(--warn)}
  .abr .find.info .rule{background:color-mix(in srgb,var(--info) 16%,transparent); color:var(--info)}
  .abr .where{font-family:var(--mono); font-size:13px; color:var(--ink); font-weight:600}
  .abr .msg{font-size:14px; margin:4px 0}
  .abr .meta{font-size:13px; color:var(--muted); margin:3px 0}
  .abr .meta b{color:var(--ink); font-weight:600}
  .abr .foot{font-family:var(--mono); font-size:11.5px; color:var(--muted);
    border-top:1px solid var(--line); margin-top:32px; padding-top:14px}
  .abr .clean{background:color-mix(in srgb,var(--user) 9%,transparent);
    border:1px solid var(--line); border-radius:10px; padding:14px 16px;
    font-size:14px; color:var(--ink)}
  .abr .recwrap{overflow-x:auto; margin:6px 0 8px}
  .abr table.rec{width:100%; border-collapse:collapse; font-size:13.5px;
    font-variant-numeric:tabular-nums}
  .abr table.rec th,.abr table.rec td{padding:9px 12px; text-align:right;
    border-bottom:1px solid var(--line)}
  .abr table.rec th:first-child,.abr table.rec td:first-child{text-align:left;
    font-family:var(--mono)}
  .abr table.rec th{font-size:11px; text-transform:uppercase; letter-spacing:.07em;
    color:var(--muted); font-weight:600}
  .abr table.rec td.gap{color:var(--gap); font-weight:650}
  .abr table.rec td.na{color:var(--muted); font-style:italic; text-align:right}
  .abr .recbar{display:flex; height:14px; border-radius:7px; overflow:hidden;
    border:1px solid var(--line); background:var(--surface); min-width:120px}
  .abr .recbar .u{background:var(--user)} .abr .recbar .g{background:var(--gap)}

  /* plain-language stakeholder summary */
  .abr .plain{border:1px solid var(--line); border-radius:14px; padding:20px 22px;
    margin:20px 0 6px; background:var(--surface)}
  .abr .plain .vhead{display:flex; align-items:center; gap:11px; margin-bottom:10px}
  .abr .plain .badge{font-family:var(--mono); font-size:11.5px; font-weight:650;
    letter-spacing:.04em; padding:4px 11px; border-radius:999px; white-space:nowrap}
  .abr .plain.ok .badge{background:color-mix(in srgb,var(--user) 16%,transparent); color:var(--user)}
  .abr .plain.warn .badge{background:color-mix(in srgb,var(--warn) 18%,transparent); color:var(--warn)}
  .abr .plain.err .badge{background:color-mix(in srgb,var(--error) 16%,transparent); color:var(--error)}
  .abr .plain.ok{border-left:5px solid var(--user)}
  .abr .plain.warn{border-left:5px solid var(--warn)}
  .abr .plain.err{border-left:5px solid var(--error)}
  .abr .plain .vhead h3{margin:0; font-size:16.5px; font-family:var(--sans);
    font-weight:650; text-wrap:balance}
  .abr .plain p{font-size:14.5px; margin:0 0 9px; color:var(--ink)}
  .abr .plain p:last-child{margin-bottom:0}
  .abr .plain b{color:var(--ink)}
  .abr .plain .sub2{font-size:12.5px; color:var(--muted); font-style:italic}
  .abr .plain ul.pl{margin:2px 0 8px; padding-left:20px}
  .abr .plain ul.pl li{font-size:14px; margin-bottom:5px}

  /* remediation checklist */
  .abr .remed{background:var(--surface); border:1px solid var(--line);
    border-radius:12px; padding:6px 4px; margin:4px 0 8px}
  .abr .remed .ritem{display:flex; gap:12px; padding:12px 16px;
    border-bottom:1px solid var(--line)}
  .abr .remed .ritem:last-child{border-bottom:none}
  .abr .remed .box{flex:0 0 auto; width:18px; height:18px; border-radius:5px;
    border:2px solid var(--muted); margin-top:1px}
  .abr .remed .ritem.err .box{border-color:var(--error)}
  .abr .remed .ritem.warn .box{border-color:var(--warn)}
  .abr .remed .rbody{flex:1}
  .abr .remed .rrule{font-family:var(--mono); font-size:11px; font-weight:650;
    letter-spacing:.03em; margin-right:7px}
  .abr .remed .ritem.err .rrule{color:var(--error)}
  .abr .remed .ritem.warn .rrule{color:var(--warn)}
  .abr .remed .rwhere{font-family:var(--mono); font-size:12.5px; color:var(--ink); font-weight:600}
  .abr .remed .rfix{font-size:13.5px; margin-top:4px; color:var(--ink)}
  .abr .remed .rfix b{color:var(--muted); font-weight:600; font-family:var(--mono);
    font-size:11px; letter-spacing:.06em; text-transform:uppercase; margin-right:6px}

  /* API-version posture */
  .abr .posture{background:var(--surface); border:1px solid var(--line);
    border-radius:12px; padding:18px 18px 16px; margin:4px 0 8px}
  .abr .posture.err{border-color:color-mix(in srgb,var(--warn) 55%,var(--line));
    background:color-mix(in srgb,var(--warn) 5%,var(--surface))}
  .abr .posture.ok{border-color:color-mix(in srgb,var(--proof) 45%,var(--line))}
  /* prominent headline: total + split */
  .abr .ptop{display:flex; align-items:stretch; gap:20px; margin-bottom:14px;
    flex-wrap:wrap}
  .abr .ptotal{display:flex; flex-direction:column; justify-content:center;
    align-items:center; text-align:center; padding:6px 18px 6px 2px;
    border-right:1px solid var(--line); min-width:96px}
  .abr .ptotal b{font-size:40px; line-height:1; color:var(--ink); font-weight:800;
    font-variant-numeric:tabular-nums}
  .abr .ptotal span{font-size:11px; letter-spacing:.05em; text-transform:uppercase;
    color:var(--muted); margin-top:6px}
  .abr .psplit{display:flex; flex:1; gap:12px; flex-wrap:wrap; min-width:200px}
  .abr .pseg{flex:1; min-width:150px; border-radius:10px; padding:11px 13px;
    border:1px solid var(--line)}
  .abr .pseg b{font-size:26px; line-height:1; font-variant-numeric:tabular-nums;
    display:block; margin-bottom:3px}
  .abr .pseg span{font-size:12px; color:var(--muted); display:block; line-height:1.35}
  .abr .pseg.safe{background:color-mix(in srgb,var(--proof) 9%,transparent);
    border-color:color-mix(in srgb,var(--proof) 30%,var(--line))}
  .abr .pseg.safe b{color:var(--proof)}
  .abr .pseg.legacy{background:color-mix(in srgb,var(--warn) 11%,transparent);
    border-color:color-mix(in srgb,var(--warn) 40%,var(--line))}
  .abr .pseg.legacy b{color:var(--warn)}
  .abr .pbar{display:flex; height:14px; border-radius:8px; overflow:hidden;
    border:1px solid var(--line); margin:2px 0 12px}
  .abr .pbar .safe{background:var(--proof)} .abr .pbar .legacy{background:var(--warn)}
  .abr .pbar .unk{background:var(--line)}
  .abr .posture .legrow{font-size:13px; margin:8px 0 0}
  .abr .posture .legrow .cls{font-family:var(--mono); font-size:12px; color:var(--ink);
    background:color-mix(in srgb,var(--warn) 12%,transparent); border-radius:5px;
    padding:2px 7px; margin:0 6px 6px 0; display:inline-block}
  .abr .posture .why{font-size:13px; color:var(--muted); margin:10px 0 0;
    border-top:1px solid var(--line); padding-top:10px}
  .abr .posture .why b{color:var(--ink)}
  .abr .censnote{font-size:13px; color:var(--muted); margin:12px 0 0; max-width:760px}
  .abr .censnote b{color:var(--ink)}

  /* clean hero */
  .abr .hero.allclear{grid-template-columns:auto 1fr; align-items:center}
  .abr .checkmark{width:64px; height:64px; border-radius:50%;
    background:color-mix(in srgb,var(--user) 16%,transparent);
    display:flex; align-items:center; justify-content:center; flex:0 0 auto}
  .abr .checkmark svg{width:34px; height:34px}
  .abr .hero.allclear h2.ch{margin:0 0 4px; font-family:var(--sans); font-size:20px;
    font-weight:650; color:var(--ink); text-transform:none; letter-spacing:0; display:block}
  .abr .hero.allclear .csub{font-size:14px; color:var(--muted); margin:0; max-width:60ch}
</style>
"""


def _esc(s) -> str:
    return html.escape(str(s))


def _circle_svg(inner_n: int, outer_n: int, gap_n: int, gdpr_n: int) -> str:
    outer_r = 118.0
    ratio = (inner_n / outer_n) if outer_n else 0.0
    inner_r = max(outer_r * math.sqrt(ratio), 32.0) if outer_n else 32.0
    if gap_n > 0:
        inner_r = min(inner_r, outer_r - 16)   # keep a visible ring when a gap exists
    cx, cy = 200, 208
    plural = "S" if gap_n != 1 else ""
    return f"""
    <svg viewBox="0 0 400 372" width="100%" role="img"
         aria-label="Agent code reaches {outer_n} fields; running user sees {inner_n}; escalation gap {gap_n}">
      <defs>
        <radialGradient id="abrGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="var(--gap)" stop-opacity="0.18"/>
          <stop offset="65%" stop-color="var(--gap)" stop-opacity="0.05"/>
          <stop offset="100%" stop-color="var(--gap)" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <circle cx="{cx}" cy="{cy}" r="152" fill="url(#abrGlow)"/>
      <circle cx="{cx}" cy="{cy}" r="{outer_r}" fill="var(--gap)" fill-opacity="0.17"
              stroke="var(--gap)" stroke-width="2.5"/>
      <circle cx="{cx}" cy="{cy}" r="{inner_r:.1f}" fill="var(--surface)"/>
      <circle cx="{cx}" cy="{cy}" r="{inner_r:.1f}" fill="var(--user)" fill-opacity="0.14"
              stroke="var(--user)" stroke-width="2.5"/>
      <text class="c-outer-label c-cap" x="{cx}" y="24" text-anchor="middle">AGENT CODE REACHES</text>
      <text class="c-outer-label c-num" x="{cx}" y="46" text-anchor="middle">{outer_n} fields</text>
      <text class="c-inner-label c-big" x="{cx}" y="{cy + 6}" text-anchor="middle">{inner_n}</text>
      <text class="c-inner-label c-cap" x="{cx}" y="{cy + 26}" text-anchor="middle">USER SEES</text>
      <text class="c-gap-label c-cap" x="{cx}" y="356" text-anchor="middle">ESCALATION GAP: {gap_n} FIELD{plural} &#8226; {gdpr_n} GDPR</text>
    </svg>
    """


def _record_section(reach) -> str:
    if not reach:
        return ""
    p = ['<p class="eyebrow">Record reach — the system-mode ceiling, not a measured result</p>']
    if reach["has_measured_gap"]:
        causes = {r.get("cause") for r in reach["measured"] if r.get("gap")}
        qual = ''
        if causes == {"crud"}:
            qual = (' <span style="color:var(--muted)">The whole measured gap is a '
                    '<b>CRUD escalation</b> — the user has no object permission at all, so it is '
                    'deterministic, not sharing-dependent.</span>')
        p.append(
            f'<div class="clean" style="border-left:4px solid var(--gap)">'
            f'The agent&rsquo;s <b>system-mode</b> reads could reach <b>up to '
            f'{reach["upper_bound_total"]}</b> records where the running user sees '
            f'<b>{reach["user_total"]}</b> &mdash; an <b>upper-bound</b> record gap of '
            f'<b>{reach["gap_total"]}</b>. <span style="color:var(--muted)">(measured '
            f'system-mode objects only)</span>{qual}</div>')
    elif reach["bounded"] and not reach["unknown"]:
        p.append(
            '<div class="clean" style="border-left:4px solid var(--proof)">'
            'Every read the agent performs <b>enforces sharing</b>, so the agent is bounded by '
            'the running user &mdash; there is <b>no record escalation</b>.</div>')
    p.append('<div class="recwrap"><table class="rec"><thead><tr>'
             '<th>Object</th><th style="text-align:left">Read mode</th>'
             '<th>Records in org</th><th>User sees</th>'
             '<th>Gap (upper bound)</th><th style="text-align:left">Cause</th>'
             '<th style="width:20%">&nbsp;</th></tr></thead><tbody>')
    for r in reach["rows"]:
        ot = "?" if r["org_total"] is None else str(r["org_total"])
        cause_txt = _CAUSE_LABEL.get(r.get("cause"), "—")
        if r["mode"] == "user":
            mode_cell = '<td style="text-align:left">user</td>'
            uv = '<td class="na">= agent (sharing enforced)</td>'
            gp = '<td>0</td>'
            bar = ''
        else:
            mode_cell = '<td style="text-align:left">system</td>'
            if r["user_visible"] is None:
                uv = f'<td class="na">n/a &middot; {_esc(r["note"])}</td>'
                gp = '<td class="na">&mdash;</td>'
                bar = ''
            else:
                uv = f'<td>{r["user_visible"]}</td>'
                g = r["gap"] or 0
                gp = f'<td class="gap">&le; {g}</td>' if g else '<td>0</td>'
                total = r["org_total"] or 0
                if total:
                    upct = round(100 * r["user_visible"] / total)
                    bar = (f'<div class="recbar"><i class="u" style="width:{upct}%"></i>'
                           f'<i class="g" style="width:{100 - upct}%"></i></div>')
                else:
                    bar = ''
        cause_cell = (f'<td style="text-align:left" class="{"na" if not r.get("cause") else ""}">'
                      f'{_esc(cause_txt)}</td>')
        p.append(f'<tr><td>{_esc(r["object"])}</td>{mode_cell}<td>{ot}</td>{uv}{gp}{cause_cell}'
                 f'<td>{bar}</td></tr>')
    p.append('</tbody></table></div>')
    p.append('<div class="clean" style="border-left:4px solid var(--info); font-size:12.5px">'
             'Only objects the agent&rsquo;s code actually <b>reads</b> are counted here '
             '(a create/insert target is a write, not a read of N records). <b>Records in org</b> '
             'is a live <code>COUNT()</code> of the whole object &mdash; it is an <b>upper '
             'bound, not the agent&rsquo;s result</b>: query predicates and <code>LIMIT</code> '
             'are not resolved statically. It is an escalation ceiling only for <b>system-mode</b> '
             'reads; a <b>user-mode</b> read enforces sharing, so the agent is bounded by the '
             'running user and the gap is 0 by construction. <b>n/a</b> marks record visibility '
             'that is sharing/ownership dependent and cannot be measured without running as the '
             'user &mdash; it is never estimated.</div>')
    return "\n".join(p)


_CHECK_SVG = ('<svg viewBox="0 0 24 24" fill="none" stroke="var(--user)" '
              'stroke-width="3" stroke-linecap="round" stroke-linejoin="round">'
              '<path d="M4 12.5l5 5L20 6"/></svg>')


def _verdict(gap, gdpr, all_findings, reach) -> str:
    """ok | warn | err - the overall posture, plain-language friendly."""
    sev = {f.severity for _a, f in all_findings}
    if "ERROR" in sev:
        return "err"
    if "WARN" in sev or (reach and reach.get("has_measured_gap")):
        return "warn"
    return "ok"


def _stakeholder_summary(agent, gap, gdpr, all_findings, reach,
                         n_actions, n_objects, n_fields, coverage) -> str:
    """A plain-language box a non-engineer (a DPO, a manager) can read and act on.
    No jargon: what we checked, the bottom line, what to do."""
    level = _verdict(gap, gdpr, all_findings, reach)
    badge = {"ok": "WITHIN BOUNDS", "warn": "NEEDS A LOOK", "err": "ACTION NEEDED"}[level]
    head = {
        "ok": "This agent's code stays within its user's permissions.",
        "warn": "This agent is mostly clean, but one or two things are worth a look.",
        "err": "This agent's code can reach data beyond what its user is allowed to see.",
    }[level]

    p = [f'<div class="plain {level}">',
         f'<div class="vhead"><span class="badge">{badge}</span>'
         f'<h3>{_esc(head)}</h3></div>']

    # 1) what we checked, in plain terms
    p.append(
        f'<p>We inspected everything the code behind <b>{_esc(agent)}</b> can touch '
        f'— <b>{n_actions}</b> action(s), reaching <b>{n_objects}</b> data object(s) '
        f'and <b>{n_fields}</b> field(s) — and compared it against what its user is '
        f'actually allowed to see. Nothing was run and no data left the org.</p>')

    # 2) the bottom line
    if level == "ok":
        p.append('<p>For every field it reads, the agent’s code respects the user’s '
                 'permissions end to end. <b>There is nothing to fix on the data-access side.</b></p>')
    else:
        if gdpr:
            p.append(
                f'<p>Its code can read <b>{len(gap)}</b> field(s) the user cannot see '
                f'— <b>{len(gdpr)}</b> of them personal-data (GDPR) fields — and that '
                f'data can reach the AI model. <b>This should be fixed before go-live.</b></p>')
        elif gap:
            p.append(
                f'<p>Its code can read <b>{len(gap)}</b> field(s) that its user has no '
                f'permission to see. None are GDPR-labelled, but it is still an access mismatch '
                f'worth reviewing.</p>')

    # 3) record reach, plainly. Only system-mode reads have a ceiling; and the org
    # COUNT is an upper bound (predicates/LIMIT unresolved), never a measured reach.
    if reach and reach.get("has_measured_gap"):
        p.append(
            f'<p>On <b>records</b>: the agent&rsquo;s system-mode code could read <b>up to '
            f'{reach["upper_bound_total"]}</b> record(s) where this user is normally allowed '
            f'<b>{reach["user_total"]}</b>. That is a ceiling, not a measured result &mdash; it is '
            f'a boundary to confirm; make sure those queries are limited to the right customer, '
            f'not the whole table.</p>')
    elif reach and reach.get("bounded") and not reach.get("unknown"):
        p.append(
            '<p>On <b>records</b>: every read the agent performs enforces sharing and the '
            'user&rsquo;s permissions, so the agent cannot see records this user could not see '
            'anyway. There is no record-level gap to fix.</p>')

    # 4) honest-coverage caveat, in plain words
    if coverage and coverage.get("not_visible"):
        p.append(
            f'<p class="sub2">Note: {coverage["not_visible"]} field(s) were not visible to the '
            f'account we scanned with, so a &ldquo;no personal data&rdquo; result is not a '
            f'guarantee for those. Re-run with a broader-read user to close this gap.</p>')
    elif coverage:
        p.append('<p class="sub2">The scan could see every field the agent reaches '
                 f'({coverage["coverage_pct"]}% classification coverage), so the personal-data '
                 'result above is a real measurement, not a blind spot.</p>')

    if level != "ok" and any(f.severity in ("ERROR", "WARN") for _a, f in all_findings):
        p.append('<p class="sub2">The exact fixes are listed under <b>What to do next</b> below.</p>')

    p.append('</div>')
    return "\n".join(p)


def _remediation(all_findings) -> str:
    """The actionable half: every ERROR/WARN finding as a fix checklist item.
    INFO findings are informational and deliberately not action items."""
    items = [(a, f) for a, f in all_findings if f.severity in ("ERROR", "WARN")]
    if not items:
        return ""
    p = ['<p class="eyebrow">What to do next</p>',
         '<p class="sub" style="margin:0 0 12px">Each item below is a concrete fix. '
         'Clear them and re-run; the report regenerates deterministically.</p>',
         '<div class="remed">']
    for _a, f in items:
        cls = "err" if f.severity == "ERROR" else "warn"
        p.append(
            f'<div class="ritem {cls}"><div class="box"></div><div class="rbody">'
            f'<span class="rrule">{_esc(f.rule)}</span>'
            f'<span class="rwhere">{_esc(f.where)}</span>'
            f'<div class="rfix"><b>Fix</b>{_esc(f.fix)}</div></div></div>')
    p.append('</div>')
    return "\n".join(p)


_AUTHORITY_PATH_CSS = """
<style>
  .abr .apath{border:1px solid var(--line); border-radius:10px; padding:14px 16px;
    margin:10px 0 2px; background:color-mix(in srgb,var(--bg) 60%,transparent)}
  .abr .apath .aphead{display:flex; align-items:center; gap:9px; margin-bottom:12px;
    font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted);
    font-family:var(--mono)}
  .abr .apath .proven{background:var(--gap); color:#fff; border-radius:5px;
    padding:2px 7px; font-weight:700; letter-spacing:.06em}
  .abr .apath .hop{display:flex; align-items:flex-start; gap:11px}
  .abr .apath .rail{display:flex; flex-direction:column; align-items:center;
    align-self:stretch; padding-top:4px}
  .abr .apath .dot2{width:10px; height:10px; border-radius:50%; flex:none;
    background:var(--muted)}
  .abr .apath .hop.src .dot2{background:var(--gap)}
  .abr .apath .hop.sink .dot2{background:var(--gap)}
  .abr .apath .line{width:2px; flex:1; min-height:16px; background:var(--line)}
  .abr .apath .box{flex:1; padding-bottom:12px; min-width:0}
  .abr .apath .box b{font-family:var(--mono); font-size:12.5px; color:var(--ink);
    word-break:break-word}
  .abr .apath .box .k2{font-size:11px; color:var(--muted); margin-top:1px}
  .abr .apath .edge{font-size:11px; color:var(--muted); font-style:italic;
    margin:-8px 0 6px 0}
</style>"""

# The report already SAYS the chain in prose. Drawing it is what lets a DPO or a
# reviewer grasp in one look that a database column ends up inside the model's
# prompt - and every hop here is a parse-tree node, which is why PS522 alone earns
# a "PROVEN" badge while PS501 stays "potential".
def _authority_path(chain: dict, rule: str) -> str:
    if not chain:
        return ""
    fld = chain.get("field", "?")
    obj = fld.split(".")[0] if "." in fld else ""
    hops = [
        ("src", fld, f"database column{' — ' + chain['tag'] if chain.get('tag') else ''}",
         "SOQL read → @InvocableVariable"),
        ("", f"@outputs.{chain.get('output')}", f"Apex action: {chain.get('action')}",
         "Agent Script: set @variables"),
        ("", f"@variables.{chain.get('variable')}", f".agent line {chain.get('set_line')}",
         "{! } interpolation"),
        ("sink", f"prompt (line {chain.get('prompt_line')})",
         "the model's instructions — and the end user's screen", None),
    ]
    proven = ('<span class="proven">PROVEN</span>' if rule == "PS522" else "")
    p = [_AUTHORITY_PATH_CSS if rule == "PS522" else "",
         '<div class="apath">',
         f'<div class="aphead">{proven}<span>Authority Path — every hop is a '
         f'parse-tree node</span></div>']
    for i, (cls, title, sub, edge) in enumerate(hops):
        last = i == len(hops) - 1
        p.append(f'<div class="hop {cls}"><div class="rail"><i class="dot2"></i>'
                 + ('' if last else '<i class="line"></i>') + '</div>'
                 f'<div class="box"><b>{_esc(title)}</b>'
                 f'<div class="k2">{_esc(sub)}</div>')
        if edge:
            p.append(f'<div class="edge" style="margin-top:6px">↓ {_esc(edge)}</div>')
        p.append('</div></div>')
    if chain.get("tag") and not chain.get("user_sees"):
        p.append('<div class="k2" style="border-top:1px solid var(--line);padding-top:9px;'
                 'font-size:12px;color:var(--muted)">The running user has <b '
                 'style="color:var(--ink)">no field-level access</b> to '
                 f'<b style="color:var(--ink)">{_esc(fld)}</b>'
                 + (f' on {_esc(obj)}' if obj else '')
                 + ' — yet its value arrives in the prompt above.</div>')
    p.append('</div>')
    return "\n".join(p)


def _backend_note(actions) -> str:
    """Not every finding carries the same evidence. The AST backend traces the
    Authority Path; the regex fallback cannot, so everything it sees stays at
    worst case - the SAME class is WARN under one and ERROR under the other. A
    reader deciding what to fix deserves to know which one produced their report,
    so say it plainly rather than letting the two look identical."""
    apex = [a for a in actions if a.kind == "apex" and a.backend]
    if not apex:
        return ""
    fallback = sorted({a.name for a in apex if a.backend != "ast"})
    if not fallback:
        return ('<p class="censnote"><b>Evidence grade:</b> every Apex action was read '
                'from a real parse tree, so the Authority Path is traced and a finding '
                'downgraded to WARN was <i>proven</i> not to reach the model &mdash; not '
                'merely unobserved.</p>')
    return ('<div class="clean" style="border-left:4px solid var(--warn);font-size:13px">'
            f'<b>Evidence grade &mdash; {len(fallback)} action(s) fell back to the regex '
            'extractor</b> ('
            + ", ".join(f'<code>{_esc(n)}</code>' for n in fallback) + '). That backend '
            'cannot trace the Authority Path, so every field it sees is held at worst case: '
            'these findings are <b>weaker evidence</b>, and some ERRORs here would likely be '
            'WARNs under the AST. Install Node + <code>npm install --prefix blast_radius</code> '
            'for the stronger read, or run with <code>--require-ast</code> to refuse the '
            'fallback outright. The fingerprint binds the backend, so the two runs are never '
            'certified as the same analysis.</div>')


def _api_posture(actions) -> str:
    """A first-class 'security posture by API version' panel, shown near the top
    because it is the single strongest at-a-glance risk signal: pre-v67 classes
    default to system mode, so they bypass sharing/FLS unless the code adds an
    explicit clause. Most real orgs are full of them. Deduplicated by class so
    the counts are of distinct classes, not action references."""
    # dedupe by action/class name so a class reached by two actions counts once
    by_class = {}
    for a in actions:
        if a.api_version is not None:
            by_class[a.name] = a.api_version
    if not by_class:
        return ""
    total = len(by_class)
    safe = sorted(n for n, v in by_class.items() if v >= 67)
    legacy = sorted(((n, v) for n, v in by_class.items() if v < 67), key=lambda x: (x[1], x[0]))
    ns, nl = len(safe), len(legacy)
    sp = round(100 * ns / total)

    level = "err" if nl else "ok"     # any legacy class -> amber posture
    p = ['<p class="eyebrow">Security posture — by Apex API version</p>',
         f'<div class="posture {level}">']

    # prominent headline: total classes + the split
    p.append(
        '<div class="ptop">'
        f'<div class="ptotal"><b>{total}</b><span>Apex '
        f'class{"es" if total != 1 else ""}<br>analysed</span></div>'
        '<div class="psplit">'
        f'<div class="pseg safe"><b>{ns}</b> at API v67+ '
        f'<span>secure-by-default (user mode)</span></div>'
        f'<div class="pseg legacy"><b>{nl}</b> pre-v67 '
        f'<span>system-mode default — sharing/FLS bypassed by default</span></div>'
        '</div></div>')

    p.append('<div class="pbar">'
             + (f'<i class="safe" style="width:{sp}%"></i>' if ns else '')
             + (f'<i class="legacy" style="width:{100 - sp}%"></i>' if nl else '')
             + '</div>')

    if legacy:
        p.append('<div class="legrow">Pre-v67 classes: '
                 + ''.join(f'<span class="cls">{_esc(n)} (v{v:g})</span>' for n, v in legacy)
                 + '</div>')
        p.append('<p class="why"><b>Why it matters:</b> a class written before API v67 '
                 'defaults to <b>system mode</b> — its queries and writes bypass the running '
                 'user’s sharing and field-level security unless the code adds an explicit '
                 '<code>WITH USER_MODE</code> / <code>as user</code> clause. Upgrading the '
                 'apiVersion flips that default, so orgs deliberately leave old classes as-is — '
                 'and the risk is permanent until each is reviewed. Every pre-v67 class is also '
                 'flagged individually (PS511).</p>')
    else:
        p.append('<p class="why">Every analysed Apex class runs at API v67 or later, so the '
                 'platform enforces the running user’s access by default. This is the strong '
                 'baseline; the findings still apply to explicit system-mode code, Flows and '
                 'legacy triggers.</p>')
    p.append('</div>')
    return "\n".join(p)


def render_html(agent: str, running_user: str, channel, actions: List[ActionSummary],
                generated: str = "deterministic", coverage=None, counts=None,
                org_health: str = "") -> str:
    fp = fingerprint(agent, running_user, channel, actions, coverage)
    gap, gdpr = escalation_gap(actions)
    reach = record_reach(counts)
    # One canonical field set, one partition. Every gap field is by definition a
    # field the code reads, so it must be part of `reached`; unioning gap in is a
    # belt-and-braces guard against any residual naming skew. The invariant
    # outer == inner + gap then holds exactly, so the concentric circles always
    # reconcile (this is the numeric-honesty contract the whole tool sells).
    reached = {f for a in actions for f in a.fields} | gap
    user_visible = reached - gap
    outer_n, inner_n = len(reached), len(user_visible)
    assert outer_n == inner_n + len(gap), \
        f"circle invariant broken: reached={outer_n} user={inner_n} gap={len(gap)}"

    objects = {o for a in actions for o in a.objects}
    system_actions = sum(1 for a in actions if a.system_mode)
    legacy = sum(1 for a in actions if a.api_version is not None and a.api_version < 67)

    all_findings = [(a, f) for a in actions for f in a.findings]
    all_findings.sort(key=finding_sort_key)

    parts: List[str] = [f'<title>Agent Blast Radius — {_esc(agent)}</title>', _CSS, '<div class="abr">']

    # header
    parts.append(
        f'<div class="bar"><span><b>AGENT</b> {_esc(agent)}</span>'
        f'<span><b>RUNNING USER</b> {_esc(running_user)}</span>'
        f'<span><b>CHANNEL</b> {_esc(channel or "n/a")}</span>'
        f'<span><b>FINGERPRINT</b> {_esc(fp)}</span>'
        f'<span><b>GENERATED</b> {_esc(generated)}</span></div>'
    )
    parts.append('<p class="eyebrow">Agent Blast Radius Report</p>')
    parts.append(f'<h1>{_esc(agent)}</h1>')
    parts.append('<p class="sub">Static, zero-credit analysis of the agent\'s real '
                 'data-access surface at the execution-semantics layer.</p>')

    # plain-language summary a non-engineer (a DPO, a manager) can read and act on
    parts.append(_stakeholder_summary(agent, gap, gdpr, all_findings, reach,
                                      len(actions), len(objects), outer_n, coverage))

    # API-version posture near the top: the single strongest at-a-glance risk signal,
    # and the number companies most need to see (how many classes are still pre-v67)
    posture = _api_posture(actions)
    if posture:
        parts.append(posture)
    backend_note = _backend_note(actions)
    if backend_note:
        parts.append(backend_note)

    # hero: the two-circle escalation gap when there IS one; a calm "within bounds"
    # panel when there isn't (an empty "0" circle reads as broken, not as good news)
    if gap:
        gap_word = "field" if len(gap) == 1 else "fields"
        parts.append('<div class="hero"><div>')
        parts.append(f'<div class="gapnum">{len(gap)}</div>')
        parts.append(f'<div class="gaplabel"><b>{gap_word} reachable beyond the running user</b>'
                     f'{f" — <b>{len(gdpr)}</b> GDPR-labelled." if gdpr else "."}</div>')
        parts.append('<div class="legend">'
                     '<span><i class="dot" style="background:var(--user)"></i>User sees</span>'
                     '<span><i class="dot" style="background:var(--gap)"></i>Agent reaches / gap</span>'
                     '</div>')
        parts.append('</div><div>')
        parts.append(_circle_svg(inner_n, outer_n, len(gap), len(gdpr)))
        parts.append('</div></div>')
    else:
        rk = (' The wider record-reach boundary is summarised below.'
              if reach and reach.get("has_measured_gap") else '')
        parts.append(
            '<div class="hero allclear">'
            f'<div class="checkmark">{_CHECK_SVG}</div>'
            '<div><h2 class="ch">No field escalation — the agent stays within its user.</h2>'
            f'<p class="csub">Every field the agent&rsquo;s code reads is one its running user '
            f'is already allowed to see.{rk}</p></div></div>')

    # stats
    stat_rows = [
        (len(actions), "Actions", False),
        (len(objects), "Objects reachable", False),
        (outer_n, "Fields reachable", False),
        (f"{system_actions}/{len(actions)}", "System-mode", system_actions > 0),
    ]
    if coverage:
        stat_rows.append((f"{coverage['coverage_pct']}%", "Classification coverage",
                          coverage['not_visible'] > 0))
    parts.append('<div class="stats">')
    for n, k, flag in stat_rows:
        parts.append(f'<div class="stat{" flag" if flag else ""}">'
                     f'<div class="n">{_esc(n)}</div><div class="k">{_esc(k)}</div></div>')
    parts.append('</div>')

    if coverage and coverage["not_visible"]:
        parts.append(
            f'<div class="clean" style="border-left:4px solid var(--warn)">'
            f'Classification coverage {coverage["coverage_pct"]}%: '
            f'{coverage["not_visible"]} reachable field(s) are not visible to the analysis '
            f'identity. A &ldquo;0 GDPR&rdquo; result is not proof of safety for those fields.'
            f'</div>')

    section = _record_section(reach)
    if section:
        parts.append(section)

    # the action list: concrete fixes, before the detailed evidence
    remediation = _remediation(all_findings)
    if remediation:
        parts.append(remediation)

    # findings by severity - the detailed evidence behind each item above
    if all_findings:
        parts.append('<p class="eyebrow" style="margin-top:30px">Findings in detail</p>')
    for sev in ("ERROR", "WARN", "INFO"):
        items = [af for af in all_findings if af[1].severity == sev]
        if not items:
            continue
        cls = _SEV[sev]
        parts.append(f'<h2>{sev} <span class="count">· {len(items)}</span></h2>')
        for _a, f in items:
            parts.append(f'<div class="find {cls}"><div class="top">'
                         f'<span class="rule">{_esc(f.rule)}</span>'
                         f'<span class="where">{_esc(f.where)}</span></div>'
                         f'<div class="msg">{_esc(f.message)}</div>'
                         f'<div class="meta"><b>Why</b> {_esc(f.why)}</div>'
                         f'<div class="meta"><b>Fix</b> {_esc(f.fix)}</div>'
                         # PS52x carries the traced hops: draw them, don't just say them
                         + _authority_path(getattr(f, "chain", None), f.rule)
                         + '</div>')

    if not all_findings:
        parts.append('<div class="clean">No authority findings. Every analysed action '
                     'enforces user mode end-to-end for the objects and fields it reaches.</div>')

    # org health: org-wide signals that don't concern THIS agent but a reviewer
    # of the org should know (whole-org API-version debt, god-mode grants, OWD)
    if org_health:
        parts.append(org_health)

    # Same wording as the markdown footer, and for the same reason: the seal names the
    # TOOL, not just the inputs. A verdict is only reproducible against the tool that
    # made it - a matching fingerprint from a newer analyzer would be a false guarantee.
    from apex_ast import parser_version as _pv
    from report import analyzer_version as _av
    parts.append(f'<div class="foot">Produced by static analysis. No agent was invoked. '
                 f'0 Flex Credits. Bound to fingerprint {_esc(fp)}, which seals both the '
                 f'INPUTS (agent config, the analysed Apex/Flow, the permission snapshot, '
                 f'and what the analysis identity could see) and the TOOL that produced '
                 f'this verdict (analyzer {_esc(_av())}, parser '
                 f'{_esc(_pv() or "none - regex fallback")}; each analysed class\'s own '
                 f'apiVersion is bound per action, since it decides the verdict). '
                 f'Regenerate if any of these change.</div>')
    parts.append('</div>')
    return "\n".join(parts)
