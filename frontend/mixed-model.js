import { RequestGate } from './investigation.js';
import { copyJSON, stableJSON } from './audit-model.js';

const HASH = /^[a-f0-9]{64}$/;
const unique = values => Array.isArray(values) && values.every(value => typeof value === 'string' && value.length > 0) && new Set(values).size === values.length;
const integer = value => Number.isSafeInteger(value) && value >= 0;
const rank = value => value === null || (Number.isSafeInteger(value) && value > 0);
function requireMixed(condition, detail) {
  if (!condition) throw new Error(`The joint-audit certificate is inconsistent: ${detail}. No verified result is claimed.`);
}

export function mixedParameters({ topK = 10, groupBudget = 1, edgeBudget = 1, groupKind = 'source', groupIds = null } = {}) {
  if (!Number.isSafeInteger(topK) || topK < 1 || topK > 100 || ![0, 1].includes(groupBudget) || ![0, 1].includes(edgeBudget)) throw new Error('Choose a top-k from 1 to 100 and group/record budgets of zero or one.');
  if (!['source', 'pubmed'].includes(groupKind)) throw new Error('Choose imported source labels or PubMed groups.');
  if (groupIds !== null && (!unique(groupIds) || groupIds.length < 1 || groupIds.length > 16 || groupIds.some(id => !id.startsWith(`${groupKind}:`)))) throw new Error('Select 1 to 16 distinct matching provenance groups.');
  if (groupKind === 'pubmed' && groupIds === null) throw new Error('A PubMed audit requires an explicit group selection.');
  return { topK, groupBudget, edgeBudget, groupKind, groupIds: groupIds === null ? null : [...groupIds].sort() };
}
export function mixedKey(topK = 10, groupBudget = 1, edgeBudget = 1) { mixedParameters({ topK, groupBudget, edgeBudget }); return `${topK}:${groupBudget}:${edgeBudget}`; }

function validState(state) {
  const counts = ['direct', 'interaction', 'pathway'].map(key => state?.counts?.[key]);
  return typeof state?.supported === 'boolean' && rank(state.rank) && Number.isFinite(state.score) && Number.isFinite(state.logit)
    && counts.every(integer) && integer(state.evidence_count) && counts.reduce((sum, count) => sum + count, 0) === state.evidence_count
    && state.supported === (state.evidence_count > 0) && (state.supported ? state.rank !== null : state.rank === null);
}

