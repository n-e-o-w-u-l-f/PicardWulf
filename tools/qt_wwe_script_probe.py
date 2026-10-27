"""Real Picard 3.0.2 parser smoke for native $pw_wwe_folder() integration.

For an isolated virtualenv and official Picard 3.0.2 source only.
Never reads user Picard.ini, preset 3, music files, or installed plugins.
"""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main() -> int:
    if sys.base_prefix == sys.prefix:
        raise RuntimeError("Isolated Python virtualenv required")
    with TemporaryDirectory(prefix="picardwulf-wwe-script-") as tmp:
        for key in ("APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                    "XDG_DATA_HOME", "XDG_CACHE_HOME"):
            p=Path(tmp)/key.lower()
            p.mkdir()
            os.environ[key]=str(p)
        os.environ["QT_QPA_PLATFORM"]="offscreen"
        from PyQt6.QtCore import QCoreApplication
        from picard.config import setup_config
        import picard
        if picard.__version__ != "3.0.2":
            raise RuntimeError("Unexpected Picard version")
        app=QCoreApplication([])
        setup_config(app=app, filename=str(Path(tmp)/"test-only-picard.ini"))
        from picard.extension_points.script_functions import register_script_function
        from picard.script import ScriptParser
        from picard.metadata import Metadata
        from neowulf_picard_repair.wwe_series import picard_wwe_folder
        register_script_function(picard_wwe_folder, name="pw_wwe_folder")
        parser=ScriptParser()
        for title,year,vol in [
            ("WWF The Music, Volume 2","1997",2),
            ("Hits of the World Wrestling Federation: We Gotta Wrestle","1997",2),
            ("ThemeAddict: WWE The Music, Vol. 6","2004",6),
            ("Voices: WWE The Music, Vol. 9","2009",9),
        ]:
            md=Metadata()
            md["album"]=title
            md["date"]=year
            result=parser.eval("$pw_wwe_folder(%album%,%date%)", context=md)
            expected=f"Various Artists/WWE The Music/{year} - WWE The Music Volume {vol}"
            if result!=expected:
                raise AssertionError(f"Native Picard script returned {result!r}, expected {expected!r}")
        print(json.dumps({"status":"PASS","version":picard.__version__,
                          "volumes":[2,6,9],"writes_to_media":0}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
