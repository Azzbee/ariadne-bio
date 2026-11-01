import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { AriadneAPI } from '../api.js';
import { MixedSession, mixedParameters, mixedKey, validateMixedAudit, mixedVerdict } from '../mixed-model.js';
import { mixedWitnessHTML } from '../mixed.js';
import { copyJSON } from '../audit-model.js';
import { validateSnapshotCase } from '../integrity.js';

const certificate = JSON.parse(await readFile(new URL('fixtures/mixed-marimastat.json', import.meta.url), 'utf8'));
const disease = certificate.disease.id, compound = certificate.compound.id;
const verification = { status: 'verified', valid: true, checks: ['Unit fixture verification record'], errors: [], certificate_sha256: certificate.certificate_sha256, verification_execution: 'recorded_at_export', replayed_witnesses: 2 };
const response = (data, bytes = Buffer.from(JSON.stringify(data))) => ({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => data, arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) });
function fixture() {
  const data = { disease: certificate.disease, mixed_audits: { [compound]: { '10:1:1': copyJSON(certificate) } }, mixed_verifications: { [compound]: { '10:1:1': copyJSON(verification) } } };
  const identity = certificate.identity;
  const manifest = { cases: { [disease]: { file: 'cases/example.json' } }, diseases: [certificate.disease], dataset_sha256: identity.dataset_sha256, graph_sha256: identity.graph_sha256, model_sha256: identity.model_sha256, stats: {}, provenance_catalog: { identity: { ...identity }, items: certificate.scope.groups } };
  return { data, manifest };
}
function apiWith(f = fixture()) {
  const calls = [], bytes = Buffer.from(JSON.stringify(f.data));
  f.manifest.files = [{ path: 'cases/example.json', bytes: bytes.byteLength, sha256: createHash('sha256').update(bytes).digest('hex') }];
  const api = new AriadneAPI({}, async (url, options) => { calls.push({ url, options }); if (url === './data/manifest.json') return response(f.manifest); if (url === './data/cases/example.json') return response(f.data, bytes); throw new Error('Unexpected request ' + url); });
  return { api, calls };
}
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { resolve, promise }; }
function sessionWith(api) { const session = new MixedSession(api); session.setFocus(certificate.disease, certificate.compound); return session; }

test('the actual generated certificate passes structural validation and reports its four bounds', () => {
  assert.equal(validateMixedAudit(certificate, disease, compound), certificate);
  assert.deepEqual(certificate.results.map(row => [row.group_budget, row.edge_budget, row.worst_supported_rank]), [[0, 0, 1], [0, 1, 1], [1, 0, 1096], [1, 1, 1096]]);
  assert.equal(mixedVerdict(certificate).kind, 'fragile');
  assert.equal(mixedKey(), '10:1:1');
});

test('live joint audit requests declare explicit simultaneous budgets and preserve the full certificate', async () => {
  const calls = [], api = new AriadneAPI({}, async (url, options) => { calls.push({ url, options }); return response(certificate); }); api.mode = 'live';
  await api.mixedAudit(disease, compound, { groupKind: 'pubmed', groupIds: ['pubmed:200', 'pubmed:100'] });
  assert.equal(calls[0].url, '/api/mixed/audit');
  assert.deepEqual(JSON.parse(calls[0].options.body), { disease_id: disease, compound_id: compound, top_k: 10, group_budget: 1, edge_budget: 1, group_kind: 'pubmed', group_ids: ['pubmed:100', 'pubmed:200'] });
  await api.verifyMixedAudit(certificate);
  assert.equal(calls[1].url, '/api/mixed/audit/verify');
  assert.deepEqual(JSON.parse(calls[1].options.body), { certificate });
});

test('invalid joint budgets and group selections fail before any network request', async () => {
  let calls = 0; const api = new AriadneAPI({}, async () => { calls += 1; }); api.mode = 'live';
  for (const options of [{ topK: 0 }, { topK: 101 }, { groupBudget: 2 }, { edgeBudget: -1 }, { edgeBudget: true }, { groupBudget: 0.5 }, { groupKind: 'x' }, { groupKind: 'pubmed' }, { groupIds: [] }, { groupIds: ['source:x', 'source:x'] }, { groupIds: ['pubmed:1'] }, { groupIds: Array.from({ length: 17 }, (_, i) => `source:${i}`) }]) await assert.rejects(api.mixedAudit(disease, compound, options));
  assert.equal(calls, 0);
  assert.deepEqual(mixedParameters({ groupIds: ['source:z', 'source:a'] }).groupIds, ['source:a', 'source:z']);
});

test('recorded joint audits use a byte-verified lazy case, detached copies and their exact stored verification', async () => {
  const { api, calls } = apiWith(); await api.initialize(true);
  const first = await api.mixedAudit(disease, compound), second = await api.mixedAudit(disease, compound);
  first.compound.name = 'Changed locally';
  assert.equal(second.compound.name, 'Marimastat');
  assert.deepEqual(await api.verifyMixedAudit(second), verification);
  assert.equal(calls.filter(call => call.url.endsWith('cases/example.json')).length, 1);
  second.results[3].covered_action_representations += 1;
  assert.equal((await api.verifyMixedAudit(second)).valid, false);
});

