import { ICommandPalette, Notification } from '@jupyterlab/apputils';
import { INotebookWidgetFactory, NotebookActions } from '@jupyterlab/notebook';
import { RestContentProvider } from '@jupyterlab/services';
import { ExecutionQueue, guardedProvider, NotebookWatcher, sessionIdle } from './core.js';

const PROVIDER = '@devenv/notebook-autoreload';
const INTERVAL = 2000;

export default {
  id: `${PROVIDER}:plugin`,
  autoStart: true,
  requires: [INotebookWidgetFactory, ICommandPalette],
  activate(app, factory, palette) {
    const contents = app.serviceManager.contents;
    const registry = contents.defaultDrive.contentProviderRegistry;
    // Never replace another extension's provider (e.g. real-time collaboration).
    // A standard Drive uses REST when getProvider() is null.
    if (!registry || registry.getProvider() || factory.contentProviderId) {
      console.warn('devenv notebook auto-reload: non-default content provider; disabled.');
      return;
    }
    const base = new RestContentProvider({
      apiEndpoint: 'api/contents', serverSettings: contents.defaultDrive.serverSettings
    });
    const loader = guardedProvider(base);
    registry.register(PROVIDER, loader.provider);
    factory.contentProviderId = PROVIDER;
    const watched = new WeakSet();
    let enabled = true;
    let policyRevision = 0;
    const command = 'devenv-notebook-autoreload:toggle';
    app.commands.addCommand(command, {
      label: 'Auto-Reload External Notebook Changes',
      caption: 'Reload saved, idle notebooks when their files change on disk',
      isToggled: () => enabled,
      execute: () => {
        enabled = !enabled;
        policyRevision += 1;
        app.commands.notifyCommandChanged(command);
      }
    });
    palette.addItem({ command, category: 'Notebook' });

    factory.widgetCreated.connect((_factory, panel) => {
      const context = panel.context;
      // Other drives don't have our provider. Split views share one context.
      if (contents.driveName(context.path) || watched.has(context)) {
        return;
      }
      watched.add(context);
      // A reused context can predate activation (even while still loading).
      // Only poll contexts whose initial content GET used our guarded provider.
      let provided = false;
      void context.ready.then(() => {
        provided = loader.served.has(contents.localPath(context.path));
      }).catch(() => { /* Initial load failed: no polling. */ });
      let revision = 0;
      let saving = false;
      let notification = null;
      let errors = false;
      const bump = () => { revision += 1; };
      const executing = new ExecutionQueue(bump);
      const onSave = (_sender, state) => {
        saving = state === 'started';
        bump();
      };
      const onExecution = (_sender, args) => {
        if (args.notebook.model === context.model) {
          executing.schedule(() => args.cell.isDisposed ? null : args.cell.outputArea?.future);
        }
      };
      const onKernelChanged = () => {
        executing.clear();
        bump();
      };
      const clearNotice = () => {
        if (notification) {
          Notification.dismiss(notification);
          notification = null;
        }
      };
      const safe = () => {
        return enabled && context.isReady && !context.isDisposed && !saving &&
          !context.model.dirty && !context.model.collaborative && executing.size === 0 &&
          sessionIdle(context.sessionContext);
      };
      const watcher = new NotebookWatcher({
        ready: () => provided && enabled && context.isReady && !context.isDisposed && !document.hidden,
        path: () => contents.localPath(context.path),
        revision: () => revision + policyRevision,
        baseline: () => context.contentsModel,
        safe,
        stat: path => base.get(path, { content: false, hash: true }),
        revert: () => context.revert(),
        clearNotice: () => { errors = false; clearNotice(); },
        notify: () => {
          clearNotice();
          notification = Notification.warning(
            `${context.path} changed on disk. Auto-reload deferred to preserve unsaved edits ` +
            'or kernel execution. Use “Reload Notebook from Disk” to load it manually ' +
            '(discards unsaved changes).',
            { autoClose: 8000 }
          );
        },
        error: () => {
          if (!errors) {
            errors = true;
            // Avoid logging file contents, response objects or tokenized URLs.
            console.warn('devenv notebook auto-reload: file check failed; will retry.');
          }
        }
      }, loader);
      context.model.contentChanged.connect(bump);
      context.pathChanged.connect(bump);
      context.saveState.connect(onSave);
      context.sessionContext.statusChanged.connect(bump);
      context.sessionContext.connectionStatusChanged.connect(bump);
      context.sessionContext.kernelChanged.connect(onKernelChanged);
      context.sessionContext.sessionChanged.connect(onKernelChanged);
      NotebookActions.executionScheduled.connect(onExecution);
      const timer = setInterval(() => { void watcher.poll(); }, INTERVAL);
      context.disposed.connect(() => {
        watcher.dispose();
        executing.clear();
        clearInterval(timer);
        clearNotice();
        context.model.contentChanged.disconnect(bump);
        context.pathChanged.disconnect(bump);
        context.saveState.disconnect(onSave);
        context.sessionContext.statusChanged.disconnect(bump);
        context.sessionContext.connectionStatusChanged.disconnect(bump);
        context.sessionContext.kernelChanged.disconnect(onKernelChanged);
        context.sessionContext.sessionChanged.disconnect(onKernelChanged);
        NotebookActions.executionScheduled.disconnect(onExecution);
      });
    });
  }
};
