/*
 * Agent Blast Radius - real Apex AST extractor.
 *
 * Parses one .cls file with the ANTLR-based @apexdevtools/apex-parser and emits
 * a normalized intermediate representation (IR) as JSON on stdout. The IR is the
 * SAME shape the Python regex extractor produces, so the Python precedence law
 * (apex_introspect._resolve) consumes either backend unchanged.
 *
 * Why AST over regex: the parse tree resolves SOQL/DML/sharing structurally, so
 * it is correct on multiline queries, subqueries, SOQL-shaped text inside string
 * literals or comments, and delegated variable types - exactly where a regex
 * extractor guesses or false-matches.
 *
 *   node ast_extract.js <path-to.cls>   ->   { class_name, sharing, operations, ... }
 *
 * On any parse failure it exits non-zero with a JSON {error}; the Python wrapper
 * then falls back to the regex extractor (honest graceful degradation).
 */
'use strict';
const fs = require('fs');
const P = require('@apexdevtools/apex-parser');

function typeName(n) { return n && n.constructor ? n.constructor.name : ''; }
function text(n) { return typeof n.getText === 'function' ? n.getText() : String((n && n.text) || ''); }
function kids(n) { return n && n.children ? n.children : []; }

// All descendants (DFS) whose constructor name is `name`.
function collect(node, name, out) {
  out = out || [];
  for (const c of kids(node)) {
    if (typeName(c) === name) out.push(c);
    collect(c, name, out);
  }
  return out;
}
function firstChildOfType(node, name) {
  for (const c of kids(node)) if (typeName(c) === name) return c;
  return null;
}
function firstDescOfType(node, name) {
  const a = collect(node, name);
  return a.length ? a[0] : null;
}

// `List<Casc_Parent__c>` -> Casc_Parent__c ; `Map<Id, Account>` -> Account.
function baseType(t) {
  if (!t) return null;
  const lt = t.indexOf('<');
  if (lt >= 0) {
    const inner = t.slice(lt + 1, t.lastIndexOf('>'));
    const parts = inner.split(',');
    return baseType(parts[parts.length - 1].trim());
  }
  return t.replace(/\[\]$/, '');
}

// Map of variable name (lowercased) -> declared sObject/base type.
function variableTypes(root) {
  const types = {};
  const put = (id, ty) => { const k = (id || '').toLowerCase(); if (k && !(k in types)) types[k] = ty; };
  for (const d of collect(root, 'LocalVariableDeclarationContext')) {
    const tref = firstChildOfType(d, 'TypeRefContext');
    const ty = tref ? baseType(text(tref)) : null;
    const vds = firstChildOfType(d, 'VariableDeclaratorsContext');
    for (const vd of collect(vds || d, 'VariableDeclaratorContext')) {
      const idc = firstChildOfType(vd, 'IdContext');
      put(idc ? text(idc) : null, ty);
    }
  }
  for (const fp of collect(root, 'FormalParameterContext')) {
    const tref = firstChildOfType(fp, 'TypeRefContext');
    const idc = firstDescOfType(fp, 'IdContext');
    put(idc ? text(idc) : null, tref ? baseType(text(tref)) : null);
  }
  return types;
}

// Top-level class sharing modifier ("with" | "without" | "inherited" | "none").
function topSharing(root) {
  const cls = firstDescOfType(root, 'ClassDeclarationContext');
  if (!cls) return 'none';
  const parent = cls.parentCtx;
  const mods = parent ? kids(parent).filter(c => typeName(c) === 'ModifierContext') : [];
  for (const m of mods) {
    const t = text(m).toLowerCase();
    if (t === 'withsharing') return 'with';
    if (t === 'withoutsharing') return 'without';
    if (t === 'inheritedsharing') return 'inherited';
  }
  return 'none';
}

