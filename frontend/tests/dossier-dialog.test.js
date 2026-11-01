import test from 'node:test';
import assert from 'node:assert/strict';
import { openDossierDialog } from '../provenance.js';

/** Minimal event/element host: tests the dialog's actual callbacks without a new DOM dependency. */
class Element extends EventTarget {
  constructor(tag, owner) { super(); this.tagName = tag; this.owner = owner; this.attributes = new Map(); this.children = []; this.parent = null; this.disabled = false; this.open = false; }
  get isConnected() { return this === this.owner.body || !!this.parent?.isConnected; }
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

test('review opens an accessible native modal with a scriptless isolated document and no automatic print/download', () => {
  const { documentObject, trigger } = host(); let downloads = 0;
  const html = '<!doctype html><title>Frozen certificate review</title><p>Exact scope</p>';
  const dialog = openDossierDialog({ html, title: 'Review <unsafe name>', onDownload: () => { downloads += 1; }, documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  assert.equal(dialog.tagName, 'dialog'); assert.equal(dialog.open, true);
  assert.equal(dialog.attributes.get('aria-labelledby'), 'dependency-review-title');
  assert.equal(descendant(dialog, element => element.id === 'dependency-review-title').textContent, 'Review <unsafe name>');
  assert.equal(frame.srcdoc, html); assert.equal(frame.attributes.get('sandbox'), 'allow-same-origin allow-modals');
  assert.ok(!frame.attributes.get('sandbox').includes('allow-scripts')); assert.equal(frame.attributes.get('referrerpolicy'), 'no-referrer');
  assert.equal(button(dialog, 'Print').disabled, true); assert.equal(downloads, 0);
  button(dialog, 'Close').click(); assert.equal(documentObject.activeElement, trigger);
});

test('printing requires a loaded preview and an explicit button action', () => {
  const { documentObject } = host(); let prints = 0, focuses = 0;
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', onDownload() {}, documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  frame.contentWindow = { focus() { focuses += 1; }, print() { prints += 1; } };
  button(dialog, 'Print').click(); assert.equal(prints, 0);
  frame.dispatchEvent(new Event('load')); assert.equal(prints, 0); assert.equal(button(dialog, 'Print').disabled, false);
  button(dialog, 'Print').click(); assert.equal(prints, 1); assert.equal(focuses, 1);
});

test('download is a separate explicit action and its message does not assert browser acceptance', () => {
  const { documentObject } = host(); let downloads = 0;
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', onDownload() { downloads += 1; return true; }, documentObject });
  button(dialog, 'Download HTML').click(); assert.equal(downloads, 1);
  assert.equal(descendant(dialog, element => element.attributes.get('role') === 'status').textContent, 'HTML prepared; check your browser’s downloads.');
});

test('Escape closes the modal, discards its embedded document and restores the invoking focus', () => {
  const { documentObject, trigger } = host();
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', onDownload() {}, documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  const escape = new Event('cancel', { cancelable: true }); dialog.dispatchEvent(escape);
  assert.equal(escape.defaultPrevented, true); assert.equal(dialog.open, false);
  assert.equal(frame.isConnected, false); assert.equal(dialog.isConnected, false); assert.equal(documentObject.activeElement, trigger);
});

test('failed print or download leaves the review accessible and reports the failure', () => {
  const { documentObject } = host();
  const dialog = openDossierDialog({ html: '<p>Review</p>', title: 'Review', onDownload() { return false; }, documentObject });
  const frame = descendant(dialog, element => element.tagName === 'iframe');
  frame.contentWindow = { focus() {}, print() { throw new Error('Unavailable'); } };
  frame.dispatchEvent(new Event('load')); button(dialog, 'Print').click();
  const status = descendant(dialog, element => element.attributes.get('role') === 'status');
  assert.match(status.textContent, /could not open its print dialog/); assert.equal(dialog.open, true);
  button(dialog, 'Download HTML').click(); assert.match(status.textContent, /could not be prepared/); assert.equal(dialog.open, true);
});
