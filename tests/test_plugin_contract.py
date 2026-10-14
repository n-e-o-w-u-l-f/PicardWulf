import importlib
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

qt = types.ModuleType('PyQt6')
widgets = types.ModuleType('PyQt6.QtWidgets')
class FakeMessageBox:
    class StandardButton:
        Yes = 1
        No = 2
    answer = 2
    messages = []
    @classmethod
    def question(cls, *args):
        return cls.answer
    @classmethod
    def information(cls, *args):
        cls.messages.append(('info', args))
    @classmethod
    def warning(cls, *args):
        cls.messages.append(('warn', args))
widgets.QMessageBox = FakeMessageBox
qt.QtWidgets = widgets

picard = types.ModuleType('picard')
plugin3 = types.ModuleType('picard.plugin3')
api_mod = types.ModuleType('picard.plugin3.api')
class FakeBaseAction: pass
api_mod.BaseAction = FakeBaseAction
script_mod = types.ModuleType('picard.script')
class FakeParser:
    def parse(self, code):
        if not code:
            raise ValueError('blank code')
        return code
script_mod.ScriptParser = FakeParser

for key, mod in [('PyQt6',qt),('PyQt6.QtWidgets',widgets),('picard',picard),('picard.plugin3',plugin3),('picard.plugin3.api',api_mod),('picard.script',script_mod)]:
    sys.modules[key] = mod

plugin = importlib.import_module('neowulf_picard_repair')
logic = importlib.import_module('neowulf_picard_repair.repair_logic')

class Setting(dict):
    def raw_value(self, name): return self[name]
class Config:
    def __init__(self):
        self.setting = Setting(file_renaming_scripts={
            'a': {'title':'NEOWULF','script':'$noop(NEOWULF_UNMATCHED_FALLBACK)'+logic.OLD+'/%title%'},
            'b': {'title':'Other','script':'%album%'}},
            active_file_naming_script_id='Preset 3')
        self.profiles = {'user_profiles': []}
        self.synced = 0
    def sync(self): self.synced+=1
class Logger:
    def error(self,*args): pass
    def info(self,*args): pass
class PluginConfig(dict):
    def register_option(self,key,default):
        self.setdefault(key,default)

class Api:
    def __init__(self):
        self.global_config=Config()
        self.plugin_config=PluginConfig()
        self.tagger=object()
        self.logger=Logger()
        self.registered=[]
    def register_tools_menu_action(self,cls):self.registered.append(('tools',cls))
    def register_file_action(self,cls):self.registered.append(('file_action',cls))
    def register_album_metadata_processor(self,fn,priority):self.registered.append(('processor',fn,priority))
    def register_file_post_load_processor(self,fn,priority=0):self.registered.append(('file_event',fn,priority))
    def register_track_metadata_processor(self,fn,priority=0):self.registered.append(('track_event',fn,priority))
class TestContract(unittest.TestCase):
    def tearDown(self):
        plugin.disable()
    def setUp(self):
        FakeMessageBox.answer=FakeMessageBox.StandardButton.No
        FakeMessageBox.messages.clear()
    def test_enable_registers_no_mutations(self):
        api=Api()
        before=api.global_config.setting['file_renaming_scripts']['a']['script']
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        self.assertEqual(len(api.registered),14)
        self.assertTrue(api.plugin_config['auto_apply_best'])
        self.assertFalse(api.plugin_config['auto_save_with_backup'])
        self.assertEqual(api.global_config.setting['file_renaming_scripts']['a']['script'],before)
    def test_repair_declined_changes_nothing(self):
        api=Api();act=plugin.Repair();act.api=api
        before=api.global_config.setting['file_renaming_scripts']['a']['script']
        act.callback([])
        self.assertEqual(api.global_config.setting['file_renaming_scripts']['a']['script'],before)
        self.assertEqual(api.global_config.setting['active_file_naming_script_id'],'Preset 3')
        self.assertEqual(api.global_config.synced,0)
    def test_repair_confirmed_changes_only_one_script(self):
        api=Api();act=plugin.Repair();act.api=api
        FakeMessageBox.answer=FakeMessageBox.StandardButton.Yes
        with patch.object(plugin,'_backup',return_value=pathlib.Path('backup.ini')) as bk:
            act.callback([])
        self.assertEqual(api.global_config.setting['active_file_naming_script_id'],'a')
        self.assertIn(logic.NEW,api.global_config.setting['file_renaming_scripts']['a']['script'])
        self.assertNotIn(logic.OLD,api.global_config.setting['file_renaming_scripts']['a']['script'])
        self.assertEqual(api.global_config.setting['file_renaming_scripts']['b']['script'],'%album%')
        bk.assert_called_once()
    def test_no_candidate_keeps_original_state(self):
        api=Api();api.global_config.setting['file_renaming_scripts']['a']['script']='%album%'
        act=plugin.Repair();act.api=api
        FakeMessageBox.answer=FakeMessageBox.StandardButton.Yes
        with patch.object(plugin,'_backup') as bk:
            act.callback([])
            bk.assert_not_called()
        self.assertEqual(api.global_config.setting['active_file_naming_script_id'],'Preset 3')
    def test_filename_fallback_only_on_clear_pattern(self):
        from types import SimpleNamespace
        track=SimpleNamespace(filename=r'C:\Music\Eminem - Mockingbird.flac', metadata={})
        self.assertEqual(plugin._file_snapshot(track)['artist'],'Eminem')
        self.assertEqual(plugin._file_snapshot(track)['title'],'Mockingbird')
        self.assertEqual(plugin._file_snapshot(track)['inferred_filename'],'1')
        other=SimpleNamespace(filename=r'C:\Music\01-Mockingbird.flac',metadata={})
        self.assertEqual(plugin._file_snapshot(other)['title'],'')

    def test_existing_tags_not_rewritten_by_filename(self):
        from types import SimpleNamespace
        track=SimpleNamespace(filename='Other - Wrong.flac',metadata={'artist':'Eminem','title':'Mockingbird'})
        self.assertEqual(plugin._file_snapshot(track)['artist'],'Eminem')
        self.assertNotIn('inferred_filename',plugin._file_snapshot(track))

    def test_release_guard(self):
        api=Api();m={'musicbrainz_releasegroupid':logic.RGID,'albumartist':'Apple Music'}
        plugin._album_guard(api,None,m,{})
        self.assertEqual(m['albumartist'],'Eminem')
if __name__=='__main__':unittest.main()
