'use strict';
window.node06GitSources=({api,run,status,changed})=>{
 const el=id=>document.getElementById(id);let site=null,source=null,enabled=false,sequence=0;
 const codes={INVALID_GITHUB_SOURCE:'Введите owner/repository и имя ветки.',SOURCE_BINDING_CHANGED:'Привязка владельца или адреса изменилась. Нужна проверка администратором.',FILE_MISSING:'Не найден manifest или указанный в нём файл.',SOURCE_CHANGED:'Источник изменился. Загрузите его заново.',SOURCE_PROOF_REQUIRED:'Опубликуйте актуальный source_proof в manifest и проверьте снова.',
 SOURCE_PREVIEW_STALE:'Сайт изменился после предпросмотра. Загрузите новый.',SOURCE_PREVIEW_EXPIRED:'Предпросмотр истёк. Загрузите новый.',SOURCE_IDENTITY_CHANGED:'Владелец или идентификатор репозитория изменился. Перевыпустите подтверждение.',
 SOURCE_RATE_LIMITED:'Повторная загрузка доступна через минуту.',SOURCE_OPERATOR_MANAGED:'Этот источник обновляется через деплой.',GITHUB_UNAVAILABLE:'GitHub недоступен или ограничил запросы. Опубликованные точки сохранены.'};
 const path=()=>'/sites/'+encodeURIComponent(site.id)+'/source';
 async function call(suffix='',method='GET',data){try{return await api(path()+suffix,method,data);}catch(e){if(codes[e.code])e.message=codes[e.code];throw e;}}
 function controls(){el('git-source').querySelectorAll('input,select,button').forEach(n=>n.disabled=!enabled);if(!source?.configured)el('git-preview-button').disabled=true;}
 function text(parent,tag,value){const n=document.createElement(tag);n.textContent=value;parent.append(n);return n;}
 function render(){
  el('git-config').hidden=Boolean(source?.operator_managed);el('git-actions').hidden=!source?.configured;
  el('git-note').textContent=source?.operator_managed?'Источник управляется через деплой.':source?.verified?'Репозиторий подтверждён.':source?.configured?'Нужно подтвердить репозиторий.':'Подключите публичный репозиторий с node06-roots.json.';
  if(source?.last_error)el('git-note').textContent+=' '+(codes[source.last_error]||source.last_error);
  if(source?.configured){el('git-repository').value=source.repository;el('git-branch').value=source.branch;el('git-policy').value=source.policy;el('git-current-policy').value=source.policy;}
  const box=el('git-comparison');box.replaceChildren();
  if(source?.preview){
   text(box,'p','Коммит: '+source.preview.commit_sha);
   if(JSON.stringify(source.preview.home_before)!==JSON.stringify(source.preview.home_after)){const d=document.createElement('details');box.append(d);text(d,'summary','Главная');text(d,'strong','Сейчас');text(d,'pre',JSON.stringify(source.preview.home_before,null,2));text(d,'strong','Новая версия');text(d,'pre',JSON.stringify(source.preview.home_after,null,2));}
   for(const point of source.preview.comparison){const details=document.createElement('details');box.append(details);text(details,'summary',point.id);text(details,'strong','Сейчас');text(details,'pre',point.before);text(details,'strong','Новая версия');text(details,'pre',point.after);}
   if(source.preview.retired.length)text(box,'p','Убираются из публикации: '+source.preview.retired.join(', '));
  }
  el('git-accept').hidden=!source?.preview;el('git-confirm').checked=false;controls();
 }
 async function load(){const token=sequence,info=await call();if(token!==sequence)return;source=info;render();}
 el('git-source').addEventListener('toggle',()=>{if(el('git-source').open&&site)run(load);});
 el('git-config').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
  const proof=await call('','PUT',{repository:el('git-repository').value.trim(),branch:el('git-branch').value.trim(),policy:el('git-policy').value,expected_generation:source?.generation||null,rights_confirmed:el('git-rights').checked});
  el('git-proof').textContent=JSON.stringify({source_proof:proof.source_proof},null,2);
  await load();status('Добавьте source_proof в node06-roots.json и сделайте commit. Затем загрузите предпросмотр.');
 });});
 el('git-preview-button').addEventListener('click',()=>run(async()=>{
  await call('/preview','POST',{generation:source.generation});await load();status('Предпросмотр готов. Публикация ещё не выполнена.');
 }));
 el('git-accept').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
  await call('/accept','POST',{generation:source.generation,preview_id:source.preview.id,accept_git_welcome:el('git-confirm').checked});
  el('git-proof').textContent='';await changed();status('Корни опубликованы.');
 });});
 el('git-policy-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
  await call('/policy','PUT',{generation:source.generation,policy:el('git-current-policy').value});await load();status('Режим обновления сохранён.');
 });});
 return {fill(value){site=value;source=null;sequence++;el('git-source').open=false;el('git-source').hidden=value.state!=='active';el('git-proof').textContent='';render();},setEnabled(value){enabled=value;controls();}};
};
