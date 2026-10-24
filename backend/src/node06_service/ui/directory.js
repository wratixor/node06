'use strict';
(() => {
  const el=id=>document.getElementById(id);
  let cursor=null,busy=false,mode='search',query='';
  function add(tag,text,parent){const n=document.createElement(tag);n.textContent=text;parent.append(n);return n;}
  async function load(append=false){
    if(busy)return;busy=true;
    for(const input of document.querySelectorAll('button,input,select'))input.disabled=true;
    el('directory-status').textContent='Загрузка…';
    if(!append){cursor=null;mode=el('directory-kind').value;query=el('directory-query').value.trim();el('directory-results').replaceChildren();}
    el('directory-more').hidden=true;
    const params=new URLSearchParams(mode==='search'?{q:query}:{kind:mode});
    if(cursor)params.set('after',cursor);
    const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),15000);
    try{
      const r=await fetch('/api/v1/directory/'+(mode==='search'?'users':'rankings')+'?'+params,{credentials:'omit',cache:'no-store',signal:abort.signal});
      const result=await r.json();
      if(!r.ok){if(result.code==='RANKING_CHANGED')el('directory-results').replaceChildren();throw new Error(result.code==='RANKING_CHANGED'?'Рейтинг обновился. Нажмите «Показать».':'Не удалось загрузить список.');}
      if(result.pending)el('directory-results').replaceChildren();
      for(const item of result.items){
        const li=add('li','',el('directory-results')),a=add('a',item.handle||item.preview||item.id,li);
        a.href=mode==='points'?'/?'+new URLSearchParams({p:item.id,open:item.id}):'/people/'+encodeURIComponent(item.id)+'/';
        if(item.influence!==undefined)add('span',' · '+item.influence,li);
      }
      cursor=result.next_cursor;el('directory-more').hidden=!cursor;
      el('directory-status').textContent=result.pending?'Расчёт влияния обновляется. Нажмите «Показать» немного позже.':el('directory-results').children.length?'':'Ничего не найдено.';
    }catch(e){el('directory-status').textContent=e.message||'Не удалось загрузить список.';}
    finally{clearTimeout(timer);busy=false;for(const input of document.querySelectorAll('button,input,select'))input.disabled=false;}
  }
  el('directory-form').addEventListener('submit',e=>{e.preventDefault();void load();});
  el('directory-kind').addEventListener('change',()=>{el('directory-query-label').hidden=el('directory-kind').value!=='search';void load();});
  el('directory-query').addEventListener('input',()=>{el('directory-more').hidden=true;});
  el('directory-more').addEventListener('click',()=>void load(true));
  void load();
})();
