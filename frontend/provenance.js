import { ProvenanceSession, provenanceDossier, provenanceVerdict } from './provenance-model.js';
import { RequestGate } from './investigation.js';
import { escapeHTML as esc, number, objectText, sourceEntries } from './utils.js';

const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const rank = value => value === null ? 'No supported rank' : `#${number(value)}`;
const errorText = error => error?.message || 'The shared-dependency audit could not complete.';
const labelFor = (certificate, id) => certificate.scope.groups.find(group => group.group_id === id)?.label || id;
const slug = value => String(value).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const exportName = (c, suffix) => `ariadne-${slug(c.disease.name)}-${slug(c.compound.name)}-${c.scope.group_kind}-budget${c.budget}-${suffix}`;

/** Native modal review; the embedded document has no script or external-resource permission. */
export function openDossierDialog({ html, title, downloadName = 'ariadne-review.html', documentObject = document, restoreFocus = documentObject.activeElement }) {
  const dialog = documentObject.createElement('dialog');
  dialog.className = 'dependency-dossier-dialog';
  dialog.setAttribute('aria-labelledby', 'dependency-review-title');
  dialog.setAttribute('aria-describedby', 'dependency-review-description');
  const header = documentObject.createElement('div'); header.className = 'dependency-dossier-header';
  const heading = documentObject.createElement('div');
  const titleElement = documentObject.createElement('h2'); titleElement.id = 'dependency-review-title'; titleElement.textContent = title;
  const description = documentObject.createElement('p'); description.id = 'dependency-review-description';
  description.textContent = 'Review the exact scope, evidence and assumptions before printing or exporting. The preview is a static document.';
  heading.append(titleElement, description);
  const controls = documentObject.createElement('div'); controls.className = 'dependency-dossier-controls';
  const print = documentObject.createElement('button'); print.type = 'button'; print.className = 'button button-outline'; print.textContent = 'Print'; print.disabled = true;
  const download = documentObject.createElement('a'); download.className = 'button button-dark'; download.textContent = 'Download HTML'; download.download = downloadName;
  const close = documentObject.createElement('button'); close.type = 'button'; close.className = 'button button-quiet'; close.textContent = 'Close'; close.setAttribute('aria-label', 'Close review dossier');
  controls.append(print, download, close); header.append(heading, controls);
  const frame = documentObject.createElement('iframe'); frame.className = 'dependency-dossier-frame'; frame.title = `${title} — document preview`;
  frame.setAttribute('sandbox', 'allow-same-origin allow-modals');
  frame.setAttribute('referrerpolicy', 'no-referrer');
  frame.addEventListener('load', () => { print.disabled = false; });
  frame.srcdoc = html;
  const status = documentObject.createElement('p'); status.className = 'dependency-dossier-status'; status.setAttribute('role', 'status');
  status.textContent = 'The document contains the complete certificate. Printing excludes the raw JSON appendix.';
  let downloadURL = null;
  try {
    downloadURL = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
    download.href = downloadURL;
  } catch {
    download.setAttribute('aria-disabled', 'true');
    status.textContent = 'The HTML export could not be prepared. The preview remains available.';
  }
  print.addEventListener('click', () => {
    if (print.disabled) return;
    try { frame.contentWindow.focus(); frame.contentWindow.print(); }
    catch { status.textContent = 'The browser could not open its print dialog. The preview remains available for review.'; }
  });
  download.addEventListener('click', event => {
    if (!downloadURL) { event.preventDefault(); return; }
    // The visible link performs its own native download; do not synthesize a second click.
    status.textContent = 'HTML prepared; check your browser’s downloads.';
  });
  close.addEventListener('click', () => dialog.close());
  dialog.addEventListener('cancel', event => { event.preventDefault(); dialog.close(); });
  dialog.addEventListener('close', () => {
    frame.remove(); dialog.remove();
    // Keep the URL available while the link is visible, then allow an in-flight download to start.
    if (downloadURL) { const url = downloadURL; downloadURL = null; setTimeout(() => URL.revokeObjectURL(url), 30000); }
    if (restoreFocus?.isConnected) restoreFocus.focus({ preventScroll: true });
  });
  dialog.append(header, frame, status); documentObject.body.append(dialog); dialog.showModal(); close.focus({ preventScroll: true });
  return dialog;
}