function modeFromWith(query) {
  const w = firstDescOfType(query, 'WithClauseContext');
  if (!w) return null;
  const t = text(w).toUpperCase();
  if (t.includes('USER_MODE')) return 'USER_MODE';
  if (t.includes('SYSTEM_MODE')) return 'SYSTEM_MODE';
  if (t.includes('SECURITY_ENFORCED')) return 'SECURITY_ENFORCED';
  return null;
}

function objectOfQuery(query) {
  // The query's OWN FROM is a direct child; a descendant FromNameList would be a
  // nested subquery's (relationship name), which must not shadow the parent.
  const from = firstChildOfType(query, 'FromNameListContext')
            || firstDescOfType(query, 'FromNameListContext');
  if (!from) return null;
  const first = kids(from)[0];              // object name; any alias is a later sibling
  return first ? text(first) : text(from);
}

// One QueryContext -> read operations (parent + any subquery children).
function readsFromQuery(query, ops, root, outTypes) {
  const mode = modeFromWith(query);
  const selectList = firstDescOfType(query, 'SelectListContext');
  const entries = selectList ? collect(selectList, 'SelectEntryContext') : [];
  const topEntries = entries.filter(e => {   // entries directly under this query's SELECT
    let p = e.parentCtx;
    while (p && typeName(p) !== 'QueryContext' && typeName(p) !== 'SubQueryContext') p = p.parentCtx;
    return p === query;
  });
  const fields = [];
  let hasFunction = false;
  let onlyCount = false;
  for (const e of topEntries) {
    const sub = firstDescOfType(e, 'SubQueryContext');
    if (sub) { readsFromQuery(sub, ops, root, outTypes); continue; }
    if (firstDescOfType(e, 'SoqlFunctionContext')) {
      hasFunction = true;
      if (/^count\(\s*\)$/i.test(text(e))) onlyCount = true;
      continue;
    }
    fields.push(text(e));
  }
  let complete = true, note = null;
  if (hasFunction && fields.length === 0) {
    if (onlyCount) { note = 'COUNT() - no field data returned'; }
    else { complete = false; note = 'aggregate/function select - fields not enumerated'; }
  } else if (hasFunction) {
    complete = false; note = 'aggregate/function select alongside fields';
  }
  const isSub = typeName(query) === 'SubQueryContext';
  const { flow, sinks } = isSub
    ? { flow: uniformFlow(fields, 'undetermined'), sinks: {} }  // subquery: not traced
    : queryFlow(query, root, outTypes, fields);
  ops.push({ operation: 'read', sobject: objectOfQuery(query), fields: fields,
             fields_complete: complete, mode: mode, note: note,
             field_flow: flow, field_sinks: sinks });
}

function uniformFlow(fields, v) { const m = {}; fields.forEach(f => m[f] = v); return m; }

/* ---- Authority Path: intra-method source->sink taint ---------------------
 * Classifies each queried field by whether its value actually flows to the
 * @InvocableMethod's output (the model), rather than assuming every read
 * reaches it. Three outcomes:
 *   returned      - provably flows to an output-object field, a return, or a
 *                   collection add/put (the sink); evidence is the sink.
 *   internal      - read but every use is a predicate/logic; never a sink.
 *   undetermined  - flow cannot be traced (alias through a var, passed to an
 *                   unmodelled method, subquery, no @InvocableMethod). Kept at
 *                   worst-case (assumed to reach the model) - soundness first.
 * INTERNAL is assigned ONLY when all uses are seen and none is a sink, so a real
 * leak is never silently downgraded.
 */
const COLL_METHODS = new Set(['add', 'addall', 'put', 'putall']);

