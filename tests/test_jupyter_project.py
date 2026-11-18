import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('jupyter_project', ROOT / 'scripts/jupyter_project.py')
jupyter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jupyter)


class ProjectJupyterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.project = self.base / 'project with spaces'
        self.project.mkdir()
        self.python = self.project / '.venv/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.symlink_to(sys.executable)
        self.tools = self.base / 'tools'
        for name in ('jupyter-lab', 'basedpyright-langserver', 'ruff'):
            path = self.tools / 'bin' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('test')
        self.state = self.base / 'state'

    def prepare(self):
        return jupyter.prepare(self.project, self.python, self.tools, self.state, 8888)

    def test_only_project_kernel_and_no_symlink_resolution(self):
        command, env = self.prepare()
        config = json.loads(Path(command[-1]).read_text())
        kernel_root = Path(env['JUPYTER_PATH']) / 'kernels'
        kernels = list(kernel_root.glob('*/kernel.json'))
        self.assertEqual(len(kernels), 1)
        kernel = json.loads(kernels[0].read_text())
        self.assertEqual(kernel['argv'][0], str(self.python))
        self.assertNotEqual(kernel['argv'][0], str(self.python.resolve()))
        self.assertEqual(kernel['env']['VIRTUAL_ENV'], str(self.python.parent.parent))
        self.assertFalse(config['KernelSpecManager']['ensure_native_kernel'])
        self.assertEqual(config['KernelSpecManager']['allowed_kernelspecs'], [kernels[0].parent.name])
        self.assertEqual(config['MappingKernelManager']['default_kernel_name'], kernels[0].parent.name)
        self.assertEqual(config['ServerApp']['port_retries'], 0)
        self.assertEqual(config['ServerApp']['root_dir'], str(self.project))
        self.assertEqual(env['JUPYTER_RUNTIME_DIR'], str(self.state / 'runtime'))

    def test_lsp_uses_same_interpreter_and_standard_type_checking(self):
        self.prepare()
        settings = json.loads((self.state / 'settings/@jupyter-lsp/jupyterlab-lsp/plugin.jupyterlab-settings').read_text())
        server = settings['language_servers']['basedpyright']['serverSettings']
        self.assertEqual(server['python.pythonPath'], str(self.python))
        self.assertEqual(server['basedpyright.analysis.typeCheckingMode'], 'standard')
        config = json.loads((self.state / 'config/jupyter_server_config.json').read_text())
        self.assertFalse(config['LanguageServerManager']['autodetect'])
        self.assertEqual(list(config['LanguageServerManager']['language_servers']), ['basedpyright'])

    def test_adaptive_catppuccin_defaults(self):
        self.prepare()
        path = self.state / 'settings/@jupyterlab/apputils-extension/themes.jupyterlab-settings'
        self.assertEqual(json.loads(path.read_text()), {
            'theme': 'Catppuccin Latte',
            'adaptive-theme': True,
            'preferred-light-theme': 'Catppuccin Latte',
            'preferred-dark-theme': 'Catppuccin Mocha',
        })

    def test_theme_choice_survives_restart(self):
        self.prepare()
        path = self.state / 'settings/@jupyterlab/apputils-extension/themes.jupyterlab-settings'
        choice = {'theme': 'Catppuccin Mocha', 'adaptive-theme': False}
        path.write_text(json.dumps(choice))
        self.prepare()
        self.assertEqual(json.loads(path.read_text()), choice)

    def test_editor_font_matches_ghostty(self):
        self.prepare()
        path = self.state / 'settings/@jupyterlab/codemirror-extension/plugin.jupyterlab-settings'
        self.assertEqual(json.loads(path.read_text()), {
            'defaultConfig': {'customStyles': {
                'fontFamily': '"JetBrainsMono Nerd Font", monospace',
                'fontSize': 16,
            }},
        })

    def test_editor_font_choice_survives_restart(self):
        self.prepare()
        path = self.state / 'settings/@jupyterlab/codemirror-extension/plugin.jupyterlab-settings'
        choice = {'defaultConfig': {'customStyles': {'fontSize': 18}}}
        path.write_text(json.dumps(choice))
        self.prepare()
        self.assertEqual(json.loads(path.read_text()), choice)

    def test_formatter_sort_then_format_with_project_configuration(self):
        (self.project / 'pyproject.toml').write_text('[tool.ruff]\nline-length = 90\n')
        self.prepare()
        settings = json.loads((self.state / 'settings/jupyterlab_code_formatter/settings.jupyterlab-settings').read_text())
        self.assertTrue(settings['formatOnSave'])
        self.assertEqual(settings['preferences']['default_formatter']['python'], ['ruff', 'ruffformat'])
        self.assertEqual(settings['ruffformat']['args'], ['--config', str(self.project / 'pyproject.toml')])
        self.assertEqual(settings['ruff']['args'][-1], '--select=I001')

    def test_formatter_uses_standalone_ruff_config(self):
        # A pyproject without tool.ruff must not hide a standalone config.
        (self.project / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        (self.project / 'ruff.toml').write_text('line-length = 90\n')
        self.prepare()
        settings = json.loads((self.state / 'settings/jupyterlab_code_formatter/settings.jupyterlab-settings').read_text())
        self.assertEqual(settings['ruffformat']['args'], ['--config', str(self.project / 'ruff.toml')])

    def test_no_live_server_status_fails_without_token_or_launch(self):
        args = ['jupyter_project', '--project', str(self.project),
                '--state-base', str(self.state), '--status']
        with patch.object(sys, 'argv', args), \
                patch.object(jupyter, 'project_root', return_value=self.project), \
                patch.object(jupyter.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(ValueError, 'No running Jupyter'):
                jupyter.main()
        popen.assert_not_called()

    def test_private_token_config_and_sanitized_environment(self):
        with patch.dict(os.environ, {'JUPYTER_TOKEN': '', 'JUPYTER_TOKEN_FILE': '/other',
                                     'PYTHONPATH': '/another-project', 'PYTHONHOME': '/other'}):
            command, env = self.prepare()
        config = json.loads(Path(command[-1]).read_text())
        self.assertGreaterEqual(len(config['IdentityProvider']['token']), 32)
        self.assertEqual(Path(command[-1]).stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        for name in ('JUPYTER_TOKEN', 'JUPYTER_TOKEN_FILE', 'PYTHONPATH', 'PYTHONHOME'):
            self.assertNotIn(name, env)

    def test_distinct_projects_have_distinct_kernel_names(self):
        self.prepare()
        other = self.base / 'other'
        other.mkdir()
        other_state = self.base / 'other-state'
        jupyter.prepare(other, self.python, self.tools, other_state, 8888)
        first = list((self.state / 'data/kernels').iterdir())[0].name
        second = list((other_state / 'data/kernels').iterdir())[0].name
        self.assertNotEqual(first, second)

    def test_missing_kernel_fails_without_installing_packages(self):
        with patch.object(jupyter.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, json.dumps({'prefix': '/project/.venv', 'kernel': False}), '')) as run:
            with self.assertRaisesRegex(ValueError, 'ipykernel missing'):
                jupyter.validate_kernel(self.python)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], str(self.python))

    def test_git_subdirectory_uses_this_checkout_root(self):
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        child = self.project / 'notebooks'
        child.mkdir()
        self.assertEqual(jupyter.project_root(child), self.project)

    def test_check_prepares_only_and_never_launches_server(self):
        args = ['jupyter_project', '--project', str(self.project), '--tools', str(self.tools),
                '--state-base', str(self.state), '--check']
        with patch.object(sys, 'argv', args), patch.object(jupyter, 'validate_kernel', return_value='/venv'), \
                patch.object(jupyter, 'project_root', return_value=self.project), \
                patch.object(jupyter.subprocess, 'Popen') as popen, \
                patch.object(jupyter.os, 'execve') as execute, contextlib.redirect_stdout(io.StringIO()):
            jupyter.main()
        popen.assert_not_called()
        execute.assert_not_called()

    def test_slow_detached_start_is_preserved_by_cleanup_status(self):
        args = ['jupyter_project', '--project', str(self.project), '--tools', str(self.tools),
                '--state-base', str(self.state)]
        with patch.object(jupyter, 'project_root', return_value=self.project), \
                patch.object(jupyter, 'validate_kernel', return_value='/venv'), \
                patch.object(jupyter, 'server_info', return_value=None), \
                patch.object(jupyter.time, 'sleep'), \
                patch.object(jupyter.subprocess, 'Popen') as popen, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            popen.return_value.pid = os.getpid()
            popen.return_value.poll.return_value = None
            with patch.object(sys, 'argv', [*args, '--detach']):
                jupyter.main()  # exhaust readiness wait without HTTP becoming ready
            output.seek(0)
            output.truncate()
            with patch.object(sys, 'argv', [*args, '--status']):
                jupyter.main()  # success prevents justfile from removing container
            status = json.loads(output.getvalue())
            self.assertEqual(status['state'], 'starting-or-unresponsive')
            self.assertEqual(status['pid'], os.getpid())
            self.assertNotIn('token', status)
            with patch.object(sys, 'argv', [*args, '--detach']):
                with self.assertRaisesRegex(ValueError, 'already running or starting'):
                    jupyter.main()
            self.assertEqual(popen.call_count, 1)

    def test_stale_process_marker_does_not_preserve_reused_pid(self):
        self.state.mkdir()
        marker = jupyter.process_identity(os.getpid())
        self.assertIsNotNone(marker)
        jupyter.write_json(self.state / 'process.json', marker)
        self.assertEqual(jupyter.pending_process(self.state), marker)
        marker['start'] = 'stale-start-time'
        jupyter.write_json(self.state / 'process.json', marker)
        self.assertIsNone(jupyter.pending_process(self.state))

    def test_reject_invalid_port(self):
        with patch.object(sys, 'argv', ['jupyter_project', '--port', '0']), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            jupyter.main()


if __name__ == '__main__':
    unittest.main()
