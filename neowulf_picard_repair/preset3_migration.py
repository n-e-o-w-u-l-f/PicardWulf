"""Conservative, backup-ready migration of ONLY active BMAX Preset 3.

Pure transformation; all QSettings I/O and full Picard.ini backup are owned
by plugin GUI action. Requires live Picard 3 parser to validate the result.
Never changes file contents, other saved scripts, or active preset selection.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256

class PresetMigrationRefused(ValueError):
    pass

PREFIX="$pw_bmax_fullpath("
SUFFIX=(
    ",%album%,%albumartist%,%originaldate%,%date%,"
    "%_primaryreleasetype%,$join(%albumartists%,;),"
    "%sampler_collection%,%sampler_volume%)"
)


def prepare_active_preset3(scripts, active_id):
    if not isinstance(scripts,dict):
        raise PresetMigrationRefused("Picard's naming scripts are not a dictionary")
    if active_id not in scripts:
        raise PresetMigrationRefused("The actual active preset ID is missing")
    selected=scripts[active_id]
    if not isinstance(selected,dict):
        raise PresetMigrationRefused("Active preset entry is not a dictionary")
    name=str(selected.get('title') or '')
    original=selected.get('script')
    if not isinstance(original,str) or not original.strip():
        raise PresetMigrationRefused("Active preset has no usable script")
    # Only user's genuine Preset 3, or the same proven NEOWULF body where the
    # preset ID/title was read from Picard. No surprise unnamed script edits.
    if "preset 3" not in name.casefold():
        raise PresetMigrationRefused(
            "Active script is not demonstrably titled Preset 3")
    if "$pw_bmax_fullpath(" in original:
        raise PresetMigrationRefused("Preset 3 already wrapped, no nested patch")
    if original.count("$pw_bmax_") or len(original)>200_000:
        raise PresetMigrationRefused("Unknown partial patch or overlong script")
    before_hash=sha256(original.encode("utf-8")).hexdigest()
    new=PREFIX+original+SUFFIX
    if not new.startswith(PREFIX) or new[len(PREFIX):-len(SUFFIX)]!=original:
        raise PresetMigrationRefused("Script byte/character retention check failed")
    updated=deepcopy(scripts)
    updated[active_id]['script']=new
    if {key for key in updated if key!=active_id}!={key for key in scripts if key!=active_id}:
        raise PresetMigrationRefused("Unrelated script keys differ")
    for key in scripts:
        if key!=active_id and updated[key]!=scripts[key]:
            raise PresetMigrationRefused("Another naming preset changed unexpectedly")
    return updated, {"active_id":active_id,"title":name,
                     "original_sha256":before_hash,
                     "updated_sha256":sha256(new.encode("utf-8")).hexdigest()}
