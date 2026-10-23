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
class FakeFolderPicker:
    folder = ''
    @classmethod
    def getExistingDirectory(cls, *args):
        return cls.folder
widgets.QFileDialog = FakeFolderPicker

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
    def register_cluster_action(self,cls):self.registered.append(('cluster_action',cls))
    def register_album_action(self,cls):self.registered.append(('album_action',cls))
    def register_album_metadata_processor(self,fn,priority):self.registered.append(('processor',fn,priority))
    def register_file_post_load_processor(self,fn,priority=0):self.registered.append(('file_event',fn,priority))
    def register_file_post_save_processor(self,fn,priority=0):self.registered.append(('file_saved_event',fn,priority))
    def register_track_metadata_processor(self,fn,priority=0):self.registered.append(('track_event',fn,priority))
class TestContract(unittest.TestCase):
    def tearDown(self):
        plugin.disable()
    def setUp(self):
        FakeMessageBox.answer=FakeMessageBox.StandardButton.No
        FakeMessageBox.messages.clear()
        FakeFolderPicker.folder = ''
    def test_enable_registers_no_mutations(self):
        api=Api()
        before=api.global_config.setting['file_renaming_scripts']['a']['script']
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        self.assertEqual(len(api.registered),23)
        self.assertEqual(len([x for x in api.registered if x[0]=='file_action']),3)
        self.assertEqual(sum(x[0]=='file_saved_event' for x in api.registered),1)
        self.assertTrue(api.plugin_config['auto_apply_best'])
        self.assertFalse(api.plugin_config['auto_save_with_backup'])
        self.assertEqual(api.global_config.setting['file_renaming_scripts']['a']['script'],before)
    def test_auto_save_toggle_refuses_unsafe_native_move(self):
        api=Api()
        api.global_config.setting.update({'rename_files':False,'move_files':True})
        action=plugin.AutoSaveToggle()
        action.api=api
        FakeMessageBox.answer=FakeMessageBox.StandardButton.Yes
        action.callback([])
        self.assertFalse(api.plugin_config.get('auto_save_with_backup',False))
        self.assertTrue(any(
            entry[0]=='warn' and 'Umbenennen' in str(entry[1])
            for entry in FakeMessageBox.messages))

    def test_auto_save_toggle_allows_tag_only_mode(self):
        api=Api()
        api.global_config.setting.update({'rename_files':False,'move_files':False})
        action=plugin.AutoSaveToggle()
        action.api=api
        FakeMessageBox.answer=FakeMessageBox.StandardButton.Yes
        action.callback([])
        self.assertTrue(api.plugin_config.get('auto_save_with_backup',False))

    def test_gold_status_exposes_native_early_retirement_warning(self):
        api=Api()
        api.global_config.setting['remove_complete_albums_after_save']=True
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        action=plugin.TagSaveStatus()
        action.api=api
        action.callback([])
        text=' '.join(str(x) for x in FakeMessageBox.messages)
        self.assertIn('GESPERRT',text)
        self.assertIn('PicardWulf-Prüfung',text)

    def test_gold_status_does_not_claim_active_without_controller(self):
        api=Api()
        api.global_config.setting['remove_complete_albums_after_save']=False
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        action=plugin.TagSaveStatus()
        action.api=api
        action.callback([])
        text=' '.join(str(x) for x in FakeMessageBox.messages)
        self.assertIn('NICHT GESTARTET',text)
        self.assertNotIn('GESPERRT',text)

    def test_picard_v3_post_save_hook_dispatches_to_tracker(self):
        api=Api()
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        events=[x for x in api.registered if x[0]=='file_saved_event']
        self.assertEqual(len(events),1)
        witness=object()
        with patch.object(plugin._save_tracker,'post_save',return_value=True) as saved:
            events[0][1](api,witness)
        saved.assert_called_once_with(witness)

    def test_native_core_policy_is_not_silently_enabled_in_stock_picard(self):
        api=Api()
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        self.assertFalse(api.plugin_config['native_move_auto'])
        self.assertEqual(api.plugin_config['native_recovery_root'],'')
        tool=plugin.NativeMoveSafetyToggle()
        tool.api=api
        tool.callback([])
        self.assertFalse(api.plugin_config['native_move_auto'])
        self.assertTrue(any(x[0]=='warn' for x in FakeMessageBox.messages))

    def test_patched_picard_core_can_register_disabled_native_policy(self):
        api=Api()
        registered=[]
        api.register_file_move_collision_processor=lambda fn,prepare:registered.append((fn,prepare))
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        self.assertEqual(registered,[(plugin._native_move_collision,plugin._native_move_prepare)])
        self.assertEqual(
            registered[0][0](api,'x.flac','y.flac',{},False,registered[0][1](api)),
            {'action':'UNHANDLED'})
        # No real music touched. Enabling the feature is a separate user
        # confirmation and version-specific runtime acceptance.
        self.assertFalse(api.plugin_config['native_move_auto'])

    def test_native_core_policy_opt_in_requires_separate_recovery(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            lib=root/'library'; recovery=root/'recovery'
            lib.mkdir(); recovery.mkdir()
            api=Api()
            callbacks=[]
            api.register_file_move_collision_processor=lambda fn,prepare:callbacks.append((fn,prepare))
            api.global_config.setting.update({
                'move_files':True,
                'move_files_to':str(lib),
                'move_overwrite_existing_files':False,
            })
            with patch.object(plugin,'AutoApplyController'),patch.object(plugin,'UniversalAggregator'):
                plugin.enable(api)
            self.assertEqual(callbacks,[(plugin._native_move_collision,plugin._native_move_prepare)])
            FakeFolderPicker.folder=str(recovery)
            FakeMessageBox.answer=FakeMessageBox.StandardButton.Yes
            action=plugin.NativeMoveSafetyToggle()
            action.api=api
            action.callback([])
            self.assertTrue(api.plugin_config['native_move_auto'])
            self.assertEqual(api.plugin_config['native_recovery_root'],str(recovery))
            from neowulf_picard_repair import native_move_bridge
            with patch.object(native_move_bridge,'arbitrate_native_flac_move',
                              return_value={'action':'KEEP'}) as bridge:
                out=callbacks[0][0](api,'staging.flac','library.flac',
                                    {'move_files':True},True,callbacks[0][1](api))
            self.assertEqual(out,{'action':'KEEP'})
            bridge.assert_called_once()
            self.assertEqual(bridge.call_args.kwargs['destination_loaded'],True)
            queued_policy = callbacks[0][1](api)
            self.assertEqual(queued_policy,(True,str(recovery)))
            action.callback([])
            self.assertFalse(api.plugin_config['native_move_auto'])
            self.assertEqual(callbacks[0][0](api,'a.flac','b.flac',{},False,
                                                  callbacks[0][1](api)),
                             {'action':'UNHANDLED'})
            # A save already queued with a GUI-thread immutable snapshot
            # cannot silently switch policy midworker if a user toggles it.
            with patch.object(native_move_bridge,'arbitrate_native_flac_move',
                              return_value={'action':'KEEP'}) as copied:
                self.assertEqual(callbacks[0][0](api,'a.flac','b.flac',{},
                                                  False,queued_policy),
                                 {'action':'KEEP'})
                copied.assert_called_once()

    def test_native_collision_opt_in_rejects_backup_nested_in_library(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            library=pathlib.Path(tmp)/'library'
            recovery=library/'recovery'
            recovery.mkdir(parents=True)
            api=Api()
            api.register_file_move_collision_processor=lambda fn,prepare:None
            api.global_config.setting.update({
                'move_files':True,
                'move_files_to':str(library),
                'move_overwrite_existing_files':False,
            })
            FakeFolderPicker.folder=str(recovery)
            FakeMessageBox.answer=FakeMessageBox.StandardButton.Yes
            action=plugin.NativeMoveSafetyToggle()
            action.api=api
            action.callback([])
            self.assertFalse(api.plugin_config.get('native_move_auto',False))
            self.assertTrue(any(kind=='warn' for kind,_ in FakeMessageBox.messages))

    def test_safe_import_file_action_dispatches_selected_files_and_tracker(self):
        api=Api()
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        actions=[item[1] for item in api.registered if item[0]=='file_action']
        matches=[cls for cls in actions if cls.TITLE.startswith(
            'PicardWulf: FLAC sicher in Musikbibliothek')]
        self.assertEqual(len(matches),1)
        action=matches[0]()
        action.api=api
        from neowulf_picard_repair import picard_safe_import
        files=[object()]
        with patch.object(picard_safe_import,'show_safe_import',return_value=True) as dispatched:
            action.callback(files)
        dispatched.assert_called_once_with(api,files,plugin._save_tracker)

    def test_context_menu_registers_album_and_cluster_multisource_action(self):
        api=Api()
        with patch.object(plugin,'AutoApplyController'), patch.object(plugin,'UniversalAggregator'):
            plugin.enable(api)
        contexts=[entry for entry in api.registered
                  if entry[0] in ('album_action','cluster_action')]
        self.assertEqual({entry[0] for entry in contexts},
                         {'album_action','cluster_action'})
        self.assertTrue(all('75 %' in entry[1].TITLE for entry in contexts))

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

    def test_production_snapshot_preserves_edition_and_fixed_decision(self):
        from types import SimpleNamespace
        fields={'title':'Mockingbird','artist':'Eminem','album':'Encore',
                'musicbrainz_albumid':'9f497f21-c32e-42cb-bc3f-7022f43d1b4d',
                'date':'2004','releasecountry':'DE','barcode':'123','releasecomment':'original',
                'tracknumber':'5','totaltracks':'16','discnumber':'2','totaldiscs':'2',
                '~length':250000,'~picardwulf_source':'deezer','~picardwulf_decision':'fixed'}
        file=SimpleNamespace(metadata=fields,orig_metadata=fields,filename='synthetic.flac')
        for snapshot in (plugin._file_snapshot(file),plugin._original_file_snapshot(file)):
            for key,value in fields.items():self.assertEqual(snapshot.get(key),value,key)

    def test_forced_conflict_reopens_review_using_production_snapshot(self):
        from collections import deque
        from types import SimpleNamespace
        import test_auto_selection as fixture
        file=fixture.DummyFile()
        q=fixture.Q
        first=fixture.agg.aggregate(q,{'deezer':[fixture.entry('deezer')]})
        later=fixture.agg.aggregate(q,{'spotify':[fixture.entry('spotify')]})
        with fixture.TestAutomaticWriting().with_fake_api():fixture.auto.apply_best_to_file(file,q,first)
        before=dict(file.metadata)
        controller=fixture.auto.AutoApplyController.__new__(fixture.auto.AutoApplyController)
        controller.stopped=False;controller._backup_wait=None;controller._refresh_iterator=None
        controller.watches={};controller.done=set();controller._round_robin=deque()
        controller.snapshot_func=plugin._file_snapshot
        controller.engine=SimpleNamespace(paused=False,schedule_async=lambda *a,**k:True)
        controller.api=SimpleNamespace(plugin_config={'auto_apply_best':True},logger=Logger())
        controller.io=SimpleNamespace(results={},invalidate=lambda key:None,read=lambda keys:None)
        controller.watch(file,plugin._file_snapshot(file),force=True)
        watch=next(iter(controller.watches.values()))
        controller.io.results[watch.key]={'payload':later}
        controller.poll()
        self.assertEqual(file.metadata['~picardwulf_review'],'LATER_RELEASE_CONFLICT')
        self.assertEqual({k:v for k,v in file.metadata.items() if k!='~picardwulf_review'},before)
if __name__=='__main__':unittest.main()
