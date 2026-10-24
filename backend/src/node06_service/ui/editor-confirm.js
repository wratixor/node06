/* Trusted top-level review. No credentials or private account data cross windows. */
'use strict';
(() => {
  const el=id=>document.getElementById(id), channel=new URLSearchParams(location.search).get('channel');
  const embed=document.body.dataset.embedOrigin, site=document.body.dataset.site;
  const peer=window.opener;
  let draft=null, key=null, actor=null, displayedActor=null, busy=false, confirmed=null,quarantined=false;
  const status=text=>{el('confirmation-status').textContent=text;};
  const tell=(kind,extra={})=>peer?.postMessage({protocol:'node06-publish/1',channel,kind,...extra},embed);
  async function api(path,options={}) {
    const abort=new AbortController(), timer=setTimeout(()=>abort.abort(),15000);
    try {
      const r=await fetch(path,{...options,credentials:'same-origin',cache:'no-store',signal:abort.signal});
      const v=await r.json();if(!r.ok){const e=new Error(v.code);e.definite=r.status<500;throw e;}return v;
    } finally {clearTimeout(timer);}
  }
  async function session() {
    try {
      const me=await api('/api/v1/me');
      if(actor&&actor!==me.user_id)throw new Error('ACCOUNT_CHANGED');
      displayedActor=me.user_id;status('Публикация от имени: '+me.handle);
      el('confirmation-publish').disabled=!draft||busy||Boolean(confirmed);
    } catch(e) {el('confirmation-publish').disabled=true;status(e.message==='ACCOUNT_CHANGED'?'Аккаунт сменился. Вернитесь в исходный аккаунт.':'Войдите в аккаунт и нажмите «Продолжить после входа».');}
  }
  const id=/^[a-z0-9][a-z0-9_-]{0,95}$/;
  function valid(value) {
    return value && Object.keys(value).sort().join() === 'body,lang,links' &&
      typeof value.body==='string' && value.body.length>0 && value.body.length<=8192 &&
      value.lang==='und' && Array.isArray(value.links) && value.links.length>=1 && value.links.length<=16 &&
      new Set(value.links.map(p=>p.id)).size===value.links.length && value.links.every(p=>
        p && Object.keys(p).sort().join()==='content_digest,id,revision_id' && id.test(p.id) &&
        (p.revision_id===null||/^v_[0-9a-f]{32}$/.test(p.revision_id)) && /^[0-9a-f]{64}$/.test(p.content_digest));
  }
  window.addEventListener('message',event=>{
    const m=event.data;
    if(event.source!==peer||event.origin!==embed||m?.protocol!=='node06-publish/1'||m.channel!==channel)return;
    if(m.kind==='draft'&&m.site===site&&valid(m.payload)&&/^[0-9a-f-]{36}$/.test(m.key||'')) {
      const encoded=JSON.stringify(m.payload);
      // The displayed operation is immutable, including the idempotency key.
      if(draft){if(encoded===draft&&m.key===key&&confirmed)tell('published',{id:confirmed,quarantined});return;}
      draft=encoded;key=m.key;
      el('confirmation-body').textContent=m.payload.body;
      for(const pin of m.payload.links){const li=document.createElement('li');li.textContent=pin.id;el('confirmation-links').append(li);}
      el('confirmation-draft').hidden=false;void session();
    }
  });
  el('confirmation-login').addEventListener('click',()=>void session());
  el('confirmation-publish').addEventListener('click',async()=>{
    if(!draft||busy||confirmed)return;
    busy=true;el('confirmation-publish').disabled=true;
    try {
      const me=await api('/api/v1/me');
      if((actor&&actor!==me.user_id)||displayedActor!==me.user_id)throw new Error('ACCOUNT_CHANGED');
      actor=me.user_id;
      const r=await api(`/editor/confirm/${site}/`,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token,'Idempotency-Key':key},body:draft});
      confirmed=r.id;quarantined=r.quarantined===true;tell('published',{id:r.id,quarantined});status(quarantined?'Сохранено в карантине. Можно закрыть это окно.':'Опубликовано. Можно закрыть это окно.');
      // Never close the editor draft on an unacknowledged or failed write.
    } catch(e) {
      status(e.message==='ACCOUNT_CHANGED'?'Аккаунт сменился. Вернитесь в исходный аккаунт.':
        e.definite?'Публикация отклонена: '+e.message+'. Вернитесь в редактор для исправления.':
        'Ответ не получен. Повторите публикацию здесь: повтор не создаст дубликат.');
      if(e.message==='IDEMPOTENCY_CONFLICT'){actor=null;status('Повтор относится к другой публикации или аккаунту. Войдите в исходный аккаунт и повторите здесь.');}
      if(e.definite&&!['IDEMPOTENCY_CONFLICT','ACCOUNT_CHANGED'].includes(e.message))tell('rejected',{code:e.message});
    } finally {busy=false;el('confirmation-publish').disabled=Boolean(confirmed);}
  });
  if(window===window.top&&peer&&/^[0-9a-f]{32}$/.test(channel||''))tell('ready');
  else status('Откройте публикацию кнопкой из редактора.');
})();
