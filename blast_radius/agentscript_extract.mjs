/*
 * Agent Blast Radius - Agent Script (.agent) extractor.
 *
 * Parses a Salesforce Agent Script authoring bundle with Salesforce's OWN
 * open-source parser (@sf-agentscript/parser, tree-sitter) and emits a
 * normalized IR as JSON on stdout.
 *
 * Why this matters: in an Agent Script agent the action's invocation target is
 * written in the file - `target: "apex://GetHealthRecordSummary"`. That retires
 * the tool's most fragile input path (resolving a custom GenAiFunction to its
 * Apex class through a Tooling API lookup). The target is now a parsed string
 * with a line and column.
 *
 * Verified against a REAL bundle produced by `sf agent generate authoring-bundle`
 * and compiled by Salesforce's own validator (`sf agent validate` -> success),
 * so the grammar here is the vendor's, not a guess.
 *
 *   node agentscript_extract.mjs <path-to.agent>
 *
 * On failure it prints {error} and exits non-zero; the Python caller reports an
 * honest unknown rather than a false clean.
 */
import { readFileSync } from 'node:fs';
import { parse } from '@sf-agentscript/parser';

const TOPIC_KEYS = new Set(['topic', 'subagent', 'start_agent']);
// Schemes the analyzer can follow to source. Everything else is opaque (PS507).
const ANALYSABLE = new Set(['apex', 'flow']);

const path = process.argv[2];
const src = readFileSync(path, 'utf8');

const txt = (n) => src.slice(n.startOffset, n.endOffset);
const kids = (n) => n._children || [];
const pos = (n) => ({ line: n.startRow + 1, col: n.startCol });

function firstOf(node, type) {
  for (const c of kids(node)) {
    if (c.type === type) return c;
    const deep = firstOf(c, type);
    if (deep) return deep;
  }
  return null;
}
function allOf(node, type, out = []) {
  for (const c of kids(node)) {
    if (c.type === type) out.push(c);
    allOf(c, type, out);
  }
  return out;
}

// A `mapping_element` is `key: value`. The key may carry several ids
// (`topic access_patient_health_records` -> ['topic', 'access_...']).
function keyIds(el) {
  const k = kids(el).find((c) => c.type === 'key');
  return k ? kids(k).filter((c) => c.type === 'id').map(txt) : [];
}
function valueNodes(el) {
  if (!el) return [];
  const cs = kids(el);
  const i = cs.findIndex((c) => c.type === ':');
  return i < 0 ? [] : cs.slice(i + 1);
}
function valueMapping(el) {
  if (!el) return null;
  return valueNodes(el).find((c) => c.type === 'mapping') || null;
}
function scalar(el) {
  if (!el) return null;
  const v = valueNodes(el)[0];
  if (!v) return null;
  const s = firstOf(v, 'string_content');
  return s ? txt(s) : txt(v).trim();
}
function elementsOf(mapping) {
  return mapping ? kids(mapping).filter((c) => c.type === 'mapping_element') : [];
}
function findEl(mapping, name) {
  if (!mapping) return null;
  return elementsOf(mapping).find((e) => keyIds(e)[0] === name) || null;
}
function keyIdsSafe(el) { return el ? keyIds(el) : []; }

// "apex://GetHealthRecordSummary" -> { scheme: 'apex', name: 'GetHealthRecordSummary' }
function splitTarget(uri) {
  const m = /^([A-Za-z][A-Za-z0-9_]*):\/\/(.+)$/.exec(uri || '');
  return m ? { scheme: m[1], name: m[2] } : { scheme: null, name: null };
}

// actions: <local>: { target: "apex://X", description: ... }
function actionsOf(topicMap) {
  const el = findEl(topicMap, 'actions');
  const out = [];
  for (const a of elementsOf(valueMapping(el))) {
    const local = keyIds(a)[0];
    const body = valueMapping(a);
    const tEl = body ? findEl(body, 'target') : null;
    const uri = tEl ? scalar(tEl) : null;
    const { scheme, name } = splitTarget(uri);
    const anchor = tEl ? (firstOf(tEl, 'string_content') || tEl) : a;
    out.push({
      local_name: local,
      target: uri,
      scheme,
      target_name: name,
      analysable: ANALYSABLE.has(scheme),
      description: body && findEl(body, 'description') ? scalar(findEl(body, 'description')) : null,
      ...pos(anchor),
    });
  }
  return out;
}

