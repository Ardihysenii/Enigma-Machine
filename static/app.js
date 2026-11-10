'use strict';
const tasks = [
  {id:'analysis',number:'01',phase:'PHASE I · FOUNDATIONS',title:'Security requirements',short:'Apply and test six server-enforced college security measures.',description:'Apply six real security controls and test student and professor permissions in the signed-in college portal.',icon:'<path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/><path d="m8 12 3 3 5-6"/>',requirements:['Identify the information and users/roles.','Describe at least three relevant threats.','Apply confidentiality, integrity and availability.','Identify evidence an IT auditor would inspect.'],next:'Build your group’s security analysis.',hint:'Start with fictional college assets and roles. Connect each threat to a control and the evidence that would demonstrate that control. The dashboard does not supply your assessed answers.',label:'Fictional scenario notes'},
  {id:'classical',number:'02',phase:'PHASE I · FOUNDATIONS',title:'Classical cipher',short:'Explore letter shifts and repeating keys with the teacher’s alphabet.',description:'Use Caesar or Vigenère to show the complete journey from plaintext to ciphertext and back.',icon:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h3m4 0h3M7 14h10"/>',requirements:['Implement Caesar OR Vigenère in Python or explained pseudocode.','Show original message, key, ciphertext and recovered plaintext.','Explain a weakness and why it is unsuitable for real records.','Compare key management with modern symmetric/asymmetric encryption.'],next:'Implement and explain one classical cipher.',hint:'Use A=0 through Z=25. Decide explicitly how to handle spaces, punctuation, lowercase and non-A–Z letters. Test the teacher’s examples and round-trip recovery.',label:'Fictional message'},
  {id:'rsa',number:'03',phase:'PHASE II · TRUST & VERIFICATION',title:'RSA encryption',short:'Explore public-key encryption and private-key recovery.',description:'Demonstrate RSA-OAEP on a short fictional message using an established cryptographic library.',icon:'<circle cx="8" cy="9" r="5"/><path d="m12 13 8 8m-5-5 3-3m0 6 3-3"/>',requirements:['Generate disposable RSA keys using an established library.','Encrypt a short message with the public key using OAEP.','Decrypt with the private key and verify exact recovery.','Explain both keys and justify key size; no textbook RSA.'],next:'Connect your group’s library-based RSA demonstration.',hint:'Keep private keys on the local Python side. Explain the short-message limit instead of treating RSA as a general arbitrary-file encryption system. Add actual recovery tests.',label:'Short fictional test message'},
  {id:'signatures',number:'04',phase:'PHASE II · TRUST & VERIFICATION',title:'Digital signatures',short:'Verify a document and reveal when its contents have changed.',description:'Use RSA-PSS with SHA-256 to demonstrate document signing and verification.',icon:'<path d="M14 3H5v18h14V8zM14 3v5h5M8 12h8M8 16h4"/>',requirements:['Sign a fictional document using RSA-PSS and SHA-256.','Verify successfully with the matching public key.','Test a modified document and an incorrect public key.','Explain signing vs encryption and the limits of claimed identity.'],next:'Write and test all three signature outcomes.',hint:'Never display a green verification result unless the library actually verified it. Document verification is not encryption and does not establish identity trust by itself.',label:'Fictional document text'},
  {id:'packaging',number:'05',phase:'PHASE III · KEYS & IDENTITY',title:'Keys & certificates',short:'Understand protected private keys and certificate packaging.',description:'Demonstrate encrypted PKCS #8 storage and protected PKCS #12 packaging.',icon:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',requirements:['Distinguish PKCS #1, #8, #11 and #12.','Demonstrate encrypted PKCS #8 private-key serialization.','Package a test key/certificate in password-protected PKCS #12.','Explain certificate limits, key protection, and show redacted evidence.'],next:'Implement local packaging with disposable laboratory material.',hint:'Do not put packaging passwords or private-key contents in this notes field. Your group will implement local secret handling and generate a test certificate. No keys or certificates exist in this scaffold.',label:'Non-secret packaging notes'},
  {id:'authentication',number:'06',phase:'PHASE III · KEYS & IDENTITY',title:'Token authentication',short:'Follow identification, a PIN check and a signed challenge.',description:'Demonstrate a clearly labeled smart-card simulation or lecturer-approved software token.',icon:'<rect x="3" y="5" width="18" height="14" rx="2"/><rect x="6" y="9" width="5" height="6" rx="1"/><path d="M15 10h3M15 14h2"/>',requirements:['Explain identification, PIN checking and private-key operation.','Verify a signed challenge; demonstrate success and failure.','Explain simulation vs real smart card and the purpose of PKCS #11.','Identify audit checks for key protection, access and audit records.'],next:'Build your group’s clearly labeled authentication simulation.',hint:'Use fictional identities and local disposable credentials. Generate fresh challenges and show actual success/failure. Do not enter a PIN in this notes field. Real hardware is not required.',label:'Non-secret authentication notes'}
];
const $ = id => document.getElementById(id);
let activeTask = null;
let requestController = null;
$('task-cards').innerHTML = tasks.map(t => `<a class="task-card" href="#${t.id}"><div class="card-top"><span class="task-icon"><svg viewBox="0 0 24 24" aria-hidden="true">${t.icon}</svg></span><span class="card-number">/ ${t.number}</span></div><p class="card-phase">${t.phase}</p><h3>${t.title}</h3><p class="description">${t.short}</p><div class="card-bottom"><span class="card-status">● &nbsp; Ready to run</span><span class="card-arrow" aria-hidden="true">↗</span></div></a>`).join('');
$('alphabet').innerHTML = Array.from({length:26},(_,i)=>`<div>${String.fromCharCode(65+i)}<small>${i}</small></div>`).join('');
function clearResult(){
  window.enigmaCipher?.reset();
  $('result').textContent='Run this task to display actual Python results.';
  $('result').className='result';
  $('response-status').textContent='Not run';
}
function navigate(){
  window.enigmaCipher?.pause();
  if(requestController) requestController.abort();
  const id=location.hash.slice(1)||'overview';
  activeTask=tasks.find(t=>t.id===id)||null;
  document.querySelectorAll('.nav-item').forEach(a=>{
    const selected=a.hash==='#'+(activeTask?activeTask.id:'overview');
    a.classList.toggle('active',selected);
    if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
  });
  $('overview').hidden=Boolean(activeTask);$('task-view').hidden=!activeTask;
  document.body.dataset.task=activeTask?.id||'overview';
  $('cipher-stage').hidden=activeTask?.id!=='classical';
  document.querySelector('.requirements').hidden=activeTask?.id==='classical';
  document.querySelector('.workspace-grid').classList.toggle('classical-grid',activeTask?.id==='classical');
  document.dispatchEvent(new CustomEvent('enigma:navigate',{detail:{id:activeTask?.id||'overview'}}));
  $('breadcrumb').textContent=activeTask?activeTask.title:'Overview';
  document.title=`ENIGMA — ${activeTask?activeTask.title:'Cryptography laboratory'}`;
  if(activeTask){
    const t=activeTask;
    $('task-phase').textContent=`TASK ${t.number} / ${t.phase}`;
    $('task-title').textContent=t.title;$('task-description').textContent=t.description;
    $('workspace-number').textContent=t.number;$('message-label').textContent=t.label;
    $('requirements-list').replaceChildren(...t.requirements.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
    $('next-title').textContent=t.next;$('next-description').textContent=t.hint;
    $('classical-options').hidden=t.id!=='classical';$('alphabet-panel').hidden=t.id!=='classical';
    document.querySelector('.workspace-grid').hidden=t.id==='analysis';
    document.querySelector('.next-step').hidden=t.id==='analysis';
    $('task-form').reset();configureTask(t.id);$('character-count').textContent='0 / 2000';clearResult();
    $('run-button').disabled=false;
  }
}
window.addEventListener('hashchange',navigate);navigate();
$('message').addEventListener('input',()=>{$('character-count').textContent=`${$('message').value.length} / 2000`;});
$('clear-button').addEventListener('click',()=>{if(requestController)requestController.abort();$('task-form').reset();configureTask(activeTask.id);$('character-count').textContent='0 / 2000';clearResult();$('run-button').disabled=false;});
$('task-form').addEventListener('submit',async event=>{
  event.preventDefault();if(!activeTask)return;
  const taskId=activeTask.id;
  const controller=new AbortController();requestController=controller;
  if(taskId==='classical')window.enigmaCipher?.pending();
  $('run-button').disabled=true;$('response-status').textContent='Contacting Python…';
  const timer=setTimeout(()=>controller.abort(),10000);
  try{
    const response=await fetch(`/api/tasks/${taskId}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collectPayload(taskId)),signal:controller.signal});
    const data=await response.json();
    if(!activeTask||activeTask.id!==taskId||controller.signal.aborted)return;
    renderResult(data,taskId);
    if(taskId==='classical'){if(response.ok)window.enigmaCipher?.render(data);else window.enigmaCipher?.fail();}
    $('result').className='result'+(!response.ok?' error':'');
    $('response-status').textContent=!response.ok?`HTTP ${response.status}`:data.authenticated===false?'Authentication rejected':'Completed locally';
  }catch(error){
    if(controller.signal.aborted)return;
    $('result').textContent='The local Python server is unavailable. Open Start ENIGMA.cmd in the project folder, keep its window open, then retry.';
    void checkHealth();
    $('result').className='result error';$('response-status').textContent='Connection failed';
  }finally{
    clearTimeout(timer);
    if(requestController===controller){requestController=null;$('run-button').disabled=false;
      if(controller.signal.aborted&&activeTask?.id===taskId&&$('response-status').textContent==='Contacting Python…'){
        if(taskId==='classical')window.enigmaCipher?.fail();
        $('response-status').textContent='Request cancelled or timed out';$('result').textContent='No result received. You can retry the operation.';void checkHealth();
      }
    }
  }
});
async function checkHealth(){
  try{
    const response=await fetch('/api/health',{signal:AbortSignal.timeout(8000)});const data=await response.json();
    if(!response.ok||data.status!=='ok')throw new Error('Unexpected health response');
    if(data.cryptography_implemented!==true){
      $('connection').textContent='○ Older server · restart Start ENIGMA.cmd';$('connection').className='connection offline';return;
    }
    $('connection').textContent='● Python connected · local';$('connection').className='connection online';
  }catch{
    $('connection').textContent='○ Python disconnected';$('connection').className='connection offline';
  }
}
checkHealth();
setInterval(() => { if (!document.hidden) void checkHealth(); }, 10000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) void checkHealth(); });
window.addEventListener('focus', () => void checkHealth());

function field(id,label,{type='text',value='',placeholder='',rows=3}={}){
  const box=document.createElement('div');
  const caption=document.createElement('label');caption.htmlFor=id;caption.textContent=label;
  const input=document.createElement(type==='textarea'?'textarea':'input');input.id=id;input.name=id;
  if(type!=='textarea')input.type=type;else input.rows=rows;
  input.maxLength=type==='password'?128:2000;input.value=value;input.placeholder=placeholder;
  if(type==='password')input.autocomplete='new-password';
  box.append(caption,input);return box;
}
function choice(id,label,options){
  const box=document.createElement('div');const caption=document.createElement('label');caption.htmlFor=id;caption.textContent=label;
  const select=document.createElement('select');select.id=id;
  options.forEach(([value,text])=>{const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);});
  box.append(caption,select);return box;
}
function configureTask(id){
  let fields=$('task-fields');
  if(!fields){fields=document.createElement('div');fields.id='task-fields';$('task-form').insertBefore(fields,document.querySelector('.form-actions'));}
  fields.replaceChildren();
  const hasMessage=['classical','rsa','signatures'].includes(id);
  $('message').hidden=!hasMessage;$('message-label').hidden=!hasMessage;
  document.querySelector('.field-meta').hidden=!hasMessage;
  $('run-button').replaceChildren(document.createTextNode('Run operation →'));
  document.querySelector('.task-heading .pill').textContent='Local laboratory';
  if(id==='classical')fields.append(field('key','Key (Caesar: integer; Vigenère: A–Z letters)',{value:'3'}));
  // Task 01 now uses the direct security panel; legacy saved analyses stay on disk.
  if(id==='packaging')fields.append(field('password','Disposable laboratory password (12–128 characters)',{type:'password'}));
  if(id==='authentication'){
    fields.append(choice('action','Operation',[['enroll','1. Enroll disposable simulated token'],['challenge','2. Issue fresh 60-second challenge'],['authenticate','3. Authenticate / consume challenge'],['audit','View session audit records']]));
    fields.append(field('identity','Fictional identity',{placeholder:'e.g. lab-student'}));
    fields.append(field('pin','Disposable laboratory PIN (4–12 digits)',{type:'password'}));
    fields.append(choice('test','Signature check',[['normal','Normal verification'],['altered','Test altered challenge'],['wrong_key','Test wrong public key']]));
  }
  const notes={analysis:'Complete the structured analysis and save it locally. Load restores the saved fields in this browser session.',classical:'Enter a key and choose encrypt or decrypt. ASCII letters become uppercase; punctuation and other characters are preserved.',rsa:'Run a short-message RSA-OAEP round trip with disposable keys. Maximum 190 UTF-8 bytes.',signatures:'Sign the document, then check original, altered-document and wrong-public-key outcomes.',packaging:'Use a disposable password. Download encrypted PKCS #8, PKCS #12 and a self-signed test certificate. Private keys never appear in the response.',authentication:'Software simulation only: enroll once, issue a challenge, then authenticate. Request a new challenge before every success/failure test. Five consecutive failures lock the token.'};
  $('next-title').textContent='How to run this task';$('next-description').textContent=notes[id];
}
function collectPayload(id){
  const payload={message:$('message').value,cipher:$('cipher').value,operation:$('operation').value};
  for(const input of $('task-fields').querySelectorAll('input,select,textarea'))payload[input.id]=input.value;
  // Do not accidentally send another task's message or retain credentials after submission.
  if(!['classical','rsa','signatures'].includes(id))delete payload.message;
  for(const key of ['password','pin'])if($(key))$(key).value='';
  return payload;
}
function renderResult(data,id){
  const result=$('result');result.replaceChildren();
  if(data.error){result.textContent=data.error;return;}
  if(id==='analysis'&&data.analysis)for(const [key,value]of Object.entries(data.analysis))if($(key))$(key).value=value;
  if(id==='classical'){
    const label=document.createElement('span');label.className='result-label';label.textContent=data.operation==='decrypt'?'RECOVERED PLAINTEXT':'CIPHERTEXT';
    const output=document.createElement('p');output.className='compact-output';output.textContent=data.output||'(empty message)';
    const note=document.createElement('p');note.className='result-note';note.textContent='Python completed this operation. Follow the signal path and calculation table for the explanation.';
    result.append(label,output,note);return;
  }
  const visible={...data};delete visible.downloads;
  const pre=document.createElement('pre');pre.textContent=JSON.stringify(visible,null,2);pre.style.whiteSpace='pre-wrap';pre.style.overflowWrap='anywhere';result.append(pre);
  if(data.downloads)for(const [name,url]of Object.entries(data.downloads)){
    const a=document.createElement('a');a.textContent='Download '+name;a.href=url;a.className='text-link';a.download=name;
    result.append(a,document.createElement('br'));
  }
}
