import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { AriadneAPI } from '../api.js';
import { sha256Fallback, sha256Hex, snapshotFileRecord, validateSnapshotCase } from '../integrity.js';

const encode = value => new TextEncoder().encode(value);
const clone = value => JSON.parse(JSON.stringify(value));
const hash = value => createHash('sha256').update(value).digest('hex');
const disease = { id: 'Disease::D1', name: 'A disease' };
const compound = { id: 'Compound::C1', name: 'A compound' };
const identity = { dataset_sha256: 'a'.repeat(64), graph_sha256: 'b'.repeat(64), model_sha256: 'c'.repeat(64) };
const caseData = {
  disease, description: 'UTF-8 matters: α → β 🧬',
  rankings: { '': { disease, candidates: [compound] } },
  audits: { [compound.id]: { '10:2': { disease, compound, top_k: 10, budget: 2, identity } } }
};
const file = 'cases/example.json';
const raw = encode(JSON.stringify(caseData));
const makeManifest = bytes => ({
  cases: { [disease.id]: { file } }, diseases: [disease], ...identity,
  stats: { graph_sha256: identity.graph_sha256, dataset_sha256: identity.dataset_sha256 },
  files: [{ path: file, bytes: bytes.byteLength, sha256: hash(bytes) }]
});
function response(bytes, permitJSON = true) {
  return {
    ok: true, status: 200, headers: { get: () => 'application/json' },
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength),
    json: async () => { assert.ok(permitJSON, 'case JSON must not be parsed before byte verification'); return JSON.parse(new TextDecoder().decode(bytes)); }
  };
}
async function snapshot({ manifest = makeManifest(raw), body = raw } = {}) {
  const calls = [];
  const api = new AriadneAPI({}, async url => {
    calls.push(url);
    if (url.endsWith('manifest.json')) return response(encode(JSON.stringify(manifest)));
    return response(typeof body === 'function' ? await body() : body, false);
  });
  await api.initialize(true);
  return { api, calls };
}