function witnessHTML(c, row, kind) {
  const witness = kind === 'unsupported' ? row.unsupported_witness : row.rank_witness;
  if (!witness) return '<p>No attaining witness exists for this outcome.</p>';
  return `<div class="dependency-witness"><div class="dependency-witness-heading"><div><span class="eyebrow">ATTAINING GROUP WITHDRAWAL</span><h4>${witness.group_ids.length ? witness.group_ids.map(id => esc(labelFor(c, id))).join(' + ') : 'The unmodified graph'}</h4><p>${kind === 'unsupported' ? 'These groups can remove every supporting path.' : `This scenario attains supported rank ${rank(witness.focus.after.rank)}.`}</p></div><div class="dependency-impact"><strong>${number(witness.removed_edge_count)}</strong><span>distinct binding records</span><strong>${number(witness.affected_compound_count)}</strong><span>compounds with records removed</span></div></div><div class="dependency-before-after"><div><span>Selected compound before</span><strong>${rank(witness.focus.before.rank)}</strong><small>${number(witness.focus.before.evidence_count)} supporting paths</small></div><span aria-hidden="true">→</span><div><span>Selected compound after</span><strong>${rank(witness.focus.after.rank)}</strong><small>${number(witness.focus.after.evidence_count)} supporting paths</small></div></div><details class="dependency-records"><summary>${witness.removed_edges_preview.length} ${witness.preview_truncated ? 'example' : 'removed'} records · inspect provenance ${icon('chevron')}</summary><p>${witness.preview_truncated ? `This is a bounded preview of ${number(witness.removed_edge_count)} distinct records. Verification reconstructs and checks the complete union.` : 'The complete removed-record set fits in this preview.'} An overlapping record is removed once.</p>${witness.removed_edges_preview.map(edge => `<article><strong>${esc(edge.source_name || edge.source)} <span>BINDS →</span> ${esc(edge.target_name || edge.target)}</strong><p>${esc(sourceEntries(edge.sources || edge.data?.sources).map(item => item.name).join(' · ') || 'No source label imported')}</p><code>${esc(edge.id)}</code><details><summary>Complete imported record</summary><pre>${esc(JSON.stringify(edge, null, 2))}</pre></details></article>`).join('')}<p class="dependency-digest">Complete union identifier SHA-256: <code>${esc(witness.removed_edge_ids_sha256)}</code></p></details></div>`;
}

function protectionHTML(c, live) {
  const plan = c.protection_plan;
  if (plan.status === 'impossible_baseline') return '<div class="dependency-protection"><span class="eyebrow">CONDITIONAL REVIEW PRIORITY</span><h3>The baseline must qualify first.</h3><p>This compound starts without support or outside the shortlist. Declaring groups unavailable for withdrawal cannot change that baseline.</p></div>';
  if (plan.status === 'already_robust') return '<div class="dependency-protection"><span class="eyebrow">CONDITIONAL REVIEW PRIORITY</span><h3>No additional protected groups needed.</h3><p>The selected compound already survives every allowed scenario. This conditional ranking result does not establish that its evidence or biological hypothesis is correct.</p></div>';
  return `<div class="dependency-protection"><span class="eyebrow">CONDITIONAL REVIEW PRIORITY</span><h3>${plan.minimum_additional_groups} ${plan.minimum_additional_groups === 1 ? 'group is' : 'groups are'} sufficient—if withdrawal is ruled out.</h3><p>The exact minimum additional group count that intersects every failing scenario. One minimum set is:</p><div class="dependency-group-chips">${plan.representative.map(id => `<span>${esc(labelFor(c, id))}</span>`).join('')}</div><p><strong>${number(plan.optimal_set_count)} minimum ${plan.optimal_set_count === 1 ? 'set' : 'sets'}</strong> · ${number(plan.failing_scenario_count)} failing scenarios covered.</p>${plan.optimal_set_count > 1 ? `<details><summary>Inspect minimum alternatives</summary><ol>${plan.optimal_sets_preview.map(ids => `<li>${esc(ids.map(id => labelFor(c, id)).join(' + '))}</li>`).join('')}</ol>${plan.alternatives_truncated ? `<p>Showing ${plan.optimal_sets_preview.length} of ${number(plan.optimal_set_count)} minimum sets.</p>` : ''}</details>` : ''}<div class="dependency-condition"><strong>This is an assumption, not a verification of the science.</strong><p>Reviewing a group does not make its records correct or independent. Protection means its withdrawal is excluded from this finite scenario model; the minimum counts groups, not review cost or experiment value.</p></div><button type="button" data-dependency-action="protect" class="button button-outline" ${live ? '' : 'disabled'}>Re-audit with these assumptions ${icon('arrow')}</button>${live ? '' : '<p class="dependency-fine">A new conditional audit requires the live application. This edition displays recorded results.</p>'}</div>`;
}