/** Structural consistency checks. Mathematical replay remains a server/offline operation. */
export function validateMixedAudit(c, diseaseId, compoundId, options = {}) {
  const p = mixedParameters(options), s = c?.scope;
  requireMixed(c?.schema_version === '1.0' && c.method === 'mixed-group-edge-envelope-v1', 'unknown method');
  requireMixed(c.disease?.id === diseaseId && c.compound?.id === compoundId && c.top_k === p.topK && c.group_budget === p.groupBudget && c.edge_budget === p.edgeBudget, 'the requested case or budget does not match');
  requireMixed(s?.relationship === 'BINDS' && s.operation === 'withdraw_group_then_delete_residual_record' && s.includes_competitor_changes === true && s.group_kind === p.groupKind, 'the full joint withdrawal scope is absent');
  requireMixed(unique(s.group_ids) && s.group_ids.length <= 16 && s.group_ids.every(id => id.startsWith(`${p.groupKind}:`)) && integer(s.eligible_group_count) && s.eligible_group_count === s.group_ids.length && integer(s.eligible_edge_count) && integer(s.candidate_count) && s.candidate_count > 0, 'invalid scope coverage');
  if (p.groupIds !== null) requireMixed(stableJSON([...s.group_ids].sort()) === stableJSON(p.groupIds), 'the selected groups differ');
  requireMixed(Array.isArray(s.groups) && s.groups.length === s.group_ids.length && unique(s.groups.map(group => group.group_id)), 'incomplete group metadata');
  for (const group of s.groups) requireMixed(s.group_ids.includes(group.group_id) && typeof group.label === 'string' && integer(group.edge_count) && group.edge_count <= s.eligible_edge_count && integer(group.compound_count) && group.compound_count <= s.candidate_count && HASH.test(group.edge_ids_sha256 || ''), 'invalid group membership');
  for (const key of ['dataset_sha256', 'graph_sha256', 'model_sha256', 'group_map_sha256']) requireMixed(HASH.test(c.identity?.[key] || ''), `missing ${key}`);
  requireMixed(c.identity.scorer === 'decimal80-binary64-v1' && HASH.test(c.certificate_sha256 || ''), 'unknown scorer or missing seal');
  requireMixed(validState(c.baseline) && (c.baseline.rank === null || c.baseline.rank <= s.candidate_count), 'invalid baseline');
  requireMixed(Array.isArray(c.results) && c.results.length === (p.groupBudget + 1) * (p.edgeBudget + 1), 'incomplete budget frontier');
  const cells = new Map();
  for (const row of c.results) {
    const key = `${row?.group_budget}:${row?.edge_budget}`;
    requireMixed([0, 1].includes(row?.group_budget) && row.group_budget <= p.groupBudget && [0, 1].includes(row?.edge_budget) && row.edge_budget <= p.edgeBudget && !cells.has(key), 'duplicate or invalid frontier cell');
    requireMixed(rank(row.worst_supported_rank) && (row.worst_supported_rank === null || row.worst_supported_rank <= s.candidate_count) && typeof row.unsupported_attainable === 'boolean' && typeof row.robust === 'boolean' && integer(row.covered_action_representations) && row.covered_action_representations >= 1, 'invalid frontier result');
    requireMixed(row.robust === (row.worst_supported_rank !== null && row.worst_supported_rank <= p.topK && !row.unsupported_attainable), 'a verdict disagrees with its bound');
    const represented = 1 + (row.edge_budget ? s.eligible_edge_count : 0)
      + (row.group_budget ? s.groups.reduce((sum, group) => sum + 1 + (row.edge_budget ? s.eligible_edge_count - group.edge_count : 0), 0) : 0);
    requireMixed(row.covered_action_representations === represented, 'the action count disagrees with the declared memberships');
    requireMixed((row.worst_supported_rank === null || row.rank_witness) && (!row.unsupported_attainable || row.unsupported_witness), 'missing attaining witness');
    for (const kind of ['rank_witness', 'unsupported_witness']) {
      const witness = row[kind]; if (!witness) continue;
      requireMixed(unique(witness.group_ids) && witness.group_ids.length <= row.group_budget && witness.group_ids.every(id => s.group_ids.includes(id)) && unique(witness.residual_edge_ids) && witness.residual_edge_ids.length <= row.edge_budget, 'witness violates its group or residual-record budget');
      requireMixed(integer(witness.removed_edge_count) && witness.removed_edge_count <= s.eligible_edge_count && integer(witness.affected_compound_count) && witness.affected_compound_count <= s.candidate_count && HASH.test(witness.removed_edge_ids_sha256 || ''), 'invalid witness impact');
      const group = witness.group_ids.length ? s.groups.find(item => item.group_id === witness.group_ids[0]) : null;
      requireMixed(witness.removed_edge_count === (group?.edge_count || 0) + witness.residual_edge_ids.length, 'group and surviving-record counts disagree');
      requireMixed(witness.affected_compound_count >= (group?.compound_count || 0) && witness.affected_compound_count <= (group?.compound_count || 0) + witness.residual_edge_ids.length, 'affected-compound count disagrees with the withdrawal');
      requireMixed(validState(witness.focus?.before) && stableJSON(witness.focus.before) === stableJSON(c.baseline) && validState(witness.focus?.after), 'invalid witness states');
      requireMixed(kind === 'rank_witness' ? witness.focus.after.supported && witness.focus.after.rank === row.worst_supported_rank : !witness.focus.after.supported && witness.focus.after.rank === null && row.unsupported_attainable, 'witness does not attain the claimed outcome');
      requireMixed(Array.isArray(witness.removed_edges_preview) && witness.removed_edges_preview.length <= 6 && unique(witness.removed_edges_preview.map(edge => edge.id)) && witness.removed_edges_preview.every(edge => edge.type === 'BINDS') && witness.removed_edges_preview.length === Math.min(6, witness.removed_edge_count) && witness.preview_truncated === (witness.removed_edge_count > 6), 'invalid bounded record preview');
      if (!witness.group_ids.length) requireMixed(witness.removed_edge_count === witness.residual_edge_ids.length, 'a record-only witness removes extra records');
      if (!witness.preview_truncated) requireMixed(witness.residual_edge_ids.every(id => witness.removed_edges_preview.some(edge => edge.id === id)), 'residual record is absent from its complete witness');
    }
    cells.set(key, row);
  }
  const origin = cells.get('0:0');
  requireMixed(origin?.worst_supported_rank === c.baseline.rank && origin.unsupported_attainable === !c.baseline.supported && origin.covered_action_representations === 1, 'zero budgets differ from baseline');
  for (const row of cells.values()) {
    for (const previous of cells.values()) {
      if (previous.group_budget <= row.group_budget && previous.edge_budget <= row.edge_budget) {
        requireMixed(previous.worst_supported_rank === null || (row.worst_supported_rank !== null && row.worst_supported_rank >= previous.worst_supported_rank), 'a larger budget improves its worst rank');
        requireMixed(!previous.unsupported_attainable || row.unsupported_attainable, 'support loss vanishes at a larger budget');
        requireMixed(row.covered_action_representations >= previous.covered_action_representations, 'a larger budget covers fewer action representations');
      }
    }
  }
  requireMixed(HASH.test(c.proof?.envelope_table_sha256 || '') && integer(c.proof.local_states_evaluated) && c.proof.covered_action_representations === cells.get(`${p.groupBudget}:${p.edgeBudget}`).covered_action_representations, 'missing or inconsistent proof metadata');
  return c;
}

