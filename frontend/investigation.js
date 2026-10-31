import { exclusionKey } from './utils.js';

/** An investigation identity includes the selected compound, even outside the shortlist. */
export function investigationKey(diseaseId, excluded = [], compoundId = null) {
  return JSON.stringify([diseaseId || null, exclusionKey(excluded), compoundId || null]);
}

/** Only the newest request in the same investigation may commit its result. */
export class RequestGate {
  constructor() { this.revision = 0; }
  begin(context) { return Object.freeze({ revision: ++this.revision, context }); }
  invalidate() { this.revision += 1; }
  current(ticket, context) { return ticket.revision === this.revision && ticket.context === context; }
}

export function candidateFromAssessment(assessment, candidates = []) {
  const current = assessment.current;
  const baseline = assessment.baseline;
  return {
    ...assessment.compound,
    rank: current.supported ? current.rank : null,
    score: current.score,
    score_status: current.score_status,
    supported: current.supported,
    baseline_rank: baseline.supported ? baseline.rank : null,
    rank_delta: assessment.delta.rank,
    known_treatment: assessment.known_treatment,
    evidence_count: current.evidence_count,
    features: { ...current.features },
    pinned: !candidates.some(item => item.id === assessment.compound.id)
  };
}

/** Fetch by identity, never infer a selected candidate's rank from a truncated list. */
export async function loadCandidateInvestigation(api, diseaseId, compoundId, excluded = [], candidates = []) {
  const [assessment, evidence] = await Promise.all([
    api.assessment(diseaseId, compoundId, excluded),
    api.evidence(diseaseId, compoundId, excluded, 12)
  ]);
  for (const response of [assessment, evidence]) {
    if (response.disease?.id !== diseaseId || response.compound?.id !== compoundId
      || exclusionKey(response.excluded || []) !== exclusionKey(excluded)) {
      throw new Error('The returned records do not match this investigation. Retry to retrieve a consistent case.');
    }
  }
  if (assessment.current.evidence_count !== evidence.total_paths) {
    throw new Error('The score assessment and evidence counts disagree. Retry to retrieve a consistent case.');
  }
  return { assessment, evidence, candidate: candidateFromAssessment(assessment, candidates) };
}

/** A stale or repeated page must never replace or duplicate the current ranking. */
export function appendRankingPage(ranking, page, expectedOffset) {
  if (!ranking || ranking.candidates.length !== expectedOffset
    || ranking.disease?.id !== page.disease?.id
    || exclusionKey(ranking.excluded || []) !== exclusionKey(page.excluded || [])) return null;
  const seen = new Set(ranking.candidates.map(candidate => candidate.id));
  const additions = page.candidates.filter(candidate => {
    if (seen.has(candidate.id)) return false;
    seen.add(candidate.id);
    return true;
  });
  return { ...ranking, candidates: [...ranking.candidates, ...additions] };
}

export function signedNumber(value, digits = 3) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const rounded = Number(Number(value).toFixed(digits));
  return `${rounded > 0 ? '+' : rounded < 0 ? '−' : ''}${Math.abs(rounded).toFixed(digits)}`;
}

export function rankMovement(baseline, current) {
  if (!baseline.supported && !current.supported) return 'No supported rank';
  if (baseline.supported && !current.supported) return 'Support removed';
  if (!baseline.supported && current.supported) return 'Support restored';
  const delta = baseline.rank - current.rank;
  return delta > 0 ? `↑ ${delta}` : delta < 0 ? `↓ ${Math.abs(delta)}` : 'Unchanged';
}

export function agentMatchesInvestigation(brief, diseaseId, compoundId, excluded = []) {
  if (!brief || brief.request_context !== investigationKey(diseaseId, excluded, compoundId)) return false;
  if (brief.disease?.id && brief.disease.id !== diseaseId) return false;
  if (brief.compound?.id && brief.compound.id !== compoundId) return false;
  if (brief.evidence?.compound?.id && brief.evidence.compound.id !== compoundId) return false;
  const answerExcluded = brief.excluded ?? brief.evidence?.excluded;
  return !answerExcluded || exclusionKey(answerExcluded) === exclusionKey(excluded);
}
