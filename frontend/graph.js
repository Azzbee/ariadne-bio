import { escapeHTML } from './utils.js';

const SVG = 'http://www.w3.org/2000/svg';
const COLORS = { Compound: '#174b3d', Gene: '#91a77c', Pathway: '#66899e', Disease: '#bd7756' };

export function pathFamily(path) {
  if (/P/.test(path.metapath || '') || (path.node_ids?.length || 0) > 4) return 'pathway';
  if ((path.node_ids?.length || 0) === 4) return 'interaction';
  return 'direct';
}

/** A deterministic layered layout: topology controls placement, not random motion. */
export function layoutGraph(data, paths = data.paths || []) {
  const ids = new Set([data.compound?.id, data.disease?.id].filter(Boolean));
  paths.forEach(path => path.node_ids.forEach(id => ids.add(id)));
  const nodes = (data.nodes || []).filter(node => ids.has(node.id)).map(node => ({ ...node }));
  const positions = new Map();
  const roles = new Map();
  paths.forEach(path => path.node_ids.forEach((id, index) => {
    if (!roles.has(id)) roles.set(id, []);
    roles.get(id).push(index / (path.node_ids.length - 1));
  }));
  const groups = new Map();
  for (const node of nodes) {
    if (node.id === data.compound?.id) { positions.set(node.id, { x: 100, y: 255 }); continue; }
    if (node.id === data.disease?.id) { positions.set(node.id, { x: 800, y: 255 }); continue; }
    const ratios = roles.get(node.id) || [0.5];
    const average = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    const group = node.label === 'Pathway' ? 'middle' : average < 0.46 ? 'left' : average > 0.54 ? 'right' : 'center';
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(node);
  }
  const xs = { left: 285, middle: 450, right: 620, center: 450 };
  for (const [group, members] of groups) {
    members.sort((a, b) => a.name.localeCompare(b.name));
    const other = group === 'center' ? groups.get('middle')?.length || 0 : 0;
    const space = Math.min(68, 385 / Math.max(1, members.length - 1));
    members.forEach((node, index) => {
      let y = 255 + (index - (members.length - 1) / 2) * space;
      if (other) y = index % 2 ? 450 - index * 25 : 75 + index * 25;
      positions.set(node.id, { x: xs[group], y });
    });
  }
  for (const node of nodes) Object.assign(node, positions.get(node.id) || { x: 450, y: 255 });
  const usedEdges = new Set(paths.flatMap(path => path.edge_ids || []));
  const edges = (data.edges || []).filter(edge => usedEdges.has(edge.id) && positions.has(edge.source) && positions.has(edge.target));
  return { nodes, edges, positions, width: 900, height: 540 };
}

function element(tag, attributes = {}, text = null) {
  const el = document.createElementNS(SVG, tag);
  Object.entries(attributes).forEach(([key, value]) => el.setAttribute(key, value));
  if (text !== null) el.textContent = text;
  return el;
}

function wrapLabel(text, maximum = 20) {
  const words = String(text).split(/\s+/);
  const lines = [];
  let line = '';
  for (const word of words) {
    if (line && (line + ' ' + word).length > maximum) { lines.push(line); line = word; }
    else line += (line ? ' ' : '') + word;
  }
  if (line) lines.push(line);
  return lines.slice(0, 3).map((value, index) => index === 2 && lines.length > 3 ? value + '…' : value);
}

function edgePath(a, b) {
  if (Math.abs(a.x - b.x) < 30) {
    const bend = 42;
    return `M ${a.x} ${a.y} C ${a.x + bend} ${a.y}, ${b.x + bend} ${b.y}, ${b.x} ${b.y}`;
  }
  const middle = (a.x + b.x) / 2;
  return `M ${a.x} ${a.y} C ${middle} ${a.y}, ${middle} ${b.y}, ${b.x} ${b.y}`;
}

export class EvidenceGraph {
  constructor(svg, tooltip, callbacks = {}) {
    this.svg = svg;
    this.tooltip = tooltip;
    this.callbacks = callbacks;
    this.data = null;
    this.paths = [];
    this.activePath = null;
    this.svg.addEventListener('pointerleave', () => { this.tooltip.hidden = true; });
  }

