import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { openDossierDialog, ProvenancePanel } from '../provenance.js';

/** Minimal event/element host: tests the dialog's actual callbacks without a new DOM dependency. */
class Element extends EventTarget {
  constructor(tag, owner) { super(); this.tagName = tag; this.owner = owner; this.attributes = new Map(); this.children = []; this.parent = null; this.disabled = false; this.open = false; }
  get isConnected() { return this === this.owner.body || !!this.parent?.isConnected; }
  get ownerDocument() { return this.owner; }
  setAttribute(name, value) { this.attributes.set(name, value); }
  append(...elements) { for (const element of elements) { element.parent = this; this.children.push(element); } }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(child => child !== this); this.parent = null; }
  focus() { this.owner.activeElement = this; }
  showModal() { this.open = true; }
  close() { if (this.open) { this.open = false; this.dispatchEvent(new Event('close')); } }
  click() { if (!this.disabled) this.dispatchEvent(new Event('click')); }
}
function host() {
  const documentObject = { activeElement: null, createElement(tag) { return new Element(tag, this); } };
  documentObject.body = documentObject.createElement('body');
  const trigger = documentObject.createElement('button'); documentObject.body.append(trigger); trigger.focus();
  return { documentObject, trigger };
}
function descendant(element, condition) {
  if (condition(element)) return element;
  for (const child of element.children) { const found = descendant(child, condition); if (found) return found; }
  return null;
}
const button = (dialog, label) => descendant(dialog, element => element.tagName === 'button' && element.textContent === label);
const downloadLink = dialog => descendant(dialog, element => element.tagName === 'a' && element.textContent === 'Download HTML');

test('review opens an accessible native modal with a scriptless isolated document and no automatic print/download', t => {
  const { documentObject, trigger, clicks } = downloadHost(t);
  const html = '<!doctype html><title>Frozen certificate review</title><p>Exact scope</p>';
  const dialog = openDossierDialog({ html, title: 'Review <unsafe name>', documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  assert.equal(dialog.tagName, 'dialog'); assert.equal(dialog.open, true);
  assert.equal(dialog.attributes.get('aria-labelledby'), 'dependency-review-title');
  assert.equal(descendant(dialog, element => element.id === 'dependency-review-title').textContent, 'Review <unsafe name>');
  assert.equal(frame.srcdoc, html); assert.equal(frame.attributes.get('sandbox'), 'allow-same-origin allow-modals');
  assert.ok(!frame.attributes.get('sandbox').includes('allow-scripts')); assert.equal(frame.attributes.get('referrerpolicy'), 'no-referrer');
  assert.equal(button(dialog, 'Print').disabled, true); assert.equal(clicks.length, 0);
  button(dialog, 'Close').click(); assert.equal(documentObject.activeElement, trigger);
});

test('printing requires a loaded preview and an explicit button action', t => {
  const { documentObject } = downloadHost(t); let prints = 0, focuses = 0;
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  frame.contentWindow = { focus() { focuses += 1; }, print() { prints += 1; } };
  button(dialog, 'Print').click(); assert.equal(prints, 0);
  frame.dispatchEvent(new Event('load')); assert.equal(prints, 0); assert.equal(button(dialog, 'Print').disabled, false);
  button(dialog, 'Print').click(); assert.equal(prints, 1); assert.equal(focuses, 1);
});

test('the visible download link keeps native activation and does not synthesize another click', t => {
  const { documentObject, clicks, blobs, timers } = downloadHost(t);
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', documentObject });
  const link = downloadLink(dialog), activation = new Event('click', { cancelable: true });
  assert.equal(link.href, 'blob:captured-export'); assert.equal(link.download, 'ariadne-review.html');
  link.dispatchEvent(activation);
  assert.equal(activation.defaultPrevented, false); assert.equal(clicks.length, 0);
  assert.equal(link.isConnected, true); assert.equal(downloadLink(dialog), link);
  assert.equal(blobs.length, 1); assert.equal(timers.length, 0, 'a visible link must not lose its Blob URL');
  assert.equal(descendant(dialog, element => element.attributes.get('role') === 'status').textContent, 'HTML prepared; check your browser’s downloads.');
});

function downloadHost(t, { failBlob = false } = {}) {
  const { documentObject, trigger } = host(), clicks = [], blobs = [], timers = [], revoked = [];
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: documentObject });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'document', previous); else delete globalThis.document; });
  t.mock.method(documentObject, 'createElement', function createElement(tag) {
    const element = new Element(tag, this);
    if (tag === 'a') element.click = () => { clicks.push({ anchor: element, parent: element.parent, connected: element.isConnected, filename: element.download }); };
    return element;
  });
  t.mock.method(URL, 'createObjectURL', blob => { if (failBlob) throw new Error('Unavailable'); blobs.push(blob); return 'blob:captured-export'; });
  t.mock.method(URL, 'revokeObjectURL', url => { revoked.push(url); });
  t.mock.method(globalThis, 'setTimeout', (callback, delay) => { timers.push({ callback, delay }); return 1; });
  return { documentObject, trigger, clicks, blobs, timers, revoked };
}

