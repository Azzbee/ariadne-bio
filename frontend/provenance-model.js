import { RequestGate } from './investigation.js';
import { copyJSON } from './audit-model.js';
import { escapeHTML as esc, number } from './utils.js';

const HASH = /^[a-f0-9]{64}$/;
const rank = value => value === null ? 'No supported rank' : `#${number(value)}`;
const finite = value => typeof value === 'number' && Number.isFinite(value);
const rankOrNull = value => value === null || (Number.isSafeInteger(value) && value > 0);
const unique = values => Array.isArray(values) && values.every(value => typeof value === 'string') && new Set(values).size === values.length;
const ordered = values => [...values].sort();

function requireClaim(condition, detail) {
  if (!condition) throw new Error(`The shared-dependency certificate is inconsistent: ${detail}. No verified result is claimed.`);
}

export function provenanceParameters({ topK = 10, budget = 2, groupKind = 'source', groupIds = null, protectedGroupIds = [] } = {}) {
  if (!Number.isSafeInteger(topK) || topK < 1 || topK > 100 || !Number.isSafeInteger(budget) || budget < 0 || budget > 2) {
    throw new Error('Choose a shortlist size from 1 to 100 and a group withdrawal budget from 0 to 2.');
  }
  if (!['source', 'pubmed'].includes(groupKind)) throw new Error('Choose imported source labels or PubMed references.');
  if (groupIds !== null && (!unique(groupIds) || groupIds.length > 16 || groupIds.length < 1)) throw new Error('Choose 1 to 16 distinct provenance groups.');
  if (groupKind === 'pubmed' && groupIds === null) throw new Error('Choose specific imported PubMed references before auditing.');
  if (!unique(protectedGroupIds) || protectedGroupIds.length > 16) throw new Error('Conditional protection must name at most 16 distinct groups.');
  const prefix = `${groupKind}:`;
  if ((groupIds || []).some(id => !id.startsWith(prefix)) || protectedGroupIds.some(id => !id.startsWith(prefix))) throw new Error('Every group must match the selected provenance type.');
  if (groupIds && protectedGroupIds.some(id => !groupIds.includes(id))) throw new Error('Conditionally protected groups must belong to the selected audit scope.');
  return { topK, budget, groupKind, groupIds: groupIds === null ? null : ordered(groupIds), protectedGroupIds: ordered(protectedGroupIds) };
}

export function provenanceKey(topK, budget) {
  provenanceParameters({ topK, budget });
  return `${topK}:${budget}`;
}

export function provenanceExampleURL(currentURL) {
  const url = new URL(currentURL);
  url.searchParams.set('disease', 'Disease::DOID:7148');
  url.searchParams.set('compound', 'Compound::DB00786');
  url.searchParams.set('dependency_budget', '1');
  url.searchParams.delete('audit_k');
  url.searchParams.delete('audit_budget');
  url.searchParams.delete('exclude');
  url.searchParams.delete('view');
  url.hash = 'dependency-section';
  return url.href;
}

function validateState(state) {
  const counts = ['direct', 'interaction', 'pathway'].map(key => state?.counts?.[key]);
  return state && typeof state.supported === 'boolean' && rankOrNull(state.rank)
    && (state.supported ? state.rank !== null : state.rank === null) && finite(state.score)
    && finite(state.logit) && counts.every(value => Number.isSafeInteger(value) && value >= 0)
    && Number.isSafeInteger(state.evidence_count) && state.evidence_count >= 0
    && counts.reduce((sum, value) => sum + value, 0) === state.evidence_count
    && state.supported === (state.evidence_count > 0);
}

function scenarioCount(groups, budget) {
  return 1 + (budget >= 1 ? groups : 0) + (budget >= 2 ? groups * (groups - 1) / 2 : 0);
}