  render(data, filter = 'all') {
    this.data = data;
    this.paths = (data.paths || []).filter(path => filter === 'all' || pathFamily(path) === filter);
    this.svg.replaceChildren();
    const mobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 690px)').matches;
    this.svg.setAttribute('viewBox', mobile ? '0 0 540 900' : '0 0 900 540');
    this.svg.parentElement.classList.toggle('graph-vertical', mobile);
    this.svg.setAttribute('aria-label', `Evidence graph from ${data.compound?.name || 'compound'} to ${data.disease?.name || 'disease'}, showing ${this.paths.length} paths. Click nodes to inspect source records.`);
    const { nodes, edges, positions } = layoutGraph(data, this.paths);
    if (mobile) {
      for (const node of nodes) {
        const x = node.y, y = node.x;
        Object.assign(node, { x, y });
        positions.set(node.id, { x, y });
      }
    }
    const desc = element('desc', {}, 'The graph shows recorded biological relationships. Lines are evidence connections, not causal effects. Path order does not override the stored direction of a relationship.');
    this.svg.append(desc);
    const edgeLayer = element('g', { class: 'graph-edges' });
    const hitLayer = element('g', { class: 'graph-edge-targets' });
    const nodeLayer = element('g', { class: 'graph-nodes' });
    this.svg.append(edgeLayer, hitLayer, nodeLayer);
    for (const edge of edges) {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      const family = edge.type === 'INTERACTS' ? 'interaction' : edge.type === 'PARTICIPATES' ? 'pathway' : edge.type === 'ASSOCIATES' ? 'disease-edge' : '';
      const d = edgePath(a, b);
      const visible = element('path', { d, class: `graph-edge ${family}`, 'data-edge-id': edge.id });
      const hit = element('path', { d, class: 'graph-edge-hit', tabindex: '0', role: 'button', 'aria-label': `${edge.type} relationship. Inspect its sources.`, 'data-edge-id': edge.id });
      hit.addEventListener('pointerenter', event => {
        visible.classList.add('highlighted');
        this.showTooltip(event, edge.type, 'Inspect source record');
      });
      hit.addEventListener('pointermove', event => this.moveTooltip(event));
      hit.addEventListener('pointerleave', () => { this.tooltip.hidden = true; if (!this.activePath) visible.classList.remove('highlighted'); });
      hit.addEventListener('click', () => this.callbacks.onEdge?.(edge));
      hit.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.callbacks.onEdge?.(edge); }
      });
      edgeLayer.append(visible);
      hitLayer.append(hit);
    }
    for (const node of nodes) {
      const endpoint = node.id === data.compound?.id || node.id === data.disease?.id;
      const color = COLORS[node.label] || COLORS.Gene;
      const radius = endpoint ? 21 : node.label === 'Pathway' ? 10 : 8;
      const group = element('g', {
        transform: `translate(${node.x},${node.y})`, class: `graph-node${endpoint ? ' endpoint' : ''}`,
        'data-node-id': node.id, tabindex: '0', role: 'button',
        'aria-label': `${node.name}, ${node.label}. Inspect source record.`
      });
      group.append(element('circle', { r: radius + 8, fill: color, opacity: 0.12, class: 'node-halo' }));
      if (endpoint) group.append(element('circle', { r: radius + 7, fill: 'none', stroke: color, 'stroke-width': 0.8, opacity: 0.25 }));
      group.append(element('circle', { r: radius, fill: color, stroke: '#fcfcf7', 'stroke-width': 2.5 }));
      if (endpoint) group.append(element('circle', { r: 4, fill: '#fcfcf7', opacity: 0.85 }));
      const labelY = endpoint ? radius + 25 : radius + 19;
      const text = element('text', { 'text-anchor': 'middle', y: labelY });
      const lines = wrapLabel(node.name, endpoint ? 19 : 23);
      lines.forEach((line, index) => text.append(element('tspan', { x: 0, dy: index ? 15 : 0 }, line)));
      group.append(text);
      if (endpoint) group.append(element('text', { y: -radius - 18, 'text-anchor': 'middle', class: 'node-subtitle' }, node.label.toUpperCase()));
      group.addEventListener('pointerenter', event => this.showTooltip(event, node.name, `${node.label} · ${node.id}`));
      group.addEventListener('pointermove', event => this.moveTooltip(event));
      group.addEventListener('pointerleave', () => { this.tooltip.hidden = true; });
      group.addEventListener('click', () => this.callbacks.onNode?.(node));
      group.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.callbacks.onNode?.(node); }
      });
      nodeLayer.append(group);
    }
    this.activePath = null;
  }

  highlight(pathId) {
    this.activePath = pathId;
    const path = this.paths.find(item => item.id === pathId);
    const nodeIds = new Set(path?.node_ids || []);
    const edgeIds = new Set(path?.edge_ids || []);
    this.svg.querySelectorAll('.graph-node').forEach(node => node.classList.toggle('dimmed', !!path && !nodeIds.has(node.dataset.nodeId)));
    this.svg.querySelectorAll('.graph-edge').forEach(edge => {
      edge.classList.toggle('dimmed', !!path && !edgeIds.has(edge.dataset.edgeId));
      edge.classList.toggle('highlighted', !!path && edgeIds.has(edge.dataset.edgeId));
    });
  }

  reset() {
    this.highlight(null);
  }

  showTooltip(event, title, subtitle) {
    this.tooltip.innerHTML = `${escapeHTML(title)}<small>${escapeHTML(subtitle)}</small>`;
    this.tooltip.hidden = false;
    this.moveTooltip(event);
  }

  moveTooltip(event) {
    const bounds = this.svg.parentElement.getBoundingClientRect();
    const width = this.tooltip.offsetWidth;
    this.tooltip.style.left = `${Math.max(8, Math.min(bounds.width - width - 8, event.clientX - bounds.left + 12))}px`;
    this.tooltip.style.top = `${Math.max(8, event.clientY - bounds.top - this.tooltip.offsetHeight - 13)}px`;
  }
}
