import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { initialView, viewURL, RECORDED_CASE, demoState } from '../landing-model.js';
import { initializeLanding } from '../landing.js';
import { validateAudit } from '../audit-model.js';
import { validateProvenanceAudit } from '../provenance-model.js';

const base = 'https://example.test/research/';

test('fresh visits introduce the product while case and audit deep links retain direct entry', () => {
  assert.equal(initialView(new URLSearchParams()), 'overview');
  assert.equal(initialView(new URLSearchParams('mode=snapshot')), 'overview');
  for (const query of ['disease=d', 'compound=c', 'audit_budget=1', 'dependency_budget=1', 'exclude=INTERACTS']) assert.equal(initialView(new URLSearchParams(query)), 'investigate', query);
  assert.equal(initialView(new URLSearchParams(), '#dependency-section'), 'investigate');
  assert.equal(initialView(new URLSearchParams(), '#audit-method'), 'method');
  assert.equal(initialView(new URLSearchParams('view=benchmark&disease=d')), 'benchmark');
  assert.equal(initialView(new URLSearchParams('view=overview&disease=d')), 'overview');
  assert.equal(initialView(new URLSearchParams('view=untrusted')), 'overview');
});

test('home removes case scopes without dropping edition or unrelated URL parameters', () => {
  const home = viewURL(`${base}?mode=snapshot&view=method&disease=d&compound=c&exclude=BINDS&audit_budget=2&audit_k=5&dependency_budget=1&locale=en#dependency-section`, 'overview');
  assert.equal(home.href, `${base}?mode=snapshot&locale=en`);
  assert.equal(initialView(home.searchParams, home.hash), 'overview');
  const resumed = viewURL(home, 'investigate', { disease: 'd', compound: 'c', excluded: 'INTERACTS' });
  assert.equal(resumed.searchParams.get('view'), 'investigate');
  assert.equal(resumed.searchParams.get('disease'), 'd');
  assert.equal(resumed.searchParams.get('compound'), 'c');
  assert.equal(resumed.searchParams.get('exclude'), 'INTERACTS');
  assert.equal(resumed.searchParams.get('mode'), 'snapshot');
});

test('method navigation retains an actual case without manufacturing one', () => {
  assert.equal(viewURL(base, 'method').searchParams.has('disease'), false);
  const url = viewURL(`${base}?disease=d&compound=old&exclude=BINDS`, 'benchmark', { disease: 'd', compound: 'new', excluded: '' });
  assert.equal(url.searchParams.get('compound'), 'new');
  assert.equal(url.searchParams.has('exclude'), false);
  assert.throws(() => viewURL(base, '<script>'), /Unknown application view/);
});

test('an individual-record bound does not invent a common path count for all choices', () => {
  assert.equal(demoState('records').paths, null);
  assert.equal(demoState('records').rank, 1);
  assert.equal(demoState('source').rank, 1096);
  assert.equal(demoState('source').paths, 206);
  assert.match(demoState('source').detail, /different, larger perturbation/);
  assert.throws(() => demoState('__proto__'), /Unknown recorded example/);
});

class Element extends EventTarget {
  constructor(dataset = {}) {
    super(); this.dataset = dataset; this.attributes = new Map(); this.classes = new Set(); this.textContent = '';
    this.classList = { toggle: (name, enabled) => enabled ? this.classes.add(name) : this.classes.delete(name), add: name => this.classes.add(name) };
  }
  setAttribute(name, value) { this.attributes.set(name, value); }
  click() { this.dispatchEvent(new Event('click')); }
}
function host(reduced = false) {
  const ids = new Map();
  for (const id of ['overview-view', 'landing-case', 'landing-rank', 'landing-rank-label', 'landing-case-state', 'landing-case-status', 'landing-case-explanation', 'landing-case-detail', 'landing-path-count', 'landing-demo-announcement', 'landing-certificate-id', 'landing-motion']) ids.set(id, new Element());
  const buttons = ['baseline', 'records', 'source'].map(demoStep => new Element({ demoStep }));
  const link = new Element();
  ids.get('overview-view').querySelectorAll = query => query === '[data-demo-step]' ? buttons : query === '[data-example-link]' ? [link] : [];
  const document = new EventTarget(); document.getElementById = id => ids.get(id); document.hidden = false;
  const media = new EventTarget(); media.matches = reduced;
  const window = { location: { href: `${base}?view=overview&mode=snapshot&exclude=BINDS` }, matchMedia: () => media };
  return { ids, buttons, link, document, window, media };
}

