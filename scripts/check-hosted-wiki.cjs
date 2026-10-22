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
    await page.locator('#submit').click();
    await page.locator('#recovery-result').waitFor({ state: 'visible' });
    await page.locator('#password').fill(password);
    await page.locator('#submit').click();
    await page.waitForFunction(() => document.querySelector('#status').textContent.startsWith('Вход выполнен:'));
    await page.locator('nav a[href="/sites/"]').click();
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
    assert(embedCookies.length > 0);
    assert((await Promise.all(embedCookies)).every(sent => !sent), 'Actual embed requests must omit the global session cookie');
    assert.deepEqual(errors, []);
    console.log('PASS: hosted UI/create/proof download/renew, conflict and session drafts, shared graph, real read-only iframe under same-origin-connect CSP, blocked storage and cookie isolation');
  } finally { await browser.close(); }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
