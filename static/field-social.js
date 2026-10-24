/* Compact point actions. Only the management origin may use personal sessions. */
"use strict";
(() => {
  if (!window.readNode06Public) return;
  const body=document.body;
  const text=(en,ru)=>document.documentElement.lang==='ru'?ru:en;
  const icons={support:'M12 20 3 11a5 5 0 0 1 9-6 5 5 0 0 1 9 6Z',block:'M5 5 14 14 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M6 6l12 12',related:'M12 4v16 M4 12h16',favorite:'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z'};
  function node(tag,value,parent){const item=document.createElement(tag);if(value)item.textContent=value;if(parent)parent.append(item);return item;}
  function mount(container,id,displayed={}){
    container.className='point-social';container.dataset.pointId=id;
    const author=node('p','',container);author.className='point-author';
    const tools=node('div','',container);tools.className='point-actions';tools.setAttribute('role','toolbar');tools.setAttribute('aria-label',text('Point actions','Действия с точкой'));
    const status=node('p','',container);status.className='point-action-status';status.setAttribute('role','status');status.hidden=true;
    let ticket=0,session=null,own=null,favorite=false,pin=null,busy=false,receipt=null;
    const controls={},alive=n=>n===ticket&&container.isConnected;
    const origin=()=>window.node06ManagementOrigin?.()||body.dataset.managementOrigin||(body.dataset.hosted==='true'&&!body.dataset.searchSite?location.origin:'');
    const firstParty=()=>body.dataset.hosted==='true'&&!body.dataset.searchSite&&origin()===location.origin;
    const labels={support:[text('Subscribe','Подписаться'),text('Unsubscribe','Отписаться')],block:[text('Block','Заблокировать'),text('Unblock','Снять блокировку')],related:[text('New related post','Новый связанный пост')],favorite:[text('Add to favorites','Добавить в избранное'),text('Remove from favorites','Удалить из избранного')]};
    function address(kind){const url=new URL(kind==='related'?'/editor/':'/community/',origin());url.search=new URLSearchParams(kind==='related'?{from:id,return_to:window.node06ReturnPath?.()||'/'}:{p:id,intent:kind});return url.href;}
    function fail(message){status.hidden=false;status.textContent=message;}
    function setAuthor(value){
      const name=value?.kind==='source'?text('Git source','Источник Git'):value?.kind==='system'?text('System','Система'):value?.name;
      author.textContent=text('Author: ','Автор: ');
      if(value?.kind==='user'&&/^u_[0-9a-f]{32}$/.test(value.id||'')&&origin()){
        const a=node('a',name||value.id,author);a.href=new URL('/people/'+value.id+'/',origin()).href;
        if(!firstParty()){a.target='_blank';a.rel='noopener noreferrer';}
      }else author.append(document.createTextNode(name||text('Git source','Источник Git')));
    }
    function state(){
      for(const [kind,control] of Object.entries(controls)){
        const active=kind==='support'?Boolean(own?.subscription?.active):kind==='block'?Boolean(own?.block):kind==='favorite'?favorite:false;
        const same=kind==='favorite'||kind==='related'?true:kind==='support'?own?.subscription?.content_digest===pin?.content_digest&&own?.subscription?.revision_id===pin?.revision_id:own?.block?.content_digest===pin?.content_digest&&own?.block?.revision_id===pin?.revision_id;
        control.title=labels[kind][active?1:0]||labels[kind][0];
        if(active&&!same&&kind!=='favorite')control.title=text('Confirm for current version','Подтвердить для текущей версии');
        control.setAttribute('aria-label',control.title);control.setAttribute('aria-pressed',String(active));control.classList.toggle('active',active);
        if(control.tagName==='BUTTON')control.disabled=busy||!pin||Boolean(receipt&&receipt.kind!==kind);
        else if(origin())control.href=address(kind);
      }
    }
    for(const kind of ['support','block','related','favorite']){
      const link=kind==='related'||!firstParty(),control=node(link?'a':'button','',tools);controls[kind]=control;control.dataset.action=kind;
      if(link){if(origin())control.href=address(kind);control.target='_blank';control.rel='noopener noreferrer';}
      else control.type='button';
      if(kind==='related')control.classList.add('point-create-related');
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
      const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[kind]);svg.append(path);control.append(svg);
      if(!link)control.addEventListener('click',()=>void act(kind));
    }
    setAuthor(displayed.author);state();
    async function fetchPrivate(path,options={}){
      const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
      try{return await fetch('/api/v1'+path,{...options,credentials:'same-origin',cache:'no-store',signal:abort.signal});}
      finally{clearTimeout(timer);}
    }
    async function personal(){
      const response=await fetchPrivate('/me');
      if(response.status===401){session=null;own=null;favorite=false;return;}
      if(!response.ok)throw new Error('PERSONAL_UNAVAILABLE');
      const identity=await response.json();
      const results=await Promise.all([fetchPrivate(`/me/subscriptions/${id}`),fetchPrivate('/me/favorites')]);
      if(results.some(response=>!response.ok))throw new Error('PERSONAL_UNAVAILABLE');
      const [reaction,favorites]=await Promise.all(results.map(response=>response.json()));session=identity;own=reaction;favorite=favorites.items.some(item=>item.id===id);
    }
    async function load(){
      const sequence=++ticket;
      try{
        const summary=await window.readNode06Public('point.social',{point_id:id});if(!alive(sequence))return;
        if(summary.schema!=='node06-point-social/1'||summary.id!==id)throw new Error('INVALID_RESPONSE');
        setAuthor(summary.author);pin={revision_id:summary.revision_id,content_digest:summary.content_digest};
        if(firstParty())await personal();if(!alive(sequence))return;
        if(displayed.content_digest&&(displayed.content_digest!==pin.content_digest||displayed.revision_id!==pin.revision_id)){
          pin=null;fail(text('Text changed. Open versions before acting.','Текст изменился. Откройте версии перед действием.'));
          const link=node('a',text('Versions','Версии'),status);link.href=address('support');link.target='_blank';link.rel='noopener noreferrer';
        }
        state();
      }catch(_){if(alive(sequence)){pin=null;state();fail(text('Actions unavailable. Reopen this point to retry.','Действия недоступны. Откройте точку заново.'));}}
    }
    async function act(kind){
      if(busy||!pin)return;busy=true;state();status.hidden=true;let committed=false;
      try{
        await personal();
        if(!session){location.assign(address(kind));return;}
        const active=kind==='support'?Boolean(own?.subscription?.active&&own.subscription.content_digest===pin.content_digest&&own.subscription.revision_id===pin.revision_id):kind==='block'?Boolean(own?.block&&own.block.content_digest===pin.content_digest&&own.block.revision_id===pin.revision_id):favorite;
        const path=kind==='favorite'?`/me/favorites/${id}`:`/points/${id}/${kind==='support'?'subscription':'block'}`;
        const payload=kind==='favorite'?{active:!active}:{...pin,active:!active};
        let bodyString=JSON.stringify(payload);
        if(receipt&&(receipt.path!==path||receipt.user!==session.user_id))throw new Error('PENDING_REQUEST');
        receipt ||= {path,kind,body:bodyString,user:session.user_id,key:crypto.randomUUID()};
        bodyString=receipt.body;
        const response=await fetchPrivate(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token,'Idempotency-Key':receipt.key},body:bodyString});
        if(!response.ok){const error=await response.json();if(response.status<500)receipt=null;throw new Error(error.code);}
        receipt=null;committed=true;await personal();state();window.dispatchEvent(new Event('node06:reaction'));
      }catch(error){fail(committed?text('Saved. Reopen the point to refresh.','Сохранено. Откройте точку заново для обновления.'):error.message==='BALLOT_SWITCH_REQUIRED'?text('Use version voting to switch your ballot.','Смените версию явным голосом в разделе версий.'):text('Action not confirmed. Retry the same icon.','Действие не подтверждено. Повторите ту же кнопку.'));}
      finally{busy=false;state();}
    }
    void load();
  }
  window.renderNode06Social=mount;
  window.addEventListener('node06:point',event=>{
    const field=document.querySelector('#point-panel-body .point-text');if(!field||!event.detail?.id)return;
    document.querySelector('#point-panel-body .point-social')?.remove();const container=document.createElement('section');field.before(container);mount(container,event.detail.id,event.detail);
  });
  if(body.dataset.currentPoint){const field=document.querySelector('#point-panel-body .point-text');if(field){const container=document.createElement('section');field.before(container);mount(container,body.dataset.currentPoint,{revision_id:body.dataset.currentRevision||null,content_digest:body.dataset.currentDigest});}}
})();