export class ProvenancePanel {
  constructor(element, api, callbacks = {}) {
    this.element = element; this.api = api; this.callbacks = callbacks; this.loading = false; this.excluded = [];
    this.catalogCoverage = new Map(); this.coveragePending = new Map();
    this.catalogGate = new RequestGate(); this.catalogSelected = new Map(); this.catalogItems = []; this.catalogBusy = false;
    this.renderedCertificate = null; this.renderedState = null; this.selectedBudget = 2; this.witnessKind = 'rank';
    this.element.innerHTML = `<div class="dependency-heading"><div><span class="eyebrow">SHARED EVIDENCE DEPENDENCIES</span><h2 id="dependency-title">What if the same source<br><em>supports many records?</em></h2><p>Audit whole provenance groups together. See how a shared dependency changes the selected compound, its rivals and the original shortlist.</p><div id="dependency-focus" class="dependency-focus">Choose a compound to begin.</div></div><form id="dependency-form" class="dependency-form"><label for="dependency-budget">Group withdrawal budget<select id="dependency-budget"><option value="1">Up to 1 group</option><option value="2" selected>Up to 2 groups</option></select></label><button type="submit" id="dependency-run" class="button button-dark" disabled>${icon('shield')}<span>Audit shared dependencies</span></button></form></div><div class="dependency-scope"><strong>DECLARED STRESS SCENARIO</strong><p>Withdraw every binding record mentioning any withdrawn group. Overlapping records count once. Imported labels and references do not establish independent support.</p><span id="dependency-edition" class="dependency-edition">Awaiting graph connection</span></div><p id="dependency-exclusion" class="dependency-condition" hidden></p><div class="dependency-scope-controls"><div><p id="dependency-scope-description">All imported source labels · top 10 · no conditional protection</p><p id="dependency-coverage" class="dependency-fine" hidden></p></div><button type="button" data-dependency-action="reset" class="button button-quiet">Reset source scope ${icon('reset')}</button></div><details id="dependency-custom" class="dependency-custom"><summary>Choose a custom source or reference scope ${icon('chevron')}</summary><p id="dependency-custom-note">The full application can audit up to 16 explicitly selected imported groups. Reference membership is a recorded annotation, not a verified causal dependency.</p><div id="dependency-catalog-controls"><form id="dependency-search-form"><label for="dependency-kind">Group type<select id="dependency-kind"><option value="source">Imported source label</option><option value="pubmed">Imported PubMed reference</option></select></label><label for="dependency-query">Search catalog<input id="dependency-query" type="search" maxlength="120" placeholder="Source label or PMID"></label><button type="submit" class="button button-outline">Search</button></form><div id="dependency-catalog" class="dependency-catalog"></div><p id="dependency-selected-count">0 groups selected</p><button type="button" id="dependency-use-groups" data-dependency-action="use-groups" class="button button-outline" disabled>Use selected scope</button></div></details><div id="dependency-body"></div><p id="dependency-status" class="sr-only" role="status" aria-live="polite" aria-atomic="true"></p>`;
    this.session = new ProvenanceSession(api, () => this.render());
    this.find('dependency-form').addEventListener('submit', event => { event.preventDefault(); this.run(); });
    this.find('dependency-budget').addEventListener('change', () => { this.session.setParameters({ budget: Number(this.find('dependency-budget').value) }); this.callbacks.onParameters?.(); });
    this.find('dependency-search-form').addEventListener('submit', event => { event.preventDefault(); this.searchCatalog(); });
    this.find('dependency-kind').addEventListener('change', () => { this.catalogGate.invalidate(); this.catalogSelected.clear(); this.catalogItems = []; this.catalogBusy = false; this.find('dependency-catalog').innerHTML = ''; this.renderCatalogSelection(); });
    this.element.addEventListener('click', event => this.handleClick(event));
    this.element.addEventListener('change', event => { if (event.target.matches('[data-dependency-group]')) this.toggleGroup(event.target); });
    this.render();
  }

