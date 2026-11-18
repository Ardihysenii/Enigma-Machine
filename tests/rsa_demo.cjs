const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const test = require('node:test');
const assert = require('node:assert/strict');
const source = fs.readFileSync(path.join(__dirname, '../static/rsa-demo.js'), 'utf8');
function harness({supported = true, fetcher} = {}) {
  const elements = new Map(), events = {};
  const get = id => {
    if (!elements.has(id)) elements.set(id, {value:id === 'rsa-message' ? 'The exam is in Room 204.' : '', textContent:'', disabled:false, hidden:false, className:'', listeners:{}, addEventListener(name, fn){this.listeners[name] = fn;}});
    return elements.get(id);
  };
  const document = {body:{dataset:{task:'rsa'}}, getElementById:get, addEventListener(name, fn){events[name] = fn;}};
  const context = vm.createContext({document, crypto:supported ? webcrypto : undefined, TextEncoder, TextDecoder, Uint8Array, btoa, setTimeout, clearTimeout, AbortController, fetch:fetcher});
  vm.runInContext(source, context);
  return {get, document, events, click: id => get('rsa-' + id).listeners.click(), input: text => {get('rsa-message').value=text; get('rsa-message').listeners.input();}};
}
test('real encryption hides plaintext until matching-key decrypt; wrong private key fails', async () => {
  const h = harness();
  assert.equal(h.get('rsa-encrypt').disabled, true);
  await h.click('generate');
  assert.match(h.get('rsa-public').textContent, /BEGIN PUBLIC KEY/);
  assert.doesNotMatch(h.get('rsa-public').textContent, /PRIVATE KEY/);
  await h.click('encrypt');
  const encoded = h.get('rsa-ciphertext').value;
  assert.equal(Buffer.from(encoded, 'base64').length, 256);
  assert.doesNotMatch(h.get('rsa-recovered').textContent, /Room 204/);
  assert.equal(JSON.parse(h.get('rsa-technical-output').textContent).decrypted, false);
  await h.click('wrong');
  assert.match(h.get('rsa-wrong-result').textContent, /Rejected/);
  assert.doesNotMatch(h.get('rsa-recovered').textContent, /Room 204/);
  await h.click('decrypt');
  assert.equal(h.get('rsa-recovered').textContent, 'The exam is in Room 204.');
  assert.equal(JSON.parse(h.get('rsa-technical-output').textContent).recovery_matches, true);
  await h.click('encrypt');
  assert.notEqual(h.get('rsa-ciphertext').value, encoded, 'OAEP must randomize repeat encryption');
});
test('input edits, reset and navigation clear stale ciphertext and discarded keys cannot decrypt', async () => {
  const h = harness(); await h.click('generate'); await h.click('encrypt');
  h.input('New message');
  assert.equal(h.get('rsa-ciphertext').value, ''); assert.equal(h.get('rsa-decrypt').disabled, true);
  await h.click('encrypt'); await h.click('reset');
  assert.equal(h.get('rsa-encrypt').disabled, true); assert.equal(h.get('rsa-ciphertext').value, '');
  await h.click('generate'); await h.click('encrypt');
  h.document.body.dataset.task = 'classical'; h.events['enigma:navigate']();
  assert.equal(h.get('rsa-demo').hidden, true); assert.equal(h.get('rsa-ciphertext').value, '');
  h.document.body.dataset.task = 'rsa'; h.events['enigma:navigate']();
  assert.equal(h.get('rsa-demo').hidden, false); assert.equal(h.get('rsa-encrypt').disabled, true);
});
test('UTF-8 limits, exact Unicode recovery and empty input', async () => {
  const h = harness(); await h.click('generate');
  h.input('🙂'.repeat(48)); assert.equal(h.get('rsa-encrypt').disabled, true);
  await h.click('encrypt'); assert.equal(h.get('rsa-ciphertext').value, '');
  h.input('é'.repeat(95)); assert.equal(h.get('rsa-encrypt').disabled, false);
  await h.click('encrypt'); await h.click('decrypt'); assert.equal(h.get('rsa-recovered').textContent, 'é'.repeat(95));
  h.input(''); assert.equal(h.get('rsa-encrypt').disabled, true);
});
test('reset during key generation prevents stale async updates', async () => {
  const h = harness(); const pending = h.click('generate'); await h.click('reset'); await pending;
  assert.equal(h.get('rsa-encrypt').disabled, true);
  assert.equal(h.get('rsa-public').textContent, 'Generate keys first.');
});
test('unsupported crypto gives guidance and preserves Python fallback', () => {
  const h = harness({supported:false});
  assert.equal(h.get('rsa-generate').disabled, true);
  assert.equal(h.get('rsa-python').disabled, false);
  assert.match(h.get('rsa-status').textContent, /HTTPS or localhost/);
});
test('original Python self-test remains separate from Bob browser state', async () => {
  let request;
  const h = harness({fetcher:async (url, options) => {request={url, options}; return {ok:true, json:async () => ({task:'rsa', recovered:'The exam is in Room 204.', recovery_matches:true})};}});
  await h.click('python');
  assert.equal(request.url, '/api/tasks/rsa/run');
  assert.equal(JSON.parse(request.options.body).message, 'The exam is in Room 204.');
  assert.equal(h.get('rsa-ciphertext').value, ''); assert.equal(h.get('rsa-decrypt').disabled, true);
  assert.equal(JSON.parse(h.get('rsa-python-output').textContent).recovery_matches, true);
});