/** Structural checks precede display. Full mathematical verification remains a separate operation. */
export function validateProvenanceAudit(c, diseaseId, compoundId, options = {}) {
  const p = provenanceParameters(options);
  requireClaim(c?.schema_version === '1.0' && c.method === 'provenance-group-exhaustive-v1', 'unknown method');
  requireClaim(c.disease?.id === diseaseId && c.compound?.id === compoundId && c.top_k === p.topK && c.budget === p.budget, 'the requested investigation does not match');
  const s = c.scope;
  requireClaim(s?.relationship === 'BINDS' && s.operation === 'withdraw_records_mentioning_any_selected_group' && s.group_kind === p.groupKind && s.includes_competitor_changes === true, 'the withdrawal rule is missing or different');
  requireClaim(unique(s.group_ids) && s.group_ids.length <= 16 && unique(s.protected_group_ids) && s.protected_group_ids.every(id => s.group_ids.includes(id)), 'invalid provenance scope');
  requireClaim(s.group_ids.every(id => id.startsWith(`${p.groupKind}:`)), 'a group has the wrong provenance type');
  if (p.groupIds !== null) requireClaim(JSON.stringify(ordered(s.group_ids)) === JSON.stringify(p.groupIds), 'the chosen groups differ');
  requireClaim(JSON.stringify(ordered(s.protected_group_ids)) === JSON.stringify(p.protectedGroupIds), 'the conditional protection differs');
  requireClaim(Array.isArray(s.groups) && s.groups.length === s.group_ids.length && new Set(s.groups.map(g => g.group_id)).size === s.groups.length, 'incomplete group membership metadata');
  for (const group of s.groups) requireClaim(s.group_ids.includes(group.group_id) && typeof group.label === 'string' && Number.isSafeInteger(group.edge_count) && group.edge_count >= 0 && Number.isSafeInteger(group.compound_count) && group.compound_count >= 0 && HASH.test(group.edge_ids_sha256 || ''), 'invalid group coverage');
  const eligible = s.group_ids.filter(id => !s.protected_group_ids.includes(id));
  requireClaim(s.eligible_group_count === s.group_ids.length && s.available_group_count === eligible.length, 'invalid group counts');
  for (const key of ['dataset_sha256', 'graph_sha256', 'model_sha256', 'group_map_sha256']) requireClaim(HASH.test(c.identity?.[key] || ''), `missing ${key}`);
  requireClaim(c.identity.scorer === 'float64-fixed-order-v1' && HASH.test(c.certificate_sha256 || ''), 'missing scorer or certificate identity');
  requireClaim(validateState(c.baseline), 'invalid baseline');
  requireClaim(Array.isArray(c.results) && c.results.length === p.budget + 1, 'incomplete budget results');
  for (let index = 0; index <= p.budget; index += 1) {
    const row = c.results[index];
    requireClaim(row?.budget === index && row.scenario_count === scenarioCount(eligible.length, index) && rankOrNull(row.worst_supported_rank) && typeof row.unsupported_attainable === 'boolean' && typeof row.robust === 'boolean', 'invalid scenario result');
    requireClaim(row.robust === (row.worst_supported_rank !== null && row.worst_supported_rank <= p.topK && !row.unsupported_attainable), 'the robustness verdict disagrees with its bound');
    if (index === 0) requireClaim(row.worst_supported_rank === c.baseline.rank && row.unsupported_attainable === !c.baseline.supported, 'budget zero differs from baseline');
    if (index > 0) {
      const previous = c.results[index - 1];
      requireClaim(previous.worst_supported_rank === null || (row.worst_supported_rank !== null && row.worst_supported_rank >= previous.worst_supported_rank), 'a larger budget improves its worst bound');
      requireClaim(!previous.unsupported_attainable || row.unsupported_attainable, 'support loss disappears at a larger budget');
    }
    requireClaim((row.worst_supported_rank === null || row.rank_witness) && (!row.unsupported_attainable || row.unsupported_witness), 'an attaining witness is missing');
    for (const kind of ['rank_witness', 'unsupported_witness']) {
      const witness = row[kind];
      if (!witness) continue;
      requireClaim(unique(witness.group_ids) && witness.group_ids.length <= index && witness.group_ids.every(id => eligible.includes(id)), 'witness groups violate the declared budget or protection');
      requireClaim(Number.isSafeInteger(witness.removed_edge_count) && witness.removed_edge_count >= 0 && HASH.test(witness.removed_edge_ids_sha256 || '') && Number.isSafeInteger(witness.affected_compound_count) && witness.affected_compound_count >= 0, 'invalid witness coverage');
      requireClaim(Array.isArray(witness.removed_edges_preview) && witness.removed_edges_preview.length <= 12 && witness.removed_edges_preview.length <= witness.removed_edge_count && witness.preview_truncated === (witness.removed_edges_preview.length < witness.removed_edge_count), 'invalid record preview coverage');
      requireClaim(witness.removed_edges_preview.every(edge => edge?.type === 'BINDS' && typeof edge.id === 'string') && new Set(witness.removed_edges_preview.map(edge => edge.id)).size === witness.removed_edges_preview.length, 'invalid preview records');
      requireClaim(validateState(witness.focus?.before) && validateState(witness.focus?.after) && witness.focus.before.rank === c.baseline.rank && witness.focus.before.score === c.baseline.score, 'invalid witness baseline');
      requireClaim(kind === 'rank_witness' ? witness.focus.after.supported && witness.focus.after.rank === row.worst_supported_rank : !witness.focus.after.supported && row.unsupported_attainable, 'the witness does not attain the result');
    }
  }
  const plan = c.protection_plan;
  requireClaim(plan && ['optimal', 'already_robust', 'impossible_baseline'].includes(plan.status) && unique(plan.representative) && plan.representative.every(id => eligible.includes(id)), 'invalid conditional protection plan');
  requireClaim(Number.isSafeInteger(plan.failing_scenario_count) && plan.failing_scenario_count >= 0 && plan.failing_scenario_count <= c.results.at(-1).scenario_count, 'invalid failing-scenario count');
  requireClaim(Array.isArray(plan.optimal_sets_preview) && plan.optimal_sets_preview.length <= 12 && Number.isSafeInteger(plan.optimal_set_count) && plan.optimal_set_count >= plan.optimal_sets_preview.length && plan.alternatives_truncated === (plan.optimal_set_count > plan.optimal_sets_preview.length), 'invalid protection alternatives');
  if (plan.status === 'impossible_baseline') requireClaim((!c.baseline.supported || c.baseline.rank > p.topK) && plan.minimum_additional_groups === null && plan.optimal_set_count === 0, 'baseline impossibility is inconsistent');
  else {
    requireClaim(Number.isSafeInteger(plan.minimum_additional_groups) && plan.minimum_additional_groups >= 0 && plan.minimum_additional_groups === plan.representative.length && plan.optimal_set_count >= 1, 'invalid minimum protection size');
    for (const ids of plan.optimal_sets_preview) requireClaim(unique(ids) && ids.length === plan.minimum_additional_groups && ids.every(id => eligible.includes(id)), 'an optimal alternative is outside the scope');
    requireClaim(plan.optimal_sets_preview.some(ids => JSON.stringify(ordered(ids)) === JSON.stringify(ordered(plan.representative))), 'the representative protection set is absent from the alternatives');
    requireClaim(plan.status === 'already_robust' ? c.results.at(-1).robust && plan.minimum_additional_groups === 0 && plan.failing_scenario_count === 0 : !c.results.at(-1).robust && plan.minimum_additional_groups > 0, 'the protection status disagrees with the audit');
  }
  requireClaim(Array.isArray(c.shortlist) && c.shortlist.length <= 20 && typeof c.shortlist_truncated === 'boolean', 'invalid shortlist overview');
  requireClaim(new Set(c.shortlist.map(entry => entry.compound?.id)).size === c.shortlist.length, 'duplicate shortlist candidates');
  for (const [index, entry] of c.shortlist.entries()) requireClaim(entry.compound?.id && typeof entry.compound.name === 'string' && entry.baseline_rank === index + 1 && entry.baseline_rank <= p.topK && finite(entry.baseline_score) && rankOrNull(entry.worst_supported_rank) && typeof entry.unsupported_attainable === 'boolean' && entry.robust === (entry.worst_supported_rank !== null && entry.worst_supported_rank <= p.topK && !entry.unsupported_attainable), 'invalid shortlist candidate');
  requireClaim(c.proof?.search_budget === 2 && c.proof.scenarios_evaluated === scenarioCount(s.group_ids.length, 2) && c.proof.covered_scenarios === c.results.at(-1).scenario_count && HASH.test(c.proof.scenario_table_sha256 || '') && c.proof.group_map_sha256 === c.identity.group_map_sha256, 'proof coverage or group identity differs');
  return c;
}