test('real example controls update visible output, exclusive selection and accessible announcement', () => {
  const h = host(); initializeLanding(h.document, h.window);
  h.buttons[2].click();
  assert.equal(h.ids.get('landing-rank').textContent, '1,096');
  assert.equal(h.ids.get('landing-case').dataset.step, 'source');
  assert.deepEqual(h.buttons.map(button => button.attributes.get('aria-pressed')), ['false', 'false', 'true']);
  assert.match(h.ids.get('landing-demo-announcement').textContent, /1,096/);
  assert.match(h.ids.get('landing-case-detail').textContent, /4,603/);
  h.buttons[1].click();
  assert.equal(h.ids.get('landing-rank').textContent, '1');
  assert.equal(h.ids.get('landing-path-count').textContent, 'All choices checked');
  h.buttons[0].click();
  assert.equal(h.ids.get('landing-path-count').textContent, '1,966 supporting paths');
  const url = new URL(h.link.href);
  assert.equal(url.searchParams.get('mode'), 'snapshot');
  assert.equal(url.searchParams.get('exclude'), null);
  assert.equal(initialView(url.searchParams, url.hash), 'investigate');
});

test('motion respects the initial preference and pauses while the page is not visible', () => {
  const h = host(true); initializeLanding(h.document, h.window);
  const root = h.ids.get('overview-view'), button = h.ids.get('landing-motion');
  assert.equal(root.classes.has('motion-paused'), true);
  assert.equal(button.attributes.get('aria-pressed'), 'true');
  assert.equal(button.textContent, 'Play motion');
  button.click(); assert.equal(root.classes.has('motion-paused'), false);
  h.document.hidden = true; h.document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(root.classes.has('motion-paused'), true);
  h.document.hidden = false; h.document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(root.classes.has('motion-paused'), false);
});

// The landing example explicitly records v1.3, while CI refits the current
// snapshot. Its original complete certificates stay independent of that fit.
// snapshot.test.js separately checks the generated snapshot and its identities.
test('the historical illustration agrees exactly with the sealed v1.3 certificates', async () => {
  const groupBytes = await readFile(new URL('./fixtures/landing-v1.3-provenance.json', import.meta.url));
  const bindingBytes = await readFile(new URL('./fixtures/landing-v1.3-binding.json', import.meta.url));
  assert.equal(createHash('sha256').update(groupBytes).digest('hex'),
    '9353fbe91855eee9021544da862d9bee01840396c010f91aa85fe45523c52e8e');
  assert.equal(createHash('sha256').update(bindingBytes).digest('hex'),
    '816b8f502b8cd15be768b5ef70ec41c8ac047ea0bcffebbb01121697dc8bd570');
  const c = validateProvenanceAudit(JSON.parse(groupBytes), RECORDED_CASE.disease,
    RECORDED_CASE.compound, { topK: 10, budget: 1 });
  const binding = validateAudit(JSON.parse(bindingBytes), RECORDED_CASE.disease,
    RECORDED_CASE.compound, 10, 2);
  assert.equal(c.certificate_sha256, RECORDED_CASE.certificate);
  assert.equal(c.identity.model_sha256, RECORDED_CASE.model);
  assert.equal(binding.certificate_sha256,
    '75a176e19f2f3948cf1758b301f27deceba6e2269a4aaa1d549d5d17dbcd172c');
  for (const key of ['dataset_sha256', 'graph_sha256', 'model_sha256', 'scorer']) {
    assert.equal(binding.identity[key], c.identity[key], key);
  }
  assert.equal(c.baseline.rank, RECORDED_CASE.baselineRank);
  assert.equal(c.baseline.evidence_count, RECORDED_CASE.baselinePaths);
  assert.equal(binding.baseline.rank, RECORDED_CASE.baselineRank);
  assert.equal(binding.baseline.evidence_count, RECORDED_CASE.baselinePaths);
  const witness = c.results[1].rank_witness;
  assert.deepEqual(witness.group_ids, [`source:${RECORDED_CASE.source}`]);
  assert.equal(witness.focus.after.rank, RECORDED_CASE.groupWorstRank);
  assert.equal(witness.focus.after.evidence_count, RECORDED_CASE.groupPaths);
  assert.equal(witness.removed_edge_count, RECORDED_CASE.removedRecords);
  assert.equal(witness.affected_compound_count, RECORDED_CASE.affectedCompounds);
  assert.equal(binding.results[2].worst_supported_rank, RECORDED_CASE.individualWorstRank);
  assert.equal(binding.results[2].unsupported_attainable, false);
  assert.equal(c.results[1].unsupported_attainable, false);
});
