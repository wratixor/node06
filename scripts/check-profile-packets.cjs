// Disposable local fixture. Files only; no remote requests or profile writes.
const assert=require('node:assert/strict');const crypto=require('node:crypto');const fs=require('node:fs');
function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));return value;}
function resign(value){delete value.digest;value.digest=crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');return value;}
async function check({browser,base,embed,errors}){
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,acceptDownloads:true,viewport:{width:390,height:844}});
 try{const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/account/');await page.locator('#handle').fill('fixture-owner');await page.locator('#password').fill('fixture-test-password');await page.locator('#submit').click();await page.waitForFunction(()=>document.querySelector('#account-form').hidden);
 await page.goto(base+'/profile-sync/');await page.waitForFunction(()=>!document.querySelector('#packet-download').disabled);
 const original=await (await page.request.get(base+'/api/v1/me/geometry')).json();
 const downloadPromise=page.waitForEvent('download');await page.locator('#packet-download').click();const download=await downloadPromise;
 const file=JSON.parse(fs.readFileSync(await download.path(),'utf8'));assert.equal(file.format,'node06-profile/1');assert.equal(file.source.handle,'fixture-owner');
 const encoded=JSON.stringify(file);for(const field of ['password','csrf','static_body','roles','influence','trust'])assert(!encoded.includes(field));
 file.coordinates=[100,150,128,128,128,128];file.source.origin='https://peer.invalid';resign(file);
 await page.locator('#packet-file').setInputFiles({name:'profile.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(file))});
 await page.locator('#packet-compare').click();await page.locator('#packet-result').waitFor({state:'visible'});assert.match(await page.locator('#packet-color').textContent(),/отличается/);assert.match(await page.locator('#packet-source').textContent(),/peer.invalid/);
 assert.deepEqual(await (await page.request.get(base+'/api/v1/me/geometry')).json(),original);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:'/tmp/node06-profile-packets-mobile.png',fullPage:true});
 await page.locator('#packet-file').setInputFiles({name:'huge.json',mimeType:'application/json',buffer:Buffer.alloc(60001,32)});await page.locator('#packet-compare').click();await page.waitForFunction(()=>document.querySelector('#packet-status').textContent.includes('60 000'));assert.equal(await page.locator('#packet-result').isVisible(),false);
 file.roles=['admin'];resign(file);await page.locator('#packet-file').setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(file))});await page.locator('#packet-compare').click();await page.waitForFunction(()=>document.querySelector('#packet-status').textContent.includes('формат'));
 assert.equal((await page.request.get(embed+'/api/v1/me/profile-export')).status(),404);assert.equal((await page.request.get(embed+'/profile-sync/')).status(),404);
 await page.request.delete(base+'/api/v1/auth/session',{headers:{Origin:base,'X-CSRF-Token':(await (await page.request.get(base+'/api/v1/me')).json()).csrf_token}});
 await page.reload();await page.waitForFunction(()=>document.querySelector('#packet-status').textContent.includes('Войдите'));assert(await page.locator('#packet-download').isDisabled());
 }finally{await ctx.close();}
}
module.exports=check;
if(require.main===module){const {chromium}=require('playwright');(async()=>{const base=process.env.NODE06_PREVIEW_URL;assert(base&&new URL(base).hostname==='localhost');const browser=await chromium.launch({headless:true,executablePath:process.env.NODE06_BROWSER_EXECUTABLE||'/usr/bin/google-chrome'});try{const errors=[];await check({browser,base,embed:process.env.NODE06_EMBED_URL,errors});assert.deepEqual(errors,[]);console.log('PASS: profile download, bounded file comparison, unverified peer, unchanged color, mobile, malformed files, logout and embed isolation');}finally{await browser.close();}})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});}
