(() => {
  'use strict';
  const el=id=>document.getElementById(id);
  let csrf=null,busy=false,preview=null,cursor=null;
  const scopeNames={color:'Цвет',favorites:'Избранное',subscriptions:'Подписки на точки',own_points:'Свои посты'};
  function scopes(parent,selected){const inputs=[];for(const [key,name] of Object.entries(scopeNames)){
    const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=key;input.checked=selected.includes(key);label.append(input,document.createTextNode(name));parent.append(label);inputs.push(input);
  }return ()=>inputs.filter(i=>i.checked).map(i=>i.value);}
  function scopeGroup(parent,title,selected){const group=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=title;group.append(legend);parent.append(group);return scopes(group,selected);}
  const getSend=scopeGroup(el('links-scopes'),'Отправлять',[]),getReceive=scopeGroup(el('links-scopes'),'Принимать',[]);
  const permissionText=(send=[],receive=[])=>'От первого сервера ко второму: '+(send.map(k=>scopeNames[k]).join(', ')||'нет данных')+'. Обратно: '+(receive.map(k=>scopeNames[k]).join(', ')||'нет данных')+'.';
  async function items(reset=true){if(reset){cursor=null;el('sync-items').replaceChildren();}
    const query=new URLSearchParams({kind:el('sync-kind').value,...(cursor||{})}),data=await api('me/profile-sync/preferences?'+query);
    for(const item of data.items){const li=document.createElement('li'),link=document.createElement('a');link.href=item.url;link.textContent=item.point_id+' · '+item.origin;link.rel='noreferrer';li.append(link);
      if(item.kind==='favorites'){const b=document.createElement('button');b.type='button';b.textContent='×';b.setAttribute('aria-label','Удалить из избранного');b.addEventListener('click',()=>run(async()=>{await api('me/profile-sync/favorite',{origin:item.origin,point_id:item.point_id,active:false});await items();}));li.append(b);}
      el('sync-items').append(li);}
    cursor=data.next_cursor;el('sync-more').hidden=!cursor;
  }
  el('sync-kind').addEventListener('change',()=>run(()=>items()));el('sync-more').addEventListener('click',()=>run(()=>items(false)));
  const controls=()=>{for(const b of document.querySelectorAll('#links-create button,#links-import button,#links-confirm,#links-reload,#sync-kind,#sync-more,#sync-items button,#links-list button'))b.disabled=!csrf||busy;};
  const messages={AUTH_REQUIRED:'Войдите на этом сервере.',PROFILE_PEER_UNAVAILABLE:'Другой сервер недоступен. Связь не подтверждена.',
    PROFILE_INVITATION_INVALID:'Приглашение истекло или отозвано.',PROFILE_INVITATION_CHANGED:'Приглашение изменилось. Проверьте его снова.',
    PROFILE_CONFIRMATION_INVALID:'Ответ истёк, уже использован или относится к другой паре.',PROFILE_PEER_INVALID:'Ответ сервера не соответствует выбранной паре.',
    PROFILE_SELF_LINK:'Выберите другой сервер.',PROFILE_LINK_LIMIT:'Достигнут лимит связей. Дождитесь окончания срока старых записей.'};
  async function api(path,body){const r=await fetch('/api/v1/'+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',
    headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},...(body?{body:JSON.stringify(body)}:{})});
    const data=await r.json();if(!r.ok){if(r.status===401)csrf=null;throw Error(data.code||'REQUEST_FAILED');}return data;}
  async function run(fn){if(busy)return;busy=true;controls();try{await fn();}catch(e){el('links-status').textContent=messages[e.message]||'Не удалось выполнить действие. Проверьте ссылку и повторите.';}finally{busy=false;controls();}}
  function origin(raw){const u=new URL(raw);if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash||u.pathname!=='/'||u.port)throw Error('INVALID_URL');return u.origin;}
  function encode(data){return btoa(JSON.stringify(data));}
  function unpack(raw){const u=new URL(raw);if(u.protocol!=='https:'||u.username||u.password||u.pathname!=='/profile-sync/'||u.search||u.port)throw Error('INVALID_URL');
    const parts=new URLSearchParams(u.hash.slice(1));if([...parts].length!==1)throw Error('INVALID_URL');
    const kind=parts.has('link-invite')?'link-invite':'link-answer',text=parts.get(kind);if(!text||text.length>3500)throw Error('INVALID_URL');
    const value=JSON.parse(atob(text));if(value.recipient!==location.origin||origin(value.origin)!==value.origin)throw Error('INVALID_URL');
    return {kind,value};}
  function output(data,kind){const url=data.recipient+'/profile-sync/#'+kind+'='+encodeURIComponent(encode(data));
    el('links-input').value='';el('links-url').value=url;el('links-go').href=url;el('links-output').hidden=false;el('links-preview').hidden=true;preview=null;
    el('links-status').textContent=kind==='link-invite'?'Приглашение действует 10 минут. Подтвердите его на другом сервере.':'Подтверждено здесь. Вернитесь по ссылке и подтвердите пару на первом сервере.';}
  async function list(){const data=await api('me/profile-links');el('links-list').replaceChildren();
    const names={pending:'Ожидает подтверждения',exchanging:'Подтверждение не завершено',active:'Связь подтверждена',revoked:'Отозвана',expired:'Срок истёк'};
    for(const row of data.items){const li=document.createElement('li'),title=document.createElement('p');
      title.textContent=row.peer_origin+(row.peer_handle?' · '+row.peer_handle:'')+' — '+names[row.status]+(row.revocation_pending?' · отзыв не доставлен':'');li.append(title);
      if(row.peer_user_id){const id=document.createElement('small');id.textContent=row.peer_user_id;li.append(id);}
      const button=(label,action)=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',()=>run(action));li.append(b);};
      if(row.status==='active'&&row.direction==='outbound')button('Проверить связь',async()=>{const r=await api('me/profile-links/'+row.id+'/refresh',{});el('links-status').textContent=r.peer_active?'Связь действует на другом сервере.':'Связь отозвана на другом сервере.';await list();});
      if(!['expired','revoked'].includes(row.status)||row.revocation_pending)button(row.revocation_pending?'Повторить отзыв':'Отозвать',async()=>{const r=await api('me/profile-links/'+row.id+'/revoke',{});el('links-status').textContent=r.peer_notified===false?'Связь отозвана здесь. Другой сервер недоступен; повторите доставку отзыва.':'Связь отозвана здесь. Другой сервер увидит отзыв при следующей проверке.';el('links-output').hidden=true;el('links-url').value='';await list();});
      if(row.status==='active'&&(row.sync_send_allowed.length||row.sync_receive_allowed.length)){
        const status=document.createElement('p');status.textContent=(row.sync_enabled?'Автообмен включён':'Обмен приостановлен')+(row.sync_last_success?' · Последний обмен: '+new Date(row.sync_last_success).toLocaleString():' · Ещё не выполнен')+(row.sync_error?' · Не удалось выполнить обмен; будет повторная попытка':'');li.append(status);
        const options=document.createElement('details');options.className='sync-options';const summary=document.createElement('summary');summary.textContent='Разрешения';options.append(summary);li.append(options);
        const send=scopeGroup(options,'Отправлять',row.sync_send),receive=scopeGroup(options,'Принимать',row.sync_receive);
        for(const input of options.querySelectorAll('fieldset:first-of-type input'))if(!row.sync_send_allowed.includes(input.value))input.disabled=true;
        for(const input of options.querySelectorAll('fieldset:last-of-type input'))if(!row.sync_receive_allowed.includes(input.value))input.disabled=true;
        const save=document.createElement('button');save.type='button';save.textContent='Сохранить разрешения';save.addEventListener('click',()=>run(async()=>{await api('me/profile-links/'+row.id+'/sync-settings',{enabled:row.sync_enabled,send:send(),receive:receive()});await list();}));options.append(save);
        button(row.sync_enabled?'Приостановить':'Возобновить',async()=>{await api('me/profile-links/'+row.id+'/sync-settings',{enabled:!row.sync_enabled,send:row.sync_send,receive:row.sync_receive});await list();});
        if(row.direction==='outbound'&&row.sync_enabled)button('Синхронизировать',async()=>{const r=await api('me/profile-links/'+row.id+'/sync',{});el('links-status').textContent=r.complete?'Обмен завершён.':'Часть данных передана. Автообмен продолжит работу.';await list();await items();});
      }
      el('links-list').append(li);
    }
  }
  el('links-create').addEventListener('submit',e=>{e.preventDefault();run(async()=>{output(await api('me/profile-links/invite',{origin:origin(el('links-origin').value),send:getSend(),receive:getReceive()}),'link-invite');await list();});});
  el('links-import').addEventListener('submit',e=>{e.preventDefault();run(async()=>{
    preview=null;el('links-preview').hidden=true;el('links-output').hidden=true;
    const {kind,value}=unpack(el('links-input').value.trim());
    // No navigation, import, grant or network call on landing/GET; explicit submit only.
    if(kind==='link-invite'){
      const invitation={origin:value.origin,id:value.id,secret:value.secret,...(value.data?{data:true}:{})},meta=await api('me/profile-links/inspect',invitation);
      preview={kind,invitation,expected:meta};el('links-pair').textContent=meta.origin+' · '+meta.handle+' ('+meta.user_id+') ↔ '+location.origin+' · '+el('links-status').dataset.handle;
    }else{
      const confirmation={origin:value.origin,id:value.id,code:value.code,state:value.state,peer_user_id:value.peer_user_id,peer_handle:value.peer_handle,...(value.send?{send:value.send,receive:value.receive}:{})};
      preview={kind,confirmation};el('links-pair').textContent=location.origin+' · '+el('links-status').dataset.handle+' ↔ '+value.origin+' · '+value.peer_handle+' ('+value.peer_user_id+'). Аккаунт будет проверен сервером при подтверждении.';
    }
    el('links-permissions').textContent=permissionText(preview.expected?.send||value.send,preview.expected?.receive||value.receive);
    el('links-preview').hidden=false;el('links-status').textContent='Проверьте оба аккаунта и направления обмена. Пароли, роли, блокировки и влияние не передаются.';
  });});
  el('links-confirm').addEventListener('click',()=>run(async()=>{
    if(!preview)return;
    if(preview.kind==='link-invite')output(await api('me/profile-links/approve',{invitation:preview.invitation,expected:preview.expected}),'link-answer');
    else{const r=await api('me/profile-links/confirm',preview.confirmation);el('links-status').textContent=r.profile_sync?'Связь подтверждена. Автообмен включён для выбранных данных.':'Связь подтверждена без обмена данными.';el('links-preview').hidden=true;preview=null;el('links-input').value='';}
    await list();
  }));
  el('links-reload').addEventListener('click',()=>run(list));
  // Remove invite/code from history immediately; keep only in this page's input.
  function landing(){if(location.hash.startsWith('#link-')){const incoming=location.href;history.replaceState(null,'',location.pathname);
    preview=null;el('links-preview').hidden=true;el('links-output').hidden=true;el('links-url').value='';el('links-input').value=incoming;}}
  window.addEventListener('hashchange',landing);landing();
  run(async()=>{const me=await api('me');csrf=me.csrf_token;el('links-status').dataset.handle=me.handle;el('links-status').textContent='Вы вошли: '+me.handle;await list();await items();});
})();