export function provenanceVerdict(c) {
  if (!c.baseline.supported) return { kind: 'unsupported', title: 'No supporting paths at baseline', summary: 'Conditional source protection cannot create a supported shortlist position.' };
  if (c.baseline.rank > c.top_k) return { kind: 'outside', title: 'Outside the shortlist at baseline', summary: `This compound starts outside the top ${c.top_k}. Protecting evidence cannot repair the unmodified baseline.` };
  if (c.results.at(-1).robust) return { kind: 'robust', title: 'Survives the shared-dependency scenarios', summary: `Every allowed combination of up to ${c.budget} group withdrawals preserves a supported top-${c.top_k} rank.` };
  return { kind: 'fragile', title: 'Shared dependencies can change the shortlist', summary: 'A provenance group can connect many records and several compounds. The witness below shows one exact, attainable change.' };
}

/** No personal notes or private records are persisted in browser storage. */
export class ProvenanceSession {
  constructor(api, onChange = () => {}) {
    this.api = api; this.onChange = onChange;
    this.gate = new RequestGate(); this.verifyGate = new RequestGate();
    this.disease = null; this.compound = null;
    this.parameters = provenanceParameters(); this.reset(false);
  }
  get context() { return JSON.stringify([this.disease?.id || null, this.compound?.id || null, this.parameters]); }
  reset(notify = true) { this.gate.invalidate(); this.verifyGate.invalidate(); this.certificate = null; this.error = null; this.verification = null; this.verificationError = null; this.busy = false; this.verifying = false; if (notify) this.onChange(); }
  setFocus(disease, compound) { const before = this.context; this.disease = disease ? { id: disease.id, name: disease.name } : null; this.compound = compound ? { id: compound.id, name: compound.name } : null; if (before !== this.context) this.reset(); }
  setParameters(options) { const next = provenanceParameters({ ...this.parameters, ...options }); if (JSON.stringify(next) === JSON.stringify(this.parameters)) return; this.parameters = next; this.reset(); }
  async run() {
    if (!this.disease || !this.compound) return null;
    const diseaseId = this.disease.id, compoundId = this.compound.id, parameters = copyJSON(this.parameters);
    this.reset(false); const ticket = this.gate.begin(this.context); this.busy = true; this.onChange();
    try { const c = await this.api.provenanceAudit(diseaseId, compoundId, parameters); if (!this.gate.current(ticket, this.context)) return null; this.certificate = copyJSON(validateProvenanceAudit(c, diseaseId, compoundId, parameters)); return this.certificate; }
    catch (error) { if (this.gate.current(ticket, this.context)) this.error = error; return null; }
    finally { if (this.gate.current(ticket, this.context)) { this.busy = false; this.onChange(); } }
  }
  exportCertificate() { if (!this.certificate || this.busy || !this.disease || !this.compound) return null; return copyJSON(validateProvenanceAudit(this.certificate, this.disease.id, this.compound.id, this.parameters)); }
  async verify() {
    const c = this.exportCertificate(); if (!c || this.verifying) return null;
    const ticket = this.verifyGate.begin(this.context); this.verifying = true; this.verification = null; this.verificationError = null; this.onChange();
    try { const response = await this.api.verifyProvenanceAudit(c); if (!this.verifyGate.current(ticket, this.context)) return null;
      if (!Array.isArray(response?.checks) || !Array.isArray(response?.errors) || !((response.status === 'verified' && response.valid === true && response.errors.length === 0) || (response.status === 'invalid' && response.valid === false))) throw new Error('The verifier returned an inconsistent result.');
      this.verification = copyJSON(response); return this.verification;
    } catch (error) { if (this.verifyGate.current(ticket, this.context)) this.verificationError = error; return null; }
    finally { if (this.verifyGate.current(ticket, this.context)) { this.verifying = false; this.onChange(); } }
  }
}

