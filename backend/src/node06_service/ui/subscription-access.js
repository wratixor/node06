/* Trusted top-level consent; the parent receives only a PKCE-bound one-use code. */
'use strict';
(()=>{
 const b=document.body,el=id=>document.getElementById(id),peer=window.opener;
 let csrf=null,busy=false,sent=false;
 const status=s=>el('access-status').textContent=s;
 async function api(action,body){const r=await fetch('/embed-subscriptions/'+b.dataset.request+'/'+action,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw Error(data.code||'FAILED');return data;}
 async function send(action){if(busy||sent||!csrf)return;busy=true;el('access-allow').disabled=true;
  try{const code=await api(action,{});sent=true;if(peer)peer.postMessage({protocol:'node06-subscriptions/1',...code},b.dataset.parent);status('Аккаунт подключён. Вернитесь на карту — подписка применится там.');}
  catch{status('Доступ не подтверждён. Повторите подключение с карты.');}
  finally{busy=false;if(!sent)el('access-allow').disabled=false;}
 }
 async function check(){try{const r=await fetch('/api/v1/me',{credentials:'same-origin',cache:'no-store'}),me=await r.json();if(!r.ok)throw Error('AUTH_REQUIRED');csrf=me.csrf_token;
   const current=await api('info');status('Общий аккаунт сервера: '+current.handle);el('access-login').hidden=true;el('access-check').hidden=true;el('access-allow').disabled=false;el('access-revoke').disabled=false;
   if(current.can_resume)await send('resume');
  }catch(error){csrf=null;const guest=error.message==='AUTH_REQUIRED';el('access-login').hidden=!guest;el('access-check').hidden=false;status(guest?'Войдите в общий аккаунт сервера и нажмите «Продолжить после входа».':error.message==='SUBSCRIPTION_REQUEST_EXPIRED'?'Время подключения истекло. Вернитесь на карту и повторите.':'Не удалось проверить подключение. Повторите проверку.');el('access-allow').disabled=true;}
 }
 el('access-check').onclick=()=>void check();el('access-allow').onclick=()=>void send('approve');
 el('access-revoke').onclick=async()=>{if(!csrf)return;await api('revoke',{});status('Доступ отключён. Можно закрыть окно.');el('access-allow').disabled=true;};
 window.addEventListener('message',e=>{if(e.source===peer&&e.origin===b.dataset.parent&&e.data?.protocol==='node06-subscriptions/1'&&e.data.kind==='done'&&e.data.id===b.dataset.request&&e.data.state===b.dataset.state)window.close();});
 if(window===window.top)void check();else{status('Откройте подключение с карты в отдельной вкладке.');el('access-check').disabled=true;}
})();
