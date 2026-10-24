// Bounded public-reference storage; no browser sessions or network access.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture({readBlocked=false,writeBlocked=false}={}){
  const data=new Map(),listeners=new Map();
  const context={URL,URLSearchParams,Map,Set,Event:class{},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options?.detail;}},
    localStorage:{getItem:key=>{if(readBlocked)throw Error('blocked');return data.get(key)||null;},setItem:(key,value)=>{if(writeBlocked)throw Error('quota');data.set(key,value);}}};
  context.window={addEventListener:(type,handler)=>listeners.set(type,handler),dispatchEvent:()=>{}};
  vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/point-clipboard.js'),'utf8'),context);
  return {clipboard:context.window.node06PointClipboard,data};
}
const origin='https://service.localhost',other='https://other.localhost';
const pin=id=>({id,preview:'<script>plain text</script>',url:'https://garden.localhost/?p='+id+'&open='+id});
const {clipboard:c}=fixture();
assert.equal(c.toggle(origin,pin('point-ru')).items.length,1);
assert.equal(c.read(other).items.length,0,'Separate registrars do not share a collection');
const stripped=new URL(c.clean([{...pin('safe'),url:'https://garden.localhost/?p=safe&token=private#capability'}])[0].url);
assert.equal(stripped.searchParams.has('token'),false);assert.equal(stripped.hash,'');
assert.equal(c.read(origin+'/ignored').items.length,1,'Scope is an origin, never a path');
assert.equal(c.toggle(origin,pin('point-ru')).items.length,0,'Remember toggles without duplicates');
assert.equal(c.clean([pin('safe'),pin('safe'),{...pin('x'),url:'javascript:alert(1)'},{...pin('x'),url:'https://user:secret@host/?p=x'},pin('../bad'),{...pin('x'),url:'https://host/?p=other'}]).length,1);
for(let index=0;index<64;index++)c.toggle(origin,pin('p'+index));
assert.throws(()=>c.toggle(origin,pin('overflow')),/CLIPBOARD_LIMIT/);
const memory=fixture({readBlocked:true,writeBlocked:true}).clipboard;
assert.equal(memory.toggle(origin,pin('one')).persistent,false);
assert.equal(memory.read(origin).items.length,1,'Blocked storage keeps this page collection usable');
const quota=fixture({writeBlocked:true}).clipboard;
quota.toggle(origin,pin('two'));assert.equal(quota.read(origin).items.length,1,'Quota failure does not replace memory with stale storage');
assert.equal(c.clean([null,{},'str',{...pin('x'),preview:42}]).length,0);
console.log('PASS: clipboard scopes, deduplication, bounds, hostile references, storage denial and quota fallback');