test('local SHA-256 matches published known answers including padding and one million bytes', () => {
  for (const [message, expected] of [
    ['', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
    ['abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
    ['abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq', '248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1'],
    ['a'.repeat(1000000), 'cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0']
  ]) assert.equal(sha256Fallback(encode(message)), expected);
});

test('local SHA-256 agrees with native crypto at block boundaries and respects byte-view offsets', () => {
  for (const length of [1, 55, 56, 63, 64, 65, 119, 120, 127, 128, 129, 4096]) {
    const storage = Uint8Array.from({ length: length + 12 }, (_, i) => (i * 179 + 83) % 256);
    const bytes = storage.subarray(7, 7 + length);
    assert.equal(sha256Fallback(bytes), hash(bytes), `length ${length}`);
  }
  assert.equal(sha256Fallback(raw), hash(raw));
});

test('WebCrypto, absent WebCrypto, and unavailable digest all perform a real byte hash', async () => {
  const expected = hash(raw);
  assert.equal(await sha256Hex(raw, webcrypto), expected);
  assert.equal(await sha256Hex(raw, null), expected);
  assert.equal(await sha256Hex(raw, {}), expected);
  assert.equal(await sha256Hex(raw, { subtle: { digest: async () => { throw new Error('Unavailable in this context'); } } }), expected);
  assert.equal(await sha256Hex(raw, { subtle: { digest: async () => new ArrayBuffer(0) } }), expected);
});

test('every actual published case also matches its checksum through the HTTP-preview fallback', async () => {
  const base = new URL('../data/', import.meta.url);
  const manifest = JSON.parse(await readFile(new URL('manifest.json', base), 'utf8'));
  for (const record of manifest.files) {
    const bytes = await readFile(new URL(record.path, base));
    assert.equal(bytes.byteLength, record.bytes, record.path);
    assert.equal(await sha256Hex(bytes, null), record.sha256, record.path);
  }
});

test('valid UTF-8 cases are verified as raw bytes before parsing and caching', async () => {
  assert.ok(raw.byteLength > JSON.stringify(caseData).length);
  const { api, calls } = await snapshot();
  const [one, two] = await Promise.all([api.loadCase(disease.id), api.loadCase(disease.id)]);
  assert.equal(one, two);
  assert.equal(one.description, caseData.description);
  assert.equal(api.cases.get(disease.id), one);
  assert.equal(api.pendingCases.size, 0);
  assert.equal(calls.filter(url => url.endsWith(file)).length, 1);
});

test('a byte-length mismatch is rejected without populating the cache', async () => {
  const { api } = await snapshot({ body: encode(JSON.stringify(caseData) + '\n') });
  await assert.rejects(api.loadCase(disease.id), /integrity check failed: byte count mismatch/);
  assert.equal(api.cases.size, 0);
  assert.equal(api.pendingCases.size, 0);
});

test('a same-length tamper fails SHA-256 before even invalid JSON can be parsed', async () => {
  const bytes = raw.slice();
  bytes[0] = '!'.charCodeAt(0);
  const { api } = await snapshot({ body: bytes });
  await assert.rejects(api.loadCase(disease.id), /integrity check failed: SHA-256 mismatch/);
  assert.equal(api.cases.size, 0);
});

test('missing, duplicate or malformed checksum metadata fails before requesting case bytes', async () => {
  const variants = [
    manifest => { delete manifest.files; },
    manifest => { manifest.files = []; },
    manifest => { manifest.files.push(clone(manifest.files[0])); },
    manifest => { delete manifest.files[0].sha256; },
    manifest => { manifest.files[0].sha256 = 'unchecked'; },
    manifest => { delete manifest.files[0].bytes; },
    manifest => { manifest.files[0].bytes = -1; },
    manifest => { manifest.files[0].bytes = '123'; }
  ];
  for (const change of variants) {
    const manifest = makeManifest(raw);
    change(manifest);
    const { api, calls } = await snapshot({ manifest });
    await assert.rejects(api.loadCase(disease.id), /integrity check failed/);
    assert.equal(calls.length, 1);
    assert.equal(api.cases.size, 0);
  }
});

test('inline case data cannot bypass the raw-byte integrity requirement', async () => {
  const manifest = makeManifest(raw);
  manifest.cases[disease.id] = caseData;
  const { api, calls } = await snapshot({ manifest });
  await assert.rejects(api.loadCase(disease.id), /Inline research cases cannot be byte-verified/);
  assert.equal(calls.length, 1);
});

test('hash-valid cases still reject missing or mismatched audit dataset, graph and model identities', async () => {
  for (const key of Object.keys(identity)) {
    for (const missing of [false, true]) {
      const data = clone(caseData);
      if (missing) delete data.audits[compound.id]['10:2'].identity[key];
      else data.audits[compound.id]['10:2'].identity[key] = 'd'.repeat(64);
      const bytes = encode(JSON.stringify(data));
      const { api } = await snapshot({ body: bytes, manifest: makeManifest(bytes) });
      await assert.rejects(api.loadCase(disease.id), new RegExp(`audit ${key} does not match`));
      assert.equal(api.cases.size, 0);
    }
  }
});

test('every audit variant is identity-checked, including unselected compounds', async () => {
  const data = clone(caseData);
  data.audits['Compound::hidden'] = { '10:2': {
    disease, compound: { id: 'Compound::hidden' }, top_k: 10, budget: 2,
    identity: { ...identity, model_sha256: 'f'.repeat(64) }
  } };
  assert.throws(() => validateSnapshotCase(data, makeManifest(raw), disease.id), /audit model_sha256 does not match/);
});

test('manifest identities must exist and agree across top-level, stats and provenance', () => {
  for (const key of Object.keys(identity)) {
    const manifest = makeManifest(raw);
    delete manifest[key];
    delete manifest.stats[key];
    assert.throws(() => validateSnapshotCase(caseData, manifest, disease.id), /missing a valid/);
  }
  const conflict = makeManifest(raw);
  conflict.stats.graph_sha256 = 'f'.repeat(64);
  assert.throws(() => validateSnapshotCase(caseData, conflict, disease.id), /conflicting graph_sha256/);
  const provenance = makeManifest(raw);
  provenance.provenance = { dataset_sha256: 'f'.repeat(64) };
  assert.throws(() => validateSnapshotCase(caseData, provenance, disease.id), /conflicting dataset_sha256/);
});

test('case and nested audit identities cannot be relocated under another manifest key', () => {
  const manifest = makeManifest(raw);
  assert.throws(() => validateSnapshotCase(caseData, manifest, 'Disease::wrong'), /case disease/);
  for (const change of [
    data => { data.audits[compound.id]['10:2'].disease.id = 'Disease::wrong'; },
    data => { data.audits[compound.id]['10:2'].compound.id = 'Compound::wrong'; },
    data => { data.audits[compound.id]['10:2'].budget = 1; }
  ]) {
    const data = clone(caseData); change(data);
    assert.throws(() => validateSnapshotCase(data, manifest, disease.id), /audit does not match its case/);
  }
});

test('a failed case load is retryable and cannot leave a rejected pending request cached', async () => {
  let attempt = 0;
  const wrong = raw.slice(); wrong[0] ^= 1;
  const { api } = await snapshot({ body: () => ++attempt === 1 ? wrong : raw });
  await assert.rejects(api.loadCase(disease.id), /SHA-256 mismatch/);
  const data = await api.loadCase(disease.id);
  assert.equal(data.disease.id, disease.id);
  assert.equal(attempt, 2);
});

test('reinitialization cannot let a pending old publication replace a new cached case', async () => {
  let resolveOld;
  const oldBody = new Promise(resolve => { resolveOld = resolve; });
  let attempt = 0;
  const { api } = await snapshot({ body: () => ++attempt === 1 ? oldBody : raw });
  const oldRequest = api.loadCase(disease.id);
  await api.initialize(true);
  const newCase = await api.loadCase(disease.id);
  resolveOld(raw);
  await assert.rejects(oldRequest, /snapshot changed while this case was loading/);
  assert.equal(api.cases.get(disease.id), newCase);
  assert.equal(api.pendingCases.size, 0);
});

test('a matching checksum never makes malformed JSON acceptable', async () => {
  const bytes = encode('{');
  const { api } = await snapshot({ body: bytes, manifest: makeManifest(bytes) });
  await assert.rejects(api.loadCase(disease.id), /unreadable JSON or invalid UTF-8/);
  assert.equal(api.cases.size, 0);
});

test('checksum records are detached so later metadata mutation cannot change an in-flight expectation', () => {
  const manifest = makeManifest(raw);
  const record = snapshotFileRecord(manifest, file);
  manifest.files[0].sha256 = '0'.repeat(64);
  assert.equal(record.sha256, hash(raw));
});
