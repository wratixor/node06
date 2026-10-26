// Disposable local fixture: explicit consent UI, private reference lists and file tools.
const assert=require('node:assert/strict');const crypto=require('node:crypto');const fs=require('node:fs');
function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));return value;}
function resign(value){delete value.digest;value.digest=crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');return value;}
async function check({browser,base,embed,errors}){
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,acceptDownloads:true,viewport:{width:390,height:844}});
 try{const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/account/');await page.locator('#handle').fill('fixture-owner');await page.locator('#password').fill('fixture-test-password');await page.locator('#submit').click();await page.waitForFunction(()=>document.querySelector('#account-form').hidden);
 await page.goto(base+'/profile-sync/');await page.waitForFunction(()=>!document.querySelector('#packet-download').disabled);
 await page.waitForFunction(()=>!document.querySelector('#links-create button').disabled);
 await page.locator('#links-origin').fill('https://peer.invalid');await page.locator('#links-create button').click();
 await page.waitForFunction(()=>!document.querySelector('#links-output').hidden);
 const invitationURL=await page.locator('#links-url').inputValue(),invitation=JSON.parse(Buffer.from(new URLSearchParams(new URL(invitationURL).hash.slice(1)).get('link-invite'),'base64').toString());
 assert.equal(invitation.recipient,'https://peer.invalid');assert.equal(invitation.secret.length,43);
 let links=await (await page.request.get(base+'/api/v1/me/profile-links')).json();assert.equal(links.items[0].status,'pending');
 assert(!JSON.stringify(links).includes(invitation.secret));
 await page.locator('#links-list button').filter({hasText:'Отозвать'}).first().click();
 await page.waitForFunction(()=>document.querySelector('#links-list').textContent.includes('Отозвана'));
 // Explicit data invitation: all scopes start off; the fragment does not contain preferences.
 assert.equal(await page.locator('#links-scopes input:checked').count(),0);
 await page.locator('#links-scopes fieldset').first().locator('input[value="color"]').check();
 await page.locator('#links-scopes fieldset').last().locator('input[value="favorites"]').check();
 await page.locator('#links-create button').click();await page.waitForFunction(()=>!document.querySelector('#links-output').hidden);
 const dataInvitation=JSON.parse(Buffer.from(new URLSearchParams(new URL(await page.locator('#links-url').inputValue()).hash.slice(1)).get('link-invite'),'base64').toString());assert.equal(dataInvitation.data,true);
 links=await (await page.request.get(base+'/api/v1/me/profile-links')).json();
 assert.deepEqual(links.items[0].sync_send_allowed,['color']);assert.deepEqual(links.items[0].sync_receive_allowed,['favorites']);
 assert(!JSON.stringify(links).includes('remote_data_token'));
 await page.locator('#links-list button').filter({hasText:'Отозвать'}).first().click();
 await page.waitForFunction(()=>[...document.querySelectorAll('#links-list li')].every(li=>li.textContent.includes('Отозвана')));
 const me=await (await page.request.get(base+'/api/v1/me')).json();
 const foreign={origin:'https://peer.invalid',point_id:'public-original',active:true};
 assert.equal((await page.request.post(base+'/api/v1/me/profile-sync/favorite',{headers:{Origin:base,'X-CSRF-Token':me.csrf_token},data:foreign})).status(),200);
 await page.locator('#sync-kind').selectOption('subscriptions');await page.waitForFunction(()=>!document.querySelector('#sync-kind').disabled);await page.locator('#sync-kind').selectOption('favorites');
 await page.locator('#sync-items a').filter({hasText:'public-original'}).waitFor();
 assert.equal(await page.locator('#sync-items a').filter({hasText:'public-original'}).getAttribute('href'),'https://peer.invalid/?p=public-original&open=public-original');
 await page.locator('#sync-items li').filter({hasText:'public-original'}).getByRole('button').click();
 await page.waitForFunction(()=>!document.querySelector('#sync-items').textContent.includes('public-original'));
 // A fragment may prefill the input, but landing never imports, approves or confirms.
 const fragment=base+'/profile-sync/#link-invite='+Buffer.from(JSON.stringify({origin:'https://peer.invalid',recipient:base,id:invitation.id,secret:invitation.secret})).toString('base64');
 let writes=0;const watch=req=>{if(req.method()==='POST'&&req.url().includes('/profile-links/'))writes++;};page.on('request',watch);
 await page.goto(fragment);await page.waitForFunction(()=>location.hash==='');await page.waitForFunction(()=>!document.querySelector('#links-create button').disabled);
 assert.equal(new URL(page.url()).hash,'');assert.equal(await page.locator('#links-input').inputValue(),fragment);assert.equal(writes,0);page.off('request',watch);
 await page.locator('details > summary').click();
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
