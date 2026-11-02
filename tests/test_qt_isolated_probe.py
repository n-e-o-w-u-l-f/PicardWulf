"""Isolated Qt smoke is safe and refuses an unpatched or unknown Picard tree.

All tests here are stdlib-only: Qt is imported only by run_smoke().
"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from compat import picard302_core_contract as core
from compat import qt_isolated_probe as smoke


class QtIsolationSourceChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        for path in core.SOURCES:
            f = self.root / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"# stand-in upstream Git blob\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(self.root),
            "-c", "user.name=Test", "-c", "user.email=dev@invalid.example",
            "commit", "-qm", "baseline",
        ], check=True)
        self.expected = {
            path: smoke._blob_sha((self.root / path).read_bytes())
            for path in core.SOURCES
        }

    def add_patch_markers(self):
        with (self.root / "picard/file.py").open("a", encoding="utf-8") as f:
            f.write("collision_native_plan = ('frozen',)\n")
        with (self.root / "picard/plugin3/api_impl.py").open("a", encoding="utf-8") as f:
            f.write("def register_file_move_collision_processor(): pass\n")
        with (self.root / "picard/extension_points/event_hooks.py").open("a", encoding="utf-8") as f:
            f.write("native_hook = True\n")

    def test_known_blob_with_complete_patched_source_passes(self):
        self.add_patch_markers()
        with patch.object(core, "UPSTREAM_BLOBS", self.expected):
            smoke.verify_upstream(self.root)

    def test_unpatched_source_refused(self):
        with patch.object(core, "UPSTREAM_BLOBS", self.expected):
            with self.assertRaisesRegex(RuntimeError, "Unpatched"):
                smoke.verify_upstream(self.root)

    def test_unrecognized_base_refused_even_with_patch_markers(self):
        self.add_patch_markers()
        mismatch = dict(self.expected)
        mismatch["picard/file.py"] = "0" * 40
        with patch.object(core, "UPSTREAM_BLOBS", mismatch):
            with self.assertRaisesRegex(RuntimeError, "Unrecognized upstream"):
                smoke.verify_upstream(self.root)

    def test_incomplete_patch_refused(self):
        with (self.root / "picard/file.py").open("a", encoding="utf-8") as f:
            f.write("collision_native_plan = 1\n")
        with (self.root / "picard/plugin3/api_impl.py").open("a", encoding="utf-8") as f:
            f.write("register_file_move_collision_processor = None\n")
        # Event hooks is still stock.
        with patch.object(core, "UPSTREAM_BLOBS", self.expected):
            with self.assertRaisesRegex(RuntimeError, "Unpatched"):
                smoke.verify_upstream(self.root)


if __name__ == "__main__":
    unittest.main()
