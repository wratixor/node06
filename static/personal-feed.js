/* Private creation feed: one occupied UTC day at a time, explicit older paging. */
'use strict';
(() => {
  const word=(ru,en,language)=>language==='ru'?ru:en;
  window.renderNode06CreationFeed=(root,{language='ru'}={})=>{
    if(root.dataset.mounted)return;root.dataset.mounted='true';
    const text=(ru,en)=>word(ru,en,language), body=document.body;
    function node(tag,value,parent=root){const n=document.createElement(tag);if(value)n.textContent=value;parent.append(n);return n;}
    const status=node('p','');status.className='creation-feed-status';status.setAttribute('role','status');
    const privateHost=body.dataset.hosted==='true'&&!body.dataset.searchSite;
    const management=window.node06ManagementOrigin?.()||body.dataset.managementOrigin;
    if(!privateHost){
      status.textContent=text('Лента доступна в вашем профиле.','Open your profile to view the feed.');
      if(management){const a=node('a',text('Лента','Feed'));a.href=new URL('/community/#feed',management).href;a.target='_blank';a.rel='noopener noreferrer';}
      return;
    }
    const controls=node('nav','');controls.className='creation-feed-controls';controls.setAttribute('aria-label',text('Даты ленты','Feed dates'));
    const newest=node('button',text('Новые','Newest'),controls),back=node('button',text('Назад','Back'),controls),older=node('button',text('Раньше','Older'),controls);
    for(const b of [newest,back,older])b.type='button';
    const heading=node('h3',''),list=node('div','');list.className='creation-feed-items';
    let actor=null,next=null,nextDay=null,busy=false,index=0,pages=[null];
    function date(value){return new Intl.DateTimeFormat(language==='ru'?'ru-RU':'en-GB',{timeZone:'UTC',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(value+'T00:00:00Z'));}
    function state(){newest.disabled=busy;back.disabled=busy||index===0;older.disabled=busy||!next;older.hidden=!next;back.hidden=index===0;older.textContent=nextDay?text('Раньше: ','Older: ')+date(nextDay):text('Раньше','Older');}
    async function api(path){
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
      try{const r=await fetch('/api/v1'+path,{credentials:'same-origin',cache:'no-store',signal:controller.signal});const v=await r.json();if(!r.ok)throw new Error(v.code);return v;}
      finally{clearTimeout(timer);}
    }
    async function load(cursor,position){
      if(busy)return;busy=true;state();status.textContent=text('Загрузка…','Loading…');
      try{
        const me=await api('/me');if(actor&&actor!==me.user_id)throw new Error('ACCOUNT_CHANGED');actor=me.user_id;
        const result=await api('/me/feed'+(cursor?'?'+new URLSearchParams({cursor}):''));
        if(!root.isConnected)return;
        if(result.viewer_id!==actor)throw new Error('ACCOUNT_CHANGED');
        list.replaceChildren();heading.textContent=result.day?date(result.day):'';
        for(const row of result.items){
          const item=node('article','',list);item.className='creation-feed-item';
          const meta=node('div','',item);meta.className='creation-feed-meta';
          if(row.author?.kind==='user'){
            const a=node('a',row.author.name,meta);a.href='/people/'+row.author.id+'/';
          }else node('span',text('Источник','Source'),meta);
          const time=node('time',new Intl.DateTimeFormat(language==='ru'?'ru-RU':'en-GB',{timeZone:'UTC',hour:'2-digit',minute:'2-digit'}).format(new Date(row.created_at)),meta);time.dateTime=row.created_at;time.title='UTC';
          const link=node('a',row.preview||row.id,item);link.className='creation-feed-point';link.href=(body.dataset.fieldPath||'/')+'?'+new URLSearchParams({p:row.id,open:row.id});
        }
        index=position;next=result.next_cursor;nextDay=result.next_day;
        status.textContent=result.items.length?'':text('Новых точек по вашим подпискам пока нет.','No new points matching your subscriptions.');
      }catch(e){
        if(e.message==='AUTH_REQUIRED'){
          list.replaceChildren();heading.textContent='';next=null;status.replaceChildren(document.createTextNode(text('Войдите, чтобы открыть ленту. ','Sign in to view your feed. ')));
          const a=node('a',text('Вход и регистрация','Sign in / register'),status);a.href='/account/';a.target='_blank';a.rel='noopener';
        }else if(e.message==='ACCOUNT_CHANGED'||e.message==='INVALID_FEED_CURSOR'){
          list.replaceChildren();heading.textContent='';next=null;status.textContent=text('Аккаунт или лента изменились. Откройте профиль заново.','Account or feed changed. Reopen your profile.');
        }else status.textContent=text('Не удалось загрузить ленту. Повторите.','Feed unavailable. Retry.');
      }finally{busy=false;state();}
    }
    newest.addEventListener('click',()=>{if(busy)return;pages=[null];void load(null,0);});
    back.addEventListener('click',()=>{if(!busy&&index>0)void load(pages[index-1],index-1);});
    older.addEventListener('click',()=>{if(busy||!next)return;pages=pages.slice(0,index+1);pages.push(next);void load(next,index+1);});
    state();void load(null,0);
  };
})();
