import test from 'node:test';
import assert from 'node:assert/strict';
import { access, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { AriadneAPI } from '../api.js';
import { loadCandidateInvestigation } from '../investigation.js';
import { auditLinkParameters, rivalExampleURL, witnessChanges } from '../audit-model.js';

const root = fileURLToPath(new URL('..', import.meta.url));
let available = true;
try { await access(resolve(root, 'data/manifest.json')); }
catch { available = false; }

async function snapshotFetcher(url) {
  const bytes = await readFile(resolve(root, url.replace(/^\.\//, '')));
  return {
    ok: true, status: 200, headers: { get: () => 'application/json' },
    json: async () => JSON.parse(bytes.toString('utf8')),
    arrayBuffer: async () => bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength)
  };
}

test('published cases are consumable through the actual frontend adapter in every evidence configuration', { skip: !available }, async () => {
  const api = new AriadneAPI({}, snapshotFetcher);
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

async function snapshotAPI() {
  const api = new AriadneAPI({}, snapshotFetcher);
  await api.initialize(true);
  return api;
}

test('a shared off-list compound and an evidence restore retain the exact selected identity', { skip: !available }, async () => {
  const api = await snapshotAPI();
  const diseaseId = 'Disease::DOID:10652';
  const link = new URL('https://example.test/?disease=Disease%3A%3ADOID%3A10652&compound=Compound%3A%3ADB00514&exclude=INTERACTS');
  const excludedRanking = await api.rankings(diseaseId, ['INTERACTS']);
  const shared = await loadCandidateInvestigation(api, link.searchParams.get('disease'), link.searchParams.get('compound'), link.searchParams.get('exclude').split(','), excludedRanking.candidates);
  assert.equal(shared.candidate.name, 'Dextromethorphan');
  assert.equal(shared.candidate.rank, 13);
  assert.equal(shared.candidate.pinned, true);
  const selected = await loadCandidateInvestigation(api, diseaseId, 'Compound::DB00677', ['INTERACTS'], excludedRanking.candidates);
  assert.equal(selected.candidate.rank, 2);
  const baselineRanking = await api.rankings(diseaseId);
  const restored = await loadCandidateInvestigation(api, diseaseId, selected.candidate.id, [], baselineRanking.candidates);
  assert.equal(restored.candidate.id, selected.candidate.id);
  assert.equal(restored.candidate.name, 'Isoflurophate');
  assert.equal(restored.candidate.rank, 31);
  assert.equal(restored.candidate.pinned, true);
  const unsupported = await loadCandidateInvestigation(api, diseaseId, selected.candidate.id, ['BINDS'], []);
  assert.equal(unsupported.candidate.id, selected.candidate.id);
  assert.equal(unsupported.candidate.rank, null);
  assert.equal(unsupported.assessment.current.supported, false);
  assert.equal(unsupported.evidence.total_paths, 0);
  assert.ok(Number.isFinite(unsupported.assessment.current.score));
});

test('snapshot assessments retain exact additive terms for every published candidate and scenario', { skip: !available }, async () => {
  const api = await snapshotAPI();
  assert.equal(api.manifest.compounds.length, 1552);
  for (const disease of api.manifest.diseases) {
    const record = await api.loadCase(disease.id);
    for (const [compoundId, scenarios] of Object.entries(record.assessments)) {
      assert.equal(Object.keys(scenarios).length, 16);
      for (const key of Object.keys(scenarios)) {
        const assessment = await api.assessment(disease.id, compoundId, key.split(',').filter(Boolean));
        const { baseline, current, decomposition } = assessment;
        const terms = decomposition.features;
        assert.equal(terms.length, 8);
        assert.ok(Math.abs(decomposition.intercept + terms.reduce((sum, item) => sum + item.contribution_after, 0) - current.logit) < 1e-10);
        assert.ok(Math.abs(terms.reduce((sum, item) => sum + item.contribution_delta, 0) - assessment.delta.logit) < 1e-10);
        assert.ok(Math.abs(current.score - 1 / (1 + Math.exp(-current.logit))) < 1e-10);
        assert.equal(assessment.model.dataset_sha256, api.manifest.dataset_sha256);
        assert.equal(assessment.model.model_sha256, api.manifest.model_sha256);
        if (!current.supported) assert.equal(current.rank, null);
        assert.equal(baseline.supported, true);
      }
    }
  }
});

test('snapshot guide resolves explicit compounds, selected context, and top-candidate intent distinctly', { skip: !available }, async () => {
  const api = await snapshotAPI();
  const diseaseId = 'Disease::DOID:10652';
  const nicotine = 'Compound::DB00184', galantamine = 'Compound::DB00674';
  const selected = await api.agent('Explain the selected compound', diseaseId, [], nicotine);
  assert.equal(selected.compound.id, nicotine);
  assert.equal(selected.candidates[0].id, galantamine, 'the ranked list remains context, not evidence focus');
  const explicit = await api.agent('Nicotine', diseaseId, [], galantamine);
  assert.equal(explicit.compound.id, nicotine);
  const top = await api.agent('Explain the highest-ranked compound', diseaseId, [], nicotine);
  assert.equal(top.compound.id, galantamine);
  for (const question of ['Explain the highest scoring compound', 'Explain the highest-scoring compound']) {
    const scored = await api.agent(question, diseaseId, [], nicotine);
    assert.equal(scored.compound.id, galantamine);
  }
  const explicitIds = await api.agent('Explain compound::db00184 for disease::doid:10652', diseaseId, [], galantamine);
  assert.equal(explicitIds.compound.id, nicotine);
  const changedDisease = await api.agent('Investigate asthma', diseaseId, [], nicotine);
  assert.equal(changedDisease.disease.id, 'Disease::DOID:2841');
  assert.equal(changedDisease.compound.name, 'Captopril');
  const ambiguous = await api.agent('Compare Nicotine and Galantamine', diseaseId, [], nicotine);
  assert.equal(ambiguous.status, 'clarification');
  const unsupported = await api.agent('Explain the selected compound', diseaseId, ['BINDS'], nicotine);
  assert.equal(unsupported.compound.id, nicotine);
  assert.equal(unsupported.assessment.current.rank, null);
  assert.equal(unsupported.evidence.total_paths, 0);
  assert.match(unsupported.answer, /diagnostic score/);
  const record = await api.loadCase(diseaseId);
  const unpublished = api.manifest.compounds.find(item => !record.assessments[item.id]);
  const missing = await api.agent(`Explain ${unpublished.name}`, diseaseId, [], nicotine);
  assert.equal(missing.status, 'clarification');
  assert.match(missing.answer, /not included in the published results/);
});

test('the published rival-change example preserves the focus score while a rival changes shortlist membership', { skip: !available }, async () => {
  const api = await snapshotAPI();
  const link = new URL(rivalExampleURL('https://example.test/?mode=snapshot&exclude=INTERACTS&view=method'));
  const diseaseId = link.searchParams.get('disease'), compoundId = link.searchParams.get('compound');
  const parameters = auditLinkParameters(link.searchParams);
  const ranking = await api.rankings(diseaseId);
  const investigation = await loadCandidateInvestigation(api, diseaseId, compoundId, [], ranking.candidates);
  assert.equal(investigation.candidate.name, 'Nifedipine');
  const certificate = await api.audit(diseaseId, compoundId, parameters.topK, parameters.budget);
  const row = certificate.results.at(-1);
  assert.equal(certificate.baseline.rank, 10);
  assert.equal(row.focus_only_worst_rank, 10);
  assert.equal(row.worst_supported_rank, 11);
  assert.equal(row.top_k_robust, false);
  assert.equal(certificate.minimum_failure_budget, 1);
  assert.equal(row.rank_witness.focus.score, certificate.baseline.score);
  assert.deepEqual(row.rank_witness.focus.counts, certificate.baseline.counts);
  assert.ok(row.rank_witness.removed_records.every(record => record.source !== compoundId));
  const comparison = witnessChanges(certificate, row.rank_witness);
  assert.equal(comparison[0].id, compoundId);
  assert.equal(comparison[0].after.rank, 11);
  assert.deepEqual(comparison[0].removed_edge_ids, []);
  assert.equal(comparison[1].name, 'Pimozide');
  assert.equal(comparison[1].before.rank, 11);
  assert.equal(comparison[1].after.rank, 9);
  const verification = await api.verifyAudit(JSON.parse(JSON.stringify(certificate)));
  assert.equal(verification.valid, true);
  assert.equal(verification.verification_execution, 'recorded_snapshot');
});
