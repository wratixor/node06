'use strict';
window.node06HomeEditor=({api,run,status})=>{
 const get=id=>document.getElementById(id);
 const form=get('home-form'),blocks=get('home-blocks');
 let site=null,latest=null,enabled=false,points=[];
 function element(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
 function button(text,action){const node=element('button',text);node.type='button';node.addEventListener('click',action);return node;}
 function field(parent,label,value,max,multiline=false){
  const wrap=element('label',label),input=element(multiline?'textarea':'input');input.value=value||'';
  input.maxLength=max;wrap.append(input);parent.append(wrap);return input;
 }
 function controls(){
  form.querySelectorAll('input,textarea,select,button').forEach(node=>{node.disabled=!enabled;});
  const auto=get('home-auto').checked;
  get('home-fields').querySelectorAll('input,textarea,select,button').forEach(node=>{node.disabled=!enabled||auto;});
  get('home-title').required=!auto;
  get('home-add').disabled=!enabled||auto||blocks.children.length>=12;
  get('home-count').textContent='Блоков: '+blocks.children.length+' / 12';
  for(const row of blocks.querySelectorAll('.home-link')){
   const kind=row.querySelector('.home-link-kind').value;
   row.querySelector('.home-link-point').disabled=!enabled||auto||kind!=='point';
   row.querySelector('.home-link-url').disabled=!enabled||auto||kind!=='url';
  }
  for(const node of blocks.children){
   const links=node.querySelector('.home-links');
   node.querySelector('.home-link-add').disabled=!enabled||auto||links.children.length>=8;
  }
 }
 function options(select,value){
  select.replaceChildren(element('option','Выберите точку'));select.firstChild.value='';
  const ids=new Set();
  for(const point of points){
   const option=element('option',(point.preview||point.id).replace(/^#+\s*/, '').slice(0,100));
   option.value=point.id;select.append(option);ids.add(point.id);
  }
  if(value&&!ids.has(value)){const option=element('option','Недоступная точка: '+value);option.value=value;select.append(option);}
  select.value=value||'';
 }
 function addLink(container,link={}){
  const row=element('fieldset');row.className='home-link';row.append(element('legend','Ссылка'));
  const label=field(row,'Текст ссылки',link.label,160);label.className='home-link-label';label.required=true;
  const kind=element('select');kind.className='home-link-kind';kind.setAttribute('aria-label','Куда ведёт ссылка');
  for(const [value,text] of [['point','Точка общего графа'],['url','Внешний сайт']]){const option=element('option',text);option.value=value;kind.append(option);}
  row.append(kind);kind.value=link.url?'url':'point';
  const target=element('select');target.className='home-link-point';target.setAttribute('aria-label','Точка');options(target,link.point_id);row.append(target);
  const url=field(row,'Адрес HTTP(S)',link.url,2048);url.type='url';url.className='home-link-url';
  function destination(){target.hidden=kind.value!=='point';url.parentElement.hidden=kind.value!=='url';target.required=kind.value==='point';url.required=kind.value==='url';}
  kind.addEventListener('change',()=>{destination();controls();});destination();
  row.append(button('Удалить ссылку',()=>{row.remove();controls();}));container.append(row);controls();
 }
 function addBlock(value={}){
  const node=element('fieldset');node.className='home-block-editor';node.append(element('legend','Блок'));
  const title=field(node,'Заголовок',value.title,160);title.required=true;title.className='home-block-title';
  field(node,'Описание',value.description,1500,true).className='home-block-description';
  const links=element('div');links.className='home-links';node.append(links);
  const add=button('Добавить ссылку',()=>{if(links.children.length<8)addLink(links);});add.className='home-link-add';node.append(add);
  node.append(button('Выше',()=>{if(node.previousElementSibling)blocks.insertBefore(node,node.previousElementSibling);}),
   button('Ниже',()=>{if(node.nextElementSibling)blocks.insertBefore(node.nextElementSibling,node);}),
   button('Удалить блок',()=>{node.remove();controls();}));
  blocks.append(node);for(const link of value.links||[])addLink(links,link);controls();
 }
 function fill(current){
  site=current;latest=null;get('home-conflict').hidden=true;
  const page=current.home_page;get('home-auto').checked=page===null||page===undefined;
  get('home-title').value=page?.title||current.display_name||'Главная';
  get('home-introduction').value=page?.introduction||'';
  blocks.replaceChildren();for(const block of page?.blocks||[])addBlock(block);
  get('home-preview').href='/sites/'+encodeURIComponent(current.id)+'/';controls();
 }
 function read(){
  if(get('home-auto').checked)return null;
  return {title:get('home-title').value,introduction:get('home-introduction').value,
   blocks:[...blocks.children].map(node=>({title:node.querySelector('.home-block-title').value,
    description:node.querySelector('.home-block-description').value,
    links:[...node.querySelector('.home-links').children].map(row=>({label:row.querySelector('.home-link-label').value,
     ...(row.querySelector('.home-link-kind').value==='point'?{point_id:row.querySelector('.home-link-point').value}:{url:row.querySelector('.home-link-url').value})}))}))};
 }
 async function save(expected=site?.settings_revision){
  if(!site)return;
  try{
   const result=await api('/sites/'+encodeURIComponent(site.id)+'/home','PUT',{
    expected_settings_revision:expected,home_page:read()});
   fill(result);status('Главная страница сохранена. Можно открыть её в новой вкладке.');
  }catch(error){
   if(error.status!==409)throw error;
   latest=await api('/sites/'+encodeURIComponent(site.id)+'/manage');
   get('home-server').textContent=JSON.stringify(latest.home_page,null,2);get('home-conflict').hidden=false;
   status('Настройки сайта изменились. Ваши блоки сохранены в форме; сравните с серверной версией.');
  }
 }
 form.addEventListener('submit',event=>{event.preventDefault();run(()=>save());});
 get('home-add').addEventListener('click',()=>{if(blocks.children.length<12)addBlock();});
 get('home-auto').addEventListener('change',controls);
 get('home-use-server').addEventListener('click',()=>{if(latest)fill(latest);});
 get('home-overwrite').addEventListener('click',()=>run(()=>latest&&save(latest.settings_revision)));
 return {fill,setEnabled(value){enabled=value&&!!site&&['pending','active'].includes(site.state);controls();},
  async loadPoints(){
   try{const response=await fetch('/data/points.json',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)throw new Error('graph unavailable');points=await response.json();
    for(const select of blocks.querySelectorAll('.home-link-point'))options(select,select.value);
   }catch{status('Список точек пока недоступен. Ваши блоки сохранены; повторите загрузку сайта позже.');}
  }};
};