  find(id) { return this.element.querySelector(`#${id}`); }
  setContext({ disease, candidate, excluded = [], loading = false }) { this.loading = loading; this.excluded = excluded; this.session.setFocus(disease, candidate); this.renderControls(); }
  configure(budget) { if (![1, 2].includes(budget)) throw new Error('Choose a group budget of one or two.'); this.find('dependency-budget').value = String(budget); this.session.setParameters({ budget }); }
  focus() { this.element.scrollIntoView({ behavior: 'instant', block: 'start' }); this.find('dependency-run').focus({ preventScroll: true }); }
  async run() { if (!this.loading && !this.session.busy) { this.ensureCoverage(); return this.session.run(); } return null; }
  announce(text) { this.find('dependency-status').textContent = text; }

  renderControls() {
    const s = this.session, p = s.parameters, live = this.api.mode === 'live', disabled = this.loading || !s.disease || !s.compound;
    this.find('dependency-run').disabled = disabled || s.busy;
    this.find('dependency-run').innerHTML = s.busy ? '<span class="spinner"></span><span>Auditing…</span>' : `${icon('shield')}<span>Audit shared dependencies</span>`;
    this.find('dependency-budget').disabled = disabled;
    this.find('dependency-focus').textContent = s.compound && s.disease ? `${s.compound.name} / ${s.disease.name}` : 'Choose a compound to begin.';
    this.find('dependency-edition').textContent = live ? 'LIVE EXHAUSTIVE AUDIT' : this.api.mode === 'snapshot' ? 'RECORDED SHARED-DEPENDENCY AUDIT' : 'Awaiting graph connection';
    this.find('dependency-body').setAttribute('aria-busy', String(s.busy));
    this.find('dependency-exclusion').hidden = !this.excluded.length;
    this.find('dependency-exclusion').textContent = `The explorer excludes ${this.excluded.join(', ')}. This audit uses the complete graph, independently of those family switches.`;
    this.find('dependency-scope-description').textContent = `${p.groupIds === null ? 'All imported source labels' : `${p.groupIds.length} selected ${p.groupKind === 'pubmed' ? 'reference' : 'source-label'} groups`} · top ${p.topK} · ${p.protectedGroupIds.length ? `${p.protectedGroupIds.length} groups protected by assumption` : 'no conditional protection'}`;
    const coverage = this.catalogCoverage.get(p.groupKind);
    this.find('dependency-coverage').hidden = !coverage;
    if (coverage) this.find('dependency-coverage').textContent = `Catalog metadata: ${number(coverage.annotated_binding_edges)} of ${number(coverage.binding_edges)} binding records have an imported ${p.groupKind === 'pubmed' ? 'PubMed reference' : 'source label'}; ${number(coverage.unannotated_binding_edges)} have none. Only selected group memberships are withdrawable.`;
    this.find('dependency-catalog-controls').hidden = !live;
    this.find('dependency-custom-note').textContent = live ? 'Select up to 16 imported groups. Reference membership is a recorded annotation, not a verified causal dependency. Unselected groups are outside this audit scope.' : 'Custom source/reference scopes and new conditional audits require the full application. This research edition contains recorded audits of all imported source labels.';
    const verify = this.find('dependency-verify');
    if (verify) { verify.disabled = s.verifying || s.busy; verify.innerHTML = `${s.verifying ? '<span class="spinner"></span>' : icon('reset')}<span>${s.verifying ? 'Checking…' : live ? 'Verify certificate' : 'View recorded verification'}</span>`; }
  }

