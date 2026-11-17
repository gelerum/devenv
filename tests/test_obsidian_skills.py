"""Exercise the real Dockerfile RUN block against a local upstream-layout fixture."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ('obsidian-markdown', 'json-canvas', 'obsidian-bases')
UPSTREAM = 'https://github.com/kepano/obsidian-skills'


def install_command():
    lines = (ROOT / 'Dockerfile').read_text().splitlines()
    start = lines.index('RUN git init -q /tmp/obsidian-skills \\')
    parts = []
    for line in lines[start:]:
        continued = line.endswith('\\')
        parts.append(line[:-1] if continued else line)
        if not continued:
            break
    return ' '.join(parts).removeprefix('RUN ')


class ObsidianSkillsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='obsidian-skills-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.upstream = self.root / 'upstream'
        self.upstream.mkdir()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.git('init', '-q')
        for skill in (*SKILLS, 'defuddle'):
            folder = self.upstream / 'plugins/obsidian/skills' / skill
            (folder / 'references').mkdir(parents=True)
            (folder / 'SKILL.md').write_text(f'---\nname: {skill}\n---\nSkill body\n')
            (folder / 'references/DETAILS.md').write_text('Bundled reference\n')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.upstream), *args], check=True,
                              text=True, capture_output=True)

    def install(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 'commit', '-qm', 'Upstream layout fixture')
        ref = self.git('rev-parse', 'HEAD').stdout.strip()
        staging = self.root / 'checkout'
        command = install_command().replace('/tmp/obsidian-skills', str(staging))
        env = {**os.environ, 'HOME': str(self.home), 'OBSIDIAN_SKILLS_REF': ref,
               'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
               'GIT_CONFIG_COUNT': '1',
               'GIT_CONFIG_KEY_0': f'url.{self.upstream.as_uri()}.insteadOf',
               'GIT_CONFIG_VALUE_0': UPSTREAM,
               'GIT_TERMINAL_PROMPT': '0'}
        # Only the transport is redirected to a local file:// repository. Sparse
        # checkout, validation, copying and cleanup are the Dockerfile commands.
        return subprocess.run(['/bin/sh', '-c', command], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=20), staging

    def test_installs_only_selected_skills_and_keeps_bundled_references(self):
        result, staging = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.home / '.claude/skills'
        self.assertEqual(set(p.name for p in installed.iterdir()), set(SKILLS))
        for skill in SKILLS:
            self.assertTrue((installed / skill / 'SKILL.md').is_file())
            self.assertEqual((installed / skill / 'references/DETAILS.md').read_text(),
                             'Bundled reference\n')
        self.assertFalse(staging.exists())

    def test_missing_skill_entry_point_fails_before_installing(self):
        (self.upstream / 'plugins/obsidian/skills/obsidian-markdown/SKILL.md').unlink()
        result, _ = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing Obsidian skill: obsidian-markdown', result.stderr)
        self.assertFalse((self.home / '.claude/skills').exists())

    def test_empty_skill_entry_point_fails_before_installing(self):
        (self.upstream / 'plugins/obsidian/skills/json-canvas/SKILL.md').write_text('')
        result, _ = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing Obsidian skill: json-canvas', result.stderr)
        self.assertFalse((self.home / '.claude/skills').exists())

    def test_upstream_revision_remains_pinned(self):
        dockerfile = (ROOT / 'Dockerfile').read_text()
        self.assertIsNotNone(re.search(r'^ARG OBSIDIAN_SKILLS_REF=[0-9a-f]{40}$', dockerfile, re.MULTILINE))
