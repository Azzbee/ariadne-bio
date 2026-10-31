import { AriadneAPI } from './api.js';
import { AuditPanel } from './audit.js';
import { auditLinkParameters, rivalExampleURL } from './audit-model.js';
import { EvidenceGraph, pathFamily } from './graph.js';
import {
  RequestGate, agentMatchesInvestigation, appendRankingPage, investigationKey,
  loadCandidateInvestigation, rankMovement, signedNumber
} from './investigation.js';
import {
  FAMILY_LABELS, compactNumber, escapeHTML as esc, evidenceSelection, exclusionKey, metricRows,
  metricValue, number, objectText, pct, safeURL, score, selectDisease, sourceEntries, titleCase
} from './utils.js';

const $ = id => document.getElementById(id);
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const config = window.ARIADNE_CONFIG || {};
const api = new AriadneAPI(config);
const query = new URLSearchParams(location.search);
const state = {
  health: null, stats: null, diseases: [], disease: null, rankings: null,
  candidate: null, assessment: null, evidence: null, challenge: null, challengeError: null, excluded: [], filter: 'all',
  evaluation: null, provenance: null, agent: null, activePath: null, view: 'investigate',
  searchIndex: -1, shownDiseases: [], busy: false, evidenceBusy: false, agentBusy: false
};
const rankGate = new RequestGate();
const evidenceGate = new RequestGate();
const agentGate = new RequestGate();
const pageGate = new RequestGate();
let toastTimer;
let bootRequest = 0;

const graph = new EvidenceGraph($('evidence-graph'), $('graph-tooltip'), {
  onNode: showNode,
  onEdge: showEdge
});
const auditPanel = new AuditPanel($('audit-section'), api, {
  onNotice: toast,
  onParameters: updateURLState,
  onMethod: () => {
    setView('method');
    $('audit-method').scrollIntoView({ block: 'start' });
    $('audit-method-title').focus({ preventScroll: true });
  }
});

function toast(message) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, 4200);
}

function errorMessage(error) { return error?.message || 'This request could not be completed. Please try again.'; }
function loading(text) { return `<div class="loading-block"><span class="spinner"></span><span>${esc(text)}</span></div>`; }
function inlineError(error, retryId) {
  return `<div class="inline-error">${esc(errorMessage(error))}${retryId ? `<button id="${retryId}" type="button">Try again</button>` : ''}</div>`;
}
function currentExcluded() { return [...document.querySelectorAll('#evidence-switches input:not(:checked)')].map(input => input.value); }
function rankingContext() { return investigationKey(state.disease?.id, state.excluded); }
function selectedContext() { return investigationKey(state.disease?.id, state.excluded, state.candidate?.id); }

function refreshControls() {
  const loadingCase = state.busy || state.evidenceBusy;
  $('export-case').disabled = loadingCase || !state.evidence || !state.assessment;
  $('share-case').disabled = loadingCase || !state.disease || !state.candidate;
  $('open-audit').disabled = loadingCase || !state.disease || !state.candidate;
  $('agent-submit').disabled = loadingCase || state.agentBusy || !state.candidate;
  document.querySelectorAll('[data-prompt]').forEach(button => { button.disabled = $('agent-submit').disabled; });
  document.querySelectorAll('[data-path-filter]').forEach(button => { button.disabled = loadingCase || !state.evidence; });
  $('fit-graph').disabled = loadingCase || !state.evidence;
  $('workbench').setAttribute('aria-busy', String(loadingCase));
  auditPanel.setContext({ disease: state.disease, candidate: state.candidate, excluded: state.excluded, loading: loadingCase });
}

function invalidateAgent() {
  agentGate.invalidate();
  state.agent = null;
  state.agentBusy = false;
  $('agent-response').hidden = true;
  $('agent-response').innerHTML = '';
  $('agent-submit').innerHTML = `<span>Investigate</span>${icon('arrow')}`;
  refreshControls();
}

function setBusy(busy) {
  state.busy = busy;
  $('workbench').classList.toggle('busy', busy);
  refreshControls();
}

function setView(view, updateURL = true) {
  if (!['investigate', 'benchmark', 'method'].includes(view)) return;
  state.view = view;
  document.querySelectorAll('.view').forEach(section => {
    const active = section.id === `${view}-view`;
    section.hidden = !active;
    section.classList.toggle('active', active);
  });
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  if (updateURL) updateURLState();
}

function updateURLState() {
  const params = new URLSearchParams(location.search);
  if (state.disease) params.set('disease', state.disease.id);
  if (state.candidate) params.set('compound', state.candidate.id);
  else params.delete('compound');
  const excluded = exclusionKey(state.excluded);
  if (excluded) params.set('exclude', excluded);
  else params.delete('exclude');
  if (state.view !== 'investigate') params.set('view', state.view);
  else params.delete('view');
  if (params.has('audit_k') || params.has('audit_budget')) {
    params.set('audit_k', String(auditPanel.session.topK));
    params.set('audit_budget', String(auditPanel.session.budget));
  }
  const next = `${location.pathname}${params.toString() ? '?' + params.toString() : ''}${location.hash}`;
  history.replaceState(null, '', next);
}

async function boot() {
  const request = ++bootRequest;
  $('fatal-error').hidden = true;
  $('runtime-pill').innerHTML = '<span class="status-dot loading"></span>Connecting';
  try {
    state.health = await api.initialize(query.get('mode') === 'snapshot');
    if (request !== bootRequest) return;
    const [stats, diseases] = await Promise.all([api.stats(), api.diseases('', 137)]);
    if (request !== bootRequest) return;
    state.stats = stats || {};
    state.diseases = diseases.items || [];
    if (!state.diseases.length) throw new Error('The graph contains no available disease cases. Prepare the dataset and retry.');
    renderOverview();
    const linkedAudit = auditLinkParameters(query);
    auditPanel.configure(linkedAudit);
    const preferred = query.get('disease') || api.manifest?.default_disease_id || 'Disease::DOID:10652';
    const selected = selectDisease(state.diseases, preferred);
    state.excluded = exclusionKey(query.get('exclude') || '').split(',').filter(Boolean);
    document.querySelectorAll('#evidence-switches input').forEach(input => { input.checked = !state.excluded.includes(input.value); });
    setView(query.get('view') || 'investigate', false);
    const remaining = Promise.allSettled([loadEvaluation(), loadProvenance()]);
    await chooseDisease(selected, query.get('compound'));
    await remaining;
    if (request !== bootRequest) return;
    if (linkedAudit.requested && state.view === 'investigate' && state.assessment && state.evidence
      && (!query.has('disease') || query.get('disease') === state.disease?.id)
      && (!query.has('compound') || query.get('compound') === state.candidate?.id)) {
      auditPanel.focus();
      await auditPanel.run();
    }
  } catch (error) {
    if (request !== bootRequest) return;
    $('fatal-message').textContent = errorMessage(error);
    $('fatal-error').hidden = false;
    document.querySelectorAll('.view').forEach(view => { view.hidden = true; });
    $('runtime-pill').innerHTML = '<span class="status-dot" style="background:#b27e50"></span>Disconnected';
  }
}

