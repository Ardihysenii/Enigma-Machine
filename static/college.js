'use strict';
const el=id=>document.getElementById(id);
const descriptions={student_own_grades_only:'Studenti sheh vetëm notat e veta',block_student_professor_area:'Zona e profesorit vetëm për profesorë',block_student_grade_edit:'Studenti nuk ndryshon nota',professor_assigned_courses_only:'Profesori vetëm te lënda e caktuar',session_inactivity_timeout:'Skadimi pas 30 sekondave pa veprim',audit_professor_only:'Auditimi vetëm për profesorë'};
const views=['grades','professor','edit','audit'];
let view=document.body.dataset.initialView||'grades';
let current=null,generation=0,busy=false,refreshing=false,deadline=null;
const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('enigma-college-policy'):null;
function clearMetrics(){for(const id of ['metric-records','metric-courses','metric-average'])el(id).textContent='—';}
function message(text,type=''){el('access-status').textContent=text;el('access-status').className='status '+type;if(type!=='allowed')clearMetrics();}
async function api(path,body){
  const options={cache:'no-store',signal:AbortSignal.timeout(8000)};
  if(body!==undefined){options.method='POST';options.headers={'Content-Type':'application/json'};options.body=JSON.stringify(body);}
  const response=await fetch('/api/college/'+path,options);return {response,data:await response.json()};
}
function timerText(){
  if(!current)return;
  el('session-status').textContent=current.session_expired?'Sesioni skadoi. Kliko Hyr / kyçu përsëri.':!current.actor?'Nuk ka sesion aktiv.':deadline!==null?`Skadimi pas ${Math.max(0,Math.ceil((deadline-Date.now())/1000))} sekondave pa veprim.`:'Skadimi 30-sekondësh nuk është aktiv.';
}
function applySnapshot(data){
  current=data;
  const initials=data.actor?data.actor.name.split(' ').slice(0,2).map(part=>part[0]).join(''):'E';
  el('identity-name').textContent=data.actor?.name||'Zgjedh identitetin';
  el('identity-role').textContent=data.actor?(data.actor.role==='student'?'Student · '+data.actor.id:'Profesor · '+data.actor.id):'Sesioni nuk është aktiv';
  el('identity-avatar').textContent=initials;el('profile-initial').textContent=initials;
  el('welcome-title').textContent=data.actor?'Mirë se erdhe, '+data.actor.name+'.':'Hapësirë për dijen.';
  deadline=data.expires_in==null?null:Date.now()+data.expires_in*1000;
  if(data.actor)el('demo-user').value=data.actor.id;
  el('mode').textContent=`${data.active_count} / ${data.total_controls} kontrolle aktive`;
  el('mode').className='badge '+(data.mode==='protected'?'protected':'');
  el('identity').textContent=data.actor?`${data.actor.name} · ${data.actor.role==='student'?'Student':'Profesor'} · ${data.actor.id}`:'Nuk je kyçur.';
  el('assigned-courses').textContent=data.actor?.role==='professor'?'Lënda e caktuar: '+data.actor.courses.join(', '):'';
  el('logout').hidden=!data.actor;
  el('policy-list').replaceChildren(...Object.entries(descriptions).map(([key,label])=>{const li=document.createElement('li');li.textContent=label;li.className=data.rules[key]?'active':'';li.title=data.rules[key]?'Kontrolli është aktiv':'Kontrolli nuk është aktiv';li.setAttribute('aria-label',label+(data.rules[key]?' — aktiv':' — jo aktiv'));return li;}));
  timerText();
}
function table(headers,rows){
  const node=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');
  for(const text of headers){const th=document.createElement('th');th.textContent=text;th.scope='col';tr.append(th);}head.append(tr);node.append(head);
  const body=document.createElement('tbody');
  for(const values of rows){const row=document.createElement('tr');for(const value of values){const td=document.createElement('td');td.textContent=String(value);row.append(td);}body.append(row);}node.append(body);return node;
}
function gradeTable(rows){
  el('metric-records').textContent=String(rows.length);
  el('metric-courses').textContent=String(new Set(rows.map(row=>row.course)).size);
  el('metric-average').textContent=rows.length?(rows.reduce((sum,row)=>sum+row.grade,0)/rows.length).toFixed(1):'—';
  const node=table(['Studenti','Lënda','Nota'],[]),body=node.querySelector('tbody');
  for(const row of rows){
    const tr=document.createElement('tr'),student=document.createElement('td'),course=document.createElement('td'),grade=document.createElement('td');
    const person=document.createElement('div');person.className='student-cell';
    const avatar=document.createElement('span');avatar.className='avatar';avatar.textContent=row.student[0];avatar.setAttribute('aria-hidden','true');
    const info=document.createElement('div'),name=document.createElement('strong'),id=document.createElement('small');name.textContent=row.student;id.textContent='STUDENT / '+row.student_id.toUpperCase();info.append(name,id);person.append(avatar,info);student.append(person);
    course.textContent=row.course;const pill=document.createElement('span');pill.className='grade-pill'+(row.grade>=9?' high':'');pill.textContent=String(row.grade);grade.append(pill);tr.append(student,course,grade);body.append(tr);
  }return node;
}
async function loadView(){
  const own=++generation;el('data-panel').replaceChildren();
  el('grade-controls').hidden=view!=='grades';el('edit-form').hidden=view!=='edit';
  for(const name of views)el('view-'+name).classList.toggle('active',view===name);
  el('view-title').textContent={grades:'Pasqyra e notave',professor:'Zona e profesorit',edit:'Menaxho notat',audit:'Regjistrat e auditimit'}[view];
  message('Duke kontrolluar qasjen në Python…');
  try{
    const target=el('grade-target').value;
    const path=view==='grades'?'grades'+(target?'?student_id='+encodeURIComponent(target):''):view==='edit'?'grades':view;
    const {response,data}=await api(path);if(own!==generation)return;
    if(data.rules)applySnapshot(data);
    if(!response.ok){message(`HTTP ${response.status} · ${data.error||'Kërkesa u refuzua.'}`,'denied');return;}
    if(view==='audit'){
      clearMetrics();
      message(`HTTP 200 · ${data.actor.name} · Auditimi u lejua.`,'allowed');
      el('data-panel').append(table(['Koha','Veprimi','Identiteti','Rezultati','Objektivi'],[...data.events].reverse().map(event=>[new Date(event.timestamp).toLocaleString('sq'),event.action,event.actor_id||'Operatori',event.allowed?'Lejuar':'Refuzuar',event.target||'—'])));
    }else{
      const detail=view==='professor'?'Zona e profesorit u hap.':data.scope==='own'?'Po shfaqen vetëm notat e tua.':data.scope==='assigned'?'Po shfaqen vetëm notat e lëndës së caktuar.':data.scope==='all'?'Po shfaqen notat e të gjithë studentëve.':'Po shfaqen notat e kërkuara.';
      message(`HTTP 200 · ${data.actor.name} (${data.actor.role==='student'?'Student':'Profesor'}) · ${detail}`,'allowed');
      el('data-panel').append(gradeTable(data.rows));
    }
  }catch(error){if(own!==generation)return;el('data-panel').replaceChildren();message('Nuk u mor përgjigje nga Python. Hape Start ENIGMA College.cmd dhe riprovo.','error');}
}
async function refreshStatus(initial=false){
  if(busy||refreshing)return;refreshing=true;
  try{
    const {response,data}=await api('status');if(!response.ok)throw new Error(data.error);
    const changed=JSON.stringify(current?.rules)!==JSON.stringify(data.rules)||current?.actor?.id!==data.actor?.id||current?.updated_at!==data.updated_at||current?.revision!==data.revision;
    if(initial){el('demo-user').replaceChildren(...data.users.map(user=>{const option=document.createElement('option');option.value=user.id;option.textContent=`${user.name} · ${user.role==='student'?'Student':'Profesor'}`;return option;}));}
    applySnapshot(data);
    if(initial||changed){
      if(data.actor)await loadView();
      else{++generation;el('data-panel').replaceChildren();message(data.session_expired?'HTTP 401 · Sesioni skadoi pas 30 sekondave pa veprim. Kyçu përsëri.':'Zgjedh një identitet dhe kliko Hyr.','denied');}
    }
  }catch(error){++generation;el('data-panel').replaceChildren();el('mode').textContent='Python nuk është i qasshëm';message('Lidhja me Python dështoi. Hape Start ENIGMA College.cmd.','error');}
  finally{refreshing=false;}
}
el('login-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;++generation;el('data-panel').replaceChildren();el('login-button').disabled=true;el('demo-user').disabled=true;
  try{const {response,data}=await api('login',{user_id:el('demo-user').value});if(!response.ok)throw new Error(data.error);applySnapshot(data);await loadView();}
  catch(error){message(error.message||'Kyçja dështoi.','error');}
  finally{busy=false;el('login-button').disabled=false;el('demo-user').disabled=false;}
});
el('demo-user').addEventListener('change',()=>{if(!busy)el('login-form').requestSubmit();});
el('logout').addEventListener('click',async()=>{
  if(busy)return;busy=true;++generation;el('data-panel').replaceChildren();
  try{const {response,data}=await api('logout',{});if(!response.ok)throw new Error(data.error);applySnapshot(data);message('Dole nga identiteti. Zgjedh një identitet për të vazhduar.');}
  catch(error){message('Dalja nuk u konfirmua. Riprovo.','error');}finally{busy=false;}
});
el('edit-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;++generation;el('save-grade').disabled=true;el('data-panel').replaceChildren();
  try{
    const {response,data}=await api('grades/update',{student_id:el('edit-student').value,course:el('edit-course').value,grade:Number(el('edit-grade').value)});
    if(data.rules)applySnapshot(data);
    if(!response.ok){message(`HTTP ${response.status} · ${data.error}`,'denied');return;}
    message(`HTTP 200 · ${data.actor.name} · Nota u ndryshua realisht: ${data.previous_grade} → ${data.row.grade}.`,'allowed');
    el('data-panel').append(gradeTable([data.row]));if(channel)channel.postMessage({type:'grades-changed'});
  }catch(error){message('Ruajtja nuk u konfirmua nga serveri.','error');}
  finally{busy=false;el('save-grade').disabled=false;}
});
for(const name of views)el('view-'+name).addEventListener('click',()=>{if(busy)return;view=name;history.replaceState(null,'',name==='professor'?'/college/demo/professor':'/college/demo');void loadView();});
el('refresh').addEventListener('click',()=>{if(!busy)void loadView();});
el('grade-target').addEventListener('change',()=>{if(!busy)void loadView();});
window.addEventListener('focus',()=>void refreshStatus());
document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refreshStatus();});
if(channel)channel.addEventListener('message',()=>void refreshStatus());
window.addEventListener('storage',event=>{if(event.key==='enigma-college-policy-changed')void refreshStatus();});
window.addEventListener('pageshow',()=>void refreshStatus());
setInterval(()=>{if(!document.hidden)void refreshStatus();},2000);
setInterval(timerText,500);
void refreshStatus(true);
