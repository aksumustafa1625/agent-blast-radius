"""Reach reader for GenAiPromptTemplate actions (the third data->model channel).

An agent action is not always Apex or a Flow. It can be a *prompt template* -
metadata that pulls record data straight into the model via merge expressions,
with no Apex in the path at all. Until now such actions were opaque (PS507); this
reads them declaratively, the same spirit as flow_introspect.

Two reach sources in a `.genAiPromptTemplate-meta.xml`:

  1. inputs whose `<definition>` is `sobject://X` (or `record://X`) - the whole
     record of X is bound into the template, so object X is reached.
  2. merge expressions in `<content>`: `{!$Input:rec.Field__c}`, `{!Record.Field}`
     - the specific field is pulled into the prompt.

A `primitive://String` input reaches NO org field on its own - it is an opaque
value some Apex computed (analysed separately). We say so, we don't invent reach.

Execution semantics: a prompt template's record merge is evaluated in the
running user's context - it is FLS-aware. So a field it pulls is enforce_fls=True
(user mode): not a field-level escalation by itself, but classified data entering
the model is still a data-minimisation finding (PS505), and it does reach the
model by design.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

NS = "{http://soap.sforce.com/2006/04/metadata}"

# {! ... } merge expressions. We only care about ones that name a field.
_MERGE = re.compile(r"\{!\s*([^}]+?)\s*\}")
# an sobject/record input definition -> the bound object
_SOBJECT_DEF = re.compile(r"(?:sobject|record)://([A-Za-z0-9_]+)", re.IGNORECASE)


@dataclass
class PromptInput:
    name: str
    kind: str                    # 'sobject' | 'record' | 'primitive' | 'other'
    sobject: Optional[str]       # bound object when kind is sobject/record


@dataclass
class PromptVersion:
    identifier: str
    active: bool
    objects: List[str] = field(default_factory=list)
    fields: List[str] = field(default_factory=list)
    fields_complete: bool = True


@dataclass
class PromptReach:
    name: str
    objects: List[str] = field(default_factory=list)     # ACTIVE version's reach
    fields: List[str] = field(default_factory=list)      # "Object.Field" where resolvable
    inputs: List[PromptInput] = field(default_factory=list)
    fields_complete: bool = True
    note: Optional[str] = None
    reaches_model: bool = True    # a prompt template's output goes to the model by design
    versions: List[PromptVersion] = field(default_factory=list)   # every version in the file
    # objects/fields that only an INACTIVE version reaches - a latent surface: an
    # old version can be re-activated, and it is shipped in the metadata today.
    inactive_extra_objects: List[str] = field(default_factory=list)
    inactive_extra_fields: List[str] = field(default_factory=list)


def _text(el, tag) -> Optional[str]:
    child = el.find(f"{NS}{tag}")
    return child.text if child is not None else None


def _parse_inputs(version_el) -> List[PromptInput]:
    out = []
    for inp in version_el.findall(f"{NS}inputs"):
        name = _text(inp, "apiName") or "?"
        definition = _text(inp, "definition") or ""
        m = _SOBJECT_DEF.search(definition)
        if m:
            kind = "sobject" if definition.lower().startswith("sobject") else "record"
            out.append(PromptInput(name, kind, m.group(1)))
        elif definition.lower().startswith("primitive"):
            out.append(PromptInput(name, "primitive", None))
        else:
            out.append(PromptInput(name, "other", None))
    return out


def _merge_fields(content: str, inputs: List[PromptInput]) -> tuple[List[str], bool]:
    """Resolve `{! ... }` merge refs to Object.Field where the base input is an
    sObject. Returns (fields, complete). Unresolvable refs -> complete=False."""
    by_name = {i.name: i for i in inputs}
    fields, complete = [], True
    for raw in _MERGE.findall(content or ""):
        expr = raw.strip()
        # forms: $Input:rec.Field   |   $Input:rec   |   rec.Field   |   Record.Field
        expr = re.sub(r"^\$Input:", "", expr, flags=re.IGNORECASE).strip()
        parts = expr.split(".")
        base = parts[0]
        inp = by_name.get(base)
        if inp and inp.sobject:
            if len(parts) >= 2:                       # rec.Field
                fields.append(f"{inp.sobject}.{parts[-1]}")
            else:                                     # whole record merged -> fields unknown
                complete = False
        # primitive inputs / system merges ($User, $Organization, literals) add no org field
    return fields, complete


def _version_reach(version_el, active: bool) -> tuple[PromptVersion, List[PromptInput]]:
    identifier = _text(version_el, "versionIdentifier") or "?"
    inputs = _parse_inputs(version_el)
    fields, complete = _merge_fields(_text(version_el, "content") or "", inputs)
    objects = sorted({i.sobject for i in inputs if i.sobject})
    return (PromptVersion(identifier, active, objects, sorted(set(fields)), complete), inputs)


def parse_prompt_template(path: str) -> PromptReach:
    root = ET.parse(path).getroot()
    name = _text(root, "developerName") or os.path.basename(path).split(".")[0]
    active_id = _text(root, "activeVersionIdentifier")

    version_els = root.findall(f"{NS}templateVersions") or [root]
    versions: List[PromptVersion] = []
    active_inputs: List[PromptInput] = []
    active_v: Optional[PromptVersion] = None
    for v in version_els:
        is_active = _text(v, "versionIdentifier") == active_id
        pv, inputs = _version_reach(v, is_active)
        versions.append(pv)
        if is_active or (active_v is None):
            active_v, active_inputs = pv, inputs   # active, else fall back to first

    reach = PromptReach(
        name=name, objects=active_v.objects, fields=active_v.fields,
        inputs=active_inputs, fields_complete=active_v.fields_complete, versions=versions)

    # Latent surface: what an INACTIVE version reaches beyond the active one.
    act_obj, act_fld = set(active_v.objects), set(active_v.fields)
    extra_obj, extra_fld = set(), set()
    for pv in versions:
        if pv is active_v or pv.active:
            continue
        extra_obj |= set(pv.objects) - act_obj
        extra_fld |= set(pv.fields) - act_fld
    reach.inactive_extra_objects = sorted(extra_obj)
    reach.inactive_extra_fields = sorted(extra_fld)

    if not reach.objects and not extra_obj:
        reach.note = ("no record input - the template consumes primitive/computed "
                      "values only, so it reads no org field on its own")
    elif not reach.fields_complete:
        reach.note = "a whole record is merged; individual fields not enumerable"
    if extra_obj or extra_fld:
        reach.note = ((reach.note + " ") if reach.note else "") + (
            f"{len(versions) - 1} inactive version(s) reach data the active one does not "
            f"(latent surface - re-activatable and shipped in the metadata today)")
    return reach


if __name__ == "__main__":
    import sys
    r = parse_prompt_template(sys.argv[1])
    print(f"{r.name}  (active) objects={r.objects}  fields={r.fields}  complete={r.fields_complete}")
    for i in r.inputs:
        print(f"  input {i.name}: {i.kind}" + (f" -> {i.sobject}" if i.sobject else ""))
    print(f"  versions in file: {len(r.versions)}")
    for v in r.versions:
        tag = "ACTIVE" if v.active else "inactive"
        print(f"    - {v.identifier} [{tag}]  objects={v.objects}  fields={v.fields}")
    if r.inactive_extra_objects or r.inactive_extra_fields:
        print(f"  LATENT (inactive-only): objects={r.inactive_extra_objects} "
              f"fields={r.inactive_extra_fields}")
    if r.note:
        print(f"  note: {r.note}")