function isDescendant(node, maybeAncestor) {
  if (!maybeAncestor) return false;
  let n = node;
  while (n) { if (n === maybeAncestor) return true; n = n.parentCtx; }
  return false;
}
function ancestorOfType(node, name) {
  let n = node.parentCtx;
  while (n && typeName(n) !== name) n = n.parentCtx;
  return n;
}
function leadingId(node) {           // leftmost identifier: recs from recs[0].x
  let n = node;
  while (n) {
    const tn = typeName(n);
    if ((tn === 'IdContext' || tn === 'IdPrimaryContext') && text(n)) {
      return tn === 'IdContext' ? text(n) : text(firstDescOfType(n, 'IdContext') || n);
    }
    const kk = kids(n);
    if (!kk.length) return text(n) || null;
    n = kk[0];
  }
  return null;
}
function callMethodName(callCtx) {
  const id = firstChildOfType(callCtx, 'AnyIdContext') || firstChildOfType(callCtx, 'IdContext');
  return id ? text(id).toLowerCase() : '';
}

// Inner classes that own @InvocableVariable fields = candidate sink (output)
// types. Over-including is sound (more fields kept as "reaches model").
function outputTypeNames(root) {
  const names = new Set();
  for (const cd of collect(root, 'ClassDeclarationContext')) {
    const body = firstChildOfType(cd, 'ClassBodyContext');
    if (!body) continue;
    const nameId = firstChildOfType(cd, 'IdContext');
    if (!nameId) continue;
    for (const decl of kids(body)) {
      if (typeName(decl) !== 'ClassBodyDeclarationContext') continue;
      if (/@InvocableVariable/i.test(text(decl)) && firstDescOfType(decl, 'FieldDeclarationContext')) {
        names.add(text(nameId));
        break;
      }
    }
  }
  return names;
}
function outputVarsIn(scope, outTypes) {
  const vars = new Set();
  for (const d of collect(scope, 'LocalVariableDeclarationContext')) {
    const tref = firstChildOfType(d, 'TypeRefContext');
    const ty = tref ? baseType(text(tref)) : null;
    if (ty && outTypes.has(ty)) {
      for (const vd of collect(d, 'VariableDeclaratorContext')) {
        const idc = firstChildOfType(vd, 'IdContext');
        if (idc) vars.add(text(idc));
      }
    }
  }
  return vars;
}

// Where does the value at `node` flow, climbing to the nearest sink?
// Returns { flow, sink } where sink NAMES the output field it lands in
// (e.g. 'summary' for `r.summary = ...`), or '*' when the whole record/return
// value leaves the method. The sink name is what lets the Agent Script layer
// join this to `set @variables.x = @outputs.summary`.
const MAX_ALIAS_DEPTH = 3;

// The identifier a local declaration binds: `String s = rec.F` -> "s".
function declaredName(declCtx) {
  const id = firstChildOfType(declCtx, 'IdContext') || firstDescOfType(declCtx, 'IdContext');
  return id ? text(id) : null;
}

/*
 * `String s = rec.Field;` used to end the trace: the value was aliased into a
 * local, so the verdict was `undetermined` = worst case = ERROR. That is the
 * single biggest source of noise in real code, because DAO/helper style puts a
 * local between every read and its use.
 *
 * So follow the alias FORWARD through its own uses instead of giving up.
 * Soundness rules, in order of how badly each could hurt:
 *   * The search scope is the enclosing METHOD. If there is no enclosing method
 *     (e.g. a class-level field) we cannot see every use, so -> undetermined.
 *     Getting this wrong would find "no uses" and wrongly conclude `internal` -
 *     a silent false-clean, the worst bug this tool can have.
 *   * `returned` wins immediately: one proven path to a sink is proof.
 *   * A single `undetermined` use poisons the rest: we did NOT see every use.
 *   * `internal` only when EVERY use was classified and none was a sink - the
 *     same rule the intra-method model already promises.
 *   * Depth-bounded (alias of an alias of an alias) -> undetermined at the limit.
 * A reassignment (`s = other; out = s;`) still reports `returned`, which
 * over-reports rather than under-reports. That direction is the safe one.
 */
