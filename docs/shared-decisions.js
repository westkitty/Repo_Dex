/* Repo_Dex / Constellation local-only decision ledger. No network or telemetry. */
(()=>{'use strict';
 const KEY='westkitty.repoDex.decisions.v1',SCHEMA='repo-dex-decisions/v1',MAX=1200;
 const ID=/^[0-9a-f]{16,64}$/;
 const CHOICES=new Set(['investigate','shelve','reject']);
 let fallback={schema:SCHEMA,owner:'westkitty',items:{}};
 const notify=()=>{try{window.dispatchEvent(new CustomEvent('repo-dex-decisions-changed'))}catch{}};
 const empty=()=>({schema:SCHEMA,owner:'westkitty',items:{}});
 function validate(src){
  if(!src||src.schema!==SCHEMA||src.owner!=='westkitty'||!src.items||typeof src.items!=='object'||Array.isArray(src.items)||Object.keys(src.items).length>MAX)throw Error('Invalid decision ledger');
  const d=empty();
  for(const [id,v] of Object.entries(src.items)){
   if(!ID.test(id)||!v||typeof v!=='object'||!CHOICES.has(v.choice)||typeof v.evidence_signature!=='string'||v.evidence_signature.length>2000||typeof v.reviewed_at!=='string'||!/^\d{4}-\d\d-\d\dT/.test(v.reviewed_at)||typeof v.reason!=='string'||v.reason.length>500)throw Error('Invalid decision entry');
   d.items[id]={choice:v.choice,reason:v.reason,evidence_signature:v.evidence_signature,reviewed_at:v.reviewed_at};
  }
  return d;
 }
 function load(){try{const raw=localStorage.getItem(KEY);if(raw){fallback=validate(JSON.parse(raw));return fallback;}}catch{}return fallback;}
 function persist(data){fallback=validate(data);try{localStorage.setItem(KEY,JSON.stringify(fallback))}catch{}notify();return fallback;}
 function signature(op){if(!op||!ID.test(String(op.id||'')))return '';const ev=Array.isArray(op.evidence)?op.evidence:[];return ev.map(s=>[s.repository_id,s.commit_sha,s.sha256].join(':')).sort().join('|').slice(0,2000);}
 function decisionFor(op){const d=load().items[op?.id];if(!d)return {choice:'new',needsReview:false,reason:''};return {...d,needsReview:d.evidence_signature!==signature(op)};}
 function set(op,choice,reason=''){
  if(!op||!ID.test(String(op.id||''))||!CHOICES.has(choice))throw Error('Unknown opportunity or choice');
  if(typeof reason!=='string'||reason.length>500)throw Error('Reason exceeds 500 characters');
  const data=load();data.items[op.id]={choice,reason,evidence_signature:signature(op),reviewed_at:new Date().toISOString()};return persist(data);
 }
 function exportJSON(){return JSON.stringify(load(),null,2)+'\n';}
 function importJSON(raw){if(typeof raw!=='string'||raw.length>250000)throw Error('Import too large');const incoming=validate(JSON.parse(raw));const before=load();const merged=empty();merged.items={...before.items};for(const [key,item] of Object.entries(incoming.items)){
  if(!merged.items[key]||item.reviewed_at>=merged.items[key].reviewed_at)merged.items[key]=item;
 }
 return persist(merged);
 }
 window.RepoDexDecisions=Object.freeze({SCHEMA,KEY,load,decisionFor,set,signature,exportJSON,importJSON});
 window.addEventListener('storage',e=>{if(e.key===KEY){load();notify()}});
})();
