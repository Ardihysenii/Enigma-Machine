const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/portal.js'), 'utf8');
const authTab = source.slice(source.indexOf('  function authTab('), source.indexOf("  ['signin', 'signup'].forEach((name)"));
const pending = source.slice(source.indexOf('  function showPendingToken('), source.indexOf("  $('token-back').addEventListener"));
function harness() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {hidden:false, value:'old-secret', textContent:'', attrs:{}, focused:false,
      setAttribute(key,value){this.attrs[key]=value;}, focus(){this.focused=true;}, scrollIntoView(){}, querySelector(){return {textContent:''};}});
    return elements.get(id);
  }
  const ctx = vm.createContext({$:element, state:{csrf:''}, clearPrivateData(){}, notice(){}, showTop(){}, message(){}, document:{querySelector(){return element('tabs');}}});
  vm.runInContext('let pendingTokenStatus=null;\n'+authTab+'\n'+pending, ctx);
  return {ctx, element};
}
for (const status of ['not_enrolled', 'active']) {
  test(status + ': only token step visible after credentials', () => {
    const {ctx,element:e}=harness();
    ctx.showPendingToken({tokenStatus:status,csrfToken:'test-csrf',pendingActor:{name:'Fictional Student',email:'student@example.test'}});
    assert.equal(e('signin-panel').hidden,true);
    assert.equal(e('signup-panel').hidden,true);
    assert.equal(e('tabs').hidden,true);
    assert.equal(e('token-step').hidden,false);
    assert.equal(e('token-login-form').hidden,false);
    assert.equal(e('login-pin').value,'');
    assert.equal(e('login-pin').focused,true);
    assert.match(e('token-account').textContent,/student@example.test/);
    assert.match(e('token-step-title').textContent,status==='active'?/Verify/:/Set up/);
  });
}
test('return to sign in restores inputs and removes stale PIN',()=>{
  const {ctx,element:e}=harness();
  ctx.showPendingToken({tokenStatus:'active'});
  e('login-pin').value='temporary';
  ctx.authTab('signin');
  assert.equal(e('tabs').hidden,false);
  assert.equal(e('signin-panel').hidden,false);
  assert.equal(e('signup-panel').hidden,true);
  assert.equal(e('token-step').hidden,true);
  assert.equal(e('login-pin').value,'');
  ctx.authTab('signup');
  assert.equal(e('signup-panel').hidden,false);
  assert.equal(e('signin-panel').hidden,true);
});
test('locked token shows recovery guidance instead of a futile PIN form',()=>{
  const {ctx,element:e}=harness();
  ctx.showPendingToken({tokenStatus:'locked'});
  assert.equal(e('token-login-form').hidden,true);
  assert.match(e('token-step-description').textContent,/administrator/);
  assert.equal(e('token-step-title').focused,true);
});
