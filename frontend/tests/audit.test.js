import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createHash } from 'node:crypto';
import { AriadneAPI } from '../api.js';
import {
  AuditSession, auditContext, auditKey, auditLinkParameters, auditVerdict, copyJSON,
  defaultWitnessKind, metadataList, rivalExampleURL, stableJSON, validateAudit, witnessChanges, witnessFor
} from '../audit-model.js';

const dataRoot = new URL('../data/', import.meta.url);
const manifest = JSON.parse(fs.readFileSync(new URL('manifest.json', dataRoot), 'utf8'));
const diseaseId = 'Disease::DOID:10652';
const caseBytes = fs.readFileSync(new URL(manifest.cases[diseaseId].file, dataRoot));
const caseData = JSON.parse(caseBytes.toString('utf8'));
const galantamine = caseData.audits['Compound::DB00674']['10:2'];
const nicotine = caseData.audits['Compound::DB00184']['10:2'];
const recordedVerification = caseData.audit_verifications[galantamine.compound.id]['10:2'];

const response = (data, bytes = new TextEncoder().encode(JSON.stringify(data))) => ({
  ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => data,
  arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
});
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function snapshotAPI(data = caseData) {
  const calls = [];
  const bytes = data === caseData ? caseBytes : Buffer.from(JSON.stringify(data));
  const fixtureManifest = copyJSON(manifest);
  const integrity = fixtureManifest.files.find(item => item.path === manifest.cases[diseaseId].file);
  integrity.bytes = bytes.byteLength;
  integrity.sha256 = createHash('sha256').update(bytes).digest('hex');
  const api = new AriadneAPI({}, async (url, options) => {
    calls.push({ url, options });
    if (url === './data/manifest.json') return response(fixtureManifest);
    if (url === `./data/${manifest.cases[diseaseId].file}`) return response(data, bytes);
    throw new Error('Unexpected request: ' + url);
  });
  return { api, calls };
}
function sessionWith(api, certificate = galantamine) {
  const session = new AuditSession(api);
  session.setFocus(certificate.disease, certificate.compound);
  session.setParameters(certificate.top_k, certificate.budget);
  return session;
}

test('live audit requests declare only their own full-graph scope and replay the unchanged envelope', async () => {
  const calls = [];
  const api = new AriadneAPI({}, async (url, options) => { calls.push({ url, options }); return response(galantamine); });
  api.mode = 'live';
  await api.audit(diseaseId, galantamine.compound.id, 10, 2);
  assert.equal(calls[0].url, '/api/audit');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    disease_id: diseaseId, compound_id: galantamine.compound.id, top_k: 10, budget: 2
  });
  assert.equal(calls[0].options.method, 'POST');
  await api.verifyAudit(galantamine);
  assert.equal(calls[1].url, '/api/audit/verify');
  assert.deepEqual(JSON.parse(calls[1].options.body), { certificate: galantamine });
});

test('invalid audit limits fail before any network request', async () => {
  let calls = 0;
  const api = new AriadneAPI({}, async () => { calls += 1; });
  api.mode = 'live';
  for (const [topK, budget] of [[0, 2], [101, 2], [10, -1], [10, 3], [1.5, 1], [10, 1.5]]) {
    await assert.rejects(api.audit(diseaseId, galantamine.compound.id, topK, budget), /shortlist size/);
  }
  assert.equal(calls, 0);
  assert.equal(auditKey(100, 0), '100:0');
});

test('recorded audits retain real bounds, use one lazy case fetch, and cannot mutate the published copy', async () => {
  const { api, calls } = snapshotAPI();
  await api.initialize(true);
  const [first, second] = await Promise.all([
    api.audit(diseaseId, galantamine.compound.id, 10, 2), api.audit(diseaseId, nicotine.compound.id, 10, 2)
  ]);
  assert.deepEqual(first.results.map(row => row.worst_supported_rank), [1, 3, 26]);
  assert.deepEqual(second.results.map(row => row.worst_supported_rank), [2, 6, 32]);
  first.results[2].worst_supported_rank = 999;
  const original = await api.audit(diseaseId, galantamine.compound.id, 10, 2);
  assert.equal(original.results[2].worst_supported_rank, 26);
  assert.equal(calls.filter(call => call.url.endsWith(manifest.cases[diseaseId].file)).length, 1);
});

