import json
import unittest
from unittest import mock
import numpy as np
from tests.test_gui_schema_v4 import _workspace_tmp
from tests import test_inversion_feature_preview as fixtures


class ResultServiceTests(unittest.TestCase):
    def test_gui_runs_all_run_view_buttons_in_background_and_caches(self):
        import sys,time
        from rotation_gui.qt_compat import QApplication,QPushButton
        from rotation_gui.window.main import PipelineWindow
        from rotation_gui import storage
        app=QApplication.instance() or QApplication([])
        with _workspace_tmp('gui_run_views') as scratch,mock.patch.object(storage,'STATE_PATH',scratch/'session.json'),mock.patch.object(storage,'PREVIEW_DIR',scratch/'previews'),mock.patch('rotation_gui.window.inversion_feature_preview.open_echo_preview_in_browser') as opened:
            window=PipelineWindow();window.python_edit.setText(sys.executable)
            window.runs_dir_edit.setText(str(scratch));window.run_name_edit.setText('experiment')
            fixtures.InversionFeaturePreviewTests().write_echo(window._run_directory()/'echo/echo.npz')
            window.config_data['inversion']['cpi_duration_s']=1.
            fixtures.write_completed_fixture(window._run_directory()/'echo/echo.npz',window.config_data['inversion'],with_inspections=True)
            window._sync_current_stage=mock.Mock()
            window.show();app.processEvents()
            for label in ('原始回波','脉冲压缩','距离—多普勒'):
                panel=window._build_result_dialog()
                actions={b.text():b for b in panel.findChildren(QPushButton)}
                actions[label].click()
                self.assertIsNotNone(window.feature_preview_process)
                deadline=time.monotonic()+15;events=0
                while window.feature_preview_process is not None and time.monotonic()<deadline:
                    app.processEvents();events+=1;time.sleep(.01)
                self.assertIsNone(window.feature_preview_process)
                self.assertGreater(events,0)
                self.assertTrue(opened.call_args.args[0].is_file())
                actions[label].click()
                self.assertIsNone(window.feature_preview_process)
                panel.deleteLater()
            self.assertEqual(opened.call_count,6)
            window._open_result_dialog();app.processEvents()
            window.grab().save(str(scratch/'window.png'))
            window._result_popup.grab().save(str(scratch/'popup.png'))
            window.close()

    def test_saved_view_needs_no_echo(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('saved_without_iq') as scratch:
            source=scratch/'echo/echo.npz'
            folder=scratch/'inversion';folder.mkdir()
            np.savez(folder/'period_observables.npz',time_elapsed_s=[0.,1.],value=[[1.],[2.]],feature_names=['total_power'],run_id=[0,0],metadata_json=np.array('{}'))
            with mock.patch('rotation_gui.window.inversion_feature_preview._load_echo',side_effect=AssertionError('IQ loaded')):
                service.build_view(source,{},folder/'features.html',kind='saved')
            self.assertTrue((folder/'features.html').is_file())
    def test_reader_sparse_rows_zip_modes_and_budget(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('row_modes') as scratch:
            values=np.arange(60,dtype=np.complex64).reshape(10,6)
            for save in (np.savez,np.savez_compressed):
                path=scratch/'data.npz';save(path,iq=values)
                np.testing.assert_array_equal(service.read_rows(path,'iq',[1,4,9]),values[[1,4,9]])
                with mock.patch.object(service,'RUN_BYTES',1),self.assertRaisesRegex(ValueError,'预算'):
                    service.read_rows(path,'iq',[1])
            np.savez(path,iq=np.asfortranarray(values))
            with self.assertRaisesRegex(ValueError,'Fortran'):
                service.read_rows(path,'iq',[1])

    def test_offset_validation_precedes_run_slice(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('offset_contract') as scratch:
            path=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(path)
            with np.load(path) as data: values={key:data[key] for key in data.files}
            values['run_id']=np.repeat([0,1],40)
            values['row_fast_time_offset_s']=np.r_[np.zeros(40),np.full(40,np.nan)]
            np.savez(path,**values)
            with self.assertRaisesRegex(ValueError,'row_fast_time_offset'):
                service.load_run(path,0)

    def test_compression_matches_unmodified_core_and_its_cache_is_reused(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('shared_compression') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo,indices=service.load_run(source,0)
            config={'motion_compensation':'none','cpi_duration_s':.4,'cpi_hop_duration_s':.1}
            core=service._inversion_module()
            prepared=core.prepare_chirp_pulse_profiles(echo,config,pulse_features_only=True)
            lag=prepared['full_compressed'].shape[1]-echo.iq.shape[1]
            expected=prepared['full_compressed'][:,lag:lag+echo.iq.shape[1]]
            cache=scratch/'compression_run_0.npz'
            actual=service.compression_cache(source,config,cache,0,echo)
            np.testing.assert_array_equal(actual,expected)
            self.assertGreater(np.max(np.abs(expected)),0)
            with mock.patch.object(core,'prepare_chirp_pulse_profiles',side_effect=AssertionError('cache ignored')):
                service.compression_cache(source,config,cache,0,echo)
            with mock.patch.object(service,'compressed_run',side_effect=AssertionError('bad hit')):
                service.compression_cache(source,config,cache,0,echo)
                with self.assertRaisesRegex(AssertionError,'bad hit'):
                    service.compression_cache(source,dict(config,motion_compensation='auto'),cache,0,echo)

    def test_rd_never_joins_original_row_gaps_or_invalid_pulses(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('rd_seams') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo,indices=service.load_run(source,0)
            config={'cpi_duration_s':7.0}
            from radar_signal import align_profiles_to_common_delay
            with mock.patch('radar_signal.align_profiles_to_common_delay',wraps=align_profiles_to_common_delay) as alignment:
                service.rd_figure(echo,indices,config,0,0)
                self.assertEqual(alignment.call_args.kwargs['method'],'fourier')
            # 80 pulses can form a 70-pulse CPI only if the seam is ignored.
            discontinuous=np.r_[np.arange(40),np.arange(80,120)]
            with self.assertRaisesRegex(ValueError,'不足'):
                service.rd_figure(echo,discontinuous,config,0,0)
            echo.valid[40]=False
            with self.assertRaisesRegex(ValueError,'不足'):
                service.rd_figure(echo,indices,config,0,0)

    def test_raw_roi_keeps_full_record_and_publication_failure_keeps_previous(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('view_atomic') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo,_=service.load_run(source,0)
            fig=service.matrix_figure(echo,echo.iq,'raw',0,{})
            self.assertEqual(len(fig.data[0].x),echo.iq.shape[1])
            self.assertTrue(fig.layout.updatemenus[0].buttons[1].args[0]['xaxis.autorange'])
            echo.valid[0]=False
            missing=service.matrix_figure(echo,echo.iq,'raw',0,{})
            self.assertTrue(np.all(np.isnan(np.asarray(missing.data[0].z)[0])))
            path=scratch/'raw.html';path.write_text('previous',encoding='utf-8')
            def fail(*args,**kwargs):raise OSError('write failed')
            with mock.patch('plotly.graph_objects.Figure.write_html',fail),self.assertRaises(OSError):
                service.build_view(source,{},path,kind='raw')
            self.assertEqual(path.read_text(encoding='utf-8'),'previous')
            self.assertFalse(path.with_suffix('.view.json').exists())

    def test_selected_run_reader_never_materializes_campaign_iq(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('run_reader') as scratch:
            path=scratch/'echo.npz'
            fixtures.InversionFeaturePreviewTests().write_echo(path)
            with np.load(path) as data:
                values={key:data[key] for key in data.files}
            values['run_id']=np.repeat([4,9],40)
            np.savez_compressed(path,**values)
            original=np.lib.npyio.NpzFile.__getitem__
            def guarded(data,key):
                if key in ('iq','clean_iq','valid'):
                    raise AssertionError('large array materialized')
                return original(data,key)
            with mock.patch.object(np.lib.npyio.NpzFile,'__getitem__',guarded):
                echo, indices=service.load_run(path,9)
            np.testing.assert_array_equal(echo.iq,values['iq'][40:])
            np.testing.assert_array_equal(indices,np.arange(40,80))

    def test_raw_view_never_calls_matched_filter(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('raw_service') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            with mock.patch.object(service,'compressed_run',side_effect=AssertionError('raw triggered MF')):
                result=service.build_view(source,{},scratch/'raw.html',kind='raw',run_id=0)
            self.assertTrue(result.is_file())