function renderOverview() {
  const snapshot = api.mode === 'snapshot';
  $('audit-example-link').href = rivalExampleURL(location.href);
  $('runtime-pill').innerHTML = `<span class="status-dot${snapshot ? ' snapshot' : ''}"></span>${snapshot ? 'Research snapshot' : 'Live graph'}`;
  $('runtime-pill').title = snapshot ? 'Published results from an executed graph analysis. No live database connection.' : `Graph backend: ${state.health.graph_backend || 'connected'}`;
  $('dataset-name').innerHTML = `${esc((state.stats.dataset || 'Hetionet').toUpperCase())} <b>v${esc(state.stats.version || '1.0')}</b>`;
  $('stat-nodes').textContent = number(state.stats.nodes);
  $('stat-edges').textContent = number(state.stats.edges);
  $('stat-diseases').textContent = number(state.stats.diseases || state.stats.node_counts?.Disease || state.diseases.length);
  document.querySelectorAll('[data-family-count]').forEach(element => {
    element.textContent = compactNumber(state.stats.edge_counts?.[element.dataset.familyCount]);
  });
  if (snapshot) {
    $('edition-notice').hidden = false;
    $('edition-notice').innerHTML = `<strong>Published research edition.</strong> Explore ${number(state.diseases.length)} recorded disease cases, with all evidence-family combinations. Rankings and paths come from executed analyses. The guide formats recorded evidence without calling an LLM. <a href="${esc(safeURL(config.repository) || 'https://github.com/Azzbee/ariadne-bio')}" target="_blank" rel="noopener noreferrer">Run the full Neo4j application ↗</a>`;
    $('agent-mode').textContent = 'DETERMINISTIC GUIDE · PUBLISHED RESULTS';
  } else {
    $('edition-notice').hidden = true;
    const mode = state.health.agent_mode || 'deterministic';
    $('agent-mode').textContent = mode === 'llm' ? 'LANGGRAPH · LLM + READ-ONLY TOOLS' : 'LANGGRAPH · DETERMINISTIC TOOL WORKFLOW';
  }
  const repository = safeURL(config.repository);
  if (repository) document.querySelectorAll('.repo-link').forEach(link => { link.href = repository; });
}

function openSearch() { renderDiseaseOptions($('disease-search').value === state.disease?.name ? '' : $('disease-search').value); }

function renderDiseaseOptions(term = '') {
  const queryText = term.toLowerCase().trim();
  state.shownDiseases = state.diseases.filter(item => `${item.name} ${item.id}`.toLowerCase().includes(queryText));
  state.searchIndex = -1;
  $('disease-search').removeAttribute('aria-activedescendant');
  $('disease-options').innerHTML = state.shownDiseases.length
    ? state.shownDiseases.map((item, index) => `<button type="button" tabindex="-1" class="disease-option" role="option" id="disease-option-${index}" data-disease-index="${index}" aria-selected="false">${esc(item.name)}<small>${esc(item.id)}</small></button>`).join('')
    : '<div class="disease-empty">No matching disease in this edition.</div>';
  $('disease-options').hidden = false;
  $('disease-search').setAttribute('aria-expanded', 'true');
}

function closeSearch() {
  $('disease-options').hidden = true;
  $('disease-search').setAttribute('aria-expanded', 'false');
  $('disease-search').removeAttribute('aria-activedescendant');
  if (state.disease) $('disease-search').value = state.disease.name;
}

function moveSearch(direction) {
  const count = state.shownDiseases.length;
  if (!count) return;
  state.searchIndex = state.searchIndex < 0 ? (direction > 0 ? 0 : count - 1) : (state.searchIndex + direction + count) % count;
  document.querySelectorAll('.disease-option').forEach((option, index) => option.setAttribute('aria-selected', String(index === state.searchIndex)));
  const option = $(`disease-option-${state.searchIndex}`);
  if (option) { option.scrollIntoView({ block: 'nearest' }); $('disease-search').setAttribute('aria-activedescendant', option.id); }
}

async function chooseDisease(disease, preferredCompound = null) {
  if (!disease) return;
  state.disease = disease;
  state.candidate = null;
  state.assessment = null;
  state.evidence = null;
  state.filter = 'all';
  invalidateAgent();
  $('disease-search').value = disease.name;
  closeSearch();
  $('disease-context').innerHTML = `<strong>${esc(disease.name)}</strong><br><span class="case-stamp">${esc(disease.id)}</span>`;
  await loadRankings(preferredCompound);
}

async function loadRankings(preferredCompound = state.candidate?.id) {
  if (!state.disease) return;
  const request = rankGate.begin(rankingContext());
  evidenceGate.invalidate();
  pageGate.invalidate();
  invalidateAgent();
  state.evidence = null;
  state.assessment = null;
  state.rankings = null;
  state.challenge = null;
  state.challengeError = null;
  state.evidenceBusy = false;
  $('candidate-list').innerHTML = loading('Following the evidence');
  $('assessment-section').hidden = true;
  graph.clear();
  $('graph-tooltip').hidden = true;
  $('graph-canvas').classList.add('graph-loading');
  $('path-list').innerHTML = '';
  $('evidence-summary').innerHTML = '<p>Loading supporting paths…</p>';
  $('load-more').hidden = true;
  $('load-more').disabled = false;
  renderChallenge(true);
  setBusy(true);
  const diseaseId = state.disease.id;
  const excluded = [...state.excluded];
  const previousCandidate = state.candidate;
  try {
    const [rankings, comparison] = await Promise.all([
      api.rankings(diseaseId, excluded, 12),
      excluded.length ? api.challenge(diseaseId, excluded, 12).then(value => ({ value })).catch(error => ({ error })) : Promise.resolve({ value: null })
    ]);
    if (!rankGate.current(request, rankingContext())) return;
    state.rankings = rankings;
    state.challenge = comparison.value || null;
    state.challengeError = comparison.error || null;
    renderCandidates();
    renderChallenge();
    const chosen = preferredCompound
      ? state.rankings.candidates.find(item => item.id === preferredCompound)
        || (previousCandidate?.id === preferredCompound ? previousCandidate : { id: preferredCompound, name: 'Selected compound' })
      : state.rankings.candidates[0];
    if (chosen) await chooseCandidate(chosen);
    else clearEvidence('No graph-supported candidates remain.', 'The excluded families remove every supported path. Restore compound binding and disease associations to investigate candidates.');
    if (rankGate.current(request, rankingContext())) updateURLState();
  } catch (error) {
    if (!rankGate.current(request, rankingContext())) return;
    $('candidate-list').innerHTML = inlineError(error, 'retry-rankings');
    $('retry-rankings')?.addEventListener('click', () => loadRankings(preferredCompound));
    clearEvidence('The ranking could not be loaded.', errorMessage(error), false);
    state.challengeError = error;
    renderChallenge();
  } finally {
    if (rankGate.current(request, rankingContext())) {
      setBusy(false);
      if (!state.evidenceBusy) $('graph-canvas').classList.remove('graph-loading');
    }
  }
}

