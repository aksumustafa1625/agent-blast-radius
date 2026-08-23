"""Org health — a compact, org-wide addendum to the agent blast-radius report.

The main report is deliberately *scoped to one agent*. This module gathers a few
whole-org signals that do NOT concern that agent specifically, but that anyone
securing the org should see once they have the report open:

  * API-version debt  - how much of the org's own Apex still defaults to system
                        mode (pre-v67). See org_census for the full breakdown.
  * God-mode grants    - permission sets granting Modify All Data / View All
                        Data, which bypass ALL sharing and FLS for their holders.
  * Permissive OWD     - custom objects whose org-wide default is Public, so
                        record-level sharing protects nothing there.

Every signal is a static Tooling/Data-API read - zero Flex Credits, no records
returned. Each query is isolated: if one signal can't be gathered (permissions,
an org that doesn't expose it), it's simply omitted rather than failing the run.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from org_loaders import _sf
from org_census import run_census, TypeCensus, SECURE_DEFAULT
from report_html import _esc


@dataclass
class OrgHealth:
    censuses: Optional[List[TypeCensus]] = None
    god_mad: Optional[int] = None          # perm sets granting Modify All Data
    god_vad: Optional[int] = None          # perm sets granting View All Data only
    owd_permissive: Optional[int] = None   # custom objects with Public OWD
    owd_models: Optional[dict] = None       # {'ReadWrite': n, 'Read': n, ...}

    @property
    def has_any(self) -> bool:
        return any(v is not None for v in
                   (self.censuses, self.god_mad, self.owd_permissive))


def _gather_god(target_org) -> tuple:
    rows = _sf("SELECT PermissionsModifyAllData, PermissionsViewAllData FROM PermissionSet "
               "WHERE PermissionsModifyAllData = true OR PermissionsViewAllData = true",
               target_org=target_org)
    mad = sum(1 for r in rows if r.get("PermissionsModifyAllData"))
    vad = sum(1 for r in rows if r.get("PermissionsViewAllData")
              and not r.get("PermissionsModifyAllData"))
    return mad, vad


def _gather_owd(target_org) -> tuple:
    rows = _sf("SELECT QualifiedApiName, InternalSharingModel FROM EntityDefinition "
               "WHERE InternalSharingModel IN ('Read','ReadWrite','FullAccess') "
               "AND IsCustomizable = true", target_org=target_org)
    custom = [r for r in rows if (r.get("QualifiedApiName") or "").endswith("__c")]
    models: dict = {}
    for r in custom:
        m = r.get("InternalSharingModel")
        models[m] = models.get(m, 0) + 1
    return len(custom), models


def gather_org_health(target_org) -> OrgHealth:
    h = OrgHealth()
    try:
        h.censuses = run_census(target_org)
    except Exception:
        pass
    try:
        h.god_mad, h.god_vad = _gather_god(target_org)
    except Exception:
        pass
    try:
        h.owd_permissive, h.owd_models = _gather_owd(target_org)
    except Exception:
        pass
    return h


# human-readable OWD names
_OWD_NAME = {"ReadWrite": "Public Read/Write", "Read": "Public Read Only",
             "FullAccess": "Public Full Access"}

# styling for the agent-connected purpose frame
_HEALTH_CSS = """
<style>
  .abr .orgframe{border:1px solid var(--line); border-radius:12px; padding:16px 18px;
    margin:6px 0 14px; background:var(--surface); border-left-width:5px}
  .abr .orgframe.err{border-left-color:var(--warn);
    background:color-mix(in srgb,var(--warn) 5%,var(--surface))}
  .abr .orgframe.warn{border-left-color:var(--warn);
    background:color-mix(in srgb,var(--warn) 5%,var(--surface))}
  .abr .orgframe.ok{border-left-color:var(--proof,#1a9d6b)}
  .abr .orgframe p{font-size:14px; margin:0 0 8px; color:var(--ink); line-height:1.55}
  .abr .orgframe p:last-child{margin-bottom:0}
  .abr .orgframe .of2{font-size:13px; color:var(--muted)}
  .abr .orgframe b{color:var(--ink)}
  .abr .orgframe code{font-family:var(--mono); font-size:12px;
    background:color-mix(in srgb,var(--line) 45%,transparent); padding:1px 5px; border-radius:4px}
</style>"""


def _agent_frame(agent: str, gap_n, agent_legacy, agent_apex_total, unresolved=0) -> str:
    """The purpose line: connect the org-wide API-version posture back to WHY this
    specific agent escalates (or is safe). An agent's data boundary is set by the
    API version of the code behind it - v67+ defaults to the running user's mode
    (the agent can reach nothing its user can't), pre-v67 defaults to system mode
    (the agent reaches PAST its user). So the org posture is not trivia: it is the
    root cause of this agent's blast radius."""
    a = _esc(agent)
    # Not "set by one thing": the specification's own precedence law puts an explicit
    # mode clause ABOVE the apiVersion default, and a WITH SYSTEM_MODE at v67 bypasses
    # exactly what this paragraph would otherwise promise. State the default as a
    # default, which is what it is.
    lead = (f'<b>Why this matters for {a}:</b> an agent can only reach what the code behind '
            'it reaches. Where no explicit access mode overrides it, the Apex '
            '<b>API version</b> sets the default for every database operation. '
            'At <b>v67+</b> that default is the running user&rsquo;s mode, so an agent '
            'reaches <i>nothing its user cannot see</i>. <b>Below v67</b> it flips to system '
            'mode and the agent reaches <i>past</i> its user. An explicit '
            '<code>WITH SYSTEM_MODE</code> still overrides either. ')

    if gap_n:
        mid = (f'That is exactly the <b>{gap_n}-field escalation</b> this report found above: '
               f'{a}&rsquo;s action code is pre-v67, so it reads fields its running user has no '
               'access to. Had those classes been v67, that gap would be <b>0</b> &mdash; the '
               'agent would be bounded to its user by the platform itself.')
        cls = "err"
    elif gap_n == 0 and unresolved:
        # A zero next to unresolved reach is not a pass, and this footer must not
        # say otherwise while the Index band above says NOT clean.
        mid = (f'{a} has <b>0 proven</b> escalation &mdash; but {unresolved} operation'
               f'{"" if unresolved == 1 else "s"} could not be resolved at all, so this is '
               '<b>not</b> a clean result: an unknown never becomes clean. And if the code is '
               'still pre-v67, even that zero rests on the code <i>explicitly</i> opting in '
               '(<code>WITH USER_MODE</code> / <code>as user</code>), not on the platform '
               'default.')
        cls = "warn"
    elif gap_n == 0:
        mid = (f'{a} currently stays within its user (gap <b>0</b>) &mdash; but if its code is '
               'still pre-v67, that safety rests on the code <i>explicitly</i> opting in '
               '(<code>WITH USER_MODE</code> / <code>as user</code>), not on the platform '
               'default. The protection is one edit away from being lost.')
        cls = "ok"
    else:
        mid = ('An agent on pre-v67 code inherits system-mode defaults; on v67+ it is bounded '
               'to its running user.')
        cls = "ok"

    tail = ''
    if agent_legacy:
        tail = (f' This agent&rsquo;s own action code: <b>{agent_legacy}</b> of '
                f'{agent_apex_total} class(es) are pre-v67.')

    return (f'<div class="orgframe {cls}"><p>{lead}{mid}{tail}</p>'
            '<p class="of2">The whole-org counts below are that same condition at scale &mdash; '
            'a map of where the <i>next</i> agent or action will escalate, before it is built.</p>'
            '</div>')


def render_health_section(health: OrgHealth, agent: str, gap_n=None,
                          agent_legacy=None, agent_apex_total=None,
                          unresolved=0) -> str:
    """A compact HTML fragment (eyebrow + agent-connected frame + stat grid + note),
    appended near the foot of the agent report. Returns '' if nothing to show.

    gap_n / agent_legacy / agent_apex_total let the frame tie the org-wide posture
    back to THIS agent's blast radius (its escalation gap and its own pre-v67 code)."""
    if not health.has_any:
        return ""

    # API-version debt across the org's own Apex
    legacy = safe = total = None
    if health.censuses:
        total = sum(c.local_total for c in health.censuses)
        legacy = sum(c.local_legacy for c in health.censuses)
        safe = total - legacy

    p: List[str] = ['<p class="eyebrow" style="margin-top:32px">Org health — beyond this agent</p>']
    p.append('<p class="sub">Whole-org signals that don&rsquo;t concern <b>' + _esc(agent) +
             '</b> directly, but anyone securing this org should know. Static Tooling-API '
             'reads — zero credits, no records returned.</p>')

    # the purpose frame: connect org posture -> this agent's boundary
    p.append(_HEALTH_CSS)
    p.append(_agent_frame(agent, gap_n, agent_legacy, agent_apex_total, unresolved))

    # compact stat grid
    p.append('<div class="stats" style="margin-top:12px">')
    if total is not None and total > 0:
        pct = round(100 * legacy / total)
        p.append(_stat(f"{legacy}/{total}", "Your Apex still pre-v67", legacy > 0,
                       sub=f"{pct}% system-mode by default"))
    if health.god_mad is not None:
        p.append(_stat(str(health.god_mad), "Grant “Modify All Data”", health.god_mad > 0))
        if health.god_vad:
            p.append(_stat(str(health.god_vad), "Grant “View All Data” only", True))
    if health.owd_permissive is not None:
        p.append(_stat(str(health.owd_permissive), "Public-OWD custom objects",
                       health.owd_permissive > 0))
    p.append('</div>')

    # a single small bar for the api-version debt (visual, still compact)
    if total and total > 0:
        sp = round(100 * safe / total)
        p.append('<div class="pbar" style="max-width:520px">'
                 + (f'<i class="safe" style="width:{sp}%"></i>' if safe else '')
                 + (f'<i class="legacy" style="width:{100 - sp}%"></i>' if legacy else '')
                 + '</div>')

    # one combined "why it matters" note
    why = []
    if legacy:
        why.append('a class or trigger below API v' + str(SECURE_DEFAULT) +
                   ' defaults to <b>system mode</b>, so its queries and writes bypass the '
                   'running user’s sharing and field-level security unless the code opts in — '
                   'this agent uses only a couple of them, but the same latent escalation sits '
                   'in every other pre-v67 file')
    if health.god_mad:
        n = health.god_mad
        why.append(f'<b>{n}</b> permission set{"s" if n != 1 else ""} grant <b>Modify All '
                   'Data</b>, which overrides all sharing and FLS for whoever holds '
                   f'{"them" if n != 1 else "it"} — an agent running as such a user has no '
                   'access boundary at all')
    if health.owd_permissive:
        parts_owd = ", ".join(f'{n} {_OWD_NAME.get(m, m)}'
                              for m, n in sorted((health.owd_models or {}).items()))
        why.append(f'<b>{health.owd_permissive}</b> custom object(s) default to Public sharing '
                   f'({parts_owd}), so record-level protection is off there regardless of code')
    elif health.owd_permissive == 0:
        why.append('every custom object defaults to <b>Private</b> sharing — a healthy baseline')

    if why:
        p.append('<p class="censnote"><b>Why this matters:</b> ' + "; ".join(why) + '.</p>')

    return "\n".join(p)


def render_health_md(health: OrgHealth, agent: str, gap_n=None,
                     agent_legacy=None, agent_apex_total=None,
                     unresolved=0) -> str:
    """Compact markdown parity of the org-health section."""
    if not health.has_any:
        return ""
    L = ["## Org health — beyond this agent", "",
         f"_Whole-org signals that don't concern {agent} directly, but anyone securing "
         "this org should know. Static Tooling-API reads — zero credits._", ""]
    # the purpose frame: org posture -> this agent's boundary
    if gap_n:
        L.append(f"> **Why this matters for {agent}:** an agent reaches only what its code "
                 "reaches, and that boundary is the Apex **API version**. v67+ defaults to the "
                 "running user's mode (reaches nothing the user can't); pre-v67 defaults to "
                 f"system mode (reaches *past* the user). That is exactly the **{gap_n}-field "
                 f"escalation** above — {agent}'s pre-v67 code reads fields its user can't. At "
                 "v67 that gap would be **0**.")
    elif gap_n == 0 and unresolved:
        L.append(f"> **Why this matters for {agent}:** **0 proven** escalation — but "
                 f"{unresolved} operation{'' if unresolved == 1 else 's'} could not be resolved "
                 "at all, so this is **not** clean: an unknown never becomes clean. And if the "
                 "code is still pre-v67, even that zero rests on the code explicitly opting in "
                 "(`WITH USER_MODE`), not the platform default.")
    elif gap_n == 0:
        L.append(f"> **Why this matters for {agent}:** it stays within its user (gap 0), but if "
                 "its code is still pre-v67 that rests on the code explicitly opting in "
                 "(`WITH USER_MODE`), not the platform default — one edit from being lost.")
    if agent_legacy:
        L.append(f">")
        L.append(f"> This agent's own action code: **{agent_legacy}** of {agent_apex_total} "
                 "class(es) are pre-v67.")
    L.append("")
    if health.censuses:
        total = sum(c.local_total for c in health.censuses)
        legacy = sum(c.local_legacy for c in health.censuses)
        pct = round(100 * legacy / total) if total else 0
        L.append(f"- **{legacy}/{total} of your own Apex files are pre-v67** ({pct}% "
                 f"system-mode by default) — the same latent escalation this report proves "
                 "for the agent's classes sits in every other legacy file.")
    if health.god_mad:
        L.append(f"- **{health.god_mad} permission set(s) grant *Modify All Data*** — "
                 "overrides all sharing and FLS for whoever holds them.")
    if health.god_vad:
        L.append(f"- {health.god_vad} permission set(s) grant *View All Data* only.")
    if health.owd_permissive:
        L.append(f"- **{health.owd_permissive} custom object(s) default to Public sharing** "
                 "— record-level protection is off there regardless of code.")
    elif health.owd_permissive == 0:
        L.append("- Every custom object defaults to **Private** sharing — a healthy baseline.")
    return "\n".join(L)


def _stat(n: str, k: str, flag: bool, sub: str = "") -> str:
    subhtml = f'<div class="k" style="text-transform:none;letter-spacing:0;opacity:.8">{_esc(sub)}</div>' if sub else ""
    return (f'<div class="stat{" flag" if flag else ""}">'
            f'<div class="n">{_esc(n)}</div><div class="k">{_esc(k)}</div>{subhtml}</div>')