test('the real dossier link belongs to the active dialog and exports exactly its captured preview bytes', async t => {
  const { documentObject, clicks, blobs, timers } = downloadHost(t);
  const dataRoot = new URL('../data/', import.meta.url);
  const manifest = JSON.parse(fs.readFileSync(new URL('manifest.json', dataRoot), 'utf8'));
  const data = JSON.parse(fs.readFileSync(new URL(manifest.cases['Disease::DOID:7148'].file, dataRoot), 'utf8'));
  const certificate = data.provenance_audits['Compound::DB00786']['10:1'];
  const panel = {
    session: { exportCertificate: () => certificate, verification: null }, api: { mode: 'snapshot' }, callbacks: {}
  };
  ProvenancePanel.prototype.openDossier.call(panel);
  const dialog = descendant(documentObject.body, element => element.tagName === 'dialog');
  assert.equal(dialog.open, true); assert.equal(clicks.length, 0);
  const link = downloadLink(dialog), frame = descendant(dialog, element => element.tagName === 'iframe');
  link.dispatchEvent(new Event('click', { cancelable: true }));
  assert.equal(clicks.length, 0); assert.equal(link.isConnected, true);
  assert.equal(link.ownerDocument, dialog.ownerDocument);
  assert.equal(link.download, 'ariadne-rheumatoid-arthritis-marimastat-source-budget1-review.html');
  assert.equal(blobs[0].type, 'text/html;charset=utf-8');
  const contents = await blobs[0].text();
  assert.equal(contents, frame.srcdoc); assert.match(contents, new RegExp(certificate.certificate_sha256));
  assert.equal(timers.length, 0);
  assert.equal(frame.attributes.get('sandbox'), 'allow-same-origin allow-modals');
});

test('the non-modal JSON export retains its normal document host and exact content', async t => {
  const { documentObject, clicks, blobs } = downloadHost(t);
  const certificate = { disease: { name: 'Example disease' }, compound: { name: 'Example compound' }, scope: { group_kind: 'source' }, budget: 1 };
  const panel = { session: { exportCertificate: () => certificate }, callbacks: {} };
  assert.equal(ProvenancePanel.prototype.download.call(panel), true);
  assert.equal(clicks[0].parent, documentObject.body); assert.equal(clicks[0].connected, true);
  assert.equal(blobs[0].type, 'application/json');
  assert.deepEqual(JSON.parse(await blobs[0].text()), certificate);
});

test('Escape closes the modal, restores focus and releases its Blob URL only after a grace period', t => {
  const { documentObject, trigger, timers, revoked } = downloadHost(t);
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  const escape = new Event('cancel', { cancelable: true }); dialog.dispatchEvent(escape);
  assert.equal(escape.defaultPrevented, true); assert.equal(dialog.open, false);
  assert.equal(frame.isConnected, false); assert.equal(dialog.isConnected, false); assert.equal(documentObject.activeElement, trigger);
  assert.deepEqual(revoked, []); assert.equal(timers.length, 1); assert.equal(timers[0].delay, 30000);
  timers[0].callback(); assert.deepEqual(revoked, ['blob:captured-export']);
  dialog.dispatchEvent(new Event('close')); assert.equal(timers.length, 1, 'cleanup must not schedule a second release');
});

test('failed printing leaves the review accessible and reports the failure', t => {
  const { documentObject } = downloadHost(t);
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  frame.contentWindow = { focus() {}, print() { throw new Error('Unavailable'); } };
  frame.dispatchEvent(new Event('load')); button(dialog, 'Print').click();
  const status = descendant(dialog, element => element.attributes.get('role') === 'status');
  assert.match(status.textContent, /could not open its print dialog/); assert.equal(dialog.open, true);
});

test('a Blob preparation failure keeps the preview available without an actionable broken download', t => {
  const { documentObject, timers, revoked } = downloadHost(t, { failBlob: true });
  const dialog = openDossierDialog({ html: '<p>Review remains readable</p>', title: 'Review', documentObject });
  const link = downloadLink(dialog), activation = new Event('click', { cancelable: true });
  assert.equal(link.href, undefined); assert.equal(link.attributes.get('aria-disabled'), 'true');
  assert.match(descendant(dialog, element => element.attributes.get('role') === 'status').textContent, /could not be prepared/);
  link.dispatchEvent(activation); assert.equal(activation.defaultPrevented, true); assert.equal(dialog.open, true);
  assert.equal(descendant(dialog, element => element.tagName === 'iframe').srcdoc, '<p>Review remains readable</p>');
  button(dialog, 'Close').click(); assert.equal(timers.length, 0); assert.deepEqual(revoked, []);
});
