import { RequestGate } from './investigation.js';

/** Audit scope is always the complete graph; explorer family exclusions are absent. */
export function auditContext(diseaseId, compoundId, topK = 10, budget = 2) {
  return JSON.stringify([diseaseId || null, compoundId || null, topK, budget]);
}

export function auditKey(topK, budget) {
  if (!Number.isInteger(topK) || topK < 1 || topK > 100
    || !Number.isInteger(budget) || budget < 0 || budget > 2) {
    throw new Error('Choose a shortlist size from 1 to 100 and a withdrawal budget from 0 to 2.');
  }
  return `${topK}:${budget}`;
}

/** Deep links may choose only configurations supported by the visible controls. */
export function auditLinkParameters(parameters) {
  const rawK = parameters.get('audit_k'), rawBudget = parameters.get('audit_budget');
  const validK = /^(1|5|10)$/.test(rawK || '');
  const validBudget = /^[012]$/.test(rawBudget || '');
  return {
    topK: validK ? Number(rawK) : 10,
    budget: validBudget ? Number(rawBudget) : 2,
    requested: (rawK !== null || rawBudget !== null)
      && (rawK === null || validK) && (rawBudget === null || validBudget)
  };
}

/** A post-benchmark illustration; outcomes always come from its actual certificate. */
export function rivalExampleURL(currentURL) {
  const url = new URL(currentURL);
  url.searchParams.set('disease', 'Disease::DOID:175');
  url.searchParams.set('compound', 'Compound::DB01115');
  url.searchParams.set('audit_k', '10');
  url.searchParams.set('audit_budget', '1');
  url.searchParams.delete('exclude');
  url.searchParams.delete('view');
  url.hash = 'audit-section';
  return url.href;
}

