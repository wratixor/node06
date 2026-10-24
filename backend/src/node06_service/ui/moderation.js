'use strict';
(() => {
  const el=id=>document.getElementById(id), args=new URLSearchParams(location.search);
  let me=null,busy=false,pending=null,scope='server',selected=null,cursor=null,userCursor=null,banCursor=null;
  const errors={SELF_BAN_FORBIDDEN:'Себя забанить нельзя.',MODERATION_TARGET_PROTECTED:'У пользователя есть полномочия в этой области. Сначала отзовите назначение.',INVALID_INPUT:'Проверьте заполнение полей.',USER_NOT_FOUND:'Активный пользователь не найден.',MODERATION_FORBIDDEN:'Нет прав в этой области.',AUTH_REQUIRED:'Войдите через раздел «Вход и безопасность».',POINT_NOT_FOUND:'Точка недоступна.',IDEMPOTENCY_CONFLICT:'Ключ операции уже использован. Перезагрузите страницу.',SCOPE_NOT_FOUND:'Сайт не найден.',INVALID_SCOPE:'Неверная область.',SELF_ROLE_CHANGE_FORBIDDEN:'Свою роль здесь изменить нельзя.'};
  function node(tag,text,parent){const item=document.createElement(tag);item.textContent=text;parent.append(item);return item;}
  function clearPrivate(){selected=null;el('detail').hidden=true;el('cases').replaceChildren();el('reports').replaceChildren();el('audit').replaceChildren();el('point-body').textContent='';el('review').hidden=true;el('roles').hidden=true;el('user-search').hidden=true;el('user-results').replaceChildren();el('users-more').hidden=true;userCursor=null;banCursor=null;el('bans').hidden=true;el('ban-results').replaceChildren();el('bans-more').hidden=true;}
  async function api(path,options={}){
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
    try{const r=await fetch('/api/v1'+path,{...options,credentials:'same-origin',cache:'no-store',signal:abort.signal});const value=await r.json();if(!r.ok){const e=new Error(value.code);e.status=r.status;throw e;}return value;}finally{clearTimeout(timer);}
  }
  async function identity(){const current=await api('/me');if(me&&current.user_id!==me.user_id){clearPrivate();throw new Error('Аккаунт изменился. Перезагрузите страницу.');}me=current;return current;}
  async function act(task){if(busy)return;busy=true;el('scope').disabled=true;el('case-state').disabled=true;el('user-query').disabled=true;for(const n of el('ban-form').querySelectorAll('input,select'))n.disabled=true;for(const b of document.querySelectorAll('button'))b.disabled=true;el('status').textContent='Загрузка…';
    try{await identity();await task();el('status').textContent='Готово.';}
    catch(e){if(e.status===401||e.status===403){clearPrivate();if(e.status===401)el('report-form').hidden=true;}el('status').textContent=errors[e.message]||((e instanceof TypeError||e.name==='AbortError')?'Нет ответа. Повторите то же действие с прежними данными.':e.message)||'Ошибка. Повторите действие.';}
    finally{busy=false;el('scope').disabled=false;el('case-state').disabled=false;el('user-query').disabled=false;for(const n of el('ban-form').querySelectorAll('input,select'))n.disabled=false;for(const b of document.querySelectorAll('button'))b.disabled=false;}
  }
  async function write(path,data){
    const fingerprint=JSON.stringify([path,data]);
    if(pending&&pending.fingerprint!==fingerprint)throw new Error('Сначала повторите незавершённое действие с прежними данными.');
    pending ||= {fingerprint,key:crypto.randomUUID()};
    try{const result=await api(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token,'Idempotency-Key':pending.key},body:JSON.stringify(data)});pending=null;return result;}
    catch(e){if(e.status&&e.status<500)pending=null;throw e;}
  }
  function path(endpoint){return '/moderation/'+endpoint+'?'+new URLSearchParams({scope});}
  async function loadCases(append=false){
    scope=el('scope').value.trim();if(!append){cursor=null;clearPrivate();}
    const result=await api(path('cases')+'&'+new URLSearchParams({status:el('case-state').value,...(cursor?{after:cursor}:{})}));
    el('review').hidden=false;el('roles').hidden=result.role!=='admin';el('user-search').hidden=false;
    if(!append)el('cases').replaceChildren();
    for(const item of result.items){const li=node('li','',el('cases')),b=node('button',item.point_id+' · '+item.reports+(item.hidden?' · скрыта':''),li);b.type='button';b.addEventListener('click',()=>void act(()=>inspect(item.point_id)));}
    cursor=result.next_cursor;el('more').hidden=!cursor;
    if(!append){await loadUsers();await loadBans();}
  }
  async function loadUsers(append=false){
    if(!append){userCursor=null;el('user-results').replaceChildren();}
    el('users-more').hidden=true;
    const result=await api(path('users')+'&'+new URLSearchParams({q:el('user-query').value.trim(),...(userCursor?{after:userCursor}:{})}));
    for(const item of result.items){
      const li=node('li','',el('user-results')),a=node(item.state==='active'?'a':'span',item.handle,li);
      if(item.state==='active')a.href='/people/'+encodeURIComponent(item.id)+'/';
      node('small',new Date(item.created_at).toLocaleString('ru-RU')+' · '+(item.state==='active'?'активен':'отключён')+' · '+item.id,li);
      if(item.state==='active'){const b=node('button','Бан',li);b.type='button';b.addEventListener('click',()=>{el('ban-user').value=item.id;el('ban-reason').focus();});}
      if(result.role==='admin'&&item.state==='active'){const b=node('button','Выбрать для доступа',li);b.type='button';b.addEventListener('click',()=>{el('role-user').value=item.id;el('roles').open=true;el('role').focus();});}
    }
    userCursor=result.next_cursor;el('users-more').hidden=!userCursor;
    if(!el('user-results').children.length)node('li','Ничего не найдено.',el('user-results'));
  }
  el('user-search-form').addEventListener('submit',e=>{e.preventDefault();void act(()=>loadUsers());});
  el('user-query').addEventListener('input',()=>{userCursor=null;el('users-more').hidden=true;});
  el('users-more').addEventListener('click',()=>void act(()=>loadUsers(true)));
  async function loadBans(append=false){
    if(!append){banCursor=null;el('ban-results').replaceChildren();}
    const p=await api(path('bans')+(banCursor?'&'+new URLSearchParams({after:banCursor}):''));
    el('bans').hidden=false;el('quarantine-link').href='/quarantine/?'+new URLSearchParams({scope});
    for(const item of p.items){const li=node('li',item.handle+' · '+(item.mode==='block'?'Запрет публикации и показа':'Карантин')+' · '+(item.expires_at?new Date(item.expires_at).toLocaleString('ru-RU'):'Бессрочно')+' · '+item.reason,el('ban-results'));const b=node('button','Изменить / отменить',li);b.type='button';b.addEventListener('click',()=>{el('ban-user').value=item.user_id;el('ban-mode').value='';el('ban-reason').value='';el('ban-reason').focus();});}
    banCursor=p.next_cursor;el('bans-more').hidden=!banCursor;
  }
  el('ban-form').addEventListener('submit',e=>{e.preventDefault();void act(async()=>{await write(path('bans/'+encodeURIComponent(el('ban-user').value)),{mode:el('ban-mode').value||null,duration_seconds:el('ban-duration').value?Number(el('ban-duration').value):null,reason:el('ban-reason').value.trim()});await loadBans();});});
  el('bans-more').addEventListener('click',()=>void act(()=>loadBans(true)));
  async function inspect(id){
    const result=await api(path('inspect/'+encodeURIComponent(id)));selected=id;el('detail').hidden=false;
    el('point-name').textContent=id;el('point-body').textContent=result.point.display_text??result.point.body??'Текст больше не опубликован.';
    el('reports').replaceChildren();for(const report of result.reports)node('li',report.reason,el('reports'));
    el('report-more').hidden=!result.reports_more;
    el('hidden-since').textContent=result.visibility?.active?'Скрыта с '+new Date(result.visibility.hidden_since).toLocaleString('ru-RU')+(scope==='server'?' · автоматическое удаление пока не включено.':' · только на этом сайте.'):'';
    el('audit').replaceChildren();for(const item of result.audit)node('li',item.created_at+' · '+item.action+' · '+item.actor_id+(item.detail.reason?' · '+item.detail.reason:''),el('audit'));
  }
  el('scope').addEventListener('input',()=>{clearPrivate();cursor=null;});
  el('scope-form').addEventListener('submit',e=>{e.preventDefault();void act(()=>loadCases());});
  el('case-state').addEventListener('change',()=>void act(()=>loadCases()));
  el('more').addEventListener('click',()=>void act(()=>loadCases(true)));
  el('report-form').addEventListener('submit',e=>{e.preventDefault();void act(async()=>{scope=el('scope').value.trim();await write(path('reports/'+encodeURIComponent(el('report-point').value)),{reason:el('report-reason').value.trim()});el('report-reason').value='';});});
  for(const [button,hidden] of [['hide-point',true],['restore-point',false]])el(button).addEventListener('click',()=>void act(async()=>{
    if(!el('visibility-form').reportValidity())return;
    await write(path('visibility/'+encodeURIComponent(selected)),{hidden,reason:el('decision-reason').value.trim()});await inspect(selected);
  }));
  el('close-case').addEventListener('click',()=>void act(async()=>{await write(path('cases/'+encodeURIComponent(selected)+'/close'),{});await loadCases();}));
  el('role-form').addEventListener('submit',e=>{e.preventDefault();void act(async()=>{await write(path('roles/'+encodeURIComponent(el('role-user').value)),{role:el('role').value||null});});});
  void act(async()=>{
    const result=await api('/moderation/scopes');
    for(const item of result.items){const option=node('option',item.name+' · '+item.role,el('scopes'));option.value=item.scope;}
    scope=args.get('scope')||result.items[0]?.scope||'server';el('scope').value=scope;
    const point=args.get('point');if(point&&/^[a-z0-9][a-z0-9_-]{0,95}$/.test(point)){el('report-point').value=point;el('report-form').hidden=false;}
    if(result.items.some(item=>item.scope===scope||item.scope==='server')){await loadCases();if(point)await inspect(point);}
  });
})();
