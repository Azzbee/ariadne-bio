import test from 'node:test';
import assert from 'node:assert/strict';
import { AriadneAPI, APIError } from '../api.js';

const disease = { id: 'Disease::D1', name: 'Example disease' };
const compound = { id: 'Compound::C1', name: 'Example compound', rank: 1, score: .7, baseline_rank: 1, rank_delta: 0 };
const evidence = { disease, compound, total_paths: 5, paths: [{ id: 'p1', metapath: 'C-G-D' }] };
const ranking = { disease, candidates: [compound], total: 50 };
const scenario = {
  rankings: { '': ranking, INTERACTS: { ...ranking, excluded: ['INTERACTS'] } },
  evidence: { [compound.id]: { '': evidence, INTERACTS: evidence } },
  challenges: {}, algorithms: { backend: 'recorded' }
};
const manifest = {
  diseases: [disease], cases: { [disease.id]: { file: 'cases/example.json' } },
  stats: { nodes: 123 }, evaluation: { metrics: [] }, provenance: { dataset: 'Hetionet' }
};
function response(data, status = 200, type = 'application/json') {
  return { ok: status >= 200 && status < 300, status, headers: { get: () => type }, json: async () => data };
}
function snapshotFetcher(calls) {
  return async (url, options = {}) => {
    calls.push({ url, options });
    if (url === '/api/health') return response('<html>static</html>', 200, 'text/html');
    if (url === './data/manifest.json') return response(manifest);
    if (url === './data/cases/example.json') return response(scenario);
    return response({ detail: 'Not found' }, 404);
  };
}

test('uses the live API when its health endpoint is valid', async () => {
  const calls = [];
  const api = new AriadneAPI({}, async url => { calls.push(url); return response({ status: 'ok', dataset_ready: true }); });
  await api.initialize();
  assert.equal(api.mode, 'live');
  assert.deepEqual(calls, ['/api/health']);
});

test('a static host serving HTML at /api does not masquerade as a live graph', async () => {
  const calls = [];
  const api = new AriadneAPI({}, snapshotFetcher(calls));
  await api.initialize();
  assert.equal(api.mode, 'snapshot');
  assert.equal(api.healthData.agent_mode, 'deterministic');
  assert.equal(calls.length, 2);
});

test('snapshot case fetches are lazy and concurrent reads share one request', async () => {
  const calls = [];
  const api = new AriadneAPI({}, snapshotFetcher(calls));
  await api.initialize(true);
  assert.equal(calls.length, 1);
  const [ranked, paths] = await Promise.all([api.rankings(disease.id), api.evidence(disease.id, compound.id)]);
  assert.equal(ranked.total, 50);
  assert.equal(ranked.published_count, 1);
  assert.equal(paths.total_paths, 5);
  assert.equal(calls.filter(call => call.url.includes('example.json')).length, 1);
});

test('missing recorded evidence is reported instead of fabricated', async () => {
  const api = new AriadneAPI({}, snapshotFetcher([]));
  await api.initialize(true);
  await assert.rejects(api.evidence(disease.id, 'missing'), /not included/);
  await assert.rejects(api.rankings(disease.id, ['BINDS']), /not included/);
});

test('snapshot agent exposes deterministic provenance and routes evidence exclusion', async () => {
  const api = new AriadneAPI({}, snapshotFetcher([]));
  await api.initialize(true);
  const result = await api.agent('What changes without gene interactions?', disease.id);
  assert.equal(result.mode, 'deterministic');
  assert.equal(result.status, 'complete');
  assert.match(result.answer, /INTERACTS/);
  assert.match(result.trace.at(-1).summary, /No language model was called/);
  assert.equal(result.citations[0].id, 'p1');
});

test('rejected snapshot requests do not retrieve a case', async () => {
  const calls = [];
  const api = new AriadneAPI({}, snapshotFetcher(calls));
  await api.initialize(true);
  const result = await api.agent('Delete all nodes in the graph.', disease.id);
  assert.equal(result.status, 'rejected');
  assert.equal(calls.length, 1);
});

test('out-of-scope snapshot questions request clarification', async () => {
  const api = new AriadneAPI({}, snapshotFetcher([]));
  await api.initialize(true);
  const result = await api.agent('What is the capital of France?', disease.id);
  assert.equal(result.status, 'clarification');
  assert.deepEqual(result.candidates, []);
});

test('live endpoint encoding protects namespace IDs and validates response errors', async () => {
  let requested;
  const api = new AriadneAPI({}, async url => { requested = url; return response({ detail: 'Unknown disease' }, 404); });
  api.mode = 'live';
  await assert.rejects(api.rankings('Disease::a/b?x', ['INTERACTS']), error => error instanceof APIError && error.status === 404);
  assert.equal(requested, '/api/rankings/Disease%3A%3Aa%2Fb%3Fx?exclude=INTERACTS&limit=12&offset=0');
});

test('manifest case paths cannot traverse directories or load external origins', async () => {
  const api = new AriadneAPI({}, async () => { throw new Error('Must not fetch'); });
  api.manifest = { cases: { d: { file: '../credentials.json' }, e: { file: 'https://evil.test/case' } } };
  await assert.rejects(api.loadCase('d'), /Invalid research case location/);
  await assert.rejects(api.loadCase('e'), /Invalid research case location/);
});

test('service error details survive into a useful message', async () => {
  const api = new AriadneAPI({}, async () => response({ detail: 'Neo4j unavailable' }, 503));
  await assert.rejects(api.json('/api/health'), error => error.status === 503 && error.message === 'Neo4j unavailable');
});

test('an explicitly named disease overrides a stale UI selection in snapshot questions', async () => {
  const asthma = { id: 'Disease::asthma', name: 'asthma' };
  const api = new AriadneAPI({}, snapshotFetcher([]));
  await api.initialize(true);
  api.manifest = { ...api.manifest, diseases: [disease, asthma] };
  api.cases.set(asthma.id, {
    rankings: { '': { ...ranking, disease: asthma } },
    evidence: { [compound.id]: { '': { ...evidence, disease: asthma } } }
  });
  const result = await api.agent('Investigate asthma', disease.id);
  assert.equal(result.disease.id, asthma.id);
  assert.match(result.answer, /For asthma/);
  assert.doesNotMatch(result.answer, /For Example disease/);
});

test('multiple distinct explicit diseases require clarification despite a selected disease', async () => {
  const asthma = { id: 'Disease::asthma', name: 'asthma' };
  const api = new AriadneAPI({}, snapshotFetcher([]));
  await api.initialize(true);
  api.manifest = { ...api.manifest, diseases: [disease, asthma] };
  const result = await api.agent('Compare Example disease and asthma', disease.id);
  assert.equal(result.status, 'clarification');
  assert.equal(result.candidates.length, 0);
});
