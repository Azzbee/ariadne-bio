import { MixedSession, mixedVerdict } from './mixed-model.js';
import { escapeHTML as esc, number, objectText } from './utils.js';

const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const rank = value => value === null ? 'No supported rank' : `#${number(value)}`;
const errorText = error => error?.message || 'The joint audit could not complete.';
const cellKey = row => `${row.group_budget}:${row.edge_budget}`;

/** Compact, four-cell view of the exact group + surviving-record audit. */
export class MixedPanel {
  constructor(element, api, callbacks = {}) {
    this.element = element; this.api = api; this.callbacks = callbacks; this.loading = false; this.excluded = [];
    this.selectedCell = '1:1'; this.witnessKind = 'rank'; this.renderedState = null; this.renderedCertificate = null;
    this.element.innerHTML = `<div class="mixed-heading"><div><span class="eyebrow">JOINT EVIDENCE AUDIT</span><h2 id="mixed-title" tabindex="-1">What if two kinds of evidence<br><em>change together?</em></h2><p>A shared source can disappear while another individual record also changes. Test both at once, with every rival included.</p><div id="mixed-focus" class="mixed-focus">Choose a compound to begin.</div></div><div class="mixed-controls"><span class="mixed-budget-badge">1 SOURCE GROUP <b>+</b> 1 SURVIVING RECORD</span><button id="mixed-run" type="button" class="button button-dark" data-mixed-action="run" disabled>${icon('shield')}<span>Run joint audit</span></button><span id="mixed-edition" class="mixed-edition"></span></div></div><div class="mixed-scope"><span class="eyebrow">DECLARED SCOPE</span><p id="mixed-scope-text">The unmodified full graph · top ten · all imported source groups · the fitted model stays fixed. A group removes every binding record mentioning its annotation. The extra record must survive that withdrawal.</p></div><div id="mixed-body"></div><p id="mixed-announcement" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>`;
    this.session = new MixedSession(api, () => this.render());
    this.element.addEventListener('click', event => {
      const cell = event.target.closest('[data-mixed-cell]');
      if (cell) { this.selectedCell = cell.dataset.mixedCell; this.renderWitness(); return; }
      const witness = event.target.closest('[data-mixed-witness]');
      if (witness) { this.witnessKind = witness.dataset.mixedWitness; this.renderWitness(); return; }
      const action = event.target.closest('[data-mixed-action]')?.dataset.mixedAction;
      if (action === 'run') void this.run();
      if (action === 'verify') void this.session.verify();
      if (action === 'download') this.download();
    });
    this.render();
  }
  find(id) { return this.element.querySelector(`#${id}`); }
  announce(text) { this.find('mixed-announcement').textContent = text; }
  setContext({ disease, candidate, excluded = [], loading = false }) {
    this.loading = loading; this.excluded = excluded; this.session.setFocus(disease, candidate); this.renderControls();
  }
  focus() { this.element.scrollIntoView({ block: 'start' }); this.find('mixed-title').focus({ preventScroll: true }); }
  async run() { if (this.loading) return null; return this.session.run(); }
  renderControls() {
    const s = this.session, recorded = this.api.mode === 'snapshot';
    const count = this.api.manifest?.cases?.[s.disease?.id]?.coverage?.mixed_audit_count;
    const available = !recorded || (typeof count === 'number' && count > 0);
    this.find('mixed-focus').textContent = s.disease && s.compound ? `${s.compound.name} / ${s.disease.name}` : 'Choose a compound to begin.';
    this.find('mixed-edition').textContent = recorded ? available ? 'Recorded certificate · no browser solver' : 'No joint audits in this recorded case. Run the full application.' : 'Exact conditional envelopes · bounded scope';
    const button = this.find('mixed-run');
    button.disabled = this.loading || s.busy || !s.disease || !s.compound || !available;
    button.innerHTML = `${s.busy ? '<span class="spinner"></span>' : icon('shield')}<span>${s.busy ? 'Auditing…' : recorded ? 'Explore recorded joint audit' : 'Run joint audit'}</span>`;
    this.find('mixed-scope-text').textContent = `${this.excluded.length ? 'Explorer family exclusions do not apply to this audit. ' : ''}The unmodified full graph · top ten · all imported source groups · the fitted model stays fixed. A group removes every binding record mentioning its annotation. The extra record must survive that withdrawal.`;
    const verify = this.find('mixed-verify');
    if (verify) { verify.disabled = s.verifying || s.busy; verify.innerHTML = `${s.verifying ? '<span class="spinner"></span>' : icon('reset')}<span>${s.verifying ? 'Checking…' : recorded ? 'View recorded verification' : 'Verify certificate'}</span>`; }
  }
  render() {
    const s = this.session;
    const status = s.busy ? 'busy' : s.error ? 'error' : s.certificate ? 'certificate' : 'empty';
    if (status !== this.renderedState || s.certificate !== this.renderedCertificate) {
      this.renderedState = status; this.renderedCertificate = s.certificate;
      if (status === 'busy') { this.find('mixed-body').innerHTML = `<div class="mixed-loading"><span class="spinner"></span><div><strong>${this.api.mode === 'snapshot' ? 'Loading the recorded joint audit' : 'Computing conditional rank envelopes'}</strong><p>The four budget cells include all competitors and separate loss-of-support outcomes.</p></div></div>`; this.announce('Joint audit in progress.'); }
      else if (status === 'error') { this.find('mixed-body').innerHTML = `<div class="mixed-error" role="alert"><strong>Joint audit unavailable</strong><p>${esc(errorText(s.error))}</p><button type="button" data-mixed-action="run" class="button button-outline">Try again</button></div>`; this.announce(errorText(s.error)); }
      else if (status === 'certificate') { this.selectedCell = `${s.certificate.group_budget}:${s.certificate.edge_budget}`; this.witnessKind = 'rank'; this.renderCertificate(); this.announce(`${s.compound.name}. ${mixedVerdict(s.certificate).title}.`); }
      else { this.find('mixed-body').innerHTML = ''; this.announce(''); }
    }
    this.renderControls(); this.renderVerification();
  }
  renderCertificate() {
    const c = this.session.certificate, verdict = mixedVerdict(c), recorded = this.api.mode === 'snapshot';
    this.find('mixed-body').innerHTML = `<div class="mixed-result ${verdict.kind}"><div class="mixed-verdict"><span class="eyebrow">${recorded ? 'RECORDED' : 'EXACT'} JOINT RESULT</span><h3>${esc(verdict.title)}</h3><p>${esc(verdict.detail)}</p></div><div class="mixed-exploration"><div><div class="mixed-block-heading"><span class="eyebrow">THE BUDGET FRONTIER</span><p>Choose a cell to inspect an attaining witness.</p></div><div class="mixed-frontier" role="group" aria-label="Group and additional-record withdrawal budgets">${c.results.map(row => `<button type="button" class="mixed-cell ${row.robust ? 'robust' : 'fragile'}" data-mixed-cell="${cellKey(row)}" aria-pressed="${cellKey(row) === this.selectedCell}"><span class="mixed-cell-budget">${row.group_budget} ${row.group_budget === 1 ? 'group' : 'groups'} + ${row.edge_budget} ${row.edge_budget === 1 ? 'record' : 'records'}</span><strong>${rank(row.worst_supported_rank)}</strong><span>Worst supported rank</span><small>${row.unsupported_attainable ? 'Support loss possible' : row.robust ? `Holds in top ${c.top_k}` : 'Can leave the shortlist'}</small></button>`).join('')}</div><p class="mixed-fine">Budgets mean “at most.” A record already removed by the group cannot use the additional-record budget. Different cells may have different worst-case witnesses.</p></div><div><div id="mixed-witness-tabs"></div><div id="mixed-witness"></div></div></div><div class="mixed-actions"><div><span class="eyebrow">REPLAY THE CLAIM</span><p>${number(c.proof.covered_action_representations)} action representations covered. Several may produce the same edited graph; this count is not a measured speedup.</p></div><div><button type="button" id="mixed-verify" data-mixed-action="verify" class="button button-outline"></button><button type="button" data-mixed-action="download" class="button button-outline">Certificate ${icon('download')}</button></div></div><div id="mixed-verification" aria-live="polite"></div><details class="mixed-proof"><summary>Scope, identities & limitations ${icon('chevron')}</summary><p>${esc(objectText(c.interpretation))}</p><p>${number(c.scope.eligible_group_count)} selected source annotations · ${number(c.scope.eligible_edge_count)} binding records · ${number(c.scope.candidate_count)} competing compounds. An annotation does not establish independent corroboration or biological truth.</p><dl>${Object.entries(c.identity).map(([key, value]) => `<dt>${esc(key)}</dt><dd><code>${esc(value)}</code></dd>`).join('')}<dt>Certificate SHA-256</dt><dd><code>${esc(c.certificate_sha256)}</code></dd></dl><a class="text-link" href="https://github.com/Azzbee/ariadne-bio/blob/main/docs/mixed_audit_proof.md" target="_blank" rel="noopener noreferrer">Read the conditional-envelope proof ↗</a></details></div>`;
    this.renderWitness();
  }
  renderWitness() {
    const c = this.session.certificate; if (!c) return;
    const row = c.results.find(item => cellKey(item) === this.selectedCell); if (!row) return;
    const active = this.element.ownerDocument?.activeElement;
    const restoreWitnessFocus = active?.matches?.('[data-mixed-witness]') ? active.dataset.mixedWitness : null;
    const choices = [['rank', 'Worst supported rank', row.rank_witness], ['unsupported', 'Loss of support', row.unsupported_witness]].filter(([, , witness]) => witness);
    if (!choices.some(([key]) => key === this.witnessKind)) this.witnessKind = choices[0]?.[0] || 'rank';
    this.find('mixed-witness-tabs').innerHTML = `<div class="mixed-witness-tabs" role="group" aria-label="Joint witness outcome">${choices.map(([key, label]) => `<button type="button" data-mixed-witness="${key}" aria-pressed="${key === this.witnessKind}">${label}</button>`).join('')}</div>`;
    const witness = this.witnessKind === 'unsupported' ? row.unsupported_witness : row.rank_witness;
    this.find('mixed-witness').innerHTML = mixedWitnessHTML(c, witness);
    this.element.querySelectorAll('[data-mixed-cell]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mixedCell === this.selectedCell)));
    if (restoreWitnessFocus) this.element.querySelector(`[data-mixed-witness="${restoreWitnessFocus}"]`)?.focus({ preventScroll: true });
    this.announce(`${row.group_budget} group and ${row.edge_budget} additional record budget. Worst supported rank ${rank(row.worst_supported_rank)}. Support loss ${row.unsupported_attainable ? 'possible' : 'not attainable'}.`);
  }
  renderVerification() {
    const element = this.find('mixed-verification'); if (!element) return;
    const s = this.session;
    if (s.verifying) { element.innerHTML = '<p>Checking the joint certificate…</p>'; return; }
    if (s.verificationError) { element.innerHTML = `<div class="mixed-error" role="alert"><strong>Verification could not complete.</strong><p>${esc(errorText(s.verificationError))}</p></div>`; return; }
    if (!s.verification) { element.innerHTML = ''; return; }
    const result = s.verification, recorded = this.api.mode === 'snapshot';
    element.innerHTML = `<div class="mixed-verification ${result.valid ? 'verified' : 'invalid'}"><strong>${result.valid ? recorded ? 'Matches a verified recorded joint certificate.' : 'Joint certificate verified.' : 'Certificate verification failed.'}</strong><p>${recorded ? 'The exact recorded certificate and its stored verification match. No solver or graph replay ran in the browser.' : 'The server recomputed the conditional rank envelopes and separately replayed witnesses using edited matrices. This does not certify biological validity.'}</p>${result.errors.length ? `<ul>${result.errors.map(error => `<li>${esc(error)}</li>`).join('')}</ul>` : ''}<details><summary>${result.checks.length} ${recorded ? 'recorded' : 'completed'} checks</summary><ul>${result.checks.map(check => `<li>${esc(check)}</li>`).join('')}</ul><p>${esc(objectText(result.verification_method))}</p></details></div>`;
  }
  download() {
    const c = this.session.exportCertificate(); if (!c) return false;
    const name = value => String(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    const blob = new Blob([JSON.stringify(c, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = `ariadne-${name(c.disease.name)}-${name(c.compound.name)}-joint-audit.json`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    this.callbacks.onNotice?.('Complete joint certificate exported with its declared scope and identity.'); return true;
  }
}

export function mixedWitnessHTML(c, witness) {
  if (!witness) return '<p class="mixed-fine">No attaining witness exists for this outcome.</p>';
  const labels = witness.group_ids.map(id => c.scope.groups.find(group => group.group_id === id)?.label || id);
  return `<article class="mixed-witness"><span class="eyebrow">AN ATTAINING WITHDRAWAL</span><div class="mixed-withdrawals"><div><span>Source group</span><strong>${labels.length ? esc(labels.join(' + ')) : 'No group withdrawn'}</strong></div><div><span>Additional surviving record</span><code>${witness.residual_edge_ids.length ? esc(witness.residual_edge_ids.join(', ')) : 'No additional record'}</code></div></div><div class="mixed-before-after"><div><span>Baseline</span><strong>${rank(witness.focus.before.rank)}</strong><small>${number(witness.focus.before.evidence_count)} paths</small></div><span aria-hidden="true">→</span><div><span>After withdrawal</span><strong>${rank(witness.focus.after.rank)}</strong><small>${number(witness.focus.after.evidence_count)} paths</small></div></div><p class="mixed-impact">${number(witness.removed_edge_count)} binding records removed · ${number(witness.affected_compound_count)} compounds affected.</p><details class="mixed-records"><summary>Inspect ${witness.preview_truncated ? 'record preview' : 'removed records'} ${icon('chevron')}</summary>${witness.removed_edges_preview.length ? witness.removed_edges_preview.map(edge => `<article><strong>${esc(edge.source)} → ${esc(edge.target)}</strong><code>${esc(edge.id)}</code><p>Imported sources: ${esc(Array.isArray(edge.sources) ? edge.sources.join(', ') : 'Not recorded')}</p></article>`).join('') : '<p>No records were removed.</p>'}${witness.preview_truncated ? '<p>This is a preview of at most six records. The complete union is bound by its count and SHA-256 below.</p>' : ''}<p class="mixed-fine">Removed-record union SHA-256</p><code>${esc(witness.removed_edge_ids_sha256)}</code></details></article>`;
}
