'use strict';
const el=id=>document.getElementById(id);
const states={pending:'Ожидает подтверждения',active:'Активен',inactive:'Неактивен'};
let csrf=null,busy=false,authenticated=false,loaded=null,latest=null,proof=null,cursor=null,embedOrigin=null;
const messages={AUTH_REQUIRED:'Нужно войти в аккаунт. Введённый текст остаётся в форме.',
 CSRF_REQUIRED:'Сессия изменилась. Проверьте вход ещё раз; ввод сохранён.',
 ORIGIN_FORBIDDEN:'Откройте управление на доверенном адресе сервиса.',
 DATABASE_NOT_CONFIGURED:'База сервиса ещё не настроена.',
 AUTH_RATE_LIMITED:'Слишком много попыток. Повторите позже.',
 SITE_FORBIDDEN:'У этого аккаунта нет прав на сайт.',SITE_NOT_FOUND:'Сайт не найден.',
 SITE_CONFLICT:'Состояние сайта изменилось. Обновите его данные.',
 SITE_CLAIM_EXPIRED:'Подтверждение истекло. Перевыпустите и загрузите новый файл.',
 SITE_ATTEMPTS_EXCEEDED:'Попытки исчерпаны. Перевыпустите и загрузите новый файл.',
 VERIFIER_BUSY:'Проверки заняты. Повторите через несколько секунд.',
 VERIFIER_TIMEOUT:'Проверка заняла слишком много времени. Проверьте доступность файла.',
 PROOF_FETCH_FAILED:'Не удалось загрузить файл. Проверьте HTTPS, адрес и публикацию.',
 PROOF_MISMATCH:'Файл не соответствует текущему подтверждению. Загрузите актуальный файл.',
 ORIGIN_INVALID:'Нужен адрес HTTPS без пути, параметров и нестандартного порта.',
 INVALID_INPUT:'Проверьте поля и параметры темы.',REQUEST_TOO_LARGE:'Слишком большой запрос.'};
