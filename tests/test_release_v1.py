"""Release integration checks; do not require a working Picard GUI."""
from pathlib import Path
import unittest
ROOT=Path(__file__).parents[1]
class TestPackaging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.installer=(ROOT/'Install-NEOWULF.ps1').read_text(encoding='utf8')
        cls.workflow=(ROOT/'neowulf_picard_repair/native_workflow.py').read_text(encoding='utf8')
        cls.ui=(ROOT/'neowulf_picard_repair/native_ui.py').read_text(encoding='utf8')
        cls.plugin=(ROOT/'neowulf_picard_repair/__init__.py').read_text(encoding='utf8')
        cls.pub=(ROOT/'Publish-PicardWulf.ps1').read_text(encoding='utf8')
    def test_native_picard_method(self):
        self.assertIn('api.tagger.move_file_to_track(f, release, recording)',self.ui)
        self.assertIn('native_release_target(q,c)',self.ui)
    def test_explicit_tag_save_uses_native_picard(self):
        self.assertIn("io.backup('backup:manual',f.filename)",self.ui)
        self.assertNotIn('media_backup(f.filename)',self.ui)
        self.assertIn('f.update()',self.ui)
        self.assertIn('f.save()',self.ui)
        self.assertIn('QMessageBox.question',self.ui)
    def test_no_background_audio_write(self):
        eng=(ROOT/'neowulf_picard_repair/universal_engine.py').read_text(encoding='utf8')
        self.assertNotIn('f.save()',eng)
        self.assertNotIn('file.save()',eng)
    def test_plugin_registers_native_review_and_context_action(self):
        self.assertIn('api.register_tools_menu_action(NativeReview)',self.plugin)
        self.assertIn('api.register_file_action(SelectedFileReview)',self.plugin)
    def test_installer_knows_v2_v3_and_current(self):
        self.assertIn('Matches-Known-V2',self.installer)
        self.assertIn('Matches-Known-V3',self.installer)
        self.assertIn("'already_current'",self.installer)
        self.assertIn("'upgrade_v3'",self.installer)
        self.assertIn('native_ui.py',self.installer)
        self.assertIn('native_workflow.py',self.installer)
    def test_publisher_pinned_exactly_one_repo(self):
        self.assertIn("$repo = 'n-e-o-w-u-l-f/PicardWulf'",self.pub)
        self.assertNotIn('force-push',self.pub.split('& git -C $stage push origin HEAD')[0].lower())
        self.assertIn('git -C $stage push origin HEAD',self.pub)
        self.assertIn('gh api "repos/$repo/commits/$commit"',self.pub)
    def test_no_clobber_unknown_plugin(self):
        self.assertIn('Pluginordner hat unbekannte lokale Aenderungen',self.installer)
    def test_license_changelog(self):
        self.assertIn('MIT License',(ROOT/'LICENSE').read_text(encoding='utf8'))
        self.assertIn('## PicardWulf v1.0 — Target release',(ROOT/'CHANGELOG.md').read_text(encoding='utf8'))
    def test_bmax_live_status_disclaimed(self):
        self.assertIn('not yet verified',(ROOT/'README.md').read_text(encoding='utf8'))

if __name__=='__main__':unittest.main()
