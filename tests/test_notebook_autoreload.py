"""Offline policy tests plus opt-in smoke of the built extension in real JupyterLab.

Build first with jupyter-builder, then set DEVENV_TEST_JUPYTER_TOOLS and
DEVENV_TEST_PLAYWRIGHT (absolute path to the installed Playwright Node package).
Only a temporary synthetic notebook/kernel is touched; no user server is used.
"""
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / 'jupyter/notebook-autoreload'


class NotebookAutoreloadTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node required for offline policy tests')
    def test_policy_and_fetch_races(self):
        tests = sorted(str(path) for path in (EXTENSION / 'test').glob('*.test.js'))
        result = subprocess.run(['node', '--test', *tests], cwd=EXTENSION,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pinned_prebuilt_extension_is_installed_in_image(self):
        package = json.loads((EXTENSION / 'package.json').read_text())
        lock = json.loads((EXTENSION / 'package-lock.json').read_text())
        self.assertEqual(package['dependencies']['@jupyterlab/notebook'], '4.6.6')
        self.assertEqual(lock['packages']['']['dependencies'], package['dependencies'])
        self.assertEqual(package['jupyterlab']['outputDir'], 'labextension')
        dockerfile = (ROOT / 'Dockerfile').read_text()
        self.assertIn('COPY jupyter/notebook-autoreload /tmp/notebook-autoreload/', dockerfile)
        self.assertIn('npm ci --ignore-scripts --no-audit --no-fund', dockerfile)
        self.assertIn('/opt/jupyter/.venv/bin/jupyter-builder build', dockerfile)
        self.assertIn('labextensions/@devenv/notebook-autoreload', dockerfile)


@unittest.skipUnless(os.environ.get('DEVENV_TEST_JUPYTER_TOOLS') and
                     os.environ.get('DEVENV_TEST_PLAYWRIGHT'),
                     'explicit Jupyter/Playwright environments required')
class NotebookAutoreloadBrowserTests(unittest.TestCase):
    def test_real_browser_external_edits_dirty_busy_and_fetch_race(self):
        spec = importlib.util.spec_from_file_location('autoreload_jupyter', ROOT / 'scripts/jupyter_project.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        tools = Path(os.environ['DEVENV_TEST_JUPYTER_TOOLS'])
        self.assertTrue((EXTENSION / 'labextension/package.json').is_file(), 'Build extension first')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'project'
            root.mkdir()
            state = Path(temporary) / 'state'
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', 0))
                port = listener.getsockname()[1]
            command, env = launcher.prepare(root, tools / 'bin/python', tools, state, port, ip='127.0.0.1')
            config_path = state / 'config/jupyter_server_config.json'
            config = json.loads(config_path.read_text())
            config['LabApp']['expose_app_in_browser'] = True  # test only
            config_path.write_text(json.dumps(config))
            token = config['IdentityProvider']['token']
            kernel = config['MappingKernelManager']['default_kernel_name']
            (root / 'test.ipynb').write_text(json.dumps({
                'nbformat': 4, 'nbformat_minor': 5,
                'metadata': {'kernelspec': {'name': kernel, 'display_name': 'Test', 'language': 'python'}},
                'cells': [{'id': 'test-cell', 'cell_type': 'code', 'metadata': {},
                           'source': 'initial source', 'outputs': [], 'execution_count': None}],
            }))
            shutil.copytree(EXTENSION / 'labextension',
                            state / 'data/labextensions/@devenv/notebook-autoreload')
            settings = state / 'settings/@jupyterlab/docmanager-extension/plugin.jupyterlab-settings'
            settings.parent.mkdir(parents=True, exist_ok=True)
            settings.write_text(json.dumps({'autosave': False}))
            formatter = state / 'settings/jupyterlab_code_formatter/settings.jupyterlab-settings'
            formatter.write_text(json.dumps({'formatOnSave': False}))
            opener = build_opener(ProxyHandler({}))
            url = f'http://127.0.0.1:{port}'
            with tempfile.TemporaryFile() as log:
                server = subprocess.Popen(command, env=env, cwd=root, stdout=log, stderr=log)
                try:
                    for _ in range(150):
                        self.assertIsNone(server.poll(), 'Synthetic Jupyter exited; log not printed (contains token)')
                        try:
                            request = Request(url + '/api/status', headers={'Authorization': 'token ' + token})
                            with opener.open(request, timeout=2):
                                break
                        except OSError:
                            time.sleep(0.2)
                    else:
                        self.fail('Synthetic Jupyter startup timeout')
                    try:
                        result = subprocess.run(['node', str(EXTENSION / 'test/browser.mjs')],
                                                env={**os.environ,
                                                     'AUTORELOAD_TEST_ROOT': str(root),
                                                     'AUTORELOAD_TEST_URL': url + '/lab?token=' + token},
                                                capture_output=True, text=True, timeout=100, check=False)
                    except subprocess.TimeoutExpired as error:
                        output = (error.stdout or b'') + (error.stderr or b'')
                        self.fail('Browser timeout: ' + output.decode(errors='replace').replace(token, '<redacted>'))
                    # Playwright errors can include the navigation URL: redact token.
                    output = (result.stdout + result.stderr).replace(token, '<redacted>')
                    self.assertEqual(result.returncode, 0, output)
                    print(result.stdout.strip())
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
