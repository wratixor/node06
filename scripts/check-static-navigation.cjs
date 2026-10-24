// Read-only browser regression against a locally served build. No production writes.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const base = process.env.NODE06_PREVIEW_URL || 'http://127.0.0.1:8766';

function neighborhood(points, id) {
  const index = new Map(points.map(p => [p.id, p]));
  const depths = new Map([[id, 0]]);
  let frontier = [id];
  for (let depth = 1; depth <= 2; depth++) {
    const next = [];
    for (const source of frontier) for (const target of index.get(source).links) {
      if (index.has(target) && !depths.has(target)) {
        depths.set(target, depth);
        next.push(target);
      }
    }
    frontier = next;
  }
  return [...depths].sort(([a], [b]) => a.localeCompare(b));
}

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.NODE06_BROWSER_EXECUTABLE ? { executablePath: process.env.NODE06_BROWSER_EXECUTABLE } : {}) });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    // Offline field/navigation fixture: do not contact the production bridge.
    // The packaged HTTPS fixture separately exercises the real two-origin SDK.
    await page.route('**/assets/connection.json', route => route.abort());
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const points = await (await fetch(`${base}/data/points.json`)).json();
    const connection = await (await fetch(`${base}/assets/connection.json`)).json();
    await page.goto(base + '/');
    for (const path of ['/account/', '/sites/', '/community/', '/editor/']) {
      await page.locator(`nav a[href="${connection.serviceOrigin}${path}"]`).waitFor();
    }
    await page.locator('nav a[href="/setup/en/"]').click();
    await page.waitForURL('**/setup/en/');
    assert.match(await page.locator('main').innerText(), /Mode 5/);
    await page.locator('main a[href="/setup/"]').click();
    await page.waitForURL('**/setup/');
    assert.match(await page.locator('main').innerText(), /Режим 5/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(base + '/');
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.setViewportSize({ width: 1440, height: 1000 });

    async function checkField(id, dataset = points) {
      await page.waitForFunction(id => document.querySelector('#field-center-id')?.textContent === id, id);
      const nodes = await page.locator('#field-map .node').evaluateAll(nodes => nodes.map(n =>
        [n.dataset.id, Number(n.classList.contains('center') ? 0 : n.classList.contains('depth-1') ? 1 : 2)]));
      assert.deepEqual(nodes.sort(([a], [b]) => a.localeCompare(b)), neighborhood(dataset, id), id);
      assert.equal(new URL(page.url()).pathname, '/');
      const positions = await page.locator('#field-map .node circle').evaluateAll(nodes =>
        nodes.map(n => `${Number(n.getAttribute('cx')).toFixed(4)},${Number(n.getAttribute('cy')).toFixed(4)}`));
      assert.equal(new Set(positions).size, positions.length, `coincident spheres at ${id}`);
    }
    // Every existing root, including the intentionally isolated root.
    for (const point of points) {
      await page.goto(`${base}/?p=${point.id}&open=${point.id}`);
      await checkField(point.id);
    }
    for (const prefix of ['ru', 'en']) {
      await page.goto(`${base}/${prefix}/?p=field-ru&open=field-ru`);
      await checkField('field-ru');
      await page.locator('.point-text [data-point-id="field-en"]').click();
      await checkField('field-en');
      await page.goBack();
      await checkField('field-ru');
      await page.goForward();
      await checkField('field-en');
      await page.goto(`${base}/${prefix}/`);
      await page.waitForURL(`${base}/`);
      assert.equal(await page.locator('#start-page').isVisible(), true);
    }
    await page.goto(`${base}/?p=skills-ru&open=skills-ru`);
    await checkField('skills-ru');
    await page.locator('[data-mode="feed"]').click();
    await page.locator('.creation-feed-status').waitFor();
    assert.equal(new URL(await page.locator('.creation-feed-status + a').getAttribute('href')).pathname, '/community/');
    assert.equal(await page.locator('[data-feed-id]').count(), 0);
    await page.locator('[data-mode="read"]').click();
    await page.locator('.field-head h1 a').click();
    await page.waitForURL(`${base}/`);
    assert.equal(await page.locator('#start-page').isVisible(), true);
    assert.equal(await page.locator('#root-field').isVisible(), false);
    for (const path of ['/recent/', '/ru/recent/', '/en/recent/']) {
      await page.goto(base + path);
      await page.waitForURL(`${base}/recent/`);
      assert.equal(await page.locator('.recent li').count(), points.length);
    }
    await page.goto(`${base}/p/skills-ru/`);
    await checkField('skills-ru');
    await page.goto(`${base}/ru/p/skills-ru/`);
    await checkField('skills-ru');

    // A third-language point without a paired translation must work identically.
    const fixture = structuredClone(points);
    const source = fixture.find(p => p.id === 'field-ru');
    source.links.push('test-ja');
    fixture.push({ ...source, id: 'test-ja', lang: 'ja', html: '<p>言葉</p>',
      links: ['field-ru'], degree: 1 });
    await page.route('**/data/points.json', route => route.fulfill({ json: fixture }));
    await page.goto(`${base}/?p=field-ru&open=field-ru`);
    await checkField('field-ru', fixture);
    await page.locator('.links-list [data-point-id="test-ja"]').click();
    await checkField('test-ja', fixture);
    assert.equal(await page.locator('.point-text').textContent(), '言葉');
    assert.equal(await page.locator('.point-text').getAttribute('lang'), 'ja');
    assert.equal(await page.locator('[data-mode="read"]').textContent(), 'READ');
    await page.locator('[data-layout="overlay"]').click();
    await page.locator('#point-panel-close').click();
    assert.equal(await page.locator('#point-panel').isVisible(), false);
    const before = await page.locator('#field-map').innerHTML();
    await page.locator('#field-map').press('w');
    assert.notEqual(await page.locator('#field-map').innerHTML(), before);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${base}/?p=skills-ru&open=skills-ru`);
    await checkField('skills-ru', fixture);
    assert.deepEqual(errors, []);
    console.log(`PASS: ${points.length} roots, full shared neighborhoods, canonical/legacy navigation, third language, feed, overlay and WASD`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