  render() {
    this.renderControls(); const s = this.session;
    const state = s.busy ? 'busy' : s.error ? 'error' : s.certificate ? 'certificate' : 'empty';
    if (state !== this.renderedState || s.certificate !== this.renderedCertificate) {
      this.renderedState = state; this.renderedCertificate = s.certificate;
      if (state === 'busy') { this.find('dependency-body').innerHTML = `<div class="dependency-loading"><span class="spinner"></span><div><strong>${this.api.mode === 'snapshot' ? 'Loading a recorded group audit' : 'Enumerating every allowed group scenario'}</strong><p>All competing compound scores and the exact conditional protection problem are included.</p></div></div>`; this.announce('Shared-dependency audit in progress.'); }
      else if (state === 'error') { this.find('dependency-body').innerHTML = `<div class="dependency-error" role="alert"><strong>Audit unavailable</strong><p>${esc(errorText(s.error))}</p><button type="button" data-dependency-action="retry" class="button button-outline">Try again</button></div>`; this.announce(errorText(s.error)); }
      else if (state === 'certificate') { this.selectedBudget = s.parameters.budget; const row = s.certificate.results.at(-1); this.witnessKind = row.unsupported_witness && (row.worst_supported_rank === null || row.worst_supported_rank <= s.parameters.topK) ? 'unsupported' : 'rank'; this.renderCertificate(); this.announce(`${s.compound.name}. ${provenanceVerdict(s.certificate).title}. Worst supported rank ${rank(row.worst_supported_rank)}.`); }
      else { this.find('dependency-body').innerHTML = ''; this.announce(''); }
    }
    this.renderControls(); this.renderVerification();
  }

