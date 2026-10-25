'use strict';
window.node06HomeEditor=({api,run,status})=>{
 const get=id=>document.getElementById(id);
 const form=get('home-form'),blocks=get('home-blocks');
 let site=null,latest=null,enabled=false,points=[],variants={},language="und",defaultLanguage="und";
 function element(tag,text){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;}
 function button(text,action){const node=element('button',text);node.type='button';node.addEventListener('click',action);return node;}
 function field(parent,label,value,max,multiline=false){
  const wrap=element('label',label),input=element(multiline?'textarea':'input');input.value=value||'';
  input.maxLength=max;wrap.append(input);parent.append(wrap);return input;
 }
 function controls(){
  form.querySelectorAll('input,textarea,select,button').forEach(node=>{node.disabled=!enabled;});
  const auto=get('home-source').value!=='ui';
  get('home-fields').hidden=auto;
  get('home-fields').querySelectorAll('input,textarea,select,button').forEach(node=>{node.disabled=!enabled||auto;});
  get('home-title').required=!auto;
  const total=blocks.children.length+Object.entries(variants).filter(([key])=>key!==language).reduce((n,[,value])=>n+(value.blocks||[]).length,0);
  get('home-add').disabled=!enabled||auto||total>=12;
  get('home-language-add').disabled=!enabled||auto||Object.keys(variants).length>=9;
  get('home-language-remove').disabled=!enabled||auto||language===defaultLanguage;
  get('home-language-default').disabled=!enabled||auto||language===defaultLanguage;
  get('home-count').textContent='Блоков всего: '+total+' / 12';
  get('home-language-note').textContent='Основной язык: '+defaultLanguage;
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
  const page=current.home_page;
  get('home-source').value=current.home_page_source||(page?'ui':'auto');
  const names={git:'из репозитория',ui:'из настроек сайта',welcome:'приветствие'};
  const gitBlocks=current.git_home_page?[current.git_home_page,...Object.values(current.git_home_page.translations||{})].reduce((n,value)=>n+(value.blocks||[]).length,0):0;
  get('home-source-note').textContent='Сейчас показывается: '+(names[current.effective_home_source]||'приветствие')+
   '. '+(current.git_home_page?'В Git опубликовано блоков: '+gitBlocks+'.':'Главная из Git ещё не опубликована.')+
   ' Для редактирования блоков здесь выберите «Из настроек сайта».';
  defaultLanguage=page?.default_language||'und';language=defaultLanguage;
  const {translations={},default_language:ignored,...base}=page||{title:current.display_name||'Главная'};
  variants=structuredClone({[defaultLanguage]:base,...translations});
  showVariant();
  get('home-preview').href='/sites/'+encodeURIComponent(current.id)+'/';controls();
 }
 function readVariant(){
  return {title:get('home-title').value,introduction:get('home-introduction').value,
   entrance_label:get('home-entrance-label').value,all_sites_label:get('home-all-sites-label').value,
   blocks:[...blocks.children].map(node=>({title:node.querySelector('.home-block-title').value,
    description:node.querySelector('.home-block-description').value,
    links:[...node.querySelector('.home-links').children].map(row=>({label:row.querySelector('.home-link-label').value,
     ...(row.querySelector('.home-link-kind').value==='point'?{point_id:row.querySelector('.home-link-point').value}:{url:row.querySelector('.home-link-url').value})}))}))};
 }
 function showVariant(){
  const value=variants[language];
  const select=get('home-language');select.replaceChildren();
  for(const key of Object.keys(variants)){const option=element('option',key);option.value=key;select.append(option);}select.value=language;
  get('home-title').value=value.title||'';get('home-introduction').value=value.introduction||'';
  get('home-entrance-label').value=value.entrance_label||(language==='ru'?'Точка входа':'Entrance point');
  get('home-all-sites-label').value=value.all_sites_label||(language==='ru'?'Все сайты':'All sites');
  blocks.replaceChildren();for(const block of value.blocks||[])addBlock(block);controls();
 }
 function remember(){variants[language]=readVariant();}
 function read(){
  if(get('home-source').value!=='ui')return site?.home_page??null;
  remember();
  return {...variants[defaultLanguage],default_language:defaultLanguage,
   translations:Object.fromEntries(Object.entries(variants).filter(([key])=>key!==defaultLanguage))};
 }
 get('home-language').addEventListener('change',()=>{remember();language=get('home-language').value;showVariant();});
 get('home-language-add').addEventListener('click',()=>{
  const tag=get('home-new-language').value.trim();
  if(!/^[a-z]{2,8}(-[a-z0-9]{1,8})*$/i.test(tag)||tag.length>35){status('Укажите языковую метку, например ru, en или pt-BR.');return;}
  if(Object.keys(variants).some(key=>key.toLowerCase()===tag.toLowerCase())){status('Этот язык уже добавлен.');return;}
  if(Object.keys(variants).length>=9)return;
  remember();language=tag;variants[tag]={title:site.display_name||'Главная',blocks:[]};get('home-new-language').value='';showVariant();
 });
 get('home-language-default').addEventListener('click',()=>{remember();defaultLanguage=language;controls();});
 get('home-language-remove').addEventListener('click',()=>{if(language===defaultLanguage)return;delete variants[language];language=defaultLanguage;showVariant();});
 async function save(expected=site?.settings_revision){
  if(!site)return;
  try{
   const result=await api('/sites/'+encodeURIComponent(site.id)+'/home','PUT',{
    expected_settings_revision:expected,home_page:read(),home_page_source:get('home-source').value});
   fill(result);status('Главная страница сохранена. Можно открыть её в новой вкладке.');
  }catch(error){
   if(error.status!==409)throw error;
   latest=await api('/sites/'+encodeURIComponent(site.id)+'/manage');
   get('home-server').textContent=JSON.stringify({home_page_source:latest.home_page_source,home_page:latest.home_page,git_home_page:latest.git_home_page},null,2);get('home-conflict').hidden=false;
   status('Настройки сайта изменились. Ваши блоки сохранены в форме; сравните с серверной версией.');
  }
 }
 form.addEventListener('submit',event=>{event.preventDefault();run(()=>save());});
 get('home-add').addEventListener('click',()=>{if(!get('home-add').disabled)addBlock();});
 get('home-source').addEventListener('change',controls);
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
