import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { AriadneAPI } from '../api.js';
import { copyJSON, stableJSON } from '../audit-model.js';
import { validateSnapshotCase } from '../integrity.js';
import {
  ProvenanceSession, provenanceDossier, provenanceExampleURL, provenanceKey,
  provenanceParameters, provenanceVerdict, validateProvenanceAudit
} from '../provenance-model.js';

const dataRoot = new URL('../data/', import.meta.url);
const fixtureBytes = fs.readFileSync(new URL('fixtures/provenance-marimastat.json', import.meta.url));
const marimastat = JSON.parse(fixtureBytes.toString('utf8'));
const one = JSON.parse(fs.readFileSync(new URL('fixtures/landing-v1.3-provenance.json', import.meta.url), 'utf8'));
const diseaseId = marimastat.disease.id;
// Immutable real certificates; the following transport records are explicit unit fixtures.
// They exercise browser behavior and do not claim a fresh scientific verification.
const verificationFixture = certificate => ({
  status: 'verified', valid: true, checks: ['Unit response fixture; no verifier executed'], errors: [],
  certificate_sha256: certificate.certificate_sha256, verification_execution: 'recorded_at_export',
  verification_method: 'Unit response fixture; no verifier executed', replayed_witnesses: 0
});
const caseData = {
  disease: marimastat.disease,
  provenance_audits: { [marimastat.compound.id]: { '10:2': marimastat, '10:1': one } },
  provenance_verifications: { [marimastat.compound.id]: { '10:2': verificationFixture(marimastat), '10:1': verificationFixture(one) } }
};
const caseBytes = Buffer.from(JSON.stringify(caseData));
const caseFile = 'cases/provenance-unit-fixture.json';
const manifest = {
  cases: { [diseaseId]: { file: caseFile } }, diseases: [marimastat.disease], ...marimastat.identity, stats: {},
  provenance_catalog: { identity: { ...marimastat.identity }, items: marimastat.scope.groups },
  files: [{ path: caseFile, bytes: caseBytes.byteLength, sha256: createHash('sha256').update(caseBytes).digest('hex') }]
};
const response = (data, bytes = new TextEncoder().encode(JSON.stringify(data))) => ({
  ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => data,
  arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
});
const optionsFor = c => ({ topK: c.top_k, budget: c.budget, groupKind: c.scope.group_kind, groupIds: c.scope.group_ids.length ? c.scope.group_ids : null, protectedGroupIds: c.scope.protected_group_ids });
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function sessionWith(api, c = marimastat) { const session = new ProvenanceSession(api); session.setFocus(c.disease, c.compound); session.setParameters({ budget: c.budget }); return session; }
function snapshotAPI(data = caseData, suppliedManifest = manifest) {
  const calls = [], bytes = data === caseData ? caseBytes : Buffer.from(JSON.stringify(data));
  const fixtureManifest = copyJSON(suppliedManifest), descriptor = fixtureManifest.files.find(item => item.path === manifest.cases[diseaseId].file);
  descriptor.bytes = bytes.byteLength; descriptor.sha256 = createHash('sha256').update(bytes).digest('hex');
  const api = new AriadneAPI({}, async (url, options) => {
    calls.push({ url, options });
    if (url === './data/manifest.json') return response(fixtureManifest);
    if (url === `./data/${manifest.cases[diseaseId].file}`) return response(data, bytes);
    throw new Error('Unexpected request: ' + url);
  });
  return { api, calls };
}

test('immutable provenance unit certificates retain their original identity and byte hash', () => {
  assert.equal(createHash('sha256').update(fixtureBytes).digest('hex'), '84a5bc3d4eefe84b9844ee7dc9fbe5816739aca87cc1c1b5f74a1c1311edb2c4');
  assert.deepEqual(marimastat.identity, one.identity);
  assert.equal(marimastat.certificate_sha256, '7b6bec88464c25177254cd511a4df0d8c0527f77f6dcd73c1bf456bbf087dbb7');
});

