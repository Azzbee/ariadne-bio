import test from 'node:test';
import assert from 'node:assert/strict';
import { layoutGraph, pathFamily } from '../graph.js';

const data = {
  compound: { id: 'c', name: 'Compound' }, disease: { id: 'd', name: 'Disease' },
  nodes: [
    { id: 'c', name: 'Compound', label: 'Compound' },
    { id: 'g1', name: 'Gene A', label: 'Gene' },
    { id: 'p', name: 'Pathway', label: 'Pathway' },
    { id: 'g2', name: 'Gene B', label: 'Gene' },
    { id: 'd', name: 'Disease', label: 'Disease' },
    { id: 'unrelated', name: 'Unrelated', label: 'Gene' }
  ],
  edges: [
    { id: 'e1', source: 'c', target: 'g1' },
    { id: 'e2', source: 'g1', target: 'p' },
    { id: 'e3', source: 'g2', target: 'p' },
    { id: 'e4', source: 'd', target: 'g2' },
    { id: 'e5', source: 'd', target: 'unrelated' }
  ],
  paths: [{ id: 'path', node_ids: ['c', 'g1', 'p', 'g2', 'd'], edge_ids: ['e1', 'e2', 'e3', 'e4'], metapath: 'C-G-P-G-D' }]
};

test('layout uses exact path topology and leaves imported records untouched', () => {
  const serialized = JSON.stringify(data);
  const result = layoutGraph(data);
  assert.equal(result.nodes.length, 5);
  assert.equal(result.edges.length, 4);
  const x = id => result.positions.get(id).x;
  assert.ok(x('c') < x('g1') && x('g1') < x('p') && x('p') < x('g2') && x('g2') < x('d'));
  assert.equal(JSON.stringify(data), serialized);
});

test('empty evidence leaves endpoints but never invents edges', () => {
  const result = layoutGraph(data, []);
  assert.deepEqual(result.nodes.map(node => node.id), ['c', 'd']);
  assert.deepEqual(result.edges, []);
});

test('layout is deterministic across rerenders', () => {
  assert.deepEqual(layoutGraph(data).nodes, layoutGraph(data).nodes);
});

test('metapath families distinguish direct, interaction, and shared pathway evidence', () => {
  assert.equal(pathFamily({ metapath: 'C-G-D', node_ids: ['c', 'g', 'd'] }), 'direct');
  assert.equal(pathFamily({ metapath: 'C-G-G-D', node_ids: ['c', 'g', 'g2', 'd'] }), 'interaction');
  assert.equal(pathFamily(data.paths[0]), 'pathway');
});
