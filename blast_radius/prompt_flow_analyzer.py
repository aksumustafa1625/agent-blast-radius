"""Authority Path, extended across the action boundary into the agent (PS52x).

The Apex-side Authority Path proves a field's value reaches the action's
@InvocableVariable output. Agent Script closes the last hop: the .agent file
declares, statically, what happens to that output next.

    HealthRecord__c.Diagnosis__c            SOQL, system mode, user has no FLS
      -> Response.summary                   @InvocableVariable  (apex_introspect
                                            field_sinks: Diagnosis__c -> 'summary')
      -> @variables.record_summary          set @variables.x = @outputs.summary
      -> prompt line 125                    {! @variables.record_summary }

Every hop is a node in a parse tree, so the claim stops being "this field can
reach the model" and becomes "this field enters the prompt, at this line".

Rules:
  PS520 INFO   an action output reaches the prompt (a data->prompt path exists)
  PS521 WARN   ... and the backing field is GDPR/PII-classified (data minimization)
  PS522 ERROR  ... and the running user has no FLS on it - a field the user
               cannot see is interpolated into the model's prompt. This is the
               PROVEN form of PS506.

Honest limits: only fields whose Apex flow is 'returned' with a NAMED sink can be
joined to a specific `@outputs.<name>`. A field that reaches the output by way of
the whole record ('*') is joined to any interpolated output of that action
(worst case, sound). Fields whose flow is 'internal' never produce a PS52x - the
Apex taint proved they do not leave the method.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from authority_analyzer import Finding, _classified

_VAR_PREFIX = "@variables."
_OUT_PREFIX = "@outputs."


def _topic_of_action(script_ir: dict, action_name: str) -> Optional[dict]:
    """The topic/subagent block that declares this action."""
    for topic in script_ir.get("topics", []):
        for a in topic.get("actions", []):
            if a.get("local_name") == action_name:
                return topic
    return None


def _interpolated_vars(topic: dict) -> Dict[str, int]:
    """{variable name: prompt line} for every `{! @variables.x }` in the topic."""
    out: Dict[str, int] = {}
    for i in topic.get("interpolations", []):
        ref = (i.get("ref") or "").strip()
        if ref.startswith(_VAR_PREFIX):
            out.setdefault(ref[len(_VAR_PREFIX):], i.get("line"))
    return out


def _output_to_prompt(topic: dict, action_name: str) -> Dict[str, tuple]:
    """{action output name: (variable, set_line, prompt_line)} for outputs that
    are bound to a variable AND that variable is interpolated into the prompt."""
    interp = _interpolated_vars(topic)
    chain: Dict[str, tuple] = {}
    for b in topic.get("bindings", []):
        if b.get("local_name") != action_name:
            continue
        for s in b.get("sets", []):
            out_name, var = s.get("from_output"), s.get("variable")
            if not out_name or not var or var not in interp:
                continue
            chain[out_name] = (var, s.get("line"), interp[var])
    return chain


def analyze_prompt_flow(action_name: str, reach, perms,
                        classification: dict, script_ir: dict) -> List[Finding]:
    """Join the Apex Authority Path to the Agent Script data->prompt chain."""
    topic = _topic_of_action(script_ir, action_name)
    if not topic:
        return []
    chain = _output_to_prompt(topic, action_name)
    if not chain:
        return []                     # nothing this action returns reaches the prompt

    findings: List[Finding] = []
    seen = set()
    for op in getattr(reach, "operations", []):
        if op.operation != "read" or not op.sobject:
            continue
        flows = op.field_flow or {}
        sinks = op.field_sinks or {}
        for fld in op.fields:
            if flows.get(fld) == "internal":
                continue              # the Apex taint PROVED it never leaves the method
            full = fld if "." in fld else f"{op.sobject}.{fld}"

            # Which interpolated output does this field land in?
            landed = [s for s in (sinks.get(fld) or []) if s in chain]
            if "*" in (sinks.get(fld) or []):
                landed = list(chain)  # whole record leaves -> any interpolated output
            if not landed:
                continue

            for out_name in landed:
                var, set_line, prompt_line = chain[out_name]
                key = (full, out_name)
                if key in seen:
                    continue
                seen.add(key)

                tag = _classified(classification, full, fld)
                user_sees = perms.can_read_field(full) or perms.can_read_field(fld)
                path = (f"{full} -> @outputs.{out_name} (Apex) -> "
                        f"@variables.{var} (line {set_line}) -> "
                        f"prompt (line {prompt_line})")
                where = f"{action_name} -> {full}"
                # structured hops so the report can DRAW the path, not just say it
                hops = {"field": full, "action": action_name, "output": out_name,
                        "variable": var, "set_line": set_line,
                        "prompt_line": prompt_line, "tag": tag, "user_sees": user_sees}

                if tag and not user_sees:
                    findings.append(Finding(
                        "PS522", "ERROR", where,
                        f"GDPR/PII field {full} is interpolated into the model's prompt "
                        f"at line {prompt_line}, and the running user has no FLS on it.",
                        f"ComplianceGroup {tag}. Traced end to end: {path}. This is not "
                        f"inferred reachability - every hop is a node in the parse tree.",
                        f"Remove {{! @variables.{var} }} from the instructions, drop the "
                        f"field from the action's output, or enforce FLS in the Apex.",
                        chain=hops))
                elif tag:
                    findings.append(Finding(
                        "PS521", "WARN", where,
                        f"Classified field {full} ({tag}) is interpolated into the model's "
                        f"prompt at line {prompt_line}.",
                        f"The running user may see it, but classified data entering the LLM "
                        f"prompt is a data-minimization concern. Traced: {path}.",
                        "Confirm this field is required in the prompt for the topic's purpose.",
                        chain=hops))
                else:
                    findings.append(Finding(
                        "PS520", "INFO", where,
                        f"Action data reaches the prompt: {full} is interpolated at "
                        f"line {prompt_line}.",
                        f"A data->prompt path exists. Traced: {path}.",
                        "No action needed; listed so the agent's prompt surface is visible.",
                        chain=hops))
    return findings
