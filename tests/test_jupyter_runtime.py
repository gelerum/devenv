"""Opt-in local smoke test; creates only a temporary synthetic project/kernel.

DEVENV_TEST_JUPYTER_TOOLS=/tmp/tools-venv \
DEVENV_TEST_JUPYTER_KERNEL=/tmp/kernel-venv/bin/python \
/tmp/tools-venv/bin/python -m unittest discover -s tests -p test_jupyter_runtime.py
"""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('jupyter_project_runtime', ROOT / 'scripts/jupyter_project.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@unittest.skipUnless(os.environ.get('DEVENV_TEST_JUPYTER_TOOLS') and
                     os.environ.get('DEVENV_TEST_JUPYTER_KERNEL'), 'explicit Jupyter tool/kernel envs required')
class JupyterRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / 'synthetic-project'
        cls.root.mkdir()
        (cls.root / 'pyproject.toml').write_text('[tool.ruff]\nline-length = 90\n')
        cls.tools = Path(os.environ['DEVENV_TEST_JUPYTER_TOOLS'])
        cls.python = Path(os.environ['DEVENV_TEST_JUPYTER_KERNEL'])
        cls.state = Path(cls.temp.name) / 'state'
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            cls.port = listener.getsockname()[1]
        prefix = launcher.validate_kernel(cls.python)
        cmd, env = launcher.prepare(cls.root, cls.python, cls.tools, cls.state,
                                    cls.port, ip='127.0.0.1', prefix=prefix)
        config = json.loads(Path(cmd[-1]).read_text())
        cls.token = config['IdentityProvider']['token']
        cls.kernel_name = config['MappingKernelManager']['default_kernel_name']
        cls.opener = build_opener(ProxyHandler({}))
        cls.log = (cls.state / 'smoke.log').open('wb')
        cls.addClassCleanup(cls.log.close)
        cls.server = subprocess.Popen(cmd, cwd=cls.root, env=env,
                                      stdout=cls.log, stderr=subprocess.STDOUT)
        cls.addClassCleanup(cls.cleanup_server)
        for _ in range(150):
            if cls.server.poll() is not None:
                raise RuntimeError('Temporary Jupyter failed; inspect smoke.log locally (may contain token)')
            try:
                cls.api('/api/status')
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError('Temporary Jupyter did not become ready')

    @classmethod
    def api(cls, path, method='GET', body=None, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'token ' + cls.token
        request = Request(f'http://127.0.0.1:{cls.port}{path}', method=method, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        with cls.opener.open(request, timeout=20) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    @classmethod
    def cleanup_server(cls):
        if cls.server.poll() is None:
            try:
                cls.api('/api/shutdown', 'POST', {})
                cls.server.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                cls.server.terminate()
                cls.server.wait(timeout=10)

    def test_data_api_requires_token(self):
        with self.assertRaises(HTTPError) as error:
            self.api('/api/kernelspecs', authenticated=False)
        self.assertIn(error.exception.code, (401, 403))

    def test_news_and_update_endpoints_are_disabled(self):
        self.assertEqual(self.api('/lab/api/news'), {'news': []})
        self.assertEqual(self.api('/lab/api/update'), {'notification': None})

    def test_privacy_settings_match_installed_schema(self):
        import jsonschema
        plugin = '@jupyterlab/apputils-extension/notification'
        schema = json.loads((self.tools / 'share/jupyter/lab/schemas' / (plugin + '.json')).read_text())
        settings = json.loads((self.state / 'settings' / (plugin + '.jupyterlab-settings')).read_text())
        jsonschema.validate(settings, schema)
        self.assertEqual(settings, {'fetchNews': 'false', 'checkForUpdates': False})

    def test_only_project_kernel_is_exposed(self):
        result = self.api('/api/kernelspecs')
        self.assertEqual(list(result['kernelspecs']), [self.kernel_name])
        self.assertEqual(result['default'], self.kernel_name)

    def test_kernel_executes_selected_project_interpreter(self):
        from jupyter_client import BlockingKernelClient
        info = self.api('/api/kernels', 'POST', {'name': self.kernel_name})
        try:
            connection = self.state / 'runtime' / f'kernel-{info["id"]}.json'
            client = BlockingKernelClient(connection_file=str(connection))
            client.load_connection_file()
            client.start_channels()
            try:
                client.wait_for_ready(timeout=20)
                msg_id = client.execute('import sys; print(sys.executable)')
                output = ''
                for _ in range(30):
                    message = client.get_iopub_msg(timeout=10)
                    if message.get('parent_header', {}).get('msg_id') != msg_id:
                        continue
                    if message['header']['msg_type'] == 'stream':
                        output += message['content']['text']
                    if message['header']['msg_type'] == 'status' and message['content']['execution_state'] == 'idle':
                        break
                self.assertEqual(output.strip(), str(self.python))
            finally:
                client.stop_channels()
        finally:
            self.api('/api/kernels/' + info['id'], 'DELETE')

    def test_lsp_backend_registers_basedpyright(self):
        result = self.api('/lsp/status')
        self.assertEqual(list(result['specs']), ['basedpyright'])

    def test_basedpyright_completes_and_reports_type_error(self):
        import websocket
        connection = websocket.create_connection(
            f'ws://127.0.0.1:{self.port}/lsp/ws/basedpyright?token={self.token}',
            origin=f'http://127.0.0.1:{self.port}', timeout=30)
        settings = {'python': {'pythonPath': str(self.python)},
                    'basedpyright': {'analysis': {'typeCheckingMode': 'standard'}}}

        def send(message):
            connection.send(json.dumps({'jsonrpc': '2.0', **message}))

        def receive():
            message = json.loads(connection.recv())
            if message.get('method') == 'workspace/configuration':
                values = []
                for item in message['params']['items']:
                    value = settings
                    for key in item.get('section', '').split('.'):
                        value = value.get(key, {}) if key else value
                    values.append(value)
                send({'id': message['id'], 'result': values})
            return message

        try:
            send({'id': 1, 'method': 'initialize', 'params': {
                'processId': None, 'rootUri': self.root.as_uri(),
                'workspaceFolders': [{'uri': self.root.as_uri(), 'name': 'test'}],
                'capabilities': {'workspace': {'configuration': True}},
            }})
            for _ in range(100):
                if receive().get('id') == 1:
                    break
            else:
                self.fail('LSP did not initialize')
            send({'method': 'initialized', 'params': {}})
            send({'method': 'workspace/didChangeConfiguration', 'params': {'settings': settings}})
            uri = (self.root / 'test.py').as_uri()
            send({'method': 'textDocument/didOpen', 'params': {'textDocument': {
                'uri': uri, 'languageId': 'python', 'version': 1,
                'text': 'import sys\nvalue: int = "wrong"\nsys.ver\n',
            }}})
            # Wait for initial analysis before requesting completions; a freshly
            # started language server may otherwise return an empty first list.
            diagnosed = False
            for _ in range(100):
                message = receive()
                if message.get('method') == 'textDocument/publishDiagnostics':
                    diagnostics = message['params'].get('diagnostics', [])
                    if any(d.get('code') == 'reportAssignmentType' for d in diagnostics):
                        diagnosed = True
                        break
            self.assertTrue(diagnosed, 'Initial type analysis did not finish')
            send({'id': 2, 'method': 'textDocument/completion', 'params': {
                'textDocument': {'uri': uri}, 'position': {'line': 2, 'character': 7},
                'context': {'triggerKind': 1},
            }})
            completed = False
            for _ in range(100):
                message = receive()
                if message.get('id') == 2:
                    self.assertNotIn('error', message)
                    result = message.get('result') or []
                    items = result.get('items', []) if isinstance(result, dict) else result
                    self.assertTrue(any(item['label'] == 'version' for item in items),
                                    [item['label'] for item in items[:12]])
                    completed = True
                if message.get('method') == 'textDocument/publishDiagnostics':
                    diagnostics = message['params'].get('diagnostics', [])
                    diagnosed |= any(d.get('code') == 'reportAssignmentType' for d in diagnostics)
                if completed and diagnosed:
                    break
            self.assertTrue(completed and diagnosed, 'Expected stdlib completion and assignment type diagnostic')
        finally:
            connection.close()

    def test_ruff_backends_are_available_and_format(self):
        formatters = self.api('/jupyterlab_code_formatter/formatters')['formatters']
        self.assertTrue(formatters['ruff']['enabled'])
        self.assertTrue(formatters['ruffformat']['enabled'])
        result = self.api('/jupyterlab_code_formatter/format', 'POST', {
            'formatter': 'ruffformat', 'code': ['x=1+2'], 'notebook': True, 'options': {},
        })
        self.assertEqual(result['code'][0]['code'].strip(), 'x = 1 + 2')
        settings = json.loads((self.state / 'settings/jupyterlab_code_formatter/settings.jupyterlab-settings').read_text())
        result = self.api('/jupyterlab_code_formatter/format', 'POST', {
            'formatter': 'ruff', 'code': ['import sys\nimport os\nx=1'],
            'notebook': True, 'options': settings['ruff'],
        })
        self.assertNotIn('error', result['code'][0])
        self.assertTrue(result['code'][0]['code'].startswith('import os\nimport sys\n'))

    def test_detached_launcher_status_url_stop(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        command = [sys.executable, str(ROOT / 'scripts/jupyter_project.py'),
                   '--project', str(self.root), '--python', str(self.python),
                   '--tools', str(self.tools), '--state-base', str(self.state / 'detached'),
                   '--port', str(port), '--ip', '127.0.0.1']

        def run(mode):
            return subprocess.run([*command, mode], capture_output=True, text=True, timeout=30)

        # Never include captured output in assertions: URL/logs may contain tokens.
        try:
            self.assertEqual(run('--detach').returncode, 0, 'Detached start failed')
            status = run('--status')
            self.assertEqual(status.returncode, 0, 'Detached status failed')
            self.assertEqual(json.loads(status.stdout)['port'], port)
            self.assertNotIn('token', status.stdout)
            self.assertNotEqual(run('--detach').returncode, 0, 'Duplicate start must fail')
            with patch.dict(os.environ, {'DEVENV_JUPYTER_HOST_PORT': '19200'}):
                url = run('--url')
            self.assertEqual(url.returncode, 0, 'URL retrieval failed')
            self.assertTrue(url.stdout.startswith('http://127.0.0.1:19200/lab?token='))
        finally:
            stopped = run('--stop')
            self.assertEqual(stopped.returncode, 0, 'Detached shutdown failed')
        for _ in range(100):
            if run('--status').returncode != 0:
                break
            time.sleep(0.1)
        else:
            self.fail('Detached server did not stop')

    def test_frontend_settings_match_installed_schemas(self):
        import jsonschema
        for schema_path, settings_path in (
            ('@jupyter-lsp/jupyterlab-lsp/schemas/@jupyter-lsp/jupyterlab-lsp/plugin.json',
             '@jupyter-lsp/jupyterlab-lsp/plugin.jupyterlab-settings'),
            ('jupyterlab_code_formatter/schemas/jupyterlab_code_formatter/settings.json',
             'jupyterlab_code_formatter/settings.jupyterlab-settings'),
        ):
            schema = json.loads((self.tools / 'share/jupyter/labextensions' / schema_path).read_text())
            settings = json.loads((self.state / 'settings' / settings_path).read_text())
            jsonschema.validate(settings, schema)


if __name__ == '__main__':
    unittest.main()
