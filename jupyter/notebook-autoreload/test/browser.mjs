// Opt-in real JupyterLab smoke, called by tests/test_notebook_autoreload.py.
// Only the synthetic notebook in the temporary test project is modified.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.DEVENV_TEST_PLAYWRIGHT);
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage();
const browserErrors = [];
page.on('pageerror', error => browserErrors.push(error.message));
page.on('console', message => {
  if (message.type() === 'error' || message.text().includes('devenv')) {
    browserErrors.push(message.text());
  }
});
const file = join(process.env.AUTORELOAD_TEST_ROOT, 'test.ipynb');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const watchdog = setTimeout(async () => {
  console.error('Browser watchdog:', await page.evaluate(() => ({
    dirty: window.__testPanel?.context.model.dirty,
    dialogs: Array.from(document.querySelectorAll('.jp-Dialog')).map(node => node.textContent)
  })).catch(() => 'unavailable'));
  await browser.close();
}, 80000);
async function externalEdit(source) {
  const document = JSON.parse(await readFile(file, 'utf8'));
  document.cells[0].source = source;
  await writeFile(file, JSON.stringify(document));
}
async function expectSource(source) {
  await page.waitForFunction(expected =>
    window.__testPanel.context.model.cells.get(0).sharedModel.getSource() === expected,
  source, { timeout: 20000 });
}
async function source() {
  return page.evaluate(() => window.__testPanel.context.model.cells.get(0).sharedModel.getSource());
}
async function manualReload() {
  await page.evaluate(async () => { await window.__testPanel.context.revert(); });
}

