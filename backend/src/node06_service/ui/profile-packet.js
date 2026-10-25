(() => {
  'use strict';
  const el=id=>document.getElementById(id);
  let csrf=null,busy=false;
  function controls(){el('packet-download').disabled=!csrf||busy;el('packet-compare').disabled=!csrf||busy;}
  async function api(path,body){
    const response=await fetch('/api/v1/'+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',
      headers:body?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},...(body?{body:JSON.stringify(body)}:{})});
    const data=await response.json();
    if(!response.ok){if(response.status===401)csrf=null;throw new Error(data.code||'REQUEST_FAILED');}
    return data;
  }
  async function run(action){if(busy)return;busy=true;controls();try{await action();}catch(error){
    const messages={AUTH_REQUIRED:'Войдите в аккаунт на этом сервере.',INVALID_INPUT:'Проверьте формат и целостность файла.',
      PROFILE_PACKET_TOO_LARGE:'Профиль превышает лимит полного экспорта. Данные не обрезаны.',
      FILE_TOO_LARGE:'Файл слишком большой: до 60 000 байт.',AUTH_RATE_LIMITED:'Слишком много запросов. Повторите позже.'};
    el('packet-status').textContent=messages[error.message]||'Не удалось прочитать профиль.';
  }finally{busy=false;controls();}}
  el('packet-download').addEventListener('click',()=>run(async()=>{
    const data=await api('me/profile-export');const url=URL.createObjectURL(new Blob([JSON.stringify(data)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='node06-profile.json';document.body.append(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);el('packet-status').textContent='Профиль скачан. Пароли, влияние и роли в файл не входят.';
  }));
  el('packet-form').addEventListener('submit',event=>{event.preventDefault();run(async()=>{
    el('packet-result').hidden=true;const file=el('packet-file').files[0];if(!file)return;
    if(file.size>60000)throw new Error('FILE_TOO_LARGE');
    let packet;try{packet=JSON.parse(await file.text());}catch{throw new Error('INVALID_INPUT');}
    const data=await api('me/profile-compare',packet);
    el('packet-source').textContent=data.source.origin+' · '+data.source.handle;
    el('packet-color').textContent=data.color_changed?'Мой цвет отличается.':'Мой цвет совпадает.';
    const target=el('packet-differences');target.replaceChildren();
    for(const [key,title] of [['subscriptions','Подписки на точки'],['favorites','Избранное'],['own_points','Свои публичные точки']]){
      const section=document.createElement('details'),summary=document.createElement('summary'),diff=data[key];
      summary.textContent=title+' · только здесь: '+diff.only_here.length+' · только в файле: '+diff.only_in_file.length+' · отличаются: '+diff.different.length;section.append(summary);
      for(const [field,label] of [['only_here','Только здесь'],['only_in_file','Только в файле'],['different','Отличаются']]){
        if(!diff[field].length)continue;const heading=document.createElement('p');heading.textContent=label;section.append(heading);
        const list=document.createElement('ul');for(const uri of diff[field]){const item=document.createElement('li');item.textContent=uri;item.style.overflowWrap='anywhere';list.append(item);}section.append(list);
      }target.append(section);
    }
    el('packet-result').hidden=false;el('packet-status').textContent='Сравнение готово. Профиль и подписки не изменены.';
  });});
  run(async()=>{const me=await api('me');csrf=me.csrf_token;el('packet-status').textContent='Вы вошли: '+me.handle;});
})();