/** A standalone, script-free review document. All imported values are escaped. */
export function provenanceDossier(c, { edition = 'unknown', verification = null, exportedAt = new Date().toISOString() } = {}) {
  const parameters = { topK: c.top_k, budget: c.budget, groupKind: c.scope.group_kind, groupIds: c.scope.group_ids.length ? c.scope.group_ids : null, protectedGroupIds: c.scope.protected_group_ids };
  validateProvenanceAudit(c, c.disease.id, c.compound.id, parameters);
  const final = c.results.at(-1), plan = c.protection_plan, label = id => c.scope.groups.find(group => group.group_id === id)?.label || id;
  const resultRows = c.results.map(row => `<tr><td>${row.budget}</td><td>${number(row.scenario_count)}</td><td>${rank(row.worst_supported_rank)}</td><td>${row.unsupported_attainable ? 'Possible' : 'Not attainable'}</td><td>${row.robust ? 'Robust within scope' : 'Can fail'}</td></tr>`).join('');
  const shortlistRows = c.shortlist.map(row => `<tr><td>${esc(row.compound.name)}</td><td>${rank(row.baseline_rank)}</td><td>${rank(row.worst_supported_rank)}</td><td>${row.unsupported_attainable ? 'Possible' : 'Not attainable'}</td><td>${row.robust ? 'Robust within scope' : 'Can fail'}</td></tr>`).join('');
  const witnesses = [['Worst supported rank', final.rank_witness], ['Loss of support', final.unsupported_witness]].filter(([, witness]) => witness).map(([title, witness]) => `<h3>${title}</h3><p>Withdrawn groups: <strong>${esc(witness.group_ids.map(label).join('; ') || 'None')}</strong>.</p><p>${number(witness.removed_edge_count)} distinct binding records; ${number(witness.affected_compound_count)} compounds with withdrawn records. Selected compound: ${rank(witness.focus.before.rank)} → ${rank(witness.focus.after.rank)}.</p><p class="identity">Complete removed-record identifier digest: ${esc(witness.removed_edge_ids_sha256)}</p><table><thead><tr><th>Record</th><th>Compound</th><th>Gene</th></tr></thead><tbody>${witness.removed_edges_preview.map(edge => `<tr><td class="identity">${esc(edge.id)}</td><td>${esc(edge.source_name || edge.source)}</td><td>${esc(edge.target_name || edge.target)}</td></tr>`).join('')}</tbody></table><p>${witness.preview_truncated ? `Preview: ${witness.removed_edges_preview.length} of ${number(witness.removed_edge_count)} records. The verifier reconstructs the complete union from the matching graph.` : 'All removed records are shown.'}</p>`).join('');
  const protection = plan.status === 'impossible_baseline' ? 'The unmodified baseline already fails; no conditional protection set can change that baseline.' : plan.status === 'already_robust' ? 'No additional conditional protection is needed within the declared scope.' : `Minimum additional groups that must be assumed unavailable for withdrawal: ${plan.minimum_additional_groups}. Representative set: ${plan.representative.map(label).join('; ')}. Exactly ${plan.optimal_set_count} minimum-cardinality sets satisfy this finite condition.`;
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"><title>ARIADNE evidence review — ${esc(c.compound.name)}</title><style>body{font:15px/1.6 system-ui,sans-serif;color:#173e38;max-width:1000px;margin:48px auto;padding:0 28px}h1{font-size:38px;line-height:1.15}h2{margin-top:40px;border-top:1px solid #c5d2cd;padding-top:20px}h3{margin-top:24px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #dce2df}.eyebrow{font-size:12px;letter-spacing:2px}.callout{background:#eef3ef;padding:20px;border-left:3px solid #456d60}.identity,pre{font:11px/1.5 ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}.fine{font-size:12px;color:#53665f}th{background:#f2f4ef}details{margin:30px 0}footer{border-top:1px solid #c5d2cd;margin-top:40px;padding-top:20px}@media print{body{margin:0;padding:0;font-size:10pt}h1{font-size:25pt}h2,h3{break-after:avoid}tr{break-inside:avoid}.appendix{display:none}@page{margin:18mm}}</style></head><body><p class="eyebrow">ARIADNE / EVIDENCE REVIEW DOSSIER</p><h1>${esc(c.compound.name)}<br>${esc(c.disease.name)}</h1><p>${esc(provenanceVerdict(c).title)}</p><div class="callout"><strong>Exact within a declared data-change model.</strong> Withdraw every BINDS record mentioning any selected group. Overlapping memberships are deduplicated; all competitors are rescored with the fixed model. Imported labels and references do not establish independent experimental support. This is a research hypothesis audit, not treatment advice or a biological intervention.</div><p class="fine">Exported ${esc(exportedAt)} · ${edition === 'snapshot' ? 'Recorded research edition; no live solver runs in the browser.' : edition === 'live' ? 'Live application result.' : 'Execution edition not recorded.'} ${verification?.valid === true ? edition === 'snapshot' ? 'The published verification was loaded; it was executed at snapshot export.' : 'The application returned a successful certificate verification.' : 'No successful verification has been attached to this dossier.'}</p><h2>1 / Scope and exact outcome</h2><p>Shortlist: top ${c.top_k}. Maximum withdrawals: ${c.budget} ${c.scope.group_kind === 'pubmed' ? 'imported reference groups' : 'imported source-label groups'}. ${c.scope.group_ids.length} selected groups, ${c.scope.protected_group_ids.length} conditionally protected; ${number(final.scenario_count)} allowed scenarios.</p><p>Selected groups: ${esc(c.scope.groups.map(group => group.label).join('; ') || 'None recorded')}.</p><p>Already protected by assumption: ${esc(c.scope.protected_group_ids.map(label).join('; ') || 'None')}.</p><table><thead><tr><th>Budget</th><th>Scenarios</th><th>Worst supported rank</th><th>Loss of support</th><th>Top-${c.top_k} membership</th></tr></thead><tbody>${resultRows}</tbody></table><h2>2 / Original shortlist overview</h2><p>Each row is independently audited against all competing compounds and all allowed scenarios. Worst cases in different rows need not occur together.</p><table><thead><tr><th>Compound</th><th>Baseline</th><th>Worst supported rank</th><th>Loss of support</th><th>Verdict</th></tr></thead><tbody>${shortlistRows}</tbody></table>${c.shortlist_truncated ? '<p>The overview is limited to 20 original shortlist members. The selected compound remains represented by its separate audit above.</p>' : ''}<h2>3 / Attaining witnesses</h2>${witnesses}<h2>4 / Conditional review priority</h2><p>${esc(protection)}</p><div class="callout">This is conditional sensitivity analysis. Reviewing a group does not prove that its records are correct, make the group independent, or guarantee that its evidence cannot be withdrawn. The minimum is a count of groups under this declared rule; it is not an optimal experiment or a measured review-cost saving.</div><h2>5 / Reproducibility</h2><p>Keep the complete JSON certificate with this dossier and verify it using the matching graph, model and numerical runtime.</p><dl>${Object.entries(c.identity).map(([key, value]) => `<dt>${esc(key)}</dt><dd class="identity">${esc(value)}</dd>`).join('')}<dt>Certificate SHA-256</dt><dd class="identity">${esc(c.certificate_sha256)}</dd></dl><details class="appendix"><summary>Complete unchanged certificate (excluded from printed pages)</summary><pre>${esc(JSON.stringify(c, null, 2))}</pre></details><footer><p>${esc(c.interpretation || '')}</p><p class="fine">ARIADNE v1.3 research review artifact. Dataset access does not establish commercial data rights. Mathematical consistency does not certify biological truth.</p></footer></body></html>`;
}
