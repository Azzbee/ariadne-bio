import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';
import { initialView, viewURL, RECORDED_CASE, demoState } from '../landing-model.js';
import { initializeLanding } from '../landing.js';

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

let snapshot = true;
const dataRoot = new URL('../data/', import.meta.url);
try { await access(new URL('manifest.json', dataRoot)); } catch { snapshot = false; }
test('the illustration agrees exactly with retained group and individual certificates', { skip: !snapshot }, async () => {
  const manifest = JSON.parse(await readFile(new URL('manifest.json', dataRoot), 'utf8'));
  const data = JSON.parse(await readFile(new URL(manifest.cases[RECORDED_CASE.disease].file, dataRoot), 'utf8'));
  const c = data.provenance_audits[RECORDED_CASE.compound]['10:1'];
  assert.equal(c.certificate_sha256, RECORDED_CASE.certificate);
  assert.equal(c.identity.model_sha256, RECORDED_CASE.model);
  assert.equal(c.baseline.rank, RECORDED_CASE.baselineRank);
  assert.equal(c.baseline.evidence_count, RECORDED_CASE.baselinePaths);
  const witness = c.results[1].rank_witness;
  assert.deepEqual(witness.group_ids, [`source:${RECORDED_CASE.source}`]);
  assert.equal(witness.focus.after.rank, RECORDED_CASE.groupWorstRank);
  assert.equal(witness.focus.after.evidence_count, RECORDED_CASE.groupPaths);
  assert.equal(witness.removed_edge_count, RECORDED_CASE.removedRecords);
  assert.equal(witness.affected_compound_count, RECORDED_CASE.affectedCompounds);
  assert.equal(data.audits[RECORDED_CASE.compound]['10:2'].results[2].worst_supported_rank, RECORDED_CASE.individualWorstRank);
});
