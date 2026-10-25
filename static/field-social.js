/* Compact point actions. Only the management origin may use personal sessions. */
"use strict";
(() => {
  if (!window.readNode06Public) return;
  const body=document.body;
  const text=(en,ru)=>document.documentElement.lang==='ru'?ru:en;
  const icons={support:'M12 20 3 11a5 5 0 0 1 9-6 5 5 0 0 1 9 6Z',block:'M5 5 14 14 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M6 6l12 12',related:'M12 4v16 M4 12h16',copy:'M9 9h11v11H9Z M15 9V4H4v11h5',remember:'M9 4H5v17h14V4h-4 M9 3h6v4H9Z M8 11h8 M8 15h8',edit:'m4 16-1 5 5-1L21 7l-4-4Z M14 6l4 4',favorite:'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9Z'};
  function node(tag,value,parent){const item=document.createElement(tag);if(value)item.textContent=value;if(parent)parent.append(item);return item;}
  function refreshActions(){for(const container of document.querySelectorAll('.point-social'))container.dispatchEvent(new Event('node06:refresh'));}
  const operations=new Map();
  function mount(container,id,displayed={}){
    if(displayed.deleted){container.remove();return;}
    container.className='point-social';container.dataset.pointId=id;
    const author=node('p','',container);author.className='point-author';
    const tools=node('div','',container);tools.className='point-actions';tools.setAttribute('role','toolbar');tools.setAttribute('aria-label',text('Point actions','Действия с точкой'));
    const status=node('p','',container);status.className='point-action-status';status.setAttribute('role','status');status.hidden=true;
    let editable=false,ticket=0,session=null,own=null,favorite=false,pin=null;
    if(!operations.has(id))operations.set(id,{busy:false,receipt:null});
    const operation=operations.get(id);
    const controls={},alive=n=>n===ticket&&container.isConnected;
    const origin=()=>window.node06ManagementOrigin?.()||body.dataset.managementOrigin||(body.dataset.hosted==='true'&&!body.dataset.searchSite?location.origin:'');
    const firstParty=()=>body.dataset.hosted==='true'&&!body.dataset.searchSite&&origin()===location.origin;
    const labels={copy:[text('Copy link','Скопировать ссылку')],remember:[text('Remember point','Запомнить точку'),text('Remove from collection','Убрать из подборки')],edit:[text('Edit point','Редактировать точку')],support:[text('Subscribe','Подписаться'),text('Unsubscribe','Отписаться')],block:[text('Block','Заблокировать'),text('Unblock','Снять блокировку')],related:[text('New related post','Новый связанный пост')],favorite:[text('Add to favorites','Добавить в избранное'),text('Remove from favorites','Удалить из избранного')]};
    function address(kind){
      const ownEdit=kind==='edit'&&firstParty()&&session?.user_id===displayed.author?.id;
      const url=new URL(kind==='related'||ownEdit?'/editor/':'/community/',origin());
      url.search=new URLSearchParams(ownEdit?{p:id,return_to:window.node06ReturnPath?.()||'/'}:kind==='related'?{from:id,return_to:window.node06ReturnPath?.()||'/'}:{p:id,intent:kind});
      return url.href;
    }
    function positionStatus(){
      const menu=container.closest('#point-context-menu');if(!menu)return;
      const box=menu.getBoundingClientRect();status.style.left=box.left+'px';status.style.width=box.width+'px';
      const height=status.getBoundingClientRect().height;
      status.style.top=(box.top-height-4>=8?box.top-height-4:Math.min(innerHeight-height-8,box.bottom+4))+'px';
    }
    function fail(message){status.hidden=false;status.textContent=message;positionStatus();}
    function pointAddress(){const url=new URL(body.dataset.fieldPath||location.pathname,location.origin);url.search=new URLSearchParams({p:id,open:id});url.hash='';return url.href;}
    function localAction(kind){
      if(kind==='copy'){
        const address=pointAddress();
        void (async()=>{try{await navigator.clipboard.writeText(address);fail(text('Link copied','Ссылка скопирована'));}
        catch{fail(text('Copy this link:','Скопируйте ссылку:'));const input=node('input','',status);input.value=address;input.readOnly=true;input.setAttribute('aria-label',text('Point address','Адрес точки'));input.focus();input.select();positionStatus();}})();
        return;
      }
      try{const result=window.node06PointClipboard.toggle(origin(),{id,preview:displayed.preview||id,url:pointAddress()});state();if(!result.persistent)fail(text('Saved for this tab; browser storage unavailable','Сохранено в этой вкладке; хранилище браузера недоступно'));}
      catch(error){fail(error.message==='CLIPBOARD_LIMIT'?text('Collection limit: 64 points','В подборке уже 64 точки'):text('Collection unavailable','Подборка недоступна'));}
    }
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
        const active=kind==='support'?Boolean(own?.subscription?.active):kind==='block'?Boolean(own?.block):kind==='favorite'?favorite:kind==='remember'?Boolean(window.node06PointClipboard?.read(origin()).items.some(pin=>pin.id===id)):false;
        const same=kind==='favorite'||kind==='related'||kind==='edit'||kind==='copy'||kind==='remember'?true:kind==='support'?own?.subscription?.content_digest===pin?.content_digest&&own?.subscription?.revision_id===pin?.revision_id:own?.block?.content_digest===pin?.content_digest&&own?.block?.revision_id===pin?.revision_id;
        control.title=labels[kind][active?1:0]||labels[kind][0];
        if(active&&!same&&kind!=='favorite')control.title=text('Confirm for current version','Подтвердить для текущей версии');
        control.setAttribute('aria-label',control.title);control.setAttribute('aria-pressed',String(active));control.classList.toggle('active',active);
        if(control.tagName==='BUTTON')control.disabled=['copy','remember'].includes(kind)?false:operation.busy||!pin||Boolean(operation.receipt&&operation.receipt.kind!==kind);
        else if(origin()){control.href=address(kind);if(kind==='edit'&&!editable)control.removeAttribute('href');}
        if(kind==='edit'){control.setAttribute('aria-disabled',String(!editable));control.tabIndex=editable?0:-1;}
      }
    }
    for(const kind of ['support','block','related','favorite','edit','copy','remember']){
      const link=kind==='related'||kind==='edit'||(!firstParty()&&!['copy','remember'].includes(kind)),control=node(link?'a':'button','',tools);controls[kind]=control;control.dataset.action=kind;
      if(link){if(origin())control.href=address(kind);control.target='_blank';control.rel='noopener noreferrer';}
      else control.type='button';
      if(kind==='related')control.classList.add('point-create-related');
      const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');
      const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[kind]);svg.append(path);control.append(svg);
      if(kind==='edit')control.addEventListener('click',event=>{if(!editable)event.preventDefault();});
      if(!link)control.addEventListener('click',()=>['copy','remember'].includes(kind)?localAction(kind):void act(kind));
    }
    const report=node('a','⚑',tools);report.className='point-report';report.title=text('Report point','Пожаловаться на точку');report.setAttribute('aria-label',report.title);
    async function reportAddress(){
      let scope=body.dataset.viewSite||body.dataset.searchSite;
      try{scope ||= (await window.node06EditorConnection?.())?.siteId;}catch{}
      if(!origin())return;const url=new URL('/moderation/',origin());url.search=new URLSearchParams({point:id,scope:scope||'server'});report.href=url.href;
    }
    void reportAddress();if(!firstParty()){report.target='_blank';report.rel='noopener noreferrer';}
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
        displayed={...displayed,author:summary.author};editable=!summary.protected;
        setAuthor(summary.author);pin={revision_id:summary.revision_id,content_digest:summary.content_digest};
        if(firstParty())await personal();if(!alive(sequence))return;
        if(displayed.content_digest&&(displayed.content_digest!==pin.content_digest||displayed.revision_id!==pin.revision_id)){
          pin=null;fail(text('Text changed. Open versions before acting.','Текст изменился. Откройте версии перед действием.'));
          const link=node('a',text('Versions','Версии'),status);link.href=address('support');link.target='_blank';link.rel='noopener noreferrer';positionStatus();
        }
        state();
      }catch(_){if(alive(sequence)){pin=null;state();fail(text('Actions unavailable. Reopen this point to retry.','Действия недоступны. Откройте точку заново.'));}}
    }
    async function act(kind){
      if(operation.busy||!pin)return;operation.busy=true;refreshActions();state();status.hidden=true;let committed=false;
      try{
        await personal();
        if(!session){location.assign(address(kind));return;}
        const active=kind==='support'?Boolean(own?.subscription?.active&&own.subscription.content_digest===pin.content_digest&&own.subscription.revision_id===pin.revision_id):kind==='block'?Boolean(own?.block&&own.block.content_digest===pin.content_digest&&own.block.revision_id===pin.revision_id):favorite;
        const path=kind==='favorite'?`/me/favorites/${id}`:`/points/${id}/${kind==='support'?'subscription':'block'}`;
        const payload=kind==='favorite'?{active:!active}:{...pin,active:!active};
        let bodyString=JSON.stringify(payload);
        if(operation.receipt&&(operation.receipt.path!==path||operation.receipt.user!==session.user_id))throw new Error('PENDING_REQUEST');
        operation.receipt ||= {path,kind,body:bodyString,user:session.user_id,key:crypto.randomUUID()};
        bodyString=operation.receipt.body;
        const response=await fetchPrivate(path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf_token,'Idempotency-Key':operation.receipt.key},body:bodyString});
        if(!response.ok){const error=await response.json();if(response.status<500)operation.receipt=null;throw new Error(error.code);}
        operation.receipt=null;committed=true;await personal();state();window.dispatchEvent(new Event('node06:reaction'));
      }catch(error){fail(committed?text('Saved. Reopen the point to refresh.','Сохранено. Откройте точку заново для обновления.'):error.message==='BALLOT_SWITCH_REQUIRED'?text('Use version voting to switch your ballot.','Смените версию явным голосом в разделе версий.'):text('Action not confirmed. Retry the same icon.','Действие не подтверждено. Повторите ту же кнопку.'));}
      finally{operation.busy=false;refreshActions();state();}
    }
    container.addEventListener('node06:clipboard-state',state);
    container.addEventListener('node06:refresh',()=>{if(!operation.busy)void load();else state();});
    void load();
  }
  window.renderNode06Social=mount;
  window.addEventListener('node06:clipboard',()=>{for(const item of document.querySelectorAll('.point-social'))item.dispatchEvent(new Event('node06:clipboard-state'));});
  let menu=null,menuSource=null;
  function closeMenu(restore=false){
    if(!menu)return;menu.remove();menu=null;
    if(restore&&menuSource?.isConnected)menuSource.focus();menuSource=null;
  }
  window.openNode06PointMenu=(point,x,y,source)=>{
    if(point.deleted){closeMenu();return;}
    closeMenu();menuSource=source;menuSource?.setAttribute('tabindex','-1');
    menu=node('section');menu.id='point-context-menu';menu.setAttribute('role','dialog');
    menu.setAttribute('aria-label',text('Point actions','Действия с точкой'));body.append(menu);
    const content=node('div','',menu);mount(content,point.id,point);
    const tools=content.querySelector('.point-actions');
    // Keep the same eight actions in a fixed nine-cell square.
    for(let i=tools.children.length;i<9;i++){const cell=node('span','',tools);cell.setAttribute('aria-hidden','true');}
    const box=menu.getBoundingClientRect();
    menu.style.left=Math.max(8,Math.min(x,innerWidth-box.width-8))+'px';
    menu.style.top=Math.max(8,Math.min(y,innerHeight-box.height-8))+'px';
    tools.querySelector('a,button')?.focus({preventScroll:true});
    menu.addEventListener('click',event=>{
      // Let the delegated editor handler open its overlay before removing the link.
      if(event.target.closest('a[href]'))queueMicrotask(()=>closeMenu());
    });
  };
  document.addEventListener('pointerdown',event=>{if(menu&&!menu.contains(event.target))closeMenu();});
  document.addEventListener('keydown',event=>{if(menu&&event.key==='Escape'){event.preventDefault();event.stopPropagation();closeMenu(true);}else if(menu&&['PageUp','PageDown','Home','End'].includes(event.key))closeMenu();},true);
  window.addEventListener('resize',()=>closeMenu());
  // Focus/layout can scroll immediately after a right-click. Dismiss only for
  // an actual scroll gesture; scrollbar clicks are covered by pointerdown.
  for(const type of ['wheel','touchmove'])window.addEventListener(type,event=>{if(menu&&!(event.target instanceof Node&&menu.contains(event.target)))closeMenu();},{capture:true,passive:true});
  window.addEventListener('node06:point',()=>closeMenu());
  window.addEventListener('node06:point',event=>{
    const field=document.querySelector('#point-panel-body .point-text');if(!field||!event.detail?.id)return;
    document.querySelector('#point-panel-body .point-social')?.remove();const container=document.createElement('section');field.before(container);mount(container,event.detail.id,event.detail);
  });
  if(body.dataset.currentPoint){const field=document.querySelector('#point-panel-body .point-text');if(field){const container=document.createElement('section');field.before(container);mount(container,body.dataset.currentPoint,{revision_id:body.dataset.currentRevision||null,content_digest:body.dataset.currentDigest});}}
})();