test('live provenance calls preserve bounded group and conditional-protection scope', async () => {
  const calls = [], api = new AriadneAPI({}, async (url, options) => { calls.push({ url, options }); return response(marimastat); });
  api.mode = 'live';
  await api.provenanceAudit(diseaseId, marimastat.compound.id, { budget: 1, groupKind: 'pubmed', groupIds: ['pubmed:200', 'pubmed:100'], protectedGroupIds: ['pubmed:100'] });
  assert.equal(calls[0].url, '/api/provenance/audit');
  assert.deepEqual(JSON.parse(calls[0].options.body), { disease_id: diseaseId, compound_id: marimastat.compound.id, top_k: 10, budget: 1, group_kind: 'pubmed', group_ids: ['pubmed:100', 'pubmed:200'], protected_group_ids: ['pubmed:100'] });
  await api.verifyProvenanceAudit(marimastat);
  assert.equal(calls[1].url, '/api/provenance/audit/verify');
  assert.deepEqual(JSON.parse(calls[1].options.body), { certificate: marimastat });
  await api.provenanceGroups('pubmed', '100 & 200', 30, 0);
  assert.equal(calls[2].url, '/api/provenance/groups?kind=pubmed&q=100%20%26%20200&limit=30&offset=0');
});

test('invalid group scopes fail before any API call', async () => {
  let calls = 0; const api = new AriadneAPI({}, async () => { calls += 1; }); api.mode = 'live';
  for (const options of [
    { budget: 3 }, { budget: -1 }, { budget: 1.5 }, { topK: 0 }, { topK: 101 },
    { groupKind: 'unknown' }, { groupKind: 'pubmed' }, { groupIds: [] },
    { groupIds: ['source:a', 'source:a'] }, { groupIds: Array.from({ length: 17 }, (_, index) => `source:${index}`) },
    { groupIds: ['pubmed:1'] }, { groupIds: ['source:a'], protectedGroupIds: ['source:b'] },
    { protectedGroupIds: ['source:a', 'source:a'] }
  ]) await assert.rejects(api.provenanceAudit(diseaseId, marimastat.compound.id, options));
  assert.equal(calls, 0);
  assert.equal(provenanceKey(10, 2), '10:2');
  assert.deepEqual(provenanceParameters({ groupIds: ['source:z', 'source:a'] }).groupIds, ['source:a', 'source:z']);
});

test('source-label records load lazily, retain their exact certificate and bind recorded verification', async () => {
  const { api, calls } = snapshotAPI(); await api.initialize(true);
  const [first, second] = await Promise.all([api.provenanceAudit(diseaseId, marimastat.compound.id), api.provenanceAudit(diseaseId, marimastat.compound.id, { budget: 1 })]);
  assert.equal(first.baseline.rank, 1);
  assert.equal(first.scope.groups.length, 14);
  assert.deepEqual(first.results.map(row => row.scenario_count), [1, 15, 106]);
  assert.deepEqual(second.results.map(row => row.scenario_count), [1, 15]);
  assert.ok(second.results[1].worst_supported_rank > 1000);
  assert.equal(second.proof.scenarios_evaluated, 106);
  assert.equal(second.proof.covered_scenarios, 15);
  first.compound.name = 'Mutated local copy';
  assert.equal((await api.provenanceAudit(diseaseId, marimastat.compound.id)).compound.name, 'Marimastat');
  const verified = await api.verifyProvenanceAudit(second);
  assert.equal(verified.valid, true); assert.equal(verified.verification_execution, 'recorded_at_export');
  assert.equal(calls.filter(call => call.url.endsWith(manifest.cases[diseaseId].file)).length, 1);
});

