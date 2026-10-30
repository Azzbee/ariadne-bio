import test from 'node:test';
import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { AriadneAPI } from '../api.js';

const root = fileURLToPath(new URL('..', import.meta.url));
let available = true;
try { await access(resolve(root, 'data/manifest.json')); }
catch { available = false; }

test('published cases are consumable through the actual frontend adapter in every evidence configuration', { skip: !available }, async () => {
  const fetcher = async url => {
    const data = JSON.parse(await readFile(resolve(root, url.replace(/^\.\//, '')), 'utf8'));
    return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => data };
  };
  const api = new AriadneAPI({}, fetcher);
  await api.initialize(true);
  const diseases = await api.diseases();
  assert.ok(diseases.items.length >= 1);
  assert.ok(diseases.items.some(item => item.id === api.manifest.default_disease_id));
  for (const disease of diseases.items) {
    const record = await api.loadCase(disease.id);
    assert.equal(Object.keys(record.rankings).length, 16, disease.name);
    for (const key of Object.keys(record.rankings)) {
      const excluded = key.split(',').filter(Boolean);
      const ranking = await api.rankings(disease.id, excluded);
      assert.ok(ranking.candidates.length <= 12);
      for (const candidate of ranking.candidates) {
        const evidence = await api.evidence(disease.id, candidate.id, excluded);
        assert.equal(evidence.compound.id, candidate.id);
        assert.equal(evidence.disease.id, disease.id);
        assert.equal(evidence.total_paths, candidate.evidence_count);
        assert.ok(evidence.total_paths >= evidence.paths.length);
        const ids = new Set(evidence.nodes.map(node => node.id));
        for (const edge of evidence.edges) {
          assert.ok(ids.has(edge.source) && ids.has(edge.target));
          assert.ok(!excluded.includes(edge.type));
          assert.ok(!['TREATS', 'PALLIATES'].includes(edge.type));
        }
      }
    }
  }
  const report = await api.evaluation();
  assert.ok(report.metrics.length >= 2);
  assert.ok(report.dataset_sha256);
});
