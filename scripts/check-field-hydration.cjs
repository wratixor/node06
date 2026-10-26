// Local static build, deterministic bridge fixture; no production writes.
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
const base=process.env.NODE06_PREVIEW_URL||'http://127.0.0.1:8766';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.NODE06_BROWSER_EXECUTABLE||'/usr/bin/google-chrome'});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/assets/connection.json',r=>r.abort());
  if(process.env.NODE06_FIELD_SCRIPT)await page.route('**/assets/site.js*',r=>r.fulfill({contentType:'application/javascript',body:require('node:fs').readFileSync(process.env.NODE06_FIELD_SCRIPT,'utf8')}));
  const saved=await (await fetch(base+'/data/points.json')).json();
  const sample=saved.find(p=>p.id==='field-ru');
  const ids=['field-ru','hydration-a','hydration-b','hydration-c','hydration-d'];
  const points=Object.fromEntries(ids.map((id,i)=>[id,{...sample,id,preview:id,html:'<p>'+id+'</p>',links:[...(i?[ids[i-1]]:[]),...(i+1<ids.length?[ids[i+1]]:[])]}]));
  await page.addInitScript(({points})=>{
   window.hydrationFixture={points,requests:[],failOnce:'hydration-b',delay:null};
   const read=async(method,{point_id})=>{
    if(method!=='point.read')throw Error('NOT_READY');
    const f=window.hydrationFixture;f.requests.push(point_id);
    if(f.failOnce===point_id){f.failOnce=null;throw Error('BUSY');}
    if(f.delay===point_id)await new Promise(r=>setTimeout(r,300));
    if(!f.points[point_id])throw Error('POINT_NOT_FOUND');
    return structuredClone(f.points[point_id]);
   };
   Object.defineProperty(window,'readNode06Public',{get:()=>read,set:()=>{}});
  },{points});
  const visible=()=>page.locator('#field-map .node').evaluateAll(ns=>ns.map(n=>n.dataset.id).sort());
  const waitCenter=id=>page.waitForFunction(id=>document.querySelector('#field-center-id')?.textContent===id,id);
  await page.goto(base+'/?p=field-ru&open=field-ru');await waitCenter('field-ru');
  assert.deepEqual(await visible(),ids.slice(0,3).sort()); // includes refreshed saved root and depth2
  assert.equal(await page.evaluate(()=>window.hydrationFixture.requests.filter(id=>id==='hydration-b').length),2);
  await page.locator('#field-map .node[data-id="hydration-a"] circle').click();await waitCenter('hydration-a');
  await page.waitForFunction(()=>document.querySelector('#field-map .node[data-id="hydration-c"]'));
  assert.deepEqual(await visible(),ids.slice(0,4).sort());
  // Back/forward must refresh the field, without new navigation entries.
  await page.goBack();await waitCenter('field-ru');await page.waitForFunction(()=>!document.querySelector('#field-map .node[data-id="hydration-c"]'));
  await page.goForward();await waitCenter('hydration-a');await page.waitForFunction(()=>document.querySelector('#field-map .node[data-id="hydration-c"]'));
  // A newly added edge on an already known point appears with the existing refresh button.
  await page.evaluate(()=>window.hydrationFixture.points['hydration-a'].links.push('hydration-d'));
  await page.locator('#field-refresh').click();
  await page.waitForFunction(()=>document.querySelector('#field-map .node[data-id="hydration-d"]'));
  // A failed read is visible, then retry succeeds without reloading the page.
  await page.evaluate(()=>{window.hydrationFixture.removed=window.hydrationFixture.points['hydration-c'];delete window.hydrationFixture.points['hydration-c'];});
  await page.locator('#field-refresh').click();
  await page.waitForFunction(()=>[...document.querySelectorAll('[role=status]')].some(n=>n.textContent.includes('Press refresh')));
  await page.evaluate(()=>window.hydrationFixture.points['hydration-c']=window.hydrationFixture.removed);
  await page.locator('#field-refresh').click();
  await page.waitForFunction(()=>![...document.querySelectorAll('[role=status]')].some(n=>n.textContent.includes('Press refresh')));
  // A deep link to a user point absent from the static bundle has the same depth-two field.
  await page.goto(base+'/?p=hydration-b&open=hydration-b');await waitCenter('hydration-b');
  assert.deepEqual(await visible(),ids.slice().sort());
  // A slower previous navigation cannot replace the new center's field or URL.
  await page.evaluate(()=>{window.hydrationFixture.delay='hydration-a';});
  await page.locator('#field-map .node[data-id="hydration-a"] circle').click();await waitCenter('hydration-a');
  await page.locator('#field-map .node[data-id="field-ru"] circle').click();await waitCenter('field-ru');
  await page.waitForFunction(()=>![...document.querySelectorAll('[role=status]')].some(n=>n.textContent==='Loading linked points…'));
  await page.waitForTimeout(350);
  assert.equal(new URL(page.url()).searchParams.get('p'),'field-ru');
  assert.deepEqual(await visible(),ids.slice(0,3).sort());
  assert.deepEqual(errors,[]);
  console.log('PASS: refreshed roots, depth two, transient retry, navigation/history, refresh and recovery');
 }finally{await browser.close();}
})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