function classifyAliasUses(declCtx, name, outVars, depth) {
  const method = ancestorOfType(declCtx, 'MethodDeclarationContext');
  if (!method || !name) return { flow: 'undetermined', sink: null };

  const uses = [];
  for (const t of ['IdPrimaryContext', 'IdContext']) {
    for (const u of collect(method, t)) {
      if (text(u) !== name) continue;
      if (isDescendant(u, declCtx)) continue;      // the declaration itself
      uses.push(u);
    }
  }
  let sawUndetermined = false;
  for (const u of uses) {
    const r = classifyFlow(u, outVars, depth);
    if (r.flow === 'returned') return r;           // proof beats everything
    if (r.flow === 'undetermined') sawUndetermined = true;
  }
  if (sawUndetermined) return { flow: 'undetermined', sink: null };
  return { flow: 'internal', sink: null };         // every use seen, none a sink
}

function classifyFlow(node, outVars, depth = 0) {
  let n = node.parentCtx;
  while (n) {
    const tn = typeName(n);
    if (tn === 'ReturnStatementContext') return { flow: 'returned', sink: '*' };
    if (tn === 'MethodCallContext' || tn === 'DotMethodCallContext') {
      return COLL_METHODS.has(callMethodName(n))
        ? { flow: 'returned', sink: '*' }
        : { flow: 'undetermined', sink: null };    // passed to a method: not traced
    }
    if (tn === 'AssignExpressionContext') {
      const lhs = kids(n)[0];
      if (outVars.has(leadingId(lhs))) {
        const fa = fieldAccess(lhs);          // `r.summary` -> field 'summary'
        return { flow: 'returned', sink: fa ? fa.field : '*' };
      }
      return { flow: 'undetermined', sink: null };  // reassigned - can't trace
    }
    if (tn === 'VariableDeclaratorContext' || tn === 'LocalVariableDeclarationContext') {
      if (depth >= MAX_ALIAS_DEPTH) return { flow: 'undetermined', sink: null };
      return classifyAliasUses(n, declaredName(n), outVars, depth + 1);
    }
    n = n.parentCtx;
  }
  return { flow: 'internal', sink: null };    // no sink up the chain: predicate/logic only
}

// Is `dot` a field access `<base>.<field>` (not a method call)?
function fieldAccess(dot) {
  if (typeName(dot) !== 'DotExpressionContext') return null;
  const cs = kids(dot);
  if (!cs.length) return null;
  if (cs.some(c => typeName(c) === 'DotMethodCallContext')) return null;
  const rhs = cs[cs.length - 1];
  const field = text(rhs);
  if (!/^[A-Za-z_]\w*$/.test(field)) return null;
  return { base: cs[0], field: field };
}

// Per-field flow for a query bound to record variable `recVar` in `scope`.
// Returns { flow: {field: verdict}, sinks: {field: [output field names]} }.
function fieldFlowFor(recVar, fields, scope, outVars) {
  const undet = new Set();
  const sinks = new Map();                     // field -> Set of sink names
  const addSink = (field, sink) => {
    if (!sinks.has(field)) sinks.set(field, new Set());
    if (sink) sinks.get(field).add(sink);
  };

  for (const dot of collect(scope, 'DotExpressionContext')) {
    const fa = fieldAccess(dot);
    if (!fa || leadingId(fa.base) !== recVar || !fields.includes(fa.field)) continue;
    const { flow, sink } = classifyFlow(dot, outVars);
    if (flow === 'returned') addSink(fa.field, sink);
    else if (flow === 'undetermined') undet.add(fa.field);
  }

  // Wholesale record use (return recs; results.add(recs[0]);) taints every field.
  // Climb past index/primary wrappers to the largest node still equal to
  // `recVar` or `recVar[..]`; if it is then the base of a `.field` selection it
  // is a field access (handled above), otherwise the whole record flows.
  const recExpr = new RegExp('^' + recVar + '(\\[[^\\]]*\\])?$');
  for (const idp of collect(scope, 'IdPrimaryContext')) {
    if (text(idp) !== recVar) continue;
    let e = idp;
    while (e.parentCtx && recExpr.test(text(e.parentCtx))) e = e.parentCtx;
    const p = e.parentCtx;
    if (p && typeName(p) === 'DotExpressionContext' && kids(p)[0] === e) continue; // .field / .method()
    const { flow, sink } = classifyFlow(e, outVars);
    if (flow === 'returned') fields.forEach(x => addSink(x, sink));
    else if (flow === 'undetermined') fields.forEach(x => undet.add(x));
  }

  const flow = {};
  const sinkMap = {};
  for (const F of fields) {
    if (sinks.has(F)) {
      flow[F] = 'returned';
      sinkMap[F] = [...sinks.get(F)];
    } else {
      flow[F] = undet.has(F) ? 'undetermined' : 'internal';
    }
  }
  return { flow, sinks: sinkMap };
}

