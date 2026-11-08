'use strict';
(()=>{
  const get=id=>document.getElementById(id);
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)');
  let result=null,index=0,phase=0,playing=false,timer=null,stale=false;
  const rows=[],inputTokens=[],outputTokens=[];
  const controls=['trace-prev','trace-play','trace-next','trace-replay'];
  function setText(id,text){get(id).textContent=text;}
  function stop(){if(playing)state('PAUSED');clearTimeout(timer);timer=null;playing=false;get('cipher-stage').classList.remove('running');setText('trace-play','Play walkthrough');}
  function state(text){setText('machine-state',text);}
  function phaseUI(value){document.querySelectorAll('.signal-route li').forEach((node,i)=>{node.classList.toggle('active',i===value);node.classList.toggle('done',i<value);});}
  function enable(on){for(const id of controls)get(id).disabled=!on;}
  function reset(){
    stop();result=null;stale=false;index=0;phase=0;rows.length=0;inputTokens.length=0;outputTokens.length=0;
    get('cipher-evidence').hidden=true;get('cipher-stale').hidden=true;get('cipher-calculation-body').replaceChildren();
    for(const id of ['trace-input','trace-value','trace-key','trace-output','trace-output-value'])setText(id,'—');
    setText('trace-key-detail','AWAITING RUN');setText('trace-equation','A = 0 · B = 1 · … · Z = 25');
    setText('trace-progress-label','No operation yet');get('trace-progress').value=0;get('trace-progress').max=1;
    state('AWAITING INPUT');phaseUI(0);enable(false);
    setText('cipher-narration','Enter a message and run the cipher. Python calculates the result; this panel then explains each letter using those exact calculations.');
    document.querySelectorAll('#alphabet > div').forEach(node=>node.classList.remove('input-active','output-active'));
  }
  function markStale(){
    if(!result)return;stop();stale=true;get('cipher-stale').hidden=false;state('INPUTS CHANGED');enable(false);
    setText('cipher-narration','Your inputs changed. The evidence below is from the previous run; run the cipher again before presenting the new settings.');
  }
  function keyDescription(step){
    if(result.cipher==='vigenere'){
      const key=result.key.toUpperCase(),letter=key[index%key.length];
      return `Vigenère key letter ${letter} gives shift ${step.key}. The key advances only for A–Z letters.`;
    }
    return `The Caesar key ${result.key} is normalized to shift ${step.key} modulo 26.`;
  }
  function narration(step,p){
    const direction=result.operation==='decrypt'?'subtract':'add';
    if(p===0)return `Read letter ${index+1} of ${result.steps.length}: ${step.input}. ASCII letters are normalized to uppercase; spaces, punctuation and non-ASCII characters are preserved.`;
    if(p===1)return `Map ${step.input} to ${step.value} using A = 0 through Z = 25. ${keyDescription(step)}`;
    if(p===2)return `To ${result.operation}, ${direction} shift ${step.key}. ${step.calculation}. Modulo 26 wraps the value back into the alphabet, including negative results.`;
    return `Map index ${step.output.charCodeAt(0)-65} back to ${step.output}. Python emitted ${step.output}; the full output is shown below. ${index===result.steps.length-1?'The next stage checks the inverse operation.':'Continue to the next letter.'}`;
  }
  function draw(p=3){
    if(!result||!result.steps.length||stale)return;
    const step=result.steps[index];phase=p;phaseUI(p);
    setText('trace-input',step.input);setText('trace-value',p>=1?String(step.value):'A–Z');
    setText('trace-key',(result.operation==='decrypt'?'−':'+')+step.key);
    setText('trace-key-detail',result.cipher==='vigenere'?'KEY '+result.key.toUpperCase()[index%result.key.length]:'CAESAR');
    setText('trace-output',p>=3?step.output:'?');setText('trace-output-value',p>=3?String(step.output.charCodeAt(0)-65):'A–Z');
    setText('trace-equation',p>=2?step.calculation:'A = 0 · … · Z = 25');
    setText('cipher-narration',narration(step,p));
    state(playing?'SIGNAL IN MOTION':'LETTER '+(index+1));
    setText('trace-progress-label',`Letter ${index+1} / ${result.steps.length} · ${result.cipher==='vigenere'?'Vigenère':'Caesar'} · ${result.operation}`);
    get('trace-progress').max=result.steps.length;get('trace-progress').value=index+1;
    rows.forEach((node,i)=>{node.classList.toggle('selected',i===index);const button=node.querySelector('button');button.setAttribute('aria-pressed',String(i===index));});
    for(const list of [inputTokens,outputTokens])list.forEach(({node,stepIndex})=>node.classList.toggle('selected',stepIndex===index));
    document.querySelectorAll('#alphabet > div').forEach((node,i)=>{node.classList.toggle('input-active',i===step.value);node.classList.toggle('output-active',p>=3&&i===step.output.charCodeAt(0)-65);});
    get('trace-prev').disabled=index===0;get('trace-next').disabled=index===result.steps.length-1;
  }
  function finish(){
    stop();phaseUI(4);state(result.recovery_matches?'INVERSE VERIFIED':'CHECK FAILED');
    setText('cipher-narration',`Python then ran the inverse operation. ${result.recovery_matches?'It recovered the normalized input exactly.':'The recovered value does not match the normalized input.'} This checks round-trip correctness, not resistance to attack. Spaces and non-ASCII characters remain unchanged.`);
    get('trace-progress').value=result.steps.length||1;
  }
  function tick(){
    if(!playing||stale||!result)return;
    if(phase<3){draw(phase+1);}
    else if(index<result.steps.length-1){index++;draw(0);}
    else{finish();return;}
    timer=setTimeout(tick,Number(get('trace-speed').value)/4);
  }
  function play(){
    if(!result||!result.steps.length||stale)return;
    if(playing){stop();return;}
    if(index===result.steps.length-1&&phase===3)index=0;
    playing=true;get('cipher-stage').classList.add('running');setText('trace-play','Pause');draw(0);
    timer=setTimeout(tick,Number(get('trace-speed').value)/4);
  }
  function select(i){stop();index=i;draw(3);}
  function ribbon(containerId,text,tokenList){
    const fragment=document.createDocumentFragment();let letter=0;
    for(const char of Array.from(text)){
      const node=document.createElement('span');const isLetter=/^[A-Z]$/.test(char);
      node.textContent=char===' '?'␠':char==='\n'?'↵':char==='\t'?'⇥':char;
      node.className='letter-token'+(!isLetter?' passthrough':'');
      const stepIndex=isLetter?letter++:null;tokenList.push({node,stepIndex});
      node.title=isLetter?'Letter '+(stepIndex+1):'Preserved character; the key does not advance';fragment.append(node);
    }get(containerId).replaceChildren(fragment);
  }
  function render(data){
    reset();result=data;get('cipher-evidence').hidden=false;enable(data.steps.length>0);
    setText('cipher-plaintext',data.plaintext||'(empty message)');setText('cipher-ciphertext',data.ciphertext||'(empty message)');
    setText('cipher-recovered',data.round_trip||'(empty message)');setText('recovery-heading',data.recovery_matches?'Inverse recovery confirmed':'Inverse recovery mismatch');
    get('recovery-heading').classList.toggle('verified',data.recovery_matches===true);
    setText('recovery-explanation',`Python applied the inverse of ${data.operation}. Recovery is compared with the uppercase-ASCII normalized input, not its original letter case. Result: ${data.recovery_matches?'MATCH':'MISMATCH'}.`);
    setText('cipher-weakness',data.weakness);setText('cipher-key-management',data.key_management);setText('cipher-raw',JSON.stringify(data,null,2));
    setText('calculation-count',`${data.steps.length} transformed letters · ${Array.from(data.input).length-data.steps.length} preserved characters`);
    const normalized=Array.from(data.input).map(char=>/^[a-z]$/i.test(char)?char.toUpperCase():char).join('');
    ribbon('cipher-input-ribbon',normalized,inputTokens);ribbon('cipher-output-ribbon',data.output,outputTokens);
    const fragment=document.createDocumentFragment();
    data.steps.forEach((step,i)=>{
      const row=document.createElement('tr'),first=document.createElement('td'),button=document.createElement('button');
      button.type='button';button.textContent=String(i+1).padStart(2,'0');button.setAttribute('aria-label','Explain letter '+(i+1));button.setAttribute('aria-pressed','false');button.addEventListener('click',()=>select(i));first.append(button);row.append(first);
      for(const value of [step.input,step.value,step.key,step.calculation,step.output]){const cell=document.createElement('td');cell.textContent=String(value);row.append(cell);}rows.push(row);fragment.append(row);
    });get('cipher-calculation-body').replaceChildren(fragment);
    if(!data.steps.length){state('PASSTHROUGH ONLY');phaseUI(4);setText('cipher-narration','There are no A–Z letters to shift. Python preserved the input unchanged. The inverse check below still verifies this result.');setText('trace-progress-label','0 transformed letters');return;}
    draw(3);
    if(!reduced.matches&&data.steps.length<=80)play();
    else setText('cipher-narration',narration(data.steps[0],3)+(data.steps.length>80?' Long message: automatic playback is off. Use the row selectors or Play.':' Reduced motion is enabled; use the manual controls or choose Play.'));
  }
  function focus(value){if(get('presentation-top')){get('presentation-top').setAttribute('aria-pressed',String(value));get('presentation-top').textContent=value?'Exit focus ↙':'Presentation focus ↗';}document.body.classList.toggle('presentation-focus',value);get('presentation-toggle').setAttribute('aria-pressed',String(value));setText('presentation-toggle',value?'Exit presentation focus ↙':'Presentation focus ↗');}
  get('trace-prev').addEventListener('click',()=>{if(result&&index>0)select(index-1);});
  get('trace-next').addEventListener('click',()=>{if(result&&index<result.steps.length-1)select(index+1);});
  get('trace-play').addEventListener('click',play);get('trace-replay').addEventListener('click',()=>{select(0);if(!reduced.matches)play();});
  get('presentation-toggle').addEventListener('click',()=>focus(!document.body.classList.contains('presentation-focus')));
  document.addEventListener('keydown',event=>{if(event.key==='Escape')focus(false);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
  document.addEventListener('enigma:navigate',()=>{stop();focus(false);});
  get('task-form').addEventListener('input',markStale);get('task-form').addEventListener('change',markStale);
  const demos=document.createElement('div');demos.id='cipher-demos';demos.className='cipher-demos';demos.hidden=location.hash!=='#classical';
  const hint=document.createElement('span');hint.textContent='PRESENTATION DEMOS';demos.append(hint);
  for(const [name,cipher,message,key] of [['Caesar / HELLO','caesar','HELLO WORLD','3'],['Vigenère / ATTACK','vigenere','ATTACK AT DAWN','LEMON'],['Wrap-around / XYZ','caesar','XYZ','3']]){
    const button=document.createElement('button');button.type='button';button.textContent=name;button.addEventListener('click',()=>{if(get('run-button').disabled)return;get('cipher').value=cipher;get('operation').value='encrypt';get('message').value=message;get('key').value=key;get('character-count').textContent=message.length+' / 2000';get('task-form').requestSubmit();});demos.append(button);
  }
  const focusButton=document.createElement('button');focusButton.type='button';focusButton.id='presentation-top';focusButton.className='focus-demo';focusButton.textContent='Presentation focus ↗';focusButton.setAttribute('aria-pressed','false');focusButton.addEventListener('click',()=>focus(!document.body.classList.contains('presentation-focus')));demos.append(focusButton);
  get('task-form').prepend(demos);
  document.addEventListener('enigma:navigate',event=>{demos.hidden=event.detail.id!=='classical';});
  get('cipher').addEventListener('change',()=>{if(location.hash==='#classical'){get('key').value=get('cipher').value==='vigenere'?'LEMON':'3';markStale();}});
  function pending(){reset();state('PYTHON WORKING');setText('cipher-narration','The request is being sent to Python. The lab waits for the actual result before displaying any transformation.');}
  function fail(){stop();state('NO VERIFIED RESULT');enable(false);setText('cipher-narration','No successful result was received. Check the input or the local server, then run again. No calculation is being presented as verified.');}
  window.enigmaCipher={render,reset,pause:stop,pending,fail};reset();
})();