try {
  await page.goto(process.env.AUTORELOAD_TEST_URL);
  await page.waitForFunction(() => window.jupyterapp?.commands.hasCommand('docmanager:open'),
    null, { timeout: 40000 });
  await page.evaluate(async () => {
    const app = window.jupyterapp;
    await app.restored;
    window.__testPanel = await app.commands.execute('docmanager:open', {
      path: 'test.ipynb', factory: 'Notebook'
    });
    await window.__testPanel.context.ready;
    await window.__testPanel.context.sessionContext.ready;
    await window.__testPanel.context.save();
  });
  await page.waitForFunction(() => {
    const context = window.__testPanel.context;
    return context.sessionContext.session?.kernel?.status === 'idle';
  });
  // Kernel-info metadata can arrive after sessionContext.ready.
  await page.evaluate(() => window.__testPanel.context.save());
  const kernel = await page.evaluate(() => window.__testPanel.context.sessionContext.session.kernel.id);
  await externalEdit('external clean edit');
  await expectSource('external clean edit');
  // Saving after auto-reload must not raise a stale-hash conflict dialog.
  console.log('Reloaded external edit; checking save baseline');
  await page.evaluate(() => window.__testPanel.context.save());
  console.log('PASS: clean external edit reloads; save baseline is current');

  await page.evaluate(() => window.__testPanel.context.model.cells.get(0).sharedModel.setSource('unsaved browser edit'));
  await externalEdit('disk edit while dirty');
  await pause(5500);
  assert.equal(await source(), 'unsaved browser edit');
  await page.waitForFunction(() => document.body.textContent.includes('Auto-reload deferred'));
  console.log('PASS: dirty notebook preserved and notification displayed');
  await manualReload();

  // Hold a real content response after the server has read it, then type.
  let release;
  let held;
  let arm = false;
  const responseHeld = new Promise(resolve => { held = resolve; });
  const responseRelease = new Promise(resolve => { release = resolve; });
  await page.route('**/api/contents/test.ipynb?*', async route => {
    const url = new URL(route.request().url());
    if (arm && route.request().method() === 'GET' && url.searchParams.get('content') !== '0') {
      arm = false;
      const response = await route.fetch();
      held();
      await responseRelease;
      await route.fulfill({ response });
    } else {
      await route.continue();
    }
  });
  arm = true;
  const oldHash = await page.evaluate(() => window.__testPanel.context.contentsModel.hash);
  await externalEdit('disk edit with delayed fetch');
  await Promise.race([responseHeld, pause(20000).then(() => { throw Error('content fetch did not start'); })]);
  await page.evaluate(() => window.__testPanel.context.model.cells.get(0).sharedModel.setSource('typed during fetch'));
  release();
  await pause(2500);
  assert.equal(await source(), 'typed during fetch');
  assert.equal(await page.evaluate(() => window.__testPanel.context.contentsModel.hash), oldHash);
  console.log('PASS: typing during content fetch preserves local model AND old disk hash');
  await page.unroute('**/api/contents/test.ipynb?*');
  await manualReload();

  // Direct execution changes kernel status, but not notebook outputs/dirty state.
  await page.evaluate(() => {
    window.__busyFuture = window.__testPanel.context.sessionContext.session.kernel.requestExecute({
      code: 'import time; time.sleep(8)'
    });
  });
  await page.waitForFunction(() => window.__testPanel.context.sessionContext.session.kernel.status === 'busy');
  await externalEdit('disk edit while busy');
  await pause(4500);
  assert.equal(await source(), 'disk edit with delayed fetch');
  await page.evaluate(() => window.__busyFuture.done);
  await expectSource('disk edit while busy');
  assert.equal(await page.evaluate(() => window.__testPanel.context.sessionContext.session.kernel.id), kernel);
  console.log('PASS: busy kernel blocks reload; idle resumes; kernel identity unchanged');

  // NotebookActions.executed is NOT emitted for a Canceled execution future.
  await page.evaluate(async () => {
    window.__testPanel.context.model.cells.get(0).sharedModel.setSource('import time; time.sleep(30)');
    await window.__testPanel.context.save();
    window.__canceledRun = window.jupyterapp.commands.execute('notebook:run-cell');
    void window.__canceledRun.catch(() => {});
  });
  await page.waitForFunction(() => window.__testPanel.context.sessionContext.session.kernel.status === 'busy');
  await page.evaluate(async () => {
    await window.__testPanel.context.sessionContext.restartKernel();
    await window.__canceledRun;
    await window.__testPanel.context.save();
  });
  await externalEdit('disk edit after canceled execution');
  await expectSource('disk edit after canceled execution');
  console.log('PASS: canceled notebook execution / restart does not permanently block auto-reload');

  await page.evaluate(() => window.jupyterapp.commands.execute('devenv-notebook-autoreload:toggle'));
  await externalEdit('disk edit with auto-reload disabled');
  await pause(5000);
  assert.equal(await source(), 'disk edit after canceled execution');
  await page.evaluate(() => window.jupyterapp.commands.execute('devenv-notebook-autoreload:toggle'));
  await expectSource('disk edit with auto-reload disabled');
  console.log('PASS: command palette toggle pauses and resumes auto-reload');

  await page.reload();
  await page.waitForFunction(() => window.jupyterapp?.commands.hasCommand('docmanager:open'));
  await page.evaluate(async () => {
    await window.jupyterapp.restored;
    window.__testPanel = await window.jupyterapp.commands.execute('docmanager:open', {
      path: 'test.ipynb', factory: 'Notebook'
    });
    await window.__testPanel.context.ready;
  });
  await externalEdit('disk edit after browser refresh');
  await expectSource('disk edit after browser refresh');
  console.log('PASS: workspace restoration after browser refresh retains auto-reload');
} catch (error) {
  console.error('Browser state:', await page.evaluate(() => {
    const context = window.__testPanel?.context;
    return { provider: window.jupyterapp?.docRegistry.getWidgetFactory('Notebook')?.contentProviderId,
      active: window.jupyterapp?.isPluginActivated('@devenv/notebook-autoreload:plugin'),
      dirty: context?.model.dirty, ready: context?.isReady,
      kernel: context?.sessionContext.session?.kernel?.status,
      dialogs: Array.from(document.querySelectorAll('.jp-Dialog')).map(node => node.textContent) };
  }).catch(() => 'unavailable'));
  console.error('Browser errors:', browserErrors);
  throw error;
} finally {
  clearTimeout(watchdog);
  await browser.close();
}
