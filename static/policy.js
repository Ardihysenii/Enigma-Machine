'use strict';
(()=>{
  const panel=document.getElementById('college-policy-panel');
  const status=document.getElementById('college-policy-status');
  const button=document.getElementById('apply-college-policy');
  const names=['student_own_grades_only','block_student_professor_area','block_student_grade_edit','professor_assigned_courses_only','session_inactivity_timeout','audit_professor_only'];
  let dirty=false,loaded=false,pending=false,refreshing=false;
  const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('enigma-college-policy'):null;
  function notify(){
    if(channel)channel.postMessage({type:'policy-changed'});
    try{localStorage.setItem('enigma-college-policy-changed',String(Date.now()));}catch(error){}
  }
  function summary(data){return `${data.active_count} / ${data.total_controls} kontrolle aktive në Python.`;}
  async function refresh(){
    if(panel.hidden||pending||refreshing)return;
    refreshing=true;
    try{
      const response=await fetch('/api/college/policy',{cache:'no-store',signal:AbortSignal.timeout(8000)});
      const data=await response.json();if(!response.ok)throw new Error(data.error);
      if(!dirty)for(const key of names)document.getElementById(key).checked=data.rules[key];
      loaded=true;button.disabled=false;
      status.textContent=summary(data)+(dirty?' Ke ndryshime të paaplikuara. Kliko Apply security rules.':'');
    }catch(error){loaded=false;button.disabled=true;status.textContent='Rregullat nuk u lexuan. Kontrollo serverin lokal dhe kliko Reload active rules.';}
    finally{refreshing=false;}
  }
  function changed(){dirty=true;status.textContent='Zgjedhja ende nuk është zbatuar. Kliko Apply security rules.';}
  function navigate(){panel.hidden=location.hash!=='#analysis';if(!panel.hidden)void refresh();}
  for(const key of names)document.getElementById(key).addEventListener('change',changed);
  for(const [id,value] of [['enable-all-controls',true],['disable-all-controls',false]])document.getElementById(id).addEventListener('click',()=>{if(pending)return;for(const key of names)document.getElementById(key).checked=value;changed();});
  document.getElementById('college-policy-form').addEventListener('submit',async event=>{
    event.preventDefault();if(pending||!loaded)return;pending=true;button.disabled=true;
    for(const key of names)document.getElementById(key).disabled=true;
    status.textContent='Duke i aplikuar rregullat në Python…';
    try{
      const rules=Object.fromEntries(names.map(key=>[key,document.getElementById(key).checked]));
      const response=await fetch('/api/college/policy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules}),signal:AbortSignal.timeout(8000)});
      const data=await response.json();if(!response.ok)throw new Error(data.error);
      dirty=false;notify();status.textContent=summary(data)+' Faqja e kolegjit përditësohet automatikisht.';
      for(const key of names)document.getElementById(key).checked=data.rules[key];
    }catch(error){dirty=true;status.textContent='Zbatimi nuk u konfirmua. Kliko Reload active rules për të kontrolluar serverin.';}
    finally{pending=false;button.disabled=!loaded;for(const key of names)document.getElementById(key).disabled=false;}
  });
  document.getElementById('reload-college-policy').addEventListener('click',()=>{if(pending)return;dirty=false;void refresh();});
  window.addEventListener('hashchange',navigate);window.addEventListener('focus',()=>void refresh());
  if(channel)channel.addEventListener('message',()=>void refresh());
  window.addEventListener('storage',event=>{if(event.key==='enigma-college-policy-changed')void refresh();});
  navigate();
})();