// {flow: {field: verdict}, sinks: {field: [output names]}} for a top-level query.
function queryFlow(query, root, outTypes, fields) {
  const uniform = (v, sink) => {
    const flow = {}, sinks = {};
    fields.forEach(f => {
      flow[f] = v;
      if (sink) sinks[f] = [sink];
    });
    return { flow, sinks };
  };
  if (outTypes.size === 0 || fields.length === 0) return uniform('undetermined');
  const ret = ancestorOfType(query, 'ReturnStatementContext');
  if (ret && isDescendant(query, ret)) return uniform('returned', '*'); // return [SELECT ...]
  const lvd = ancestorOfType(query, 'LocalVariableDeclarationContext');
  if (lvd) {
    const vd = firstDescOfType(lvd, 'VariableDeclaratorContext');
    const idc = vd ? firstChildOfType(vd, 'IdContext') : null;
    const recVar = idc ? text(idc) : null;
    if (recVar) {
      const method = ancestorOfType(query, 'MethodDeclarationContext') || root;
      return fieldFlowFor(recVar, fields, method, outputVarsIn(method, outTypes));
    }
  }
  const call = ancestorOfType(query, 'DotMethodCallContext');       // add([SELECT ...])
  if (call && COLL_METHODS.has(callMethodName(call))) return uniform('returned', '*');
  return uniform('undetermined');
}

const DML_NODE = {
  InsertStatementContext: 'insert', UpdateStatementContext: 'update',
  UpsertStatementContext: 'upsert', DeleteStatementContext: 'delete',
  UndeleteStatementContext: 'undelete', MergeStatementContext: 'update',
};
const DB_DML = new Set(['insert', 'update', 'upsert', 'delete', 'undelete']);

function dmlObject(stmt, varTypes) {
  const creator = firstDescOfType(stmt, 'CreatorContext');
  if (creator) {
    const cn = firstChildOfType(creator, 'CreatedNameContext');
    if (cn) return baseType(text(cn));
  }
  // operand is a plain variable: the ExpressionContext that is not the accessLevel
  for (const c of kids(stmt)) {
    const tn = typeName(c);
    if (tn === 'AccessLevelContext') continue;
    if (tn.endsWith('ExpressionContext') || tn === 'ExpressionContext') {
      const id = text(c);
      if (/^[A-Za-z_]\w*$/.test(id)) return varTypes[id.toLowerCase()] || null;
    }
  }
  return null;
}
function dmlMode(stmt) {
  const al = firstDescOfType(stmt, 'AccessLevelContext');
  if (!al) return null;
  const t = text(al).toLowerCase();
  if (t.includes('asuser')) return 'user';
  if (t.includes('assystem')) return 'system';
  return null;
}

