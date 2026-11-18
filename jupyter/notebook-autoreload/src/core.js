// No Jupyter imports: the reload policy and its races can be tested offline.
export function version(model) {
  if (model?.hash) {
    return `${model.hash_algorithm ?? ''}:${model.hash}`;
  }
  return model?.last_modified ?? null;
}

export function sessionIdle(session) {
  if (session.pendingInput) {
    return false;
  }
  const status = session.kernelDisplayStatus;
  return status === 'idle' ||
    (!session.session?.kernel && session.isReady && status === 'unknown');
}

/** Execution completion signals omit cancellations; futures settle in both cases. */
export class ExecutionQueue {
  constructor(changed) {
    this.changed = changed;
    this.tokens = new Set();
  }

  get size() { return this.tokens.size; }

  schedule(getFuture) {
    const token = {};
    this.tokens.add(token);
    this.changed();
    const finish = () => {
      if (this.tokens.delete(token)) { this.changed(); }
    };
    // In JupyterLab 4.6.6 CodeCell.execute assigns outputArea.future synchronously
    // immediately after executionScheduled. Capture it before the next UI task.
    queueMicrotask(() => {
      if (!this.tokens.has(token)) { return; }
      try {
        const future = getFuture();
        if (future) { void future.done.then(finish, finish); }
        else { finish(); } // Empty cell, deleted cell or no kernel.
      } catch {
        finish();
      }
    });
  }

  clear() {
    if (this.tokens.size) {
      this.tokens.clear();
      this.changed();
    }
  }
}

/**
 * A per-notebook content provider, not a patch of the global contents manager.
 * Context.revert() fetches asynchronously and then replaces the notebook model.
 * Check again AFTER the fetch so typing/execution/save during it cannot be lost.
 * Returning the original metadata with no content makes revert a true no-op:
 * in particular it must NOT accept the new disk hash if nothing was reloaded.
 */
export function guardedProvider(base) {
  const guards = new Map();
  const served = new Set();
  return {
    served,
    provider: {
      sharedModelFactory: base.sharedModelFactory,
      async get(path, options) {
        // Context.revert() retries at the new path if the document is renamed
        // during its GET. Keep that recursive request guarded as well.
        const guard = guards.get(path) ?? [...guards.values()].find(g => g.currentPath() === path);
        if (options?.content !== false) {
          served.add(path);
        }
        let result;
        try {
          result = await base.get(path, options);
        } catch (error) {
          if (!guard || options?.content === false) {
            throw error;
          }
          // An automatic reload must not produce a modal error every poll when
          // an external writer has left a partial file, or the network is down.
          guard.deferred = true;
          return { ...guard.baseline(), content: null };
        }
        if (guard && options?.content !== false) {
          if (!guard.safe() || !Array.isArray(result.content?.cells) ||
              !result.content?.metadata || result.content?.nbformat !== 4) {
            guard.deferred = true;
            return { ...guard.baseline(), content: null };
          }
        }
        return result;
      },
      save: (path, options) => base.save(path, options)
    },
    async reload(path, baseline, safe, revert, currentPath = () => path) {
      if (guards.has(path)) {
        return false;
      }
      const guard = { baseline, safe, currentPath, deferred: false };
      guards.set(path, guard);
      try {
        await revert();
        return !guard.deferred;
      } finally {
        guards.delete(path);
      }
    }
  };
}

/** One instance per document context (split views share a context). */
export class NotebookWatcher {
  constructor(adapter, loader) {
    this.adapter = adapter;
    this.loader = loader;
    this.pending = false;
    this.disposed = false;
    this.candidate = null;
    this.notice = null;
  }

  dispose() {
    this.disposed = true;
  }

  warn(diskVersion) {
    if (this.notice !== diskVersion) {
      this.notice = diskVersion;
      this.adapter.notify();
    }
  }

  async poll() {
    const a = this.adapter;
    if (this.disposed || this.pending || !a.ready()) {
      return;
    }
    this.pending = true;
    try {
      const path = a.path();
      const revision = a.revision();
      const baseline = a.baseline();
      const baselineVersion = version(baseline);
      const disk = await a.stat(path);
      if (this.disposed || path !== a.path() || revision !== a.revision()) {
        this.candidate = null;
        return;
      }
      const diskVersion = version(disk);
      // No baseline means we cannot tell an external edit from initial loading.
      if (!baselineVersion || !diskVersion || diskVersion === version(a.baseline())) {
        this.candidate = null;
        this.notice = null;
        a.clearNotice();
        return;
      }
      const stable = this.candidate === diskVersion;
      this.candidate = diskVersion;
      if (!a.safe()) {
        this.warn(diskVersion);
        return;
      }
      // Two equal observations avoid reloading in the middle of a writer's save.
      if (!stable) {
        return;
      }
      const safe = () => !this.disposed && path === a.path() &&
        revision === a.revision() && baselineVersion === version(a.baseline()) && a.safe();
      const reloaded = await this.loader.reload(
        path, () => a.baseline(), safe, () => a.revert(), () => a.path()
      );
      if (!this.disposed && !reloaded) {
        this.warn(diskVersion);
      } else if (!this.disposed) {
        this.candidate = null;
        this.notice = null;
        a.clearNotice();
      }
    } catch (error) {
      // Deletions, partial JSON writes and temporary network failures are retried.
      // Never log the response/request URL (it may include credentials).
      this.adapter.error(error);
    } finally {
      this.pending = false;
    }
  }
}