// reasoning: { instructions: -> (template), actions: { <bind>: @actions.x } }
function reasoningOf(topicMap) {
  const el = findEl(topicMap, 'reasoning');
  const map = valueMapping(el);
  const result = { instructions: null, interpolations: [], bindings: [] };
  if (!map) return result;

  const instr = findEl(map, 'instructions');
  if (instr) {
    const proc = valueNodes(instr).find((c) => c.type === 'procedure') || instr;
    result.instructions = txt(proc);
    // `{! @variables.x }` is a first-class node: template_expression.
    for (const te of allOf(proc, 'template_expression')) {
      const expr = firstOf(te, 'member_expression') || firstOf(te, 'expression');
      result.interpolations.push({ ref: expr ? txt(expr).trim() : txt(te), ...pos(te) });
    }
  }

  const binds = findEl(map, 'actions');
  for (const b of elementsOf(valueMapping(binds))) {
    const local = keyIds(b)[0];
    const expr = firstOf(b, 'member_expression');
    // `set @variables.x = @outputs.y` is a first-class `set_statement` node:
    // its two member_expressions are the target variable and the source value.
    // This is the hop that carries an action's output into the agent's state.
    const sets = [];
    for (const s of allOf(b, 'set_statement')) {
      const refs = allOf(s, 'member_expression').map(m => txt(m).trim());
      const target = refs[0] || null;
      const source = refs[1] || null;
      if (!target) continue;
      sets.push({
        target,                                       // '@variables.record_summary'
        variable: target.split('.').pop(),            // 'record_summary'
        source,                                       // '@outputs.summary'
        from_output: source && source.startsWith('@outputs.')
          ? source.split('.').pop()                   // 'summary'
          : null,
        ...pos(s),
      });
    }
    result.bindings.push({
      local_name: local,
      ref: expr ? txt(expr).trim() : null,
      sets,
      ...pos(b),
    });
  }
  return result;
}

function variablesOf(rootMap) {
  const el = findEl(rootMap, 'variables');
  const out = [];
  for (const v of elementsOf(valueMapping(el))) {
    const ids = keyIds(v);                       // e.g. ['EndUserId'] ; modifier is in the value
    const head = txt(v).split('\n')[0];          // `EndUserId: linked string`
    const m = /:\s*(linked|mutable)\s+(\w+)/.exec(head);
    const body = valueMapping(v);
    out.push({
      name: ids[0],
      modifier: m ? m[1] : null,
      type: m ? m[2] : null,
      source: body && findEl(body, 'source') ? scalar(findEl(body, 'source')) : null,
      ...pos(v),
    });
  }
  return out;
}

try {
  const { rootNode } = await parse(src);
  if (rootNode.isError) throw new Error('Agent Script file did not parse cleanly');
  const rootMap = firstOf(rootNode, 'mapping');

  const cfg = valueMapping(findEl(rootMap, 'config'));
  const agentName = cfg && findEl(cfg, 'developer_name')
    ? scalar(findEl(cfg, 'developer_name')) : null;

  const topics = [];
  for (const el of elementsOf(rootMap)) {
    const ids = keyIds(el);
    if (!TOPIC_KEYS.has(ids[0]) || ids.length < 2) continue;
    const map = valueMapping(el);
    const r = reasoningOf(map);
    topics.push({
      kind: ids[0],                              // topic | subagent | start_agent
      name: ids[1],
      label: findEl(map, 'label') ? scalar(findEl(map, 'label')) : null,
      actions: actionsOf(map),
      interpolations: r.interpolations,
      bindings: r.bindings,
      instructions: r.instructions,
      ...pos(el),
    });
  }

  process.stdout.write(JSON.stringify({
    agent_name: agentName,
    file: path,
    variables: variablesOf(rootMap),
    topics,
    backend: 'agentscript',
  }));
} catch (e) {
  process.stdout.write(JSON.stringify({ error: String((e && e.message) || e) }));
  process.exit(2);
}
