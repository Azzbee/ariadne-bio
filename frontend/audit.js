import { AuditSession, auditVerdict, defaultWitnessKind, metadataList, witnessChanges, witnessFor } from './audit-model.js';
import { escapeHTML as esc, number, objectText, safeURL, sourceEntries } from './utils.js';

const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const rank = value => value === null || value === undefined ? 'No supported rank' : `#${number(value)}`;
const numericScore = value => Number.isFinite(value) ? value.toFixed(6) : '—';
const plural = value => value === 1 ? 'record' : 'records';
const message = error => error?.message || 'The audit could not be completed. Please try again.';
const slug = value => String(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

function recordHTML(edge, index) {
  const sources = sourceEntries(edge.sources || edge.data?.sources).map(item => item.name);
  const publications = [...new Set(metadataList(edge.data?.pubmed_ids).map(String).filter(id => /^\d+$/.test(id)))];
  const external = metadataList(edge.data?.urls).map(value => safeURL(value)).filter(Boolean);
  const actions = metadataList(edge.data?.actions);
  return `<article class="audit-record"><div class="audit-record-number">${String(index + 1).padStart(2, '0')}</div><div class="audit-record-content">
    <div class="audit-record-chain"><strong>${esc(edge.source_name || edge.source)}</strong><span>BINDS →</span><strong>${esc(edge.target_name || edge.target)}</strong></div>
    <p>${esc(sources.join(' · ') || 'Source not specified in the imported record')}</p>
    <details class="audit-record-details"><summary>Inspect source record ${icon('chevron')}</summary><dl>
      <dt>Record ID</dt><dd><code>${esc(edge.id)}</code></dd><dt>Source entity</dt><dd>${esc(edge.source)}</dd><dt>Target entity</dt><dd>${esc(edge.target)}</dd>
      <dt>Imported license</dt><dd>${esc(objectText(edge.license || edge.data?.license) || 'Not specified')}</dd>
      ${actions.length ? `<dt>Imported actions</dt><dd>${esc(objectText(actions))}</dd>` : ''}
      ${publications.length ? `<dt>Imported references</dt><dd class="audit-reference-links">${publications.map(id => `<a href="https://pubmed.ncbi.nlm.nih.gov/${id}/" target="_blank" rel="noopener noreferrer">PMID ${esc(id)} ↗</a>`).join('')}</dd>` : ''}
      ${external.length ? `<dt>Source links</dt><dd>${external.map((url, i) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Source record ${i + 1} ↗</a>`).join('<br>')}</dd>` : ''}
    </dl><p>Source names and imported references are provenance, not a count of independent studies. Withdrawing this consolidated record is a hypothetical data change.</p><details><summary>Complete imported metadata</summary><pre>${esc(JSON.stringify(edge, null, 2))}</pre></details></details>
  </div></article>`;
}

function proofHTML(certificate) {
  const { scope, identity, proof, baseline } = certificate;
  return `<details class="audit-proof"><summary><span>${icon('shield')} Scope, arithmetic & proof</span><span class="audit-proof-stamp">${number(scope.eligible_edges)} eligible records</span></summary><div class="audit-proof-body">
    <p>This certificate covers withdrawal of any set of at most <strong>${certificate.budget} recorded BINDS ${plural(certificate.budget)}</strong> across <strong>all ${number(scope.candidate_count)} compounds</strong>. Other relationship families and the fitted model stay fixed. Rank uses the declared canonical scorer and compound-ID tie breaking.</p>
    <dl class="audit-proof-metrics"><div><dt>Local states evaluated</dt><dd>${number(proof.local_states_evaluated)}</dd></div><div><dt>Global states covered by the envelope</dt><dd>${number(proof.covered_global_states)}</dd></div><div><dt>Envelope search budget</dt><dd>0–${proof.search_budget} withdrawals</dd></div></dl>
    <p>The bounds cover combinations through the envelope; the solver does not independently rebuild every global graph. The displayed verdict is restricted to your requested budget. Losing all support is reported separately from a numerical rank.</p>
    <p class="audit-scope-limit">The guarantee does not extend to other edge families, source-wide or correlated failures, added records, model refitting, or a larger withdrawal budget. It is a statement about this graph and model, not about biological truth or drug efficacy.</p>
    <dl class="audit-identity"><dt>Canonical scorer</dt><dd><code>${esc(identity.scorer)}</code></dd><dt>Explorer comparison</dt><dd>Explorer rank ${rank(baseline.legacy_rank)} · score difference ${esc(Number.isFinite(baseline.score_difference) ? baseline.score_difference.toExponential(3) : 'not recorded')}. The certificate uses its own declared arithmetic.</dd>
      <dt>Certificate SHA-256</dt><dd><code>${esc(certificate.certificate_sha256)}</code></dd><dt>Envelope SHA-256</dt><dd><code>${esc(proof.envelope_bounds_sha256)}</code></dd>
      <dt>Graph SHA-256</dt><dd><code>${esc(identity.graph_sha256)}</code></dd><dt>Model SHA-256</dt><dd><code>${esc(identity.model_sha256)}</code></dd><dt>Dataset SHA-256</dt><dd><code>${esc(identity.dataset_sha256)}</code></dd></dl>
    <p class="audit-interpretation">${esc(certificate.interpretation)}</p><button type="button" class="text-link" data-audit-action="method">Read the method & research scope ${icon('arrow')}</button>
  </div></details>`;
}

function boundsHTML(certificate, selectedBudget) {
  const rows = certificate.results.map(row => `<tr${row.budget === selectedBudget ? ' class="selected"' : ''}>
    <th scope="row">${row.budget === 0 ? 'Baseline' : 'Up to ' + row.budget}</th>
    <td>${rank(row.worst_supported_rank)}</td><td>${row.unsupported_attainable ? 'Possible' : 'Not possible'}</td>
    <td><span class="audit-table-status ${row.top_k_robust ? 'robust' : 'fragile'}">${row.top_k_robust ? 'Preserved' : 'Not preserved'}</span></td>
    <td><button type="button" class="audit-inspect" data-audit-budget="${row.budget}" aria-label="Inspect witness for budget ${row.budget}" aria-pressed="${row.budget === selectedBudget}">Inspect <span aria-hidden="true">↗</span></button></td></tr>`).join('');
  return `<div class="audit-bounds"><div class="audit-block-heading"><span class="eyebrow">EVERY BUDGET, ONE FIXED MODEL</span><h3>Where the guarantee ends</h3></div><div class="audit-table-scroll" tabindex="0" role="region" aria-label="Exact audit bounds by budget"><table class="audit-bounds-table"><caption class="sr-only">Global bounds for ${esc(certificate.compound.name)} in the top ${certificate.top_k}</caption><thead><tr><th scope="col">Withdrawals</th><th scope="col">Worst supported rank</th><th scope="col">Loss of support</th><th scope="col">Top ${certificate.top_k}</th><th scope="col"><span class="sr-only">Inspect witness</span></th></tr></thead><tbody>${rows}</tbody></table></div><p>“Worst” includes changes to rivals. Every row permits any set of records within that budget.</p></div>`;
}

function witnessHTML(certificate, selectedBudget, selectedKind) {
  const row = certificate.results.find(item => item.budget === selectedBudget);
  const witness = witnessFor(certificate, selectedBudget, selectedKind);
  const tabs = [
    row.rank_witness ? `<button type="button" data-audit-witness="rank" aria-pressed="${selectedKind === 'rank'}">Worst supported rank</button>` : '',
    row.unsupported_witness ? `<button type="button" data-audit-witness="unsupported" aria-pressed="${selectedKind === 'unsupported'}">Loss of support</button>` : ''
  ].join('');
  if (!witness) return `<div class="audit-witness"><div class="audit-block-heading"><span class="eyebrow">BUDGET ${selectedBudget}</span><h3>No supported witness</h3></div><p>No supported state is available for this result. A missing rank is not replaced by an artificial last place.</p></div>`;
  const changes = witnessChanges(certificate, witness);
  return `<div class="audit-witness"><div class="audit-witness-heading"><div><span class="eyebrow">ATTAINING WITNESS · BUDGET ${selectedBudget}</span><h3>${witness.deletions_used ? `Withdraw ${witness.deletions_used} specific ${plural(witness.deletions_used)}.` : 'The unmodified graph.'}</h3><p>${selectedKind === 'unsupported' ? 'This set removes every supporting path for the selected pair.' : `This set attains the global supported-rank bound: ${rank(witness.focus.rank)}.`}</p></div><div class="audit-witness-tabs" role="group" aria-label="Witness outcome">${tabs}</div></div>
    <div class="audit-witness-grid"><div class="audit-record-list">${witness.removed_records.length ? witness.removed_records.map(recordHTML).join('') : '<div class="audit-empty-witness"><span>0</span><p>No binding records are withdrawn in this witness.</p></div>'}</div>
    <div class="audit-rivals"><span class="eyebrow">RECOMPUTED BEFORE & AFTER</span><div class="audit-table-scroll" tabindex="0" role="region" aria-label="Compound changes in this witness"><table><caption class="sr-only">Selected compound and affected rivals under this witness</caption><thead><tr><th scope="col">Compound</th><th scope="col">Baseline</th><th scope="col">Witness</th></tr></thead><tbody>${changes.map(item => `<tr${item.role === 'focus' ? ' class="focus"' : ''}><th scope="row">${esc(item.name)}<small>${item.role === 'focus' ? 'SELECTED COMPOUND' : 'COMPETITOR'}${item.removed_edge_ids?.length ? ` · ${item.removed_edge_ids.length} ${plural(item.removed_edge_ids.length)} withdrawn` : ''}</small></th><td>${rank(item.before.rank)}<small>${numericScore(item.before.score)}</small></td><td>${rank(item.after.rank)}<small>${numericScore(item.after.score)}${item.after.supported ? '' : ' · diagnostic'}</small></td></tr>`).join('')}</tbody></table></div>
    <p class="audit-rival-note">Ranks reflect the full candidate universe; small figures are model scores. The table identifies the focus and compounds whose records were withdrawn.</p><div class="audit-witness-count"><strong>${number(witness.focus.evidence_count)}</strong><span>supporting paths remain for ${esc(certificate.compound.name)}</span></div></div></div>
  </div>`;
}

export class AuditPanel {
  constructor(element, api, callbacks = {}) {
    this.element = element;
    this.api = api;
    this.callbacks = callbacks;
    this.externalLoading = false;
    this.excluded = [];
    this.selectedBudget = 2;
    this.selectedKind = 'rank';
    this.renderedCertificate = null;
    this.renderedState = null;
    this.element.innerHTML = `<div class="audit-heading"><div class="audit-intro"><span class="eyebrow">04 / AUDIT THE SHORTLIST</span><h2 id="audit-title">Would this rank survive?</h2><p>Withdraw up to two binding records anywhere in the graph. Find the exact worst rank, including changes to rival compounds.</p><div id="audit-focus" class="audit-focus">Choose a compound to begin.</div></div>
      <form id="audit-form" class="audit-form" aria-describedby="audit-scope-note"><label for="audit-top-k">Shortlist<select id="audit-top-k"><option value="1">Top 1</option><option value="5">Top 5</option><option value="10" selected>Top 10</option></select></label><label for="audit-budget">Maximum withdrawals<select id="audit-budget"><option value="0">0 · baseline only</option><option value="1">1 record</option><option value="2" selected>2 records</option></select></label><button type="submit" id="audit-run" class="button button-dark" disabled>${icon('shield')}<span>Audit shortlist</span></button></form></div>
      <div class="audit-scope-strip"><p id="audit-scope-note"><strong>FULL-GRAPH BASELINE</strong><span>All recorded BINDS edges · every compound · fixed model</span></p><span id="audit-edition" class="audit-edition">Awaiting graph connection</span></div>
      <p id="audit-exclusion-note" class="audit-exclusion-note" hidden></p><div id="audit-body" class="audit-body"></div><p id="audit-status" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>`;
    this.session = new AuditSession(api, () => this.render());
    this.element.querySelector('#audit-form').addEventListener('submit', event => {
      event.preventDefault();
      this.run();
    });
    for (const id of ['audit-top-k', 'audit-budget']) this.element.querySelector(`#${id}`).addEventListener('change', () => {
      this.session.setParameters(Number(this.find('audit-top-k').value), Number(this.find('audit-budget').value));
      this.callbacks.onParameters?.();
    });
    this.element.addEventListener('click', event => this.handleClick(event));
    this.render();
  }

  find(id) { return this.element.querySelector(`#${id}`); }

  configure({ topK, budget }) {
    if (![1, 5, 10].includes(topK) || ![0, 1, 2].includes(budget)) throw new Error('Unsupported audit controls.');
    this.find('audit-top-k').value = String(topK);
    this.find('audit-budget').value = String(budget);
    this.session.setParameters(topK, budget);
  }

  async run() {
    if (!this.externalLoading && !this.session.busy) return this.session.run();
    return null;
  }

  setContext({ disease, candidate, excluded = [], loading = false }) {
    this.externalLoading = loading;
    this.excluded = excluded;
    this.session.setFocus(disease, candidate);
    this.renderControls();
  }

  focus() {
    // A toolbar jump must settle before the next pointerdown/up targets the form.
    this.element.scrollIntoView({ behavior: 'instant', block: 'start' });
    this.find('audit-run').focus({ preventScroll: true });
  }

  renderControls() {
    const session = this.session;
    const disabled = this.externalLoading || !session.disease || !session.compound;
    this.find('audit-run').disabled = disabled || session.busy;
    const runLabel = session.busy ? 'busy' : 'ready';
    if (this.find('audit-run').dataset.state !== runLabel) {
      this.find('audit-run').dataset.state = runLabel;
      this.find('audit-run').innerHTML = session.busy ? '<span class="spinner"></span><span>Auditing…</span>' : `${icon('shield')}<span>Audit shortlist</span>`;
    }
    this.find('audit-top-k').disabled = disabled;
    this.find('audit-budget').disabled = disabled;
    this.find('audit-focus').textContent = session.compound && session.disease ? `${session.compound.name} / ${session.disease.name}` : 'Choose a compound to begin.';
    this.find('audit-edition').textContent = this.api.mode === 'snapshot' ? 'RECORDED CERTIFICATES' : this.api.mode === 'live' ? 'LIVE EXACT AUDIT' : 'Awaiting graph connection';
    this.find('audit-exclusion-note').hidden = !this.excluded.length;
    this.find('audit-exclusion-note').textContent = `The explorer currently excludes ${this.excluded.join(', ')}. This audit starts from the unmodified graph and does not inherit those switches.`;
    this.find('audit-body').setAttribute('aria-busy', String(session.busy));
    const replay = this.find('audit-replay');
    if (replay) {
      replay.disabled = session.verifying || session.busy;
      replay.innerHTML = `${session.verifying ? '<span class="spinner"></span>' : icon('reset')}<span>${session.verifying ? 'Checking…' : this.api.mode === 'snapshot' ? 'View recorded verification' : 'Replay certificate'}</span>`;
    }
  }

  render() {
    const session = this.session;
    this.renderControls();
    const stateKey = session.busy ? 'busy' : session.error ? 'error' : session.certificate ? 'certificate' : 'empty';
    if (stateKey !== this.renderedState || session.certificate !== this.renderedCertificate) {
      this.renderedState = stateKey;
      this.renderedCertificate = session.certificate;
      if (stateKey === 'busy') {
        this.find('audit-body').innerHTML = `<div class="audit-loading"><span class="spinner"></span><div><strong>${this.api.mode === 'snapshot' ? 'Loading the recorded certificate' : 'Computing the global binding envelope'}</strong><p>${this.api.mode === 'snapshot' ? 'The published certificate records an executed exact audit.' : 'The selected compound and its competitors are included. The model stays fixed.'}</p></div></div>`;
        this.announce('Shortlist audit in progress.');
      } else if (stateKey === 'error') {
        this.find('audit-body').innerHTML = `<div class="audit-error" role="alert"><strong>Audit unavailable</strong><p>${esc(message(session.error))}</p><button type="button" data-audit-action="retry" class="button button-outline">Try again</button></div>`;
        this.announce('The audit could not be completed.');
      } else if (stateKey === 'certificate') {
        this.selectedBudget = session.budget;
        this.selectedKind = defaultWitnessKind(session.certificate.results.at(-1), session.topK);
        this.renderCertificate();
        const verdict = auditVerdict(session.certificate);
        this.announce(`${session.certificate.compound.name}. ${verdict.title}. Worst supported rank: ${rank(session.certificate.results.at(-1).worst_supported_rank)}. ${session.certificate.results.at(-1).unsupported_attainable ? 'Loss of support is possible.' : 'Support remains within this budget.'}`);
      } else {
        this.find('audit-body').innerHTML = '';
        this.announce('');
      }
    }
    this.renderControls();
    this.renderVerification();
  }

  announce(value) { this.find('audit-status').textContent = value; }

  renderCertificate() {
    const c = this.session.certificate;
    if (!c) return;
    const verdict = auditVerdict(c), row = c.results.at(-1);
    this.find('audit-body').innerHTML = `<div class="audit-result ${verdict.kind}"><div class="audit-verdict"><div><span class="audit-verdict-label">${icon('shield')} ${this.api.mode === 'snapshot' ? 'RECORDED EXACT RESULT' : 'EXACT BOUNDED RESULT'}</span><h3>${esc(verdict.title)}</h3><p>${esc(verdict.summary)}</p></div><div class="audit-budget-mark" aria-hidden="true"><span>UP TO</span><strong>${c.budget}</strong><span>WITHDRAWALS</span></div></div>
      ${!c.baseline.rank_agrees_with_legacy ? `<p class="audit-arithmetic-note">The canonical audit baseline is ${rank(c.baseline.rank)}; the explorer reports ${rank(c.baseline.legacy_rank)}. This certificate consistently uses its fixed-order scorer and tie rule. See the proof details.</p>` : ''}
      <div class="audit-metrics"><div><span>Baseline rank</span><strong>${rank(c.baseline.rank)}</strong><small>Canonical audit scoring</small></div><div><span>Worst supported rank</span><strong>${rank(row.worst_supported_rank)}</strong><small>Across the full binding universe</small></div><div><span>Support can vanish</span><strong>${row.unsupported_attainable ? 'Yes' : 'No'}</strong><small>Reported independently of rank</small></div><div><span>Minimum failure budget</span><strong>${c.minimum_failure_budget === null ? `None ≤ ${c.budget}` : c.minimum_failure_budget}</strong><small>${c.minimum_failure_budget === 0 ? 'Outside the shortlist at baseline' : 'Within the requested scope'}</small></div></div>
      <div class="audit-analysis-grid">${boundsHTML(c, this.selectedBudget)}<div class="audit-competition"><div class="audit-block-heading"><span class="eyebrow">WHY RIVALS MATTER</span><h3>Challenge the whole ranking.</h3></div><div class="audit-rank-comparison"><div><span>Selected compound only</span><strong>${rank(row.focus_only_worst_rank)}</strong><small>${row.focus_only_unsupported_attainable ? 'Support can also vanish' : 'Support retained within budget'}</small></div><div class="global"><span>Any compound’s records</span><strong>${rank(row.worst_supported_rank)}</strong><small>${row.unsupported_attainable ? 'Support can also vanish' : 'Support retained within budget'}</small></div></div><p>${row.competitor_rank_gap > 0 ? `Allowing withdrawals on rivals worsens the supported-rank bound by ${number(row.competitor_rank_gap)} ${row.competitor_rank_gap === 1 ? 'place' : 'places'}.` : 'The supported-rank bounds coincide in this case. Rivals are still included in the global audit.'} Removing evidence can raise a rival’s score, so a focus-only check is a narrower question.</p></div></div>
      <div id="audit-witness-area">${witnessHTML(c, this.selectedBudget, this.selectedKind)}</div>
      <div class="audit-certificate-actions"><div><span class="eyebrow">KEEP A REPLAYABLE RECORD</span><p>Export the complete, unchanged certificate. ${this.api.mode === 'snapshot' ? 'Verification below was executed when this snapshot was prepared.' : 'Replay rechecks the envelope and witness using the server’s graph and model.'}</p></div><div><button type="button" id="audit-replay" data-audit-action="verify" class="button button-outline"></button><button type="button" data-audit-action="export" class="button button-dark">${icon('download')} Export certificate</button></div></div><div id="audit-verification" class="audit-verification" aria-live="polite"></div>
      ${proofHTML(c)}<p class="audit-bottom-note">Exact for the declared graph, scorer, and withdrawal budget. A hypothetical record withdrawal makes no assertion that the record is false or that a compound is effective.</p></div>`;
    this.renderControls();
    this.renderVerification();
  }

  renderVerification() {
    const container = this.find('audit-verification');
    if (!container) return;
    const { verifying, verification, verificationError } = this.session;
    if (verifying) { container.innerHTML = '<p class="audit-verification-pending">Checking the certificate…</p>'; return; }
    if (verificationError) { container.innerHTML = `<div class="audit-verification-result invalid" role="alert"><strong>Verification could not complete.</strong><p>${esc(message(verificationError))}</p></div>`; return; }
    if (!verification) { container.innerHTML = ''; return; }
    const recorded = this.api.mode === 'snapshot';
    const title = verification.valid ? recorded ? 'Matches a verified recorded certificate.' : 'Certificate replay verified.' : 'Certificate verification failed.';
    container.innerHTML = `<div class="audit-verification-result ${verification.valid ? 'verified' : 'invalid'}"><strong>${esc(title)}</strong><p>${recorded ? 'This browser compared the envelope with the published certificate and loaded its recorded verification. No graph recomputation ran here.' : 'The server checked the certificate against its data and fixed model. This verifies hashes and mathematics, not independent scientific authority.'}</p>${verification.errors.length ? `<ul>${verification.errors.map(item => `<li>${esc(item)}</li>`).join('')}</ul>` : ''}<details><summary>${verification.checks.length} ${recorded ? 'recorded checks' : 'checks passed'} · inspect verification</summary><ul>${verification.checks.map(item => `<li>${esc(item)}</li>`).join('')}</ul><p>${esc(objectText(verification.verification_method))}</p>${verification.generated_at ? `<p>Recorded at ${esc(verification.generated_at)}</p>` : ''}</details></div>`;
  }

  handleClick(event) {
    const budgetButton = event.target.closest('[data-audit-budget]');
    if (budgetButton && this.session.certificate) {
      this.selectedBudget = Number(budgetButton.dataset.auditBudget);
      this.selectedKind = defaultWitnessKind(this.session.certificate.results[this.selectedBudget], this.session.topK);
      this.renderWitness();
      return;
    }
    const witnessButton = event.target.closest('[data-audit-witness]');
    if (witnessButton && this.session.certificate) {
      this.selectedKind = witnessButton.dataset.auditWitness;
      this.renderWitness();
      this.element.querySelector(`[data-audit-witness="${this.selectedKind}"]`)?.focus({ preventScroll: true });
      return;
    }
    const action = event.target.closest('[data-audit-action]')?.dataset.auditAction;
    if (action === 'retry' && !this.externalLoading) this.session.run();
    if (action === 'verify') this.session.verify();
    if (action === 'export') this.exportCertificate();
    if (action === 'method') this.callbacks.onMethod?.();
  }

  renderWitness() {
    const c = this.session.certificate;
    this.find('audit-witness-area').innerHTML = witnessHTML(c, this.selectedBudget, this.selectedKind);
    this.element.querySelectorAll('[data-audit-budget]').forEach(button => {
      const selected = Number(button.dataset.auditBudget) === this.selectedBudget;
      button.setAttribute('aria-pressed', String(selected));
      button.closest('tr').classList.toggle('selected', selected);
    });
    const witness = witnessFor(c, this.selectedBudget, this.selectedKind);
    this.announce(`Witness for budget ${this.selectedBudget}. ${witness ? `${witness.deletions_used} records withdrawn; ${rank(witness.focus.rank)}.` : 'No witness available.'}`);
  }

  exportCertificate() {
    try {
      const certificate = this.session.exportCertificate();
      if (!certificate) return;
      const url = URL.createObjectURL(new Blob([JSON.stringify(certificate, null, 2) + '\n'], { type: 'application/json' }));
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `ariadne-${slug(certificate.disease.name)}-${slug(certificate.compound.name)}-top${certificate.top_k}-budget${certificate.budget}-certificate.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      this.callbacks.onNotice?.('The complete audit certificate is ready, including scope, witness records, and graph/model identities.');
    } catch (error) { this.callbacks.onNotice?.(message(error)); }
  }
}
