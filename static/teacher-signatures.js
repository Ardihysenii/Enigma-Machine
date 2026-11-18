(() => {
  'use strict';
  const el = id => document.getElementById('ts-' + id);
  if (!el('workspace')) return;
  const pad = el('pad'), ctx = pad.getContext('2d');
  let actor = null, csrf = '', strokes = [], stroke = null, bundle = null, busy = false, epoch = 0;
  const active = () => document.body.dataset.task === 'signatures';
  const clone = value => JSON.parse(JSON.stringify(value));
  const payload = () => ({version:1, document:el('document').value, drawing:clone(strokes)});
  function status(value) { el('status').textContent = value; }
  function controls() {
    el('tools').hidden = !actor; el('gate').hidden = Boolean(actor);
    ['sign','clear','sample','tamper','restore','original','current','wrong'].forEach(id => {
      el(id).disabled = !actor || busy || (['tamper','restore','original','current','wrong'].includes(id) && !bundle);
    });
    el('document').disabled = busy;
  }
  function draw() {
    ctx.clearRect(0,0,800,240); ctx.strokeStyle='#20252a'; ctx.lineWidth=3; ctx.lineCap='round'; ctx.lineJoin='round';
    for (const line of strokes) {
      if (!line.length) continue;
      ctx.beginPath(); ctx.moveTo(...line[0]); for (const p of line.slice(1)) ctx.lineTo(...p); ctx.stroke();
    }
  }
  function changed() {
    el('verdict').textContent = bundle ? 'Working copy changed. Verify the current copy to check it against the existing signature.' : 'Draw a fictional signature, then click Sign.';
    el('verdict').className = '';
  }
  function clearWorkingCopy() {
    epoch++; busy=false; actor=null; csrf=''; strokes=[]; stroke=null; bundle=null;
    el('document').value='College notice: The exam starts at 10:00 in Room 204.';
    el('signed-state').textContent='Sign a document first. Editing later does not automatically sign it again.';
    el('evidence').textContent='No signature yet.'; el('verdict').textContent='No verification yet.'; el('verdict').className=''; draw(); controls();
  }
  function lock(message) { clearWorkingCopy(); status(message); }
  function finishStroke(event) {
    if (!stroke || (event && event.pointerId !== stroke.pointerId)) return;
    if (stroke.points.length < 2) strokes = strokes.filter(s => s !== stroke.points);
    stroke=null; draw(); changed();
  }
  function point(event) {
    const r=pad.getBoundingClientRect();
    return [Math.round(Math.max(0,Math.min(800,(event.clientX-r.left)*800/r.width))*10)/10,
      Math.round(Math.max(0,Math.min(240,(event.clientY-r.top)*240/r.height))*10)/10];
  }
  pad.addEventListener('pointerdown', event => {
    if (!actor || busy || stroke || (event.pointerType==='mouse' && event.button!==0)) return;
    if (strokes.length>=40 || strokes.flat().length>=800) {status('Drawing limit reached. Clear the pad or use the sample doodle.');return;}
    event.preventDefault(); const points=[point(event)]; strokes.push(points); stroke={pointerId:event.pointerId,points}; pad.setPointerCapture(event.pointerId); changed();
  });
  pad.addEventListener('pointermove', event => {
    if (!stroke || stroke.pointerId!==event.pointerId || busy) return;
    event.preventDefault(); if(strokes.flat().length>=800){finishStroke(event);status('Drawing limit reached; you can sign now.');return;}
    const p=point(event), last=stroke.points[stroke.points.length-1];
    if(Math.hypot(p[0]-last[0],p[1]-last[1])<2)return;
    stroke.points.push(p); draw();
  });
  ['pointerup','pointercancel','lostpointercapture'].forEach(name=>pad.addEventListener(name,finishStroke));
  el('clear').addEventListener('click',()=>{if(busy)return;strokes=[];stroke=null;draw();changed();});
  el('sample').addEventListener('click',()=>{if(busy)return;strokes=[[[90,160],[130,60],[145,150],[190,95],[220,155],[270,80],[300,150],[355,110],[400,140],[520,120],[670,145]]];stroke=null;draw();changed();});
  el('document').addEventListener('input',changed);
  el('tamper').addEventListener('click',()=>{
    if(!bundle||busy)return;
    const text=el('document').value;
    el('document').value=text.includes('10:00')?text.replace('10:00','12:00'):text.slice(0,1980)+' [modified]';changed();
  });
  el('restore').addEventListener('click',()=>{
    if(!bundle||busy)return;el('document').value=bundle.payload.document;strokes=clone(bundle.payload.drawing);stroke=null;draw();changed();status('Original text and drawing restored. Verify the current copy again.');
  });
  async function session() {
    if(!active()||busy)return;
    const version=epoch;
    try {
      const response=await fetch('/api/portal/session',{credentials:'same-origin',cache:'no-store'}), data=await response.json();
      if(version!==epoch||!active())return;
      if(!response.ok)throw Error(data.error||'Cannot check your account.');
      if(!data.actor||data.actor.role!=='professor'){lock('Teacher accounts only. Sign in at College, then return here.');return;}
      if(actor && actor.id!==data.actor.id)clearWorkingCopy();
      actor=data.actor;csrf=data.csrfToken;controls();status('Teacher: '+actor.name+'. Use a fictional document and made-up signature.');
    } catch(error){if(version===epoch&&active())lock('Account check failed. Sign in at College or retry.');}
  }
  async function api(path, body) {
    const response=await fetch('/api/portal/signatures/'+path,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
    const data=await response.json();
    if(!response.ok){if([401,403].includes(response.status))lock('Teacher access ended or the security check failed. Sign in and check your account again.');throw Error(data.error||'Request failed.');}
    return data;
  }
  async function run(action) {
    if(busy||!actor||!active())return;
    finishStroke();busy=true;controls();const version=epoch;
    try {await action(()=>version===epoch&&active());}
    catch(error){if(version===epoch&&active()){if(!bundle){el('signed-state').textContent='No signature created. Check the text and drawing, then retry.';el('evidence').textContent='No signature yet.';}status(error.name==='TimeoutError'?'Request timed out. Retry when connected.':error.message);}}
    finally{if(version===epoch){busy=false;controls();}}
  }
  el('sign').addEventListener('click',()=>run(async current=>{
    // Do not allow a failed replacement signing request to leave an old signature looking new.
    bundle=null;el('evidence').textContent='Signing…';el('signed-state').textContent='Signing current text and drawing…';el('verdict').textContent='No verification yet.';controls();
    status('Signing with a fresh disposable RSA private key…');
    const data=await api('sign',{payload:payload()});if(!current())return;
    bundle=data;el('evidence').textContent=JSON.stringify({algorithm:data.algorithm,signature:data.signature,publicKey:data.publicKey,publicKeyFingerprint:data.publicKeyFingerprint},null,2);
    el('signed-state').textContent='Signed by the current teacher session. The private key was discarded; verify with the returned public key.';
    status('Text and drawing signed. Now verify the original, or edit a copy to test tampering.');
  }));
  async function verify(mode) {
    return run(async current=>{
      if(!bundle)throw Error('Sign a document first.');
      status('Verifying the document and drawing…');
      const currentPayload=mode==='current'?payload():clone(bundle.payload);
      const data=await api('verify',{payload:currentPayload,signature:bundle.signature,publicKey:bundle.publicKey,test:mode==='wrong'?'wrong_key':'normal'});
      if(!current())return;
      const label=mode==='current'?'Current copy':mode==='wrong'?'Original with unrelated public key':'Signed original';
      el('verdict').textContent=label+': '+(data.verified?'VALID — exact content matches this signature and public key.':'INVALID — content or public key does not match the signature.');
      el('verdict').className=data.verified?'ts-valid':'ts-invalid';status('Verification finished. This does not independently establish the signer’s real identity.');
    });
  }
  ['original','current','wrong'].forEach(mode=>el(mode).addEventListener('click',()=>verify(mode)));
  el('recheck').addEventListener('click',session);
  function navigate(){el('workspace').hidden=!active();if(!active())clearWorkingCopy();else void session();}
  document.addEventListener('enigma:navigate',navigate);
  window.addEventListener('focus',()=>{void session();});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)void session();});
  setInterval(()=>{if(!document.hidden)void session();},15000);
  clearWorkingCopy();navigate();
})();