function renderCandidates() {
  const candidates = state.rankings?.candidates || [];
  const list = $('candidate-list');
  const focusedId = list.contains(document.activeElement) ? document.activeElement.dataset.compoundId : null;
  const scroll = { left: list.scrollLeft, top: list.scrollTop };
  $('candidate-count').textContent = number(candidates.length);
  const pinned = state.candidate?.pinned && !candidates.some(item => item.id === state.candidate.id)
    ? `<div class="pinned-candidate"><span>SELECTED INVESTIGATION</span><strong>${esc(state.candidate.name)}</strong><small>${!state.assessment ? 'Refreshing this compound’s assessment…' : state.candidate.rank === null ? 'No supporting paths remain. The assessment stays available.' : 'Rank #' + state.candidate.rank + ' · outside the displayed shortlist'}</small></div>` : '';
  if (!candidates.length) {
    list.innerHTML = pinned + '<div class="empty-message">No supported paths remain with this evidence configuration. Restore the core evidence families.</div>';
    $('candidate-footer').textContent = 'No evidence-supported hypotheses under this configuration.';
    $('load-more').hidden = true;
    return;
  }
  const maxScore = Math.max(...candidates.map(item => Number(item.score)), 0.001);
  list.innerHTML = pinned + candidates.map(candidate => {
    const delta = Number(candidate.rank_delta || 0);
    const change = state.excluded.length ? `<span class="rank-delta ${delta > 0 ? 'up' : delta < 0 ? 'down' : 'same'}" title="Rank change from all evidence">${delta > 0 ? '↑ ' + delta : delta < 0 ? '↓ ' + Math.abs(delta) : '—'}</span>` : '';
    return `<button class="candidate-card${state.candidate?.id === candidate.id ? ' selected' : ''}" data-compound-id="${esc(candidate.id)}" aria-pressed="${state.candidate?.id === candidate.id}" aria-label="Inspect ${esc(candidate.name)}, rank ${candidate.rank}, model score ${score(candidate.score)}">
      <span class="candidate-rank">${String(candidate.rank).padStart(2, '0')}</span><span>
      <span class="candidate-name-row"><span class="candidate-name">${esc(candidate.name)}</span><span class="candidate-score">${score(candidate.score)}</span></span>
      <span class="score-track" style="display:block"><span class="score-fill" style="display:block;width:${Math.max(0, Math.min(100, Number(candidate.score) / maxScore * 100))}%"></span></span>
      <span class="candidate-meta"><span>${compactNumber(candidate.evidence_count)} paths</span>${candidate.known_treatment ? '<span class="indication-tag" title="A treatment relationship is recorded in Hetionet. It is kept separate from predictive evidence.">Recorded indication</span>' : ''}${change}</span></span></button>`;
  }).join('');
  const published = state.rankings.published_count || candidates.length;
  $('candidate-footer').textContent = api.mode === 'snapshot'
    ? `${number(Math.min(published, candidates.length))} published candidates · ${number(state.rankings.total)} supported in the full ranking`
    : `${number(candidates.length)} of ${number(state.rankings.total)} supported candidates · fixed model`;
  $('load-more').hidden = api.mode === 'snapshot' || candidates.length >= state.rankings.total;
  if (focusedId) [...list.querySelectorAll('[data-compound-id]')].find(button => button.dataset.compoundId === focusedId)?.focus({ preventScroll: true });
  list.scrollLeft = scroll.left;
  list.scrollTop = scroll.top;
}

async function chooseCandidate(candidate) {
  state.candidate = candidate;
  const request = evidenceGate.begin(selectedContext());
  invalidateAgent();
  state.evidence = null;
  state.assessment = null;
  state.evidenceBusy = true;
  state.activePath = null;
  renderCandidates();
  $('graph-title').textContent = candidate.name;
  $('graph-subheading').textContent = 'Retrieving this compound’s assessment and source records…';
  $('assessment-section').hidden = true;
  graph.clear();
  $('graph-tooltip').hidden = true;
  $('graph-canvas').classList.add('graph-loading');
  $('graph-empty').hidden = true;
  $('graph-hint').hidden = true;
  $('path-list').innerHTML = '';
  $('evidence-summary').innerHTML = '<p>Retrieving source records…</p>';
  ['all', 'direct', 'interaction', 'pathway'].forEach(key => { $(`path-count-${key}`).textContent = '—'; });
  refreshControls();
  const diseaseId = state.disease.id;
  const excluded = [...state.excluded];
  try {
    const result = await loadCandidateInvestigation(api, diseaseId, candidate.id, excluded, state.rankings?.candidates || []);
    if (!evidenceGate.current(request, selectedContext())) return;
    Object.assign(state, result);
    renderCandidates();
    $('graph-title').textContent = state.candidate.name;
    $('graph-subheading').innerHTML = `${state.candidate.supported ? 'Model score' : 'Unsupported · diagnostic score'} <strong>${score(state.candidate.score)}</strong> <span class="hypothesis-indicator">${state.candidate.known_treatment ? 'RECORDED INDICATION' : 'RESEARCH HYPOTHESIS'}</span>${state.excluded.length ? ' <span class="family-off">Evidence excluded</span>' : ''}${state.candidate.pinned ? ` <span class="case-stamp">${state.candidate.rank === null ? 'No supported rank' : 'Rank #' + state.candidate.rank}</span>` : ''}`;
    renderEvidence();
    renderAssessment();
    $('investigation-status').textContent = `${state.candidate.name}: ${state.candidate.supported ? 'rank ' + state.candidate.rank : 'no supported rank'}, ${number(state.evidence.total_paths)} supporting paths. ${state.excluded.length ? 'Evidence exclusions applied.' : 'All evidence included.'}`;
    updateURLState();
  } catch (error) {
    if (!evidenceGate.current(request, selectedContext())) return;
    state.evidence = null;
    state.assessment = null;
    $('path-list').innerHTML = inlineError(error, 'retry-evidence');
    $('retry-evidence')?.addEventListener('click', () => chooseCandidate(candidate));
    $('evidence-summary').innerHTML = '<p>The supporting records could not be loaded.</p>';
    graph.clear();
    $('graph-caption').textContent = errorMessage(error);
  } finally {
    if (evidenceGate.current(request, selectedContext())) {
      state.evidenceBusy = false;
      $('graph-canvas').classList.remove('graph-loading');
      refreshControls();
    }
  }
}

