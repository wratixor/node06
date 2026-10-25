// Disposable installed-wheel HTTPS acceptance. Never run against production.
const assert = require('node:assert/strict');
async function check({browser, base, embed, otherSite, errors}) {
  const context = await browser.newContext({ignoreHTTPSErrors:true, locale:'en-US', viewport:{width:390,height:844}});
  const page = await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  const entry = base+'/sites/'+otherSite+'/';
  try {
    await page.goto(base+'/account/');await page.locator('#handle').fill('fixture-owner');
    await page.locator('#password').fill('fixture-test-password');await page.locator('#submit').click();
    await page.waitForFunction(()=>document.querySelector('#account-form').hidden);
    await page.goto(base+'/sites/');await page.locator(`[data-site-id="${otherSite}"]`).click();
    await page.locator('#home-source').selectOption('ui');
    async function addLanguage(tag,title) {
      await page.locator('#home-new-language').fill(tag);await page.locator('#home-language-add').click();
      await page.locator('#home-title').fill(title);
    }
    async function addBlock(title,target) {
      await page.locator('#home-add').click();
      const block=page.locator('.home-block-editor').last();
      await block.locator('.home-block-title').fill(title);await block.locator('.home-link-add').click();
      await block.locator('.home-link-label').fill(title);await block.locator('.home-link-point').selectOption(target);
    }
    await addLanguage('ru','Мир');await page.locator('#home-language-default').click();
    await addBlock('Мир','field-ru');
    await page.locator('#home-language').selectOption('und');await page.locator('#home-language-remove').click();
    await addLanguage('en','World');await addBlock('World','field-en');
    await addLanguage('ja','世界');
    await page.locator('#home-language').selectOption('ru');
    assert.equal(await page.locator('#home-title').inputValue(),'Мир','Switching editor keeps unsaved variants');
    await page.locator('#home-form button[type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Главная страница сохранена.'));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Owner editor fits mobile');
    await page.reload();await page.locator(`[data-site-id="${otherSite}"]`).click();
    await page.locator('#home-language').selectOption('en');assert.equal(await page.locator('#home-title').inputValue(),'World');
    const graphBefore=await (await page.request.get(base+'/data/points.json')).json();
    await page.goto(entry);
    const selector=page.locator('[data-home-language-select]');
    await page.waitForFunction(()=>document.querySelector('#start-page').dataset.homeCurrent==='en');
    assert.equal(await page.locator('html').getAttribute('lang'),'en');
    assert.equal(await page.locator('[data-home-language="en"] .welcome-card a').getAttribute('data-point-id'),'field-en');
    assert.equal(await page.locator('[data-home-language="ru"]').isVisible(),false);
    await selector.selectOption('ru');await page.reload();
    await page.waitForFunction(()=>document.querySelector('#start-page').dataset.homeCurrent==='ru');
    assert.equal(await page.locator('html').getAttribute('lang'),'ru');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Translated home fits mobile');
    await page.screenshot({path:'/tmp/node06-home-languages-mobile.png',fullPage:true});
    await page.locator('[data-home-language="ru"] .welcome-card a').click();
    await page.waitForURL('**/?p=field-ru&open=field-ru');
    assert.equal(new URL(page.url()).pathname,'/sites/'+otherSite+'/');
    await page.locator('#root-field').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#field-center-id')?.textContent==='field-ru');
    assert.deepEqual(await (await page.request.get(base+'/data/points.json')).json(),graphBefore);
    await page.goto(embed+'/embed/v1/'+otherSite+'/');
    await page.waitForFunction(()=>document.querySelector('#start-page').dataset.homeCurrent==='en');
    await page.locator('[data-home-language-select]').selectOption('ru');
    assert.equal(await page.locator('[data-home-language="ru"] .welcome-card a').getAttribute('href'),
      '/embed/v1/'+otherSite+'/?p=field-ru&open=field-ru');
  } finally { await context.close(); }
  for(const test of [
    {locale:'it-IT',expected:'ru'},
    {locale:'ja-JP',expected:'ja',blocked:true},
    {locale:'en-US',expected:'en',saved:'xx'},
    {locale:'en-US',expected:'ru',javaScriptEnabled:false},
  ]) {
    const ctx=await browser.newContext({ignoreHTTPSErrors:true,locale:test.locale,javaScriptEnabled:test.javaScriptEnabled??true});
    try {
      const tab=await ctx.newPage();tab.on('pageerror',error=>errors.push(error.message));
      if(test.blocked)await tab.addInitScript(()=>{Object.defineProperty(window,'localStorage',{get(){throw new DOMException('Blocked','SecurityError');}});});
      if(test.saved)await tab.addInitScript(({id,saved})=>localStorage.setItem('node06.home-language.'+id,saved),{id:otherSite,saved:test.saved});
      await tab.goto(entry);
      await tab.locator(`[data-home-language="${test.expected}"]`).waitFor({state:'visible'});
      assert.equal(await tab.locator('html').getAttribute('lang'),test.expected);
      if(test.blocked){await tab.locator('[data-home-language-select]').selectOption('en');assert(await tab.locator('[data-home-language="en"]').isVisible());}
      if(test.javaScriptEnabled===false)assert.equal(await tab.locator('[data-home-language-select]').isVisible(),false);
    } finally { await ctx.close(); }
  }
}
module.exports=check;
if(require.main===module){
 const {chromium}=require('playwright');
 (async()=>{
  const base=process.env.NODE06_PREVIEW_URL;assert(base&&new URL(base).hostname==='localhost');
  const browser=await chromium.launch({headless:true,executablePath:process.env.NODE06_BROWSER_EXECUTABLE||'/usr/bin/google-chrome'});
  try{const errors=[];await check({browser,base,embed:process.env.NODE06_EMBED_URL,otherSite:process.env.NODE06_TEST_OTHER_SITE,errors});assert.deepEqual(errors,[]);console.log('PASS: multilingual owner editor, persisted variants and distinct destinations, whole-page fallback, no JS, blocked storage, mobile and embed');}
  finally{await browser.close();}
 })().catch(error=>{console.error(error.stack||error.message);process.exitCode=1;});
}
