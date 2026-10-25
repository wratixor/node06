'use strict';
(() => {
  const el=id=>document.getElementById(id), id=location.pathname.split('/')[2];
  const site=new URLSearchParams(location.search).get('site'),siteQuery=site?'?'+new URLSearchParams({site}):'';
  let siteBlocked=false;
  let actor=null, relation=null, pending=null, busy=false, cursor=null, needsLogin=false;
  const status=text=>{el('author-status').textContent=text;};
  async function api(path,options={}){
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
    try{const r=await fetch('/api/v1'+path,{...options,credentials:'same-origin',cache:'no-store',signal:abort.signal});const v=await r.json();if(!r.ok){const e=new Error(v.code);e.definite=r.status<500;throw e;}return v;}
    finally{clearTimeout(timer);}
  }
  function render(){
    const self=actor?.user_id===id;
    el('author-actions').hidden=!actor||self;
    el('author-login').hidden=Boolean(actor)&&!needsLogin;
    el('author-follow').textContent=relation?.following?'Отписаться':'Подписаться';
    el('author-follow').setAttribute('aria-pressed',String(Boolean(relation?.following)));
    el('author-follow').disabled=busy||!relation||relation?.blocked||Boolean(pending&&pending.kind!=='trust');
    el('author-block').textContent=relation?.blocked?'Разблокировать на сервере':'Заблокировать на сервере';
    el('author-site-block').hidden=!site||!actor||self;
    el('author-site-block').disabled=busy||!relation||Boolean(pending&&pending.kind!=='site-block');
    el('author-site-block').textContent=siteBlocked?'Разблокировать на этом сайте':'Заблокировать на этом сайте';
    el('author-site-block').setAttribute('aria-pressed',String(siteBlocked));
    el('author-block').setAttribute('aria-pressed',String(Boolean(relation?.blocked)));
    el('author-block').disabled=busy||!relation||Boolean(pending&&pending.kind!=='block');
  }
  async function points(){
    const query=new URLSearchParams();if(cursor)query.set('after',cursor);if(site)query.set('site',site);
    const page=await api('/people/'+id+'/points'+(query.size?'?'+query:''));
    for(const p of page.items){const li=document.createElement('li'),a=document.createElement('a');a.textContent=p.preview||p.id;a.href=(site?'/sites/'+encodeURIComponent(site)+'/':'/')+'?'+new URLSearchParams({p:p.id,open:p.id});li.append(a);el('author-points').append(li);}
    if(!cursor&&!page.items.length)el('author-points').textContent='Пока нет точек';
    cursor=page.next_cursor;el('author-more').hidden=!cursor;
  }
  async function act(kind){
    if(busy||!actor||actor.user_id===id)return;
    busy=true;render();
    let saved=false;
    try{
      const session=await api('/me');needsLogin=false;if(session.user_id!==actor.user_id)throw new Error('ACCOUNT_CHANGED');
      if(pending&&pending.kind!==kind)throw new Error('PENDING_REQUEST');
      pending ||= {kind,active:kind==='trust'?!relation.following:kind==='site-block'?!siteBlocked:!relation.blocked,key:crypto.randomUUID(),user:session.user_id};
      if(pending.user!==session.user_id)throw new Error('ACCOUNT_CHANGED');
      try{await api('/people/'+id+'/'+kind+(kind==='site-block'?siteQuery:''),{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token,'Idempotency-Key':pending.key},body:JSON.stringify({active:pending.active})});}
      catch(e){if(e.definite)pending=null;throw e;}
      pending=null;saved=true;relation=await api('/me/people/'+id);
      if(site)siteBlocked=(await api('/me/people/'+id+'/site-block'+siteQuery)).blocked;
      status(kind==='site-block'?(siteBlocked?'Автор скрыт в ленте этого сайта.':'Блокировка на этом сайте снята.'):relation.blocked?'Автор заблокирован. Доверие снято.':relation.following?'Вы подписаны на автора.':'Вы не подписаны на автора.');
    }catch(e){if(saved)relation=null;if(e.message==='AUTH_REQUIRED')needsLogin=true;status(saved?'Сохранено. Обновите страницу для проверки состояния.':e.message==='ACCOUNT_CHANGED'?'Аккаунт сменился. Вернитесь в исходный аккаунт.':e.message==='AUTH_REQUIRED'?'Войдите в исходный аккаунт и повторите.':e.message==='AUTHOR_BLOCKED'?'Сначала разблокируйте автора. Обновите страницу.':'Действие не подтверждено. Повторите ту же кнопку.');}
    finally{busy=false;render();}
  }
  el('author-site-block').addEventListener('click',()=>void act('site-block'));
  el('author-follow').addEventListener('click',()=>void act('trust'));
  el('author-block').addEventListener('click',()=>void act('block'));
  el('author-more').addEventListener('click',async()=>{el('author-more').disabled=true;try{await points();}catch(_){status('Не удалось загрузить точки. Повторите.');}finally{el('author-more').disabled=false;}});
  window.addEventListener('beforeunload',event=>{if(pending)event.preventDefault();});
  (async()=>{
    try{
      const p=await api('/people/'+id);el('author-name').textContent=p.handle;el('author-name').style.borderLeft='8px solid '+p.color;el('author-name').style.paddingLeft='12px';document.title=p.handle+' — Профиль';
      await points();
      try{actor=await api('/me');relation=await api('/me/people/'+id);if(site)siteBlocked=(await api('/me/people/'+id+'/site-block'+siteQuery)).blocked;status(actor.user_id===id?'Это ваш публичный профиль.':relation.blocked?'Автор заблокирован.':relation.following?'Вы подписаны на автора.':'Вы не подписаны на автора.');}
      catch(e){if(e.message!=='AUTH_REQUIRED')throw e;actor=null;status('Войдите, чтобы подписаться на автора.');}
      render();
    }catch(e){status(e.message==='USER_NOT_FOUND'?'Автор недоступен.':'Профиль не удалось загрузить. Обновите страницу.');}
  })();
})();
