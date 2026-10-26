/* One server account. A trusted top-level handoff never asks for site permission. */
'use strict';
(()=>{
 const b=document.body,el=id=>document.getElementById(id),peer=window.opener;
 let busy=false,finished=false;
 const status=s=>el('access-status').textContent=s;
 async function check(){
  if(busy||finished)return;busy=true;
  try{
   const r=await fetch('/api/v1/me',{credentials:'same-origin',cache:'no-store'}),me=await r.json();
   if(!r.ok)throw Error('AUTH_REQUIRED');
   el('access-login').hidden=true;el('access-check').hidden=true;
   const response=await fetch('/embed-subscriptions/'+b.dataset.request+'/approve',{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf_token},body:'{}'});
   const code=await response.json();if(!response.ok)throw Error(code.code||'FAILED');
   finished=true;if(peer)peer.postMessage({protocol:'node06-subscriptions/1',...code},b.dataset.parent);
   status('Вы вошли: '+me.handle);el('access-return').hidden=false;
  }catch(error){
   const guest=error.message==='AUTH_REQUIRED';el('access-login').hidden=!guest;el('access-check').hidden=!guest;
   status(guest?'Войдите в общий аккаунт сервера.':error.message==='SUBSCRIPTION_REQUEST_EXPIRED'?'Время входа истекло. Повторите действие на сайте.':'Не удалось проверить вход. Повторите действие на сайте.');
  }finally{busy=false;}
 }
 el('access-check').onclick=()=>void check();
 window.addEventListener('focus',()=>void check());
 window.addEventListener('message',e=>{if(e.source===peer&&e.origin===b.dataset.parent&&e.data?.protocol==='node06-subscriptions/1'&&e.data.kind==='done'&&e.data.id===b.dataset.request&&e.data.state===b.dataset.state)window.close();});
 if(window===window.top)void check();else status('Откройте вход с сайта.');
})();