test('snapshot parameters without an executed certificate are unavailable, never interpolated', async () => {
  const { api } = snapshotAPI();
  await api.initialize(true);
  await assert.rejects(api.audit(diseaseId, galantamine.compound.id, 7, 2), /not included/);
  await assert.rejects(api.audit(diseaseId, 'Compound::DB00001', 10, 2), /not included/);
});

test('snapshot verification labels recorded execution and rejects a changed envelope even with its original hash', async () => {
  const { api } = snapshotAPI();
  await api.initialize(true);
  const certificate = await api.audit(diseaseId, galantamine.compound.id, 10, 2);
  const good = await api.verifyAudit(certificate);
  assert.equal(good.valid, true);
  assert.equal(good.verification_execution, 'recorded_snapshot');
  assert.deepEqual(good.checks, recordedVerification.checks);
  certificate.results[2].rank_witness.removed_records[0].source_name = 'Altered provenance';
  const bad = await api.verifyAudit(certificate);
  assert.equal(bad.valid, false);
  assert.equal(bad.status, 'invalid');
  assert.match(bad.errors.join(' '), /does not exactly match/);
});

test('a missing recorded verification does not masquerade as fresh server replay', async () => {
  const modifiedCase = copyJSON(caseData);
  delete modifiedCase.audit_verifications;
  const { api } = snapshotAPI(modifiedCase);
  await api.initialize(true);
  await assert.rejects(api.verifyAudit(galantamine), /No recorded verification/);
});

test('every published audit has complete scope, valid bounds, exact witness identities, and recorded verification', () => {
  let count = 0;
  for (const descriptor of Object.values(manifest.cases)) {
    const data = JSON.parse(fs.readFileSync(new URL(descriptor.file, dataRoot), 'utf8'));
    for (const [compoundId, variants] of Object.entries(data.audits)) {
      assert.equal(Object.keys(variants).length, 9);
      for (const [key, certificate] of Object.entries(variants)) {
        validateAudit(certificate, data.disease.id, compoundId, certificate.top_k, certificate.budget);
        assert.equal(key, auditKey(certificate.top_k, certificate.budget));
        const verified = data.audit_verifications[compoundId][key];
        assert.equal(verified.status, 'verified');
        assert.equal(verified.valid, true);
        assert.deepEqual(verified.errors, []);
        count += 1;
      }
    }
  }
  assert.equal(count, Object.values(manifest.cases).reduce((total, descriptor) => total + descriptor.coverage.audit_count, 0));
});

test('verdict distinguishes bounded robustness, fragility, and a baseline already outside the shortlist', () => {
  assert.equal(auditVerdict(galantamine).kind, 'fragile');
  const one = caseData.audits[galantamine.compound.id]['10:1'];
  assert.equal(auditVerdict(one).kind, 'robust');
  assert.match(auditVerdict(one).title, /up to 1 withdrawal/);
  const outside = caseData.audits[nicotine.compound.id]['1:2'];
  assert.equal(auditVerdict(outside).kind, 'outside');
  assert.equal(outside.minimum_failure_budget, 0);
});

test('unsupported witnesses keep a null rank, separate from the worst supported-rank bound', () => {
  const certificate = caseData.audits['Compound::DB00465']['10:2'];
  const row = certificate.results.at(-1);
  assert.equal(row.unsupported_attainable, true);
  assert.equal(typeof row.worst_supported_rank, 'number');
  const witness = witnessFor(certificate, 2, 'unsupported');
  assert.equal(witness.focus.supported, false);
  assert.equal(witness.focus.rank, null);
  assert.equal(witness.focus.evidence_count, 0);
  assert.equal(defaultWitnessKind({ ...row, worst_supported_rank: null }, 10), 'unsupported');
});