test('recorded mode never invents custom scopes, missing audit cells or successful verification', async () => {
  const f = fixture(); delete f.data.mixed_verifications[compound]['10:1:1'];
  const { api } = apiWith(f); await api.initialize(true);
  await assert.rejects(api.mixedAudit(disease, compound, { groupIds: ['source:DrugBank (target)'] }), /live application/);
  await assert.rejects(api.mixedAudit(disease, compound, { groupBudget: 0 }), /not included/);
  await assert.rejects(api.verifyMixedAudit(certificate), /no matching successful recorded verification/);
});

test('a complete group catalogue and matching scientific identities are required', async () => {
  const f = fixture(); f.manifest.provenance_catalog.items = f.manifest.provenance_catalog.items.slice(1);
  const { api } = apiWith(f); await api.initialize(true);
  await assert.rejects(api.mixedAudit(disease, compound), /complete published source-label catalog/);
  for (const key of ['dataset_sha256', 'graph_sha256', 'model_sha256', 'group_map_sha256']) {
    const f2 = fixture(); f2.data.mixed_audits[compound]['10:1:1'].identity[key] = '0'.repeat(64);
    assert.throws(() => validateSnapshotCase(f2.data, f2.manifest, disease), /does not match/);
  }
});

const changes = [
  ['wrong case', c => { c.disease.id = 'other'; }],
  ['unknown scorer', c => { c.identity.scorer = 'approximate'; }],
  ['missing competitors', c => { c.scope.includes_competitor_changes = false; }],
  ['missing cell', c => { c.results.pop(); }],
  ['duplicate cell', c => { c.results[3] = copyJSON(c.results[2]); }],
  ['false verdict', c => { c.results[3].robust = true; }],
  ['false origin', c => { c.results[0].worst_supported_rank = 2; }],
  ['unsupported missing witness', c => { c.results[3].unsupported_attainable = true; c.results[3].unsupported_witness = null; }],
  ['witness exceeds budget', c => { c.results[0].rank_witness.residual_edge_ids = ['a']; }],
  ['unknown group', c => { c.results[3].rank_witness.group_ids = ['source:unknown']; }],
  ['false witness rank', c => { c.results[3].rank_witness.focus.after.rank = 5; }],
  ['wrong witness baseline', c => { c.results[3].rank_witness.focus.before.score = 0; }],
  ['invented full preview', c => { c.results[0].rank_witness.removed_edge_count = 1; }],
  ['wrong proof coverage', c => { c.proof.covered_action_representations += 1; }],
  ['forged representation coverage', c => { c.results[3].covered_action_representations += 1; c.proof.covered_action_representations += 1; }],
  ['double-counted group record', c => { c.results[3].rank_witness.residual_edge_ids = [c.results[3].rank_witness.removed_edges_preview[0].id]; }]
];
for (const [name, change] of changes) test(`joint display rejects ${name}`, () => { const c = copyJSON(certificate); change(c); assert.throws(() => validateMixedAudit(c, disease, compound), /inconsistent/); });

test('late joint results cannot replace a newly selected compound or be exported', async () => {
  const pending = deferred(), session = sessionWith({ mixedAudit: () => pending.promise });
  const run = session.run(); session.setFocus(certificate.disease, { id: 'new', name: 'New' }); pending.resolve(certificate); await run;
  assert.equal(session.certificate, null); assert.equal(session.exportCertificate(), null); assert.equal(session.busy, false);
});

test('a new audit invalidates pending verification even when the selected compound is unchanged', async () => {
  const pending = deferred(), session = sessionWith({ mixedAudit: async () => certificate, verifyMixedAudit: () => pending.promise });
  await session.run(); const verify = session.verify(); await session.run(); pending.resolve(verification); await verify;
  assert.equal(session.verification, null); assert.equal(session.verifying, false);
  const exported = session.exportCertificate(); exported.baseline.rank = 9;
  assert.equal(session.exportCertificate().baseline.rank, 1);
});

test('malformed verifier success stays an error instead of becoming a verification badge', async () => {
  const session = sessionWith({ mixedAudit: async () => certificate, verifyMixedAudit: async () => ({ ...verification, errors: ['Replay failed'] }) });
  await session.run(); await session.verify();
  assert.equal(session.verification, null); assert.match(session.verificationError.message, /inconsistent/);
});

test('interaction wording requires both separate tests to hold and the joint test to fail', () => {
  const c = copyJSON(certificate);
  c.results[2].robust = true;
  assert.equal(mixedVerdict(c).kind, 'interaction');
  c.results[1].robust = false;
  assert.equal(mixedVerdict(c).kind, 'fragile');
  c.baseline.rank = 11;
  assert.equal(mixedVerdict(c).kind, 'outside');
  c.baseline.supported = false;
  assert.equal(mixedVerdict(c).kind, 'unsupported');
});

test('untrusted group labels, record identifiers and sources remain inert in witness markup', () => {
  const c = copyJSON(certificate), witness = c.results[3].rank_witness;
  c.scope.groups.find(group => group.group_id === witness.group_ids[0]).label = '<img src=x onerror=alert(1)>';
  witness.removed_edges_preview[0].source = '<script>bad</script>';
  witness.removed_edges_preview[0].sources = ['<svg onload=bad>'];
  witness.residual_edge_ids = ['<img src=x>'];
  const html = mixedWitnessHTML(c, witness);
  assert.ok(!html.includes('<script>')); assert.ok(!html.includes('<img')); assert.ok(!html.includes('<svg onload'));
  assert.ok(html.includes('&lt;img')); assert.ok(html.includes('&lt;script&gt;')); assert.match(html, /at most six records/);
});
