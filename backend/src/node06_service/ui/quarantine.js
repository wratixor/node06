'use strict';
(() => {
  const el=id=>document.getElementById(id),args=new URLSearchParams(location.search);
  let actor=null,busy=false,cursor=null;
  function node(tag,text,parent){const n=document.createElement(tag);n.textContent=text;parent.append(n);return n;}
  function clear(){el('q-points').replaceChildren();el('q-article').hidden=true;el('q-author').textContent='';el('q-body').textContent='';el('q-more').hidden=true;cursor=null;}
  async function api(path){const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);try{const r=await fetch('/api/v1'+path,{credentials:'same-origin',cache:'no-store',signal:abort.signal});const value=await r.json();if(!r.ok)throw new Error(value.code);return value;}finally{clearTimeout(timer);}}
  async function act(task){if(busy)return;busy=true;for(const n of document.querySelectorAll('button,select'))n.disabled=true;el('q-status').textContent='Загрузка…';
    try{const me=await api('/me');if(actor&&actor!==me.user_id)throw new Error('ACCOUNT_CHANGED');actor=me.user_id;await task();el('q-status').textContent='Готово.';}
    catch(e){clear();el('q-bans').replaceChildren();el('q-status').textContent=e.message==='AUTH_REQUIRED'?'Войдите в аккаунт.':e.message==='ACCOUNT_CHANGED'?'Аккаунт изменился. Перезагрузите страницу.':'Нет доступа или точка больше не в карантине. Обновите список.';}
    finally{busy=false;for(const n of document.querySelectorAll('button,select'))n.disabled=false;}
  }
  async function open(id){const p=await api('/me/quarantine/'+encodeURIComponent(id)+'?'+new URLSearchParams({scope:el('q-scope').value}));el('q-author').textContent=p.author?.name||p.id;el('q-body').textContent=p.body;el('q-article').hidden=false;el('q-article').scrollIntoView({block:'nearest'});}
  async function load(append=false){if(!append)clear();const p=await api('/me/quarantine?'+new URLSearchParams({scope:el('q-scope').value,...(cursor?{after:cursor}:{})}));for(const item of p.items){const li=node('li','',el('q-points')),b=node('button',item.preview||item.id,li);b.type='button';b.addEventListener('click',()=>void act(()=>open(item.id)));}cursor=p.next_cursor;el('q-more').hidden=!cursor;if(!el('q-points').children.length)node('li','Нет точек в карантине.',el('q-points'));}
  el('q-form').addEventListener('submit',e=>{e.preventDefault();void act(()=>load());});
  el('q-scope').addEventListener('change',()=>{clear();void act(()=>load());});
  el('q-more').addEventListener('click',()=>void act(()=>load(true)));
  void act(async()=>{const [bans,roles]=await Promise.all([api('/me/bans'),api('/moderation/scopes')]);const scopes=new Map();for(const r of bans.items)scopes.set(r.scope,r.scope);for(const r of roles.items)scopes.set(r.scope,r.name||r.scope);for(const [value,label] of scopes){const o=node('option',label,el('q-scope'));o.value=value;}if(/^(server|s_[0-9a-f]{32})$/.test(args.get('scope')||'')&&!scopes.has(args.get('scope'))){const o=node('option',args.get('scope'),el('q-scope'));o.value=args.get('scope');scopes.set(o.value,o.value);}if(args.get('scope')&&scopes.has(args.get('scope')))el('q-scope').value=args.get('scope');if(!scopes.size)throw new Error('QUARANTINE_FORBIDDEN');await load();for(const b of bans.items)node('li',b.scope+' · '+(b.mode==='block'?'Запрет публикации и показа':'Карантин')+' · '+(b.expires_at?new Date(b.expires_at).toLocaleString('ru-RU'):'Бессрочно')+' · '+b.reason,el('q-bans'));if(args.get('point'))await open(args.get('point'));});
})();
