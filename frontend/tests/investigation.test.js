import test from 'node:test';
import assert from 'node:assert/strict';
import {
  RequestGate, agentMatchesInvestigation, appendRankingPage, candidateFromAssessment,
  investigationKey, loadCandidateInvestigation, rankMovement, signedNumber
} from '../investigation.js';

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

test('a later guide request wins when answers arrive out of order', async () => {
  const gate = new RequestGate();
  const key = investigationKey('disease', ['INTERACTS'], 'compound');
  const first = deferred(), second = deferred();
  let answer;
  const receive = async pending => {
    const ticket = gate.begin(key);
    const result = await pending.promise;
    if (gate.current(ticket, key)) answer = result;
  };
  const oldRequest = receive(first), newRequest = receive(second);
  second.resolve('current evidence');
  await newRequest;
  first.resolve('old evidence');
  await oldRequest;
  assert.equal(answer, 'current evidence');
});

test('leaving and returning to the same case does not revive an old pagination request', () => {
  const gate = new RequestGate();
  const key = investigationKey('disease', [], 'compound');
  const first = gate.begin(key);
  gate.invalidate();
  gate.begin(investigationKey('another disease'));
  gate.begin(key);
  assert.equal(gate.current(first, key), false);
});

test('candidate, disease, and evidence changes all invalidate a response context', () => {
  const gate = new RequestGate();
  const ticket = gate.begin(investigationKey('disease', ['INTERACTS'], 'compound'));
  assert.equal(gate.current(ticket, investigationKey('disease', ['INTERACTS'], 'other compound')), false);
  assert.equal(gate.current(ticket, investigationKey('other disease', ['INTERACTS'], 'compound')), false);
  assert.equal(gate.current(ticket, investigationKey('disease', [], 'compound')), false);
  assert.equal(gate.current(ticket, investigationKey('disease', ['INTERACTS', 'INTERACTS'], 'compound')), true);
  gate.invalidate();
  assert.equal(gate.current(ticket, ticket.context), false);
});

test('pagination checks its offset and scope and never appends duplicate candidates', () => {
  const ranking = { disease: { id: 'd' }, excluded: ['INTERACTS'], candidates: [{ id: 'a' }, { id: 'b' }] };
  const page = { disease: { id: 'd' }, excluded: ['INTERACTS'], candidates: [{ id: 'b' }, { id: 'c' }, { id: 'c' }] };
  const combined = appendRankingPage(ranking, page, 2);
  assert.deepEqual(combined.candidates.map(item => item.id), ['a', 'b', 'c']);
  assert.equal(ranking.candidates.length, 2, 'the original ranking is not mutated');
  assert.equal(appendRankingPage(combined, page, 2), null);
  assert.equal(appendRankingPage(ranking, { ...page, disease: { id: 'other' } }, 2), null);
  assert.equal(appendRankingPage(ranking, { ...page, excluded: [] }, 2), null);
});

test('an unsupported compound remains selected without receiving a fabricated rank', () => {
  const assessment = {
    compound: { id: 'c', name: 'Compound' }, known_treatment: false,
    baseline: { supported: true, rank: 31 },
    current: { supported: false, rank: null, score: .13, score_status: 'unsupported_diagnostic', evidence_count: 0, features: { direct: 0, interaction: 0, pathway: 0 } },
    delta: { rank: null }
  };
  const candidate = candidateFromAssessment(assessment, []);
  assert.equal(candidate.id, 'c');
  assert.equal(candidate.rank, null);
  assert.equal(candidate.score, .13);
  assert.equal(candidate.supported, false);
  assert.equal(candidate.pinned, true);
  assert.equal(rankMovement(assessment.baseline, assessment.current), 'Support removed');
});

test('a mismatched assessment or evidence count cannot form an exportable investigation', async () => {
  const assessment = { disease: { id: 'd' }, compound: { id: 'c' }, excluded: [], current: { evidence_count: 5 } };
  const api = {
    assessment: async () => assessment,
    evidence: async () => ({ disease: { id: 'd' }, compound: { id: 'other' }, excluded: [], total_paths: 5 })
  };
  await assert.rejects(loadCandidateInvestigation(api, 'd', 'c'), /do not match/);
  api.evidence = async () => ({ disease: { id: 'd' }, compound: { id: 'c' }, excluded: [], total_paths: 6 });
  await assert.rejects(loadCandidateInvestigation(api, 'd', 'c'), /counts disagree/);
});

test('case export rejects briefs about another compound, disease, or evidence configuration', () => {
  const brief = {
    request_context: investigationKey('d', [], 'c'),
    disease: { id: 'd' }, compound: { id: 'c' }, excluded: []
  };
  assert.equal(agentMatchesInvestigation(brief, 'd', 'c'), true);
  assert.equal(agentMatchesInvestigation({ ...brief, disease: { id: 'other' } }, 'd', 'c'), false);
  assert.equal(agentMatchesInvestigation({ ...brief, compound: { id: 'other' } }, 'd', 'c'), false);
  assert.equal(agentMatchesInvestigation({ ...brief, excluded: ['INTERACTS'] }, 'd', 'c'), false);
  assert.equal(agentMatchesInvestigation(brief, 'd', 'c', ['INTERACTS']), false);
  assert.equal(agentMatchesInvestigation(null, 'd', 'c'), false);
});

test('signed model terms preserve their units and do not display negative zero or unknown as zero', () => {
  assert.equal(signedNumber(-2.08168199), '−2.082');
  assert.equal(signedNumber(.37186568), '+0.372');
  assert.equal(signedNumber(-.0000001), '0.000');
  assert.equal(signedNumber(15, 0), '+15');
  assert.equal(signedNumber(null), '—');
  assert.equal(signedNumber(NaN), '—');
  assert.equal(rankMovement({ supported: true, rank: 2 }, { supported: true, rank: 10 }), '↓ 8');
  assert.equal(rankMovement({ supported: false, rank: null }, { supported: false, rank: null }), 'No supported rank');
});
