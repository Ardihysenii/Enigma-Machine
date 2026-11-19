'use strict';
// Frontend contract tests, not cryptographic validation or browser rendering tests.
// Run: node --test tests/key_houses.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/key-houses.js'), 'utf8');
const KEY = 'enigma.house-demo.v1';
const PASSWORD = 'disposable-test-password';
const flags = ['pkcs8_recovered', 'pkcs12_recovered', 'wrong_password_rejected_pkcs8', 'wrong_password_rejected_pkcs12'];
function generated() {
  return {
    artifacts: {
      pkcs8: '-----BEGIN ENCRYPTED PRIVATE KEY-----\nMOCK-ENCRYPTED-ONLY\n-----END ENCRYPTED PRIVATE KEY-----',
      pkcs12: Buffer.from('mock encrypted PKCS12 bytes').toString('base64'),
      certificate: '-----BEGIN CERTIFICATE-----\nMOCK-PUBLIC-CERTIFICATE\n-----END CERTIFICATE-----'
    },
    house_public_keys: [0, 1, 2].map(i => '-----BEGIN PUBLIC KEY-----\nMOCK-PUBLIC-' + i + '\n-----END PUBLIC KEY-----'),
    certificate_sha256: 'ab'.repeat(32), valid_until: '2026-11-26T12:00:00+00:00',
    ...Object.fromEntries(flags.map(k => [k, true])),
    // Deliberately unwanted server fields must not reach browser storage.
    password: PASSWORD, decrypted_key: 'NEVER-PERSIST-THIS-SECRET',
    downloads: {'private-key.pem': '/api/download/worker-local-link'},
  };
}
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.dataset = {}; this.attributes = {};
    this.events = new Map(); this.value = ''; this.textContent = ''; this.disabled = false;
    this.checked = false; this._classes = new Set();
    this.classList = {
      add: (...xs) => xs.forEach(x => this._classes.add(x)),
      remove: (...xs) => xs.forEach(x => this._classes.delete(x)),
      contains: x => this._classes.has(x),
      toggle: (x, force) => { const yes = force === undefined ? !this._classes.has(x) : force; if (yes) this._classes.add(x); else this._classes.delete(x); return yes; },
    };
  }
  set className(text) { this._classes = new Set(text.split(/\s+/)); }
  set innerHTML(text) {
    this._html = text;
    // Only synthetic house state spans are needed; do not emulate an HTML parser.
    if (text.includes('kh-house-state')) { const state = new Element('span'); state.className = 'kh-house-state'; this.append(state); }
  }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(x => x !== this); }
  setAttribute(k, v) { this.attributes[k] = v; }
  addEventListener(name, fn) { const list = this.events.get(name) || []; list.push(fn); this.events.set(name, list); }
  matches(selector) {
    if (selector === '[data-kh-download]') return Boolean(this.dataset.khDownload);
    if (selector === 'input[name="kh-format"]:checked') return this.tagName === 'input' && this.name === 'kh-format' && this.checked;
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    return this.tagName === selector;
  }
  querySelectorAll(selectors) {
    const choices = selectors.split(','), found = [];
    const visit = node => { for (const child of node.children) { if (choices.some(s => child.matches(s))) found.push(child); visit(child); } };
    visit(this); return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  reset() { for (const input of this.querySelectorAll('input')) { if (input.name === 'kh-format') input.checked = input.value === 'pkcs8'; else input.value = ''; } }
  click() { return Promise.all((this.events.get('click') || []).map(fn => fn({preventDefault() {}}))); }
}
function harness(initial = new Map(), storageMode = '') {
  const nodes = {}, calls = [], replies = [], downloads = [], blobs = new Map(), mutations = [];
  const body = new Element('body'); body.dataset.task = 'packaging';
  function node(id, tag = 'div', parent = body) { const el = new Element(tag); el.id = id; nodes[id] = el; parent.append(el); return el; }
  const panel = node('key-houses', 'section');
  for (const id of ['houses', 'storage', 'status', 'target-heading', 'metadata', 'log']) node('kh-' + id, 'div', panel);
  const generate = node('kh-generate', 'form', panel), open = node('kh-open', 'form', panel);
  node('kh-new-password', 'input', generate); generate.append(new Element('button'));
  node('kh-test-password', 'input', open); open.append(new Element('button'));
  const fieldset = new Element('fieldset'); open.append(fieldset);
  for (const format of ['pkcs8', 'pkcs12']) { const input = new Element('input'); input.name = 'kh-format'; input.value = format; input.checked = format === 'pkcs8'; fieldset.append(input); }
  for (const id of ['clear', 'log-download']) node('kh-' + id, 'button', panel);
  for (const filename of ['private-key.pem', 'bundle.p12', 'certificate.pem']) { const button = new Element('button'); button.dataset.khDownload = filename; panel.append(button); }
  const document = {
    body, getElementById: id => nodes[id] || null, addEventListener() {},
    createElement(tag) { const el = new Element(tag); if (tag === 'a') el.click = () => downloads.push({filename: el.download, blob: blobs.get(el.href)}); return el; },
  };
  const localStorage = {
    getItem(k) { if (storageMode === 'unavailable') throw new Error('SecurityError'); return initial.get(k) ?? null; },
    setItem(k, v) { if (storageMode) throw new Error('QuotaExceededError'); mutations.push(['set', k]); initial.set(k, String(v)); },
    removeItem(k) { if (storageMode === 'unavailable') throw new Error('SecurityError'); mutations.push(['remove', k]); initial.delete(k); },
  };
  const context = vm.createContext({document, localStorage, location: {hash: '#packaging'}, Blob, Uint8Array,
    atob, btoa, console, AbortSignal: {timeout: ms => ({timeout: ms})},
    URL: {createObjectURL(blob) { const url = 'blob:mock-' + blobs.size; blobs.set(url, blob); return url; }, revokeObjectURL() {}},
    setTimeout: fn => { fn(); return 0; },
    fetch: async (url, options = {}) => {
      calls.push({url, method: options.method || 'GET', payload: options.body ? JSON.parse(options.body) : null});
      if (url !== '/api/tasks/packaging/run' || options.method !== 'POST') throw new Error('Unexpected request: worker-local GET regression');
      assert.ok(replies.length, 'Fetch has a configured reply');
      const reply = replies.shift(); return {ok: reply.status < 400, status: reply.status, json: async () => reply.data};
    },
  });
  new vm.Script(source, {filename: 'key-houses.js'}).runInContext(context, {timeout: 1000});
  async function emit(id, event = 'submit') {
    const handlers = nodes['kh-' + id].events.get(event) || [];
    assert.ok(handlers.length, 'Expected handler for ' + id);
    let timer;
    try { await Promise.race([Promise.all(handlers.map(fn => fn({preventDefault() {}}))), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Async handler exceeded 1500ms')), 1500); })]); }
    finally { clearTimeout(timer); }
  }
  return {nodes, panel, calls, replies, downloads, mutations, store: initial, emit,
    houses: () => nodes['kh-houses'].children,
    reply(data, status = 200) { replies.push({data, status}); },
    async generate() { nodes['kh-new-password'].value = PASSWORD; this.reply(generated()); await emit('generate'); },
    format(value) { for (const input of fieldset.children) input.checked = input.value === value; },
  };
}
const bounded = {timeout: 5000};
test('generation gets encrypted artifacts in one POST with no download GETs', bounded, async () => {
  const h = harness(); await h.generate();
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].method, 'POST');
  assert.deepEqual(h.calls[0].payload, {password: PASSWORD});
  assert.ok(h.store.has(KEY)); assert.equal(h.nodes['kh-new-password'].value, '');
  assert.match(h.nodes['kh-status'].textContent, /Both containers passed/);
  assert.equal(h.panel.attributes['aria-busy'], 'false');
});
test('persisted object contains only encrypted artifacts and allowlisted public metadata', bounded, async () => {
  const h = harness(); await h.generate(); const raw = h.store.get(KEY), data = JSON.parse(raw), fixture = generated();
  assert.deepEqual(Object.keys(data).sort(), ['version','pkcs8','pkcs12','certificate','publicKeys','fingerprint','validUntil','checks'].sort());
  assert.equal(data.pkcs8, fixture.artifacts.pkcs8); assert.equal(data.pkcs12, fixture.artifacts.pkcs12);
  assert.equal(data.certificate, fixture.artifacts.certificate); assert.deepEqual(data.publicKeys, fixture.house_public_keys);
  assert.deepEqual(Object.keys(data.checks).sort(), flags.slice().sort());
  assert.ok(!raw.includes(PASSWORD)); assert.ok(!raw.includes('NEVER-PERSIST-THIS-SECRET')); assert.ok(!raw.includes('/api/download/'));
  assert.ok(!h.nodes['kh-log'].textContent.includes(PASSWORD));
});
test('fresh harness restores saved artifacts and downloads all three without fetch', bounded, async () => {
  const first = harness(); await first.generate(); const h = harness(new Map(first.store));
  assert.equal(h.calls.length, 0); assert.match(h.nodes['kh-status'].textContent, /restored/);
  assert.ok(h.houses().every(el => !el.classList.contains('is-open')));
  for (const button of h.panel.querySelectorAll('[data-kh-download]')) { assert.equal(button.disabled, false); await button.click(); }
  assert.equal(h.calls.length, 0); assert.equal(h.downloads.length, 3);
  const fixture = generated();
  assert.equal(await h.downloads[0].blob.text(), fixture.artifacts.pkcs8);
  assert.equal(Buffer.from(await h.downloads[1].blob.arrayBuffer()).toString('base64'), fixture.artifacts.pkcs12);
  assert.equal(await h.downloads[2].blob.text(), fixture.artifacts.certificate);
});
test('wrong short password returns a failure and never opens a house', bounded, async () => {
  const h = harness(); await h.generate(); h.nodes['kh-test-password'].value = 'bad';
  h.reply({error: 'Incorrect password or invalid encrypted package.'}, 400); await h.emit('open');
  assert.equal(h.calls[1].payload.password, 'bad'); assert.equal(h.nodes['kh-test-password'].value, '');
  assert.ok(h.houses().every(el => !el.classList.contains('is-open')));
  assert.equal(h.houses()[0].classList.contains('is-rejected'), true);
  assert.match(h.nodes['kh-status'].textContent, /Incorrect password/);
});
test('matching result opens only selected house and submits restored PKCS12 bytes', bounded, async () => {
  const first = harness(); await first.generate(); const h = harness(new Map(first.store)); h.format('pkcs12');
  h.nodes['kh-test-password'].value = PASSWORD; h.reply({opened: true, key_loaded: true, certificate_matches: true}); await h.emit('open');
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].payload.action, 'open');
  assert.equal(h.calls[0].payload.artifact, generated().artifacts.pkcs12); assert.equal(h.calls[0].payload.format, 'pkcs12');
  assert.equal(h.calls[0].payload.public_key, generated().house_public_keys[0]);
  assert.equal(h.houses()[0].classList.contains('is-open'), true);
  assert.ok(h.houses().slice(1).every(el => !el.classList.contains('is-open')));
  assert.equal(h.nodes['kh-test-password'].value, ''); assert.ok(!h.nodes['kh-log'].textContent.includes(PASSWORD));
});
test('valid password but mismatched house remains locked with correct public-key payload', bounded, async () => {
  const h = harness(); await h.generate(); await h.houses()[1].click(); h.nodes['kh-test-password'].value = PASSWORD;
  h.reply({opened: false, key_loaded: true}); await h.emit('open');
  assert.equal(h.calls[1].payload.public_key, generated().house_public_keys[1]);
  assert.equal(h.calls[1].payload.artifact, generated().artifacts.pkcs8);
  assert.ok(h.houses().every(el => !el.classList.contains('is-open')));
  assert.match(h.nodes['kh-status'].textContent, /different public key/);
});
test('clear resets doors and removes only this demo storage key', bounded, async () => {
  const h = harness(new Map([['unrelated-session', 'retain-me']])); await h.generate();
  h.nodes['kh-test-password'].value = PASSWORD; h.reply({opened: true, key_loaded: true}); await h.emit('open');
  await h.emit('clear', 'click');
  assert.equal(h.store.has(KEY), false); assert.equal(h.store.get('unrelated-session'), 'retain-me');
  assert.deepEqual(h.mutations.filter(x => x[0] === 'remove'), [['remove', KEY]]);
  assert.ok(h.houses().every(el => !el.classList.contains('is-open') && !el.classList.contains('is-rejected')));
  assert.ok(h.panel.querySelectorAll('[data-kh-download]').every(el => el.disabled));
  assert.equal(h.nodes['kh-open'].querySelector('button').disabled, true);
});
test('corrupt saved data is rejected, not fetched or enabled for download', bounded, () => {
  const h = harness(new Map([[KEY, '{broken JSON']]));
  assert.equal(h.calls.length, 0); assert.match(h.nodes['kh-status'].textContent, /could not be loaded/);
  assert.ok(h.panel.querySelectorAll('[data-kh-download]').every(el => el.disabled));
});
test('quota failure retains in-memory encrypted downloads without saving password', bounded, async () => {
  const h = harness(new Map(), 'quota'); await h.generate();
  assert.equal(h.store.has(KEY), false); assert.match(h.nodes['kh-storage'].textContent, /unavailable or full/);
  await h.panel.querySelectorAll('[data-kh-download]')[0].click(); assert.equal(h.downloads.length, 1);
  assert.equal(await h.downloads[0].blob.text(), generated().artifacts.pkcs8);
});
