import json
import unittest
import time
from unittest import mock
import numpy as np
from tests.test_gui_schema_v4 import _workspace_tmp
from rotation_gui import storage
from rotation_gui.qt_compat import QApplication
from rotation_gui.window.main import PipelineWindow


class SavedResultViewsTests(unittest.TestCase):
    def test_cli_view_race_cannot_certify_old_html_with_new_stat(self):
        from inversion.src.result_views import publish_saved_features
        with _workspace_tmp('cli_feature_race') as scratch:
            source, echo, html = scratch / 'observables.npz', scratch / 'echo.npz', scratch / 'features.html'
            echo.write_bytes(b'original echo')
            np.savez(source, time_elapsed_s=[0., 1.], value=[[1.], [2.]], feature_names=['total_power'],
                run_id=[0, 0], metadata_json=np.array('{}'))
            html.write_text('previous', encoding='utf-8')
            def changed(figure, pending, **kwargs):
                from pathlib import Path
                Path(pending).write_text('new', encoding='utf-8')
                echo.write_bytes(b'changed echo during rendering')
            with mock.patch('plotly.graph_objects.Figure.write_html', changed):
                with self.assertRaisesRegex(ValueError, '源文件发生变化'):
                    publish_saved_features(source, {}, html, echo)
            self.assertEqual(html.read_text(encoding='utf-8'), 'previous')
            self.assertFalse(html.with_suffix('.view.json').exists())

    def test_result_menu_opens_saved_artifacts_without_computation(self):
        from rotation_gui.window import inversion_feature_preview as preview
        QApplication.instance() or QApplication([])
        with _workspace_tmp('result_menu') as scratch, \
             mock.patch.object(storage, 'STATE_PATH', scratch / 'session.json'), \
             mock.patch.object(preview, 'open_echo_preview_in_browser') as opened, \
             mock.patch('rotation_gui.window.main.QMessageBox.information') as missing:
            window = PipelineWindow()
            window.runs_dir_edit.setText(str(scratch))
            window.run_name_edit.setText('experiment')
            folder = window._run_directory() / 'inversion'
            folder.mkdir(parents=True)
            for filename in ('processing.html', 'periodogram.html'):
                (folder / filename).write_text('saved', encoding='utf-8')
            np.savez(folder/'period_observables.npz',time_elapsed_s=[0.,1.],value=[[1.],[2.]],feature_names=['total_power'],run_id=[0,0],metadata_json=np.array('{}'))
            (folder/'best_summary.json').write_text('{}',encoding='utf-8')
            panel = window._build_result_dialog()
            from rotation_gui.qt_compat import QPushButton
            actions = {b.text(): b for b in panel.findChildren(QPushButton)}
            window._open_inversion_artifact('processing.html')
            self.assertEqual(opened.call_args.args[0], folder / 'processing.html')
            actions['周期搜索'].click()
            self.assertEqual(opened.call_args.args[0], folder / 'periodogram.html')
            (folder / 'processing.html').unlink()
            window._open_inversion_artifact('processing.html')
            missing.assert_called_once()
            self.assertIsNone(window.feature_preview_process)
            window.close()

    def test_saved_three_five_and_cw_columns_are_exact(self):
        from inversion.src.result_views import saved_feature_figure
        with _workspace_tmp('feature_columns') as scratch:
            for names in (['total_power', 'centroid_delay_s', 'energy_width_90_s'],
                ['total_power', 'doppler_centroid_hz', 'rms_bandwidth_hz', 'range_centroid_s', 'energy_range_width_90_s'],
                ['total_power', 'centroid_hz', 'rms_bandwidth_hz']):
                values = np.arange(4 * len(names)).reshape(4, len(names))
                path = scratch / 'features.npz'
                np.savez(path, time_elapsed_s=np.arange(4), value=values, feature_names=names,
                    run_id=[0, 0, 1, 1], metadata_json=np.array(json.dumps({'inversion_config': {'x': 1}})))
                figure = saved_feature_figure(path, current_config={'x': 2})
                self.assertIn('参数已修改', figure.layout.title.text)
                self.assertEqual(len(figure.data), len(names))
                for column, trace in enumerate(figure.data):
                    np.testing.assert_array_equal(trace.y, values[:, column])

    def test_processing_saves_true_frame_axes_and_fallback_has_no_rd(self):
        from inversion.src.result_views import save_processing_view
        from inversion.src.radar_signal import RangeDopplerCube, RangeProfiles
        from types import SimpleNamespace
        with _workspace_tmp('processing_views') as scratch:
            spectrum = np.arange(36).reshape(3, 4, 3).astype(complex)
            axes = np.array([[-1., 0, 1], [-2., 0, 2], [-3., 0, 3]])
            dynamic = RangeDopplerCube(np.arange(3), np.arange(4), axes[0], spectrum,
                np.zeros(3), np.arange(3), np.arange(3) + 2, frame_frequencies_hz=axes)
            save_processing_view(SimpleNamespace(dynamic_spectrum=dynamic, search_diagnostics={}), scratch)
            with np.load(scratch / 'processing_preview.npz') as data:
                np.testing.assert_array_equal(data['rd_frequencies_hz'], axes)
                np.testing.assert_array_equal(data['rd_power'], np.abs(spectrum)**2)
            dynamic = RangeProfiles(np.arange(3), np.arange(4), np.ones((3, 4), complex))
            save_processing_view(SimpleNamespace(dynamic_spectrum=dynamic, search_diagnostics={}), scratch)
            with np.load(scratch / 'processing_preview.npz') as data:
                self.assertNotIn('rd_power', data.files)
            self.assertTrue(json.dumps('没有慢时间 FFT')[1:-1] in (scratch / 'processing.html').read_text(encoding='utf-8'))

    def test_pulse_cache_ignores_cpi_but_invalidates_compensation_and_source(self):
        from rotation_gui.window import inversion_feature_preview as preview
        from tests.test_inversion_feature_preview import InversionFeaturePreviewTests
        with _workspace_tmp('pulse_view_cache') as scratch:
            source, path = scratch / 'echo.npz', scratch / 'features.html'
            InversionFeaturePreviewTests().write_echo(source)
            config = {'motion_compensation': 'auto', 'cpi_duration_s': 1.}
            preview.build_inversion_feature_html(source, config, path)
            with mock.patch.object(preview, '_load_echo', side_effect=AssertionError('cache recomputed')):
                preview.build_inversion_feature_html(source, {**config, 'cpi_duration_s': 10.}, path)
            self.assertFalse(preview.cached_feature_html(source, {**config, 'motion_compensation': 'none'}, path))
            source.write_bytes(b'changed')
            self.assertFalse(preview.cached_feature_html(source, config, path))

    def test_source_change_during_render_preserves_previous_html(self):
        from rotation_gui.window import inversion_feature_preview as preview
        from tests.test_inversion_feature_preview import InversionFeaturePreviewTests
        with _workspace_tmp('feature_race') as scratch:
            source, path = scratch / 'echo.npz', scratch / 'features.html'
            InversionFeaturePreviewTests().write_echo(source)
            path.write_text('previous', encoding='utf-8')
            def change_source(figure, pending, **kwargs):
                from pathlib import Path
                Path(pending).write_text('new', encoding='utf-8')
                source.write_bytes(b'changed during render')
            with mock.patch('plotly.graph_objects.Figure.write_html', change_source):
                with self.assertRaisesRegex(ValueError, '源文件发生变化'):
                    preview.build_inversion_feature_html(source, {}, path)
            self.assertEqual(path.read_text(encoding='utf-8'), 'previous')

    def test_completed_inversion_preview_never_loads_iq(self):
        from rotation_gui.window import inversion_feature_preview as preview
        QApplication.instance() or QApplication([])
        with _workspace_tmp('saved_features') as scratch:
            run = scratch / 'experiment'
            (run / 'echo').mkdir(parents=True)
            (run / 'echo/echo.npz').write_bytes(b'IQ must not be read')
            (run / 'inversion').mkdir()
            (run/'inversion/best_summary.json').write_text('{}',encoding='utf-8')
            (run/'inversion/periodogram.html').write_text('saved',encoding='utf-8')
            np.savez(run / 'inversion/period_observables.npz', time_elapsed_s=[0., 1.],
                value=np.array([[1., 2., 3.], [2., 4., 6.]]),
                feature_names=['total_power', 'centroid_delay_s', 'energy_width_90_s'],
                run_id=[0, 0], metadata_json=np.array(json.dumps({'time_axis_role': 'scatter_elapsed_s'})))
            with mock.patch.object(storage, 'STATE_PATH', scratch / 'session.json'), \
                 mock.patch.object(preview, '_load_echo', side_effect=AssertionError('IQ loaded')), \
                 mock.patch.object(preview, 'open_echo_preview_in_browser'):
                window = PipelineWindow()
                window.runs_dir_edit.setText(str(scratch))
                window.run_name_edit.setText('experiment')
                window._open_feature_preview()
                deadline = time.monotonic() + 15
                while window.feature_preview_process is not None and time.monotonic() < deadline:
                    QApplication.processEvents()
                    time.sleep(.01)
                self.assertTrue((run / 'inversion/features.html').is_file())
                self.assertIsNone(window.feature_preview_process)
                with mock.patch.object(window, '_read_feature_preview_output'):
                    window._open_feature_preview()
                    self.assertIsNone(window.feature_preview_process)
                window.close()
