"""Offline wiring tests for the exact Dockerfile Nix-linter build command.

The standalone-rustup self-update failure is modelled by a stub; toolchain and
crate downloads are not needed for this regression test. A separate real build
check is required when changing versions or compilation options.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def build_command():
    lines = (ROOT / 'Dockerfile').read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('RUN export RUSTUP_HOME=/tmp/nix-lint-rustup'))
    parts = []
    for line in lines[start:]:
        continued = line.endswith('\\')
        parts.append(line[:-1] if continued else line)
        if not continued:
            break
    return ' '.join(parts).removeprefix('RUN ')


STUB = '''
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['NIX_BUILD_TEST_LOG'], 'a') as log:
    log.write(json.dumps({'name': name, 'args': args}) + '\\n')
if name == 'rustup':
    if '--no-self-update' not in args:
        print('error: rustup is not installed at ' + os.environ['CARGO_HOME'], file=sys.stderr)
        sys.exit(1)
    pathlib.Path(os.environ['RUSTUP_HOME']).mkdir(parents=True)
    pathlib.Path(os.environ['CARGO_HOME']).mkdir(parents=True)
elif name == 'cargo':
    assert os.environ['RUSTUP_TOOLCHAIN'] == os.environ['NIX_LINT_RUST_VERSION']
    assert '--locked' in args
    assert pathlib.Path(os.environ['RUSTUP_HOME']).is_dir()
    target = pathlib.Path(args[args.index('--root') + 1]) / 'bin' / args[-1]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('#!/bin/sh\\necho ' + args[-1] + '-fixture\\n')
    target.chmod(0o755)
'''


class NixLintBuildTests(unittest.TestCase):
    def run_build(self, remove_self_update_guard=False):
        temp = tempfile.TemporaryDirectory(prefix='nix-build-test-')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        tools = root / 'tools'
        tools.mkdir()
        for name in ('rustup', 'cargo'):
            binary = tools / name
            binary.write_text(f'#!{sys.executable}\n' + STUB)
            binary.chmod(0o755)
        home = root / 'home'
        home.mkdir()
        installed = root / 'installed'
        installed.mkdir()
        command = build_command()
        for name in ('rustup', 'cargo', 'bin'):
            command = command.replace('/tmp/nix-lint-' + name, str(root / ('build-' + name)))
        command = command.replace('/usr/local/bin/', str(installed) + '/')
        if remove_self_update_guard:
            command = command.replace(' --no-self-update', '')
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('CARGO_', 'RUSTUP_'))}
        env.update(HOME=str(home), PATH=str(tools) + ':' + env['PATH'],
                   NIX_BUILD_TEST_LOG=str(root / 'commands.jsonl'))
        for name in ('STATIX_REF', 'DEADNIX_VERSION', 'NIX_LINT_RUST_VERSION'):
            env[name] = re.search(rf'^ARG {name}=(\S+)$', (ROOT / 'Dockerfile').read_text(), re.MULTILINE).group(1)
        result = subprocess.run(['/bin/sh', '-c', command], cwd=root, env=env,
                                capture_output=True, text=True, timeout=20)
        calls = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()]
        return root, result, calls

    def test_standalone_rustup_skips_self_update_and_both_locked_builds_are_installed(self):
        root, result, calls = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call['name'] for call in calls], ['rustup', 'cargo', 'cargo'])
        self.assertIn('--no-self-update', calls[0]['args'])
        self.assertEqual(calls[1]['args'][-1], 'statix')
        self.assertIn('--git', calls[1]['args'])
        self.assertIn('--rev', calls[1]['args'])
        self.assertEqual(calls[2]['args'][-1], 'deadnix')
        self.assertIn('--version', calls[2]['args'])
        for name in ('statix', 'deadnix'):
            self.assertTrue(os.access(root / 'installed' / name, os.X_OK))
        for name in ('rustup', 'cargo', 'bin'):
            self.assertFalse((root / ('build-' + name)).exists())
        self.assertFalse((root / 'home/.cargo').exists())

    def test_without_self_update_guard_the_build_stops_before_cargo(self):
        _, result, calls = self.run_build(remove_self_update_guard=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('rustup is not installed at', result.stderr)
        self.assertEqual([call['name'] for call in calls], ['rustup'])