// Database.insert(x, AccessLevel.SYSTEM_MODE) etc. - method-call form of DML.
function dbDmlOps(root, varTypes, ops) {
  for (const mc of collect(root, 'DotMethodCallContext')) {
    const nameNode = firstChildOfType(mc, 'AnyIdContext') || firstChildOfType(mc, 'IdContext');
    const verb = nameNode ? text(nameNode).toLowerCase() : '';
    if (!DB_DML.has(verb)) continue;
    // qualifier must be Database (the DotExpression parent's left side)
    const whole = mc.parentCtx ? text(mc.parentCtx) : text(mc);
    if (!/database\./i.test(whole)) continue;
    const args = firstDescOfType(mc, 'ExpressionListContext');
    let obj = null, mode = null;
    if (args) {
      for (const a of kids(args)) {
        const at = text(a);
        const m = at.match(/^AccessLevel\.(USER|SYSTEM)_MODE$/i);
        if (m) { mode = m[1].toLowerCase(); continue; }
        if (obj === null && /^[A-Za-z_]\w*$/.test(at)) obj = varTypes[at.toLowerCase()] || null;
      }
    }
    ops.push({ operation: verb, sobject: obj, fields: [], fields_complete: true,
               mode: mode, note: obj ? null : 'DML target object undetermined' });
  }
}

function isDynamicSoql(root) {
  for (const mc of collect(root, 'DotMethodCallContext')) {
    const nameNode = firstChildOfType(mc, 'AnyIdContext') || firstChildOfType(mc, 'IdContext');
    const nm = nameNode ? text(nameNode).toLowerCase() : '';
    if (['query', 'querywithbinds', 'countquery', 'getquerylocator'].includes(nm)) {
      const whole = mc.parentCtx ? text(mc.parentCtx) : text(mc);
      if (/database\./i.test(whole)) return true;
    }
  }
  return false;
}

function referencedClasses(root) {
  const names = new Set();
  for (const cr of collect(root, 'CreatorContext')) {           // new X(...)
    const cn = firstChildOfType(cr, 'CreatedNameContext');
    if (cn) { const b = baseType(text(cn)); if (/^[A-Z]/.test(b)) names.add(b); }
  }
  for (const dm of collect(root, 'DotMethodCallContext')) {      // X.method(...)
    const p = dm.parentCtx ? text(dm.parentCtx) : '';
    const m = p.match(/^([A-Z][A-Za-z0-9_]*)\./);
    if (m) names.add(m[1]);
  }
  return Array.from(names);
}

function main() {
  const path = process.argv[2];
  const src = fs.readFileSync(path, 'utf8');
  const parser = P.ApexParserFactory.createParser(src);
  parser.removeErrorListeners();
  const root = parser.compilationUnit();

  const className = (path.split(/[\\/]/).pop() || '').replace(/\.cls$/i, '');
  const varTypes = variableTypes(root);
  const outTypes = outputTypeNames(root);
  const ops = [];
  for (const q of collect(root, 'QueryContext')) {
    // skip subqueries here; they are emitted while walking their parent query
    let p = q.parentCtx;
    while (p && typeName(p) !== 'QueryContext') {
      if (typeName(p) === 'SubQueryContext') break;
      p = p.parentCtx;
    }
    if (p && typeName(p) === 'SubQueryContext') continue;
    readsFromQuery(q, ops, root, outTypes);
  }
  for (const [nodeName, verb] of Object.entries(DML_NODE)) {
    for (const stmt of collect(root, nodeName)) {
      ops.push({ operation: verb, sobject: dmlObject(stmt, varTypes), fields: [],
                 fields_complete: true, mode: dmlMode(stmt),
                 note: dmlObject(stmt, varTypes) ? null : 'DML target object undetermined' });
    }
  }
  dbDmlOps(root, varTypes, ops);

  process.stdout.write(JSON.stringify({
    class_name: className,
    sharing: topSharing(root),
    operations: ops,
    dynamic_soql: isDynamicSoql(root),
    referenced_classes: referencedClasses(root),
    backend: 'ast',
  }));
}

try {
  main();
} catch (e) {
  process.stdout.write(JSON.stringify({ error: String(e && e.message || e) }));
  process.exit(2);
}
