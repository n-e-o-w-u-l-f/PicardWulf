"""Real Picard 3.0.2 ScriptParser/Qt integration smoke for Preset 3 wrapper.

Disposable configuration only; no user profile or media ever accessed.
"""
from pathlib import Path
import json
import os
import sys
from tempfile import TemporaryDirectory


def main():
    if sys.base_prefix==sys.prefix:
        raise RuntimeError("Use an isolated venv with official Picard 3.0.2")
    with TemporaryDirectory(prefix="picardwulf-bmax-parser-") as tmp:
        for key in ("APPDATA","LOCALAPPDATA","XDG_CONFIG_HOME","XDG_DATA_HOME","XDG_CACHE_HOME"):
            sub=Path(tmp)/key.lower()
            sub.mkdir()
            os.environ[key]=str(sub)
        os.environ["QT_QPA_PLATFORM"]="offscreen"
        from PyQt6.QtCore import QCoreApplication
        from picard.config import setup_config
        from picard.script import ScriptParser
        from picard.metadata import Metadata
        from picard.extension_points.script_functions import register_script_function
        import picard
        if picard.__version__!="3.0.2":
            raise RuntimeError("Unexpected Picard release")
        app=QCoreApplication([])
        setup_config(app=app,filename=str(Path(tmp)/"disposable-picard.ini"))
        from neowulf_picard_repair.bmax_naming import (
            picard_bmax_folder,picard_bmax_fullpath)
        from neowulf_picard_repair.preset3_migration import prepare_active_preset3
        register_script_function(picard_bmax_folder,name="pw_bmax_folder")
        register_script_function(picard_bmax_fullpath,name="pw_bmax_fullpath")
        original=(
            "$noop(NEOWULF_UNMATCHED_FALLBACK)"
            "$if(%albumartist%,%albumartist%/%date% - %album%/"
            "$num(%tracknumber%,2) - %title%,fallback/Track)"
        )
        scripts={"id3":{"title":"Preset 3","script":original},
                 "other":{"title":"Untouched","script":"%artist%/%album%"}}
        transformed,receipt=prepare_active_preset3(scripts,"id3")
        testset=[
            ("Dr. Dre & Friends","Verschiedene Interpreten","2003","Intro",
             "Dr. Dre/2003 - Dr. Dre & Friends/01 - Intro"),
            ("Nordic Rave 2","Verschiedene Interpreten","1996","Antiloop",
             "![-1.2-VARiOUS-ARTiSTz-]!/Nordic Rave/1996 - Nordic Rave 2/01 - Antiloop"),
            ("Danza Kuduro","W&W X AXMO X André Schnura feat. Lucenzo & Don Omar",
             "2024","Danza Kuduro",
             "![-1.1-COLLABORATiVEz--]!/W&W X AXMO X André Schnura feat. Lucenzo & Don Omar/2024 - Danza Kuduro/01 - Danza Kuduro"),
            ("Rolfs Liederkalender _ Die Jahresuhr","Verschiedene Interpreten",
             "2001","Die Jahresuhr",
             "Rolf Zuckowski/2001 - Die Jahresuhr/01 - Die Jahresuhr"),
            ("Aladdin (Deutscher Original Film-Soundtrack)","Verschiedene Interpreten",
             "1993","Intro",
             "[--3--SOUNTRACKz--]/1993 - Aladdin (Deutscher Original Film-Soundtrack)/01 - Intro"),
        ]
        parser=ScriptParser()
        parser.parse(transformed['id3']['script'])
        count=0
        for title,albumartist,year,track,expected in testset:
            md=Metadata()
            md['album']=title
            md['albumartist']=albumartist
            md['date']=year
            md['tracknumber']='1'
            md['title']=track
            actual=parser.eval(transformed['id3']['script'],context=md)
            if actual!=expected:
                raise AssertionError(f'{title}: {actual!r} != {expected!r}')
            count+=1
        print(json.dumps({
            "status":"PASS","picard":picard.__version__,
            "real_script_parser":True,"cases":count,
            "original_script_unchanged":scripts['id3']['script']==original,
            "other_preset_unchanged":transformed["other"]==scripts["other"],
            "writes_to_user_media":0,
        }))
if __name__=="__main__":
    main()
