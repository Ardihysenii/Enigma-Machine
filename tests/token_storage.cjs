const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/portal.js'), 'utf8');
const sync = source.slice(source.indexOf('  function syncDemoToken('), source.indexOf('  function clearPrivateData('));
function harness(blocked = false) {
  const values = new Map();
  const ctx = vm.createContext({localStorage: {
    setItem(k, v) { if (blocked) throw Error('blocked'); values.set(k, v); },
    removeItem(k) { if (blocked) throw Error('blocked'); values.delete(k); }
  }});
  vm.runInContext(sync, ctx);
  return {values, sync: data => ctx.syncDemoToken(data)};
}
test('login saves exact digits as string; refresh and next login restore same ID', () => {
  const h = harness();
  const data = {actor: {id: 'student'}, tokenId: '1234567890123456789012345678901234567890'};
  h.sync(data); assert.equal(h.values.get('enigma_token_id'), data.tokenId);
  h.sync(data); assert.equal(h.values.get('enigma_token_id'), data.tokenId);
  h.sync(null); assert.equal(h.values.size, 0);
  h.sync(data); assert.equal(h.values.get('enigma_token_id'), data.tokenId);
});
test('pending, anonymous, unenrolled and invalid responses clear stale identifier', () => {
  const h = harness();
  for (const data of [null, {actor:null, tokenId:'123'}, {pending:true}, {actor:{}}, {actor:{},tokenId:123}, {actor:{},tokenId:'secret-key'}]) {
    h.sync({actor:{}, tokenId:'123'}); h.sync(data); assert.equal(h.values.size, 0);
  }
});
test('blocked storage never interrupts authentication', () => {
  const h = harness(true);
  assert.doesNotThrow(() => h.sync({actor:{}, tokenId:'123'}));
  assert.doesNotThrow(() => h.sync(null));
});
test('all successful authentication paths sync; private-data cleanup removes identifier', () => {
  assert.match(source, /state.actor = data.actor; state.csrf = data.csrfToken; syncDemoToken\(data\)/);
  assert.match(source, /state.actor=data.actor;state.csrf=data.csrfToken;syncDemoToken\(data\)/);
  assert.match(source, /clearPrivateData\(\); syncDemoToken\(data\); state.csrf/);
  assert.match(source, /function clearPrivateData\(\) \{\s*syncDemoToken\(null\)/);
  assert.match(source, /await api\('\/signout', \{\}\); clearPrivateData\(\)/);
});
