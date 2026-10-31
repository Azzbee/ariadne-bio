import { compoundReferences, diseaseReferences, exclusionKey, isUnsafeQuestion, makeChallenge, requestedExclusions, requestsTopCandidate } from './utils.js';

export class APIError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = 'APIError';
    this.status = status;
    this.details = details;
  }
}

/** The live and published research editions share exactly one interface. */
export class AriadneAPI {
  constructor(config = {}, fetcher = globalThis.fetch.bind(globalThis)) {
    this.base = (config.apiBase || '/api').replace(/\/$/, '');
    this.manifestPath = config.snapshotManifest || './data/manifest.json';
    this.fetcher = fetcher;
    this.mode = null;
    this.manifest = null;
    this.healthData = null;
    this.cases = new Map();
    this.pendingCases = new Map();
  }

  async json(url, options = {}, timeout = 30000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await this.fetcher(url, { ...options, signal: controller.signal });
      const type = response.headers?.get?.('content-type') || '';
      if (type && !type.includes('json')) throw new APIError('The server returned a page instead of graph data.', response.status);
      let data;
      try { data = await response.json(); }
      catch { throw new APIError('The server returned unreadable data.', response.status); }
      if (!response.ok) {
        const detail = data.detail || data.message || 'The request could not be completed.';
        throw new APIError(typeof detail === 'string' ? detail : JSON.stringify(detail), response.status, data);
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new APIError('The graph request timed out. Please try again.');
      throw error;
    } finally { clearTimeout(timer); }
  }

  async initialize(forceSnapshot = false) {
    if (!forceSnapshot) {
      try {
        const health = await this.json(`${this.base}/health`, {}, 4000);
        if (!health || !('status' in health)) throw new APIError('The API health response is incomplete.');
        this.healthData = health;
        this.mode = 'live';
        return health;
      } catch (error) { this.liveError = error; }
    }
    try {
      this.manifest = await this.json(this.manifestPath);
      if (!this.manifest.cases || !Array.isArray(this.manifest.diseases)) throw new APIError('The published data manifest is incomplete.');
      this.mode = 'snapshot';
      this.healthData = {
        status: 'ok', graph_backend: 'published research snapshot', dataset_ready: true,
        agent_mode: 'deterministic', version: '1.1.0', ...(this.manifest.health || {})
      };
      return this.healthData;
    } catch {
      throw new APIError('ARIADNE could not reach its graph API or a published research snapshot. Start the application with make docker-run, then retry.');
    }
  }