test('certificates cannot cross disease, compound, parameter, or global-scope boundaries', () => {
  for (const args of [
    ['Disease::other', galantamine.compound.id, 10, 2],
    [diseaseId, nicotine.compound.id, 10, 2],
    [diseaseId, galantamine.compound.id, 5, 2],
    [diseaseId, galantamine.compound.id, 10, 1]
  ]) assert.throws(() => validateAudit(galantamine, ...args), /does not match/);
  const partial = copyJSON(galantamine);
  partial.scope.includes_competitor_changes = false;
  assert.throws(() => validateAudit(partial, diseaseId, partial.compound.id, 10, 2), /full-graph/);
});

test('invalid verdicts, disappearing outcomes, and duplicate witness records are rejected', () => {
  const wrongVerdict = copyJSON(galantamine);
  wrongVerdict.results[2].top_k_robust = true;
  assert.throws(() => validateAudit(wrongVerdict, diseaseId, wrongVerdict.compound.id, 10, 2), /verdict/);
  const narrowing = copyJSON(galantamine);
  narrowing.results[2].worst_supported_rank = 1;
  assert.throws(() => validateAudit(narrowing, diseaseId, narrowing.compound.id, 10, 2), /narrower/);
  const duplicate = copyJSON(galantamine);
  duplicate.results[2].rank_witness.removed_records[1] = duplicate.results[2].rank_witness.removed_records[0];
  assert.throws(() => validateAudit(duplicate, diseaseId, duplicate.compound.id, 10, 2), /identifiers/);
});

test('an audit arriving after a different compound is selected cannot commit or be exported', async () => {
  const waiting = deferred();
  const session = sessionWith({ audit: () => waiting.promise });
  const pending = session.run();
  session.setFocus(nicotine.disease, nicotine.compound);
  waiting.resolve(galantamine);
  await pending;
  assert.equal(session.certificate, null);
  assert.equal(session.exportCertificate(), null);
  assert.equal(session.busy, false);
});

test('changing the audit budget invalidates in-flight results without changing the explorer scope', async () => {
  const waiting = deferred();
  const session = sessionWith({ audit: () => waiting.promise });
  const pending = session.run();
  session.setParameters(10, 1);
  waiting.resolve(galantamine);
  await pending;
  assert.equal(session.certificate, null);
  assert.equal(session.context, auditContext(diseaseId, galantamine.compound.id, 10, 1));
});

test('leaving and returning to the same audit does not revive an old result', async () => {
  const waiting = deferred();
  const session = sessionWith({ audit: () => waiting.promise });
  const pending = session.run();
  session.setFocus(nicotine.disease, nicotine.compound);
  session.setFocus(galantamine.disease, galantamine.compound);
  waiting.resolve(galantamine);
  await pending;
  assert.equal(session.certificate, null);
});

test('a newer audit wins even when an older request later fails', async () => {
  const old = deferred(), fresh = deferred();
  let calls = 0;
  const session = sessionWith({ audit: () => (++calls === 1 ? old.promise : fresh.promise) });
  const oldRequest = session.run(), newRequest = session.run();
  fresh.resolve(galantamine);
  await newRequest;
  old.reject(new Error('Old request failed'));
  await oldRequest;
  assert.equal(session.certificate.certificate_sha256, galantamine.certificate_sha256);
  assert.equal(session.error, null);
  assert.equal(session.busy, false);
});

test('a late replay cannot validate a new context or a new audit run', async () => {
  const waiting = deferred();
  const session = sessionWith({ audit: async () => galantamine, verifyAudit: () => waiting.promise });
  await session.run();
  const replay = session.verify();
  await session.run();
  waiting.resolve(recordedVerification);
  await replay;
  assert.equal(session.verification, null);
  assert.equal(session.verifying, false);
});

test('inconsistent verifier success is rejected and cannot be displayed as a verified result', async () => {
  const session = sessionWith({ audit: async () => galantamine, verifyAudit: async () => ({
    status: 'verified', valid: true, checks: ['one check'], errors: ['witness differs']
  }) });
  await session.run();
  await session.verify();
  assert.equal(session.verification, null);
  assert.match(session.verificationError.message, /inconsistent/);
});

