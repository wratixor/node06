// Disposable HTTPS, actual static UI and hidden bridge. No production account or writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
async function check({browser,base,embed,active,errors}){
 assert.equal(new URL(base).hostname,'localhost','Disposable localhost fixture only');assert(new URL(embed).hostname.endsWith('.localhost'));
 const ctx=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1100,height:850}});
 try{
  const account=await ctx.newPage();account.on('pageerror',e=>errors.push(e.message));
  await account.goto(base+'/account/');await account.locator('#handle').fill('fixture-owner');await account.locator('#password').fill('fixture-test-password');await account.locator('#submit').click();await account.waitForFunction(()=>document.querySelector('#account-form').hidden);
  const parent='https://garden.localhost',root=process.env.NODE06_BROWSER_DIST;
  await ctx.grantPermissions(['local-network-access'],{origin:parent});
  let html=fs.readFileSync(path.join(root,'index.html'),'utf8').replaceAll('https://wiki.geno-dice.com',base);
  const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
    const open=window.open.bind(window);
    window.open=(url,...args)=>{
      if(url==='about:blank')throw Error('Blank popup must never be used for subscriptions');
      if(!sessionStorage.getItem('subscription-popup-tested')){sessionStorage.setItem('subscription-popup-tested','yes');return null;}
      return open(url,...args);
    };
  });
  await page.route(parent+'/**',async route=>{
   const u=new URL(route.request().url());
   if(u.pathname==='/assets/connection.json')return route.fulfill({json:{embedOrigin:embed,serviceOrigin:base,siteId:active}});
   if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:html,headers:{'Content-Security-Policy':`default-src 'self'; script-src 'self'; connect-src 'self'; frame-src ${embed}; style-src 'self'`}});
   const file=path.join(root,u.pathname);if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return route.abort();
   return route.fulfill({contentType:u.pathname.endsWith('.js')?'application/javascript':u.pathname.endsWith('.css')?'text/css':u.pathname.endsWith('.json')?'application/json':'image/svg+xml',body:fs.readFileSync(file)});
  });
  const target=parent+'/?p=skills-ru&open=skills-ru';await page.goto(target);
  const support=()=>page.locator('#point-panel-body .point-social [data-action="support"]');
  await support().waitFor();try{await page.waitForFunction(()=>!document.querySelector('#point-panel-body [data-action=support]').disabled);}catch(e){console.error('Action status:',await page.locator('.point-action-status').allTextContents());console.error('Script errors:',errors);console.error('Summary check:',await page.evaluate(async()=>{try{const r=await window.readNode06Public('point.social',{point_id:'skills-ru'});return {schema:r.schema,id:r.id};}catch(e){return {error:e.message};}}));throw e;}
  assert.equal(await support().getAttribute('aria-pressed'),'mixed');
  // A blocked automatic launch offers a real URL; the explicit click retries
  // under a fresh user gesture without an about:blank redirect or profile hop.
  await support().click();
  const connect=page.locator('#point-panel-body .point-action-status a');await connect.waitFor();
  assert((await connect.getAttribute('href')).startsWith(base+'/embed-subscriptions/e_'));
  const popupPromise=page.waitForEvent('popup');await connect.click();const popup=await popupPromise;
  popup.on('pageerror',e=>errors.push(e.message));await popup.waitForURL(base+'/embed-subscriptions/**');
  await popup.locator('#access-allow').waitFor();await popup.waitForFunction(()=>!document.querySelector('#access-allow').disabled);
  assert.equal(await page.url(),target);
  await popup.locator('#access-allow').click();
  await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]').getAttribute('aria-pressed')==='true');
  assert(await support().evaluate(e=>e.classList.contains('active')));
  assert.equal(await page.locator('#point-editor-overlay').count(),0);assert.equal(await page.url(),target);
  await page.waitForFunction(()=>!document.querySelector('#point-panel-body [data-action=support]').disabled);
  await support().click();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]').getAttribute('aria-pressed')==='false');
  await page.waitForFunction(()=>!document.querySelector('#point-panel-body [data-action=support]').disabled);
  await support().click();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]').getAttribute('aria-pressed')==='true');
  // A partitioned grant restores highlighting without exposing the management cookie.
  await page.reload();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='true');
  const privateState=await page.evaluate(async()=>{const r=await window.node06SubscriptionRequest('subscription.read',{point_id:'skills-ru'});return r;});
  assert(privateState.subscription.active);assert(!JSON.stringify(privateState).includes('token'));assert(!JSON.stringify(privateState).includes('user_id'));
  // Same action state in the 3x3 sphere menu.
  await page.locator('#field-map .node.center circle').click({button:'right'});
  await page.waitForFunction(()=>document.querySelector('#point-context-menu [data-action=support]')?.getAttribute('aria-pressed')==='true');
  await page.keyboard.press('Escape');
  const me=await (await account.request.get(base+'/api/v1/me')).json();
  assert.equal((await account.request.post(base+'/api/v1/me/embed-subscriptions/revoke',{headers:{Origin:base,'X-CSRF-Token':me.csrf_token},data:{}})).status(),200);
  await page.reload();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='mixed');
  assert.equal(await page.url(),target);
  // Simulate denied third-party cookie storage: retain only iframe memory.
  await ctx.clearCookies({domain:new URL(embed).hostname});
  await page.route(embed+'/bridge/v1/'+active+'/subscriptions/redeem',async route=>{
    const r=await route.fetch(),headers={...r.headers()};delete headers['set-cookie'];await ctx.clearCookies({domain:new URL(embed).hostname});
    await route.fulfill({response:r,headers});
  });
  await page.reload();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='mixed');
  const secondPromise=page.waitForEvent('popup');await support().click();const second=await secondPromise;
  await second.waitForURL(base+'/embed-subscriptions/**');await second.waitForFunction(()=>!document.querySelector('#access-allow').disabled);await second.locator('#access-allow').click();
  await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='true');
  if(!second.isClosed())await second.waitForEvent('close');
  // Connecting to an existing subscription must not accidentally unsubscribe it.
  await page.waitForFunction(()=>!document.querySelector('#point-panel-body [data-action=support]').disabled);
  await support().click();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='false');
  await page.reload();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='mixed');
  const resumePromise=page.waitForEvent('popup');await support().click();const resumed=await resumePromise;await resumed.waitForURL(base+'/embed-subscriptions/**');
  // Prior consent resumes only its remaining lifetime, without another Allow click.
  await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='true');
  assert.equal(await page.url(),target);
  await account.request.post(base+'/api/v1/me/embed-subscriptions/revoke',{headers:{Origin:base,'X-CSRF-Token':me.csrf_token},data:{}});
  await page.reload();await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='mixed');
  await page.evaluate(()=>{window.open=()=>null;});
  await support().click();await page.locator('#point-panel-body .point-action-status a').waitFor();
  await page.locator('#point-panel-body .point-action-status button').click();
  await page.waitForFunction(()=>!document.querySelector('#point-panel-body [data-action=support]').disabled);
  assert.equal(await support().getAttribute('aria-pressed'),'mixed');
  assert.equal(await page.url(),target);
  assert.match(await page.locator('#point-panel-body .point-action-status').innerText(),/cancelled|отменено/);
  const guest=await browser.newContext({ignoreHTTPSErrors:true});
  try{const g=await guest.newPage();await g.goto(base+'/?p=skills-ru&open=skills-ru');
    await g.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.disabled===false);
    await g.locator('#point-panel-body [data-action=support]').click();
    await g.locator('#point-panel-body .point-action-status a').waitFor();
    assert.equal(await g.locator('#point-panel-body .point-action-status a').getAttribute('href'),base+'/account/');
    assert.equal(new URL(g.url()).pathname,'/');
  }finally{await guest.close();}
  console.log('PASS: consented static subscription, direct toggle, highlight/reload/menu, denied cookies, resume, revocation, real-URL popup retry/cancel');
 }finally{await ctx.close();}
}
module.exports=check;
if(require.main===module){const {chromium}=require('playwright');(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.NODE06_BROWSER_EXECUTABLE||'/usr/bin/google-chrome',args:['--host-resolver-rules=MAP embed.localhost 127.0.0.1']});try{const errors=[];await check({browser,base:process.env.NODE06_PREVIEW_URL,embed:process.env.NODE06_EMBED_URL,active:process.env.NODE06_TEST_ACTIVE_SITE,errors});assert.deepEqual(errors,[]);}finally{await browser.close();}})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});}