  async get(path) { return this.json(`${this.base}${path}`); }
  async post(path, data) {
    return this.json(`${this.base}${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
    }, 90000);
  }

  async loadCase(diseaseId) {
    if (this.cases.has(diseaseId)) return this.cases.get(diseaseId);
    if (this.pendingCases.has(diseaseId)) return this.pendingCases.get(diseaseId);
    const descriptor = this.manifest.cases[diseaseId];
    if (!descriptor) throw new APIError('This disease is not included in the published research edition. Run the full application to investigate all diseases.');
    if (descriptor.rankings) { this.cases.set(diseaseId, descriptor); return descriptor; }
    const file = typeof descriptor === 'string' ? descriptor : descriptor.file;
    if (!file || file.includes('..') || /^(?:https?:|\/\/)/i.test(file)) throw new APIError('Invalid research case location.');
    const root = this.manifestPath.slice(0, this.manifestPath.lastIndexOf('/') + 1);
    const promise = this.json(`${root}${file}`).then(data => {
      this.cases.set(diseaseId, data);
      this.pendingCases.delete(diseaseId);
      return data;
    }).catch(error => { this.pendingCases.delete(diseaseId); throw error; });
    this.pendingCases.set(diseaseId, promise);
    return promise;
  }

  async stats() { return this.mode === 'snapshot' ? this.manifest.stats : this.get('/stats'); }
  async provenance() { return this.mode === 'snapshot' ? this.manifest.provenance : this.get('/provenance'); }
  async evaluation() { return this.mode === 'snapshot' ? this.manifest.evaluation : this.get('/evaluation'); }

  async diseases(query = '', limit = 137, offset = 0) {
    if (this.mode === 'live') return this.get(`/diseases?q=${encodeURIComponent(query)}&limit=${limit}&offset=${offset}`);
    const items = this.manifest.diseases.filter(item => item.name.toLowerCase().includes(query.toLowerCase()));
    return { items: items.slice(offset, offset + limit), total: items.length };
  }

  async rankings(diseaseId, excluded = [], limit = 12, offset = 0) {
    const key = exclusionKey(excluded);
    if (this.mode === 'live') return this.get(`/rankings/${encodeURIComponent(diseaseId)}?exclude=${key}&limit=${limit}&offset=${offset}`);
    const data = await this.loadCase(diseaseId);
    const response = data.rankings[key];
    if (!response) throw new APIError('This evidence configuration is not included in the published snapshot. Restore the evidence or run the full application.');
    return { ...response, candidates: response.candidates.slice(offset, offset + limit), published_count: response.candidates.length };
  }

  async evidence(diseaseId, compoundId, excluded = [], limit = 12) {
    const key = exclusionKey(excluded);
    if (this.mode === 'live') return this.get(`/evidence/${encodeURIComponent(diseaseId)}/${encodeURIComponent(compoundId)}?exclude=${key}&limit=${limit}`);
    const data = await this.loadCase(diseaseId);
    const response = data.evidence?.[compoundId]?.[key];
    if (!response) throw new APIError('This candidate’s evidence is not included in the published snapshot. Run the full application to inspect it.');
    return response;
  }

  async assessment(diseaseId, compoundId, excluded = []) {
    const key = exclusionKey(excluded);
    if (this.mode === 'live') return this.get(`/assessment/${encodeURIComponent(diseaseId)}/${encodeURIComponent(compoundId)}?exclude=${key}`);
    const data = await this.loadCase(diseaseId);
    const response = data.assessments?.[compoundId]?.[key];
    if (!response) throw new APIError('This compound’s score assessment is not included in this published case. Choose a published candidate or run the full application.');
    return response;
  }

  async challenge(diseaseId, excluded, limit = 12) {
    const key = exclusionKey(excluded);
    if (this.mode === 'live') return this.post('/challenge', { disease_id: diseaseId, exclude: key.split(',').filter(Boolean), limit });
    const data = await this.loadCase(diseaseId);
    return data.challenges?.[key] || makeChallenge(await this.rankings(diseaseId, [], limit), await this.rankings(diseaseId, excluded, limit), excluded);
  }

  async similar(compoundId, diseaseId, limit = 10) {
    if (this.mode === 'live') return this.get(`/similar/${encodeURIComponent(compoundId)}?limit=${limit}`);
    const data = await this.loadCase(diseaseId);
    return data.similarities?.[compoundId] || null;
  }

  async algorithms(diseaseId, limit = 10) {
    if (this.mode === 'live') return this.get(`/algorithms/${encodeURIComponent(diseaseId)}?limit=${limit}`);
    const data = await this.loadCase(diseaseId);
    return data.algorithms || null;
  }

  async agent(question, diseaseId, excluded = [], compoundId = null) {
    if (this.mode === 'live') return this.post('/agent', { question, disease_id: diseaseId, compound_id: compoundId, exclude: excluded });
    const disclaimer = 'Research hypotheses, not validated treatments or medical advice.';
    if (isUnsafeQuestion(question)) return {
      status: 'rejected', mode: 'deterministic',
      answer: 'This research guide only reads published graph evidence. It cannot change the graph, reveal credentials, prescribe treatment, or bypass its evidence rules.',
      candidates: [], citations: [], suggestions: ['Explain the current ranking', 'What changes without gene interactions?'],
      trace: [{ step: 1, tool: 'validate_request', status: 'rejected', summary: 'The request is outside the read-only research scope.' }], disclaimer
    };
    const diseaseIds = diseaseReferences(this.manifest.diseases, question);
    if (diseaseIds.unknown.length) return {
      status: 'clarification', mode: 'deterministic',
      answer: `This published edition does not recognize ${diseaseIds.unknown.join(', ')}. Choose one available disease case; a different valid name does not resolve an unknown identifier.`,
      candidates: [], citations: [], trace: [], suggestions: [], disclaimer
    };
    const mentioned = diseaseIds.matches;
    if (mentioned.length > 1) return {
      status: 'clarification', mode: 'deterministic', answer: 'Choose one disease in the investigation selector so the evidence has an unambiguous starting point.',
      candidates: [], citations: [], trace: [], suggestions: mentioned.map(item => item.name), disclaimer
    };
    const id = mentioned[0]?.id || diseaseId;
    if (!id) return { status: 'clarification', mode: 'deterministic', answer: 'Select a published disease case first.', candidates: [], citations: [], trace: [], suggestions: [], disclaimer };
    const manifestReferences = compoundReferences(this.manifest.compounds || [], question);
    if (this.manifest.compounds && manifestReferences.unknown.length) return {
      status: 'clarification', mode: 'deterministic',
      answer: `The requested compound identifier is not recognized: ${manifestReferences.unknown.join(', ')}. Choose one recorded compound; a different valid name does not resolve an unknown identifier.`,
      candidates: [], citations: [], trace: [], suggestions: [], disclaimer
    };
    if (!mentioned.length && !manifestReferences.matches.length && !/\b(?:rank|ranking|top|compound|candidate|evidence|gene|genes|interaction|interactions|pathway|pathways|model|score|explain|why|support|supported|hypothesis|hypotheses|changes?)\b/i.test(question)) return {
      status: 'clarification', mode: 'deterministic',
      answer: 'This published research guide can explain the selected disease’s ranking and compare evidence exclusions. Ask about a candidate, its paths, or what changes without gene interactions.',
      candidates: [], citations: [], trace: [], suggestions: ['Explain the top candidate', 'What changes without gene interactions?'], disclaimer
    };
    const data = await this.loadCase(id);
    const availableCompounds = Object.values(data.assessments || {}).map(scenarios => Object.values(scenarios)[0]?.compound).filter(Boolean);
    const identities = this.manifest.compounds || availableCompounds;
    const references = this.manifest.compounds ? manifestReferences : compoundReferences(identities, question);
    const namedCompounds = references.matches;
    if (references.unknown.length) return {
      status: 'clarification', mode: 'deterministic', answer: `This published edition does not recognize ${references.unknown.join(', ')}. Choose one recorded compound.`,
      candidates: [], citations: [], trace: [], suggestions: [], disclaimer
    };
    if (namedCompounds.length > 1) return {
      status: 'clarification', mode: 'deterministic',
      answer: 'Name one compound so the score explanation and evidence refer to a single investigation.',
      candidates: [], citations: [], trace: [], suggestions: namedCompounds.map(item => item.name), disclaimer
    };
    const explicitlyTop = requestsTopCandidate(question);
    const changedDisease = mentioned.length === 1 && id !== diseaseId;
    const selectedId = namedCompounds[0]?.id || (!explicitlyTop && !changedDisease ? compoundId : null);
    if (selectedId && !data.assessments?.[selectedId]) return {
      status: 'clarification', mode: 'deterministic', disease: data.disease,
      answer: `${namedCompounds[0]?.name || 'The selected compound'} is not included in the published results for ${data.disease?.name || 'this disease'}. Choose a published candidate or run the full application to investigate it.`,
      candidates: [], citations: [], trace: [], suggestions: ['Explain the top candidate'], disclaimer
    };
    const effective = requestedExclusions(question, excluded);
    const result = await this.rankings(id, effective, 3);
    const focusId = selectedId || result.candidates[0]?.id;
    const [assessment, evidence] = focusId ? await Promise.all([
      this.assessment(id, focusId, effective), this.evidence(id, focusId, effective, 12)
    ]) : [null, null];
    const current = assessment?.current;
    const baseline = assessment?.baseline;
    const position = value => value.supported ? `rank #${value.rank}, model score ${Number(value.score).toFixed(3)}` : `no supported rank, diagnostic score ${Number(value.score).toFixed(3)}`;
    const answer = assessment
      ? `For ${result.disease.name}, this brief investigates ${assessment.compound.name}.\n\nCurrent evidence: ${position(current)}. ${current.evidence_count} complete supporting paths: ${current.features.direct} direct, ${current.features.interaction} interaction, and ${current.features.pathway} pathway.\n\n${effective.length ? `All-evidence baseline: ${position(baseline)}, with ${baseline.evidence_count} paths. Excluded evidence: ${exclusionKey(effective)}. The fitted model is unchanged.\n\n` : ''}${current.supported ? 'The exact score assessment records the feature values, fitted coefficients, and their contributions in logit space.' : 'No supporting paths remain. A finite model output is shown only for diagnosis; the compound is not included in the supported ranking.'}\n\nThe ranking is a research hypothesis. It does not establish efficacy, safety, or causality.`
      : 'No supported candidates are available under this evidence configuration. Restore evidence families to investigate a candidate.';
    return {
      status: 'complete', mode: 'deterministic', answer, disease: result.disease,
      compound: assessment?.compound || null, assessment, excluded: effective,
      candidates: result.candidates, evidence,
      citations: (evidence?.paths || []).slice(0, 3).map(path => ({ id: path.id, label: `${path.metapath || 'Evidence path'} · ${path.id}` })),
      trace: [
        { step: 1, tool: 'validate_request', status: 'complete', summary: 'Read-only research question accepted.' },
        { step: 2, tool: 'resolve_entity', status: 'complete', summary: result.disease.name },
        { step: 3, tool: 'load_recorded_ranking', status: 'complete', summary: `${effective.length ? effective.join(', ') + ' excluded' : 'All evidence families'} · fixed fitted model` },
        { step: 4, tool: 'load_recorded_assessment', status: 'complete', summary: assessment ? `${assessment.compound.name} · exact fitted-model terms · ${current.supported ? 'supported rank' : 'unsupported diagnostic'}` : 'No supported candidate selected' },
        { step: 5, tool: 'retrieve_recorded_paths', status: 'complete', summary: `${evidence?.paths?.length || 0} displayed evidence paths` },
        { step: 6, tool: 'format_structured_brief', status: 'complete', summary: 'Deterministic summary of published results. No language model was called.' }
      ], suggestions: ['What changes without gene interactions?', 'Explain the current ranking'], disclaimer
    };
  }
}