test('certificate export preserves the unchanged envelope and is detached from view state', async () => {
  const session = sessionWith({ audit: async () => galantamine });
  await session.run();
  const exported = session.exportCertificate();
  assert.deepEqual(exported, galantamine);
  exported.results[2].worst_supported_rank = 999;
  assert.equal(session.exportCertificate().results[2].worst_supported_rank, 26);
  session.setParameters(5, 2);
  assert.equal(session.exportCertificate(), null);
});

test('recorded-envelope equality tolerates key ordering but never altered metadata or array order', () => {
  const reordered = Object.fromEntries(Object.entries(galantamine).reverse());
  assert.equal(stableJSON(reordered), stableJSON(galantamine));
  const altered = copyJSON(galantamine);
  altered.results.reverse();
  assert.notEqual(stableJSON(altered), stableJSON(galantamine));
});

test('a rival-only witness always compares the selected compound without inventing a withdrawal on it', () => {
  const rival = { id: nicotine.compound.id, name: nicotine.compound.name, role: 'competitor',
    before: { rank: 2, score: .92 }, after: { rank: 1, score: .95 }, removed_edge_ids: ['rival-record'] };
  const witness = { focus: { supported: true, rank: 2, score: galantamine.baseline.score }, changed_compounds: [rival] };
  const rows = witnessChanges(galantamine, witness);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].id, galantamine.compound.id);
  assert.equal(rows[0].role, 'focus');
  assert.equal(rows[0].before.rank, 1);
  assert.equal(rows[0].after.rank, 2);
  assert.deepEqual(rows[0].removed_edge_ids, []);
  assert.equal(rows[1], rival);
  assert.equal(witness.changed_compounds.length, 1);
  assert.equal(witnessChanges(galantamine, { ...witness, changed_compounds: rows }).length, 2);
});

test('imported single-value references, URLs and actions can be inspected without array assumptions', () => {
  assert.deepEqual(metadataList('10971048'), ['10971048']);
  assert.deepEqual(metadataList('https://example.org/source'), ['https://example.org/source']);
  assert.deepEqual(metadataList('inhibitor'), ['inhibitor']);
  assert.deepEqual(metadataList(['one', 'two']), ['one', 'two']);
  assert.deepEqual(metadataList(null), []);
  assert.deepEqual(metadataList(undefined), []);
});

test('audit links accept only supported integer controls and preserve normal defaults', () => {
  assert.deepEqual(auditLinkParameters(new URLSearchParams()), { topK: 10, budget: 2, requested: false });
  assert.deepEqual(auditLinkParameters(new URLSearchParams('audit_k=5&audit_budget=0')), { topK: 5, budget: 0, requested: true });
  assert.deepEqual(auditLinkParameters(new URLSearchParams('audit_budget=1')), { topK: 10, budget: 1, requested: true });
  for (const query of ['audit_k=100', 'audit_k=0', 'audit_k=1.5', 'audit_k=1e1', 'audit_k=', 'audit_budget=3', 'audit_budget=-1', 'audit_budget=1.0', 'audit_budget=']) {
    assert.equal(auditLinkParameters(new URLSearchParams(query)).requested, false, query);
  }
});

test('the rival example link preserves the current edition and selects a full-graph one-record audit', () => {
  const url = new URL(rivalExampleURL('https://example.test/app/?mode=snapshot&exclude=INTERACTS&view=method&disease=old&compound=old'));
  assert.equal(url.origin, 'https://example.test');
  assert.equal(url.pathname, '/app/');
  assert.equal(url.searchParams.get('mode'), 'snapshot');
  assert.equal(url.searchParams.get('disease'), 'Disease::DOID:175');
  assert.equal(url.searchParams.get('compound'), 'Compound::DB01115');
  assert.equal(url.searchParams.has('exclude'), false);
  assert.equal(url.searchParams.has('view'), false);
  assert.equal(url.hash, '#audit-section');
  assert.deepEqual(auditLinkParameters(url.searchParams), { topK: 10, budget: 1, requested: true });
});