function clearEvidence(title, message, clearSelection = true) {
  state.evidence = null;
  state.assessment = null;
  state.evidenceBusy = false;
  if (clearSelection) state.candidate = null;
  $('assessment-section').hidden = true;
  $('graph-title').textContent = title;
  $('graph-subheading').textContent = message;
  graph.clear();
  $('graph-empty').hidden = true;
  $('graph-hint').hidden = true;
  $('evidence-summary').innerHTML = '<p>No supporting records are displayed.</p>';
  $('path-list').innerHTML = '';
  $('graph-caption').textContent = 'An unsupported ranking is not presented as evidence.';
  ['all', 'direct', 'interaction', 'pathway'].forEach(key => { $(`path-count-${key}`).textContent = '0'; });
  refreshControls();
}

function renderEvidence() {
  const evidence = state.evidence;
  if (!evidence) return;
  const paths = (evidence.paths || []).filter(path => state.filter === 'all' || pathFamily(path) === state.filter);
  const nodes = new Map(evidence.nodes.map(node => [node.id, node]));
  const edges = new Map(evidence.edges.map(edge => [edge.id, edge]));
  graph.render(evidence, state.filter);
  $('graph-hint').hidden = !paths.length;
  $('graph-empty').hidden = true;
  $('path-count-all').textContent = compactNumber(evidence.total_paths);
  for (const family of ['direct', 'interaction', 'pathway']) $(`path-count-${family}`).textContent = compactNumber(evidence.counts?.[family] || 0);
  document.querySelectorAll('[data-path-filter]').forEach(button => {
    const active = button.dataset.pathFilter === state.filter;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  const fullCount = state.filter === 'all' ? evidence.total_paths : evidence.counts?.[state.filter] || 0;
  $('evidence-summary').innerHTML = `<div class="summary-counts"><strong>${number(fullCount)}</strong> supporting ${fullCount === 1 ? 'path' : 'paths'}</div><p>${number(paths.length)} displayed · complete counts used by the model</p>`;
  $('path-list').innerHTML = paths.length ? paths.map((path, index) => {
    const sources = [...new Set((path.edge_ids || []).flatMap(id => sourceEntries(edges.get(id)?.sources).map(source => source.name)))];
    return `<button class="path-card" data-path-id="${esc(path.id)}" aria-label="Highlight evidence path ${index + 1}: ${esc(path.metapath)}" aria-pressed="false"><span class="path-card-header"><span>PATH ${String(index + 1).padStart(2, '0')}</span><span class="path-badge">${esc(pathFamily(path).toUpperCase())}</span></span><span class="path-chain">${path.node_ids.map((id, step) => `${step ? '<span class="arrow">→</span>' : ''}<span>${esc(nodes.get(id)?.name || id)}</span>`).join('')}</span><span class="path-source">${sources.length ? esc(sources.slice(0, 3).join(' · ')) + (sources.length > 3 ? ` +${sources.length - 3}` : '') : 'Source metadata available in individual records'}</span></button>`;
  }).join('') : '<div class="empty-message">No paths from this family are in the displayed sample. Exact counts are shown above.</div>';
  $('graph-caption').textContent = `Showing ${number(paths.length)} of ${number(fullCount)} ${state.filter === 'all' ? '' : state.filter + ' '}paths. ${evidenceSelection(evidence)} Model features use complete path counts.`;
  if (!paths.length && !fullCount) $('graph-caption').textContent = 'This evidence family provides no supporting paths under the current configuration.';
}

function renderAssessment() {
  const assessment = state.assessment;
  if (!assessment) { $('assessment-section').hidden = true; return; }
  const { baseline, current, decomposition, model } = assessment;
  const changed = assessment.excluded.length > 0;
  const terms = decomposition.features || [];
  const contributionField = changed ? 'contribution_delta' : 'contribution_after';
  const maximum = Math.max(...terms.map(term => Math.abs(Number(term[contributionField]) || 0)), .001);
  const rankText = value => value.supported ? `#${number(value.rank)}` : 'No supported rank';
  const rows = [
    ['Supported rank', rankText(baseline), rankText(current), rankMovement(baseline, current)],
    ['Model score', score(baseline.score), score(current.score), signedNumber(assessment.delta.score)],
    ['Complete paths', number(baseline.evidence_count), number(current.evidence_count), signedNumber(assessment.delta.evidence_count, 0)],
    ['Direct paths', number(baseline.features.direct), number(current.features.direct), signedNumber(current.features.direct - baseline.features.direct, 0)],
    ['Interaction paths', number(baseline.features.interaction), number(current.features.interaction), signedNumber(current.features.interaction - baseline.features.interaction, 0)],
    ['Pathway paths', number(baseline.features.pathway), number(current.features.pathway), signedNumber(current.features.pathway - baseline.features.pathway, 0)]
  ];
  const bars = terms.map(term => {
    const value = Number(term[contributionField]);
    const width = Number.isFinite(value) ? Math.abs(value) / maximum * 50 : 0;
    return `<li class="contribution-row"><span class="contribution-label">${esc(term.label || term.name)}</span><span class="contribution-track" aria-hidden="true"><span class="contribution-zero"></span><span class="contribution-bar ${value < 0 ? 'negative' : 'positive'}" style="width:${width}%;${value < 0 ? 'right' : 'left'}:50%"></span></span><span class="contribution-value">${signedNumber(value)}</span></li>`;
  }).join('');
  const table = terms.map(term => `<tr><th scope="row">${esc(term.label || term.name)}<small>${esc(term.definition || '')}</small><small>Training mean ${number(term.mean, 6)} · scale ${number(term.scale, 6)}</small></th><td>${number(term.value_before, 5)}</td><td>${number(term.value_after, 5)}</td><td>${signedNumber(term.coefficient, 5)}</td><td>${signedNumber(term.contribution_before, 5)}</td><td>${signedNumber(term.contribution_after, 5)}</td><td>${signedNumber(term.contribution_delta, 5)}</td></tr>`).join('');
  $('assessment-section').innerHTML = `
    <div class="assessment-heading"><div><span class="eyebrow">THE SELECTED COMPOUND · BEFORE & AFTER</span><h2 id="assessment-title">${esc(assessment.compound.name)}<span>Follow the same hypothesis.</span></h2></div><span class="assessment-context${current.supported ? '' : ' unsupported'}">${current.supported ? `${changed ? 'Evidence challenged' : 'All evidence included'} · rank #${number(current.rank)}` : 'NO SUPPORTED RANK'}</span></div>
    <div class="assessment-grid">
      <div class="assessment-comparison"><p class="assessment-intro">${changed ? esc(assessment.excluded.map(family => FAMILY_LABELS[family] || family).join(' + ')) + ' excluded.' : 'The current configuration includes every evidence family.'} The same fitted model scores both columns.</p><div class="assessment-table-wrap"><table class="assessment-table"><caption class="sr-only">${esc(assessment.compound.name)} for ${esc(assessment.disease.name)}: all-evidence baseline compared with the current configuration</caption><thead><tr><th scope="col">Measure</th><th scope="col">All evidence</th><th scope="col">Current</th><th scope="col">Change</th></tr></thead><tbody>${rows.map((row, index) => `<tr${index === 2 ? ' class="path-total-row"' : index > 2 ? ' class="path-detail-row"' : ''}><th scope="row">${row[0]}</th><td>${row[1]}</td><td>${row[2]}</td><td>${row[3]}</td></tr>`).join('')}</tbody></table></div><p class="assessment-note${current.supported ? '' : ' unsupported-note'}">${current.supported ? 'Model scores prioritize retrieval. They are not probabilities of clinical efficacy. Rank changes also depend on how the other compounds move.' : 'No supporting paths remain. The finite score is a diagnostic model output only; this compound is excluded from the supported ranking. Its identity and baseline stay available.'}</p></div>
      <div class="assessment-explanation"><div class="contribution-heading"><div><span class="eyebrow">EXACT FITTED-MODEL TERMS</span><h3>${changed ? 'What moved the score?' : 'How the score is assembled.'}</h3></div><span class="contribution-unit">${changed ? 'Δ LOGIT' : 'LOGIT'}</span></div><p class="contribution-description">${changed ? 'Each bar is the exact change in a feature’s contribution from the all-evidence baseline.' : 'Each bar is a feature’s signed contribution relative to its training mean.'} Values add in logit space.</p><ol class="contribution-list">${bars}</ol><div class="logit-equation"><span>${changed ? 'Total logit change' : 'Intercept + feature terms'}</span><strong>${changed ? signedNumber(assessment.delta.logit, 4) : `${signedNumber(decomposition.intercept, 4)} + (${signedNumber(current.logit - decomposition.intercept, 4)}) = ${signedNumber(current.logit, 4)}`}</strong></div><p class="contribution-caption">Negative terms decrease the model logit; positive terms increase it. Bar lengths share one absolute scale. These are model calculations, not biological effects.</p></div>
    </div>
    <details class="assessment-details"><summary>Inspect all ${terms.length} terms, the formula, and model identity <span>Exact arithmetic · no generated attribution</span></summary><div class="assessment-formula"><code>term = coefficient × (feature − training mean) / scale</code><code>logit = intercept + Σ terms · score = sigmoid(logit)</code><p>Baseline logit ${signedNumber(baseline.logit, 6)} → current logit ${signedNumber(current.logit, 6)}. Intercept ${signedNumber(decomposition.intercept, 6)} is unchanged. ${esc(decomposition.degree_divisor || '')}</p></div><div class="assessment-detail-scroll" tabindex="0" role="region" aria-label="Exact model terms table"><table class="assessment-terms-table"><thead><tr><th scope="col">Feature</th><th scope="col">Value before</th><th scope="col">Value current</th><th scope="col">Coefficient</th><th scope="col">Term before</th><th scope="col">Term current</th><th scope="col">Term change</th></tr></thead><tbody>${table}</tbody></table></div><p class="assessment-interpretation">${esc(assessment.interpretation)}</p><dl class="assessment-identity"><dt>Model</dt><dd>${esc(model.name)} · ${esc(model.version)}</dd><dt>Model SHA-256</dt><dd><code>${esc(model.model_sha256)}</code></dd><dt>Dataset SHA-256</dt><dd><code>${esc(model.dataset_sha256)}</code></dd></dl><p class="assessment-export-note">The evidence export includes full-precision feature values, means, scales, coefficients, and both assessments. Displayed values are rounded.</p></details>`;
  $('assessment-section').hidden = false;
}

function renderChallenge(pending = false) {
  if (!state.excluded.length) {
    $('challenge-result').innerHTML = '<div class="challenge-neutral"><span class="challenge-orbit">↗</span><strong>All evidence is included.</strong><p>Turn a family off to discover which hypotheses depend on it.</p></div>';
    return;
  }
  const names = state.excluded.map(value => FAMILY_LABELS[value] || value).join(' + ');
  if (pending) {
    $('challenge-result').innerHTML = loading('Recomputing the comparison');
    return;
  }
  const changes = (state.challenge?.changes || []).filter(change => change.before_rank !== change.after_rank).sort((a, b) => {
    const dropA = a.after_rank === null ? 10000 : Math.abs(a.rank_delta || 0);
    const dropB = b.after_rank === null ? 10000 : Math.abs(b.rank_delta || 0);
    return dropB - dropA;
  }).slice(0, 3);
  $('challenge-result').innerHTML = `<span class="challenge-active-label">${icon('info')} ${esc(names)} excluded</span>${state.challengeError ? `<p class="challenge-unavailable">The ranking-wide comparison could not be loaded. ${esc(errorMessage(state.challengeError))}</p>` : changes.length ? changes.map(change => `<div class="challenge-change"><span>${esc(change.name)}</span><span class="rank-comparison">${change.before_rank === null ? 'unranked' : '#' + change.before_rank} → <b>${change.after_rank === null ? 'no paths' : '#' + change.after_rank}</b></span></div>`).join('') : '<div class="challenge-change"><span>No rank changes among displayed candidates.</span></div>'}<p class="challenge-footnote">Same fitted model. Changed evidence. Rank movement is sensitivity, not a biological effect.</p><button id="reset-evidence" class="reset-button">${icon('reset')} Restore all evidence</button>`;
  $('reset-evidence').addEventListener('click', async () => {
    document.querySelectorAll('#evidence-switches input').forEach(input => { input.checked = true; });
    state.excluded = [];
    await loadRankings();
  });
}

function showDialog(eyebrow, content) {
  $('detail-eyebrow').textContent = eyebrow;
  $('detail-content').innerHTML = content;
  $('graph-tooltip').hidden = true;
  if (!$('detail-dialog').open) $('detail-dialog').showModal();
}

function sourceHTML(sources) {
  const entries = sourceEntries(sources);
  return entries.length ? entries.map(source => source.url ? `<a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(source.name)} ↗</a>` : esc(source.name)).join('<br>') : 'Not specified in this source record';
}

function showNode(node) {
  const url = safeURL(node.url || node.data?.url);
  showDialog(`${node.label || 'ENTITY'} / SOURCE RECORD`, `<h2>${esc(node.name)}</h2><p class="record-id">${esc(node.id)}</p><dl class="record-fields"><dt>Entity type</dt><dd>${esc(node.label)}</dd><dt>Identifier</dt><dd>${esc(node.identifier || node.id)}</dd><dt>Source</dt><dd>${sourceHTML(node.sources || node.source || node.data?.source || node.data?.sources)}</dd><dt>License</dt><dd>${esc(objectText(node.license || node.data?.license) || 'Not specified in this source record')}</dd>${url ? `<dt>External record</dt><dd><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open the original record ↗</a></dd>` : ''}</dl><p class="record-note">The name and identifier come from the imported dataset. A missing citation or license is not a claim that the data is independently verified or unrestricted.</p><details class="provenance-raw"><summary>Inspect complete imported record</summary><pre class="record-raw">${esc(JSON.stringify(node, null, 2))}</pre></details>`);
}

function showEdge(edge) {
  const nodes = new Map((state.evidence?.nodes || []).map(node => [node.id, node]));
  showDialog('RELATIONSHIP / SOURCE RECORD', `<h2>${esc(titleCase(edge.type))}</h2><p class="record-id">${esc(edge.id)}</p><dl class="record-fields"><dt>From</dt><dd>${esc(nodes.get(edge.source)?.name || edge.source)}</dd><dt>To</dt><dd>${esc(nodes.get(edge.target)?.name || edge.target)}</dd><dt>Relationship</dt><dd>${esc(edge.type)}</dd><dt>Sources</dt><dd>${sourceHTML(edge.sources || edge.source_names || edge.data?.sources)}</dd><dt>License</dt><dd>${esc(objectText(edge.license || edge.data?.license) || 'Not specified in this source record')}</dd></dl><p class="record-note">This is a consolidated relationship in Hetionet. Source names identify contributing resources; they do not imply that every connection has a primary publication or that multiple resources are independent studies.</p><details class="provenance-raw"><summary>Inspect complete imported record</summary><pre class="record-raw">${esc(JSON.stringify(edge, null, 2))}</pre></details>`);
}

async function askAgent(event) {
  event?.preventDefault();
  const question = $('agent-question').value.trim();
  if (!question || !state.disease || state.busy || state.evidenceBusy) return;
  const request = agentGate.begin(selectedContext());
  const diseaseId = state.disease.id;
  const compoundId = state.candidate?.id || null;
  const excluded = [...state.excluded];
  state.agent = null;
  state.agentBusy = true;
  refreshControls();
  $('agent-submit').innerHTML = '<span class="spinner small"></span><span>Following evidence</span>';
  $('agent-response').hidden = false;
  $('agent-response').className = 'agent-response';
  $('agent-response').innerHTML = loading('Resolving the question and retrieving graph evidence');
  try {
    const response = await api.agent(question, diseaseId, excluded, compoundId);
    if (!agentGate.current(request, selectedContext())) return;
    state.agent = { question, ...response, request_context: request.context };
    renderAgent(response);
  } catch (error) {
    if (!agentGate.current(request, selectedContext())) return;
    $('agent-response').innerHTML = inlineError(error, 'retry-agent');
    $('retry-agent')?.addEventListener('click', () => askAgent());
  } finally {
    if (agentGate.current(request, selectedContext())) {
      state.agentBusy = false;
      $('agent-submit').innerHTML = `<span>Investigate</span>${icon('arrow')}`;
      refreshControls();
    }
  }
}

function renderAgent(response) {
  const rejected = response.status === 'rejected';
  $('agent-response').classList.toggle('rejected', rejected);
  const label = rejected ? 'REQUEST REJECTED' : response.status === 'clarification' ? 'A LITTLE MORE CONTEXT' : 'EVIDENCE BRIEF';
  const mode = response.mode === 'llm' ? 'LLM + verified tools' : api.mode === 'snapshot' ? 'Deterministic · snapshot' : 'Deterministic · LangGraph';
  const citations = (response.citations || []).map(citation => {
    const labelText = typeof citation === 'string' ? citation : citation.label || citation.id || citation.title || 'Evidence record';
    const url = safeURL(typeof citation === 'object' ? citation.url : null);
    return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(labelText)} ↗</a>` : `<span>${esc(labelText)}</span>`;
  }).join('');
  const trace = (response.trace || []).map(step => `<li><b>${esc(step.tool || step.step || 'step')} · ${esc(step.status || 'complete')}</b>${esc(step.summary || '')}</li>`).join('');
  const scope = [response.compound?.name, response.disease?.name].filter(Boolean).join(' · ');
  const sameScope = agentMatchesInvestigation(state.agent, state.disease?.id, state.candidate?.id, state.excluded);
  $('agent-response').innerHTML = `<div class="agent-response-header"><span>${rejected ? '○' : '✳'} ${label}</span><span>${esc(mode)}</span></div>${scope ? `<p class="agent-scope"><strong>${esc(scope)}</strong>${sameScope ? '' : '<span>This answer uses a different investigation scope and is not attached to the current case export.</span>'}</p>` : ''}<div class="agent-answer">${esc(response.answer || 'No answer was returned.')}</div>${citations ? `<div class="agent-citations">${citations}</div>` : ''}${trace ? `<details class="agent-trace" open><summary>Inspect ${response.trace.length} workflow steps</summary><ol class="trace-list">${trace}</ol></details>` : ''}<p class="agent-disclaimer">${esc(response.disclaimer || 'Research hypotheses, not validated treatments.')}</p>`;
}

