"""Per-pulse feature preview matches the chirp fallback observables."""

import unittest
import json
import sys
import time
from unittest import mock

import numpy as np

import pipeline

from inversion.tests.test_chirp_contracts import chirp_echo
from rotation_gui import storage
from rotation_gui.qt_compat import QApplication, QTimer
from rotation_gui.widgets.attention_button import AttentionButton
from rotation_gui.window.inversion_feature_preview import build_inversion_feature_figure, build_inversion_feature_html
from rotation_gui.window.main import PipelineWindow
from tests.test_gui_schema_v4 import _workspace_tmp


def write_completed_fixture(echo_path,config=None,with_inspections=False):
    import json
    from inversion.src.result_views import file_identity
    folder=echo_path.parent.parent/'inversion';folder.mkdir(parents=True,exist_ok=True)
    cfg=dict(config or {})
    np.savez(folder/'period_observables.npz',time_elapsed_s=[0.,1.],value=[[1.,2.,3.],[2.,4.,6.]],
        feature_names=['total_power','centroid_delay_s','energy_width_90_s'],run_id=[0,0],
        metadata_json=np.array(json.dumps(dict(inversion_config=cfg,time_axis_role='scatter_elapsed_s',
            echo_identity=file_identity(echo_path),search_diagnostics=dict(processing_path='cpi')))))
    (folder/'best_summary.json').write_text('{}',encoding='utf-8')
    (folder/'periodogram.html').write_text('saved',encoding='utf-8')
    if with_inspections:
        from rotation_gui.window.inversion_feature_preview import _load_echo,_inversion_module
        echo=_load_echo(echo_path);core=_inversion_module()
        core.prepare_chirp_observations(echo,cfg)
        from inspection_store import write_inspections
        write_inspections(echo,echo_path,cfg)


class InversionFeaturePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def write_echo(self, path):
        echo = chirp_echo('centroid_compensated')
        data = {key: value for key, value in vars(echo).items() if key != 'metadata'}
        n = len(echo.iq)
        data.update(clean_iq=echo.iq, emit_elapsed_s=echo.scatter_elapsed_s,
                    tx_los_icrs=np.zeros((n, 3)), rx_los_icrs=np.zeros((n, 3)),
                    metadata_json=np.array(json.dumps(echo.metadata)))
        for name in ('acquisition_id', 'track_id', 'row_start_sample', 'rx_adc_start_elapsed_s',
                     'rx_adc_stop_elapsed_s', 'signal_echo_overlap', 'window_overlap',
                     'common_path_rate_m_s'):
            data[name] = np.zeros(n)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, **data)

    def wait_preview(self, window):
        deadline = time.monotonic() + 15
        while window.feature_preview_process is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(window.feature_preview_process)

    def test_html_write_failure_preserves_previous_result(self):
        with _workspace_tmp('feature_atomic') as scratch:
            echo_path = scratch / 'echo.npz'
            self.write_echo(echo_path)
            html_path = scratch / 'features.html'
            html_path.write_text('previous', encoding='utf-8')
            def partial_write(figure, path, **kwargs):
                from pathlib import Path
                Path(path).write_text('partial', encoding='utf-8')
                raise OSError('write failed')
            with mock.patch('plotly.graph_objects.Figure.write_html', partial_write):
                with self.assertRaisesRegex(OSError, 'write failed'):
                    build_inversion_feature_html(echo_path, {}, html_path)
            self.assertEqual(html_path.read_text(encoding='utf-8'), 'previous')
            self.assertFalse(html_path.with_suffix('.html.part').exists())

    def test_gui_child_success_error_cancel_and_start_failure(self):
        with _workspace_tmp('feature_child') as scratch:
            with mock.patch.object(storage, 'STATE_PATH', scratch / 'session.json'), \
                 mock.patch.object(storage, 'PREVIEW_DIR', scratch / 'previews'), \
                 mock.patch('rotation_gui.window.inversion_feature_preview.open_echo_preview_in_browser') as opened, \
                 mock.patch('rotation_gui.window.main.QMessageBox.critical') as critical:
                window = PipelineWindow()
                window.show()
                try:
                    window.python_edit.setText(sys.executable)
                    window.runs_dir_edit.setText(str(scratch / 'runs'))
                    window.run_name_edit.setText('case')
                    echo_path = window._run_directory() / 'echo' / 'echo.npz'
                    self.write_echo(echo_path)
                    write_completed_fixture(echo_path,window.config_data['inversion'])
                    timer = QTimer(window)
                    ticks = []
                    timer.timeout.connect(lambda: ticks.append(True))
                    timer.start(10)
                    window._open_feature_preview()
                    self.assertIsNotNone(window.feature_preview_process)
                    self.assertFalse(window.feature_preview_btn.isEnabled())
                    self.assertFalse(window.run_btn.isEnabled())
                    self.assertTrue(window.stop_btn.isEnabled())
                    process = window.feature_preview_process
                    identity = window._feature_preview_identity
                    window._open_feature_preview()
                    self.assertIs(window.feature_preview_process, process)
                    # Changing selection must not relabel the result of the running job.
                    window.run_name_edit.setText('other_case')
                    self.wait_preview(window)
                    timer.stop()
                    self.assertGreater(len(ticks), 2)  # GUI event loop stayed alive.
                    opened.assert_called_once()
                    critical.assert_not_called()
                    self.assertEqual(window.progress.value(), 100)
                    self.assertIn('case',window._feature_preview_path.parts)
                    self.assertIn(identity, window._opened_previews['features'])
                    window.run_name_edit.setText('case')
                    result = window._feature_preview_path.read_bytes()
                    self.assertTrue(window.run_btn.isEnabled())
                    # Cancel a real running child; previous HTML must remain intact.
                    # A repeated click now reuses HTML. Invalidate only its view stamp
                    # to exercise the actual child cancellation branch.
                    window._feature_preview_path.with_suffix('.view.json').unlink()
                    window._open_feature_preview()
                    self.assertTrue(window.feature_preview_process.waitForStarted(3000))
                    window.stop_btn.click()
                    self.wait_preview(window)
                    self.assertIn('已中止', window.progress.format())
                    self.assertEqual(window._feature_preview_path.read_bytes(), result)
                    self.assertEqual(opened.call_count, 1)
                    # Invalid artifact must report failure rather than open stale HTML.
                    observables=window._run_directory()/'inversion/period_observables.npz'
                    with np.load(observables) as data:bad={key:data[key] for key in data.files}
                    bad['value']=np.ones((2,1))
                    np.savez(observables,**bad)
                    window._open_feature_preview()
                    self.wait_preview(window)
                    self.assertEqual(critical.call_count, 1)
                    self.assertEqual(opened.call_count, 1)
                    self.assertEqual(window._feature_preview_path.read_bytes(), result)
                    # FailedToStart does not emit finished: verify explicit cleanup.
                    window.python_edit.setText(str(scratch / 'missing_python.exe'))
                    window._open_feature_preview()
                    self.wait_preview(window)
                    self.assertEqual(critical.call_count, 2)
                    self.assertTrue(window.run_btn.isEnabled())
                    self.assertFalse(window.stop_btn.isEnabled())
                    self.write_echo(echo_path)
                    window.python_edit.setText(sys.executable)
                    window._open_feature_preview()
                    self.assertTrue(window.feature_preview_process.waitForStarted(3000))
                    window.close()
                    self.assertIsNone(window.feature_preview_process)
                    self.assertEqual(opened.call_count, 1)
                    self.assertEqual(critical.call_count, 2)
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()

    def test_figure_plots_each_pulse_feature_on_the_search_clock(self):
        echo = chirp_echo("centroid_compensated")
        figure = build_inversion_feature_figure(
            echo, {"period_time_role": "scatter_centroid", "motion_compensation": "auto"}
        )
        self.assertEqual(len(figure.data), 3)
        times = np.asarray(echo.scatter_elapsed_s, dtype=float)
        for trace in figure.data:
            self.assertTrue(np.allclose(trace.x, times))
        amplitude = 1.5 + 0.5 * np.sin(2 * np.pi * times / 2.0)
        power = np.asarray(figure.data[0].y, dtype=float)
        self.assertGreater(float(np.corrcoef(power, amplitude**2)[0, 1]), 0.9)
        self.assertEqual(figure.layout.xaxis3.title.text, "散射时刻（相对观测起点，s）")
        self.assertEqual(figure.data[2].name, "距离 90% 能量宽度")

    def test_preview_streams_features_through_a_bounded_pulse_chunk(self):
        from rotation_gui.window import inversion_feature_preview as preview

        echo = chirp_echo("centroid_compensated")
        module = preview._inversion_module()
        real_stream = module.streamed_chirp_pulse_features
        seen = {}

        def spy(echo_arg, config, chunk_size):
            seen["chunk_size"] = chunk_size
            seen["echo_is_argument"] = echo_arg is echo
            return real_stream(echo_arg, config, chunk_size)

        with mock.patch.object(module, "bounded_pulse_chunk_size", return_value=7) as picker:
            with mock.patch.object(module, "streamed_chirp_pulse_features", side_effect=spy) as streamer:
                figure = build_inversion_feature_figure(echo, {"motion_compensation": "auto"})
        self.assertEqual(len(figure.data), 3)
        picker.assert_called_once()
        self.assertEqual(picker.call_args[0][0], echo)
        self.assertEqual(picker.call_args[0][1], preview._FEATURE_WORKSPACE_BUDGET_BYTES)
        # 预算本身必须有界：改成 GB 级就失去了这次修复的意义。
        self.assertGreater(preview._FEATURE_WORKSPACE_BUDGET_BYTES, 0)
        self.assertLessEqual(preview._FEATURE_WORKSPACE_BUDGET_BYTES, 1 << 30)
        streamer.assert_called_once()
        self.assertEqual(seen["chunk_size"], 7)
        self.assertTrue(seen["echo_is_argument"])
        # 预览必须走分块路径：非分块入口不允许被调用。
        with mock.patch.object(
            module, "chirp_pulse_range_features", side_effect=AssertionError("未分块")
        ):
            build_inversion_feature_figure(echo, {"motion_compensation": "auto"})

    def test_unified_view_button_stays_visible_and_legacy_buttons_are_hidden(self):
        with _workspace_tmp("feature_preview_gui") as scratch:
            with mock.patch.object(storage, "STATE_PATH", scratch / "session.json"):
                window = PipelineWindow()
                window.show()
                self.app.processEvents()
                try:
                    window.runs_dir_edit.setText(str(scratch / "runs"))
                    window.run_name_edit.setText("empty_case")
                    self.app.processEvents()
                    self.assertFalse(window.feature_preview_btn.isVisible())
                    self.assertTrue(window.result_btn.isVisible())
                    self.assertFalse(window.feature_preview_btn.isEnabled())
                    self.assertFalse(window.preview_btn.isEnabled())
                    echo_dir = window._run_directory() / "echo"
                    echo_dir.mkdir(parents=True)
                    (echo_dir / "echo.npz").write_bytes(b"echo")
                    window._sync_echo_artifact_buttons()
                    self.assertFalse(window.feature_preview_btn.isEnabled())
                    self.assertTrue(window.preview_btn.isEnabled())
                    window._select_stage("inversion")
                    self.app.processEvents()
                    self.assertFalse(window.feature_preview_btn.isVisible())
                    self.assertTrue(window.result_btn.isVisible())
                    window._select_stage("echo")
                    self.app.processEvents()
                    self.assertFalse(window.feature_preview_btn.isVisible())
                    self.assertTrue(window.result_btn.isVisible())
                    self.assertFalse(window.feature_preview_btn.isEnabled())
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()
                    del window

    def test_breathing_edge_stops_after_the_button_is_opened(self):
        button = AttentionButton("查看回波")
        button.setEnabled(True)
        button.set_attention(True)
        self.assertTrue(button.attention_active())
        button.set_attention(False)
        self.assertFalse(button.attention_active())
        self.assertFalse(button._timer.isActive())

    def test_existing_product_is_ran_until_its_parameters_change(self):
        import pipeline

        with _workspace_tmp("stage_status") as scratch:
            with mock.patch.object(storage, "STATE_PATH", scratch / "session.json"):
                window = PipelineWindow()
                try:
                    window.runs_dir_edit.setText(str(scratch / "runs"))
                    window.run_name_edit.setText("case")
                    run_dir = window._run_directory()
                    run_dir.mkdir(parents=True)
                    artifact = run_dir / "observation_info.npz"
                    np.savez(artifact, elapsed_s=np.array([0.0]))
                    window._refresh_saved_run_status(overwrite_errors=True)
                    self.assertEqual(window.stage_status["observation"], "已运行")
                    prepared = pipeline.prepare_run(
                        window.config_data,
                        config_path=window.config_path,
                        run_dir=run_dir,
                        through_stage="observation",
                    )
                    pipeline.write_stage_success(
                        run_dir,
                        "observation",
                        fingerprint="different-fingerprint",
                        projection={"observation": {}},
                        output_path=artifact,
                    )
                    window._refresh_saved_run_status(overwrite_errors=True)
                    self.assertEqual(
                        window.stage_status["observation"],
                        window.STALE_STATUS,
                    )
                    self.assertIsNotNone(prepared["observation_fingerprint"])
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()