test('snapshots reject fresh reference scopes and conditional re-audits explicitly', async () => {
  const { api, calls } = snapshotAPI(); await api.initialize(true);
  await assert.rejects(api.provenanceAudit(diseaseId, marimastat.compound.id, { groupKind: 'pubmed', groupIds: ['pubmed:200'] }), /require the live application/);
  await assert.rejects(api.provenanceAudit(diseaseId, marimastat.compound.id, { protectedGroupIds: ['source:DrugBank (target)'] }), /require the live application/);
  await assert.rejects(api.provenanceGroups('pubmed'), /full application/);
  assert.equal(calls.length, 1);
  const catalog = await api.provenanceGroups('source', 'DrugBank');
  assert.equal(catalog.items.length, 4); assert.equal(catalog.total, 4);
});

test('altered certificates never inherit a recorded verification', async () => {
  const { api } = snapshotAPI(); await api.initialize(true);
  const altered = copyJSON(marimastat); altered.protection_plan.minimum_additional_groups += 1;
  const result = await api.verifyProvenanceAudit(altered);
  assert.equal(result.valid, false); assert.equal(result.replayed_witnesses, 0);
});

test('provenance display accepts both declared scorer contracts and rejects unknown identities', () => {
  for (const scorer of ['decimal80-binary64-v1', 'float64-fixed-order-v1']) {
    const certificate = copyJSON(marimastat); certificate.identity.scorer = scorer;
    if (scorer === 'decimal80-binary64-v1') {
      for (const key of ['legacy_score', 'legacy_rank', 'score_difference', 'rank_agrees_with_legacy']) delete certificate.baseline[key];
    }
    // This checks display structure only; the edited fixture is not a resealed certificate.
    assert.equal(validateProvenanceAudit(certificate, diseaseId, certificate.compound.id, { budget: certificate.budget }), certificate);
  }
  for (const scorer of ['decimal80-binary64-v2', 'unknown', null, undefined]) {
    const certificate = copyJSON(marimastat); certificate.identity.scorer = scorer;
    assert.throws(() => validateProvenanceAudit(certificate, diseaseId, certificate.compound.id, { budget: certificate.budget }), /unknown scorer/);
  }
});

test('changing a provenance certificate scorer cannot inherit recorded verification', async () => {
  const { api } = snapshotAPI(); await api.initialize(true);
  const certificate = await api.provenanceAudit(diseaseId, marimastat.compound.id);
  certificate.identity.scorer = certificate.identity.scorer === 'decimal80-binary64-v1' ? 'float64-fixed-order-v1' : 'decimal80-binary64-v1';
  const result = await api.verifyProvenanceAudit(certificate);
  assert.equal(result.valid, false); assert.equal(result.status, 'invalid'); assert.equal(result.replayed_witnesses, 0);
});

test('stale verification records are rejected even when case bytes match their manifest', async () => {
  const data = copyJSON(caseData); data.provenance_verifications[marimastat.compound.id]['10:2'].certificate_sha256 = 'f'.repeat(64);
  const { api } = snapshotAPI(data); await api.initialize(true);
  await assert.rejects(api.verifyProvenanceAudit(marimastat), /no matching successful recorded verification/);
});

test('group audits bind graph, model and complete provenance-map identities before use', () => {
  for (const identity of ['dataset_sha256', 'graph_sha256', 'model_sha256', 'group_map_sha256']) {
    const data = copyJSON(caseData); data.provenance_audits[marimastat.compound.id]['10:2'].identity[identity] = 'f'.repeat(64);
    assert.throws(() => validateSnapshotCase(data, manifest, diseaseId), /integrity check failed/);
  }
  const wrongCatalog = copyJSON(manifest); wrongCatalog.provenance_catalog.identity.graph_sha256 = 'f'.repeat(64);
  assert.throws(() => validateSnapshotCase(caseData, wrongCatalog, diseaseId), /provenance catalog/);
});

