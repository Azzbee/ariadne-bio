/** Navigation and the published, finite example used on the introduction page. */
export const VIEWS = Object.freeze(['overview', 'investigate', 'benchmark', 'method']);

export function initialView(params, hash = '') {
  const explicit = params.get('view');
  if (VIEWS.includes(explicit)) return explicit;
  if (['disease', 'compound', 'exclude', 'audit_k', 'audit_budget', 'dependency_budget', 'mixed_audit'].some(key => params.has(key))
      || ['#audit-section', '#dependency-section', '#mixed-section', '#assessment-section', '#workbench'].includes(hash)) return 'investigate';
  if (['#audit-method', '#dependency-method-title'].includes(hash)) return 'method';
  return 'overview';
}

export function viewURL(currentURL, view, investigation = {}) {
  if (!VIEWS.includes(view)) throw new Error('Unknown application view');
  const url = new URL(currentURL);
  const params = url.searchParams;
  if (view === 'overview') {
    for (const key of ['view', 'disease', 'compound', 'exclude', 'audit_k', 'audit_budget', 'dependency_budget', 'mixed_audit']) params.delete(key);
    url.hash = '';
  } else {
    params.set('view', view);
    if (investigation.disease) params.set('disease', investigation.disease);
    if (investigation.compound) params.set('compound', investigation.compound);
    else params.delete('compound');
    if (investigation.excluded) params.set('exclude', investigation.excluded);
    else params.delete('exclude');
  }
  return url;
}

// Frozen illustration from v1.3.0. These are recorded audit results, not a live
// computation or a predicted treatment effect. The snapshot test checks the
// values against the full retained certificates whenever the snapshot is present.
export const RECORDED_CASE = Object.freeze({
  disease: 'Disease::DOID:7148', compound: 'Compound::DB00786',
  certificate: '73b4f7cc762e8e362e1d2fc0c753b290bbee3f051eb5a3df9809ca9de58a60e2',
  model: '311897fb3678a7885b8ddb7d63becfe990860bfb3c39cb6195166bad531d14f3',
  source: 'DrugBank (target)',
  baselineRank: 1, individualWorstRank: 1, groupWorstRank: 1096,
  baselinePaths: 1966, groupPaths: 206, removedRecords: 4603, affectedCompounds: 1182
});

export const DEMO_STATES = Object.freeze({
  baseline: Object.freeze({
    rank: RECORDED_CASE.baselineRank, paths: RECORDED_CASE.baselinePaths,
    label: 'All recorded evidence', status: 'Ranked first',
    explanation: 'The fixed model places Marimastat first for rheumatoid arthritis, with 1,966 supporting paths through the prepared graph.',
    detail: 'A research hypothesis, not a claim of clinical efficacy.',
    rankLabel: 'Baseline supported rank', withdrawn: false
  }),
  records: Object.freeze({
    rank: RECORDED_CASE.individualWorstRank, paths: null,
    label: 'Any two individual binding records', status: 'Still ranked first',
    explanation: 'Its worst supported rank remains first when any two individual binding records are withdrawn anywhere in the graph, including rivals’ records.',
    detail: 'An exact bounded guarantee for the frozen model and this deletion rule.',
    rankLabel: 'Worst supported rank', withdrawn: false
  }),
  source: Object.freeze({
    rank: RECORDED_CASE.groupWorstRank, paths: RECORDED_CASE.groupPaths,
    label: 'DrugBank (target) group withdrawn', status: 'Outside the top ten',
    explanation: 'Withdraw every binding record carrying this one source annotation and its supported rank falls to 1,096. All competing compounds are reranked together.',
    detail: '4,603 records removed across 1,182 compounds. A different, larger perturbation than two individual records.',
    rankLabel: 'Supported rank after withdrawal', withdrawn: true
  })
});

export function demoState(key) {
  if (!Object.hasOwn(DEMO_STATES, key)) throw new Error('Unknown recorded example step');
  return DEMO_STATES[key];
}
