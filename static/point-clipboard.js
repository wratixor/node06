/* Public point references only. Never reads the OS clipboard or stores account data. */
'use strict';
(() => {
  const memory=new Map(),volatile=new Set(),limit=64,idPattern=/^[a-z0-9][a-z0-9_-]{0,95}$/;
  function scope(value){try{const url=new URL(value);return /^https?:$/.test(url.protocol)&&!url.username&&!url.password?url.origin:null;}catch{return null;}}
  function clean(items){
    if(!Array.isArray(items))return [];
    const result=new Map();
    for(const item of items.slice(0,limit)){
      if(!item||typeof item.id!=='string'||item.id.trim()!==item.id||!idPattern.test(item.id)||typeof item.preview!=='string'||typeof item.url!=='string'||item.url.length>2048)continue;
      try{
        const url=new URL(item.url);
        if(!/^https?:$/.test(url.protocol)||url.username||url.password||url.searchParams.get('p')!==item.id)continue;
        url.search=new URLSearchParams({p:item.id,open:item.id});url.hash='';
        result.set(item.id,{id:item.id,preview:item.preview.slice(0,160),url:url.href});
      }catch{/* Ignore malformed public references. */}
    }
    return [...result.values()];
  }
  function read(origin){
    const server=scope(origin);if(!server)return {items:[],persistent:false};
    if(volatile.has(server))return {items:memory.get(server)||[],persistent:false};
    try{
      const raw=localStorage.getItem('node06.point-clipboard/1:'+server);
      const items=raw?clean(JSON.parse(raw)):[];memory.set(server,items);return {items,persistent:true};
    }catch{return {items:memory.get(server)||[],persistent:false};}
  }
  function write(origin,items){
    const server=scope(origin);if(!server)throw new Error('CLIPBOARD_SCOPE_REQUIRED');
    items=clean(items);memory.set(server,items);let persistent=true;
    try{localStorage.setItem('node06.point-clipboard/1:'+server,JSON.stringify(items));}catch{persistent=false;volatile.add(server);}
    window.dispatchEvent(new CustomEvent('node06:clipboard',{detail:{scope:server}}));
    return {items,persistent};
  }
  function toggle(origin,item){
    const items=read(origin).items,index=items.findIndex(pin=>pin.id===item.id);
    if(index>=0)items.splice(index,1);
    else {if(items.length>=limit)throw new Error('CLIPBOARD_LIMIT');items.push(item);}
    return write(origin,items);
  }
  window.node06PointClipboard={read,write,toggle,clean,scope,limit};
  window.addEventListener('storage',event=>{if(event.key===null||event.key?.startsWith('node06.point-clipboard/1:'))window.dispatchEvent(new Event('node06:clipboard'));});
})();
