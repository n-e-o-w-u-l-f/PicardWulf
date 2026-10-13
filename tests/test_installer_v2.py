import pathlib
import unittest

ROOT = pathlib.Path(__file__).parents[1]

class TestInstallerV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ps = (ROOT / 'Install-NEOWULF.ps1').read_text(encoding='utf-8')
        cls.cmd = (ROOT / 'Install-NEOWULF.cmd').read_text(encoding='utf-8')
        cls.docs = (ROOT / 'README.md').read_text(encoding='utf-8')

    def test_no_broken_cli_call(self):
        self.assertNotIn('& $cli', self.ps)
        self.assertNotIn('& $cli', self.ps)
        self.assertNotIn('plugins install $target', self.ps)
        self.assertNotIn('plugins install $source', self.ps)

    def test_target_picard_plugins3(self):
        self.assertIn("'MusicBrainz\\Picard\\plugins3'", self.ps)
        self.assertIn('PICARD_PLUGIN_DIR', self.ps)

    def test_only_user_desktop_account(self):
        self.assertIn("$env:USERNAME -ine 'megal'", self.ps)
        self.assertIn("$env:COMPUTERNAME -ine 'BMAX-B6'", self.ps)

    def test_preflight_blocks_live_picard(self):
        self.assertIn('Get-Process', self.ps)
        self.assertIn('Stop-Install', self.ps)

    def test_atomic_stage_and_content_check(self):
        self.assertIn('Files-Match', self.ps)
        self.assertIn('Get-FileHash', self.ps)
        self.assertIn('Move-Item -LiteralPath $stage -Destination $target', self.ps)

    def test_no_config_mutation(self):
        self.assertNotIn('Set-Content', self.ps)
        self.assertNotIn('Add-Content', self.ps)
        self.assertNotIn('plugins3_enabled_plugins', self.ps)

    def test_preserves_old_staging(self):
        self.assertNotIn("Join-Path $env:LOCALAPPDATA 'NEOWULF", self.ps)
        self.assertIn('fehlgeschlagenen Registrierungsversuch', self.docs)

    def test_activation_is_explicit(self):
        self.assertIn('Aktivieren', self.ps)
        self.assertIn('GUI', self.ps)

    def test_cmd_entrypoint(self):
        self.assertIn('Install-NEOWULF.ps1', self.cmd)
        self.assertIn('ExecutionPolicy Bypass', self.cmd)

if __name__ == '__main__':
    unittest.main()
