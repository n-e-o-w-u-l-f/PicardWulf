"""Pinned Picard 3.0.2 *source* integration for cancellable FLAC move policy.

This is a core-source patch builder, not a runtime monkeypatch or installer.
It edits ONLY an isolated checkout of the upstream tag after the operator
reviews it. Source anchors are exact and fail closed on upstream drift.
The user's live Picard installation and music are never touched.
"""
from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

SOURCES = (
    "picard/file.py",
    "picard/extension_points/event_hooks.py",
    "picard/plugin3/api_impl.py",
)


def _replace_once(source: str, before: str, after: str, name: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"Picard 3.0.2 source changed: {name}: {count} matching anchors")
    return source.replace(before, after, 1)


def patch_sources(source: dict[str, str]) -> dict[str, str]:
    """Return complete modified sources, without writing files."""
    if set(source) != set(SOURCES):
        raise ValueError("Exactly the three Picard 3.0.2 files are required")

    file = source["picard/file.py"]
    file = _replace_once(
        file,
        "        metadata.copy(self.metadata)\n        # Track in-flight saves",
        """        metadata.copy(self.metadata)
        # Capture loaded-target ownership on the Qt thread. The worker must
        # not query mutable Tagger/Qt objects to arbitrate FLAC collisions.
        collision_target_loaded = False
        if (file_move_collision_processors.functions
                and self.filename.lower().endswith('.flac')):
            settings = get_config().setting
            if settings['rename_files'] or settings['move_files']:
                proposed = self.make_filename(self.filename, metadata, settings)
                collision_target_loaded = (
                    proposed != self.filename and proposed in self.tagger.files)
        # Track in-flight saves""",
        "file.save loaded target")
    file = _replace_once(
        file,
        "partial(self._save_and_rename, self.filename, metadata),",
        "partial(self._save_and_rename, self.filename, metadata, collision_target_loaded),",
        "file.save worker args")
    file = _replace_once(
        file,
        "    def _save_and_rename(self, old_filename, metadata):",
        "    def _save_and_rename(self, old_filename, metadata, collision_target_loaded=False):",
        "save worker signature")
    file = _replace_once(
        file,
        "self._rename(old_filename, metadata, config.setting)",
        "self._rename(old_filename, metadata, config.setting, collision_target_loaded)",
        "save worker rename call")
    file = _replace_once(
        file,
        "        self._move_additional_files(old_filename, new_filename, config)",
        """        # Source-preserving native FLAC copy must not relocate companion
        # files from the staging directory. The original native MOVE still
        # removes its source and keeps Picard's original sidecar behavior.
        if new_filename == old_filename or not os.path.exists(old_filename):
            self._move_additional_files(old_filename, new_filename, config)""",
        "preserve staging companion files after native safe copy")
    file = _replace_once(
        file,
        "    def _rename(self, old_filename, metadata, settings):",
        "    def _rename(self, old_filename, metadata, settings, destination_loaded=False):",
        "rename policy signature")
    file = _replace_once(
        file,
        """        new_dirname = os.path.dirname(new_filename)
        os.makedirs(new_dirname, exist_ok=True)
        if not settings['move_overwrite_existing_files']:""",
        """        # Explicit source-level extension point, invoked on Picard's native
        # save worker BEFORE any directory creation, move or overwrite. It
        # receives plain strings and a settings copy, never a mutable File.
        # No resolver => upstream native behavior remains unchanged.
        if old_filename.lower().endswith('.flac'):
            resolvers = tuple(file_move_collision_processors.functions)
            if resolvers:
                if len(resolvers) != 1:
                    raise RuntimeError('Conflicting native FLAC collision policies')
                decision = resolvers[0](
                    old_filename, new_filename, dict(settings),
                    destination_loaded)
                if not isinstance(decision, dict):
                    raise RuntimeError('Invalid native FLAC collision result')
                action = decision.get('action')
                if action == 'KEEP':
                    return old_filename
                if action == 'COMMITTED':
                    if (decision.get('destination') != new_filename
                            or not os.path.isfile(new_filename)):
                        raise RuntimeError('Native FLAC destination not verified')
                    return new_filename
                if action != 'UNHANDLED':
                    raise RuntimeError('Unexpected native FLAC collision decision')

        new_dirname = os.path.dirname(new_filename)
        os.makedirs(new_dirname, exist_ok=True)
        if not settings['move_overwrite_existing_files']:""",
        "rename interception before native move")
    file = _replace_once(
        file,
        "file_pre_save_processors = PluginFunctions[[File], None](label='file_pre_save_processors')",
        """file_move_collision_processors = PluginFunctions(label='file_move_collision_processors')
file_pre_save_processors = PluginFunctions[[File], None](label='file_pre_save_processors')""",
        "native collision processor registry")

    hooks = source["picard/extension_points/event_hooks.py"]
    hooks = _replace_once(
        hooks,
        "    file_post_save_processors,\n    file_pre_save_processors,",
        "    file_post_save_processors,\n    file_move_collision_processors,\n    file_pre_save_processors,",
        "event hooks registry import")
    hooks = _replace_once(
        hooks,
        "\ndef register_file_pre_save_processor(function: Callable[[File], None], priority: int = 0) -> None:",
        """\ndef register_file_move_collision_processor(function: Callable[..., dict]) -> None:
    \"\"\"Register one worker-safe file-move resolver.

    The callback receives (old_filename, target_filename, frozen_settings,
    destination_loaded). It returns action KEEP, COMMITTED or UNHANDLED.
    Every callback must be side-effect-safe, not touch File/Tagger/Qt, and
    ensure COMMITTED is an independently verified, recoverable copy.
    \"\"\"
    file_move_collision_processors.register(function.__module__, function)


def register_file_pre_save_processor(function: Callable[[File], None], priority: int = 0) -> None:""",
        "event hooks new registry function")

    api = source["picard/plugin3/api_impl.py"]
    api = _replace_once(
        api,
        "    register_file_post_save_processor,\n    register_file_pre_save_processor,",
        "    register_file_post_save_processor,\n    register_file_move_collision_processor,\n    register_file_pre_save_processor,",
        "plugin3 API extension import")
    api = _replace_once(
        api,
        "    def register_file_pre_save_processor(\n",
        """    def register_file_move_collision_processor(
        self, function: Callable[['PluginApi', str, str, dict, bool], dict]
    ) -> None:
        \"\"\"Register a worker-safe cancellable file move collision policy.

        Invoked before Picard's native rename/overwrite on the save worker
        with (old_filename, target_filename, settings_copy,
        destination_loaded). Return a dict with action KEEP, COMMITTED or
        UNHANDLED. Only COMMITTED can return a new file path, and the new
        target must already be independently verified and recoverable.

        This is a Picard 3.0.2 *core extension*, not part of stock Picard.
        \"\"\"
        wrapped = partial(function, self)
        update_wrapper(wrapped, function)
        return register_file_move_collision_processor(wrapped)

    def register_file_pre_save_processor(
""",
        "plugin3 public native collision policy API")

    return {
        "picard/file.py": file,
        "picard/extension_points/event_hooks.py": hooks,
        "picard/plugin3/api_impl.py": api,
    }


def unified_patch(source: dict[str, str]) -> str:
    patched = patch_sources(source)
    return ''.join(
        ''.join(unified_diff(
            source[path].splitlines(keepends=True),
            patched[path].splitlines(keepends=True),
            fromfile='a/'+path,
            tofile='b/'+path,
        )) for path in SOURCES
    )


def read_checkout(root: Path) -> dict[str, str]:
    root = Path(root)
    return {path: (root/path).read_text(encoding='utf-8') for path in SOURCES}


def write_checkout_patch(root: Path, patch_out: Path) -> None:
    """Produce a reviewable patch. NEVER apply it to a live installation."""
    patch_out = Path(patch_out)
    patch_out.write_text(unified_patch(read_checkout(root)), encoding='utf-8')