async function loadEvaluation() {
  try {
    state.evaluation = await api.evaluation();
    renderEvaluation(state.evaluation || {});
  } catch (error) {
    $('benchmark-content').innerHTML = inlineError(error, 'retry-evaluation');
    $('retry-evaluation')?.addEventListener('click', loadEvaluation);
  }
}

function renderEvaluation(report) {
  const rows = metricRows(report);
  if (!rows.length) { $('benchmark-content').innerHTML = '<div class="empty-message">No executed benchmark report is available in this edition. The interface will not invent evaluation metrics.</div>'; return; }
  const maximum = Math.max(...rows.map(row => metricValue(row, 'recall_at_10') || 0), .01);
  const mainModel = rows.find(row => /logistic|ariadne|typed/i.test(row.model || row.name || '')) || rows[0];
  const split = report.split || {};
  const splitCount = key => Number(split[key]?.count ?? split[key] ?? 0);
  const train = splitCount('train'), validation = splitCount('validation') || splitCount('val'), test = splitCount('test');
  const total = train + validation + test || 1;
  const protocol = report.protocol || {};
  const protocolEntries = typeof protocol === 'string' ? [['Protocol', protocol]] : Object.entries(protocol).filter(([key]) => !['split_fractions', 'graph', 'llm_role', 'metrics', 'ablation'].includes(key));
  const selectedProtocol = protocolEntries.filter(([key]) => ['task', 'split_unit', 'candidate_universe', 'unobserved_sampling', 'negative_label_meaning', 'preprocessing', 'hyperparameters'].includes(key));
  const entries = selectedProtocol.length ? selectedProtocol : protocolEntries.slice(0, 7);
  const examples = Array.isArray(report.examples) ? report.examples : Object.entries(report.examples || {}).map(([outcome, value]) => ({ outcome, ...value }));
  const examplesHTML = examples.map(example => {
    const failure = /miss|fail/i.test(example.outcome || '') || Number(example.rank) > 10;
    return `<article class="example-card${failure ? ' failure' : ''}"><span class="eyebrow">${failure ? 'A MISS THAT MATTERS' : 'A RECOVERED LINK'}</span><h3>${esc(objectText(example.compound || example.compound_name || 'Compound'))}</h3><div class="example-disease">${esc(objectText(example.disease || example.disease_name || 'Disease'))}</div><span class="example-rank">#${number(example.rank)} <small style="font-size:10px;letter-spacing:0;color:var(--muted)">of ${number(example.candidate_count || protocol.candidate_count)} candidates</small></span><p>${esc(example.explanation || (failure ? 'This recorded treatment link was held out and did not appear in the top 10. The graph representation and scoring model miss useful biological information.' : 'This recorded treatment link was held out and recovered among the top 10 candidates. Recovery is retrospective evidence about retrieval, not validation of a new treatment.'))}</p></article>`;
  }).join('');
  const limitations = Array.isArray(report.limitations) ? report.limitations : report.limitations ? [objectText(report.limitations)] : [
    'The split is transductive: entities and biological evidence are shared across training and test.',
    'Unobserved pairs are not proven negative treatment relationships.',
    'Graph associations and rank changes do not establish biological causality.',
    'The benchmark measures retrospective label recovery, not prospective clinical performance.'
  ];
  $('benchmark-content').innerHTML = `
    <div class="benchmark-grid"><article class="benchmark-card"><span class="eyebrow" style="color:var(--green-2);display:block;margin-bottom:11px">HELD-OUT TEST SET</span><h2>A model earns its ranking.</h2><p>All reported methods use the same candidate universe and test links.</p><table class="benchmark-table"><thead><tr><th scope="col">Method</th><th scope="col">Recall@10</th><th scope="col">MRR</th></tr></thead><tbody>${rows.map(row => `<tr${row === mainModel ? ' class="featured"' : ''}><td>${esc(row.name || row.model || 'Model')}</td><td>${pct(metricValue(row, 'recall_at_10'))}</td><td>${score(metricValue(row, 'mrr'))}</td></tr>`).join('')}</tbody></table><div aria-label="Recall at 10 comparison">${rows.map(row => `<div class="metric-bar-row${row === mainModel ? ' featured' : ''}"><span class="metric-bar-name">${esc(row.name || row.model || 'Model')}</span><span class="metric-bar-track"><span class="metric-bar-value" style="display:block;width:${Math.max(0, (metricValue(row, 'recall_at_10') || 0) / maximum * 100)}%"></span></span><span class="metric-bar-number">${pct(metricValue(row, 'recall_at_10'))}</span></div>`).join('')}</div><p class="metric-definition"><strong>Recall@10</strong> measures the share of held-out treatment links recovered in the first ten results. <strong>MRR</strong> rewards placing each held-out link near the top. Bars are scaled to the best displayed Recall@10.</p></article>
    <article class="benchmark-card"><span class="eyebrow" style="color:var(--green-2);display:block;margin-bottom:11px">THE EXPERIMENT</span><h2>The split stays visible.</h2><p>${number(test || mainModel.evaluated_links)} held-out treatment links${mainModel.evaluated_diseases ? ` across ${number(mainModel.evaluated_diseases)} diseases` : ''}.</p>${train || test ? `<div class="split-strip" aria-label="Train ${train}, validation ${validation}, test ${test}"><span class="split-segment train" style="width:${train / total * 100}%"></span><span class="split-segment val" style="width:${validation / total * 100}%"></span><span class="split-segment test" style="width:${test / total * 100}%"></span></div><div class="split-legend"><span>Train <b>${number(train)}</b></span><span>Validation <b>${number(validation)}</b></span><span>Test <b>${number(test)}</b></span></div>` : ''}<ul class="protocol-list">${entries.map(([key, value]) => `<li><strong>${esc(titleCase(key))}</strong>${esc(objectText(value))}</li>`).join('')}</ul></article></div>
    <div class="evaluation-footnote"><strong>Leakage boundary.</strong> ${esc(typeof protocol.graph === 'string' ? protocol.graph : 'Treatment and palliation relationships are excluded from every evidence graph and feature computation.')} ${esc(typeof protocol.llm_role === 'string' ? `LLM contribution to the benchmark: ${protocol.llm_role}.` : 'The language model does not generate rankings or benchmark answers.')}</div>
    ${examples.length ? `<section class="examples-section"><div class="section-heading"><h2>Show the hits. Show the misses.</h2><span>Selected held-out examples</span></div><div class="example-grid">${examplesHTML}</div></section>` : ''}
    ${Array.isArray(report.ablations) && report.ablations.length ? `<section class="examples-section"><div class="section-heading"><h2>What changes when evidence disappears?</h2><span>The same fitted model</span></div><article class="benchmark-card"><table class="benchmark-table" style="margin-top:0"><thead><tr><th scope="col">Excluded evidence</th><th scope="col">Recall@10</th><th scope="col">MRR</th></tr></thead><tbody>${report.ablations.map(row => `<tr><td>${esc((row.excluded || []).map(family => FAMILY_LABELS[family] || family).join(', '))}</td><td>${pct(metricValue(row, 'recall_at_10'))}</td><td>${score(metricValue(row, 'mrr'))}</td></tr>`).join('')}</tbody></table><p class="comparison-note">Stable aggregate recall can coexist with substantial changes in individual candidate rankings. This is a sensitivity analysis, not a causal experiment.</p></article></section>` : ''}
    <section class="examples-section"><div class="section-heading"><h2>What this experiment cannot tell us.</h2></div><ul class="limitation-list">${limitations.map(item => `<li>${esc(objectText(item))}</li>`).join('')}</ul></section>
    <details class="benchmark-extra"><summary>Inspect the complete reproducible evaluation report</summary><pre>${esc(JSON.stringify(report, null, 2))}</pre></details><div style="padding:18px 0 32px;font-size:9px;color:var(--muted)">Dataset SHA-256: <span style="font-family:var(--mono);overflow-wrap:anywhere">${esc(report.dataset_sha256 || state.stats?.dataset_sha256 || 'Not recorded')}</span></div>`;
}