  renderCertificate() {
    const c = this.session.certificate; if (!c) return;
    const row = c.results.at(-1), verdict = provenanceVerdict(c);
    this.find('dependency-body').innerHTML = `<div class="dependency-result ${verdict.kind}"><div class="dependency-verdict"><div><span class="eyebrow">${this.api.mode === 'snapshot' ? 'RECORDED' : 'EXACT'} GROUP RESULT</span><h3>${esc(verdict.title)}</h3><p>${esc(verdict.summary)}</p></div><div class="dependency-scenario-count"><strong>${number(row.scenario_count)}</strong><span>allowed scenarios</span></div></div><div class="dependency-metrics"><div><span>Selected baseline</span><strong>${rank(c.baseline.rank)}</strong></div><div><span>Worst supported rank</span><strong>${rank(row.worst_supported_rank)}</strong></div><div><span>Support can vanish</span><strong>${row.unsupported_attainable ? 'Yes' : 'No'}</strong></div><div><span>Groups available for withdrawal</span><strong>${c.scope.available_group_count}</strong></div></div><div class="dependency-exploration"><div><div class="dependency-budget-tabs" role="group" aria-label="Shared-dependency witness budget">${c.results.map(result => `<button type="button" data-dependency-budget="${result.budget}" aria-pressed="${result.budget === this.selectedBudget}">Budget ${result.budget}<small>${rank(result.worst_supported_rank)}${result.unsupported_attainable ? ' · support can vanish' : ''}</small></button>`).join('')}</div><div id="dependency-witness-tabs"></div><div id="dependency-witness"></div></div>${protectionHTML(c, this.api.mode === 'live')}</div><section class="dependency-shortlist"><div class="dependency-block-heading"><span class="eyebrow">THE ORIGINAL TOP ${c.top_k}</span><h3>Audit every shortlisted hypothesis.</h3><p>Each row includes every competitor. Different rows’ worst cases may require different withdrawals.</p></div><div class="dependency-table-scroll" tabindex="0" role="region" aria-label="Original shortlist under group withdrawals"><table><thead><tr><th scope="col">Compound</th><th scope="col">Baseline</th><th scope="col">Worst supported</th><th scope="col">Support loss</th><th scope="col">Verdict</th></tr></thead><tbody>${c.shortlist.map(item => `<tr${item.compound.id === c.compound.id ? ' class="selected"' : ''}><th scope="row"><button type="button" data-dependency-compound="${esc(item.compound.id)}">${esc(item.compound.name)}</button>${item.compound.id === c.compound.id ? '<small>SELECTED</small>' : ''}</th><td>${rank(item.baseline_rank)}</td><td>${rank(item.worst_supported_rank)}</td><td>${item.unsupported_attainable ? 'Possible' : 'Not attainable'}</td><td><span class="dependency-outcome ${item.robust ? 'robust' : 'fragile'}">${item.robust ? 'Robust within scope' : 'Can fail'}</span></td></tr>`).join('')}</tbody></table></div>${c.shortlist_truncated ? '<p class="dependency-fine">The overview is limited to 20 original shortlist members; the selected compound’s full audit remains above.</p>' : ''}</section><details class="dependency-groups"><summary>${c.scope.groups.length} imported groups · inspect membership and scope ${icon('chevron')}</summary><p>These labels are not necessarily independent suppliers or studies. For example, one provider can supply several differently named collections. Each count refers to the recorded membership, not an independent replication.</p><div class="dependency-table-scroll"><table><thead><tr><th>Imported label</th><th>Binding records</th><th>Compounds</th><th>Withdrawal</th></tr></thead><tbody>${c.scope.groups.map(group => `<tr><th>${esc(group.label)}</th><td>${number(group.edge_count)}</td><td>${number(group.compound_count)}</td><td>${c.scope.protected_group_ids.includes(group.group_id) ? 'Excluded by assumption' : 'Eligible'}</td></tr>`).join('')}</tbody></table></div><p>Imported group-map SHA-256: <code>${esc(c.identity.group_map_sha256)}</code></p></details><div class="dependency-actions"><div><span class="eyebrow">TAKE THE REVIEW WITH YOU</span><p>Export a printable, self-contained dossier and the complete certificate. Keep the declared assumptions attached to every result.</p></div><div><button type="button" id="dependency-verify" data-dependency-action="verify" class="button button-outline"></button><button type="button" data-dependency-action="json" class="button button-outline">Certificate ${icon('download')}</button><button type="button" data-dependency-action="dossier" class="button button-dark">Review dossier ${icon('download')}</button></div></div><div id="dependency-verification" aria-live="polite"></div><details class="dependency-proof"><summary>Exact scope & reproducibility identities ${icon('chevron')}</summary><p>Every allowed combination is enumerated. The verifier recomputes scenario outcomes and the minimum conditional protection sets, then independently replays witness matrix edits. The guarantee concerns the fixed scoring function and declared record withdrawals.</p><dl>${Object.entries(c.identity).map(([key, value]) => `<dt>${esc(key)}</dt><dd><code>${esc(value)}</code></dd>`).join('')}<dt>Certificate SHA-256</dt><dd><code>${esc(c.certificate_sha256)}</code></dd></dl><p>${esc(objectText(c.interpretation))}</p></details></div>`;
    this.renderWitness(); this.renderControls();
  }

  renderWitness() {
    const c = this.session.certificate, row = c.results[this.selectedBudget];
    const choices = [['rank', 'Worst supported rank', row.rank_witness], ['unsupported', 'Loss of support', row.unsupported_witness]].filter(([, , witness]) => witness);
    if (!choices.some(([kind]) => kind === this.witnessKind)) this.witnessKind = choices[0]?.[0] || 'rank';
    this.find('dependency-witness-tabs').innerHTML = `<div class="dependency-witness-tabs" role="group" aria-label="Shared-dependency witness outcome">${choices.map(([kind, label]) => `<button type="button" data-dependency-witness="${kind}" aria-pressed="${this.witnessKind === kind}">${label}</button>`).join('')}</div>`;
    this.find('dependency-witness').innerHTML = witnessHTML(c, row, this.witnessKind);
    this.element.querySelectorAll('[data-dependency-budget]').forEach(button => button.setAttribute('aria-pressed', String(Number(button.dataset.dependencyBudget) === this.selectedBudget)));
  }