test('all exported source certificates pass display invariants and verification bindings', t => {
  let manifestBytes;
  try { manifestBytes = fs.readFileSync(new URL('manifest.json', dataRoot), 'utf8'); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    t.skip('Run make snapshot to verify the generated source-certificate cohort.');
    return;
  }
  // A malformed manifest or missing/corrupt case is an error, never a skipped export.
  const manifest = JSON.parse(manifestBytes);
  let count = 0, maximumBytes = 0;
  for (const [id, descriptor] of Object.entries(manifest.cases)) {
    const bytes = fs.readFileSync(new URL(descriptor.file, dataRoot));
    const record = manifest.files.find(item => item.path === descriptor.file);
    assert.equal(bytes.length, record.bytes); assert.equal(createHash('sha256').update(bytes).digest('hex'), record.sha256);
    const data = JSON.parse(bytes); validateSnapshotCase(data, manifest, id);
    for (const [compoundId, variants] of Object.entries(data.provenance_audits)) {
      for (const [key, certificate] of Object.entries(variants)) {
        validateProvenanceAudit(certificate, id, compoundId, { budget: certificate.budget });
        assert.equal(data.provenance_verifications[compoundId][key].certificate_sha256, certificate.certificate_sha256);
        assert.equal(data.provenance_verifications[compoundId][key].valid, true);
        maximumBytes = Math.max(maximumBytes, Buffer.byteLength(JSON.stringify({ certificate })));
        count += 1;
      }
    }
  }
  assert.equal(count, Object.values(manifest.cases).reduce((sum, entry) => sum + entry.coverage.provenance_audit_count, 0));
  assert.ok(count > 400); assert.ok(maximumBytes <= 256 * 1024, `Largest verification request is ${maximumBytes} bytes`);
});

for (const [name, damage] of [
  ['changed withdrawal rule', c => { c.scope.operation = 'all_sources_removed'; }],
  ['missing competitor scope', c => { c.scope.includes_competitor_changes = false; }],
  ['duplicate selected groups', c => { c.scope.group_ids.push(c.scope.group_ids[0]); }],
  ['wrong available-group count', c => { c.scope.available_group_count -= 1; }],
  ['false robust verdict', c => { c.results[2].robust = !c.results[2].robust; }],
  ['incomplete scenario coverage', c => { c.results[2].scenario_count -= 1; }],
  ['different baseline', c => { c.results[0].worst_supported_rank += 1; }],
  ['negative path count', c => { c.baseline.counts.direct = -1; }],
  ['unsafe numeric count', c => { c.baseline.evidence_count = Number.MAX_SAFE_INTEGER + 1; }],
  ['unscoped witness group', c => { c.results[2].rank_witness.group_ids = ['source:unknown']; }],
  ['false record-preview coverage', c => { c.results[2].rank_witness.preview_truncated = !c.results[2].rank_witness.preview_truncated; }],
  ['false attaining witness', c => { c.results[2].rank_witness.focus.after.rank += 1; }],
  ['false protection minimum', c => { c.protection_plan.minimum_additional_groups += 1; }],
  ['unscoped protection group', c => { c.protection_plan.representative = ['source:unknown']; }],
  ['duplicate shortlist row', c => { c.shortlist[1] = copyJSON(c.shortlist[0]); }],
  ['wrong proof coverage', c => { c.proof.covered_scenarios -= 1; }],
  ['different group-map proof', c => { c.proof.group_map_sha256 = 'f'.repeat(64); }]
]) test(`display rejects ${name}`, () => { const c = copyJSON(marimastat); damage(c); assert.throws(() => validateProvenanceAudit(c, diseaseId, c.compound.id), /inconsistent/); });

test('a stale group audit cannot replace a new compound investigation', async () => {
  const pending = deferred(), session = sessionWith({ provenanceAudit: () => pending.promise });
  const operation = session.run(); session.setFocus(marimastat.disease, { id: 'Compound::other', name: 'Other' });
  pending.resolve(marimastat); assert.equal(await operation, null); assert.equal(session.certificate, null); assert.equal(session.busy, false);
});