async function loadProvenance() {
  try {
    state.provenance = await api.provenance();
    renderProvenance(state.provenance || {});
  } catch (error) {
    $('provenance-content').innerHTML = inlineError(error, 'retry-provenance');
    $('retry-provenance')?.addEventListener('click', loadProvenance);
  }
}

function renderProvenance(provenance) {
  const citation = provenance.citation || {};
  const citationURL = safeURL(typeof citation === 'object' ? citation.doi || citation.url : citation);
  const sourceURL = safeURL(provenance.url || provenance.source_url || provenance.repository || citation.repository);
  const rows = [
    ['Dataset', `${provenance.dataset || state.stats.dataset || 'Hetionet'} ${provenance.version || state.stats.version || ''}`],
    ['Source version', provenance.upstream_commit || provenance.source_commit || provenance.version || 'Not recorded'],
    ['Evidence graph', `${number(provenance.nodes || state.stats.nodes)} entities · ${number(provenance.edges || state.stats.edges)} relationships`],
    ['Label boundary', objectText(provenance.excluded_from_features || ['TREATS', 'PALLIATES']) + ' excluded from predictive features'],
    ['Licensing', provenance.license_policy || provenance.licensing || 'Constituent resources retain their own terms; inspect node and relationship metadata.'],
    ['Provenance', provenance.provenance_policy || 'Available source metadata is preserved. A missing primary citation is not fabricated.']
  ];
  $('provenance-content').innerHTML = `<dl class="provenance-record">${rows.map(([label, value]) => `<div class="provenance-row"><dt>${esc(label)}</dt><dd>${esc(objectText(value))}</dd></div>`).join('')}<div class="provenance-row"><dt>SHA-256</dt><dd><code>${esc(provenance.dataset_sha256 || state.stats.dataset_sha256 || 'Not recorded')}</code></dd></div>${citationURL ? `<div class="provenance-row"><dt>Original research</dt><dd><a href="${esc(citationURL)}" target="_blank" rel="noopener noreferrer">${esc(citation.title || 'Original Hetionet publication')} ↗</a></dd></div>` : ''}${sourceURL ? `<div class="provenance-row"><dt>Source data</dt><dd><a href="${esc(sourceURL)}" target="_blank" rel="noopener noreferrer">Inspect the versioned source ↗</a></dd></div>` : ''}</dl><details class="provenance-raw"><summary>Inspect the complete source manifest</summary><pre>${esc(JSON.stringify(provenance, null, 2))}</pre></details>`;
}

