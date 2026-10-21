"""No real credentials or host configuration are touched by these tests."""
import fcntl
from pathlib import Path
import sqlite3
import shutil
import tempfile
import unittest

from test_pi_config import storage


class AgentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.home.mkdir()
        self.root = storage.host_root(self.home)
        self.put('.config/devenv/pi/settings.json', '{"model":"old"}')
        self.put('.config/devenv/pi/models.json', '{}')

    def put(self, relative, text):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_copies_old_layout_and_keeps_originals(self):
        old_auth = self.put('.pi/agent/auth.json', '{"fake-token":"test-only"}')
        old_session = self.put('.pi/agent/sessions/project/session.jsonl', 'history')
        self.put('.pi/agent/memory/project/MEMORY.md', 'memory')
        self.put('.pi/agent/subagents/run/result.jsonl', 'subagent-history')
        self.put('.claude/projects/project/memory/MEMORY.md', 'claude-memory')
        self.put('.claude/.credentials.json', '{"fake-token":"claude"}')
        self.put('.claude/settings.json', '{"theme":"auto"}')
        self.put('.config/devenv/claude.env', 'TEST_ONLY=1\n')
        self.put('.local/share/devenv/codex/auth.json', '{"fake-token":"codex"}')
        self.put('.local/share/devenv/codex/memories/MEMORY.md', 'codex-memory')
        self.put('.local/share/devenv/codex/sessions/session.jsonl', 'codex-history')
        storage.migrate(self.home)
        self.assertTrue(old_auth.exists())
        self.assertTrue(old_session.exists())
        self.assertEqual((self.root / 'pi/data/subagents/run/result.jsonl').read_text(),
                         'subagent-history')
        self.assertEqual((self.root / 'pi/data/sessions/project/session.jsonl').read_text(), 'history')
        self.assertEqual((self.root / 'pi/auth/auth.json').read_text(), old_auth.read_text())
        self.assertEqual((self.root / 'claude/config/settings.json').read_text(), '{"theme":"auto"}')
        self.assertEqual((self.root / 'codex/data/memories/MEMORY.md').read_text(), 'codex-memory')
        self.assertFalse((self.root / 'codex/data/auth.json').exists())
        self.assertEqual((self.root / 'codex/auth/auth.json').stat().st_mode & 0o777, 0o600)
        storage.migrate(self.home)  # Idempotent before clients change the destination.
        storage.initialize(self.home)

    def test_conflict_detected_before_any_copy(self):
        original = self.put('.config/devenv/agents/pi/config/settings.json', 'new')
        with self.assertRaises(ValueError):
            storage.migrate(self.home)
        self.assertEqual(original.read_text(), 'new')
        self.assertFalse((self.root / 'pi/config/models.json').exists())

    def test_codex_legacy_sources_do_not_silently_override_each_other(self):
        self.put('.config/devenv/codex/config.toml', 'model = "one"')
        self.put('.codex/config.toml', 'model = "two"')
        with self.assertRaises(ValueError):
            storage.migrate(self.home)
        self.assertFalse((self.root / 'pi/config/settings.json').exists())

    def test_local_runtime_stays_outside_sync_tree(self):
        storage.migrate(self.home)
        runtime = storage.runtime_root(self.home)
        self.assertFalse(runtime.is_relative_to(self.root))
        self.assertTrue(runtime.is_dir())
        self.assertIn('[analytics]\nenabled = false', (self.root / 'codex/config/config.toml').read_text())

    def test_rejects_config_that_bypasses_local_sqlite_or_file_auth(self):
        storage.migrate(self.home)
        config = self.root / 'codex/config/config.toml'
        for text in ('sqlite_home = "/elsewhere"',
                     'cli_auth_credentials_store = "keyring"',
                     'cli_auth_credentials_store = "auto"'):
            config.write_text(text)
            with self.assertRaises(ValueError):
                storage.initialize(self.home)
            with self.assertRaises(ValueError):
                storage.snapshot(self.home)

    def test_snapshot_and_restore_refuse_active_codex(self):
        storage.migrate(self.home)
        lock = storage.runtime_root(self.home) / '.devenv-active.lock'
        with lock.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_SH)
            for restore in (False, True):
                with self.assertRaisesRegex(ValueError, 'завершите все клиенты Codex'):
                    storage.snapshot(self.home, restore=restore)

    def test_restore_requires_synced_snapshot(self):
        storage.migrate(self.home)
        with self.assertRaisesRegex(ValueError, 'Нет снимков SQLite'):
            storage.snapshot(self.home, restore=True)

    def test_two_device_handoff_shares_memory_but_not_logins(self):
        self.put('.pi/agent/auth.json', '{"fake-token":"device-one"}')
        self.put('.pi/agent/memory/project/MEMORY.md', 'shared-memory')
        storage.migrate(self.home)
        with sqlite3.connect(storage.runtime_root(self.home) / 'memories_1.sqlite') as conn:
            conn.execute('CREATE TABLE memory (note TEXT)')
            conn.execute('INSERT INTO memory VALUES (?)', ('sqlite-memory',))
        storage.snapshot(self.home)
        other = self.home.parent / 'second-device'
        other.mkdir()
        other_root = storage.host_root(other)
        for agent in storage.AGENTS:
            for kind in ('config', 'data'):
                shutil.copytree(self.root / agent / kind, other_root / agent / kind)
        storage.initialize(other)
        self.assertEqual((other_root / 'pi/auth/auth.json').read_text(), '{}\n')
        self.assertEqual((other_root / 'pi/data/memory/project/MEMORY.md').read_text(), 'shared-memory')
        self.assertFalse((other_root / 'codex/auth/auth.json').exists())
        storage.snapshot(other, restore=True)
        with sqlite3.connect(storage.runtime_root(other) / 'memories_1.sqlite') as conn:
            self.assertEqual(conn.execute('SELECT note FROM memory').fetchone()[0], 'sqlite-memory')

    def test_restore_checks_entire_snapshot_before_touching_local_state(self):
        storage.migrate(self.home)
        runtime = storage.runtime_root(self.home)
        db = runtime / 'state_5.sqlite'
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE state (note TEXT)')
            conn.execute('INSERT INTO state VALUES (?)', ('original',))
        storage.snapshot(self.home)
        snapshot = self.root / 'codex/data/sqlite-snapshot/state_5.sqlite'
        snapshot.write_bytes(b'partial sync')
        with self.assertRaisesRegex(ValueError, 'не синхронизирован или повреждён'):
            storage.snapshot(self.home, restore=True)
        with sqlite3.connect(db) as conn:
            self.assertEqual(conn.execute('SELECT note FROM state').fetchone()[0], 'original')
        self.assertFalse(list(runtime.glob('before-restore-*')))

    def test_restore_does_not_mix_stale_runtime_databases(self):
        storage.migrate(self.home)
        runtime = storage.runtime_root(self.home)
        with sqlite3.connect(runtime / 'state_5.sqlite') as conn:
            conn.execute('CREATE TABLE state (note TEXT)')
        storage.snapshot(self.home)
        stale = runtime / 'memories_1.sqlite'
        with sqlite3.connect(stale) as conn:
            conn.execute('CREATE TABLE stale (note TEXT)')
        storage.snapshot(self.home, restore=True)
        self.assertFalse(stale.exists())
        self.assertEqual(len(list(runtime.glob('before-restore-*/memories_1.sqlite'))), 1)

    def test_snapshot_restore_keeps_prior_local_database(self):
        storage.migrate(self.home)
        runtime = storage.runtime_root(self.home)
        db = runtime / 'memories_1.sqlite'
        with sqlite3.connect(db) as conn:
            conn.execute('CREATE TABLE memory (note TEXT)')
            conn.execute('INSERT INTO memory VALUES (?)', ('from-device-one',))
        with sqlite3.connect(runtime / 'logs_2.sqlite') as conn:
            conn.execute('CREATE TABLE logs (text TEXT)')
        storage.snapshot(self.home)
        snapshots = self.root / 'codex/data/sqlite-snapshot'
        self.assertTrue((snapshots / db.name).exists())
        self.assertFalse((snapshots / 'logs_2.sqlite').exists())
        with sqlite3.connect(db) as conn:
            conn.execute('UPDATE memory SET note = ?', ('local-before-restore',))
        storage.snapshot(self.home, restore=True)
        with sqlite3.connect(db) as conn:
            self.assertEqual(conn.execute('SELECT note FROM memory').fetchone()[0], 'from-device-one')
        backups = list(runtime.glob('before-restore-*/*.sqlite'))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as conn:
            self.assertEqual(conn.execute('SELECT note FROM memory').fetchone()[0], 'local-before-restore')
