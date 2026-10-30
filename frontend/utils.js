/** Small, pure utilities shared by the interface and its tests. */
export const FAMILIES = Object.freeze(['BINDS', 'ASSOCIATES', 'INTERACTS', 'PARTICIPATES']);

export const FAMILY_LABELS = Object.freeze({
  BINDS: 'Compound binding',
  ASSOCIATES: 'Disease association',
  INTERACTS: 'Gene interactions',
  PARTICIPATES: 'Shared pathways'
});

export function exclusionKey(values = []) {
  const input = typeof values === 'string' ? values.split(',') : values;
  return [...new Set(input)].filter(value => FAMILIES.includes(value)).sort().join(',');
}

export function escapeHTML(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));
}

export function safeURL(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

export function compactNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(number);
}

export function number(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return new Intl.NumberFormat('en', { maximumFractionDigits: digits }).format(Number(value));
}

export function score(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return Number(value).toFixed(3);
}

export function pct(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function titleCase(value) {
  return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
}

export function objectText(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(objectText).filter(Boolean).join(' · ');
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${key}: ${objectText(item)}`).join(' · ');
  return String(value);
}

export function metricRows(report = {}) {
  if (Array.isArray(report.metrics)) return report.metrics;
  if (report.metrics && typeof report.metrics === 'object') {
    return Object.entries(report.metrics).map(([model, values]) => ({ model, ...values }));
  }
  return [];
}

export function metricValue(row, metric) {
  const aliases = metric === 'recall_at_10'
    ? ['recall_at_10', 'recall@10', 'recall_10', 'Recall@10', 'recall10']
    : ['mrr', 'MRR', 'mean_reciprocal_rank'];
  for (const key of aliases) {
    if (row[key] !== undefined && row[key] !== null && Number.isFinite(Number(row[key]))) return Number(row[key]);
  }
  return null;
}

export function makeChallenge(before, after, excluded) {
  const old = new Map(before.candidates.map(candidate => [candidate.id, candidate]));
  const current = new Map(after.candidates.map(candidate => [candidate.id, candidate]));
  const ids = [...new Set([...old.keys(), ...current.keys()])];
  return {
    disease: after.disease,
    excluded: exclusionKey(excluded).split(',').filter(Boolean),
    before: before.candidates,
    after: after.candidates,
    changes: ids.map(id => {
      const a = old.get(id);
      const b = current.get(id);
      return {
        id, name: (b || a).name,
        before_rank: a?.rank ?? b?.baseline_rank ?? null,
        after_rank: b?.rank ?? null,
        rank_delta: a && b ? a.rank - b.rank : b?.rank_delta ?? null,
        score_before: a?.score ?? null,
        score_after: b?.score ?? null
      };
    }),
    explanation: 'Evidence families are excluded before features are recomputed. The fitted scoring model is held fixed. This measures dependence on graph evidence, not the effect of a biological intervention.'
  };
}

export function isUnsafeQuestion(question) {
  return /\b(?:delete|detach|drop|merge|create|set|remove)\s+(?:all\b|database\b|graph\b|node\b|nodes\b|table\b|\()/i.test(question)
    || /\b(?:ignore|override|bypass)\b.{0,45}\b(?:instruction|guardrail|safety|system|rule)/i.test(question)
    || /\b(?:api[_ -]?key|password|secret|credentials)\b/i.test(question)
    || /\b(?:dosage|prescribe|what should i take|treat me|my symptoms)\b/i.test(question);
}

export function selectDisease(items, preferred) {
  return items.find(item => item.id === preferred)
    || items.find(item => /multiple sclerosis/i.test(item.name))
    || items.find(item => /breast cancer/i.test(item.name))
    || items[0] || null;
}

/** Resolve explicit entity mentions before using the UI's current selection. */
export function diseaseMentions(items, question) {
  const normalize = value => (String(value).toLowerCase().match(/[a-z0-9]+/g) || []).join(' ');
  const normalized = normalize(question);
  const occurrences = [];
  for (const disease of items) {
    const name = normalize(disease.name);
    if (!name) continue;
    const pattern = new RegExp(`\\b${name}\\b`, 'g');
    for (const match of normalized.matchAll(pattern)) {
      occurrences.push({ start: match.index, end: match.index + name.length, disease });
    }
  }
  const resolved = new Map();
  for (const occurrence of occurrences) {
    const contained = occurrences.some(other => other.start <= occurrence.start
      && occurrence.end <= other.end
      && other.end - other.start > occurrence.end - occurrence.start);
    if (!contained) resolved.set(occurrence.disease.id, occurrence.disease);
  }
  return [...resolved.values()];
}

export function evidenceSelection(evidence) {
  if (!evidence.truncated) return 'All available paths are shown.';
  const selection = typeof evidence.selection === 'string' ? evidence.selection.trim().replace(/[.]+$/, '') : '';
  return selection ? `Sample selection: ${selection}.` : 'This is a bounded sample of the available supporting paths.';
}

export function sourceEntries(value) {
  if (!value) return [];
  if (typeof value === 'string') return [{ name: value, url: safeURL(value) }];
  if (Array.isArray(value)) return value.flatMap(sourceEntries);
  if (typeof value === 'object') {
    if (value.name || value.url) return [{ name: value.name || value.url, url: safeURL(value.url) }];
    return Object.entries(value).map(([name, detail]) => ({ name, url: safeURL(detail), detail: objectText(detail) }));
  }
  return [];
}

export function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
