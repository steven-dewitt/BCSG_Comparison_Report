// Drives BCSG_Comparison.html in headless Chromium for the test suite.
// usage: node driver.cjs <html> <data file> <out dir> <search text> [baseline] [screenshot.png]
// Prints a JSON summary of what the page showed; exports are saved into <out dir>.
const path = require('path');
const { chromium } = require('playwright');

(async () => {
  const [html, data, outDir, search, baseline, shot] = process.argv.slice(2);
  const browser = await chromium.launch();
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1400, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto('file://' + path.resolve(html));
  await page.setInputFiles('#file', data);
  await page.waitForSelector('#layout:not([hidden])', { timeout: 10000 }).catch(() => {});
  const loadError = await page.textContent('#loadError');
  const result = { errors, loadError, status: await page.textContent('#status') };
  if (!loadError) {
    await page.fill('#search', search);
    await page.press('#search', 'Enter');
    if (baseline) await page.selectOption('#baseline', baseline);
    result.selected = await page.$$eval('#chips .chip', (els) => els.map((e) => e.dataset.label));
    result.summary = await page.$$eval('#report table:first-of-type tbody tr', (rows) =>
      rows.map((r) => Array.from(r.cells).map((c) => c.textContent)));
    result.svgCount = await page.$$eval('#report svg', (s) => s.length);
    result.headings = await page.$$eval('#report h2, #report h3', (s) => s.map((h) => h.textContent));
    for (const id of ['exportXlsx', 'exportHtml', 'exportCsv']) {
      const [dl] = await Promise.all([page.waitForEvent('download'), page.click('#' + id)]);
      const target = path.join(outDir, dl.suggestedFilename());
      await dl.saveAs(target);
      result[id] = target;
    }
    if (shot) await page.screenshot({ path: shot });
    // Reload: the saved data and selection should come back without reopening the file.
    await page.reload();
    result.afterReload = await page.$$eval('#chips .chip', (els) => els.map((e) => e.dataset.label));
  }
  console.log(JSON.stringify(result));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
