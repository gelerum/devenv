"""Offline packaging regressions; optional real CLI checks after image rebuild."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PiToolsPackagingTests(unittest.TestCase):
    def test_npm_dependencies_are_exact_and_lock_matches(self):
        package = json.loads((ROOT / 'pi-tools/package.json').read_text())
        lock = json.loads((ROOT / 'pi-tools/package-lock.json').read_text())
        self.assertEqual(package['dependencies'], lock['packages']['']['dependencies'])
        for version in package['dependencies'].values():
            self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        for key, value in lock['packages'].items():
            if key:
                self.assertTrue(value.get('integrity'), key)

    def test_serena_allows_code_tools_only(self):
        # This intentionally checks our small allowlist, not upstream defaults.
        context = (ROOT / 'pi-tools/serena-context.yml').read_text()
        fixed = context.split('fixed_tools:\n', 1)[1].split('excluded_apis:', 1)[0]
        names = re.findall(r'^  - (\w+)$', fixed, re.MULTILINE)
        self.assertEqual(len(names), 13)
        self.assertIn('find_symbol', names)
        self.assertIn('rename_symbol', names)
        self.assertIn('safe_delete_symbol', names)
        self.assertFalse(any(re.search(r'memory|memories|onboard|^serena_repl$|shell', n) for n in names))
        self.assertIn('excluded_apis:\n  - mem', context)
        self.assertIn('single_project: true', context)

    def test_image_pins_sources_and_prebuilds_runtime(self):
        docker = (ROOT / 'Dockerfile').read_text()
        for name in ('STATIX_REF', 'SERENA_REF', 'UNDERSTAND_ANYTHING_REF'):
            self.assertRegex(docker, rf'ARG {name}=[0-9a-f]{{40}}\n')
        self.assertIn('npm ci --ignore-scripts', docker)
        self.assertIn('pnpm install --frozen-lockfile', docker)
        self.assertIn('uv sync --project /opt/serena --frozen', docker)
        self.assertIn('--git https://github.com/oppiliappan/statix --rev "$STATIX_REF"', docker)
        self.assertIn('skills/*', docker)
        self.assertIn('agents/*.md', docker)
        self.assertIn('UNDERSTAND_NO_WORKTREE_REDIRECT=1', docker)


@unittest.skipUnless(os.environ.get('DEVENV_TEST_PI_TOOLS') == '1',
                     'set DEVENV_TEST_PI_TOOLS=1 inside the rebuilt image')
class InstalledPiToolsTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run(args, text=True, capture_output=True, timeout=30, check=True)

    def test_versions(self):
        for binary in ('statix', 'deadnix', 'node', 'pnpm'):
            self.assertIsNotNone(shutil.which(binary), binary)
            self.command(binary, '--version')
        self.command('/opt/serena/.venv/bin/serena', '--help')
        self.command('/opt/pi-tools/node_modules/.bin/playwright-mcp', '--help')

    def test_upstream_skills_and_agents_are_installed(self):
        home = Path.home() / '.pi/agent'
        self.assertTrue((home / 'skills/understand/SKILL.md').is_file())
        self.assertTrue((home / 'agents/project-scanner.md').is_file())
        self.command('node', '--input-type=module', '-e',
                     "import('/opt/understand-anything/understand-anything-plugin/packages/core/dist/index.js')")

    def test_mcp_config_uses_installed_runtimes_and_tools_interface(self):
        config = json.loads((Path.home() / '.pi/agent/mcp.json').read_text())['mcpServers']
        self.assertEqual(set(config), {'context7', 'serena', 'playwright'})
        for name in ('serena', 'playwright'):
            self.assertTrue(os.access(config[name]['command'], os.X_OK))
            self.assertEqual(config[name]['exposure'], 'deferred')
        args = config['serena']['args']
        self.assertEqual(args[args.index('--agent-interface') + 1], 'tools')
        self.assertIn('no-memories', args)
        self.assertIn('--project-from-cwd', args)
        self.assertIn('--isolated', config['playwright']['args'])
        self.assertNotIn('headers', config['context7'])  # no embedded credentials
