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

from report import ActionSummary, escalation_gap, fingerprint

_SEV = {"ERROR": "error", "WARN": "warn", "INFO": "info"}

_CSS = """
<style>
  .abr { --bg:#f5f8fa; --surface:#ffffff; --ink:#0f1720; --muted:#5c6b7a;
    --line:#e3e9ef; --accent:#0e8f9c; --user:#3b6fe0; --gap:#e5484d;
    --error:#d93a3f; --warn:#b5720a; --info:#64748b;
    --mono:ui-monospace,"SF Mono","Cascadia Code","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    color:var(--ink); background:var(--bg); font-family:var(--sans);
    line-height:1.55; max-width:900px; margin:0 auto; padding:32px 22px 64px;
    -webkit-font-smoothing:antialiased; }
  @media (prefers-color-scheme:dark){ .abr{
    --bg:#0b1016; --surface:#141d26; --ink:#e6edf3; --muted:#8b9aa8;
    --line:#223041; --accent:#22b8cf; --user:#6aa0ff; --gap:#ff6b72;
    --error:#ff6169; --warn:#e6a12b; --info:#8b9aa8; } }
  :root[data-theme="dark"] .abr{
    --bg:#0b1016; --surface:#141d26; --ink:#e6edf3; --muted:#8b9aa8;
    --line:#223041; --accent:#22b8cf; --user:#6aa0ff; --gap:#ff6b72;
    --error:#ff6169; --warn:#e6a12b; --info:#8b9aa8; }
  :root[data-theme="light"] .abr{
    --bg:#f5f8fa; --surface:#ffffff; --ink:#0f1720; --muted:#5c6b7a;
    --line:#e3e9ef; --accent:#0e8f9c; --user:#3b6fe0; --gap:#e5484d;
    --error:#d93a3f; --warn:#b5720a; --info:#64748b; }
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


def render_html(agent: str, running_user: str, channel, actions: List[ActionSummary],
                generated: str = "deterministic") -> str:
    fp = fingerprint(agent, running_user, channel, actions)
    gap, gdpr = escalation_gap(actions)
    reached = {f for a in actions for f in a.fields}
    user_visible = reached - gap
    outer_n, inner_n = len(reached), len(user_visible)

    objects = {o for a in actions for o in a.objects}
    system_actions = sum(1 for a in actions if a.system_mode)
    legacy = sum(1 for a in actions if a.api_version is not None and a.api_version < 67)

    all_findings = [(a, f) for a in actions for f in a.findings]
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    all_findings.sort(key=lambda af: (order.get(af[1].severity, 9), af[1].rule, af[1].where))

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

    # hero: gap number + circles
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

    # stats
    parts.append('<div class="stats">')
    for n, k, flag in [
        (len(actions), "Actions", False),
        (len(objects), "Objects reachable", False),
        (outer_n, "Fields reachable", False),
        (f"{system_actions}/{len(actions)}", "System-mode", system_actions > 0),
        (f"{legacy}/{len(actions)}", "Legacy API <v67", legacy > 0),
    ]:
        parts.append(f'<div class="stat{" flag" if flag else ""}">'
                     f'<div class="n">{_esc(n)}</div><div class="k">{_esc(k)}</div></div>')
    parts.append('</div>')

    # findings by severity
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
                         f'<div class="meta"><b>Fix</b> {_esc(f.fix)}</div></div>')

    if not all_findings:
        parts.append('<div class="clean">No authority findings. Every analysed action '
                     'enforces user mode end-to-end for the objects and fields it reaches.</div>')

    parts.append(f'<div class="foot">Produced by static analysis. No agent was invoked. '
                 f'0 Flex Credits. Bound to fingerprint {_esc(fp)}; regenerate if the agent '
                 f'config, any analysed Apex/Flow, or permission metadata changes.</div>')
    parts.append('</div>')
    return "\n".join(parts)