test('budget or protection changes invalidate a pending verification', async () => {
  const pending = deferred(), session = sessionWith({ provenanceAudit: async () => marimastat, verifyProvenanceAudit: () => pending.promise });
  await session.run(); const operation = session.verify(); session.setParameters({ budget: 1 });
  pending.resolve({ status: 'verified', valid: true, checks: ['test'], errors: [] });
  assert.equal(await operation, null); assert.equal(session.verification, null); assert.equal(session.certificate, null);
});

test('failed audit and malformed verification responses are visible without stale success', async () => {
  const session = sessionWith({ provenanceAudit: async () => marimastat, verifyProvenanceAudit: async () => ({ status: 'verified', valid: true, checks: [], errors: ['Contradiction'] }) });
  await session.run(); assert.equal(await session.verify(), null); assert.ok(session.verificationError); assert.equal(session.verification, null);
  session.api.provenanceAudit = async () => { throw new Error('Service unavailable'); };
  assert.equal(await session.run(), null); assert.equal(session.certificate, null); assert.match(session.error.message, /Service unavailable/);
});

test('exported certificate copies cannot mutate session claims', async () => {
  const session = sessionWith({ provenanceAudit: async () => marimastat }); await session.run();
  const exported = session.exportCertificate(); exported.protection_plan.representative.push('source:fake');
  assert.equal(stableJSON(session.exportCertificate()), stableJSON(marimastat));
});

test('dossier is self-contained, printable, explicit about assumptions and includes the complete certificate', () => {
  const html = provenanceDossier(one, { edition: 'snapshot', exportedAt: '2026-11-01T00:00:00Z' });
  assert.match(html, /Content-Security-Policy/); assert.match(html, /default-src &#39;none&#39;|default-src 'none'/);
  assert.match(html, /@media print/); assert.match(html, /no live solver runs in the browser/);
  assert.match(html, /Reviewing a group does not prove/); assert.match(html, /Different|Worst cases in different rows need not occur together/);
  assert.match(html, new RegExp(one.certificate_sha256)); assert.match(html, /Complete unchanged certificate/);
  assert.ok(!html.includes('<script')); assert.ok(!html.includes('<iframe')); assert.ok(!html.includes('<link'));
});

test('untrusted names, source labels, metadata and interpretation remain inert in dossier HTML', () => {
  const c = copyJSON(one), hostile = '</title><script>alert(1)</script><img src=x onerror=alert(2)>';
  c.compound.name = hostile; c.disease.name = hostile; c.interpretation = hostile;
  c.scope.groups[0].label = hostile; c.results[1].rank_witness.removed_edges_preview[0].source_name = hostile;
  const html = provenanceDossier(c);
  assert.ok(!html.includes('<script')); assert.ok(!html.includes('<img')); assert.ok(!html.includes(hostile));
  assert.match(html, /&lt;script&gt;/);
});

test('recorded verification is described without implying a fresh browser solver', () => {
  const verification = caseData.provenance_verifications[one.compound.id]['10:1'];
  assert.match(provenanceDossier(one, { edition: 'snapshot', verification }), /verification was loaded; it was executed at snapshot export/);
  assert.match(provenanceDossier(one, { edition: 'live', verification }), /application returned a successful certificate verification/);
});

test('the shared-source illustration links an actual recorded candidate and a declared one-group scope', () => {
  const url = new URL(provenanceExampleURL('https://example.org/?exclude=INTERACTS&view=method&audit_k=5&audit_budget=2'));
  assert.equal(url.searchParams.get('disease'), diseaseId); assert.equal(url.searchParams.get('compound'), marimastat.compound.id);
  assert.equal(url.searchParams.get('dependency_budget'), '1'); assert.equal(url.searchParams.has('exclude'), false); assert.equal(url.searchParams.has('view'), false);
  assert.equal(url.searchParams.has('audit_k'), false); assert.equal(url.searchParams.has('audit_budget'), false);
  assert.equal(url.hash, '#dependency-section'); assert.equal(provenanceVerdict(one).kind, 'fragile');
});