function exportCase() {
  if (!state.evidence || !state.assessment || state.busy || state.evidenceBusy) return;
  const payload = {
    application: 'ARIADNE', version: state.health?.version || '1.2.0',
    exported_at: new Date().toISOString(), edition: api.mode,
    disease: state.disease, selected_compound: state.candidate,
    excluded_families: state.excluded, ranking: state.rankings,
    assessment: state.assessment, evidence: state.evidence, challenge: state.challenge,
    agent_brief: agentMatchesInvestigation(state.agent, state.disease?.id, state.candidate?.id, state.excluded) ? state.agent : null,
    dataset_sha256: state.stats?.dataset_sha256,
    model: state.stats?.model,
    interpretation: 'Research hypotheses and recorded graph evidence. Not clinical advice or a causal intervention.'
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `ariadne-${state.disease.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}-evidence.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast('Evidence export prepared, including source records and dataset identity.');
}

async function shareCase() {
  updateURLState();
  try {
    if (!navigator.clipboard) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(location.href);
    toast('Case link copied. The disease, candidate, and evidence settings are preserved.');
  } catch {
    showDialog('SHARE THIS INVESTIGATION', `<h2>Keep the thread.</h2><p class="record-note">This link preserves the disease, candidate, and excluded evidence families. The recipient needs access to the same application edition.</p><input class="share-input" id="share-link-input" aria-label="Case link" readonly value="${esc(location.href)}">`);
    $('share-link-input').focus();
    $('share-link-input').select();
  }
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
$('retry-boot').addEventListener('click', boot);
$('disease-search').addEventListener('focus', openSearch);
$('disease-search').addEventListener('click', openSearch);
$('disease-search').addEventListener('input', event => renderDiseaseOptions(event.target.value));
$('disease-search').addEventListener('keydown', event => {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); if ($('disease-options').hidden) openSearch(); moveSearch(event.key === 'ArrowDown' ? 1 : -1); }
  if (event.key === 'Escape') closeSearch();
  if (event.key === 'Enter' && !$('disease-options').hidden) {
    event.preventDefault();
    const disease = state.shownDiseases[state.searchIndex >= 0 ? state.searchIndex : 0];
    if (disease) chooseDisease(disease);
  }
});
$('disease-options').addEventListener('click', event => {
  const option = event.target.closest('[data-disease-index]');
  if (option) chooseDisease(state.shownDiseases[Number(option.dataset.diseaseIndex)]);
});
$('disease-options').addEventListener('pointerdown', event => {
  if (event.pointerType === 'mouse' && event.target.closest('[data-disease-index]')) event.preventDefault();
});
document.querySelector('.disease-selector').addEventListener('focusout', event => {
  if (!event.currentTarget.contains(event.relatedTarget)) closeSearch();
});
document.addEventListener('click', event => { if (!event.target.closest('.disease-selector')) closeSearch(); });
document.addEventListener('keydown', event => {
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) && !$('detail-dialog').open) {
    event.preventDefault(); setView('investigate'); $('disease-search').focus(); $('disease-search').select();
  }
});
$('candidate-list').addEventListener('click', event => {
  const button = event.target.closest('[data-compound-id]');
  if (!button) return;
  const candidate = state.rankings?.candidates.find(item => item.id === button.dataset.compoundId);
  if (candidate) chooseCandidate(candidate);
});
$('load-more').addEventListener('click', async () => {
  if (!state.rankings || state.busy) return;
  const request = pageGate.begin(rankingContext());
  $('load-more').disabled = true;
  const diseaseId = state.disease.id;
  const excluded = [...state.excluded];
  const offset = state.rankings.candidates.length;
  try {
    const next = await api.rankings(diseaseId, excluded, 12, offset);
    if (!pageGate.current(request, rankingContext())) return;
    const combined = appendRankingPage(state.rankings, next, offset);
    if (!combined) return;
    state.rankings = combined;
    if (state.candidate) state.candidate.pinned = !combined.candidates.some(candidate => candidate.id === state.candidate.id);
    renderCandidates();
  } catch (error) { if (pageGate.current(request, rankingContext())) toast(errorMessage(error)); }
  finally { if (pageGate.current(request, rankingContext())) $('load-more').disabled = false; }
});
$('evidence-switches').addEventListener('change', async event => {
  if (!event.target.matches('input')) return;
  state.excluded = currentExcluded();
  state.filter = 'all';
  await loadRankings();
});
$('path-family-strip').addEventListener('click', event => {
  const button = event.target.closest('[data-path-filter]');
  if (!button) return;
  state.filter = button.dataset.pathFilter;
  state.activePath = null;
  renderEvidence();
});
$('path-list').addEventListener('click', event => {
  const button = event.target.closest('[data-path-id]');
  if (!button) return;
  state.activePath = state.activePath === button.dataset.pathId ? null : button.dataset.pathId;
  graph.highlight(state.activePath);
  document.querySelectorAll('.path-card').forEach(card => {
    const active = card.dataset.pathId === state.activePath;
    card.classList.toggle('active', active);
    card.setAttribute('aria-pressed', String(active));
  });
});
$('fit-graph').addEventListener('click', () => {
  graph.reset(); state.activePath = null;
  document.querySelectorAll('.path-card').forEach(card => { card.classList.remove('active'); card.setAttribute('aria-pressed', 'false'); });
});
$('agent-form').addEventListener('submit', askAgent);
document.querySelectorAll('[data-prompt]').forEach(button => button.addEventListener('click', () => {
  $('agent-question').value = button.dataset.prompt;
  $('agent-question').focus();
  askAgent();
}));
$('export-case').addEventListener('click', exportCase);
$('share-case').addEventListener('click', shareCase);
$('open-audit').addEventListener('click', () => auditPanel.focus());
document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => $('detail-dialog').close()));
$('detail-dialog').addEventListener('click', event => {
  const rect = $('detail-dialog').getBoundingClientRect();
  if (event.target === $('detail-dialog') && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) $('detail-dialog').close();
});
boot();
