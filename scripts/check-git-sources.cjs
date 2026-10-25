// Disposable local HTTPS fixture only. Never run against a production server.
const assert=require('node:assert/strict');
async function check({browser,base,otherSite,errors}) {
    const ownerContext=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});
    const ownerPage=await ownerContext.newPage();ownerPage.on('pageerror',error=>errors.push(error.message));
    await ownerPage.goto(base+'/account/');await ownerPage.locator('#handle').fill('fixture-owner');
    await ownerPage.locator('#password').fill('fixture-test-password');await ownerPage.locator('#submit').click();
    await ownerPage.waitForFunction(()=>document.querySelector('#account-form').hidden);
    await ownerPage.goto(base+'/sites/');
    await ownerPage.locator('[data-site-id="'+otherSite+'"]').click();
    await ownerPage.locator('#git-source summary').click();
    await ownerPage.waitForFunction(()=>document.querySelector('#git-note').textContent.includes('Подключите'));
    await ownerPage.locator('#git-repository').fill('fixture/wiki');await ownerPage.locator('#git-rights').check();
    await ownerPage.locator('#git-config button').click();
    await ownerPage.waitForFunction(()=>document.querySelector('#git-proof').textContent.includes('source_proof'));
    await ownerPage.waitForFunction(()=>!document.querySelector('#git-preview-button').disabled);
    await ownerPage.locator('#git-preview-button').click();
    await ownerPage.locator('#git-accept').waitFor({state:'visible'});
    await ownerPage.locator('#git-comparison details').evaluateAll(nodes=>nodes.forEach(n=>{n.open=true;}));
    assert((await ownerPage.locator('#git-comparison').innerText()).includes('Other fixture'));
    assert((await ownerPage.locator('#git-comparison').innerText()).includes('Git fixture home'));
    assert(await ownerPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Git preview fits mobile');
    await ownerPage.screenshot({path:'/tmp/node06-git-preview-mobile.png',fullPage:true});
    await ownerPage.locator('#git-confirm').check();
    await ownerPage.route(base+'/api/v1/sites/'+otherSite+'/source/accept',async route=>{
      const response=await route.fetch();assert.equal(response.status(),200);await route.abort();
    },{times:1});
    await ownerPage.locator('#git-accept button').click();
    await ownerPage.waitForFunction(()=>!document.querySelector('#git-accept button').disabled);
    await ownerPage.locator('#git-accept button').click();
    await ownerPage.waitForFunction(()=>document.querySelector('#status').textContent==='Корни опубликованы.');
    assert.equal(await ownerPage.locator('#settings-form button').isDisabled(),true);
    const imported=await ownerPage.request.get(base+'/api/v1/points/r_'+otherSite.slice(2)+'_idea');
    assert.equal(imported.status(),200);assert((await imported.json()).body.includes('Git browser point'));
    assert(await ownerPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Git sources fit mobile');
    await ownerPage.screenshot({path:'/tmp/node06-sources-mobile.png',fullPage:true});
    await ownerContext.close();
}
module.exports=check;
if(require.main===module){
 const {chromium}=require('playwright');
 (async()=>{
  const base=process.env.NODE06_PREVIEW_URL;
  assert(base&&['localhost','127.0.0.1'].includes(new URL(base).hostname));
  const browser=await chromium.launch({headless:true,executablePath:process.env.NODE06_BROWSER_EXECUTABLE||'/usr/bin/google-chrome'});
  try{const errors=[];await check({browser,base,otherSite:process.env.NODE06_TEST_OTHER_SITE,errors});assert.deepEqual(errors,[]);console.log('PASS: owner Git source UI, preview, lost-response retry, publication and mobile layout');}
  finally{await browser.close();}
 })().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
}
