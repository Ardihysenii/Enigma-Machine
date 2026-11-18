const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const test=require('node:test'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../static/teacher-signatures.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function harness(role='professor'){
 const nodes=new Map(),events={},requests=[];let signed=null,sessionRole=role;
 const ctx={clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){}};
 function get(id){if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,disabled:false,className:'',listeners:{},getContext:()=>ctx,getBoundingClientRect:()=>({left:0,top:0,width:800,height:240}),setPointerCapture(){},addEventListener(n,fn){this.listeners[n]=fn;}});return nodes.get(id);}
 const document={body:{dataset:{task:'signatures'}},hidden:false,getElementById:get,addEventListener(n,fn){events[n]=fn;}};
 const fetcher=async(url,options)=>{
  if(url.endsWith('/session'))return{ok:true,json:async()=>({actor:sessionRole?{id:'teacher-1',name:'Teacher',role:sessionRole}:null,csrfToken:'a'.repeat(43)})};
  const data=JSON.parse(options.body);requests.push({url,data,headers:options.headers});
  if(url.endsWith('/sign')){signed=structuredClone(data.payload);return{ok:true,json:async()=>({payload:signed,signature:'demo-signature',publicKey:'demo-public-key',algorithm:'RSA-PSS / SHA-256'})};}
  return{ok:true,json:async()=>({verified:data.test==='normal'&&JSON.stringify(data.payload)===JSON.stringify(signed)})};
 };
 vm.runInNewContext(source,{document,window:{addEventListener(){}},fetch:fetcher,AbortSignal,setInterval(){},JSON,Math});
 return{get,document,events,requests,setRole:r=>sessionRole=r,click:id=>get('ts-'+id).listeners.click()};
}
test('only teacher session reveals tools; students and administrators remain locked',async()=>{
 for(const role of ['professor','student','admin',null]){const h=harness(role);await settle();assert.equal(h.get('ts-tools').hidden,role!=='professor');}
});
test('sign uses CSRF, original snapshot is preserved, edits fail and restore succeeds',async()=>{
 const h=harness();await settle();h.click('sample');await h.click('sign');
 assert.equal(h.requests[0].headers['X-CSRF-Token'],'a'.repeat(43));
 assert.ok(h.requests[0].data.payload.drawing.length>0);
 await h.click('original');assert.match(h.get('ts-verdict').textContent,/VALID —/);
 h.click('tamper');await h.click('current');assert.match(h.get('ts-verdict').textContent,/INVALID/);
 await h.click('original');assert.match(h.get('ts-verdict').textContent,/VALID —/);
 await h.click('wrong');assert.match(h.get('ts-verdict').textContent,/INVALID/);
 h.click('restore');await h.click('current');assert.match(h.get('ts-verdict').textContent,/VALID —/);
 h.click('clear');await h.click('current');assert.match(h.get('ts-verdict').textContent,/INVALID/);
});
test('touchpad pointer strokes are included in signed payload',async()=>{
 const h=harness();await settle();const p=h.get('ts-pad');
 const event=(x,y)=>({clientX:x,clientY:y,pointerId:1,pointerType:'mouse',button:0,preventDefault(){}});
 p.listeners.pointerdown(event(20,30));p.listeners.pointermove(event(60,80));p.listeners.pointerup(event(60,80));
 await h.click('sign');assert.deepEqual(h.requests[0].data.payload.drawing,[[[20,30],[60,80]]]);
});
test('detected sign-out and leaving section clear drawing and evidence',async()=>{
 const h=harness();await settle();h.click('sample');await h.click('sign');
 h.setRole(null);await h.click('recheck');assert.equal(h.get('ts-tools').hidden,true);assert.equal(h.get('ts-evidence').textContent,'No signature yet.');
 h.document.body.dataset.task='rsa';h.events['enigma:navigate']();assert.equal(h.get('ts-workspace').hidden,true);
});
