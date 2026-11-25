"""Offline integration tests for /account, using Pi's real registry and request code."""
import base64
import json
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import tempfile
from threading import Thread
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / 'pi-tools/openai-accounts.ts'
PI_BINARY = os.environ.get('DEVENV_TEST_PI_BINARY')

# The only transport in this test: never contact an OAuth or inference endpoint.
MOCK_TRANSPORT = r'''
import { appendFileSync } from "node:fs";
import { zstdDecompressSync } from "node:zlib";
export default function () {
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init);
    const body = request.headers.get("content-encoding") === "zstd"
      ? JSON.parse(zstdDecompressSync(Buffer.from(await request.arrayBuffer())).toString("utf8"))
      : await request.json();
    appendFileSync(process.env.MOCK_REQUESTS, JSON.stringify({
      url: request.url, authorization: request.headers.get("authorization"),
      account: request.headers.get("chatgpt-account-id"), body,
    }) + "\n");
    const item = { type: "message", role: "assistant", id: "msg_test", content: [], status: "in_progress" };
    const part = { type: "output_text", text: "", annotations: [] };
    const events = [
      { type: "response.output_item.added", item },
      { type: "response.content_part.added", part },
      { type: "response.output_text.delta", delta: "test response" },
      { type: "response.output_item.done", item: { ...item, content: [{ ...part, text: "test response" }] } },
      { type: "response.completed", response: { id: "resp_test", status: "completed" } },
    ];
    return new Response(events.map(e => `data: ${JSON.stringify(e)}\n\n`).join(""), {
      status: 200, headers: { "Content-Type": "text/event-stream" },
    });
  };
}
'''


