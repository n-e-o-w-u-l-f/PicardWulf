"""Packaging and documentation invariants for PicardWulf cross-source updates."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
LANGUAGES=['README.md','README.de.md','README.ru.md','README.fr.md',
           'README.es.md','README.it.md','README.pt-BR.md',
           'README.pl.md','README.uk.md','README.ja.md','README.zh-CN.md']

class DocumentationAndInstaller(unittest.TestCase):
    def test_all_readme_languages_crosslink_above_h1(self):
        for name in LANGUAGES:
            with self.subTest(name=name):
                content=(ROOT/name).read_text(encoding='utf-8')
                header=content.split('</div>',1)[0]
                self.assertLess(content.index('</div>'),content.index('# PicardWulf'))
                for target in LANGUAGES:
                    self.assertEqual(header.count(']('+target+')'),1,(name,target))
                self.assertGreater(len(content),1500)

    def test_en_de_ru_have_runtime_caveats(self):
        docs=[(ROOT/name).read_text(encoding='utf-8') for name in LANGUAGES[:3]]
        for content in docs:
            self.assertIn('93',content)
            self.assertIn('BMAX-B6',content)
            self.assertIn('Deezer',content)
            self.assertIn('Spotify',content)

    def test_upgrade_from_v1_v2_v3_is_protected(self):
        installer=(ROOT/'Install-NEOWULF.ps1').read_text(encoding='utf-8')
        for name in ('Matches-Known-V1','Matches-Known-V2','Matches-Known-V3',
                     'upgrade_v1','upgrade_v2','upgrade_v3',
                     'Matches-Pinned-Source'):
            self.assertIn(name,installer)
        self.assertIn('Pluginordner hat unbekannte lokale Aenderungen',installer)
        self.assertIn('auto_selection.py',installer)
        self.assertIn('auto_apply.py',installer)

    def test_source_neutral_plugin_hooks_and_options(self):
        plugin=(ROOT/'neowulf_picard_repair/__init__.py').read_text(encoding='utf-8')
        for registration in ('api.register_album_metadata_processor(_album_guard',
                             'api.register_file_post_load_processor(_file_loaded)',
                             'api.register_track_metadata_processor(_track_loaded',
                             'api.register_tools_menu_action(Repair)',
                             'api.register_tools_menu_action(ResultsAction)',
                             'api.register_tools_menu_action(NativeReview)',
                             'api.register_tools_menu_action(AutoApplyToggle)',
                             'api.register_tools_menu_action(AutoSaveToggle)'):
            self.assertIn(registration,plugin)
        self.assertIn("register_option('auto_apply_best', True)",plugin)
        self.assertIn("register_option('auto_save_with_backup', False)",plugin)

    def test_native_id_integrity_and_external_release_scoring(self):
        scoring=(ROOT/'neowulf_picard_repair/auto_selection.py').read_text(encoding='utf-8')
        native=(ROOT/'neowulf_picard_repair/native_workflow.py').read_text(encoding='utf-8')
        self.assertIn('source_neutral_score',scoring)
        self.assertIn('multiple editions with distinct release IDs',scoring)
        self.assertIn("candidate.get('source') != 'musicbrainz'",native)
        self.assertIn('~picardwulf_source',(ROOT/'neowulf_picard_repair/auto_apply.py').read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
