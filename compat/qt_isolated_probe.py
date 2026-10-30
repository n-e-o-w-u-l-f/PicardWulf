"""Isolated, non-mutating Qt/Picard 3.0.2 runtime smoke.

Do not import the PyInstaller-managed _internal/PyQt6 from production Picard.
Run only from a dedicated Python virtualenv whose packages were installed
independently. This verifies a real Qt event loop and native Picard Python
imports; it does NOT launch the complete Tagger GUI or authorize deployment.
"""
from __future__ import annotations

import argparse
from hashlib import sha1
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def _blob_sha(payload: bytes) -> str:
    return sha1(b"blob " + str(len(payload)).encode("ascii") + b"\x00" + payload).hexdigest()


def verify_upstream(checkout: Path) -> None:
    """Verify official base HEAD and source-level patched API without writes."""
    from compat.picard302_core_contract import SOURCES, UPSTREAM_BLOBS

    checkout = checkout.resolve(strict=True)
    for rel in SOURCES:
        base = subprocess.run(
            ["git", "-C", str(checkout), "show", "HEAD:" + rel],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        ).stdout
        if _blob_sha(base) != UPSTREAM_BLOBS[rel]:
            raise RuntimeError(f"Unrecognized upstream Picard 3.0.2 base: {rel}")
        source = (checkout / rel).read_text(encoding="utf-8")
        if source.encode("utf-8") == base:
            raise RuntimeError(f"Unpatched Picard 3.0.2 source: {rel}")
    if "collision_native_plan" not in (checkout / "picard/file.py").read_text(encoding="utf-8"):
        raise RuntimeError("Missing native snapshot/target drift guard")
    if "register_file_move_collision_processor" not in (
        checkout / "picard/plugin3/api_impl.py"
    ).read_text(encoding="utf-8"):
        raise RuntimeError("Missing native move collision registration")


def run_smoke(checkout: Path) -> dict[str, str]:
    checkout = checkout.resolve(strict=True)
    verify_upstream(checkout)
    if not getattr(sys, "base_prefix", sys.prefix) != sys.prefix:
        raise RuntimeError("Refusing to import Qt outside a dedicated Python virtualenv")
    if any("MusicBrainz Picard\\_internal" in p or "MusicBrainz Picard/_internal" in p
           for p in sys.path):
        raise RuntimeError("Refusing production PyInstaller _internal Python packages")

    # These variables are set before importing Picard, which initializes
    # platform-specific appdirs and may open or write configuration files.
    with tempfile.TemporaryDirectory(prefix="picardwulf-qt-smoke-") as tmp:
        sandbox = Path(tmp)
        for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                     "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            target = sandbox / name.lower()
            target.mkdir(parents=True, exist_ok=True)
            os.environ[name] = str(target)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["PICARD_DISABLE_AUTOUPDATE"] = "1"
        os.environ.pop("PYTHONHOME", None)
        os.environ.pop("QT_PLUGIN_PATH", None)
        # Always prefer this *patched* checkout to installed stock Picard.
        sys.path.insert(0, str(checkout))
        from PyQt6.QtCore import QTimer, PYQT_VERSION_STR
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        import picard
        assert picard.__version__ == "3.0.2", picard.__version__
        assert Path(picard.__file__).resolve().is_relative_to(checkout)
        from picard.file import File, file_move_collision_processors
        from picard.plugin3.api_impl import PluginApi
        from picard.extension_points.event_hooks import register_file_move_collision_processor

        if not callable(register_file_move_collision_processor):
            raise AssertionError("Event hooks native registration is not callable")
        if not callable(PluginApi.register_file_move_collision_processor):
            raise AssertionError("PluginApi missing native collision registration")
        if not callable(File.save) or not callable(File._rename):
            raise AssertionError("Native File.save/_rename missing")
        if not hasattr(file_move_collision_processors, "functions"):
            raise AssertionError("Native move registry unavailable")

        QTimer.singleShot(0, app.quit)
        result = app.exec()
        if result != 0:
            raise RuntimeError(f"Real Qt event loop exited with {result}")
        return {
            "status": "PASS_QT_SMOKE_NOT_FULL_GUI",
            "picard": picard.__version__,
            "qt_python": PYQT_VERSION_STR,
            "platform": app.platformName(),
            "upstream": str(checkout),
            "native_extension": "PRESENT",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_smoke(args.upstream)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc), "type": type(exc).__name__}),
              file=sys.stderr)
        raise
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
