const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const test=require('node:test'),assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'../static/course-notices.js'),'utf8');
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function harness(role='professor'){
 const nodes=new Map(),events={},requests=[];let account=role;const courses=[{id:'course-1',code:'SEC101',title:'Security'}];let saved=null,publishCount=0,timeoutNext=false;
 const ctx={clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){}};
 function node(id=''){return {id,value:'',textContent:'',hidden:false,disabled:false,className:'',children:[],listeners:{},get options(){return this.children;},getContext:()=>ctx,getBoundingClientRect:()=>({left:0,top:0,width:800,height:240}),setPointerCapture(){},addEventListener(n,fn){this.listeners[n]=fn;},replaceChildren(...items){this.children=items;if(id==='cn-course'||id==='cn-filter')this.value=items[0]?.value||'';},append(...items){this.children.push(...items);}};}
 function get(id){if(['notices-view','dashboard-view'].includes(id))return null;if(!nodes.has(id))nodes.set(id,node(id));return nodes.get(id);}
 const document={body:{dataset:{task:'signatures'}},hidden:false,getElementById:get,createElement:()=>node(),addEventListener(n,fn){events[n]=fn;}};
 const response=(data,ok=true,status=200)=>({ok,status,json:async()=>structuredClone(data)});
 const fetcher=async(url,options={})=>{
  if(url.endsWith('/session'))return response({actor:account?{id:'user-1',name:'Fictional User',role:account}:null,csrfToken:'a'.repeat(43)});
  requests.push({url,options,body:options.body?JSON.parse(options.body):null});
  if(url.endsWith('/notices/courses'))return response({courses});
  if(url.includes('/notices?')||url.endsWith('/notices')&&options.method==='GET')return response({notices:saved?[saved]:[]});
  if(url.endsWith('/notices')&&options.method==='POST'){
   const b=JSON.parse(options.body);publishCount++;
   saved={id:'notice-1',courseId:b.courseId,courseCode:'SEC101',teacherName:'Teacher',publishedAt:'2026-11-18T19:00:00Z',title:b.title,payload:b.payload,signature:'test-signature',publicKey:'test-public',publicKeyFingerprint:'test-fingerprint',algorithm:'RSA-PSS / SHA-256'};
   if(timeoutNext){timeoutNext=false;throw Error('Network response lost');}return response({notice:saved});
  }
  if(url.endsWith('/verify')){const b=JSON.parse(options.body);return response({verified:b.test==='original'||b.test==='current'&&JSON.stringify(b.payload)===JSON.stringify(saved.payload),identityTrusted:false});}
  return response({notice:saved});
 };
 vm.runInNewContext(source,{document,window:{addEventListener(){}},fetch:fetcher,crypto:webcrypto,AbortSignal,setInterval(){},JSON,Math,Date,encodeURIComponent});
 return{get,document,events,requests,click:id=>get('cn-'+id).listeners.click(),setRole:r=>account=r,get saved(){return saved;},get publishCount(){return publishCount;},timeout:()=>timeoutNext=true};
}
async function ready(h){await settle();await settle();}
async function publish(h){h.get('cn-title').value='Exam notice';h.click('sample');await h.click('publish');}
test('teacher publishes course notice; original stays unchecked until explicit verify',async()=>{
 const h=harness();await ready(h);assert.equal(h.get('cn-compose').hidden,false);await publish(h);
 assert.equal(h.saved.payload.drawing.length,1);assert.equal(h.get('cn-reader').hidden,false);assert.match(h.get('cn-check-state').textContent,/Not checked/);
 const r=h.requests.find(r=>r.options.method==='POST'&&r.url.endsWith('/notices'));assert.equal(r.options.headers['X-CSRF-Token'],'a'.repeat(43));assert.match(r.body.requestId,/^[0-9a-f-]{36}$/);
 await h.click('verify');assert.match(h.get('cn-check-state').textContent,/^VALID/);
 h.click('tamper');await h.click('test');assert.match(h.get('cn-test-state').textContent,/^INVALID/);assert.match(h.saved.payload.document,/10:00/);
 h.click('restore');await h.click('test');assert.match(h.get('cn-test-state').textContent,/^VALID/);
 h.click('change-drawing');await h.click('test');assert.match(h.get('cn-test-state').textContent,/^INVALID/);
 await h.click('wrong');assert.match(h.get('cn-check-state').textContent,/^INVALID/);
});
test('students cannot compose, admins and anonymous cannot access notices',async()=>{
 for(const role of ['student','admin',null]){const h=harness(role);await ready(h);assert.equal(h.get('cn-compose').hidden,true);assert.equal(h.get('cn-content').hidden,role!=='student');}
});
test('network loss preserves request ID when teacher retries unchanged publish',async()=>{
 const h=harness();await ready(h);h.get('cn-title').value='Notice';h.click('sample');h.timeout();await h.click('publish');await h.click('publish');
 const posts=h.requests.filter(r=>r.options.method==='POST'&&r.url.endsWith('/notices'));assert.equal(posts.length,2);assert.equal(posts[0].body.requestId,posts[1].body.requestId);
});
test('sign-out clears saved content from the page; navigation clears private working copies',async()=>{
 const h=harness();await ready(h);await publish(h);h.setRole(null);await h.click('recheck');assert.equal(h.get('cn-content').hidden,true);assert.equal(h.get('cn-original-text').textContent,'');
 h.document.body.dataset.task='rsa';h.events['enigma:navigate']();assert.equal(h.get('cn-workspace').hidden,true);
});
test('touchpad strokes become part of the published drawing',async()=>{
 const h=harness();await ready(h);h.get('cn-title').value='Notice';const p=h.get('cn-pad'),e=(x,y)=>({pointerType:'mouse',button:0,pointerId:1,clientX:x,clientY:y,preventDefault(){}});
 p.listeners.pointerdown(e(20,30));p.listeners.pointermove(e(90,100));p.listeners.pointerup(e(90,100));await h.click('publish');assert.deepEqual(h.saved.payload.drawing,[[[20,30],[90,100]]]);
});
