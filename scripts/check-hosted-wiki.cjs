// Local disposable fixture only. This creates test accounts/sites; never run on production.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.NODE06_PREVIEW_URL || 'https://localhost:8846';
const embed = process.env.NODE06_EMBED_URL || 'https://embed.localhost:8847';
const active = process.env.NODE06_TEST_ACTIVE_SITE;
const otherSite=process.env.NODE06_TEST_OTHER_SITE;
for (const url of [base, embed]) {
  const host = new URL(url).hostname;
  assert(host === 'localhost' || host.endsWith('.localhost') || host === '127.0.0.1', 'Local fixtures only');
}
assert(active && /^s_[0-9a-f]{32}$/.test(active), 'Set NODE06_TEST_ACTIVE_SITE from the local fixture');

(async () => {
  const browser = await chromium.launch({ headless: true,
    executablePath: process.env.NODE06_BROWSER_EXECUTABLE || '/usr/bin/google-chrome',
    args: ['--host-resolver-rules=MAP embed.localhost 127.0.0.1'] });
  try {
    const context = await browser.newContext({ ignoreHTTPSErrors: true, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    async function waitGeometry(pid,color){
      const deadline=Date.now()+45000;
      while(Date.now()<deadline){
        const response=await page.request.get(base+'/api/v1/geometry?'+new URLSearchParams({ids:pid}));
        assert.equal(response.status(),200);
        const data=await response.json();
        if(!data.pending&&data.items[0]?.color===color)return;
        await page.waitForTimeout(500);
      }
      throw new Error('Geometry snapshot did not converge: '+pid+' '+color);
    }
    const errors = [];
    const embedCookies = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.url().startsWith(embed + '/'))
        embedCookies.push(request.allHeaders().then(headers => Boolean(headers.cookie)));
    });
    const handle = 'browser-' + Date.now();
    const password = 'browser-test-password';
    await page.goto(base + '/account/');
    await page.locator('#action').selectOption('register');
    await page.locator('#handle').fill(handle);
    await page.locator('#password').fill(password);
    await page.locator('#confirmation').fill(password);
    let registrations = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/v1/auth/register')) registrations++;
    });
    await page.locator('#handle').fill(handle.toUpperCase());
    await page.locator('#submit').click();
    assert((await page.locator('#status').textContent()).includes('строчные латинские'));
    assert.equal(registrations, 0, 'Invalid uppercase name must not reach registration API');
    assert.equal(await page.locator('#handle').inputValue(), handle.toUpperCase());
    assert.equal(await page.locator('#password').inputValue(), password);
    await page.locator('#handle').fill(handle);
    assert.equal(await page.locator('#handle').evaluate(input => input.validity.valid), true,
      'Browser Unicode-v pattern must accept a valid hyphenated lowercase name');
    await page.locator('#submit').click();
    await page.locator('#recovery-result').waitFor({ state: 'visible' });
    await page.locator('#password').fill(password);
    await page.locator('#submit').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Вход выполнен:'));
    assert.equal(await page.locator('#account-form').isVisible(), false);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Вы вошли:'));
    assert.equal(await page.locator('#account-form').isVisible(), false);
    for (const logout of ['#logout', '#logout-all']) {
      await page.locator(logout).click();
      await page.locator('#account-form').waitFor({ state: 'visible' });
      assert.equal(await page.locator('#session-actions').isVisible(), false);
      await page.locator('#handle').fill(handle);
      await page.locator('#password').fill(password);
      await page.locator('#submit').click();
      await page.waitForFunction(() => document.querySelector('#account-form').hidden);
    }
    // A session revoked elsewhere must restore the form on returning to this tab.
    const session = await (await page.request.get(base + '/api/v1/me')).json();
    assert.equal((await page.request.delete(base + '/api/v1/auth/session', {
      headers: { Origin: base, 'X-CSRF-Token': session.csrf_token }
    })).status(), 204);
    await page.evaluate(() => window.dispatchEvent(new Event('focus')));
    await page.locator('#account-form').waitFor({ state: 'visible' });
    await page.locator('#password').fill(password);
    await page.locator('#submit').click();
    await page.waitForFunction(() => document.querySelector('#account-form').hidden);
    // First-party authoring works for an ordinary user before any site registration.
    await page.goto(base + '/editor/');
    await page.locator('#editor-form').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#point-lang').count(),0);
    assert.equal(await page.locator('#editor-form input').count(),0);
    assert((await page.locator('#tag-tools').boundingBox()).y < (await page.locator('#point-body').boundingBox()).y);
    assert(await page.evaluate(()=>document.querySelector('#editor-form').lastElementChild.id === 'publish'));
    await page.locator('#point-body').fill('воля');
    await page.locator('#point-body').evaluate(input => input.setSelectionRange(0, input.value.length));
    await page.locator('#link-word').click();
    await page.locator('#point-picker-query').fill('skills-ru');
    await page.locator('#point-picker-results [data-point-id=skills-ru] button').click();
    await page.waitForFunction(()=>document.querySelector('#point-body').value.includes('md://point/skills-ru'));
    assert.equal(await page.locator('#point-body').inputValue(), '[воля](md://point/skills-ru)');
    assert.equal(await page.locator('#point-picker-query').evaluate(e=>getComputedStyle(e).borderRadius), '0px');
    assert.equal(await page.locator('#tag-search .point-search').count(), 1);
    await page.getByRole('button', {name:'☆ Сохранить тег',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#editor-status').textContent.includes('Тег сохранён'));
    assert((await page.locator('#favorite-tags').innerText()).includes('Навык'));
    // Commit succeeds but response is lost: the same draft retries the same receipt.
    await page.route(base + '/api/v1/points', async route => {
      const response = await route.fetch();
      assert.equal(response.status(), 201);
      await route.abort();
    }, { times: 1 });
    await page.locator('#publish').click();
    await page.waitForFunction(() => !document.querySelector('#publish').disabled);
    assert((await page.locator('#editor-status').textContent()).includes('Текст сохранён'));
    await page.locator('#publish').click();
    await page.waitForURL(url=>url.pathname==='/'&&url.searchParams.has('open'));
    const authoredId = new URL(page.url()).searchParams.get('p');
    assert(/^p_[0-9a-f]{32}$/.test(authoredId));
    assert.equal((await (await page.request.get(base+'/api/v1/points/'+authoredId)).json()).lang,'und');
    assert.equal((await (await page.request.get(base + '/api/v1/me/points')).json()).items.length, 1);
    const authored = await (await page.request.get(base + '/api/v1/points/' + authoredId)).json();
    const graph = await (await page.request.get(base + '/data/points.json')).json();
    assert(graph.find(point => point.id === authoredId).links.includes('skills-ru'));
    assert(graph.find(point => point.id === 'skills-ru').links.includes(authoredId));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Editor fits mobile');
    await page.screenshot({ path: '/tmp/node06-editor-mobile.png', fullPage: true });
    await page.goto(base+'/editor/?p='+authoredId);
    await page.locator('#editor-form').waitFor({state:'visible'});
    const authorSession = await (await page.request.get(base + '/api/v1/me')).json();
    const pin = await (await page.request.get(base + '/api/v1/points/skills-ru')).json();
    assert.equal((await page.request.patch(base + '/api/v1/points/' + authoredId, {
      headers: { Origin: base, 'X-CSRF-Token': authorSession.csrf_token, 'Idempotency-Key': 'browser-update-key' },
      data: { body: 'New version elsewhere', lang: 'en', expected_revision_id: authored.revision_id,
        links: [{ id: pin.id, revision_id: pin.revision_id, content_digest: pin.content_digest }] }
    })).status(), 200);
    await page.locator('#point-body').fill('Unsaved local version');
    await page.locator('#publish').click();
    await page.waitForFunction(() => !document.querySelector('#publish').disabled);
    assert((await page.locator('#editor-status').textContent()).includes('Точка уже изменена'));
    assert.equal(await page.locator('#point-body').inputValue(), 'Unsaved local version');
    page.once('dialog',dialog=>dialog.accept());
    await page.reload();
    await page.locator('#editor-form').waitFor({state:'visible'});
    await page.locator('#point-body').fill('Edited without a language selector');
    await page.locator('#publish').click();
    await page.waitForURL(url=>url.pathname==='/'&&url.searchParams.get('open')===authoredId);
    assert.equal((await (await page.request.get(base+'/api/v1/points/'+authoredId)).json()).lang,'en');
    await page.goto(base+'/editor/?p='+authoredId);
    await page.locator('#editor-form').waitFor({state:'visible'});
    await page.locator('#point-body').fill('Unsaved after metadata-preserving edit');

    page.once('dialog', dialog => dialog.accept());
    await page.goto(base + '/sites/');

    await page.waitForFunction(() => !document.querySelector('#new-origin').disabled);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Management must fit 390px');
    await page.locator('#new-origin').fill('https://' + handle + '.example');
    await page.locator('#new-name').fill('My test garden');
    await page.locator('#new-body').fill('Привет / Hello / 言葉');
    await page.locator('#create-form button').click();
    await page.locator('#site-list button').first().waitFor();
    const id = await page.locator('#site-list button').first().getAttribute('data-site-id');
    const proof = await page.locator('#proof').inputValue();
    assert(proof.includes('site=' + id));
    const downloadPromise = page.waitForEvent('download');
    await page.locator('#download').click();
    const download = await downloadPromise;
    assert.equal(download.suggestedFilename(), 'node06-verification.txt');
    const stream = await download.createReadStream();
    const chunks = [];
    for await (const chunk of stream) chunks.push(chunk);
    assert.equal(Buffer.concat(chunks).toString(), proof);
    await page.locator('#renew').click();
    await page.waitForFunction(old => document.querySelector('#proof').value !== old, proof);
    assert.equal(await page.locator('#pending').isVisible(), true);
    // A server conflict must preserve typed text and require explicit reconciliation.
    await page.locator('#body').fill('My unsaved meaning');
    const me = await (await page.request.get(base + '/api/v1/me')).json();
    const current = await (await page.request.get(base + `/api/v1/sites/${id}/manage`)).json();
    const other = await page.request.patch(base + `/api/v1/sites/${id}`, {
      headers: { Origin: base, 'X-CSRF-Token': me.csrf_token },
      data: { expected_settings_revision: current.settings_revision,
        expected_welcome_revision: current.welcome_revision_id, display_name: 'Other name',
        welcome_body: 'Changed in another tab', theme: {} }
    });
    assert.equal(other.status(), 200);
    await page.locator('#settings-form button').click();
    await page.locator('#conflict').waitFor({ state: 'visible' });
    assert.equal(await page.locator('#body').inputValue(), 'My unsaved meaning');
    assert((await page.locator('#server-version').textContent()).includes('Changed in another tab'));
    await page.locator('#save-draft').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent === 'Изменения сохранены.');
    assert.equal(await page.locator('#body').inputValue(), 'My unsaved meaning');
    // Session failure also retains the form; signing in again does not reload it.
    assert.equal((await page.request.delete(base + '/api/v1/auth/session', {
      headers: { Origin: base, 'X-CSRF-Token': me.csrf_token }
    })).status(), 204);
    await page.locator('#body').fill('Draft survives logout');
    await page.locator('#settings-form button').click();
    await page.waitForFunction(() => document.querySelector('#body').disabled);
    assert.equal(await page.locator('#body').inputValue(), 'Draft survives logout');
    assert.equal((await page.request.post(base + '/api/v1/auth/login', {
      headers: { Origin: base }, data: { handle, password }
    })).status(), 200);
    await page.locator('#refresh').click();
    await page.waitForFunction(() => !document.querySelector('#body').disabled);
    assert.equal(await page.locator('#body').inputValue(), 'Draft survives logout');
    // If the private follow-up GET fails after a real 201, the one-time proof is still usable.
    let abortManage = true;
    await page.route('**/api/v1/sites/*/manage', route => {
      if (abortManage) { abortManage = false; return route.abort(); }
      return route.continue();
    });
    await page.locator('#new-origin').fill('https://second-' + handle + '.example');
    await page.locator('#create-form button').click();
    await page.waitForFunction(old => {
      const p = document.querySelector('#proof');
      return !p.hidden && p.value.includes('nonce=') && !p.value.includes('site=' + old);
    }, id);
    await page.waitForFunction(() => !document.querySelector('#refresh').disabled);
    assert.equal(await page.locator('#download').isVisible(), true);
    assert.equal(await page.locator('#settings-form button').isDisabled(), true);
    await page.unroute('**/api/v1/sites/*/manage');
    // Hosted view and real iframe use the same public graph and no embed session.
    await page.goto(base + `/sites/${active}/`);
    await page.locator('#start-page').waitFor({ state: 'visible' });
    await page.getByRole('link', { name: 'Точка входа / Entrance point', exact: true }).click();
    await page.waitForFunction(id => document.querySelector('#field-center-id').textContent === id, active);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Hosted field must fit 390px');
    assert.equal(await page.locator('.point-text script').count(), 0);
    await page.locator('.links-list [data-point-id="all-sites"]').click();
    await page.waitForFunction(() => document.querySelector('#field-center-id').textContent === 'all-sites');
    assert(new URL(page.url()).pathname === `/sites/${active}/`);
    const dataset = await (await page.request.get(base + '/data/points.json')).json();
    assert(dataset.some(p => p.id === 'field-ru') && dataset.some(p => p.id === 'field-en'));
    // A real active owner's UI exposes the iframe code without applying its theme to management.
    assert.equal((await page.request.post(base + '/api/v1/auth/login', {
      headers: { Origin: base }, data: { handle: 'fixture-owner', password: 'fixture-test-password' }
    })).status(), 200);
    await page.goto(base + '/sites/');
    await page.locator(`[data-site-id="${active}"]`).click();
    await page.locator('#active').waitFor();
    assert((await page.locator('#embed-code').inputValue()).includes(embed + '/embed/v1/' + active + '/'));
    assert.equal(await page.locator('#editor img').count(), 0);
    assert.notEqual(await page.evaluate(() => getComputedStyle(document.body).getPropertyValue('--bg').trim()), '#123');
    await page.addInitScript(() => {
      if (location.hostname === 'embed.localhost') {
        Storage.prototype.getItem = () => { throw new DOMException('blocked', 'SecurityError'); };
        Storage.prototype.setItem = () => { throw new DOMException('blocked', 'SecurityError'); };
      }
    });
    await page.locator('#show-preview').click();
    const frame = page.frameLocator('iframe');
    await frame.getByRole('link', { name: 'Точка входа / Entrance point', exact: true }).click();
    await frame.locator('#field-map .node.center').waitFor();
    assert.equal(await frame.locator('#field-center-id').textContent(), active);
    const direct = await page.evaluate(async url => {
      try { await fetch(url + '/data/points.json'); return true; } catch { return false; }
    }, embed);
    assert.equal(direct, false, 'Parent connect-src self must block a direct cross-origin fetch');
    const child = page.frames().find(f => f.url().startsWith(embed + '/embed/'));
    assert.equal(await child.evaluate(async () => (await fetch('/api/v1/me')).status), 404);
    assert.equal(await child.evaluate(() => getComputedStyle(document.body).getPropertyValue('--bg').trim()), '#123');
    await frame.locator('.links-list [data-point-id="all-sites"]').click();
    assert((await child.evaluate(() => location.pathname)).startsWith('/embed/v1/'));
    await frame.locator('[data-layout="overlay"]').click();
    await frame.locator('#point-panel-close').click();
    assert.equal(await frame.locator('#point-panel').isVisible(), false);
    // The full iframe uses its public bridge endpoint, never embed /api.
    await frame.locator('#point-picker-open').click();
    await frame.locator('#point-picker-query').fill('skill');
    await frame.locator('#point-picker-results a').first().waitFor();
    assert((await frame.locator('#point-picker-results a').first().getAttribute('href')).includes('/embed/v1/'));
    assert.equal(await frame.locator('#point-picker-detail').count(),0);
    await frame.locator('#point-picker-query').press('Escape');
    assert.equal(await frame.locator('#point-picker').isVisible(), false);
    assert.equal(await frame.locator('#point-panel').isVisible(), false);
    // Neocities-style parent: only local scripts/connect, external frames allowed.
    // Serve the copied SDK as a local file, just as the site owner will do.
    await page.route(base + '/fixture-client.js', route => route.fulfill({
      path: require('node:path').join(__dirname, '../backend/src/node06_service/ui/bridge-client.js'),
      contentType: 'text/javascript',
    }));
    await page.addScriptTag({ url: base + '/fixture-client.js' });
    const bridged = await page.evaluate(async ({ embed, active }) => {
      const bridge = await connectNode06({ embedOrigin: embed, siteId: active });
      window.fixtureBridge = bridge;
      const site = await bridge.request('site.get');
      const ru = await bridge.request('point.get', { point_id: 'field-ru' });
      const en = await bridge.request('point.get', { point_id: 'field-en' });
      const search = await bridge.request('points.search', { query: 'skill' });
      const page = await bridge.request('points.searchPage', { query: 'skill', limit: 1 });
      const next = await bridge.request('points.searchPage', { query: 'skill', limit: 1, after: page.next_cursor });
      const current = await bridge.request('point.read', { point_id: 'skills-ru' });
      const neighbors = await bridge.request('point.neighbors', { point_id: 'skills-ru', limit: 1 });
      let invalidLimit;
      try { await bridge.request('points.searchPage', { query: 'skill', limit: '2' }); }
      catch (error) { invalidLimit = error.message; }
      let write;
      try { await bridge.request('point.createIntent', {}); } catch (error) { write = error.message; }
      let arbitrary;
      try { await bridge.request('site.get', { url: 'https://evil.example' }); } catch (error) { arbitrary = error.message; }
      return { site: site.id, ru: ru.id, en: en.id, found: search.items.length, write, arbitrary,
        current: current.id, revision: current.revision_id, body: Boolean(current.body),
        page: page.items[0].id, next: next.items[0].id, neighbors: neighbors.items.length, invalidLimit };
    }, { embed, active });
    assert.equal(bridged.site, active);
    assert.equal(bridged.ru, 'field-ru'); assert.equal(bridged.en, 'field-en');
    assert(bridged.found > 0);
    assert.equal(bridged.write, 'METHOD_NOT_ALLOWED');
    assert.equal(bridged.arbitrary, 'INVALID_PARAMS');
    assert.equal(bridged.current, 'skills-ru'); assert.equal(bridged.revision, null);
    assert(bridged.body && bridged.next > bridged.page && bridged.neighbors === 1);
    assert.equal(bridged.invalidLimit, 'INVALID_PARAMS');
    const bridgeChild = page.frames().find(f => f.url().startsWith(embed + '/bridge/v1/'));
    const spoofed = await bridgeChild.evaluate(() => new Promise(resolve => {
      let reads = 0;
      const original = window.fetch;
      window.fetch = (...args) => { reads++; return original(...args); };
      const hello = { protocol: 'node06-embed/1', channel: 'x'.repeat(32), kind: 'hello' };
      dispatchEvent(new MessageEvent('message', { origin: 'https://evil.example', source: parent, data: hello }));
      dispatchEvent(new MessageEvent('message', { origin: 'https://localhost:8846', source: parent,
        data: { ...hello, kind: 'request', id: 'spoof', method: 'site.get', params: {} } }));
      setTimeout(() => { window.fetch = original; resolve(reads); }, 50);
    }));
    assert.equal(spoofed, 0, 'Wrong parent origin or channel must not invoke API');
    await bridgeChild.goto(embed + '/bridge/v1/' + active + '/');
    await page.waitForFunction(() => !document.contains(window.fixtureBridge.frame));
    assert.equal(await page.evaluate(async () => {
      try { await fixtureBridge.request('site.get'); return 'unexpected'; } catch (e) { return e.message; }
    }), 'BRIDGE_CLOSED');
    // Hosted picker reads current revision metadata and displays raw text safely.
    await page.goto(base + '/');
    await page.evaluate(() => openNode06Picker({ onSelect: point => { window.pickedPoint = point; } }));
    await page.locator('#point-picker-query').fill(active);
    await page.locator('#point-picker-results button').first().click();
    await page.waitForFunction(()=>Boolean(window.pickedPoint));
    assert.equal(await page.locator('#point-picker-detail').count(),0);
    assert.equal(await page.evaluate(() => window.stolen), undefined);
    const picked = await page.evaluate(() => window.pickedPoint);
    assert.equal(picked.id, active); assert(picked.revision_id.startsWith('v_'));
    assert.equal(new URL(picked.href).searchParams.get('p'), active);
    await page.locator('#point-picker-open').click();
    await page.locator('#point-picker-query').fill('zznothingexists');
    await page.waitForFunction(() => document.querySelector('#point-picker-status').textContent.includes('No matches'));
    await page.route(base + '/api/v1/points/search?*', async route => {
      const q = new URL(route.request().url()).searchParams.get('q');
      if (q === 'zzslow') {
        await new Promise(resolve => setTimeout(resolve, 1200));
        return route.fulfill({ json: { items: [{ id: 'stale', lang: 'en', preview: 'Old request' }], next_cursor: null } });
      }
      if (q === 'zzfail') return route.fulfill({ status: 503, json: { code: 'POINTS_UNAVAILABLE' } });
      return route.continue();
    });
    const slow = page.waitForRequest(request => request.url().includes('q=zzslow'));
    await page.locator('#point-picker-query').fill('zzslow'); await slow;
    await page.locator('#point-picker-query').fill('skill');
    await page.locator('#point-picker-results [data-point-id=skills-ru] a').waitFor();
    await page.waitForTimeout(1300);
    assert.equal(await page.locator('#point-picker-results [data-point-id=stale] a').count(), 0);
    await page.locator('#point-picker-query').fill('zzfail');
    await page.waitForFunction(() => document.querySelector('#point-picker-status').textContent.includes('Search unavailable'));
    assert.equal(await page.locator('#point-picker-query').inputValue(), 'zzfail');
    await page.locator('#point-picker-query').fill('skill');
    await page.locator('#point-picker-results [data-point-id=skills-ru] a').waitFor();
    if (await page.locator('#point-picker-more').isVisible()) {
      const before = await page.locator('#point-picker-results li').count();
      await page.locator('#point-picker-more').click();
      await page.waitForFunction(before => document.querySelectorAll('#point-picker-results li').length > before, before);
    }
    await page.getByRole('button', { name: 'Close results', exact: true }).click();
    // Authenticated social actions stay first-party; a separate fixture point
    // keeps earlier editor tests and the site's source ownership independent.
    const socialSession = await (await page.request.get(base + '/api/v1/me')).json();
    const socialTarget = await (await page.request.get(base + '/api/v1/points/skills-ru')).json();
    const createdSocial = await page.request.post(base + '/api/v1/points', {
      headers: { Origin: base, 'X-CSRF-Token': socialSession.csrf_token, 'Idempotency-Key': 'browser-social-point' },
      data: { body: 'Browser social old text', lang: 'en', links: [{ id: socialTarget.id, revision_id: socialTarget.revision_id, content_digest: socialTarget.content_digest }] }
    });
    assert.equal(createdSocial.status(), 201);
    const socialPoint = (await createdSocial.json()).id;
    await page.goto(base + '/community/?p=' + socialPoint);
    await page.locator('#support-point').waitFor({ state: 'visible' });
    await page.waitForFunction(() => !document.querySelector('#choose-point').disabled);
    await page.locator('#support-point').click();
    await page.waitForFunction(() => document.querySelector('#support-status').textContent.includes('основную'));
    assert.equal(await page.locator('#proposal-lang').count(),0);
    await page.locator('#proposal-body').fill('Browser social new text <script>unsafe()</script>');
    await page.locator('#submit-proposal').click();
    await page.getByRole('button', { name: 'Голос за новую', exact: true }).waitFor();
    assert((await page.locator('#point-current').textContent()).includes('old text'));
    await page.getByRole('button', { name: 'Голос за новую', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#point-current').textContent.includes('new text'));
    assert.equal(await page.locator('#selected-point script').count(), 0, 'Comparison uses plain text');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: '/tmp/node06-community-mobile.png', fullPage: true });
    const inboxDeadline = Date.now() + 45000;
    while (Date.now() < inboxDeadline) {
      await page.locator('#community-refresh').click();
      await page.waitForFunction(() => !document.querySelector('#community-refresh').disabled);
      if ((await page.locator('#inbox').textContent()).includes('proposal-adopted')) break;
      await page.waitForTimeout(1000);
    }
    assert((await page.locator('#inbox').textContent()).includes('proposal-adopted'), 'Background outbox delivers without operator commands');
    const feedTopic=await (await page.request.get(base+'/api/v1/points/skills-ru')).json();
    assert.equal((await page.request.post(base+'/api/v1/points/skills-ru/subscription',{
      headers:{Origin:base,'X-CSRF-Token':socialSession.csrf_token,'Idempotency-Key':'browser-feed-subscription'},
      data:{revision_id:feedTopic.revision_id,content_digest:feedTopic.content_digest,active:true}
    })).status(),200);
    // The creation feed is separate from revision notifications and mounted lazily.
    await page.locator('[data-tab=feed]').click();
    await page.locator('#creation-feed .creation-feed-item').first().waitFor();
    assert((await page.locator('#creation-feed').textContent()).includes('Browser social new text'));
    assert(!(await page.locator('#creation-feed').textContent()).includes('proposal-adopted'));
    const feedCount=await page.locator('#creation-feed .creation-feed-item').count();
    await page.locator('#creation-feed button').first().click();
    await page.waitForFunction(()=>!document.querySelector('#creation-feed button').disabled);
    assert.equal(await page.locator('#creation-feed .creation-feed-item').count(),feedCount);
    // Six raw stats survive loading/saving. No RGB slider may reconstruct the
    // opposite stat or erase large values accepted by the coordinate API.
    const statOrder=['body','spirit','onslaught','composure','reaction','technique'];
    assert.deepEqual(require('../content/root-coordinates-v1.json').coordinate_order,statOrder);
    const largeStats=[65535,2,3500,7,64000,9];
    assert.equal((await page.request.post(base+'/api/v1/me/geometry',{
      headers:{Origin:base,'X-CSRF-Token':socialSession.csrf_token,'Idempotency-Key':'browser-full-stats'},
      data:{coordinates:largeStats}
    })).status(),200);
    await page.reload();
    await page.waitForFunction(()=>!document.querySelector('#choose-point').disabled);
    await page.locator('[data-tab=color]').click();
    assert.equal(await page.locator('#color-radar [role=slider]').count(),6);
    assert((await page.locator('#color-radar').boundingBox()).width<=230);
    const radarHandle=page.locator('#color-radar [data-axis="0"]');
    const dragBox=await radarHandle.boundingBox();
    const dragTarget=await page.locator('#color-radar').evaluate(svg=>{const p=new DOMPoint(150,65).matrixTransform(svg.getScreenCTM());return {x:p.x,y:p.y};});
    await page.mouse.move(dragBox.x+dragBox.width/2,dragBox.y+dragBox.height/2);
    await page.mouse.down();await page.mouse.move(dragTarget.x,dragTarget.y,{steps:5});await page.mouse.up();
    assert.notEqual(await page.locator('#coordinate-0').inputValue(),String(largeStats[0]));
    assert.equal(await page.locator('#coordinate-1').inputValue(),String(largeStats[1]));
    await radarHandle.focus();await page.keyboard.press('Home');assert.equal(await radarHandle.getAttribute('aria-valuenow'),'1');
    await page.keyboard.press('End');assert.equal(await radarHandle.getAttribute('aria-valuenow'),'65535');
    // Real touch events exercise pointer capture on the SVG under mobile sizing.
    const touchBox=await radarHandle.boundingBox(), cdp=await context.newCDPSession(page);
    await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:touchBox.x+touchBox.width/2,y:touchBox.y+touchBox.height/2}]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[dragTarget]});
    await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.detach();
    assert.notEqual(await page.locator('#coordinate-0').inputValue(),'65535');
    await radarHandle.focus();await page.keyboard.press('End');
    await page.locator('#color-values summary').click();
    assert.equal(await page.locator('#color-form input[type=range]').count(),0);
    assert.equal(await page.locator('#color-r,#color-g,#color-b').count(),0);
    assert(!/Тело|Дух|Натиск|Самообладание|Реакция|Техника/.test(await page.locator('#color-form').textContent()));
    assert.deepEqual(await page.locator('.profile-stats input').evaluateAll(inputs=>inputs.map(i=>Number(i.dataset.coordinate))),[0,1,2,3,4,5]);
    for(const [index,stat] of statOrder.entries())assert.equal(await page.locator('#coordinate-'+index).inputValue(),String(largeStats[index]));
    await page.locator('#color-form button').click();
    await page.waitForFunction(()=>document.querySelector('#community-status').textContent.includes('Координаты сохранены'));
    assert.deepEqual((await (await page.request.get(base+'/api/v1/me/geometry')).json()).coordinates,largeStats);
    await page.locator('#coordinate-0').fill('90');
    assert.equal(await page.locator('#coordinate-1').inputValue(),'2','Changing Body must not rewrite Spirit');
    const stats=[90,10,40,60,20,80];
    for(const [index,stat] of statOrder.entries())await page.locator('#coordinate-'+index).fill(String(stats[index]));
    assert.equal(await page.locator('#color-preview').textContent(),'#e66633');
    assert.equal(await page.locator('#color-radar .radar-area').evaluate(el=>getComputedStyle(el).fill),'rgb(230, 102, 51)');
    let invalidStatWrites=0;
    const statRequest=r=>{if(r.method()==='POST'&&r.url()===base+'/api/v1/me/geometry')invalidStatWrites++;};
    page.on('request',statRequest);
    for(const invalid of ['','0','65536','1.5']){
      await page.locator('#coordinate-0').fill(invalid);
      assert.equal(await page.locator('#color-form').evaluate(form=>form.checkValidity()),false);
      await page.locator('#color-form button').click();
    }
    assert.equal(invalidStatWrites,0,'Invalid stats never reach the API');
    page.off('request',statRequest);
    await page.locator('#coordinate-0').fill('90');
    await page.locator('#color-form button').click();
    await page.waitForFunction(()=>!document.querySelector('#color-form button').disabled);
    const savedStats=await (await page.request.get(base+'/api/v1/me/geometry')).json();
    assert.deepEqual(savedStats.coordinates,stats);assert.equal(savedStats.color,'#e66633');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:'/tmp/node06-stats-mobile.png',fullPage:true});
    await waitGeometry(socialPoint,'#e66633');
    await page.goto(base+'/?p='+socialPoint+'&open='+socialPoint);
    const actions=page.locator('#point-panel-body .point-actions');
    await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=support]')?.getAttribute('aria-pressed')==='true');
    assert.equal(await actions.locator('svg').count(),7);
    assert.equal(await page.locator('#point-panel-body .point-social h2').count(),0);
    assert.equal(await page.locator('#field-map .node title').count(),0);
    const sphere=page.locator(`#field-map .node[data-id="${socialPoint}"] circle`);
    await sphere.hover();await page.locator('#hover-card').waitFor({state:'visible'});
    await sphere.click({button:'right'});
    const menu=page.locator('#point-context-menu');await menu.waitFor();
    await page.waitForFunction(()=>document.querySelector('#point-context-menu [data-action=support]')?.getAttribute('aria-pressed')==='true');
    assert.equal(await menu.locator('.point-actions > *').count(),9);
    assert.equal(await menu.locator('.point-actions a,.point-actions button').count(),8);
    const grid=await menu.locator('.point-actions').evaluate(n=>{const r=n.getBoundingClientRect();return [r.width,r.height,getComputedStyle(n).gridTemplateColumns];});
    assert.equal(grid[0],grid[1]);assert.equal(grid[2],'42px 42px 42px');
    const edit=menu.locator('[data-action=edit]');assert.equal(new URL(await edit.getAttribute('href')).searchParams.get('p'),socialPoint);
    await edit.click();await page.locator('#point-editor-overlay').waitFor();
    await page.frameLocator('#point-editor-overlay iframe').locator('#editor-form[data-ready=true]').waitFor();
    await page.locator('#point-editor-overlay .editor-overlay-heading button').click();
    await page.locator('#point-editor-overlay').waitFor({state:'detached'});
    await sphere.click({button:'right'});await menu.waitFor();
    await page.screenshot({path:'/tmp/node06-sphere-menu-hosted.png'});
    await page.keyboard.press('Escape');await menu.waitFor({state:'detached'});
    await page.locator('#field-map .node[data-id="skills-ru"] circle').click({button:'right'});
    await menu.waitFor();
    await page.waitForFunction(()=>document.querySelector('#point-context-menu [data-action=related]')?.href.includes('from=skills-ru'));
    await page.waitForFunction(()=>document.querySelector('#point-context-menu [data-action=support]')?.disabled===false);
    assert.equal(await menu.locator('[data-action=edit]').getAttribute('aria-disabled'),'true');
    assert.equal(await page.locator('#field-center-id').textContent(),socialPoint,'Right-click keeps center');
    await page.keyboard.press('Escape');

    assert((await page.locator('#point-panel-body .point-author').textContent()).includes(socialSession.handle));
    assert.equal(await page.locator('#point-panel-body .point-author a').getAttribute('href'),base+'/people/'+socialSession.user_id+'/?'+new URLSearchParams({site:active}));
    const authorPage=await context.newPage();await authorPage.goto(base+'/people/'+socialSession.user_id+'/');
    await authorPage.locator('#author-points a').first().waitFor();assert.equal(await authorPage.locator('#author-actions').isVisible(),false);
    // A distinct public author can be subscribed through the existing T1 edge.
    const profileViewer=await (await authorPage.request.get(base+'/api/v1/me')).json();
    const candidates=await (await authorPage.request.get(base+'/api/v1/people?q=browser')).json();
    const otherAuthor=candidates.items.find(u=>u.id!==profileViewer.user_id);
    if(!otherAuthor)throw new Error('Browser fixture needs another author');
    await authorPage.goto(base+'/people/'+otherAuthor.id+'/?'+new URLSearchParams({site:active}));await authorPage.locator('#author-actions').waitFor();
    await authorPage.locator('#author-follow').click();await authorPage.waitForFunction(()=>document.querySelector('#author-follow').getAttribute('aria-pressed')==='true');
    await authorPage.locator('#author-site-block').click();await authorPage.waitForFunction(()=>document.querySelector('#author-site-block').getAttribute('aria-pressed')==='true');
    assert.equal(await authorPage.locator('#author-follow').getAttribute('aria-pressed'),'true');
    assert.equal(await authorPage.locator('#author-block').getAttribute('aria-pressed'),'false');
    await authorPage.locator('#author-site-block').click();await authorPage.waitForFunction(()=>document.querySelector('#author-site-block').getAttribute('aria-pressed')==='false');
    await authorPage.locator('#author-block').click();await authorPage.waitForFunction(()=>document.querySelector('#author-block').getAttribute('aria-pressed')==='true');
    assert.equal(await authorPage.locator('#author-follow').isDisabled(),true);
    await authorPage.locator('#author-block').click();await authorPage.waitForFunction(()=>document.querySelector('#author-block').getAttribute('aria-pressed')==='false');
    assert.equal(await authorPage.locator('#author-follow').getAttribute('aria-pressed'),'false');
    await authorPage.screenshot({path:'/tmp/node06-author-profile-mobile.png',fullPage:true});await authorPage.close();

    assert.equal(await page.locator('#point-panel-body .point-action-status').isVisible(),false);
    const favorite=actions.locator('[data-action=favorite]');
    await page.route(base+'/api/v1/me/favorites/'+socialPoint,async route=>{
      assert.equal((await route.fetch()).status(),200);await route.abort();
    },{times:1});
    await favorite.click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-action-status')?.textContent.includes('not confirmed'));
    // Retry the viewer's lost acknowledgment from the context menu, sharing its receipt.
    await sphere.click({button:'right'});await menu.waitFor();
    await page.waitForFunction(()=>document.querySelector('#point-context-menu [data-action=favorite]')?.disabled===false);
    await menu.locator('[data-action=favorite]').click();
    await page.waitForFunction(()=>document.querySelector('#point-context-menu [data-action=favorite]')?.getAttribute('aria-pressed')==='true');
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=favorite]')?.getAttribute('aria-pressed')==='true');
    await favorite.click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=favorite]')?.getAttribute('aria-pressed')==='false');
    await page.waitForFunction(id=>document.querySelector(`.node[data-id="${id}"]`)?.dataset.color==='#e66633',socialPoint,{timeout:45000});
    assert((await page.locator('#point-panel-body > .eyebrow').textContent()).includes('SOCIAL GEOMETRY'));
    await page.screenshot({path:'/tmp/node06-colored-field-mobile.png',fullPage:true});
    await actions.locator('[data-action=block]').click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=block]')?.getAttribute('aria-pressed')==='true');
    assert.equal(await actions.locator('[data-action=support]').getAttribute('aria-pressed'),'false');
    // Q12 normalization places the mirrored red channel just below the half-unit tie.
    await waitGeometry(socialPoint,'#1999cc');
    await page.locator('#field-refresh').click();
    await page.waitForFunction(id=>document.querySelector(`.node[data-id="${id}"]`)?.dataset.color==='#1999cc',socialPoint);
    await actions.locator('[data-action=block]').click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body [data-action=block]')?.getAttribute('aria-pressed')==='false');
    await waitGeometry(socialPoint,null);
    await page.locator('#field-refresh').click();
    await page.waitForFunction(id=>document.querySelector(`.node[data-id="${id}"]`)?.dataset.coordinateSource==='display-only',socialPoint);

    // Late summaries cannot replace another point, and unavailable data is not zero.
    let started, finished;
    const slowStarted=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Expected summary request was not observed')),15000);started=()=>{clearTimeout(timer);resolve();};});
    const slowFinished=new Promise(resolve=>{finished=resolve;});
    await page.route(base+'/api/v1/points/skills-ru/social-summary',async route=>{
      const response=await route.fetch(); started();
      await new Promise(resolve=>setTimeout(resolve,1500));
      await route.fulfill({response}); finished();
    },{times:1});
    await page.goto(base+'/?p=skills-ru&open=skills-ru');
    await slowStarted;
    await page.locator('#point-panel-body .links-list [data-point-id="skills-en"]').click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-social')?.dataset.pointId==='skills-en');
    await slowFinished; await page.waitForTimeout(150);
    assert.equal(await page.locator('#point-panel-body .point-social').getAttribute('data-point-id'),'skills-en');
    await page.route(base+'/api/v1/points/skills-en/social-summary',async route=>{
      const response=await route.fetch(),value=await response.json();value.content_digest='0'.repeat(64);await route.fulfill({json:value});
    },{times:1});
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-action-status')?.textContent.includes('Text changed'));
    assert.equal(await page.locator('#point-panel-body [data-action=support]').isDisabled(),true);
    await page.route(base+'/api/v1/points/skills-en/social-summary',route=>route.fulfill({status:400,json:{code:'METHOD_NOT_ALLOWED'}}),{times:1});
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-action-status')?.textContent.includes('Actions unavailable'));
    assert(await page.locator('#point-panel-body .point-text').isVisible());
    await page.route(base+'/api/v1/me/subscriptions/skills-en',route=>route.fulfill({status:503,json:{code:'UNAVAILABLE'}}),{times:1});
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-action-status')?.textContent.includes('Actions unavailable'));
    await page.goto(base + '/community/?p=skills-ru');
    await page.waitForFunction(() => !document.querySelector('#choose-point').disabled);
    assert.equal(await page.locator('#proposal-form').isVisible(), false, 'Git point proposals are protected');
    assert((await page.locator('#protection').textContent()).includes('Защищённая'));
    await page.goto(base + '/?p=skills-ru&open=skills-ru');
    const related = page.locator('.point-create-related');
    await related.waitFor();
    const relatedHref = await related.getAttribute('href');
    assert.equal(new URL(relatedHref).searchParams.get('from'), 'skills-ru');
    assert.equal(new URL(relatedHref).searchParams.get('return_to'),'/');
    await page.locator('#point-panel-body [data-action=remember]').click();
    const collected=await page.evaluate(()=>window.node06PointClipboard.read(location.origin).items);
    assert(collected.some(pin=>pin.id==='skills-ru'));
    const beforeEditor=page.url();
    await related.click();
    const editorFrame=page.frameLocator('#point-editor-overlay iframe');
    await editorFrame.locator('#editor-form').waitFor({state:'visible'});
    await editorFrame.locator('#clipboard-points [data-point-id=skills-ru]').waitFor();
    await editorFrame.locator('#clipboard-url').fill(base+'/?p=skills-en&open=skills-en');
    await editorFrame.locator('#clipboard-url-form button').click();
    await editorFrame.locator('#clipboard-points [data-point-id=skills-en]').waitFor();
    await page.evaluate(()=>{const c=window.node06PointClipboard;c.write(location.origin,[...c.read(location.origin).items,{id:'missing-clipboard-point',preview:'Missing',url:location.origin+'/?p=missing-clipboard-point'}]);});
    await editorFrame.locator('#clipboard-points [data-point-id=missing-clipboard-point]').waitFor();
    const beforeMissing=await editorFrame.locator('#point-body').inputValue();
    await editorFrame.locator('#clipboard-insert-all').click();
    await page.waitForFunction(()=>document.querySelector('#point-editor-overlay iframe').contentDocument.querySelector('#editor-status').textContent.includes('недоступна'));
    assert.equal(await editorFrame.locator('#point-body').inputValue(),beforeMissing,'Missing point never partially inserts text');
    await editorFrame.locator('#clipboard-points [data-point-id=missing-clipboard-point] button').click();
    await editorFrame.locator('#clipboard-points [data-point-id=missing-clipboard-point]').waitFor({state:'detached'});
    await editorFrame.locator('#clipboard-insert-all').click();
    await editorFrame.locator('#point-body').evaluate(input=>input.value);
    await page.waitForFunction(()=>document.querySelector('#point-editor-overlay iframe')?.contentDocument.querySelector('#point-body').value.includes('md://point/skills-en'));
    const inserted=await editorFrame.locator('#point-body').inputValue();assert(inserted.includes('md://point/skills-ru'));
    assert.equal(await editorFrame.locator('#point-links li').count(),2);
    await editorFrame.locator('#clipboard-clear').click();
    await editorFrame.locator('#clipboard-points li').first().waitFor({state:'detached'});
    assert.equal((await page.evaluate(()=>window.node06PointClipboard.read(location.origin).items)).length,0);
    await editorFrame.locator('#point-body').fill('Unsaved overlay draft');
    const keepDraft=page.waitForEvent('dialog').then(dialog=>dialog.dismiss());
    await page.locator('#point-editor-overlay .editor-overlay-heading button').click();
    await keepDraft;
    assert.equal(await editorFrame.locator('#point-body').inputValue(),'Unsaved overlay draft');
    const discardDraft=page.waitForEvent('dialog').then(dialog=>dialog.accept());
    await page.locator('#point-editor-overlay .editor-overlay-heading button').click();
    await discardDraft;
    await page.locator('#point-editor-overlay').waitFor({state:'detached'});
    assert.equal(page.url(),beforeEditor,'Closing editor preserves map URL');
    await related.click();
    await editorFrame.locator('#tag-tools').waitFor({state:'visible'});
    await page.frames().find(f=>f.url().includes("editor_channel=")).waitForFunction(()=>document.querySelector('#editor-form').dataset.ready==='true');
    assert.equal(await editorFrame.locator('#favorite-tags button').count(), 0, 'The fixture owner must not see another account favorites');
    await editorFrame.getByRole('button', {name:'☆ Сохранить тег',exact:true}).click();
    await page.frames().find(f=>f.url().includes("editor_channel=")).waitForFunction(()=>document.querySelector('#editor-status').textContent.includes('Тег сохранён'));
    const editorDocument=page.frames().find(f=>f.url().includes("editor_channel="));
    await Promise.all([editorDocument.waitForNavigation({waitUntil:'load'}),editorFrame.locator("body").evaluate(()=>location.reload())]);
    await editorDocument.waitForFunction(()=>document.querySelector('#editor-form').dataset.ready==='true'&&document.querySelector('#favorite-tags button'));
    assert((await editorFrame.locator('#point-links').innerText()).includes('Навык'));
    assert((await editorFrame.locator('#favorite-tags').innerText()).includes('Навык'));
    await editorFrame.getByRole('button',{name:'Убрать связь',exact:true}).click();
    await editorFrame.locator('#favorite-tags button').first().click();
    await page.frames().find(f=>f.url().includes("editor_channel=")).waitForFunction(()=>document.querySelectorAll('#point-links li').length === 1);
    // Link action wraps selected words and also inserts at an empty caret.
    const linkedBody=editorFrame.locator('#point-body');
    await linkedBody.fill('Before meaning after');
    await linkedBody.evaluate(n=>{n.focus();n.setSelectionRange(7,14);});
    await editorFrame.locator('#link-word').click();
    await editorFrame.locator('#point-picker-query').fill('skills-ru');
    await editorFrame.locator('#point-picker-results li[data-point-id="skills-ru"] button').click();
    await editorDocument.waitForFunction(()=>document.querySelector('#point-body').value.includes('md://point/skills-ru'));
    assert.equal(await linkedBody.inputValue(),'Before [meaning](md://point/skills-ru) after');
    const caret=await linkedBody.evaluate(n=>n.selectionStart);
    assert.equal(caret,'Before [meaning](md://point/skills-ru)'.length);
    await linkedBody.fill('Before  after');
    await linkedBody.evaluate(n=>{n.focus();n.setSelectionRange(7,7);});
    await editorFrame.locator('#link-word').click();
    await editorFrame.locator('#point-picker-results li[data-point-id="skills-ru"] button').click();
    await editorDocument.waitForFunction(()=>document.querySelector('#point-body').value.includes('md://point/skills-ru'));
    assert.match(await linkedBody.inputValue(),/^Before \[[^\]]+\]\(md:\/\/point\/skills-ru\) after$/);
    assert.equal(await editorFrame.locator('#point-links li').count(),1,'Repeated inline target shares one declared link');
    await editorFrame.locator('#point-body').fill('A related point from the current meaning');
    await page.screenshot({path:'/tmp/node06-editor-overlay-mobile.png',fullPage:true});
    await editorFrame.locator('#publish').click();
    await page.waitForURL(url=>url.pathname==='/'&&/^p_[0-9a-f]{32}$/.test(url.searchParams.get('p')||'')&&url.searchParams.get('p')===url.searchParams.get('open'));
    const relatedId = new URL(page.url()).searchParams.get('p');
    const relatedPublished = await (await page.request.get(base+'/api/v1/points/'+relatedId)).json();
    assert(relatedPublished.links.includes('skills-ru'));
    assert.equal(relatedPublished.body,'A related point from the current meaning');
    await page.locator('.point-create-related').click();
    await editorFrame.locator('#editor-form[data-ready=true]').waitFor();
    await editorFrame.locator('.editor-meta details').first().locator('summary').click();
    await editorFrame.locator('#my-points a').filter({hasText:'A related point from the current meaning'}).click();
    await editorFrame.locator('#title').filter({hasText:'Изменить точку'}).waitFor();
    await editorFrame.locator('#point-body').fill('Updated through the map overlay');
    await editorFrame.locator('#publish').click();
    await page.locator('#point-editor-overlay').waitFor({state:'detached'});
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-text')?.textContent.includes('Updated through the map overlay'));
    assert.equal(new URL(page.url()).searchParams.get('p'),relatedId);

    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:'/tmp/node06-editor-related-mobile.png',fullPage:true});
    await page.setViewportSize({width:1280,height:1000});
    await page.screenshot({path:'/tmp/node06-editor-related-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    // A Neocities-style static page ships its own SDK/config and does not fetch
    // the remote API directly. The local HTTPS fixture is the registered parent.
    await page.route(base + '/assets/connection.json', route => route.fulfill({
      json: { embedOrigin: embed, serviceOrigin: base, siteId: active },
    }));
    // Explicitly permit this disposable test origin to reach its loopback fixture, not the LAN
    // from production. CSP and bridge source/origin/credential checks stay active.
    await context.grantPermissions(['local-network-access'], { origin: base });
    await page.route(base + '/picker-parent**', route => route.fulfill({
      body: require('node:fs').readFileSync(require('node:path').join(process.env.NODE06_BROWSER_DIST||require('node:path').join(__dirname,'../dist'),'index.html'),'utf8').replace('data-page="field"','data-page="field" data-field-path="/picker-parent"'),
      contentType: 'text/html',
      headers: { 'Content-Security-Policy': `default-src 'self'; connect-src 'self'; frame-src ${embed}; script-src 'self'; style-src 'self'` },
    }));
    await page.goto(base + '/picker-parent');
    assert.equal(await page.evaluate(() => typeof connectNode06), 'function', 'Static SDK is present');
    const searchInput = page.locator('#point-picker-query');
    assert.equal(await searchInput.isVisible(), true, 'Search is already an inline field');
    assert.equal(await page.locator('dialog#point-picker').count(), 0, 'No modal search window');
    assert.equal(await page.locator('#point-picker-open svg').count(), 1, 'Submit uses a magnifier');
    assert.equal(await searchInput.evaluate(input => getComputedStyle(input).borderRadius), '0px');
    assert(new URL(await page.locator('link[rel=stylesheet]').first().getAttribute('href'), base).searchParams.has('v'), 'Styles are content-versioned');
    await searchInput.fill('skill');
    await searchInput.press('Enter');
    await page.waitForFunction(() => {
      const text = document.querySelector('#point-picker-status').textContent;
      return document.querySelector('#point-picker-results a') || (text && !text.includes('Searching'));
    });
    assert(await page.locator('#point-picker-results a').count(),
      'Static picker: '+await page.locator('#point-picker-status').textContent());
    const destination=new URL(await page.locator('#point-picker-results a').first().getAttribute('href'));
    assert.equal(destination.origin,base);assert.equal(destination.pathname,`/sites/${active}/`);
    assert.equal(await page.locator('#point-picker-results a').first().getAttribute('target'),'_blank');
    assert.equal(await page.locator('#point-picker-detail').count(),0);
    assert.equal(await page.locator('#point-picker .point-social').count(),0);
    assert.equal(await page.locator('#point-picker input').count(),0);
    const publicSocial=await page.evaluate(()=>window.readNode06Public('point.social',{point_id:'skills-ru'}));
    assert.equal(publicSocial.id,'skills-ru');
    assert.equal(publicSocial.protected,true);
    const publicGeometry=await page.evaluate(()=>window.readNode06Public('points.geometry',{point_ids:['skills-ru','skills-en']}));
    assert.equal(publicGeometry.schema,'node06-geometry/1');
    assert.equal(publicGeometry.items.length,2);
    assert.equal(await page.evaluate(async()=>{
      try{await window.readNode06Public('points.geometry',{point_ids:['skills-ru','skills-ru']});return null;}catch(error){return error.message;}
    }),'INVALID_PARAMS');
    assert(page.frames().some(frame => frame.url().startsWith(embed + '/bridge/v1/')));
    assert.equal(await page.evaluate(async embed => {
      try { await fetch(embed + '/api/v1/meta'); return true; } catch { return false; }
    }, embed), false, 'Static parent direct cross-origin fetch remains blocked by CSP');
    const popup = await page.locator('#point-picker').boundingBox();
    assert(popup.x >= 0 && popup.x + popup.width <= 390 && popup.y + popup.height <= 844,
      'Mobile dropdown stays inside the viewport');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: '/tmp/node06-picker-mobile.png', fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: '/tmp/node06-picker-desktop.png', fullPage: true });
    await page.locator('#point-picker-query').press('Escape');
    assert.equal(await page.locator('#point-picker').isVisible(), false);
    assert.equal(await searchInput.isVisible(), true);
    assert.equal(await searchInput.inputValue(), 'skill', 'Escape preserves query');
    await searchInput.press('Enter');
    await page.locator('#point-picker-results a').first().waitFor();
    await searchInput.press('ArrowDown');
    assert.equal(await page.locator('#point-picker-results a').first().evaluate(node => node === document.activeElement), true);
    await page.locator('main').click({ position: { x: 3, y: 3 } });
    assert.equal(await page.locator('#point-picker').isVisible(), false, 'Outside click dismisses results');
    await searchInput.fill('');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: '/tmp/node06-search-field-mobile.png', fullPage: true });
    // Neocities-style anonymous draft overlay: no popup on opening, exact root
    // pin, explicit top-level review, uncertain response replay, back to static map.
    const staticPage=await context.newPage();
    staticPage.on('pageerror',error=>errors.push(error.message));
    staticPage.on('request',request=>{if(request.url().startsWith(embed+'/'))embedCookies.push(request.allHeaders().then(headers=>Boolean(headers.cookie)));});
    await context.grantPermissions(['local-network-access'],{origin:'https://garden.localhost'});
    await staticPage.route('https://garden.localhost/**',async route=>{
      const path=new URL(route.request().url()).pathname;
      if(path==='/assets/connection.json')return route.fulfill({json:{embedOrigin:embed,serviceOrigin:base,siteId:active}});
      if(path==='/full-parent')return route.fulfill({contentType:'text/html',body:`<iframe id=wiki width=380 height=800 src="${embed}/embed/v1/${active}/?p=point-ru&open=point-ru"></iframe>`,headers:{'Content-Security-Policy':`default-src 'self'; frame-src ${embed}`}});
      if(path==='/picker-parent')return route.fulfill({
        body:require('node:fs').readFileSync(require('node:path').join(process.env.NODE06_BROWSER_DIST||require('node:path').join(__dirname,'../dist'),'index.html'),'utf8').replace('data-page="field"','data-page="field" data-field-path="/picker-parent"'),
        contentType:'text/html',headers:{'Content-Security-Policy':`default-src 'self'; connect-src 'self'; frame-src ${embed}; script-src 'self'; style-src 'self'`}
      });
      if(/^\/(assets|data)\/[a-z0-9_.-]+$/.test(path))return route.fulfill({path:require('node:path').join(__dirname,'../dist',path)});
      return route.abort();
    });
    await staticPage.goto('https://garden.localhost/picker-parent?p=point-ru&open=point-ru');
    assert.equal(await staticPage.locator('.site-header nav a').first().textContent(),'NODE06');
    await staticPage.locator('.point-create-related').waitFor();
    assert.equal(await staticPage.locator('[data-view]').count(),0);
    assert.equal(await staticPage.locator('#field-controls #field-refresh').count(),1);
    let externalPrivateFeedReads=0;
    const externalFeedRequest=request=>{if(new URL(request.url()).pathname==='/api/v1/me/feed')externalPrivateFeedReads++;};
    staticPage.on('request',externalFeedRequest);
    await staticPage.locator('[data-mode=feed]').click();
    await staticPage.locator('.creation-feed-status').waitFor();
    assert.equal(new URL(await staticPage.locator('.creation-feed-status + a').getAttribute('href')).pathname,'/community/');
    assert.equal(externalPrivateFeedReads,0,'Static copy cannot read the personal feed');
    await staticPage.locator('[data-mode=read]').click();
    await staticPage.goto('https://garden.localhost/picker-parent?p=point-ru&open=point-ru');
    await staticPage.locator('.point-create-related').waitFor();
    staticPage.off('request',externalFeedRequest);
    await staticPage.locator('#point-panel-body [data-action=remember]').click();
    assert((await staticPage.evaluate(()=>window.node06PointClipboard.read(window.node06ManagementOrigin?.()||document.body.dataset.managementOrigin).items)).some(pin=>pin.id==='point-ru'));
    const pagesBefore=context.pages().length;
    await staticPage.locator('.point-create-related').click();
    const externalEditor=staticPage.frameLocator('#point-editor-overlay iframe');
    await externalEditor.locator('#editor-form[data-ready=true]').waitFor();
    await externalEditor.locator('#clipboard-points [data-point-id=point-ru]').waitFor();
    const countBeforeSpoof=await externalEditor.locator('#clipboard-points li').count();
    await externalEditor.locator('body').evaluate(()=>window.dispatchEvent(new MessageEvent('message',{origin:document.body.dataset.parentOrigin,data:{protocol:'node06-editor/1',kind:'clipboard',channel:'spoof',scope:document.body.dataset.managementOrigin,items:[]}})));
    assert.equal(await externalEditor.locator('#clipboard-points li').count(),countBeforeSpoof);
    await externalEditor.locator('#clipboard-add-all').click();
    await externalEditor.locator('#clipboard-clear').click();
    await externalEditor.locator('#clipboard-points li').first().waitFor({state:'detached'});
    assert.equal(context.pages().length,pagesBefore,'Opening draft must not open a new window');
    assert((await externalEditor.locator('#point-links').textContent()).includes('Точка'));
    const libraryActor=await (await page.request.get(base+'/api/v1/me')).json();
    assert.equal((await page.request.post(base+'/api/v1/me/favorites/field-en',{headers:{Origin:base,'X-CSRF-Token':libraryActor.csrf_token,'Idempotency-Key':'browser-library-favorite'},data:{active:true}})).status(),200);
    const libraryPromise=staticPage.waitForEvent('popup');await externalEditor.locator('#open-library').click();const libraryPage=await libraryPromise;
    await libraryPage.locator('#library-favorites button[data-point-id=field-en]').waitFor();
    assert.equal(await libraryPage.locator('#library-favorites').textContent().then(t=>t.length>0),true);
    // Wrong source/channel cannot add a public point to the draft.
    const linkCount=await externalEditor.locator('#point-links li').count();
    await externalEditor.locator('body').evaluate(()=>window.dispatchEvent(new MessageEvent('message',{origin:document.body.dataset.managementOrigin,data:{protocol:'node06-library/1',kind:'selected',id:'field-en',channel:'spoof'}})));
    assert.equal(await externalEditor.locator('#point-links li').count(),linkCount);
    await libraryPage.locator('#library-favorites button[data-point-id=field-en]').click();
    await externalEditor.locator('#point-links li').nth(linkCount).waitFor();assert.equal(await externalEditor.locator('#point-body').inputValue(),'');
    await externalEditor.locator('#point-body').fill('Embedded root child <script>not executable</script>');
    await staticPage.locator('#point-editor-overlay .editor-overlay-heading button').click();
    await staticPage.locator('.editor-discard').waitFor();
    await staticPage.getByRole('button',{name:'Keep editing',exact:true}).click();
    assert.equal(await externalEditor.locator('#point-body').inputValue(),'Embedded root child <script>not executable</script>');
    const popupPromise=staticPage.waitForEvent('popup');
    await externalEditor.locator('#publish').click();
    const approval=await popupPromise;
    await approval.locator('#confirmation-publish:not([disabled])').waitFor();
    assert((await approval.locator('#confirmation-links').textContent()).includes('point-ru'));
    assert.equal(await approval.locator('#confirmation-body').textContent(),'Embedded root child <script>not executable</script>');
    assert.equal(await approval.locator('#confirmation-body script').count(),0);
    const fixedDraft=await approval.locator('#confirmation-body').textContent();
    // Wrong source, even the registered parent origin, cannot replace the draft.
    await approval.evaluate(()=>window.dispatchEvent(new MessageEvent('message',{origin:location.origin,data:{protocol:'node06-publish/1',kind:'draft',payload:{body:'spoofed'}}})));
    assert.equal(await approval.locator('#confirmation-body').textContent(),fixedDraft);
    let approvalLost=true;
    await approval.route(base+`/editor/confirm/${active}/`,async route=>{
      if(approvalLost){approvalLost=false;await route.fetch();await route.abort('failed');}
      else await route.continue();
    });
    await approval.locator('#confirmation-publish').click();
    await approval.waitForFunction(()=>document.querySelector('#confirmation-status').textContent.includes('Ответ не получен'));
    assert.equal(await externalEditor.locator('#point-body').getAttribute('readonly'),'');
    await approval.locator('#confirmation-publish').click();
    await staticPage.waitForURL(url=>url.pathname==='/picker-parent'&&/^p_[0-9a-f]{32}$/.test(url.searchParams.get('p')||''));
    const embeddedId=new URL(staticPage.url()).searchParams.get('p');
    await staticPage.waitForFunction(()=>document.querySelector('#point-panel-body .point-text')?.textContent.includes('Embedded root child'));
    assert.equal(await staticPage.locator('#point-panel-body .point-text script').count(),0);
    const publishedRootChild=await (await page.request.get(base+'/api/v1/points/'+embeddedId)).json();
    assert.deepEqual(publishedRootChild.declared_links,['field-en','point-ru']);
    await staticPage.screenshot({path:'/tmp/node06-embedded-published-mobile.png',fullPage:true});
    await staticPage.goto('https://garden.localhost/full-parent');
    const fullWiki=staticPage.frameLocator('#wiki');
    assert.equal(await fullWiki.locator('.site-home-link').getAttribute('href'),`/embed/v1/${active}/`);
    await fullWiki.locator('.point-create-related').click();
    const nestedEditor=fullWiki.frameLocator('#point-editor-overlay iframe');
    await nestedEditor.locator('#editor-form[data-ready=true]').waitFor();
    await nestedEditor.locator('#point-body').fill('Nested draft');
    await fullWiki.locator('#point-editor-overlay .editor-overlay-heading button').click();
    await fullWiki.getByRole('button',{name:'Discard draft',exact:true}).click();
    await fullWiki.locator('#point-editor-overlay').waitFor({state:'detached'});
    await page.goto(base+`/sites/${active}/?p=point-ru&open=point-ru`);
    assert.equal(await page.locator('.site-home-link').getAttribute('href'),'/');
    await page.locator('.site-home-link').click();
    await page.waitForURL(url=>url.pathname==='/'&&!url.search);
    // Compact profile panels keep unrelated lists collapsed and unsubscribe direct.
    await page.goto(base+'/community/');
    await page.waitForFunction(()=>!document.querySelector('#choose-point').disabled);
    assert.equal(await page.locator('[data-profile-panel]:visible').count(),1);
    await page.locator('[data-tab=blocks]').click();
    assert.equal(await page.locator('[data-profile-panel=blocks]').isVisible(),true);
    assert.equal(await page.locator('[data-profile-panel=subscriptions]').isVisible(),false);
    await page.locator('[data-tab=favorites]').click();
    assert.equal(await page.locator('[data-profile-panel=favorites]').isVisible(),true);
    await page.locator('#profile-query').fill('no-such-favorite');
    assert.equal(await page.locator('#profile-favorites li:visible').count(),0);
    await page.locator('#profile-query').fill('');
    await page.locator('[data-tab=favorites]').focus();
    await page.keyboard.press('Home');
    assert.equal(await page.locator('[data-tab=points]').getAttribute('aria-selected'),'true');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:'/tmp/node06-compact-profile-mobile.png',fullPage:true});
    // Every trusted personal page has the same navigation and current-page marker.
    for(const [path,key] of [['/sites/','sites'],['/account/','account'],['/editor/','editor'],['/moderation/','moderation'],['/directory/','directory'],['/profile-sync/','profile-sync'],['/community/','profile']]){
      await page.goto(base+path);
      const nav=page.locator('.personal-header nav');
      assert.equal(await nav.locator('a').count(),9);
      assert.equal(await nav.locator('a[href="/profile-sync/"]').count(),1);
      assert.equal(await nav.locator('[aria-current=page]').count(),1);
      assert.equal(await nav.locator('[aria-current=page]').getAttribute('href'),path);
      assert.equal(await nav.locator('a[target]').count(),key==='editor'?1:0);
      if(key==='editor')assert.equal(await nav.locator('a[target=_blank]').getAttribute('href'),'/account/');
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),key+' mobile overflow');
    }
    await page.waitForFunction(()=>!document.querySelector('#choose-point').disabled);
    await page.locator('[data-tab=color]').click();
    assert.equal(new URL(page.url()).hash,'#color');
    assert.equal(await page.locator('#profile-filter').isVisible(),false);
    assert.equal(await page.locator('#choose-point').isVisible(),false);
    assert.equal(await page.locator('#color-form').isVisible(),true);
    await page.locator('[data-tab=inbox]').click();
    await page.goBack();
    assert.equal(await page.locator('[data-tab=color]').getAttribute('aria-selected'),'true');
    await page.reload();
    await page.waitForFunction(()=>!document.querySelector('#choose-point').disabled);
    assert.equal(await page.locator('#color-form').isVisible(),true);
    await page.goto(base+'/community/#my-color');
    await page.waitForFunction(()=>!document.querySelector('#choose-point').disabled);
    assert.equal(await page.locator('#color-form').isVisible(),true);
    await page.screenshot({path:'/tmp/node06-profile-color-navigation.png',fullPage:true});
    // The trusted report panel is reached from a site-context point action.
    await page.goto(base+'/sites/'+active+'/?p='+socialPoint+'&open='+socialPoint);
    await page.locator('.point-report[href]').waitFor();
    assert.equal(new URL(await page.locator('.point-report').getAttribute('href')).searchParams.get('scope'),active);
    await page.locator('.point-report').click();
    await page.waitForURL('**/moderation/**');
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Готово.');
    await page.locator('#report-reason').fill('Needs review <script>window.moderationUnsafe=true</script>');
    await page.locator('#report-form button').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Готово.');
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#reports li'));
    assert.equal(await page.locator('#reports script').count(),0);
    assert.equal(await page.evaluate(()=>window.moderationUnsafe),undefined);
    await page.locator('#decision-reason').fill('Browser site-only hide');
    await page.route(base+'/api/v1/moderation/visibility/*',async route=>{
      assert.equal((await route.fetch()).status(),200);await route.abort();
    },{times:1});
    await page.locator('#hide-point').click();
    await page.waitForFunction(()=>!document.querySelector('#hide-point').disabled);
    await page.locator('#hide-point').click();
    await page.waitForFunction(()=>document.querySelector('#hidden-since').textContent.includes('только на этом сайте'));
    assert.equal((await page.request.get(base+'/api/v1/points/'+socialPoint+'?site='+active)).status(),404);
    assert.equal((await page.request.get(base+'/api/v1/points/'+socialPoint+'?site='+otherSite)).status(),200);
    await page.screenshot({path:'/tmp/node06-moderation-mobile.png',fullPage:true});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Moderation fits mobile');
    await page.locator('#restore-point').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Готово.');
    assert.equal((await page.request.get(base+'/api/v1/points/'+socialPoint+'?site='+active)).status(),200);
    await page.locator('#user-query').fill(handle);
    await page.locator('#user-search-form button').click();
    await page.waitForFunction(()=>!document.querySelector('#user-query').disabled);
    await page.waitForFunction(()=>document.querySelector('#user-results button'));
    assert.equal(await page.locator('#user-results a').getAttribute('href'),'/people/'+authorSession.user_id+'/');
    assert((await page.locator('#user-results small').textContent()).includes('активен'));
    await page.getByRole('button',{name:'Выбрать для доступа',exact:true}).click();
    assert.equal(await page.locator('#role-user').inputValue(),authorSession.user_id);
    // Controls share a baseline on desktop; mobile uses a full-width scope row.
    await page.setViewportSize({width:1000,height:850});
    const aligned=await page.locator('#scope-form').evaluate(form=>{
      const boxes=[...form.querySelectorAll('input,select,button')].map(n=>n.getBoundingClientRect());
      return Math.max(...boxes.map(b=>b.bottom))-Math.min(...boxes.map(b=>b.bottom))<2;
    });
    assert(aligned,'Scope input, status and submit align');
    await page.screenshot({path:'/tmp/node06-moderation-desktop-directory.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'User search fits mobile');
    await page.screenshot({path:'/tmp/node06-moderation-users-mobile.png',fullPage:true});
    await page.locator('#role-form button').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Готово.');
    const delegated=await browser.newContext({ignoreHTTPSErrors:true});
    assert.equal((await delegated.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{handle,password}})).status(),200);
    assert.equal((await delegated.request.get(base+'/api/v1/moderation/cases?scope='+active)).status(),200);
    await page.locator('#role').selectOption('');await page.locator('#role-form button').click();
    await page.waitForFunction(()=>document.querySelector('#status').textContent==='Готово.');
    assert.equal((await delegated.request.get(base+'/api/v1/moderation/cases?scope='+active)).status(),403);
    // Site quarantine is private here and remains ordinary public content elsewhere.
    await page.locator('#ban-user').fill(authorSession.user_id);
    await page.locator('#ban-mode').selectOption('quarantine');
    await page.locator('#ban-reason').fill('Browser quarantine <script>window.banUnsafe=true</script>');
    await page.locator('#ban-form button').click();
    await page.waitForFunction(()=>!document.querySelector('#ban-user').disabled);
    assert.equal(await page.locator('#ban-results script').count(),0);
    assert.equal(await page.evaluate(()=>window.banUnsafe),undefined);
    const isolatedWriter=await delegated.newPage();
    await isolatedWriter.goto(base+'/editor/?'+new URLSearchParams({from:'skills-ru',return_to:'/sites/'+active+'/'}));
    await isolatedWriter.locator('#editor-form[data-ready=true]').waitFor();
    await isolatedWriter.locator('#point-body').fill('Quarantine browser private <script>unsafe()</script>');
    const qResponse=isolatedWriter.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/v1/points');
    await isolatedWriter.locator('#publish').click();
    const qResult=await(await qResponse).json();
    assert.equal(qResult.quarantined,true);
    await isolatedWriter.waitForFunction(()=>document.querySelector('#editor-status').textContent==='Точка сохранена в карантине.');
    assert.equal((await delegated.request.get(base+'/api/v1/points/'+qResult.id+'?site='+active)).status(),404);
    assert.equal((await delegated.request.get(base+'/api/v1/points/'+qResult.id+'?site='+otherSite)).status(),200);
    await isolatedWriter.goto(base+'/quarantine/?'+new URLSearchParams({scope:active,point:qResult.id}));
    await isolatedWriter.locator('#q-article').waitFor({state:'visible'});
    assert((await isolatedWriter.locator('#q-body').textContent()).includes('unsafe()'));
    assert.equal(await isolatedWriter.locator('#q-body script').count(),0);
    await isolatedWriter.setViewportSize({width:390,height:844});
    assert(await isolatedWriter.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Private quarantine fits mobile');
    await isolatedWriter.screenshot({path:'/tmp/node06-quarantine-mobile.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Ban panel fits mobile');
    await page.screenshot({path:'/tmp/node06-scoped-bans-mobile.png',fullPage:true});
    await page.locator('#ban-mode').selectOption('');
    await page.locator('#ban-reason').fill('Browser restore');
    await page.locator('#ban-form button').click();
    await page.waitForFunction(()=>!document.querySelector('#ban-user').disabled);
    assert.equal((await delegated.request.get(base+'/api/v1/points/'+qResult.id+'?site='+active)).status(),200);
    assert.equal((await delegated.request.get(base+'/api/v1/me/quarantine/'+qResult.id+'?scope='+active)).status(),403);
    await delegated.close();
    const discovery=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:390,height:844}});
    const directoryPage=await discovery.newPage();
    await directoryPage.goto(base+'/directory/');
    await directoryPage.locator('#directory-query').fill(handle);
    await directoryPage.locator('#directory-form button').click();
    await directoryPage.waitForFunction(()=>document.querySelector('#directory-results a'));
    assert.equal(await directoryPage.locator('#directory-results a').textContent(),handle);
    assert.equal(await directoryPage.locator('#directory-results a').getAttribute('href'),'/people/'+authorSession.user_id+'/');
    await directoryPage.locator('#directory-results a').click();
    await directoryPage.locator('#author-points a').first().waitFor();
    assert.equal(await directoryPage.locator('#author-name').textContent(),handle);
    await directoryPage.goto(base+'/directory/');
    await directoryPage.locator('#directory-kind').selectOption('users');
    await directoryPage.waitForFunction(()=>document.querySelector('#directory-results a')||document.querySelector('#directory-status').textContent.includes('Расчёт'));
    assert.equal(await directoryPage.locator('#directory-query').isVisible(),false);
    assert(await directoryPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Public directory fits mobile');
    await directoryPage.screenshot({path:'/tmp/node06-directory-mobile.png',fullPage:true});
    assert.equal((await discovery.request.get(embed+'/directory/')).status(),404);
    await discovery.close();
    await require('./check-home-languages.cjs')({browser,base,embed,otherSite,errors});
    await require('./check-git-sources.cjs')({browser,base,otherSite,errors});
    await require('./check-profile-packets.cjs')({browser,base,embed,errors});
    const purged=process.env.NODE06_TEST_PURGED_POINT;
    assert(purged,'Disposable fixture must provide a purged point');
    await page.goto(base+'/?'+new URLSearchParams({p:purged,open:purged}));
    await page.locator('.point-text').filter({hasText:'Point deleted.'}).waitFor();
    assert.equal(await page.locator('.point-actions').count(),0,'Tombstone has no publication actions');
    assert(!(await page.locator('body').innerText()).includes('Purged fixture secret'));
    const marker=await page.request.get(embed+'/bridge/v1/'+active+'/read?'+new URLSearchParams({method:'point.read',point_id:purged}));
    assert.equal(marker.status(),200);assert.equal((await marker.json()).deleted,true);
    assert(embedCookies.length > 0);
    assert((await Promise.all(embedCookies)).every(sent => !sent), 'Actual embed requests must omit the global session cookie');
    assert.deepEqual(errors, []);
    console.log('PASS: hosted UI, public API bridge/SDK, shared bilingual graph/search, rejected writes/spoofs, reload cleanup, real read-only iframe under same-origin-connect CSP, blocked storage and cookie isolation');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
