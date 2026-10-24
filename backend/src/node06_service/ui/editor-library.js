/* First-party private lists. Only an explicit public point ID leaves this window. */
'use strict';
(() => {
  const el=id=>document.getElementById(id), peer=window.opener;
  const channel=new URLSearchParams(location.search).get('channel'), site=document.body.dataset.site, embed=document.body.dataset.embedOrigin;
  let actor=null,cursor=null,busy=false;
  const valid=window===top&&peer&&/^[0-9a-f]{32}$/.test(channel||'')&&Boolean(embed);
  const status=text=>{el('library-status').textContent=text;};
  async function api(path){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
    try{const r=await fetch('/api/v1'+path,{credentials:'same-origin',cache:'no-store',signal:controller.signal});const v=await r.json();if(!r.ok)throw new Error(v.code);return v;}finally{clearTimeout(timer);}
  }
  function row(pin,list){
    const li=document.createElement('li'),b=document.createElement('button');
    b.type='button';b.dataset.pointId=pin.id;b.textContent=pin.preview||pin.id;b.disabled=Boolean(pin.unavailable);
    b.addEventListener('click',async()=>{
      if(busy||!actor||!valid)return;busy=true;b.disabled=true;
      try{const session=await api('/me');if(session.user_id!==actor)throw new Error('ACCOUNT_CHANGED');
        // Resolve public visibility at the moment of selection, not from a private list.
        const p=await api('/points/'+pin.id);
        if(peer.closed)throw new Error('EDITOR_CLOSED');
        peer.postMessage({protocol:'node06-library/1',kind:'selected',channel,site,id:p.id},embed);
        status('Ссылка передана в редактор.');
      }catch(e){status(e.message==='ACCOUNT_CHANGED'?'Аккаунт сменился. Обновите библиотеку.':'Не удалось выбрать точку. Повторите.');}
      finally{busy=false;b.disabled=Boolean(pin.unavailable);}
    });li.append(b);el(list).append(li);
  }
  async function mine(){
    const page=await api('/me/points'+(cursor?'?'+new URLSearchParams({after:cursor}):''));
    for(const pin of page.items)row(pin,'library-points');
    cursor=page.next_cursor;el('library-more').hidden=!cursor;
  }
  async function refresh(){
    if(busy||!valid)return;busy=true;el('library-refresh').disabled=true;
    el('library-favorites').replaceChildren();el('library-points').replaceChildren();actor=null;cursor=null;
    try{const me=await api('/me');actor=me.user_id;
      const favorites=await api('/me/favorites');for(const pin of favorites.items)row(pin,'library-favorites');
      await mine();status('Вы вошли: '+me.handle);
    }catch(e){status(e.message==='AUTH_REQUIRED'?'Войдите и нажмите «Обновить».':'Библиотека недоступна. Нажмите «Обновить».');}
    finally{busy=false;el('library-refresh').disabled=false;}
  }
  el('library-refresh').addEventListener('click',()=>void refresh());
  el('library-more').addEventListener('click',async()=>{if(busy)return;busy=true;try{const me=await api('/me');if(me.user_id!==actor)throw new Error('ACCOUNT_CHANGED');await mine();}catch(_){status('Обновите библиотеку для продолжения.');}finally{busy=false;}});
  if(valid)void refresh();else{el('library-refresh').disabled=true;status('Откройте библиотеку из редактора.');}
})();
