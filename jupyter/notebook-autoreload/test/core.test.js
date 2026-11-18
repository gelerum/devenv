import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ExecutionQueue, guardedProvider, NotebookWatcher, sessionIdle, version } from '../src/core.js';

const notebook = { nbformat: 4, nbformat_minor: 5, metadata: {}, cells: [] };
const model = hash => ({ path: 'test.ipynb', hash, hash_algorithm: 'sha256',
  last_modified: hash, content: notebook });
const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};

function fixture() {
  const f = {
    path: 'test.ipynb', revision: 0, baseline: model('old'), disk: model('new'),
    ready: true, safe: true, notices: 0, cleared: 0, errors: 0, reverts: 0, gets: 0
  };
  f.base = {
    get: async () => { f.gets += 1; return f.disk; },
    save: async (path, options) => ({ path, ...options })
  };
  f.loader = guardedProvider(f.base);
  f.adapter = {
    ready: () => f.ready,
    path: () => f.path,
    revision: () => f.revision,
    baseline: () => f.baseline,
    safe: () => f.safe,
    stat: async () => f.disk,
    notify: () => { f.notices += 1; },
    clearNotice: () => { f.cleared += 1; },
    error: () => { f.errors += 1; },
    revert: async () => {
      f.reverts += 1;
      // The relevant Context.revert semantics: content:null doesn't replace
      // the model, but the returned metadata ALWAYS replaces the baseline.
      const path = f.path;
      const response = await f.loader.provider.get(path, { content: true });
      if (path !== f.path) { return f.adapter.revert(); }
      f.baseline = response;
      if (response.content) { f.applied = response.content; }
    }
  };
  f.watcher = new NotebookWatcher(f.adapter, f.loader);
  return f;
}

async function changed(f) {
  await f.watcher.poll();
  await f.watcher.poll();
}

test('prefers content hash, falls back to modification time', () => {
  assert.equal(version({ hash: 'abc', hash_algorithm: 'sha256' }), 'sha256:abc');
  assert.equal(version({ last_modified: 'today' }), 'today');
  assert.equal(version(null), null);
});

test('session safety rejects transitions, disconnection, pending input and unready no-kernel state', () => {
  const idle = { isReady: true, session: { kernel: {} }, kernelDisplayStatus: 'idle', pendingInput: false };
  assert.equal(sessionIdle(idle), true);
  assert.equal(sessionIdle({ ...idle, pendingInput: true }), false);
  for (const status of ['busy', 'starting', 'initializing', 'restarting', 'terminating',
    'dead', 'unknown', 'connecting', 'disconnected']) {
    assert.equal(sessionIdle({ ...idle, kernelDisplayStatus: status }), false, status);
  }
  assert.equal(sessionIdle({ ...idle, session: null, kernelDisplayStatus: 'unknown' }), true);
  assert.equal(sessionIdle({ ...idle, session: null, kernelDisplayStatus: 'initializing' }), false);
  assert.equal(sessionIdle({ ...idle, session: null, kernelDisplayStatus: 'unknown', isReady: false }), false);
});