function status(text){el('status').textContent=text;}
function controls(){
 document.querySelectorAll('button,input,select,textarea').forEach(node=>{
  node.disabled=busy||(!authenticated&&node.id!=='refresh');
 });
 el('more').hidden=!cursor;
 if(!loaded?.welcome_revision_id||!['pending','active'].includes(loaded.state)||loaded.welcome_source!=='ui')
  el('settings-form').querySelectorAll('button,input,textarea').forEach(b=>{b.disabled=true;});
 if(latest&&(!['pending','active'].includes(latest.state)||latest.welcome_source!=='ui'))el('save-draft').disabled=true;
}
async function api(path,method='GET',data){
 let response;try{response=await fetch('/api/v1'+path,{method,credentials:'same-origin',cache:'no-store',
  headers:{...(data?{'Content-Type':'application/json'}:{}),...(csrf?{'X-CSRF-Token':csrf}:{})},
  ...(data?{body:JSON.stringify(data)}:{})});}catch{
  throw new Error('Нет ответа сервера. Ввод сохранён. Перед повторным созданием сайта обновите список: создание могло состояться.');
 }
 let value;try{value=await response.json();}catch{
  throw new Error('Не удалось прочитать ответ сервера. Ввод сохранён. Проверьте состояние перед повтором действия.');
 }
 if(!response.ok){
  if(response.status===401){authenticated=false;csrf=null;el('session').textContent=messages.AUTH_REQUIRED;}
  const error=new Error(messages[value.code]||'Запрос не выполнен. Ввод сохранён.');
  error.code=value.code;error.status=response.status;throw error;
 }
 return value;
}
async function run(action){
 if(busy)return;busy=true;controls();
 try{await action();}catch(error){status(error.message||'Ошибка соединения. Ввод сохранён.');}
 finally{busy=false;controls();}
}
function path(){return '/sites/'+encodeURIComponent(loaded.id);}
function showProof(){
 const valid=proof&&loaded&&proof.claim_id===loaded.claim_id&&loaded.state==='pending';
 el('proof').hidden=!valid;el('download').hidden=!valid;el('proof').value=valid?proof.proof_document:'';
 el('proof-help').textContent=valid?'Скачайте или скопируйте этот файл и загрузите на свой сайт.':
  'Содержимое подтверждения не хранится на сервере. Если файл не сохранён, перевыпустите его.';
}
function showMeta(){
 el('editor').hidden=false;el('site-title').textContent=loaded.origin;
 el('site-state').textContent=(states[loaded.state]||loaded.state)+
  ' · версия настроек '+loaded.settings_revision+' · попыток '+loaded.attempt_count;
 el('pending').hidden=loaded.state!=='pending';el('active').hidden=loaded.state!=='active';
 el('proof-url').href=loaded.origin+'/node06-verification.txt';
 el('open-site').href='/sites/'+encodeURIComponent(loaded.id)+'/';
 el('embed-label').hidden=!embedOrigin;
 el('bridge-label').hidden=!embedOrigin;
 el('bridge-url').value=embedOrigin?embedOrigin+'/bridge/v1/'+encodeURIComponent(loaded.id)+'/':'';
 el('show-preview').hidden=!embedOrigin;
 el('preview').hidden=true;el('preview').removeAttribute('src');
 el('edit-note').textContent=loaded.welcome_source==='git'?'Текст управляется Git-источником.':
  loaded.state==='inactive'?'Неактивный сайт нельзя редактировать.':'';
 if(embedOrigin)el('embed-code').value='<iframe src="'+embedOrigin+'/embed/v1/'+
  encodeURIComponent(loaded.id)+'/" title="Shared wiki" width="100%" height="700" loading="lazy"></iframe>';
 showProof();
}
function fill(current){
 loaded=current;latest=null;el('conflict').hidden=true;
 el('name').value=current.display_name||'';el('body').value=current.welcome_body;
 el('theme').value=JSON.stringify(current.theme,null,2);showMeta();
}
async function list(append=false){
 const data=await api('/me/sites?limit=30'+(append&&cursor?'&after='+encodeURIComponent(cursor):''));
 if(!append)el('site-list').replaceChildren();
 for(const item of data.items){
  const li=document.createElement('li'),button=document.createElement('button');button.type='button';
  button.textContent=(item.display_name||item.origin)+' — '+(states[item.state]||item.state);
  button.dataset.siteId=item.id;
  button.addEventListener('click',()=>run(async()=>{
   fill(await api('/sites/'+encodeURIComponent(item.id)+'/manage'));status('Данные сайта загружены.');
  }));li.append(button);el('site-list').append(li);
 }
 cursor=data.next_cursor;
}
async function reconcile(){
 latest=await api(path()+'/manage');el('conflict').hidden=false;
 el('server-version').textContent=JSON.stringify({display_name:latest.display_name,
  welcome_body:latest.welcome_body,theme:latest.theme},null,2);
}
async function save(){
 if(!loaded)return;
 let theme;try{theme=JSON.parse(el('theme').value);}catch{throw new Error('Тема должна быть корректным JSON. Ввод сохранён.');}
 const data={expected_settings_revision:loaded.settings_revision,
  expected_welcome_revision:loaded.welcome_revision_id,display_name:el('name').value||null,
  welcome_body:el('body').value,theme};
 try{fill(await api(path(),'PATCH',data));status('Изменения сохранены.');}
 catch(error){if(error.status===409){await reconcile();status('Есть изменения на сервере. Сравните версии; ваш ввод сохранён.');}else throw error;}
}
el('refresh').addEventListener('click',()=>run(async()=>{
 const me=await api('/me');csrf=me.csrf_token;authenticated=true;
 el('session').textContent='Вы вошли: '+me.handle;
 const config=await api('/ui-config');embedOrigin=config.embed_origin;
 await list();if(loaded)showMeta();status('Список обновлён. Ввод в форме сохранён.');
}));
el('more').addEventListener('click',()=>run(()=>list(true)));
el('create-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
 const draft={origin:el('new-origin').value,display_name:el('new-name').value||null,
  welcome_body:el('new-body').value};
 proof=await api('/sites','POST',draft);
 // Display the one-time proof before a follow-up request can fail.
 fill({...draft,id:proof.site_id,origin:proof.origin,claim_id:proof.claim_id,state:'pending',
  settings_revision:1,welcome_revision_id:null,welcome_source:'ui',theme:{},attempt_count:0});
 status('Точка сайта создана. Сохраните файл подтверждения.');
 fill(await api('/sites/'+encodeURIComponent(proof.site_id)+'/manage'));
 status('Точка сайта создана. Теперь подтвердите владение.');
 await list();
});});
el('settings-form').addEventListener('submit',event=>{event.preventDefault();run(save);});
el('renew').addEventListener('click',()=>run(async()=>{
 proof=await api(path()+'/claim/renew','POST',{expected_claim_id:loaded.claim_id});
 loaded={...loaded,claim_id:proof.claim_id,claim_expires_at:proof.expires_at,attempt_count:0};
 showMeta();status('Подтверждение перевыпущено. Загрузите новый файл вместо старого.');
}));
el('verify').addEventListener('click',()=>run(async()=>{
 await api(path()+'/verify','POST',{});loaded={...loaded,state:'active'};showMeta();
 status('Владение подтверждено. Сайт активен.');
 await list();
}));
el('download').addEventListener('click',()=>{
 if(!proof||!loaded||proof.claim_id!==loaded.claim_id)return;
 const url=URL.createObjectURL(new Blob([proof.proof_document],{type:'text/plain;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download='node06-verification.txt';link.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
});
el('show-preview').addEventListener('click',()=>{
 if(!embedOrigin||loaded?.state!=='active')return;
 el('preview').src=embedOrigin+'/embed/v1/'+encodeURIComponent(loaded.id)+'/';
 el('preview').hidden=false;
});
el('use-server').addEventListener('click',()=>{if(latest)fill(latest);});
el('save-draft').addEventListener('click',()=>run(async()=>{
 if(!latest)return;loaded=latest;latest=null;el('conflict').hidden=true;await save();
}));
controls();el('refresh').click();
