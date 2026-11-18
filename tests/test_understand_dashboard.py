"""Offline launcher checks; no agent, package manager or container required."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/understand-dashboard.sh"


class UnderstandDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project with spaces"
        self.project.mkdir()
        self.plugin = self.root / "plugin with spaces"
        self.dashboard = self.plugin / "packages/dashboard"
        vite = self.dashboard / "node_modules/.bin/vite"
        vite.parent.mkdir(parents=True)
        vite.write_text('#!/bin/sh\nprintf "%s\\n" "$GRAPH_DIR" "$PWD" "$__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS" "$@"\n')
        vite.chmod(0o755)

    def graph(self, directory=".ua"):
        data = self.project / directory
        data.mkdir(exist_ok=True)
        (data / "knowledge-graph.json").write_text('{"nodes": [], "edges": []}')

    def run_launcher(self, *args, allowed_host=""):
        return subprocess.run(
            ["sh", str(SCRIPT), *args],
            cwd=self.project,
            env={**os.environ, "UNDERSTAND_ANYTHING_ROOT": str(self.plugin),
                 "__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": allowed_host},
            capture_output=True, text=True, check=False,
        )

    def test_current_directory_and_vite_defaults(self):
        self.graph()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.project), result.stdout)
        self.assertIn(str(self.dashboard), result.stdout)
        self.assertIn("\ncalculation.tailnet.internal\n", result.stdout)
        self.assertTrue(result.stdout.endswith("--strictPort\n--host\n0.0.0.0\n--port\n5173\n"))

    def test_explicit_project_and_container_bind(self):
        self.graph()
        result = self.run_launcher(str(self.project), "--host", "127.0.0.1", "--port", "5174")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith(
            "--strictPort\n--host\n0.0.0.0\n--port\n5173\n--host\n127.0.0.1\n--port\n5174\n"))

    def test_explicit_allowed_host_is_preserved(self):
        self.graph()
        result = self.run_launcher(allowed_host="other.tailnet.internal")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("\nother.tailnet.internal\n", result.stdout)
        self.assertNotIn("calculation.tailnet.internal", result.stdout)

    def test_legacy_graph(self):
        self.graph(".understand-anything")
        self.graph()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Viewing: {self.project}/.understand-anything/knowledge-graph.json", result.stdout)

    def test_missing_graph_does_not_launch_vite(self):
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("/understand first", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_empty_legacy_directory_falls_back_to_ua(self):
        self.graph()
        (self.project / ".understand-anything").mkdir()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"Viewing: {self.project}/.ua/knowledge-graph.json", result.stdout)

    def test_missing_runtime(self):
        self.graph()
        (self.dashboard / "node_modules/.bin/vite").unlink()
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Rebuild/pull", result.stderr)

    def test_recipe_is_ephemeral_and_loopback_published(self):
        recipe = (REPO / "justfile").read_text().split('understand port="5173":', 1)[1].split('\njupyter-status:', 1)[0]
        self.assertIn("run --rm --no-deps", recipe)
        self.assertIn("127.0.0.1:$1:$1", recipe)
        self.assertIn("--entrypoint devenv-understand", recipe)
        self.assertIn("--host 0.0.0.0", recipe)
        self.assertIn("COPY --chmod=755 scripts/understand-dashboard.sh /usr/local/bin/devenv-understand", (REPO / "Dockerfile").read_text())


if __name__ == "__main__":
    unittest.main()