test('execution future cancellation releases the queue without an executed signal', async () => {
  let changes = 0;
  const queue = new ExecutionQueue(() => { changes += 1; });
  const request = deferred();
  queue.schedule(() => ({ done: request.promise }));
  assert.equal(queue.size, 1);
  await new Promise(resolve => queueMicrotask(resolve));
  request.reject(Error('Canceled future for execute_request'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(queue.size, 0);
  assert.equal(changes, 2);
});

test('duplicate cell executions are counted independently', async () => {
  const queue = new ExecutionQueue(() => {});
  const first = deferred();
  const second = deferred();
  queue.schedule(() => ({ done: first.promise }));
  queue.schedule(() => ({ done: second.promise }));
  await new Promise(resolve => queueMicrotask(resolve));
  first.resolve();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(queue.size, 1);
  second.resolve();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(queue.size, 0);
});

test('old kernel completions cannot release new kernel executions', async () => {
  const queue = new ExecutionQueue(() => {});
  const old = deferred();
  const current = deferred();
  queue.schedule(() => ({ done: old.promise }));
  await new Promise(resolve => queueMicrotask(resolve));
  queue.clear();
  queue.schedule(() => ({ done: current.promise }));
  await new Promise(resolve => queueMicrotask(resolve));
  old.reject(Error('Canceled on restart'));
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(queue.size, 1);
  current.resolve();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(queue.size, 0);
});

test('empty/deleted cells do not leave execution tokens behind', async () => {
  const queue = new ExecutionQueue(() => {});
  queue.schedule(() => null);
  queue.schedule(() => { throw Error('disposed cell'); });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(queue.size, 0);
});

test('two stable polls reload clean idle notebook and update baseline', async () => {
  const f = fixture();
  await f.watcher.poll();
  assert.equal(f.reverts, 0);
  await f.watcher.poll();
  assert.equal(f.reverts, 1);
  assert.equal(f.applied, notebook);
  assert.equal(f.baseline.hash, 'new');
  await changed(f);
  assert.equal(f.reverts, 1);
});

test('dirty, saving, disconnected or busy notebook is never reloaded', async () => {
  const f = fixture();
  f.safe = false;
  await changed(f);
  await changed(f);
  assert.equal(f.notices, 1);
  assert.equal(f.reverts, 0);
  f.disk = model('newer');
  await f.watcher.poll();
  assert.equal(f.notices, 2);
});

test('deferred notebook reloads after becoming safe', async () => {
  const f = fixture();
  f.safe = false;
  await changed(f);
  f.safe = true;
  await f.watcher.poll();
  assert.equal(f.reverts, 1);
});

test('own save / identical disk version does not reload or notify', async () => {
  const f = fixture();
  f.disk = model('old');
  await changed(f);
  assert.equal(f.reverts, 0);
  assert.equal(f.notices, 0);
});

test('initial load without a baseline is not mistaken for external edit', async () => {
  const f = fixture();
  f.baseline = null;
  await changed(f);
  assert.equal(f.reverts, 0);
});

test('continuously changing file waits until stable', async () => {
  const f = fixture();
  await f.watcher.poll();
  f.disk = model('newer');
  await f.watcher.poll();
  assert.equal(f.reverts, 0);
  await f.watcher.poll();
  assert.equal(f.reverts, 1);
});

test('hidden/unready/disposed documents are not polled', async () => {
  const f = fixture();
  f.adapter.stat = async () => { throw Error('must not fetch'); };
  f.ready = false;
  await changed(f);
  f.ready = true;
  f.watcher.dispose();
  await f.watcher.poll();
  assert.equal(f.errors, 0);
});

test('one in-flight poll per notebook', async () => {
  const f = fixture();
  const request = deferred();
  let count = 0;
  f.adapter.stat = () => { count += 1; return request.promise; };
  const pending = f.watcher.poll();
  await f.watcher.poll();
  assert.equal(count, 1);
  request.resolve(f.disk);
  await pending;
});

for (const change of ['edit', 'rename', 'busyThenIdle', 'save']) {
  test(`${change} during metadata fetch cancels this poll`, async () => {
    const f = fixture();
    await f.watcher.poll();
    const request = deferred();
    f.adapter.stat = () => request.promise;
    const pending = f.watcher.poll();
    f.revision += 1;
    if (change === 'rename') { f.path = 'renamed.ipynb'; }
    request.resolve(f.disk);
    await pending;
    assert.equal(f.reverts, 0);
  });
}

for (const change of ['edit', 'rename', 'busyThenIdle', 'save', 'dispose']) {
  test(`${change} during CONTENT fetch preserves model AND old hash`, async () => {
    const f = fixture();
    await f.watcher.poll();
    const request = deferred();
    f.base.get = () => request.promise;
    const pending = f.watcher.poll();
    // Let metadata check finish and Context.revert start its content GET.
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(f.reverts, 1);
    if (change === 'dispose') { f.watcher.dispose(); }
    else { f.revision += 1; }
    if (change === 'rename') {
      f.path = 'renamed.ipynb';
      f.baseline = { ...f.baseline, path: f.path };
    }
    request.resolve(f.disk);
    await pending;
    assert.equal(f.applied, undefined);
    if (change === 'rename') { assert.equal(f.baseline.path, 'renamed.ipynb'); }
    assert.equal(f.baseline.hash, 'old');
  });
}

test('new unsaved edits during content fetch block even without revision signal', async () => {
  const f = fixture();
  await f.watcher.poll();
  f.base.get = async () => { f.safe = false; return f.disk; };
  await f.watcher.poll();
  assert.equal(f.applied, undefined);
  assert.equal(f.baseline.hash, 'old');
  assert.equal(f.notices, 1);
});

test('save completing during fetch keeps its latest known baseline', async () => {
  const f = fixture();
  await f.watcher.poll();
  f.base.get = async () => {
    f.revision += 1;
    f.baseline = model('just-saved');
    return f.disk;
  };
  await f.watcher.poll();
  assert.equal(f.applied, undefined);
  assert.equal(f.baseline.hash, 'just-saved');
});

test('metadata errors are retried; in-flight lock is released', async () => {
  const f = fixture();
  f.adapter.stat = async () => { throw Error('offline'); };
  await f.watcher.poll();
  assert.equal(f.errors, 1);
  f.adapter.stat = async () => f.disk;
  await changed(f);
  assert.equal(f.reverts, 1);
});

test('content GET errors do not open core revert error dialogs or accept new hash', async () => {
  const f = fixture();
  f.base.get = async () => { throw Error('partial JSON write'); };
  await changed(f);
  assert.equal(f.errors, 0);
  assert.equal(f.baseline.hash, 'old');
  assert.equal(f.applied, undefined);
  assert.equal(f.notices, 1);
  f.base.get = async () => f.disk;
  await f.watcher.poll();
  assert.equal(f.baseline.hash, 'new');
});

test('invalid notebook content is not applied', async () => {
  const f = fixture();
  f.base.get = async () => ({ ...f.disk, content: {} });
  await changed(f);
  assert.equal(f.baseline.hash, 'old');
  assert.equal(f.applied, undefined);
});

test('only provider content reads identify contexts owned by this extension', async () => {
  const f = fixture();
  await f.loader.provider.get(f.path, { content: false });
  assert.equal(f.loader.served.has(f.path), false);
  await f.loader.provider.get(f.path, { content: true });
  assert.equal(f.loader.served.has(f.path), true);
});

test('manual reads and writes retain default provider behavior', async () => {
  const f = fixture();
  assert.equal(await f.loader.provider.get(f.path, { content: true }), f.disk);
  assert.deepEqual(await f.loader.provider.save(f.path, { content: notebook }), {
    path: f.path, content: notebook
  });
  f.base.get = async () => { throw Error('manual error'); };
  await assert.rejects(f.loader.provider.get(f.path, { content: true }), /manual error/);
});

test('manual revert errors cannot leave an active guard behind', async () => {
  const f = fixture();
  await assert.rejects(f.loader.reload(f.path, () => f.baseline, () => false,
    async () => { throw Error('revert failed'); }), /revert failed/);
  const response = await f.loader.provider.get(f.path, { content: true });
  assert.equal(response.content, notebook);
});
