// Local disposable fixture only. This creates test accounts/sites; never run on production.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.NODE06_PREVIEW_URL || 'https://localhost:8846';
const embed = process.env.NODE06_EMBED_URL || 'https://embed.localhost:8847';
const active = process.env.NODE06_TEST_ACTIVE_SITE;
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
    await page.locator('#point-lang').fill('ru');
    await page.locator('#point-body').fill('воля');
    await page.locator('#point-body').evaluate(input => input.setSelectionRange(0, input.value.length));
    await page.locator('#link-word').click();
    await page.locator('#point-picker-query').fill('skills-ru');
    await page.getByRole('button', { name: 'skills-ru · ru', exact: true }).click();
    await page.getByRole('button', { name: 'Выбрать / Select', exact: true }).click();
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
    await page.locator('#open-point').waitFor({ state: 'visible' });
    const authoredId = new URL(page.url()).searchParams.get('p');
    assert(/^p_[0-9a-f]{32}$/.test(authoredId));
    assert.equal((await (await page.request.get(base + '/api/v1/me/points')).json()).items.length, 1);
    const authored = await (await page.request.get(base + '/api/v1/points/' + authoredId)).json();
    const graph = await (await page.request.get(base + '/data/points.json')).json();
    assert(graph.find(point => point.id === authoredId).links.includes('skills-ru'));
    assert(graph.find(point => point.id === 'skills-ru').links.includes(authoredId));
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Editor fits mobile');
    await page.screenshot({ path: '/tmp/node06-editor-mobile.png', fullPage: true });
    await page.reload();
    await page.locator('#editor-form').waitFor({ state: 'visible' });
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
    await frame.locator('#point-picker-results button').first().waitFor();
    await frame.getByRole('button', { name: /^skills-ru ·/ }).click();
    await frame.locator('#point-picker-detail a').first().waitFor();
    assert((await frame.locator('#point-picker-detail a').first().getAttribute('href')).includes('/embed/v1/'));
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
    await page.locator('#point-picker-detail a').first().waitFor();
    assert((await page.locator('.picker-body').textContent()).includes('<script>'));
    assert.equal(await page.evaluate(() => window.stolen), undefined);
    await page.getByRole('button', { name: 'Выбрать / Select', exact: true }).click();
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
    await page.getByRole('button', { name: /^skills-ru ·/ }).waitFor();
    await page.waitForTimeout(1300);
    assert.equal(await page.getByRole('button', { name: /^stale ·/ }).count(), 0);
    await page.locator('#point-picker-query').fill('zzfail');
    await page.waitForFunction(() => document.querySelector('#point-picker-status').textContent.includes('Search unavailable'));
    assert.equal(await page.locator('#point-picker-query').inputValue(), 'zzfail');
    await page.locator('#point-picker-query').fill('skill');
    await page.getByRole('button', { name: /^skills-ru ·/ }).waitFor();
    if (await page.locator('#point-picker-more').isVisible()) {
      const before = await page.locator('#point-picker-results li').count();
      await page.locator('#point-picker-more').click();
      await page.waitForFunction(before => document.querySelectorAll('#point-picker-results li').length > before, before);
    }
    await page.getByRole('button', { name: 'Закрыть результаты / Close results', exact: true }).click();
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
    await page.goto(base+'/?p='+socialPoint+'&open='+socialPoint);
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-social')?.textContent.includes('Current-version influence: 0.5'));
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-social')?.textContent.includes('You support the current version'));
    assert.equal(await page.locator('#point-panel-body .point-social').getAttribute('data-point-id'),socialPoint);
    const manageHref=await page.locator('#point-panel-body .point-social a').getAttribute('href');
    assert.equal(new URL(manageHref).searchParams.get('p'),socialPoint);
    assert.equal(new URL(manageHref).origin,base);
    assert.equal(await page.locator('#point-panel-body .point-social script').count(),0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:'/tmp/node06-field-social-mobile.png',fullPage:true});

    // Late summaries cannot replace another point, and unavailable data is not zero.
    let started, finished;
    const slowStarted=new Promise(resolve=>{started=resolve;});
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
      const response=await route.fetch(), value=await response.json();
      value.content_digest='0'.repeat(64); await route.fulfill({json:value});
    },{times:1});
    await page.locator('#point-panel-body .point-social button').click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-social')?.textContent.includes('Server text changed'));
    assert(!(await page.locator('#point-panel-body .point-social').innerText()).includes('Current-version influence:'));
    await page.route(base+'/api/v1/points/skills-en/social-summary',route=>route.fulfill({status:400,json:{code:'METHOD_NOT_ALLOWED'}}),{times:1});
    await page.locator('#point-panel-body .point-social button').click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-social')?.textContent.includes('Server update required'));
    assert(await page.locator('#point-panel-body .point-text').isVisible());
    await page.route(base+'/api/v1/me/subscriptions/skills-en',route=>route.fulfill({status:503,json:{code:'UNAVAILABLE'}}),{times:1});
    await page.locator('#point-panel-body .point-social button').click();
    await page.waitForFunction(()=>document.querySelector('#point-panel-body .point-social')?.textContent.includes('Personal support unavailable'));
    await page.goto(base + '/community/?p=skills-ru');
    await page.waitForFunction(() => !document.querySelector('#choose-point').disabled);
    assert.equal(await page.locator('#proposal-form').isVisible(), false, 'Git point proposals are protected');
    assert((await page.locator('#protection').textContent()).includes('Защищённая'));
    await page.goto(base + '/?p=skills-ru&open=skills-ru');
    const related = page.locator('.point-create-related');
    await related.waitFor();
    const relatedHref = await related.getAttribute('href');
    assert.equal(new URL(relatedHref).searchParams.get('from'), 'skills-ru');
    await page.goto(relatedHref);
    await page.locator('#tag-tools').waitFor({state:'visible'});
    await page.waitForFunction(()=>document.querySelector('#favorite-tags').textContent.length > 0);
    assert.equal(await page.locator('#favorite-tags button').count(), 0, 'The fixture owner must not see another account favorites');
    await page.getByRole('button', {name:'☆ Сохранить тег',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#editor-status').textContent.includes('Тег сохранён'));
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#favorite-tags button'));
    assert((await page.locator('#point-links').innerText()).includes('Навык'));
    assert((await page.locator('#favorite-tags').innerText()).includes('Навык'));
    await page.getByRole('button',{name:'Убрать связь',exact:true}).click();
    await page.locator('#favorite-tags button').first().click();
    await page.waitForFunction(()=>document.querySelectorAll('#point-links li').length === 1);
    await page.locator('#point-body').fill('A related point from the current meaning');
    await page.locator('#publish').click();
    await page.locator('#open-point').waitFor({state:'visible'});
    const relatedId = new URL(page.url()).searchParams.get('p');
    const relatedPublished = await (await page.request.get(base+'/api/v1/points/'+relatedId)).json();
    assert(relatedPublished.links.includes('skills-ru'));
    assert.equal(relatedPublished.body,'A related point from the current meaning');
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
    await page.route(base + '/picker-parent', route => route.fulfill({
      path: require('node:path').join(__dirname, '../dist/index.html'),
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
      return document.querySelector('#point-picker-results button') || (text && !text.includes('Searching'));
    });
    assert(await page.locator('#point-picker-results button').count(),
      'Static picker: ' + await page.locator('#point-picker-status').textContent());
    await page.locator('#point-picker-results button').first().click();
    await page.locator('#point-picker-detail a').first().waitFor();
    const destination = new URL(await page.locator('#point-picker-detail a').first().getAttribute('href'));
    assert((await page.locator('#point-picker-detail').boundingBox()).y < 844, 'Selected detail must be in view');
    assert.equal(destination.origin, base);
    assert.equal(destination.pathname, `/sites/${active}/`);
    assert.equal(await page.locator('#point-picker-detail a').first().getAttribute('target'), '_blank');
    const publicSocial=await page.evaluate(()=>window.readNode06Public('point.social',{point_id:'skills-ru'}));
    assert.equal(publicSocial.id,'skills-ru');
    assert.equal(publicSocial.protected,true);
    const socialBox=page.locator('#point-picker-detail .point-social');
    await socialBox.getByRole('link').waitFor();
    await page.waitForFunction(()=>document.querySelector('#point-picker-detail .point-social')?.textContent.includes('Source-managed point'));
    assert.equal(new URL(await socialBox.locator('a').getAttribute('href')).origin,base);
    assert((await socialBox.innerText()).includes('Open account to manage support'));

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
    await page.locator('#point-picker-results button').first().waitFor();
    await searchInput.press('ArrowDown');
    assert.equal(await page.locator('#point-picker-results button').first().evaluate(node => node === document.activeElement), true);
    await page.locator('main').click({ position: { x: 3, y: 3 } });
    assert.equal(await page.locator('#point-picker').isVisible(), false, 'Outside click dismisses results');
    await searchInput.fill('');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: '/tmp/node06-search-field-mobile.png', fullPage: true });
    assert(embedCookies.length > 0);
    assert((await Promise.all(embedCookies)).every(sent => !sent), 'Actual embed requests must omit the global session cookie');
    assert.deepEqual(errors, []);
    console.log('PASS: hosted UI, public API bridge/SDK, shared bilingual graph/search, rejected writes/spoofs, reload cleanup, real read-only iframe under same-origin-connect CSP, blocked storage and cookie isolation');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack || error.message); process.exitCode = 1; });