@unittest.skipUnless(PI_BINARY, 'set DEVENV_TEST_PI_BINARY for real Pi account integration')
class OpenAIAccountsTests(unittest.TestCase):
    def test_account_switch_routes_next_request_without_mutating_auth_or_defaults(self):
        self.check_switch('openai', 'gpt-5', 'OpenAI — аккаунт 4', 'openai-account-4', [
            ('OpenAI — аккаунт 2', 'openai-account-2', 'two'),
            ('OpenAI — аккаунт 3', 'openai-account-3', 'three'),
            ('OpenAI — аккаунт 1', 'openai-account-1', 'one'),
        ])

    def test_codex_uses_original_login_and_separate_slot_in_same_session(self):
        self.check_switch('openai-codex', 'gpt-6.2-sol', 'Codex — аккаунт 3', 'openai-codex-account-3', [
            ('Codex — аккаунт 2', 'openai-codex-account-2', 'second'),
            ('Codex — основной вход', 'openai-codex', 'primary'),
            ('Codex — аккаунт 2', 'openai-codex-account-2', 'second'),
        ])

    def check_switch(self, default, model, empty_label, empty_id, selections):
        codex = default == 'openai-codex'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = root / 'auth.json'
            def token(name):
                if not codex:
                    return f'fake-access-{name}'
                claim = {'https://api.openai.com/auth': {'chatgpt_account_id': name}}
                payload = base64.b64encode(json.dumps(claim).encode()).decode()
                return f'fake.{payload}.signature'

            def oauth(name):
                return {'type': 'oauth', 'access': token(name),
                        'refresh': f'fake-refresh-{name}', 'expires': 9999999999999}

            initial_auth = {provider: oauth(name) for _, provider, name in selections}
            initial_auth['openai'] = {'type': 'api_key', 'key': 'sk-fake-original'}
            auth.write_text(json.dumps(initial_auth))
            auth.chmod(0o600)
            original_auth = auth.read_bytes()
            # Ordinary config with JSONC syntax is compatible with the slots.
            (root / 'models.json').write_text('{\n// no overrides\n"providers": {},\n}')
            (root / 'settings.json').write_text(json.dumps({
                'defaultProvider': default, 'defaultModel': model, 'transport': 'sse',
            }))
            mock = root / 'mock.ts'
            mock.write_text(MOCK_TRANSPORT)
            wire = root / 'wire.jsonl'
            env = {'PATH': os.environ['PATH'], 'HOME': directory, 'PI_CODING_AGENT_DIR': directory,
                   'PI_OFFLINE': '1', 'PI_TELEMETRY': '0', 'MOCK_REQUESTS': str(wire),
                   'OPENAI_API_KEY': 'sk-fake-env'}
            with (root / 'stderr').open('w+') as stderr, subprocess.Popen(
                [PI_BINARY, '--mode', 'rpc', '--no-session', '-ne', '-e', str(mock), '-e', str(EXTENSION)],
                cwd=root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True,
            ) as pi:
                output = Queue()
                lines = []

                def read_lines():
                    for line in pi.stdout:
                        lines.append(line)
                        output.put(line)
                    output.put(None)

                reader = Thread(target=read_lines, daemon=True)
                reader.start()

                def send(kind, **fields):
                    pi.stdin.write(json.dumps({'type': kind, **fields}) + '\n')
                    pi.stdin.flush()

                def receive(**fields):
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        try:
                            line = output.get(timeout=max(0, deadline - time.monotonic()))
                        except Empty:
                            break
                        if line is None:
                            break
                        event = json.loads(line)
                        if all(event.get(key) == value for key, value in fields.items()):
                            return event
                        if event.get('type') == 'response':
                            self.assertTrue(event.get('success'), event)
                    stderr.seek(0)
                    self.fail(f'No {fields!r}: {lines[-5:]!r}\n{stderr.read()}')

                def switch(label, active=None, method='notify'):
                    send('prompt', id='switch', message='/account')
                    menu = receive(type='extension_ui_request', method='select')
                    if active:
                        self.assertIn(f'{active} ●', menu['options'])
                    choice = next(option for option in menu['options'] if option.startswith(label))
                    self.assertEqual('добавить вход' in choice, label == empty_label)
                    send('extension_ui_response', id=menu['id'], value=choice)
                    event = receive(type='extension_ui_request', method=method)
                    receive(type='response', id='switch')
                    return event

                try:
                    send('get_state', id='initial')
                    initial = receive(type='response', id='initial')['data']
                    self.assertEqual(initial['model']['provider'], default)
                    empty = switch(empty_label, active='Codex — основной вход' if codex else None,
                                   method='set_editor_text')
                    self.assertEqual(empty['text'], f'/login {empty_id}')
                    for index, (label, provider, _) in enumerate(selections):
                        notification = switch(label)
                        self.assertIn('Активен', notification['message'])
                        send('get_state', id=provider)
                        state = receive(type='response', id=provider)['data']
                        self.assertEqual(state['sessionId'], initial['sessionId'])
                        self.assertEqual(state['model']['provider'], provider)
                        self.assertEqual(state['model']['id'], model)
                        send('prompt', message=f'test prompt {index}')
                        end = receive(type='agent_end')
                        message = end['messages'][-1]
                        self.assertEqual(message['provider'], provider)
                        self.assertEqual(message['stopReason'], 'stop', message)
                    self.assertEqual(auth.read_bytes(), original_auth)
                    # Simulate a logout from another Pi while using the slot.
                    remaining = json.loads(original_auth)
                    del remaining[selections[-1][1]]
                    auth.write_text(json.dumps(remaining))
                    send('prompt', id='signed-out', message='must not fall back to OPENAI_API_KEY')
                    reply = receive(type='response', id='signed-out')
                    if reply['success']:
                        end = receive(type='agent_end')
                        self.assertEqual(end['messages'][-1]['stopReason'], 'error')
                finally:
                    pi.terminate()
                    pi.wait(timeout=10)
                    reader.join(timeout=5)

            requests = [json.loads(line) for line in wire.read_text().splitlines()]
            url = 'https://chatgpt.com/backend-api/codex/responses' if codex else 'https://api.openai.com/v1/responses'
            names = [name for _, _, name in selections]
            self.assertEqual([r['url'] for r in requests], [url] * len(names))
            self.assertEqual([r['authorization'] for r in requests], [f'Bearer {token(name)}' for name in names])
            self.assertEqual([r['account'] for r in requests], names if codex else [None] * len(names))
            self.assertIn('test prompt 0', json.dumps(requests[-1]['body']['input']))
            if not codex:
                for request in requests:
                    self.assertNotIn('max_output_tokens', request['body'])
            for name in names:
                self.assertNotIn(token(name), ''.join(lines))
            self.assertNotIn('fake-refresh-', ''.join(lines))
            self.assertEqual(json.loads(auth.read_text()), remaining)
            self.assertEqual(json.loads((root / 'settings.json').read_text())['defaultProvider'], default)

    def test_models_json_cannot_route_slot_token_through_alternate_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = root / 'auth.json'
            auth.write_text(json.dumps({'openai-account-1': {'type': 'oauth', 'access': 'fake-access-one',
                                                            'refresh': 'fake-refresh-one', 'expires': 9999999999999}}))
            auth.chmod(0o600)
            (root / 'models.json').write_text(json.dumps({'providers': {'openai-account-1': {
                'models': [{'id': 'custom-azure', 'api': 'azure-openai-responses',
                            'baseUrl': 'https://wrong.invalid/v1'}],
            }}}))
            mock = root / 'mock.ts'
            mock.write_text(MOCK_TRANSPORT)
            wire = root / 'wire.jsonl'
            result = subprocess.run(
                [PI_BINARY, '-ne', '-e', str(mock), '-e', str(EXTENSION), '--no-session',
                 '--model', 'openai-account-1/custom-azure', '-p', 'test prompt'],
                cwd=root, capture_output=True, text=True, timeout=20,
                env={'PATH': os.environ['PATH'], 'HOME': directory, 'PI_CODING_AGENT_DIR': directory,
                     'PI_OFFLINE': '1', 'PI_TELEMETRY': '0', 'MOCK_REQUESTS': str(wire),
                     'AZURE_OPENAI_BASE_URL': 'https://wrong.invalid/openai/v1'},
            )
            output = result.stderr + result.stdout
            self.assertNotIn('fake-access-one', output)
            self.assertFalse(wire.exists(), 'alternate adapter got as far as an HTTP request')
            self.assertNotEqual(result.returncode, 0, output)
            self.assertIn('Remove the openai-account-1 entry from models.json', output)