/** Semantic equality for recorded envelopes, not a substitute for a certificate hash. */
export function stableJSON(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJSON).join(',')}]`;
  return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableJSON(value[key])}`).join(',')}}`;
}

export function copyJSON(value) { return JSON.parse(JSON.stringify(value)); }
export function metadataList(value) { return Array.isArray(value) ? value : value === null || value === undefined ? [] : [value]; }

/** A rival-only witness still needs the selected compound in its comparison. */
export function witnessChanges(certificate, witness) {
  const changes = Array.isArray(witness.changed_compounds) ? witness.changed_compounds : [];
  if (changes.some(item => item.id === certificate.compound.id)) return changes;
  return [{
    id: certificate.compound.id, name: certificate.compound.name, role: 'focus',
    before: certificate.baseline, after: witness.focus, removed_edge_ids: []
  }, ...changes];
}

function requireAudit(condition, message) {
  if (!condition) throw new Error(`The audit certificate is inconsistent: ${message}. Retry or inspect the server result.`);
}

function rankOrNull(value) { return value === null || (Number.isInteger(value) && value >= 1); }

/** Reject mismatched scopes and impossible verdicts before displaying/exporting them. */
export function validateAudit(certificate, diseaseId, compoundId, topK, budget) {
  auditKey(topK, budget);
  const c = certificate;
  requireAudit(c?.schema_version === '1.0' && c.method === 'binding-envelope-v1', 'unsupported method');
  requireAudit(c.disease?.id === diseaseId && c.compound?.id === compoundId
    && c.top_k === topK && c.budget === budget, 'the requested investigation does not match');
  requireAudit(c.scope?.relationship === 'BINDS' && c.scope?.operation === 'delete_record'
    && c.scope?.universe === 'all_recorded_BINDS_edges'
    && c.scope?.includes_competitor_changes === true, 'the full-graph withdrawal scope is missing');
  requireAudit(Number.isInteger(c.scope.eligible_edges) && c.scope.eligible_edges >= 0
    && Number.isInteger(c.scope.candidate_count) && c.scope.candidate_count > 0, 'invalid graph coverage');
  requireAudit(c.identity?.scorer === 'float64-fixed-order-v1', 'unknown canonical scorer');
  for (const key of ['dataset_sha256', 'graph_sha256', 'model_sha256']) {
    requireAudit(/^[a-f0-9]{64}$/.test(c.identity[key] || ''), `missing ${key}`);
  }
  requireAudit(/^[a-f0-9]{64}$/.test(c.certificate_sha256 || ''), 'missing certificate identity');
  requireAudit(typeof c.baseline?.supported === 'boolean' && rankOrNull(c.baseline.rank)
    && (c.baseline.supported ? c.baseline.rank !== null : c.baseline.rank === null)
    && Number.isFinite(c.baseline.score), 'invalid baseline');
  requireAudit(Array.isArray(c.results) && c.results.length === budget + 1, 'incomplete budget breakdown');
  for (let index = 0; index <= budget; index += 1) {
    const row = c.results[index];
    requireAudit(row?.budget === index && rankOrNull(row.worst_supported_rank)
      && rankOrNull(row.focus_only_worst_rank)
      && typeof row.unsupported_attainable === 'boolean'
      && typeof row.focus_only_unsupported_attainable === 'boolean'
      && typeof row.top_k_robust === 'boolean', 'invalid budget result');
    requireAudit(row.worst_supported_rank === null || row.worst_supported_rank <= c.scope.candidate_count,
      'rank exceeds the candidate universe');
    if (index === 0) requireAudit(row.worst_supported_rank === c.baseline.rank
      && row.unsupported_attainable === !c.baseline.supported,
    'budget zero does not reproduce the baseline');
    if (index > 0) {
      const previous = c.results[index - 1];
      requireAudit(previous.worst_supported_rank === null || (row.worst_supported_rank !== null
        && row.worst_supported_rank >= previous.worst_supported_rank), 'a larger budget has a narrower rank bound');
      requireAudit(!previous.unsupported_attainable || row.unsupported_attainable,
        'a larger budget loses a previously possible unsupported state');
    }
    const robust = row.worst_supported_rank !== null && row.worst_supported_rank <= topK && !row.unsupported_attainable;
    requireAudit(row.top_k_robust === robust, 'the shortlist verdict disagrees with its bounds');
    requireAudit((row.worst_supported_rank === null || row.rank_witness)
      && (!row.unsupported_attainable || row.unsupported_witness), 'an attaining witness is missing');
    for (const kind of ['rank_witness', 'unsupported_witness']) {
      const witness = row[kind];
      if (!witness) continue;
      requireAudit(Array.isArray(witness.removed_edge_ids) && Array.isArray(witness.removed_records)
        && Number.isInteger(witness.deletions_used) && witness.deletions_used <= index
        && witness.deletions_used === witness.removed_edge_ids.length
        && new Set(witness.removed_edge_ids).size === witness.removed_edge_ids.length,
      'invalid witness withdrawal budget');
      requireAudit(witness.removed_records.length === witness.removed_edge_ids.length
        && new Set(witness.removed_records.map(edge => edge.id)).size === witness.removed_records.length
        && witness.removed_records.every(edge => edge.type === 'BINDS' && witness.removed_edge_ids.includes(edge.id)),
      'witness records do not match their identifiers');
      requireAudit(kind === 'rank_witness'
        ? witness.focus?.supported === true && witness.focus.rank === row.worst_supported_rank
        : witness.focus?.supported === false && witness.focus.rank === null && row.unsupported_attainable,
      'witness does not attain its stated result');
    }
  }
  const failed = c.results.find(row => !row.top_k_robust)?.budget ?? null;
  const lastRobust = c.results.filter(row => row.top_k_robust).at(-1)?.budget ?? null;
  requireAudit(c.minimum_failure_budget === failed && c.robust_through_budget === lastRobust,
    'the minimum failure budget disagrees with the results');
  requireAudit(Number.isInteger(c.proof?.search_budget) && c.proof.search_budget >= budget,
    'proof coverage does not include the requested budget');
  return c;
}

export function auditVerdict(certificate) {
  const row = certificate.results.at(-1);
  if (!certificate.baseline.supported) return {
    kind: 'unsupported', title: 'No support at baseline',
    summary: 'The full graph provides no supporting paths for this pair. There is no supported shortlist position to protect.'
  };
  if (certificate.baseline.rank > certificate.top_k) return {
    kind: 'outside', title: 'Outside the shortlist at baseline',
    summary: `The canonical baseline rank is already outside the top ${certificate.top_k}; the minimum failure budget is zero.`
  };
  if (row.top_k_robust) return {
    kind: 'robust', title: `Survives up to ${certificate.budget} ${certificate.budget === 1 ? 'withdrawal' : 'withdrawals'}`,
    summary: `Every allowed withdrawal set within this budget preserves a supported rank in the top ${certificate.top_k}.`
  };
  return {
    kind: 'fragile', title: 'The shortlist can change',
    summary: `${certificate.minimum_failure_budget} binding ${certificate.minimum_failure_budget === 1 ? 'record is' : 'records are'} enough to overturn top-${certificate.top_k} membership. This is the smallest budget within the audited scope.`
  };
}

export function witnessFor(certificate, budget, kind = 'rank') {
  const row = certificate.results.find(item => item.budget === budget);
  if (!row) return null;
  if (kind === 'unsupported') return row.unsupported_witness || null;
  return row.rank_witness || null;
}

export function defaultWitnessKind(row, topK) {
  return row.unsupported_witness && (row.worst_supported_rank === null || row.worst_supported_rank <= topK)
    ? 'unsupported' : row.rank_witness ? 'rank' : 'unsupported';
}

/** UI-independent request state makes stale audit/replay handling directly testable. */
export class AuditSession {
  constructor(api, onChange = () => {}) {
    this.api = api;
    this.onChange = onChange;
    this.auditGate = new RequestGate();
    this.verifyGate = new RequestGate();
    this.disease = null;
    this.compound = null;
    this.topK = 10;
    this.budget = 2;
    this.reset(false);
  }

  get context() { return auditContext(this.disease?.id, this.compound?.id, this.topK, this.budget); }

  reset(notify = true) {
    this.auditGate.invalidate();
    this.verifyGate.invalidate();
    this.certificate = null;
    this.error = null;
    this.verification = null;
    this.verificationError = null;
    this.busy = false;
    this.verifying = false;
    if (notify) this.onChange();
  }

  setFocus(disease, compound) {
    const previous = this.context;
    this.disease = disease ? { id: disease.id, name: disease.name } : null;
    this.compound = compound ? { id: compound.id, name: compound.name } : null;
    if (previous !== this.context) this.reset();
  }

  setParameters(topK, budget) {
    auditKey(topK, budget);
    if (topK === this.topK && budget === this.budget) return;
    this.topK = topK;
    this.budget = budget;
    this.reset();
  }

  async run() {
    if (!this.disease || !this.compound) return null;
    const { topK, budget } = this;
    const diseaseId = this.disease.id, compoundId = this.compound.id;
    this.reset(false);
    const ticket = this.auditGate.begin(this.context);
    this.busy = true;
    this.onChange();
    try {
      const response = await this.api.audit(diseaseId, compoundId, topK, budget);
      if (!this.auditGate.current(ticket, this.context)) return null;
      this.certificate = copyJSON(validateAudit(response, diseaseId, compoundId, topK, budget));
      return this.certificate;
    } catch (error) {
      if (this.auditGate.current(ticket, this.context)) this.error = error;
      return null;
    } finally {
      if (this.auditGate.current(ticket, this.context)) { this.busy = false; this.onChange(); }
    }
  }

  async verify() {
    const certificate = this.exportCertificate();
    if (!certificate || this.verifying) return null;
    const ticket = this.verifyGate.begin(this.context);
    this.verification = null;
    this.verificationError = null;
    this.verifying = true;
    this.onChange();
    try {
      const response = await this.api.verifyAudit(certificate);
      if (!this.verifyGate.current(ticket, this.context)) return null;
      if (!response || !Array.isArray(response.checks) || !Array.isArray(response.errors)
        || !((response.status === 'verified' && response.valid === true && response.errors.length === 0)
          || (response.status === 'invalid' && response.valid === false))) {
        throw new Error('The verifier returned an inconsistent result. No successful replay is claimed.');
      }
      this.verification = copyJSON(response);
      return this.verification;
    } catch (error) {
      if (this.verifyGate.current(ticket, this.context)) this.verificationError = error;
      return null;
    } finally {
      if (this.verifyGate.current(ticket, this.context)) { this.verifying = false; this.onChange(); }
    }
  }

  exportCertificate() {
    if (!this.certificate || this.busy || !this.disease || !this.compound) return null;
    validateAudit(this.certificate, this.disease.id, this.compound.id, this.topK, this.budget);
    return copyJSON(this.certificate);
  }
}