  renderVerification() {
    const element = this.find('dependency-verification'); if (!element) return;
    const s = this.session;
    if (s.verifying) { element.innerHTML = '<p>Checking the certificate…</p>'; return; }
    if (s.verificationError) { element.innerHTML = `<div class="dependency-error" role="alert"><strong>Verification could not complete.</strong><p>${esc(errorText(s.verificationError))}</p></div>`; return; }
    if (!s.verification) { element.innerHTML = ''; return; }
    const result = s.verification, recorded = this.api.mode === 'snapshot';
    element.innerHTML = `<div class="dependency-verification ${result.valid ? 'verified' : 'invalid'}"><strong>${result.valid ? recorded ? 'Matches a verified recorded group certificate.' : 'Shared-dependency certificate verified.' : 'Certificate verification failed.'}</strong><p>${recorded ? 'The browser compared the exact published result and loaded its verification record. No solver or graph replay ran in the browser.' : 'The server recomputed the finite scenario table and conditional protection claims. Mathematical verification does not certify scientific validity.'}</p>${result.errors.length ? `<ul>${result.errors.map(error => `<li>${esc(error)}</li>`).join('')}</ul>` : ''}<details><summary>${result.checks.length} ${recorded ? 'recorded' : 'completed'} checks</summary><ul>${result.checks.map(check => `<li>${esc(check)}</li>`).join('')}</ul><p>${esc(objectText(result.verification_method))}</p></details></div>`;
  }


  async ensureCoverage() {
    const kind = this.session.parameters.groupKind;
    if (this.catalogCoverage.has(kind) || this.coveragePending.has(kind)) return;
    const pending = this.api.provenanceGroups(kind, '', 1, 0);
    this.coveragePending.set(kind, pending);
    try {
      const result = await pending, coverage = result?.coverage;
      if (coverage && ['binding_edges', 'annotated_binding_edges', 'unannotated_binding_edges'].every(key => Number.isSafeInteger(coverage[key]) && coverage[key] >= 0) && coverage.binding_edges === coverage.annotated_binding_edges + coverage.unannotated_binding_edges) this.catalogCoverage.set(kind, coverage);
    } catch { /* A catalog lookup cannot manufacture or alter an audit result. */ }
    finally { this.coveragePending.delete(kind); this.renderControls(); }
  }

  async searchCatalog() {
    if (this.api.mode !== 'live') return;
    const kind = this.find('dependency-kind').value, query = this.find('dependency-query').value.trim();
    const ticket = this.catalogGate.begin(kind); this.catalogBusy = true;
    this.find('dependency-catalog').innerHTML = '<p>Searching recorded provenance…</p>';
    try {
      const result = await this.api.provenanceGroups(kind, query, 30, 0);
      if (!this.catalogGate.current(ticket, this.find('dependency-kind').value)) return;
      if (!Array.isArray(result?.items) || result.kind !== kind || result.items.some(item => typeof item.group_id !== 'string' || !item.group_id.startsWith(`${kind}:`) || typeof item.label !== 'string')) throw new Error('The provenance catalog returned invalid groups.');
      this.catalogItems = result.items;
      this.find('dependency-catalog').innerHTML = `<p>${number(result.total)} matching groups${result.total > result.items.length ? ` · showing ${result.items.length}; refine your search` : ''}.</p><div class="dependency-catalog-list">${result.items.map(item => `<label><input type="checkbox" data-dependency-group="${esc(item.group_id)}" ${this.catalogSelected.has(item.group_id) ? 'checked' : ''}><span><strong>${esc(item.label)}</strong><small>${number(item.edge_count)} records · ${number(item.compound_count)} compounds</small></span></label>`).join('')}</div><p class="dependency-fine">${number(result.coverage?.unannotated_binding_edges || 0)} binding records have no ${kind === 'pubmed' ? 'imported PubMed reference' : 'imported source label'}; no unrecorded membership is inferred.</p>`;
    } catch (error) { if (this.catalogGate.current(ticket, this.find('dependency-kind').value)) this.find('dependency-catalog').innerHTML = `<p role="alert">${esc(errorText(error))}</p>`; }
    finally { if (this.catalogGate.current(ticket, this.find('dependency-kind').value)) { this.catalogBusy = false; this.renderCatalogSelection(); } }
  }

