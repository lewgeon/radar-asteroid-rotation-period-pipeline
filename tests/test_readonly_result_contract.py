"""Scientific computation belongs to execution, never to saved-result browsing."""
import json
import subprocess
import sys
import unittest
from unittest import mock
import numpy as np
from tests.test_gui_schema_v4 import _workspace_tmp
from tests import test_inversion_feature_preview as fixtures
from rotation_gui.window import result_service as service
from rotation_gui.window.inversion_feature_preview import _load_echo, _inversion_module


class ReadonlyResultContractTests(unittest.TestCase):
    def test_gui_only_raw_enabled_before_inversion(self):
        from rotation_gui import storage
        from rotation_gui.qt_compat import QApplication
        from rotation_gui.window.main import PipelineWindow
        QApplication.instance() or QApplication([])
        with _workspace_tmp('readonly_gui') as scratch, mock.patch.object(storage,'STATE_PATH',scratch/'session.json'):
            source=scratch/'experiment/echo/echo.npz';source.parent.mkdir(parents=True)
            fixtures.InversionFeaturePreviewTests().write_echo(source)
            window=PipelineWindow();window.runs_dir_edit.setText(str(scratch));window.run_name_edit.setText('experiment')
            try:
                window._build_result_dialog()
                self.assertTrue(window._result_actions['原始回波'].isEnabled())
                for label in ('脉冲压缩','逐脉冲检查','实际反演特征','距离—多普勒','周期搜索','误差诊断'):
                    self.assertFalse(window._result_actions[label].isEnabled(),label)
            finally:window.close()

    def fixture(self, scratch, inspections=False):
        source=scratch/'experiment/echo/echo.npz'
        source.parent.mkdir(parents=True)
        fixtures.InversionFeaturePreviewTests().write_echo(source)
        fixtures.write_completed_fixture(source,config={'cpi_duration_s':1.},with_inspections=inspections)
        return source

    def test_echo_alone_does_not_enable_or_compute_inversion_views(self):
        with _workspace_tmp('readonly_echo') as scratch:
            source=scratch/'experiment/echo/echo.npz';source.parent.mkdir(parents=True)
            fixtures.InversionFeaturePreviewTests().write_echo(source)
            with mock.patch.object(service,'scientific_features',side_effect=AssertionError('compute')), mock.patch.object(service,'scientific_rd',side_effect=AssertionError('compute')):
                for kind in ('pulse','saved','compression','rd','period'):
                    self.assertFalse(service.saved_view_available(source,kind))
                for kind in ('pulse','saved','compression','rd','scientific_features'):
                    with self.assertRaisesRegex(ValueError,'先运行周期反演'):
                        service.build_view(source,{},scratch/'view.html',kind=kind,read_only=True)

    def test_uncertainty_view_requires_completed_enabled_saved_report(self):
        with _workspace_tmp('uncertainty_readonly') as scratch:
            source=self.fixture(scratch)
            folder=service.completed_inversion(source)['folder']
            self.assertFalse(service.saved_view_available(source,'uncertainty'))
            (folder/'period_uncertainty.html').write_text('<p>saved</p>',encoding='utf-8')
            for enabled in (False,True):
                (folder/'period_uncertainty.json').write_text(json.dumps(dict(enabled=enabled)),encoding='utf-8')
                self.assertEqual(service.saved_view_available(source,'uncertainty'),enabled)
            (folder/'inversion_in_progress.json').write_text('{}',encoding='utf-8')
            self.assertFalse(service.saved_view_available(source,'uncertainty'))

    def test_selection_view_requires_matching_json_and_html_identities(self):
        with _workspace_tmp('selection_identity') as scratch:
            source=self.fixture(scratch)
            folder=service.completed_inversion(source)['folder']
            report=folder/'period_selection.json'
            html=folder/'period_selection.html'
            report.write_text('{"period_s":20}',encoding='utf-8')
            html.write_text('<p>saved selection</p>',encoding='utf-8')
            marker=folder/'inversion_complete.json'
            stamp=dict(observables=service._views().file_identity(folder/'period_observables.npz'))
            marker.write_text(json.dumps(stamp),encoding='utf-8')
            # Legacy completion without identities must not certify stray reports.
            self.assertFalse(service.saved_view_available(source,'selection'))
            def certify():
                stamp.update(selection_report_identity=service._views().file_identity(report),
                             selection_html_identity=service._views().file_identity(html))
                marker.write_text(json.dumps(stamp),encoding='utf-8')
            certify()
            self.assertTrue(service.saved_view_available(source,'selection'))
            report.write_text('{"period_s":200}',encoding='utf-8')
            self.assertFalse(service.saved_view_available(source,'selection'))
            certify()
            self.assertTrue(service.saved_view_available(source,'selection'))
            html.write_text('<p>changed saved selection</p>',encoding='utf-8')
            self.assertFalse(service.saved_view_available(source,'selection'))
            certify()
            self.assertTrue(service.saved_view_available(source,'selection'))

    def test_reading_saved_inspections_never_loads_or_processes_iq(self):
        with _workspace_tmp('readonly_saved') as scratch:
            source=self.fixture(scratch,True)
            core=_inversion_module()
            with mock.patch.object(core,'prepare_chirp_pulse_profiles',side_effect=AssertionError('MF')), mock.patch.object(service,'load_run',side_effect=AssertionError('IQ')):
                for kind in ('pulse','compression','saved'):
                    self.assertTrue(service.saved_view_available(source,kind))
                    path=scratch/f'{kind}.html'
                    service.build_view(source,{'cpi_duration_s':999},path,kind=kind,run_id=-1,read_only=True)
                    self.assertTrue(path.is_file())
            folder=service.completed_inversion(source)['folder']
            (folder/'inversion_in_progress.json').write_text('{}',encoding='utf-8')
            self.assertIsNone(service.completed_inversion(source))

    def test_inspection_identity_and_pulse_values(self):
        with _workspace_tmp('inspection_identity') as scratch:
            source=self.fixture(scratch,True)
            from inspection_store import ready_inspection,write_inspections
            echo=_load_echo(source);core=_inversion_module()
            expected=core.streamed_chirp_pulse_features(echo,{},3)[0]
            folder=ready_inspection(source,{})
            with np.load(folder/'pulse_observables.npz') as data:
                np.testing.assert_array_equal(data['value'],np.column_stack([expected.total_power,expected.centroid_delay_s,expected.energy_width_90_s]))
                self.assertGreater(np.ptp(data['value'][:,0]),0)
            (folder/'compression_campaign.npz').write_bytes(b'broken')
            self.assertIsNone(ready_inspection(source,{}))
            self.assertEqual(write_inspections(echo,source,{}),folder)
            self.assertIsNotNone(ready_inspection(source,{}))
            (folder/'manifest.json').write_text('null',encoding='utf-8')
            self.assertIsNone(ready_inspection(source,{}))
            # Direct mappings own the source on Windows until explicitly closed.
            echo.close()
            source.write_bytes(b'replaced')
            with self.assertRaisesRegex(ValueError,'身份不匹配'):
                write_inspections(echo,source,{})
            self.assertFalse(service.saved_view_available(source,'pulse'))

    def test_completion_stamp_and_missing_rd_are_not_certified(self):
        with _workspace_tmp('completion_identity') as scratch:
            source=self.fixture(scratch)
            context=service.completed_inversion(source)
            self.assertEqual(context['observations'],2)
            self.assertFalse(service.saved_view_available(source,'rd'))
            folder=context['folder'];observables=folder/'period_observables.npz'
            (folder/'inversion_complete.json').write_text(json.dumps({'observables':service._views().file_identity(observables)}),encoding='utf-8')
            self.assertIsNotNone(service.completed_inversion(source))
            (folder/'inversion_complete.json').write_text('[]',encoding='utf-8')
            self.assertIsNone(service.completed_inversion(source))
            (folder/'inversion_complete.json').write_text(json.dumps({'observables':service._views().file_identity(observables)}),encoding='utf-8')
            observables.write_bytes(b'changed')
            self.assertIsNone(service.completed_inversion(source))

    def test_worker_default_is_read_only(self):
        with _workspace_tmp('readonly_cli') as scratch:
            source=self.fixture(scratch)
            result=subprocess.run([sys.executable,'-m','rotation_gui.window.result_service','--echo',str(source),'--config-json','{}','--output',str(scratch/'view.html'),'--kind','scientific_features'],capture_output=True,timeout=30)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse((scratch/'view.html').exists())

    def test_interleaved_runs_and_invalid_pulse_preserve_native_features(self):
        with _workspace_tmp('inspection_interleaved') as scratch:
            source=scratch/'echo.npz'
            fixtures.InversionFeaturePreviewTests().write_echo(source)
            with np.load(source,allow_pickle=False) as data:payload={name:data[name] for name in data.files}
            payload['run_id']=np.arange(len(payload['iq']))%3
            payload['valid']=payload['valid'].copy();payload['valid'][0]=False
            np.savez(source,**payload)
            echo=_load_echo(source);core=_inversion_module()
            expected,_,runs=core.streamed_chirp_pulse_features(echo,{},3)
            from inspection_store import write_inspections
            folder=write_inspections(echo,source,{})
            with np.load(folder/'pulse_observables.npz') as data:
                np.testing.assert_array_equal(data['run_id'],runs)
                np.testing.assert_array_equal(data['value'],np.column_stack([expected.total_power,expected.centroid_delay_s,expected.energy_width_90_s]))
                self.assertTrue(np.isnan(data['value'][0,2]))
            for run in range(3):self.assertTrue((folder/f'compression_run_{run}.npz').is_file())

    def test_saved_rd_reads_valid_frame_without_processing(self):
        from types import SimpleNamespace
        with _workspace_tmp('readonly_rd') as scratch:
            source=scratch/'experiment/echo/echo.npz';source.parent.mkdir(parents=True)
            fixtures.InversionFeaturePreviewTests().write_echo(source)
            config={'cpi_duration_s':1.6,'cpi_hop_duration_s':.4}
            fixtures.write_completed_fixture(source,config=config,with_inspections=True)
            from processing_store import identity,cpi_folder
            token=SimpleNamespace(_source_identity=identity(source),_processing_store=source.parent/'processing_cache')
            indices=[i for i,_ in service.cpi_catalog(source,config,-1) if i>=0]
            self.assertGreater(len(indices),1)
            first=cpi_folder(token,config)/f'{indices[0]}.npz';first.unlink()
            self.assertFalse(service.saved_view_available(source,'rd',-1,indices[0]))
            self.assertTrue(service.saved_view_available(source,'rd',-1,-1))
            core=_inversion_module()
            with mock.patch.object(core,'prepare_chirp_observations',side_effect=AssertionError('compute')), mock.patch.object(service,'scientific_rd',side_effect=AssertionError('FFT')):
                service.build_view(source,{},scratch/'rd.html',kind='rd',run_id=-1,cpi_index=-1,read_only=True)
            self.assertTrue((scratch/'rd.html').is_file())
            observations=source.parent/'processing_cache/observations.npz'
            with np.load(observations) as data:payload={name:data[name] for name in data.files}
            payload['manifest']=np.array('null');np.savez(observations,**payload)
            self.assertFalse(service.saved_view_available(source,'rd'))


if __name__=='__main__':unittest.main()
