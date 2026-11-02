"""Boot the actual patched Picard 3.0.2 Tagger under an isolated Qt profile.

This is a full QWidget/Tagger startup and clean shutdown in a temporary
profile, NOT a Windows production Ctrl+S or end-to-end FLAC save test.
Do not use the PyInstaller-managed production Picard _internal Python tree.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from compat.qt_isolated_probe import verify_upstream


def run_full_tagger(checkout: Path) -> dict[str, str]:
    checkout = checkout.resolve(strict=True)
    verify_upstream(checkout)
    if sys.base_prefix == sys.prefix:
        raise RuntimeError("Dedicated virtualenv required; production Python is not accepted")
    if any("musicbrainz picard" in p.casefold() and "_internal" in p.casefold()
           for p in sys.path):
        raise RuntimeError("Refusing production PyInstaller Qt libraries")

    # Picard reads these during Tagger initialization, not just QApplication.
    # The temporary directory is removed when the probe finishes.
    with tempfile.TemporaryDirectory(prefix="picardwulf-full-tagger-") as tmp:
        root = Path(tmp)
        for name in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                     "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            d = root / name.lower()
            d.mkdir(parents=True, exist_ok=True)
            os.environ[name] = str(d)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        os.environ["PICARD_DISABLE_AUTOUPDATE"] = "1"
        os.environ.pop("QT_PLUGIN_PATH", None)
        os.environ.pop("PYTHONHOME", None)
        sys.path.insert(0, str(checkout))

        # No user-supplied media path or command-line options are carried into
        # Picard; there is no launched production app, plugin or real music.
        sys.argv[:] = ["picard", "--no-crash-dialog"]
        from PyQt6.QtCore import QTimer, PYQT_VERSION_STR
        from picard.tagger import Tagger, process_cmdline_args
        import picard
        if picard.__version__ != "3.0.2":
            raise RuntimeError("Unexpected Picard release")
        if not Path(picard.__file__).resolve().is_relative_to(checkout):
            raise RuntimeError("Tagger is not using the patched source checkout")
        args = process_cmdline_args()
        tagger = Tagger(args, localedir=None, autoupdate=False, pipe_handler=None)
        if not tagger.window:
            raise RuntimeError("Picard Qt main window not initialized")
        # Run the real Tagger.run() event loop briefly and then exit normally.
        QTimer.singleShot(1000, tagger.quit)
        code = tagger.run()
        if code != 0:
            raise RuntimeError(f"Full Qt Tagger startup exited with {code}")
        return {
            "status": "PASS_FULL_TAGGER_OFFSCREEN_NOT_WINDOWS_SAVE",
            "picard": picard.__version__,
            "qt_python": PYQT_VERSION_STR,
            "upstream": str(checkout),
            "exit_code": "0",
            "production_data": "NOT_ACCESSED",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_full_tagger(args.upstream)
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "type": type(exc).__name__,
                          "error": str(exc)}), file=sys.stderr)
        raise
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