  toggleGroup(input) {
    const item = this.catalogItems.find(group => group.group_id === input.dataset.dependencyGroup); if (!item) return;
    if (input.checked && this.catalogSelected.size >= 16) { input.checked = false; this.callbacks.onNotice?.('The exact audit accepts at most 16 selected groups.'); return; }
    if (input.checked) this.catalogSelected.set(item.group_id, item); else this.catalogSelected.delete(item.group_id);
    this.renderCatalogSelection();
  }

  renderCatalogSelection() {
    this.find('dependency-selected-count').textContent = `${this.catalogSelected.size} groups selected${this.catalogSelected.size ? ': ' + [...this.catalogSelected.values()].map(item => item.label).join(' · ') : ''}`;
    this.find('dependency-use-groups').disabled = this.catalogBusy || !this.catalogSelected.size;
  }

  handleClick(event) {
    const budget = event.target.closest('[data-dependency-budget]'); if (budget && this.session.certificate) { this.selectedBudget = Number(budget.dataset.dependencyBudget); this.renderWitness(); return; }
    const witness = event.target.closest('[data-dependency-witness]'); if (witness && this.session.certificate) { this.witnessKind = witness.dataset.dependencyWitness; this.renderWitness(); return; }
    const compound = event.target.closest('[data-dependency-compound]');
    if (compound && this.session.certificate) { const item = this.session.certificate.shortlist.find(row => row.compound.id === compound.dataset.dependencyCompound); if (item) this.callbacks.onCompound?.(item.compound); return; }
    const action = event.target.closest('[data-dependency-action]')?.dataset.dependencyAction;
    if (action === 'retry') this.run();
    if (action === 'verify') this.session.verify();
    if (action === 'reset') { this.session.setParameters({ groupKind: 'source', groupIds: null, protectedGroupIds: [] }); this.catalogSelected.clear(); this.renderCatalogSelection(); }
    if (action === 'use-groups' && this.api.mode === 'live' && this.catalogSelected.size) { this.session.setParameters({ groupKind: this.find('dependency-kind').value, groupIds: [...this.catalogSelected.keys()], protectedGroupIds: [] }); this.find('dependency-custom').open = false; this.run(); }
    if (action === 'protect' && this.api.mode === 'live' && this.session.certificate) { const c = this.session.certificate; this.session.setParameters({ groupKind: c.scope.group_kind, groupIds: c.scope.group_ids, protectedGroupIds: [...c.scope.protected_group_ids, ...c.protection_plan.representative] }); this.run(); }
    if (action === 'json') this.download();
    if (action === 'dossier') this.openDossier();
  }

  openDossier() {
    try {
      const certificate = this.session.exportCertificate(); if (!certificate) return;
      const html = provenanceDossier(certificate, { edition: this.api.mode, verification: this.session.verification });
      openDossierDialog({ html, title: `Review dossier · ${certificate.compound.name}`, downloadName: exportName(certificate, 'review.html') });
    } catch (error) { this.callbacks.onNotice?.(errorText(error)); }
  }

  download() {
    try {
      const c = this.session.exportCertificate(); if (!c) return false;
      const url = URL.createObjectURL(new Blob([JSON.stringify(c, null, 2) + '\n'], { type: 'application/json' }));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = exportName(c, 'certificate.json');
      document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
      this.callbacks.onNotice?.('The complete group certificate is ready for verification with the matching graph and model.');
      return true;
    } catch (error) { this.callbacks.onNotice?.(errorText(error)); return false; }
  }
}
