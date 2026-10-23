from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter(prefix="/account")
HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
}

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>NODE06 — аккаунт</title><link rel="stylesheet" href="/account/style.css">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="shortcut icon" href="/favicon.ico">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<script src="/account/client.js" defer></script></head><body><main>
<nav><a href="/">Вики</a> · <a href="/sites/">Мои сайты</a>
· <a href="/editor/">Мои точки / создать</a></nav>
<h1>Аккаунт NODE06</h1><p>Одна учётная запись для всей сети сайтов.</p>
<p id="status" role="status" aria-live="polite">Проверяем сессию…</p>
<section id="recovery-result" hidden><h2>Сохраните аварийный код</h2>
<p>Он показан один раз. Храните его отдельно от пароля: код позволяет восстановить аккаунт.
После восстановления понадобится новый код.</p>
<textarea id="saved-code" readonly aria-label="Новый аварийный код"></textarea>
<button id="dismiss-code" type="button">Код сохранён — скрыть</button></section>
<form id="account-form" hidden>
<label>Действие<select id="action"><option value="login">Вход</option>
<option value="register">Регистрация</option><option value="recover">Восстановление</option>
</select></label>
<label>Имя пользователя<input id="handle" autocomplete="username" required
pattern="[a-z0-9][a-z0-9_\\-]{2,63}" minlength="3" maxlength="64"></label>
<p>3–64 символа: строчные латинские буквы, цифры, дефис и подчёркивание.</p>
<label>Пароль<input id="password" type="password" autocomplete="current-password"
required minlength="12" maxlength="128"></label>
<p>Пароль: 12–128 символов.</p>
<label id="confirmation-label" hidden>Повторите новый пароль
<input id="confirmation" type="password" autocomplete="new-password" maxlength="128"></label>
<label id="recovery-label" hidden>Аварийный код<input id="recovery" autocomplete="off"
minlength="48" maxlength="48"></label>
<button id="submit" type="submit">Продолжить</button></form>
<section id="session-actions" hidden><button id="logout" type="button">Выйти здесь</button>
<button id="logout-all" type="button">Выйти во всех браузерах</button></section>
<noscript>Для этого интерфейса нужен JavaScript.</noscript>
</main></body></html>"""

CSS = """body{background:#090b10;color:#d7e0e8;font:17px/1.5 system-ui;margin:0}
main{max-width:620px;margin:3rem auto;padding:1rem}label{display:block;margin:1rem 0}
input,select,textarea,button{font:inherit;box-sizing:border-box;max-width:100%;padding:.6rem;
border:1px solid #8292a2;background:#131b25;color:inherit}input,select,textarea{display:block;
width:100%}button{cursor:pointer;margin:.3rem 0}button:focus-visible,input:focus-visible,
select:focus-visible,textarea:focus-visible{outline:3px solid #8ee4ea;outline-offset:2px}
[hidden]{display:none!important}#recovery-result{border:2px solid #8ee4ea;padding:1rem}
textarea{min-height:5rem;overflow-wrap:anywhere}p{overflow-wrap:anywhere}"""

SCRIPT = """'use strict';
const el=id=>document.getElementById(id);
let csrf=null,authRevision=0;
function signedIn(value){
 el('account-form').hidden=value;el('session-actions').hidden=!value;
 if(!value){csrf=null;authRevision++;}
}
function validateHandle(){
 el('handle').setCustomValidity(/^[a-z0-9][a-z0-9_-]{2,63}$/.test(el('handle').value)?'':
  'Имя: 3–64 символа, только строчные латинские буквы, цифры, дефис и подчёркивание. '+
  'Первый символ — буква или цифра. Например: wratixor.');
}
el('handle').addEventListener('input',validateHandle);
el('account-form').addEventListener('invalid',event=>{
 el('status').textContent=event.target.validationMessage;
},true);
const messages={INVALID_CREDENTIALS:'Неверное имя или пароль.',
INVALID_RECOVERY:'Аварийный код не подходит или уже использован.',
ACCOUNT_CONFLICT:'Не удалось зарегистрировать это имя. Выберите другое.',
AUTH_RATE_LIMITED:'Слишком много попыток. Повторите позже.',
AUTH_BUSY:'Сервис занят. Повторите через несколько секунд.',
AUTH_ORIGIN_NOT_CONFIGURED:'Вход ещё не настроен оператором.',
DATABASE_NOT_CONFIGURED:'Сервис аккаунтов ещё не настроен.',
AUTH_REQUIRED:'Нужно войти снова.',CSRF_REQUIRED:'Сессия изменилась. Обновите страницу.',
ORIGIN_FORBIDDEN:'Откройте управление на доверенном адресе сервиса.',
INVALID_INPUT:'Проверьте имя, пароль и аварийный код.'};
async function api(path,method='GET',data){
 const headers={}; if(data) headers['Content-Type']='application/json';
 if(csrf) headers['X-CSRF-Token']=csrf;
 const response=await fetch('/api/v1'+path,{method,headers,credentials:'same-origin',
 body:data?JSON.stringify(data):undefined,cache:'no-store'});
 const value=response.status===204?{}:await response.json();
 if(!response.ok){const error=new Error(messages[value.code]||
  'Не удалось выполнить запрос. Повторите позже.');error.code=value.code;throw error;}
 return value;
}
async function session(){
 const revision=authRevision;
 try{const value=await api('/me');if(revision!==authRevision)return null;
 csrf=value.csrf_token;signedIn(true);return value.handle;}
 catch(error){if(revision!==authRevision)return null;
 if(error.code==='AUTH_REQUIRED')signedIn(false);throw error;}
}
function mode(){
 const action=el('action').value;
 el('confirmation-label').hidden=action==='login';
 el('confirmation').required=action!=='login';
 el('recovery-label').hidden=action!=='recover';el('recovery').required=action==='recover';
 el('password').autocomplete=action==='login'?'current-password':'new-password';
}
el('action').addEventListener('change',mode);
el('dismiss-code').addEventListener('click',()=>{
 el('saved-code').value='';el('recovery-result').hidden=true;
});
el('account-form').addEventListener('submit',async event=>{
 event.preventDefault();const action=el('action').value;
 validateHandle();if(!el('account-form').reportValidity())return;
 if(action!=='login'&&el('password').value!==el('confirmation').value){
 el('status').textContent='Пароли не совпадают.';return;}
 el('submit').disabled=true;
 authRevision++;
 try{
 const data={handle:el('handle').value,password:el('password').value};
 if(action==='recover') data.recovery_code=el('recovery').value;
 const value=await api('/auth/'+action,'POST',data);
 if(action==='login'){
  try{const handle=await session();if(handle)el('status').textContent='Вход выполнен: '+handle;}
  catch{throw new Error('Браузер не сохранил сессию. '+
   'Разрешите cookies для этого сайта и войдите снова.');}
 }else{
  el('saved-code').value=value.recovery_code;el('recovery-result').hidden=false;
  el('status').textContent=action==='register'?'Аккаунт создан. Сохраните код, затем войдите.':
   'Пароль изменён, старые сессии отозваны. Сохраните новый код, затем войдите.';
  if(action==='recover')signedIn(false);
  el('action').value='login';mode();
 }
 el('password').value='';el('confirmation').value='';el('recovery').value='';
 }catch(error){el('status').textContent=error.message||'Ошибка соединения. Повторите запрос.';}
 finally{el('submit').disabled=false;}
});
for(const [id,path] of [['logout','/auth/session'],['logout-all','/auth/sessions']]){
 el(id).addEventListener('click',async()=>{authRevision++;try{await api(path,'DELETE');
 signedIn(false);el('status').textContent='Вы вышли из аккаунта.';}
 catch(error){if(error.code==='AUTH_REQUIRED')signedIn(false);
 el('status').textContent=error.message;}});
}
mode();session().then(handle=>{
 if(handle)el('status').textContent='Вы вошли: '+handle;
}).catch(error=>{
 signedIn(false);el('status').textContent=error.message;
});
window.addEventListener('focus',()=>{
 if(el('session-actions').hidden)return;
 session().then(handle=>{if(handle)el('status').textContent='Вы вошли: '+handle;})
 .catch(error=>{el('status').textContent=error.message;});
});
"""


@router.get("/", response_class=HTMLResponse)
def account_page():
    return HTMLResponse(PAGE, headers=HEADERS)


@router.get("/client.js")
def account_script():
    return Response(SCRIPT, media_type="application/javascript", headers=HEADERS)


@router.get("/style.css")
def account_styles():
    return Response(CSS, media_type="text/css", headers=HEADERS)