export function mixedVerdict(c) {
  const cell = (g, e) => c.results.find(row => row.group_budget === g && row.edge_budget === e);
  const joint = cell(c.group_budget, c.edge_budget);
  if (!c.baseline.supported) return { kind: 'unsupported', title: 'No supported baseline', detail: 'The selected hypothesis starts without supporting paths in the unmodified graph.' };
  if (c.baseline.rank > c.top_k) return { kind: 'outside', title: 'Already outside the shortlist', detail: `The baseline rank already exceeds the selected top ${c.top_k}.` };
  if (joint.robust) return { kind: 'robust', title: 'The joint test holds', detail: `The candidate remains supported in the top ${c.top_k} throughout the declared joint withdrawal space.` };
  if (cell(0, 1)?.robust && cell(1, 0)?.robust && c.group_budget === 1 && c.edge_budget === 1) return { kind: 'interaction', title: 'Separate tests hold. The joint test fails.', detail: 'One group alone and one record alone preserve the shortlist. Their combination can break it. This is an interaction in the fixed ranking function, not biological synergy.' };
  return { kind: 'fragile', title: 'The joint test can fail', detail: `Some allowed withdrawals remove support or push this hypothesis outside the top ${c.top_k}. The four cells show where fragility first appears.` };
}

export class MixedSession {
  constructor(api, onChange = () => {}) { this.api = api; this.onChange = onChange; this.gate = new RequestGate(); this.verifyGate = new RequestGate(); this.disease = null; this.compound = null; this.parameters = mixedParameters(); this.reset(false); }
  get context() { return JSON.stringify([this.disease?.id || null, this.compound?.id || null, this.parameters]); }
  reset(notify = true) { this.gate.invalidate(); this.verifyGate.invalidate(); this.certificate = null; this.error = null; this.verification = null; this.verificationError = null; this.busy = false; this.verifying = false; if (notify) this.onChange(); }
  setFocus(disease, compound) { const before = this.context; this.disease = disease ? { id: disease.id, name: disease.name } : null; this.compound = compound ? { id: compound.id, name: compound.name } : null; if (before !== this.context) this.reset(); }
  async run() {
    if (!this.disease || !this.compound) return null;
    const disease = this.disease.id, compound = this.compound.id, parameters = copyJSON(this.parameters);
    this.reset(false); const ticket = this.gate.begin(this.context); this.busy = true; this.onChange();
    try { const c = await this.api.mixedAudit(disease, compound, parameters); if (!this.gate.current(ticket, this.context)) return null; this.certificate = copyJSON(validateMixedAudit(c, disease, compound, parameters)); return this.certificate; }
    catch (error) { if (this.gate.current(ticket, this.context)) this.error = error; return null; }
    finally { if (this.gate.current(ticket, this.context)) { this.busy = false; this.onChange(); } }
  }
  exportCertificate() { return !this.certificate || this.busy || !this.disease || !this.compound ? null : copyJSON(validateMixedAudit(this.certificate, this.disease.id, this.compound.id, this.parameters)); }
  async verify() {
    const c = this.exportCertificate(); if (!c || this.verifying) return null;
    const ticket = this.verifyGate.begin(this.context); this.verifying = true; this.verification = null; this.verificationError = null; this.onChange();
    try {
      const result = await this.api.verifyMixedAudit(c); if (!this.verifyGate.current(ticket, this.context)) return null;
      if (!Array.isArray(result?.checks) || !Array.isArray(result?.errors) || !((result.status === 'verified' && result.valid === true && result.errors.length === 0) || (result.status === 'invalid' && result.valid === false))) throw new Error('The joint verifier returned an inconsistent result.');
      this.verification = copyJSON(result); return this.verification;
    } catch (error) { if (this.verifyGate.current(ticket, this.context)) this.verificationError = error; return null; }
    finally { if (this.verifyGate.current(ticket, this.context)) { this.verifying = false; this.onChange(); } }
  }
}
