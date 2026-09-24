"""Offscreen GUI schema-v4 regression checks (requires PySide6 in the pytorch env).

Run with:
    E:\\anaconda3\\envs\\pytorch\\python.exe -m pytest tests/test_gui_schema_v4.py -q -p no:cacheprovider

Modal dialogs (QMessageBox / QFileDialog) are replaced with mocks so the
offscreen platform can never block on a native dialog; tests assert that no
error dialog appeared for the success paths they exercise.
"""

import json
import os
import shutil
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtTest import QTest

import pipeline
from rotation_gui import storage
from rotation_gui.styling import GUI_STYLE
from rotation_gui.qt_compat import QApplication, QComboBox, QFrame, QLabel, QLineEdit, QProcess, QTextEdit, QWidget, Qt
from rotation_gui.widgets.inputs import (
    BooleanFieldWidget,
    NumericInputError,
    UnitValueWidget,
    VectorValueWidget,
    np_vector3,
)
from rotation_gui.window import main as main_module
from rotation_gui.window.main import PipelineWindow
from rotation_gui.window.parameter_form import ScheduleFeedbackWidget
from observation.src.campaign_planning import resolve_campaign_run_plan


@contextmanager
def _workspace_tmp(prefix: str):
    """A writable scratch directory under the git-ignored tmp/ folder."""
    name = f".tmp_{prefix}_{os.getpid()}_{int(time.time() * 1000)}"
    path = storage.ROOT / "tmp" / name
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _write_stub_observation(path: Path) -> None:
    np.savez(path, elapsed_s=np.array([0.0]), valid_plan=np.ones((1, 2), dtype=bool))


def _write_stub_echo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, iq=np.zeros((1, 2), dtype=np.complex64))


def _record_stage_success(run_dir: Path, config: dict, config_path, stage: str) -> None:
    """Write a valid stub artifact plus the fingerprint that current config expects."""

    run_dir = Path(run_dir)
    if stage == "observation":
        path = run_dir / "observation_info.npz"
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_stub_observation(path)
        prepared = pipeline.prepare_run(
            config, config_path=config_path, run_dir=run_dir, through_stage="observation"
        )
        pipeline.write_stage_success(
            run_dir,
            "observation",
            fingerprint=prepared["observation_fingerprint"],
            projection=pipeline.observation_dependency_projection(prepared["observation"]),
            output_path=path,
        )
        return
    if stage == "echo":
        echo_npz = run_dir / "echo" / "echo.npz"
        _write_stub_echo(echo_npz)
        prepared = pipeline.prepare_run(
            config, config_path=config_path, run_dir=run_dir, through_stage="echo"
        )
        observation_sha = (
            pipeline.file_sha256(prepared["observation_output"])
            if Path(prepared["observation_output"]).exists()
            else None
        )
        echo_proj = pipeline.echo_dependency_projection(
            prepared["echo"], observation_sha, config_path=config_path
        )
        pipeline.write_stage_success(
            run_dir,
            "echo",
            fingerprint=prepared["echo_fingerprint"],
            projection=echo_proj,
            output_path=echo_npz,
        )
        return
    raise ValueError(f"unsupported stage: {stage}")


def _set_widget_value(widget, value) -> None:
    """Drive a parameter widget the way a user would, regardless of widget type."""
    if isinstance(widget, BooleanFieldWidget):
        widget.setChecked(bool(value))
    elif isinstance(widget, UnitValueWidget):
        widget.edit.setText(str(value))
    elif isinstance(widget, VectorValueWidget):
        for edit, item in zip(widget.edits, value):
            edit.setText(str(item))
    elif isinstance(widget, QComboBox):
        data = "true" if value is True else "false" if value is False else str(value)
        index = widget.findData(data)
        if index < 0:
            widget.insertItem(0, data, data)
            index = 0
        widget.setCurrentIndex(index)
    elif isinstance(widget, QTextEdit):
        widget.setPlainText(json.dumps(value, ensure_ascii=False))
    elif isinstance(widget, QLineEdit):
        widget.setText(str(value))
    else:
        raise AssertionError(f"Unsupported widget type: {type(widget)!r}")


class GuiSchemaV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._state_workspace = _workspace_tmp("gui_state_")
        self._state_dir = self._state_workspace.__enter__()
        self._state_path_patcher = mock.patch.object(storage, "STATE_PATH", self._state_dir / "session.json")
        self._state_path_patcher.start()
        # Replace the message-box symbol in main.py so any unexpected error
        # dialog is recorded instead of blocking the offscreen event loop.
        self._msgbox_patcher = mock.patch.object(main_module, "QMessageBox")
        self.message_box = self._msgbox_patcher.start()

    def tearDown(self):
        self._msgbox_patcher.stop()
        self._state_path_patcher.stop()
        self._state_workspace.__exit__(None, None, None)

    def _make_window(self) -> PipelineWindow:
        return PipelineWindow()

    def _close_window(self, window) -> None:
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_schedule_feedback_distinguishes_infeasible_run_and_cartesian_visibility(self):
        config = json.loads(
            (storage.ROOT / "configs" / "chirp_mesh_target_test.json").read_text(encoding="utf-8")
        )["observation"]
        config["schedule"]["run_count"] = 1
        config["schedule"]["run_duration_s"] = 600.0
        plan = resolve_campaign_run_plan(config, allow_infeasible_preview=True)
        payload = plan.json_payload(config.get("transmitter"))
        feedback = ScheduleFeedbackWidget(lambda: None)
        try:
            feedback.resize(900, 220)
            feedback.show_plan(payload, 1)
            feedback.show()
            self.app.processEvents()

            self.assertFalse(payload.get("visibility_applicable", True))
            self.assertTrue(payload.get("visibility_computed", True))
            self.assertIn("单次 Run 不可行", feedback.summary.text())
            self.assertIn("run_duration_s 必须小于约", feedback.summary.text())
            self.assertIn("自定义直角坐标：不应用地平可见性约束", feedback.detail.text())
            self.assertNotIn("灰色斜纹", feedback.detail.text())
            self.assertIn("浅蓝", feedback.detail.text())
            self.assertEqual(len(feedback.timeline._payload["reservation_intervals_elapsed_s"]), 1)
            self.assertEqual(len(feedback.timeline._payload["adc_preview_intervals_elapsed_s"]), 1)
            self.assertGreaterEqual(feedback.timeline.height(), 112)
        finally:
            feedback.close()
            feedback.deleteLater()
            self.app.processEvents()

    def test_schedule_feedback_uses_grey_hatch_only_when_visibility_is_uncomputed(self):
        payload = {
            "campaign_duration_s": 10.0,
            "visibility_applicable": True,
            "visibility_computed": False,
            "allow_unobservable": False,
            "run_feasible": True,
            "max_run_count": 1,
            "occupied_duration_s": 1.0,
            "run_intervals_elapsed_s": [[0.0, 1.0]],
            "reservation_intervals_elapsed_s": [[0.0, 1.5]],
            "adc_preview_intervals_elapsed_s": [[0.2, 1.4]],
            "visibility_windows_elapsed_s": [],
        }
        feedback = ScheduleFeedbackWidget(lambda: None)
        try:
            feedback.resize(900, 220)
            feedback.show_plan(payload, 1)
            feedback.show()
            self.app.processEvents()
            self.assertIn("灰色斜纹：当前坐标无法计算几何可见性", feedback.detail.text())
            self.assertNotIn("自定义直角坐标", feedback.detail.text())
        finally:
            feedback.close()
            feedback.deleteLater()
            self.app.processEvents()

    def test_schedule_feedback_does_not_hatch_cartesian_even_if_delay_estimate_failed(self):
        payload = {
            "campaign_duration_s": 10.0,
            "visibility_applicable": False,
            "visibility_computed": False,
            "allow_unobservable": False,
            "run_feasible": True,
            "max_run_count": 1,
            "occupied_duration_s": 1.0,
            "run_intervals_elapsed_s": [[0.0, 1.0]],
            "reservation_intervals_elapsed_s": [[0.0, 1.5]],
            "adc_preview_intervals_elapsed_s": [[0.2, 1.4]],
            "visibility_windows_elapsed_s": [[0.0, 10.0]],
        }
        feedback = ScheduleFeedbackWidget(lambda: None)
        try:
            feedback.resize(900, 220)
            feedback.show_plan(payload, 1)
            feedback.show()
            self.app.processEvents()
            self.assertIn("自定义直角坐标：不应用地平可见性约束", feedback.detail.text())
            self.assertNotIn("灰色斜纹", feedback.detail.text())
        finally:
            feedback.close()
            feedback.deleteLater()
            self.app.processEvents()

    def test_card_titles_keep_uniform_height_with_schedule_preview(self):
        window = self._make_window()
        try:
            window.resize(1400, 900)
            window.show()
            for _ in range(5):
                self.app.processEvents()

            cards = window.parameter_form._cards[0].cards
            title_heights = {}
            for card in cards:
                title = next(
                    child
                    for child in card.findChildren(QLabel)
                    if child.objectName() == "cardTitle"
                )
                title_heights[card.property("groupName")] = title.height()

            self.assertEqual(len(set(title_heights.values())), 1, title_heights)
            self.assertEqual(title_heights["plan"], 24)
        finally:
            self._close_window(window)

    def test_default_config_loads_without_deprecated_keys(self):
        window = self._make_window()
        try:
            config = window.config_data

            # Top-level stage contract, no schema_version.
            self.assertNotIn("schema_version", config)
            for section in ("observation", "echo", "inversion"):
                self.assertIn(section, config)

            observation = config["observation"]
            self.assertNotIn("solver", observation)
            self.assertNotIn("campaign", observation)
            # Monostatic example omits receiver.
            self.assertNotIn("receiver", observation)

            self.assertNotIn("waveform", observation)
            self.assertIn("transmit", observation)
            echo = config["echo"]
            self.assertEqual(echo.get("waveform", {}).get("type"), "chirp_pulse_train")
            # Timing/ADC live in observation, not the echo waveform.
            for key in ("pulse_width_s", "prf_hz", "fast_sample_rate_hz"):
                self.assertNotIn(key, echo.get("waveform", {}))

            inversion = config["inversion"]
            # Chirp CPI uses physical durations, not pulse counts.
            self.assertNotIn("cpi_pulses", inversion)
            self.assertNotIn("cpi_hop_pulses", inversion)
        finally:
            self._close_window(window)

    def test_collect_rejects_legacy_observation_waveform(self):
        window = self._make_window()
        try:
            window.config_data["observation"]["waveform"] = {
                "type": "chirp_pulse_train",
                "prf_hz": 20.0,
                "pulse_width_s": 0.01,
            }
            with self.assertRaisesRegex(ValueError, r"observation\.waveform 已废弃"):
                window.parameter_form.collect()
            self.assertIn("waveform", window.config_data["observation"])
        finally:
            self._close_window(window)

    def test_field_widgets_use_v4_paths(self):
        window = self._make_window()
        try:
            widgets = window.parameter_form.field_widgets
            # The default chirp branch owns fast sampling under receiver_sampling.
            self.assertIn("observation.receiver_sampling.fast_sample_rate_hz", widgets)
            self.assertIn("observation.transmit.prf_hz", widgets)
            self.assertNotIn("observation.waveform.type", widgets)
            self.assertNotIn("observation.waveform.prf_hz", widgets)
            self.assertNotIn("echo.waveform.type", widgets)
            self.assertNotIn("echo.scattering_model", widgets)
            self.assertEqual(window.waveform_combo.currentData(), "chirp_pulse_train")
            self.assertEqual(window.scattering_model_combo.currentData(), "point_target")
            # Deprecated keys must not be rendered.
            self.assertNotIn("observation.solver", widgets)
            self.assertNotIn("observation.receive.acquisitions", widgets)
            self.assertNotIn("echo.waveform.fast_sample_rate_hz", widgets)
            self.assertNotIn("echo.waveform.pulse_width_s", widgets)
        finally:
            self._close_window(window)

    def test_config_sync_edits_propagate_into_config_data(self):
        window = self._make_window()
        try:
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.receiver_sampling.fast_sample_rate_hz", widgets)

            _set_widget_value(
                widgets["observation.receiver_sampling.fast_sample_rate_hz"], 7.5
            )
            window._sync_current_stage()

            self.assertEqual(
                window.config_data["observation"]["receiver_sampling"]["fast_sample_rate_hz"],
                7500.0,
            )
            self.assertFalse(self.message_box.critical.called)
        finally:
            self._close_window(window)

    def test_stage_switch_syncs_edited_observation_value(self):
        window = self._make_window()
        try:
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.receiver_sampling.fast_sample_rate_hz", widgets)
            _set_widget_value(
                widgets["observation.receiver_sampling.fast_sample_rate_hz"], 6.0
            )

            window._select_stage("echo")

            self.assertEqual(window.current_stage, "echo")
            self.assertEqual(
                window.config_data["observation"]["receiver_sampling"]["fast_sample_rate_hz"],
                6000.0,
            )
            # The echo stage now renders its own v4 fields.
            self.assertIn("echo.waveform.amplitude", window.parameter_form.field_widgets)
            self.assertFalse(self.message_box.critical.called)
        finally:
            self._close_window(window)

    def test_save_config_as_writes_to_new_path(self):
        with _workspace_tmp("gui_v4_saveas_") as tmp:
            target = Path(tmp) / "saved_config.json"
            window = self._make_window()
            try:
                fake_dialog = mock.Mock()
                fake_dialog.getSaveFileName.return_value = (str(target), "")
                with mock.patch.object(main_module, "QFileDialog", fake_dialog):
                    window._save_config_as()

                self.assertEqual(window.config_path, target.resolve())
                self.assertEqual(window.run_name_edit.text(), "chirp_point_target_test")
                self.assertTrue(target.exists())
                saved = json.loads(target.read_text(encoding="utf-8"))
                self.assertNotIn("schema_version", saved)
                self.assertIn("observation", saved)
                self.assertIn("echo", saved)
                self.assertIn("inversion", saved)
                self.assertFalse(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_save_updates_current_file_independently_of_experiment_name(self):
        with _workspace_tmp("gui_v4_save_current_") as tmp:
            original = tmp / "source.json"
            window = self._make_window()
            try:
                original.write_text(json.dumps(window.config_data, ensure_ascii=False), encoding="utf-8")
                window.config_path_edit.setText(str(original))
                window._load_config_from_entry()
                self.assertEqual(window.run_name_edit.text(), "source")
                window.parameter_form.field_widgets["observation.target.name"].setText("changed_target")
                window.run_name_edit.setText("new_experiment")
                window._save_config()
                self.assertEqual(window.config_path, original.resolve())
                self.assertEqual(window.config_path_edit.text(), str(original.resolve()))
                self.assertEqual(window.run_name_edit.text(), "new_experiment")
                self.assertEqual(json.loads(original.read_text(encoding="utf-8"))["observation"]["target"]["name"], "changed_target")
                self.assertFalse((tmp / "new_experiment.json").exists())
                self.assertEqual(window._run_directory().name, "new_experiment")
                self.assertFalse(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_save_as_collision_does_not_overwrite_another_config(self):
        with _workspace_tmp("gui_v4_saveas_collision_") as tmp:
            original = tmp / "source.json"
            occupied = tmp / "occupied.json"
            window = self._make_window()
            try:
                original.write_text(json.dumps(window.config_data, ensure_ascii=False), encoding="utf-8")
                occupied.write_text('{"sentinel": true}', encoding="utf-8")
                window.config_path_edit.setText(str(original))
                window._load_config_from_entry()
                fake_dialog = mock.Mock()
                fake_dialog.getSaveFileName.return_value = (str(occupied), "")
                with mock.patch.object(main_module, "QFileDialog", fake_dialog):
                    window._save_config_as()
                self.assertEqual(occupied.read_text(encoding="utf-8"), '{"sentinel": true}')
                self.assertEqual(window.config_path, original.resolve())
                self.assertTrue(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_save_as_new_directory_keeps_mesh_input_target(self):
        with _workspace_tmp("gui_v4_rebase_mesh_") as tmp:
            source = storage.ROOT / "configs" / "chirp_mesh_target_test.json"
            target = tmp / "elsewhere" / "copy.json"
            window = self._make_window()
            try:
                window.config_path_edit.setText(str(source))
                window._load_config_from_entry()
                original_model = (source.parent / window.config_data["echo"]["model_path"]).resolve()
                window.run_name_edit.setText("keep_run_name")
                fake_dialog = mock.Mock()
                fake_dialog.getSaveFileName.return_value = (str(target), "")
                with mock.patch.object(main_module, "QFileDialog", fake_dialog):
                    window._save_config_as()
                saved_model = json.loads(target.read_text(encoding="utf-8"))["echo"]["model_path"]
                self.assertEqual((target.parent / saved_model).resolve(), original_model)
                self.assertEqual(window.config_data["echo"]["model_path"], saved_model)
                self.assertEqual(window.run_name_edit.text(), "keep_run_name")
                self.assertFalse(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_save_as_does_not_replace_file_created_during_write(self):
        with _workspace_tmp("gui_v4_saveas_race_") as tmp:
            target = tmp / "raced.json"
            window = self._make_window()
            try:
                fake_dialog = mock.Mock()
                fake_dialog.getSaveFileName.return_value = (str(target), "")
                actual_link = os.link

                def create_competing_file(source, destination):
                    Path(destination).write_text('{"sentinel": true}', encoding="utf-8")
                    return actual_link(source, destination)

                with mock.patch.object(main_module, "QFileDialog", fake_dialog), mock.patch.object(
                    storage.os, "link", side_effect=create_competing_file
                ):
                    window._save_config_as()
                self.assertEqual(target.read_text(encoding="utf-8"), '{"sentinel": true}')
                self.assertNotEqual(window.config_path, target.resolve())
                self.assertTrue(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_save_as_cleanup_error_does_not_misreport_completed_file(self):
        with _workspace_tmp("gui_v4_saveas_cleanup_") as tmp:
            target = tmp / "new.json"
            window = self._make_window()
            try:
                fake_dialog = mock.Mock()
                fake_dialog.getSaveFileName.return_value = (str(target), "")
                with mock.patch.object(main_module, "QFileDialog", fake_dialog), mock.patch.object(
                    storage.os, "unlink", side_effect=PermissionError("temporary file busy")
                ):
                    window._save_config_as()
                self.assertTrue(target.is_file())
                self.assertEqual(window.config_path, target.resolve())
                self.assertFalse(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_config_path_is_display_only_and_run_name_cannot_escape_runs_dir(self):
        window = self._make_window()
        try:
            self.assertIsInstance(window.config_path_edit, QLabel)
            self.assertNotIsInstance(window.config_path_edit, QLineEdit)
            self.assertEqual(window.config_path_edit.focusPolicy(), Qt.FocusPolicy.NoFocus)
            self.assertEqual(window.config_path_edit.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
            self.assertFalse(hasattr(window, "load_btn"))
            window.run_name_edit.setText("../other")
            with self.assertRaisesRegex(ValueError, "实验名"):
                window._run_directory()
        finally:
            self._close_window(window)

    def test_config_path_click_has_no_focus_or_editing_affordance(self):
        window = self._make_window()
        try:
            window.show()
            for _ in range(4):
                self.app.processEvents()
            display = window.config_path_edit
            full_path = display.text()
            display.resize(160, display.height())
            self.assertEqual(display.text(), full_path)
            self.assertIn(full_path, display.toolTip())
            narrow_text = super(type(display), display).text()
            self.assertIn("…", narrow_text)
            display.resize(700, display.height())
            self.assertGreater(len(super(type(display), display).text()), len(narrow_text))
            display.setText("D:/other_config.json")
            self.assertEqual(display.text(), "D:/other_config.json")
            self.assertIn("D:/other_config.json", display.toolTip())
            QTest.mouseClick(display, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertFalse(display.hasFocus())
            self.assertNotIn("QLabel#configPathDisplay:focus", GUI_STYLE)
        finally:
            self._close_window(window)

    def test_failed_open_restores_the_current_save_target(self):
        with _workspace_tmp("gui_v4_failed_open_") as tmp:
            current = tmp / "current.json"
            invalid = tmp / "invalid.json"
            window = self._make_window()
            try:
                current.write_text(json.dumps(window.config_data, ensure_ascii=False), encoding="utf-8")
                invalid.write_text("{bad", encoding="utf-8")
                window.config_path_edit.setText(str(current))
                window._load_config_from_entry()
                name_widget = window.parameter_form.field_widgets["observation.target.name"]
                name_widget.setText("unsaved_after_failed_open")
                fake_dialog = mock.Mock()
                fake_dialog.getOpenFileName.return_value = (str(invalid), "")
                with mock.patch.object(main_module, "QFileDialog", fake_dialog):
                    window._choose_config()
                self.assertTrue(self.message_box.critical.called)
                self.assertEqual(window.config_path, current.resolve())
                self.assertEqual(window.config_path_edit.text(), str(current.resolve()))
                self.assertEqual(name_widget.text(), "unsaved_after_failed_open")
                window._save_config()
                self.assertEqual(invalid.read_text(encoding="utf-8"), "{bad")
                self.assertEqual(
                    json.loads(current.read_text(encoding="utf-8"))["observation"]["target"]["name"],
                    "unsaved_after_failed_open",
                )
            finally:
                self._close_window(window)

    def test_observation_run_defers_chirp_bandwidth_check_until_echo(self):
        window = self._make_window()
        try:
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            window.config_data["echo"]["waveform"]["bandwidth_hz"] = 1e12
            with mock.patch.object(window, "_run_next_pending_stage") as launch:
                window._start_stages(["observation"])
                launch.assert_called_once()
                self.assertFalse(self.message_box.critical.called)
                self.message_box.reset_mock()
                window._start_stages(["echo"])
                launch.assert_called_once()
                self.assertTrue(self.message_box.critical.called)
        finally:
            self._close_window(window)

    def test_run_all_rejects_inconsistent_echo_before_any_stage(self):
        window = self._make_window()
        try:
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            window.config_data["echo"]["waveform"]["bandwidth_hz"] = 1e12
            with mock.patch.object(window, "_run_next_pending_stage") as launch:
                window._start_stages(["observation", "echo", "inversion"])
                launch.assert_not_called()
            self.assertTrue(self.message_box.critical.called)
            self.assertTrue(window.run_btn.isEnabled())
            self.assertEqual(window.progress.format(), "校验失败")
            self.assertEqual(window.stage_status["observation"], "失败")
            self.assertEqual(window.stage_status["echo"], "未运行")
        finally:
            self._close_window(window)

    def test_zero_exit_without_primary_artifact_is_failure(self):
        window = self._make_window()
        try:
            missing = Path("missing_observation_info.npz")
            window.process = None
            window.process_stage = "observation"
            window.process_outputs = {"observation": (("观测信息", missing),)}
            window._pending_stages = ["echo"]
            window._process_finished(0)
            self.assertEqual(window.stage_status["observation"], "失败")
            self.assertEqual(window._pending_stages, [])
            self.assertTrue(window.run_btn.isEnabled())
            self.assertEqual(window.progress.format(), "主产物缺失")
            self.assertTrue(self.message_box.critical.called)
        finally:
            self._close_window(window)

    def test_zero_exit_empty_npz_is_failure(self):
        from tests.scratch import scratch_directory

        window = self._make_window()
        try:
            with scratch_directory("gui_empty_npz") as tmp:
                empty = Path(tmp) / "observation_info.npz"
                empty.write_bytes(b"")
                window.process = None
                window.process_stage = "observation"
                window.process_outputs = {"observation": (("观测信息", empty),)}
                window._pending_stages = ["echo"]
                window._process_finished(0)
                self.assertEqual(window.stage_status["observation"], "失败")
                self.assertEqual(window._pending_stages, [])
                self.assertTrue(window.run_btn.isEnabled())
                self.assertEqual(window.progress.format(), "主产物缺失")
                self.assertTrue(self.message_box.critical.called)
        finally:
            self._close_window(window)

    def test_echo_run_rejects_empty_chirp_bandwidth_widget(self):
        window = self._make_window()
        try:
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            window._select_stage("echo")
            self.app.processEvents()
            widget = window.parameter_form.field_widgets["echo.waveform.bandwidth_hz"]
            widget.edit.setText("")
            with mock.patch.object(window, "_run_next_pending_stage") as launch:
                window._start_stages(["echo"])
                launch.assert_not_called()
            self.assertTrue(self.message_box.critical.called)
        finally:
            self._close_window(window)

    def test_structured_warning_is_readable_and_log_actions_work(self):
        window = self._make_window()
        try:
            window._handle_output_line('__WARNING__ {"stage":"observation","message":"\\u65e0\\u6cd5\\u8ba1\\u7b97\\u51e0\\u4f55\\u53ef\\u89c1\\u6027"}')
            self.assertIn("警告", window.log.toPlainText())
            self.assertIn("无法计算几何可见性", window.log.toPlainText())
            self.assertNotIn("__WARNING__", window.log.toPlainText())
            self.assertNotIn("\\u65e0", window.log.toPlainText())
            window.copy_log_btn.click()
            self.assertIn("无法计算几何可见性", self.app.clipboard().text())
            window.clear_log_btn.click()
            self.assertEqual(window.log.toPlainText(), "")
            window._handle_output_line("samples=8")
            self.assertIn("样本数：8", window.log.toPlainText())
            window._append_log("计划警告。", level="warning")
            window._append_log("任务完成。", level="success")
            window._append_log("任务失败。", level="error")
            rendered = window.log.toHtml()
            self.assertIn("#177245", rendered)
            self.assertIn("#a86100", rendered)
            self.assertIn("#b4232c", rendered)
        finally:
            self._close_window(window)

    def test_log_renders_json_block_without_html_entities(self):
        window = self._make_window()
        try:
            window._append_log("{")
            window._append_log('  "runtime_s": 944.0594044,')
            window._append_log('  "iq_shape": [')
            window._append_log("    60000,")
            window._append_log(
                '  "observation_info_path": "D:\\\\runs\\\\chirp_mesh_target_test\\\\echo\\\\echo.npz"'
            )
            text = window.log.toPlainText()
            self.assertNotIn("&quot;", text)
            self.assertNotIn("<span", text)
            self.assertIn('"runtime_s": 944.0594044,', text)
            self.assertIn("    60000,", text)
            self.assertIn('"observation_info_path": "D:\\\\runs', text)
        finally:
            self._close_window(window)

    def test_completed_stage_reports_artifact_paths(self):
        with _workspace_tmp("gui_v4_outputs_") as tmp:
            run_dir = Path(tmp) / "outputs_run"
            window = self._make_window()
            try:
                prepared = pipeline.prepared_configs(
                    window.config_data, run_dir, validate_echo_waveform=False
                )
                outputs = main_module.stage_output_paths(prepared)
                echo_dir = Path(prepared["echo_output_dir"])
                echo_dir.mkdir(parents=True, exist_ok=True)
                _write_stub_echo(echo_dir / "echo.npz")
                (echo_dir / "summary.json").write_text("{}", encoding="utf-8")
                outputs = main_module.stage_output_paths(prepared)
                self.assertEqual(
                    dict(outputs["observation"])["观测信息"], Path(prepared["observation_output"])
                )
                self.assertEqual(
                    dict(outputs["inversion"])["反演结果"],
                    Path(prepared["inversion_output_dir"]) / "summary.json",
                )

                window.process = None
                window.process_stage = "echo"
                window.process_run_dir = run_dir
                window.process_outputs = outputs
                window._pending_stages = []
                window._process_finished(0)

                text = window.log.toPlainText()
                self.assertIn(str(Path(prepared["echo_output_dir"]) / "echo.npz"), text)
                self.assertIn(str(Path(prepared["echo_output_dir"]) / "summary.json"), text)
                self.assertFalse(self.message_box.critical.called)
            finally:
                self._close_window(window)

    def test_malformed_protocol_lines_never_reach_the_log_raw(self):
        window = self._make_window()
        try:
            window._handle_output_line('__WARNING__ {"stage":"echo",')
            window._handle_output_line('__PROGRESS__ {"percent":')
            window._handle_output_line('__ERROR__ {"stage":"inversion","message":"磁盘空间不足"}')
            text = window.log.toPlainText()
            for marker in ("__WARNING__", "__PROGRESS__", "__ERROR__"):
                self.assertNotIn(marker, text)
            self.assertIn("磁盘空间不足", text)
            self.assertIn('{"stage":"echo",', text)
            # 进度条不应被坏消息改动
            window.progress.setValue(42)
            window._handle_output_line('__PROGRESS__ {"percent":"不是数字"}')
            self.assertEqual(window.progress.value(), 42)
            self.assertNotIn("__PROGRESS__", window.log.toPlainText())
        finally:
            self._close_window(window)

    def test_warning_line_carries_stage_without_duplicate_severity_word(self):
        window = self._make_window()
        try:
            window._handle_output_line(
                '__WARNING__ {"stage":"observation","message":"无法计算几何可见性"}'
            )
            line = window.log.toPlainText().strip()
            self.assertIn("观测解算：无法计算几何可见性", line)
            self.assertNotIn("警告（观测解算）", line)
        finally:
            self._close_window(window)

    def test_blank_log_lines_insert_no_non_breaking_space(self):
        window = self._make_window()
        try:
            window._append_log("第一行")
            window._append_log("")
            window._append_log("第二行")
            text = window.log.toPlainText()
            self.assertNotIn("\u00a0", text)
            self.assertIn("第一行\n\n第二行", text)
        finally:
            self._close_window(window)

    def test_user_abort_is_reported_as_abort_not_failure(self):
        window = self._make_window()
        try:
            window.run_btn.setEnabled(False)
            window.run_all_btn.setEnabled(False)
            window.stop_btn.setEnabled(True)
            window.process = mock.Mock()
            window.process_stage = "echo"
            window.process_run_dir = None
            window.process_outputs = {}
            window._pending_stages = ["inversion"]
            window._abort_requested = True
            window._process_finished(1)

            text = window.log.toPlainText()
            self.assertIn("已中止", text)
            self.assertNotIn("失败", text)
            self.assertFalse(self.message_box.critical.called)
            self.assertTrue(window.run_btn.isEnabled())
            self.assertFalse(window.stop_btn.isEnabled())
            self.assertEqual(window._pending_stages, [])
            self.assertEqual(window.stage_status["echo"], "已中止")
        finally:
            self._close_window(window)

    def test_failed_to_start_clears_running_state(self):
        window = self._make_window()
        try:
            window.run_btn.setEnabled(False)
            window.run_all_btn.setEnabled(False)
            window.stop_btn.setEnabled(True)
            window.process = mock.Mock()
            window.process.errorString.return_value = "系统找不到指定的文件"
            window.process_stage = "echo"
            window._pending_stages = ["inversion"]
            window._process_error(QProcess.ProcessError.FailedToStart)

            text = window.log.toPlainText()
            self.assertIn("无法启动进程", text)
            self.assertIn("系统找不到指定的文件", text)
            self.assertIsNone(window.process)
            self.assertIsNone(window.process_stage)
            self.assertTrue(window.run_btn.isEnabled())
            self.assertFalse(window.stop_btn.isEnabled())
            self.assertEqual(window._pending_stages, [])
            self.assertEqual(window.stage_status["echo"], "失败")
        finally:
            self._close_window(window)

    def test_inversion_stage_reuses_existing_echo_and_reports_missing_artifact(self):
        with _workspace_tmp("gui_v4_reuse_") as tmp:
            window = self._make_window()
            try:
                # 让默认配置的回波带宽通过采样率校验，测试关注的是复用与缺失提示。
                window.config_data["echo"]["waveform"]["bandwidth_hz"] = 1000.0
                window.runs_dir_edit.setText(str(tmp))
                window.run_name_edit.setText("reuse_run")
                echo_dir = Path(tmp) / "reuse_run" / "echo"
                echo_dir.mkdir(parents=True)
                _record_stage_success(
                    Path(tmp) / "reuse_run",
                    window.config_data,
                    window.config_path,
                    "echo",
                )

                with mock.patch.object(main_module.QProcess, "start") as start:
                    window._pending_stages = ["inversion"]
                    window._run_next_pending_stage()
                    self.assertTrue(start.called)
                    self.assertEqual(
                        window.process.processChannelMode(),
                        QProcess.ProcessChannelMode.MergedChannels,
                    )
                text = window.log.toPlainText()
                self.assertIn("复用已有回波数据", text)
                self.assertIn(str(echo_dir / "echo.npz"), text)

                window.run_name_edit.setText("missing_run")
                window._pending_stages = ["inversion"]
                with mock.patch.object(main_module.QProcess, "start") as start_missing:
                    window._run_next_pending_stage()
                    self.assertFalse(start_missing.called)
                text = window.log.toPlainText()
                self.assertIn("找不到回波数据", text)
                self.assertIn("复用已有回波", text)
                self.assertTrue(self.message_box.critical.called)
                self.assertTrue(window.run_btn.isEnabled())
                self.assertEqual(window._pending_stages, [])
            finally:
                self._close_window(window)

    def test_leftover_generated_does_not_silently_reuse_echo(self):
        with _workspace_tmp("gui_v4_leftover_generated_") as tmp:
            window = self._make_window()
            try:
                window.config_data["echo"]["waveform"]["bandwidth_hz"] = 1000.0
                window.runs_dir_edit.setText(str(tmp))
                window.run_name_edit.setText("leftover_run")
                run_dir = Path(tmp) / "leftover_run"
                echo_dir = run_dir / "echo"
                echo_dir.mkdir(parents=True)
                _write_stub_echo(echo_dir / "echo.npz")
                prepared = pipeline.prepare_run(
                    window.config_data,
                    config_path=window.config_path,
                    run_dir=run_dir,
                    through_stage="echo",
                )
                config_dir = run_dir / "configs"
                config_dir.mkdir(parents=True, exist_ok=True)
                (config_dir / "echo.generated.json").write_text(
                    json.dumps(prepared["echo"], ensure_ascii=False), encoding="utf-8"
                )

                with mock.patch.object(main_module.QProcess, "start") as start:
                    window._pending_stages = ["inversion"]
                    window._run_next_pending_stage()
                    self.assertFalse(start.called)
                self.assertTrue(self.message_box.question.called)
                self.assertIn("缺少可核对的阶段指纹", window.log.toPlainText())
                self.assertNotIn("复用已有回波数据", window.log.toPlainText())
            finally:
                self._close_window(window)

    def test_summary_protocol_renders_readable_lines(self):
        window = self._make_window()
        try:
            payload = {
                "stage": "inversion",
                "title": "周期反演结果",
                "items": [
                    ["推荐周期", "139.502 s（0.0388 h）"],
                    ["显著性", "不显著"],
                ],
            }
            window._handle_output_line("__SUMMARY__ " + json.dumps(payload, ensure_ascii=True))
            text = window.log.toPlainText()
            self.assertNotIn("__SUMMARY__", text)
            self.assertIn("周期反演结果", text)
            self.assertIn("    推荐周期：139.502 s（0.0388 h）", text)
            self.assertIn("    显著性：不显著", text)
            self.assertNotIn('"items"', text)

            window.log.clear()
            window._handle_output_line("__SUMMARY__ {坏载荷")
            self.assertNotIn("__SUMMARY__", window.log.toPlainText())
        finally:
            self._close_window(window)

    def test_primary_artifact_write_is_not_logged_twice(self):
        window = self._make_window()
        try:
            primary = Path(r"D:\runs\x\observation_info.npz")
            window.process_stage = "observation"
            window.process_outputs = {"observation": (("观测信息", primary),)}
            window._handle_output_line(f"Wrote {primary}")
            self.assertNotIn("已写入", window.log.toPlainText())

            window._handle_output_line(r"Wrote D:\runs\x\other.npz")
            self.assertIn(r"已写入：D:\runs\x\other.npz", window.log.toPlainText())
        finally:
            self._close_window(window)

    def test_log_block_count_is_capped(self):
        window = self._make_window()
        try:
            document = window.log.document()
            self.assertEqual(document.maximumBlockCount(), 5000)
            document.setMaximumBlockCount(10)
            for index in range(25):
                window._append_log(f"第 {index} 行")
            self.assertLessEqual(document.blockCount(), 10)
            text = window.log.toPlainText()
            self.assertIn("第 24 行", text)
            self.assertNotIn("第 0 行", text)
        finally:
            self._close_window(window)

    def test_reusing_upstream_blocks_when_effective_config_differs(self):
        with _workspace_tmp("gui_v4_reuse_cfg_") as tmp:
            window = self._make_window()
            try:
                window.config_data["echo"]["waveform"]["bandwidth_hz"] = 1000.0
                window.runs_dir_edit.setText(str(tmp))

                stored = json.loads(json.dumps(window.config_data))
                stored["inversion"]["period_max_s"] = 1234.0
                _record_stage_success(
                    Path(tmp) / "run_a", stored, window.config_path, "echo"
                )
                window.run_name_edit.setText("run_a")
                with mock.patch.object(main_module.QProcess, "start"):
                    window._pending_stages = ["inversion"]
                    window._run_next_pending_stage()
                self.assertIn("复用已有回波数据", window.log.toPlainText())
                self.assertNotIn("不一致", window.log.toPlainText())

                window.log.clear()
                stored = json.loads(json.dumps(window.config_data))
                stored["echo"]["waveform"]["bandwidth_hz"] = 500.0
                _record_stage_success(
                    Path(tmp) / "run_b", stored, window.config_path, "echo"
                )
                window.run_name_edit.setText("run_b")
                with mock.patch.object(main_module.QProcess, "start") as start_blocked:
                    window._pending_stages = ["inversion"]
                    window._run_next_pending_stage()
                    self.assertFalse(start_blocked.called)
                self.assertIn("请重跑上游阶段", window.log.toPlainText())
                self.assertTrue(self.message_box.critical.called)

                window.log.clear()
                self.message_box.reset_mock()
                stored = json.loads(json.dumps(window.config_data))
                stored["echo"]["waveform"]["bandwidth_hz"] = 500.0
                _record_stage_success(
                    Path(tmp) / "run_c", stored, window.config_path, "observation"
                )
                window.run_name_edit.setText("run_c")
                with mock.patch.object(main_module.QProcess, "start"):
                    window._pending_stages = ["echo"]
                    window._run_next_pending_stage()
                self.assertIn("复用已有观测信息", window.log.toPlainText())
                self.assertNotIn("请重跑上游阶段", window.log.toPlainText())
            finally:
                self._close_window(window)

    def test_run_snapshot_is_the_canonical_pipeline_config(self):
        with _workspace_tmp("gui_v4_canonical_snapshot_") as tmp:
            window = self._make_window()
            try:
                window.runs_dir_edit.setText(str(tmp))
                window.run_name_edit.setText("canonical_snapshot")
                window.config_data["echo"]["waveform"]["bandwidth_hz"] = 1000.0
                window.config_data["inversion"].pop("motion_compensation", None)
                prepared = pipeline.prepare_run(
                    window.config_data,
                    config_path=window.config_path,
                    run_dir=Path(tmp) / "canonical_snapshot",
                    through_stage="observation",
                )
                expected = prepared["observation"]

                with mock.patch.object(main_module.QProcess, "start"):
                    window._pending_stages = ["observation"]
                    window._run_next_pending_stage()

                stored = json.loads(
                    (
                        Path(tmp)
                        / "canonical_snapshot"
                        / "configs"
                        / "observation.generated.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(stored, expected)
            finally:
                self._close_window(window)

    def test_inversion_rejects_echo_with_stale_chirp_row_width(self):
        """A pre-fix 251-column echo must not mix with a 252-column plan."""

        with _workspace_tmp("gui_v4_stale_chirp_width_") as tmp:
            window = self._make_window()
            try:
                window.runs_dir_edit.setText(str(tmp))
                window.run_name_edit.setText("stale_width")
                run_dir = Path(tmp) / "stale_width"
                echo_dir = run_dir / "echo"
                echo_dir.mkdir(parents=True)
                np.savez(
                    run_dir / "observation_info.npz",
                    valid_plan=np.ones((2, 252), dtype=bool),
                    row_start_sample=np.array([0, 250], dtype=np.int64),
                    metadata_json=json.dumps(
                        {
                            "data_layout": "pulse_adc_windows",
                            "fast_sample_count": 252,
                            "fast_sample_rate_hz": 5_000.0,
                        }
                    ),
                )
                np.savez(
                    echo_dir / "echo.npz",
                    iq=np.zeros((2, 251), dtype=np.complex64),
                    fast_time_s=np.arange(251, dtype=float) / 5_000.0,
                    metadata_json=json.dumps(
                        {
                            "data_layout": "pulse_adc_windows",
                            "fast_sample_rate_hz": 5_000.0,
                        }
                    ),
                )
                prepared = pipeline.prepare_run(
                    window.config_data,
                    config_path=window.config_path,
                    run_dir=run_dir,
                    through_stage="echo",
                )
                pipeline.write_stage_success(
                    run_dir,
                    "observation",
                    fingerprint=prepared["observation_fingerprint"],
                    projection=pipeline.observation_dependency_projection(
                        prepared["observation"]
                    ),
                    output_path=run_dir / "observation_info.npz",
                )
                observation_sha = pipeline.file_sha256(run_dir / "observation_info.npz")
                echo_proj = pipeline.echo_dependency_projection(
                    prepared["echo"],
                    observation_sha,
                    config_path=window.config_path,
                )
                pipeline.write_stage_success(
                    run_dir,
                    "echo",
                    fingerprint=prepared["echo_fingerprint"],
                    projection=echo_proj,
                    output_path=echo_dir / "echo.npz",
                )

                with mock.patch.object(main_module.QProcess, "start") as start:
                    window._pending_stages = ["inversion"]
                    window._run_next_pending_stage()

                start.assert_not_called()
                self.assertIn("观测计划为 252 列，回波为 251 列", window.log.toPlainText())
                self.assertEqual(window.progress.format(), "上游产物不兼容")

                window.log.clear()
                window._prepare_echo_preview(run_dir)
                self.assertFalse(window.preview_btn.isEnabled())
                self.assertIn("回波预览拒绝不兼容产物", window.log.toPlainText())

                cached_preview = echo_dir / "preview.html"
                cached_preview.write_text("<html>old preview</html>", encoding="utf-8")
                window.echo_preview_html = cached_preview
                window._set_preview_ready(True)
                window.log.clear()
                with mock.patch(
                    "rotation_gui.window.echo_preview.open_echo_preview_in_browser"
                ) as open_preview:
                    window._open_echo_preview()
                open_preview.assert_not_called()
                self.assertFalse(window.preview_btn.isEnabled())
                self.assertIsNone(window.echo_preview_html)
                self.assertIn("回波预览拒绝不兼容产物", window.log.toPlainText())
            finally:
                self._close_window(window)

    def test_gui_restores_last_session_config_and_experiment_name(self):
        with _workspace_tmp("gui_v4_session_") as tmp:
            selected = Path(tmp) / "selected.json"
            first = self._make_window()
            try:
                selected.write_text(json.dumps(first.config_data, ensure_ascii=False), encoding="utf-8")
                first.config_path_edit.setText(str(selected))
                first._load_config_from_entry()
                first.parameter_form.field_widgets["observation.target.name"].setText("unsaved_target")
                first.run_name_edit.setText("draft_experiment")
            finally:
                self._close_window(first)
            second = self._make_window()
            try:
                self.assertEqual(second.config_path, selected.resolve())
                self.assertEqual(second.run_name_edit.text(), "draft_experiment")
                self.assertEqual(second.config_data["observation"]["target"]["name"], "unsaved_target")
                self.assertNotEqual(json.loads(selected.read_text(encoding="utf-8"))["observation"]["target"]["name"], "unsaved_target")
            finally:
                self._close_window(second)

    def test_invalid_gui_session_falls_back_to_current_default(self):
        storage.STATE_PATH.write_text(json.dumps({"config_path": "missing.json", "config": {"unsupported": True}}), encoding="utf-8")
        window = self._make_window()
        try:
            self.assertEqual(window.config_path, storage.DEFAULT_CONFIG_PATH.resolve())
            self.assertEqual(window.run_name_edit.text(), storage.DEFAULT_CONFIG_PATH.stem)
        finally:
            self._close_window(window)

    def test_resize_three_widths_keeps_form_intact(self):
        window = self._make_window()
        try:
            for width in (1100, 1440, 1920):
                window.resize(width, 900)
                self.app.processEvents()
                self.assertEqual(window.width(), width)
                self.assertGreater(len(window.parameter_form.field_widgets), 0)
                self.assertIn(
                    "observation.receiver_sampling.fast_sample_rate_hz",
                    window.parameter_form.field_widgets,
                )
                for canvas in window.parameter_form._cards:
                    canvas.reflow()
                    self.app.processEvents()
                    visible = [card for card in canvas.cards if not card.isHidden()]
                    for card in visible:
                        self.assertGreaterEqual(card.geometry().left(), 0)
                        self.assertLessEqual(card.geometry().right(), canvas.width() - 1)
                        self.assertGreaterEqual(card.height(), card.minimumSizeHint().height())
                    for index, left in enumerate(visible):
                        for right in visible[index + 1:]:
                            self.assertFalse(
                                left.geometry().intersects(right.geometry()),
                                f"cards overlap at width={width}: "
                                f"{left.property('groupName')} / {right.property('groupName')}",
                            )
        finally:
            self._close_window(window)

    def test_full_roundtrip_edit_save_reload(self):
        with _workspace_tmp("gui_v4_roundtrip_") as tmp:
            target = Path(tmp) / "roundtrip.json"
            window = self._make_window()
            try:
                widgets = window.parameter_form.field_widgets
                self.assertIn("observation.receiver_sampling.fast_sample_rate_hz", widgets)
                _set_widget_value(
                    widgets["observation.receiver_sampling.fast_sample_rate_hz"], 9.25
                )
                window._sync_current_stage()

                window.config_path = target
                window.config_path_edit.setText(str(target))
                window.run_name_edit.setText(target.stem)
                window._save_config()
                self.assertTrue(target.exists())

                window2 = self._make_window()
                try:
                    window2.config_path_edit.setText(str(target))
                    window2._load_config_from_entry()

                    self.assertEqual(
                        window2.config_data["observation"]["receiver_sampling"]["fast_sample_rate_hz"],
                        9250.0,
                    )
                    self.assertNotIn("schema_version", window2.config_data)
                    self.assertFalse(self.message_box.critical.called)
                finally:
                    self._close_window(window2)
            finally:
                self._close_window(window)

    def test_loading_deprecated_fields_fails_without_migration(self):
        with _workspace_tmp("gui_v4_legacy_") as tmp:
            target = Path(tmp) / "legacy.json"
            payload = pipeline.canonical_pipeline_config(
                json.loads((storage.ROOT / "configs" / "chirp_point_target_test.json").read_text(encoding="utf-8"))
            )
            payload["observation"]["campaign"] = {"query_start_utc": "2026-01-01T00:00:00Z"}
            target.write_text(json.dumps(payload), encoding="utf-8")
            window = self._make_window()
            try:
                window.config_path_edit.setText(str(target))
                window._load_config_from_entry()
                self.assertTrue(self.message_box.critical.called)

                payload = pipeline.canonical_pipeline_config(
                    json.loads(
                        (storage.ROOT / "configs" / "chirp_point_target_test.json").read_text(
                            encoding="utf-8"
                        )
                    )
                )
                payload["observation"]["waveform"] = {
                    "type": "chirp_pulse_train",
                    "prf_hz": 20.0,
                    "pulse_width_s": 0.01,
                }
                target.write_text(json.dumps(payload), encoding="utf-8")
                self.message_box.critical.reset_mock()
                window.config_path_edit.setText(str(target))
                window._load_config_from_entry()
                self.assertTrue(self.message_box.critical.called)
                self.assertNotIn("waveform", window.config_data["observation"])
            finally:
                self._close_window(window)

    def test_point_target_toggle_strips_mesh_fields(self):
        window = self._make_window()
        try:
            _set_widget_value(window.scattering_model_combo, "mesh")
            self.app.processEvents()
            self.assertEqual(window.config_data["echo"]["scattering_model"], "mesh")
            self.assertIn("model_path", window.config_data["echo"])
            _set_widget_value(window.scattering_model_combo, "point_target")
            self.app.processEvents()
            echo = window.config_data["echo"]
            self.assertEqual(echo["scattering_model"], "point_target")
            for key in ("model_path", "target", "scattering_power", "scattering_spot"):
                self.assertNotIn(key, echo)
            pipeline.canonical_pipeline_config(window.config_data)
        finally:
            self._close_window(window)

    def test_mesh_from_point_target_restores_target_and_scattering_cards(self):
        window = self._make_window()
        try:
            self.assertEqual(window.config_data["echo"]["scattering_model"], "point_target")
            window._select_stage("echo")
            self.app.processEvents()
            self.assertNotIn("echo.model_path", window.parameter_form.field_widgets)
            _set_widget_value(window.scattering_model_combo, "mesh")
            self.app.processEvents()
            self.assertEqual(window.config_data["echo"]["scattering_model"], "mesh")
            for path in (
                "echo.model_path",
                "echo.target.rotation_period_s",
                "echo.scattering_power",
                "echo.scattering_spot.enabled",
            ):
                self.assertIn(path, window.parameter_form.field_widgets)
            cards = [card.property("groupName") for card in window.parameter_form._cards[0].cards]
            self.assertIn("target", cards)
            self.assertIn("scattering_spot", cards)
            self.assertIn("noise", cards)
        finally:
            self._close_window(window)

    def test_switching_to_cw_drops_chirp_event_source(self):
        window = self._make_window()
        try:
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            self.assertEqual(
                window.config_data["echo"]["waveform"]["type"], "chirp_pulse_train"
            )
            self.assertNotIn("waveform", window.config_data["observation"])
            self.assertIn("schedule", window.config_data["observation"])
            self.assertIn(
                "observation.transmit.prf_hz", window.parameter_form.field_widgets
            )
            _set_widget_value(window.waveform_combo, "continuous_wave")
            self.app.processEvents()
            observation = window.config_data["observation"]
            self.assertIn("receive", observation)
            self.assertNotIn("schedule", observation)
            self.assertNotIn("transmit", observation)
            self.assertNotIn("waveform", observation)
            self.assertEqual(
                window.config_data["echo"]["waveform"]["type"], "continuous_wave"
            )
            self.assertNotIn("cpi_duration_s", window.config_data["inversion"])
            pipeline.canonical_pipeline_config(window.config_data)
        finally:
            self._close_window(window)

    def test_extent_path_m_shown_on_chirp_sampling_card_hidden_for_cw(self):
        window = self._make_window()
        try:
            window.config_data["observation"]["target"]["extent_path_m"] = 3000.0
            _set_widget_value(window.waveform_combo, "continuous_wave")
            window._select_stage("observation")
            self.app.processEvents()
            self.assertNotIn(
                "observation.target.extent_path_m", window.parameter_form.field_widgets
            )

            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.target.extent_path_m", widgets)
            self.assertNotIn("observation.receiver_sampling.pre_guard_s", widgets)
            self.assertNotIn("observation.receiver_sampling.post_guard_s", widgets)
            readout = window.parameter_form.range_gate_readout
            self.assertIsNotNone(readout)
            self.assertIn("整行", readout.text())
            cards = window.parameter_form._cards[0].cards
            sampling_card = next(
                card for card in cards if card.property("groupName") == "receiver_sampling"
            )
            self.assertTrue(
                any(
                    widgets["observation.target.extent_path_m"] is child
                    or widgets["observation.target.extent_path_m"].isAncestorOf(child)
                    or child.isAncestorOf(widgets["observation.target.extent_path_m"])
                    for child in sampling_card.findChildren(QWidget)
                )
            )

            extent_widget = widgets["observation.target.extent_path_m"]
            extent_factor = float(extent_widget.unit_combo.currentData())
            pulse = widgets["observation.transmit.pulse_width_s"]
            rate = widgets["observation.receiver_sampling.fast_sample_rate_hz"]
            window.config_data["echo"].setdefault("waveform", {})["bandwidth_hz"] = 1000.0
            pulse.unit_combo.setCurrentText("s")
            pulse.edit.setText("0.01")
            rate_factor = float(rate.unit_combo.currentData())
            rate.edit.setText(str(5000.0 / rate_factor))
            extent_widget.edit.setText("0")
            self.app.processEvents()
            readout = window.parameter_form.range_gate_readout.text()
            self.assertIn("静止时标", readout)
            self.assertIn("整行 53 点", readout)
            self.assertIn("150 km", readout)
            extent_widget.edit.setText(str(1500.0 / extent_factor))
            window._sync_current_stage()
            self.assertEqual(
                window.config_data["observation"]["target"]["extent_path_m"], 1500.0
            )

            _set_widget_value(window.waveform_combo, "continuous_wave")
            self.app.processEvents()
            self.assertNotIn(
                "observation.target.extent_path_m", window.parameter_form.field_widgets
            )
            self.assertEqual(
                window.config_data["observation"]["target"]["extent_path_m"], 1500.0
            )
        finally:
            self._close_window(window)

    def test_loading_legacy_time_guards_logs_the_path_gate_fold(self):
        window = self._make_window()
        try:
            with _workspace_tmp("legacy_gate") as tmp:
                path = tmp / "legacy.json"
                config = json.loads(
                    (storage.ROOT / "configs" / "chirp_point_target_test.json").read_text(
                        encoding="utf-8"
                    )
                )
                config["observation"]["receiver_sampling"]["pre_guard_s"] = 0.01
                config["observation"]["receiver_sampling"]["post_guard_s"] = 0.01
                path.write_text(json.dumps(config), encoding="utf-8")
                window.config_path_edit.setText(str(path))
                window._load_config_from_entry()
                self.app.processEvents()
                self.assertIn("采集路径窗已合并", window.log.toPlainText())
                sampling = window.config_data["observation"]["receiver_sampling"]
                self.assertNotIn("pre_guard_s", sampling)
                self.assertNotIn("post_guard_s", sampling)
                self.assertGreater(
                    window.config_data["observation"]["target"]["extent_path_m"], 1.0e6
                )
        finally:
            self._close_window(window)

    def test_target_state_roundtrip_preserves_numeric_vector_and_drops_horizons_id(self):
        window = self._make_window()
        try:
            widgets = window.parameter_form.field_widgets
            self.assertEqual(widgets["observation.target.state"].currentData(), "static")
            widgets["observation.target.linear_motion"].setChecked(True)
            self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertEqual(window.config_data["observation"]["target"]["state"], "linear")
            position = widgets["observation.target.position0_m"]
            _set_widget_value(position, ["299,792,458", 0.0, 0.0])
            window._sync_current_stage()

            widgets = window.parameter_form.field_widgets
            widgets["observation.target.linear_motion"].setChecked(False)
            self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.target.position_m", widgets)
            self.assertNotIn("observation.target.position0_m", widgets)
            self.assertEqual(window.config_data["observation"]["target"]["position_m"], [299792458, 0.0, 0.0])

            _set_widget_value(widgets["observation.target.state"], "horizons_vectors")
            self.app.processEvents()
            self.assertNotIn("observation.target.object_type", window.parameter_form.field_widgets)
            self.assertEqual(window.config_data["observation"]["target"]["object_type"], "smallbody")
            _set_widget_value(window.parameter_form.field_widgets["observation.target.state"], "static")
            self.app.processEvents()
            target = window.config_data["observation"]["target"]
            self.assertNotIn("id", target)
            self.assertIn("position_m", target)
            pipeline.canonical_pipeline_config(window.config_data)
        finally:
            self._close_window(window)

    def test_station_coordinate_switch_keeps_editor_left_edge(self):
        window = self._make_window()
        try:
            window.show()
            self.app.processEvents()
            form = window.parameter_form
            station_state = form.field_widgets["observation.transmitter.state"]
            cartesian_x = station_state.mapToGlobal(station_state.rect().topLeft()).x()
            _set_widget_value(station_state, "geodetic")
            self.app.processEvents()
            station_state = form.field_widgets["observation.transmitter.state"]
            geodetic_x = station_state.mapToGlobal(station_state.rect().topLeft()).x()
            self.assertEqual(cartesian_x, geodetic_x)
            _set_widget_value(station_state, "cartesian")
            self.app.processEvents()
            station_state = form.field_widgets["observation.transmitter.state"]
            self.assertEqual(cartesian_x, station_state.mapToGlobal(station_state.rect().topLeft()).x())
        finally:
            self._close_window(window)

    def test_visibility_fields_follow_station_coordinate_semantics(self):
        window = self._make_window()
        try:
            widgets = window.parameter_form.field_widgets
            self.assertNotIn("observation.visibility.min_tx_elevation_deg", widgets)
            self.assertNotIn("observation.visibility.sample_step_s", widgets)
            self.assertNotIn("observation.visibility.allow_unobservable_for_simulation", widgets)

            _set_widget_value(widgets["observation.transmitter.state"], "geodetic")
            self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.visibility.min_tx_elevation_deg", widgets)
            self.assertIn("observation.visibility.sample_step_s", widgets)
            self.assertIn("observation.visibility.allow_unobservable_for_simulation", widgets)

            _set_widget_value(widgets["observation.transmitter.state"], "cartesian")
            self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertNotIn("observation.visibility.min_tx_elevation_deg", widgets)
            self.assertNotIn("observation.visibility.sample_step_s", widgets)
            self.assertNotIn("observation.visibility.allow_unobservable_for_simulation", widgets)
            self.assertNotIn("visibility", window.config_data["observation"])
        finally:
            self._close_window(window)

    def test_mixed_stations_show_only_horizon_side_visibility_fields(self):
        window = self._make_window()
        try:
            window.show()
            self.app.processEvents()
            window._bistatic_receiver_backup = {
                "name": "receiver",
                "state": "static",
                "position_m": [0.0, 0.0, 0.0],
            }
            window.monostatic_checkbox.setChecked(False)
            for _ in range(5):
                self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.receiver.state", widgets)
            _set_widget_value(widgets["observation.transmitter.state"], "geodetic")
            self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            _set_widget_value(widgets["observation.receiver.state"], "cartesian")
            for _ in range(5):
                self.app.processEvents()
            widgets = window.parameter_form.field_widgets
            self.assertIn("observation.visibility.sample_step_s", widgets)
            self.assertIn("observation.visibility.min_tx_elevation_deg", widgets)
            self.assertNotIn("observation.visibility.min_rx_elevation_deg", widgets)
            visibility = window.config_data["observation"].get("visibility") or {}
            self.assertNotIn("min_rx_elevation_deg", visibility)
        finally:
            self._close_window(window)

    def test_random_seed_remains_reachable_without_scroll_jump(self):
        window = self._make_window()
        try:
            window.resize(1100, 720)
            window.show()
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            form = window.parameter_form
            selection = form.field_widgets["observation.schedule.selection"]
            _set_widget_value(selection, "automatic")
            self.app.processEvents()
            bar = form.scroll.verticalScrollBar()
            bar.setValue(bar.maximum())
            self.app.processEvents()
            original_scroll = bar.value()
            form.field_widgets["observation.schedule.random_selection"].setChecked(True)
            for _ in range(5):
                self.app.processEvents()
            self.assertEqual(bar.value(), original_scroll)
            self.assertTrue(form.field_widgets["observation.schedule.random_selection"].hasFocus())
            self.assertFalse(window.config_path_edit.hasFocus())
            bar.setValue(bar.maximum())
            self.app.processEvents()
            seed = form.field_widgets["observation.schedule.random_seed"]
            viewport = form.scroll.viewport()
            self.assertLessEqual(
                seed.mapToGlobal(seed.rect().bottomLeft()).y(),
                viewport.mapToGlobal(viewport.rect().bottomLeft()).y(),
            )
            bar.setValue(original_scroll)
            form.field_widgets["observation.schedule.random_selection"].setChecked(False)
            for _ in range(5):
                self.app.processEvents()
            self.assertEqual(bar.value(), original_scroll)
            self.assertTrue(form.field_widgets["observation.schedule.random_selection"].hasFocus())
            self.assertFalse(window.config_path_edit.hasFocus())
        finally:
            self._close_window(window)

    def test_merged_observation_fields_use_uniform_vertical_spacing(self):
        window = self._make_window()
        try:
            window.resize(1100, 720)
            window.show()
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()

            def peer_gaps(*prefixes):
                widgets = window.parameter_form.field_widgets
                paths = [path for path in widgets if any(path.startswith(prefix) for prefix in prefixes)]
                ordered = sorted(
                    paths,
                    key=lambda path: widgets[path].mapToGlobal(widgets[path].rect().topLeft()).y(),
                )
                self.assertGreaterEqual(len(ordered), 2, ordered)
                gaps = []
                for first, second in zip(ordered, ordered[1:]):
                    upper = widgets[first]
                    lower = widgets[second]
                    gaps.append(
                        lower.mapToGlobal(lower.rect().topLeft()).y()
                        - upper.mapToGlobal(upper.rect().bottomLeft()).y()
                        - 1
                    )
                return gaps

            cartesian_gaps = peer_gaps("observation.schedule.")
            self.assertEqual(len(set(cartesian_gaps)), 1, cartesian_gaps)
            widgets = window.parameter_form.field_widgets
            sample_rate = widgets["observation.receiver_sampling.fast_sample_rate_hz"]
            extent = widgets["observation.target.extent_path_m"]
            sampling_gap = (
                extent.mapToGlobal(extent.rect().topLeft()).y()
                - sample_rate.mapToGlobal(sample_rate.rect().bottomLeft()).y()
                - 1
            )
            self.assertEqual(sampling_gap, cartesian_gaps[0])
            self.assertEqual(
                sample_rate.mapToGlobal(sample_rate.rect().topLeft()).x(),
                extent.mapToGlobal(extent.rect().topLeft()).x(),
            )
            readout = window.parameter_form.range_gate_readout
            self.assertIsNotNone(readout)
            readout_gap = (
                readout.mapToGlobal(readout.rect().topLeft()).y()
                - extent.mapToGlobal(extent.rect().bottomLeft()).y()
                - 1
            )
            self.assertEqual(readout_gap, sampling_gap)
            self.assertFalse(isinstance(readout, QLineEdit))

            _set_widget_value(widgets["observation.transmitter.state"], "geodetic")
            for _ in range(5):
                self.app.processEvents()
            geodetic_gaps = peer_gaps("observation.visibility.", "observation.schedule.")
            self.assertEqual(len(set(geodetic_gaps)), 1, geodetic_gaps)
        finally:
            self._close_window(window)

    def test_startup_scroll_extent_matches_card_bottom(self):
        window = self._make_window()
        try:
            window.resize(1280, 800)
            window.show()
            for _ in range(8):
                self.app.processEvents()
            form = window.parameter_form
            cards = form._cards[0]
            content_bottom = max(card.geometry().bottom() for card in cards.cards)
            bar = form.scroll.verticalScrollBar()
            scroll_extent = bar.maximum() + form.scroll.viewport().height()
            self.assertLessEqual(scroll_extent, content_bottom + 24)
            self.assertLessEqual(form.canvas.minimumHeight(), content_bottom + 24)
            self.assertEqual(cards.column_count, 2)
            wide_minimum = cards.card_minimum
            cards.card_minimum = cards.width()
            cards.reflow()
            for _ in range(4):
                self.app.processEvents()
            self.assertEqual(cards.column_count, 1)
            tall = form.canvas.minimumHeight()
            cards.card_minimum = wide_minimum
            cards.reflow()
            for _ in range(4):
                self.app.processEvents()
            self.assertEqual(cards.column_count, 2)
            self.assertLess(form.canvas.minimumHeight(), tall - 200)
        finally:
            self._close_window(window)

    def test_readout_focus_does_not_collapse_cards_to_one_column(self):
        window = self._make_window()
        try:
            window.resize(1280, 800)
            window.show()
            for _ in range(8):
                self.app.processEvents()
            form = window.parameter_form
            extent = form.field_widgets["observation.target.extent_path_m"]
            extent.edit.setFocus()
            self.app.processEvents()
            readout = form.range_gate_readout
            cards = form._cards[0]
            self.assertIsNotNone(readout)
            self.assertEqual(readout.focusPolicy(), Qt.FocusPolicy.NoFocus)
            self.assertEqual(readout.textInteractionFlags(), Qt.TextInteractionFlag.NoTextInteraction)
            self.assertGreaterEqual(cards.sizeHint().width(), cards.width())
            QTest.mouseClick(readout, Qt.MouseButton.LeftButton)
            for _ in range(8):
                self.app.processEvents()
            cards = form._cards[0]
            self.assertEqual(cards.column_count, 2)
            xs = {card.geometry().x() for card in cards.cards}
            self.assertGreater(len(xs), 1)
            self.assertGreater(min(card.geometry().width() for card in cards.cards), cards.card_minimum)
        finally:
            self._close_window(window)

    def test_range_gate_readout_reaches_the_viewport_when_scrolled_to_the_end(self):
        window = self._make_window()
        try:
            window.resize(1100, 640)
            window.show()
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            form = window.parameter_form
            readout = form.range_gate_readout
            self.assertIsNotNone(readout)
            viewport = form.scroll.viewport()
            content_bottom = readout.mapTo(form.scroll.widget(), readout.rect().bottomLeft()).y()
            target = max(0, content_bottom - viewport.height() + 1)
            bar = form.scroll.verticalScrollBar()
            self.assertLessEqual(target, bar.maximum())
            bar.setValue(target)
            for _ in range(5):
                self.app.processEvents()
            self.assertLessEqual(
                readout.mapToGlobal(readout.rect().bottomLeft()).y(),
                viewport.mapToGlobal(viewport.rect().bottomLeft()).y(),
            )
            self.assertGreaterEqual(
                readout.mapToGlobal(readout.rect().topLeft()).y(),
                viewport.mapToGlobal(viewport.rect().topLeft()).y(),
            )
        finally:
            self._close_window(window)

    def test_scattering_model_roundtrip_restores_mesh_configuration(self):
        window = self._make_window()
        try:
            _set_widget_value(window.scattering_model_combo, "mesh")
            self.app.processEvents()
            window._select_stage("echo")
            widgets = window.parameter_form.field_widgets
            original_model_path = window.config_data["echo"]["model_path"]
            original_rotation = window.config_data["echo"]["target"]["rotation_period_s"]
            self.assertNotIn("echo.scattering_model", widgets)

            _set_widget_value(window.scattering_model_combo, "point_target")
            self.app.processEvents()
            window._select_stage("echo")
            self.app.processEvents()
            self.assertNotIn("echo.model_path", window.parameter_form.field_widgets)
            self.assertNotIn("echo.target.rotation_period_s", window.parameter_form.field_widgets)
            self.assertNotIn("echo.scattering_model", window.parameter_form.field_widgets)

            _set_widget_value(window.scattering_model_combo, "mesh")
            self.app.processEvents()
            self.assertIn("echo.model_path", window.parameter_form.field_widgets)
            self.assertIn("echo.target.rotation_period_s", window.parameter_form.field_widgets)
            for path in (
                "echo.scattering_power",
                "echo.scattering_spot.enabled",
                "echo.scattering_spot.direction_body",
                "echo.scattering_spot.radius_deg",
                "echo.scattering_spot.strength",
            ):
                self.assertIn(path, window.parameter_form.field_widgets)
            self.assertEqual(window.config_data["echo"]["model_path"], original_model_path)
            self.assertEqual(
                window.config_data["echo"]["target"]["rotation_period_s"], original_rotation
            )
            pipeline.canonical_pipeline_config(window.config_data)
        finally:
            self._close_window(window)

    def test_invalid_vector_component_is_marked_and_blocks_validation(self):
        window = self._make_window()
        try:
            position = window.parameter_form.field_widgets["observation.target.position_m"]
            position.edits[0].setText("几个汉字")
            self.app.processEvents()
            self.assertTrue(position.edits[0].parentWidget().property("inputError"))
            self.assertFalse(window._validate_config())
            self.assertTrue(self.message_box.critical.called)
            self.assertEqual(
                window.config_data["observation"]["target"]["position_m"][0],
                299792458.0,
            )
        finally:
            self._close_window(window)

    def test_invalid_scalar_is_marked_and_blocks_validation(self):
        window = self._make_window()
        try:
            window._select_stage("echo")
            seed = window.parameter_form.field_widgets["echo.seed"]
            seed.setText("无效种子")
            self.app.processEvents()
            self.assertTrue(seed.property("inputError"))
            self.assertFalse(window._validate_config())
            self.assertTrue(self.message_box.critical.called)
            self.assertEqual(window.config_data["echo"]["seed"], 20250729)
        finally:
            self._close_window(window)

    def test_noise_enabled_toggle_hides_snr_and_seed(self):
        window = self._make_window()
        try:
            window._select_stage("echo")
            self.app.processEvents()
            form = window.parameter_form
            cards = [card.property("groupName") for card in form._cards[0].cards]
            self.assertIn("noise", cards)
            toggle = form.field_widgets["echo.noise_enabled"]
            self.assertIsInstance(toggle, BooleanFieldWidget)
            self.assertTrue(toggle.value())
            self.assertIn("echo.snr_db", form.field_widgets)
            self.assertIn("echo.seed", form.field_widgets)
            original_snr = window.config_data["echo"]["snr_db"]
            original_seed = window.config_data["echo"]["seed"]

            toggle.setChecked(False)
            self.app.processEvents()
            self.assertNotIn("echo.snr_db", form.field_widgets)
            self.assertNotIn("echo.seed", form.field_widgets)
            self.assertIn("echo.noise_enabled", form.field_widgets)
            self.assertIsNone(window.config_data["echo"]["snr_db"])
            self.assertNotIn("noise_enabled", window.config_data["echo"])

            # Noise toggle must not erase mesh target/scattering cards.
            _set_widget_value(window.scattering_model_combo, "mesh")
            self.app.processEvents()
            self.assertIn("echo.scattering_spot.enabled", form.field_widgets)
            form.field_widgets["echo.noise_enabled"].setChecked(False)
            self.app.processEvents()
            self.assertIn("echo.scattering_spot.enabled", form.field_widgets)
            self.assertIn("echo.model_path", form.field_widgets)

            form.field_widgets["echo.noise_enabled"].setChecked(True)
            self.app.processEvents()
            self.assertIn("echo.snr_db", form.field_widgets)
            self.assertIn("echo.seed", form.field_widgets)
            self.assertEqual(window.config_data["echo"]["snr_db"], original_snr)
            self.assertEqual(window.config_data["echo"]["seed"], original_seed)
            pipeline.canonical_pipeline_config(window.config_data)
        finally:
            self._close_window(window)

    def test_invalid_scattering_direction_is_not_silently_replaced(self):
        with self.assertRaisesRegex(NumericInputError, "散射热点方向"):
            np_vector3(["错误", 0.0, 0.0])
        with self.assertRaisesRegex(NumericInputError, "非零"):
            np_vector3([0.0, 0.0, 0.0])

    def test_waveform_and_scattering_switches_leave_canonical_config(self):
        window = self._make_window()
        try:
            for waveform, scattering in (
                ("chirp_pulse_train", "point_target"),
                ("continuous_wave", "mesh"),
                ("chirp_pulse_train", "mesh"),
                ("continuous_wave", "point_target"),
                ("continuous_wave", "mesh"),
            ):
                _set_widget_value(window.waveform_combo, waveform)
                self.app.processEvents()
                _set_widget_value(window.scattering_model_combo, scattering)
                self.app.processEvents()
                window._select_stage("inversion")
                self.app.processEvents()
                self.assertEqual(
                    window.config_data["echo"]["waveform"]["type"], waveform
                )
                self.assertNotIn("waveform", window.config_data["observation"])
                if waveform == "chirp_pulse_train":
                    self.assertIn("transmit", window.config_data["observation"])
                else:
                    self.assertNotIn("transmit", window.config_data["observation"])
                self.assertEqual(
                    window.config_data["echo"]["scattering_model"], scattering
                )
                pipeline.canonical_pipeline_config(window.config_data)
        finally:
            self._close_window(window)

    def test_mode_switch_does_not_unparent_visible_widgets(self):
        window = self._make_window()
        try:
            window.show()
            self.app.processEvents()
            flashes = []
            original = QWidget.setParent

            def wrapped(self_widget, parent, *args, **kwargs):
                if parent is None and self_widget.isVisible() and self_widget is not window:
                    flashes.append(self_widget.objectName() or type(self_widget).__name__)
                return original(self_widget, parent, *args, **kwargs)

            with mock.patch.object(QWidget, "setParent", wrapped):
                _set_widget_value(window.waveform_combo, "chirp_pulse_train")
                self.app.processEvents()
                _set_widget_value(window.scattering_model_combo, "point_target")
                self.app.processEvents()
            self.assertEqual(flashes, [])
        finally:
            self._close_window(window)

    def test_chrome_layout_places_scattering_only_in_echo_stage(self):
        window = self._make_window()
        try:
            window.show()
            self.app.processEvents()
            self.assertFalse(window.findChildren(QFrame, "experimentModePanel"))
            self.assertTrue(window.waveform_combo.isVisible())
            self.assertFalse(window.scattering_model_combo.isVisible())
            self.assertTrue(window.progress.isVisible())
            self.assertFalse(hasattr(window, "status_label"))
            self.assertFalse(hasattr(window, "stage_title"))
            self.assertLess(window.progress.mapToGlobal(window.progress.rect().topLeft()).y(), window.parameter_form.mapToGlobal(window.parameter_form.rect().topLeft()).y())
            for stage in ("observation", "echo", "inversion"):
                if window.current_stage != stage:
                    window._select_stage(stage)
                self.app.processEvents()
                self.assertEqual(window.scattering_model_combo.isVisible(), stage == "echo")
                if stage == "echo":
                    self.assertLess(window.scattering_model_combo.mapToGlobal(window.scattering_model_combo.rect().topLeft()).y(), window.parameter_form.mapToGlobal(window.parameter_form.rect().topLeft()).y())
                self.assertNotIn(
                    "observation.waveform.type", window.parameter_form.field_widgets
                )
                self.assertNotIn("echo.scattering_model", window.parameter_form.field_widgets)
        finally:
            self._close_window(window)

    def test_schedule_save_contract_keeps_only_active_selection_fields(self):
        window = self._make_window()
        try:
            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            form = window.parameter_form
            _set_widget_value(form.field_widgets["observation.schedule.selection"], "automatic")
            self.app.processEvents()
            form.field_widgets["observation.schedule.random_selection"].setChecked(True)
            for _ in range(5):
                self.app.processEvents()
            schedule = form.collect()["observation"]["schedule"]
            self.assertEqual(schedule["selection"], "random_visible_time")
            self.assertIn("random_seed", schedule)
            self.assertNotIn("runs", schedule)
            form.field_widgets["observation.schedule.random_selection"].setChecked(False)
            for _ in range(5):
                self.app.processEvents()
            schedule = form.collect()["observation"]["schedule"]
            self.assertEqual(schedule["selection"], "equal_visible_time")
            self.assertNotIn("random_seed", schedule)
            self.assertNotIn("runs", schedule)
            self.assertIn("run_count", schedule)
            self.assertIn("run_duration_s", schedule)
            _set_widget_value(form.field_widgets["observation.schedule.selection"], "manual")
            for _ in range(5):
                self.app.processEvents()
            collected = form.collect()
            schedule = collected["observation"]["schedule"]
            self.assertEqual(schedule["selection"], "manual")
            self.assertIn("runs", schedule)
            self.assertNotIn("run_count", schedule)
            self.assertNotIn("random_seed", schedule)
            pipeline.canonical_pipeline_config(collected)
        finally:
            self._close_window(window)

    def test_schedule_feedback_labels_approximate_capacity(self):
        payload = {
            "campaign_duration_s": 10.0,
            "visibility_applicable": False,
            "visibility_computed": True,
            "allow_unobservable": False,
            "run_feasible": True,
            "max_run_count": 3,
            "occupied_duration_s": 1.0,
            "capacity_is_approximate": True,
            "run_intervals_elapsed_s": [[0.0, 1.0]],
            "reservation_intervals_elapsed_s": [[0.0, 1.5]],
            "adc_preview_intervals_elapsed_s": [[0.2, 1.4]],
            "visibility_windows_elapsed_s": [[0.0, 10.0]],
        }
        feedback = ScheduleFeedbackWidget(lambda: None)
        try:
            feedback.show_plan(payload, 2)
            self.assertIn("近似可排列最多 3 次 Run", feedback.summary.text())
            self.assertIn("不表示正式计划已通过光行时解算", feedback.summary.text())
        finally:
            feedback.close()
            feedback.deleteLater()
            self.app.processEvents()

    def test_pulse_width_offers_microsecond_millisecond_and_second(self):
        from rotation_gui.schema import EDITABLE_UNIT_WIDTH, FIXED_UNIT_WIDTH, UNIT_CHOICES

        options = (("s", 1.0), ("ms", 1.0e-3), ("µs", 1.0e-6))
        micro = UnitValueWidget(4.0e-5, options, editable_unit=True, label="pulse")
        milli = UnitValueWidget(0.01, options, editable_unit=True, label="duration")
        fixed = UnitValueWidget(2.0, (("Hz", 1.0),), editable_unit=False, label="rate")
        radians = UnitValueWidget(180.0, UNIT_CHOICES["initial_phase_deg"], editable_unit=True, label="angle")
        window = self._make_window()
        try:
            for choices in UNIT_CHOICES.values():
                factors = [factor for _label, factor in choices]
                self.assertEqual(factors, sorted(factors, reverse=True))
            self.assertEqual(micro.unit_combo.currentText(), "µs")
            self.assertAlmostEqual(float(micro.edit.text()), 40.0)
            self.assertAlmostEqual(micro.value(), 4.0e-5)
            self.assertEqual(milli.unit_combo.currentText(), "ms")
            self.assertAlmostEqual(float(milli.edit.text()), 10.0)
            self.assertAlmostEqual(milli.value(), 0.01)

            _set_widget_value(window.waveform_combo, "chirp_pulse_train")
            self.app.processEvents()
            widget = window.parameter_form.field_widgets["observation.transmit.pulse_width_s"]
            labels = [widget.unit_combo.itemText(i) for i in range(widget.unit_combo.count())]
            self.assertEqual(labels, ["s", "ms", "µs"])
            self.assertEqual(widget.unit_combo.width(), EDITABLE_UNIT_WIDTH)
            self.assertEqual(fixed.unit_suffix.width(), FIXED_UNIT_WIDTH)
            self.assertLessEqual(EDITABLE_UNIT_WIDTH, 64)
            self.assertLessEqual(FIXED_UNIT_WIDTH, 32)
            self.assertEqual(radians.unit_combo.currentText(), "π")
            self.assertEqual(radians.unit_combo.width(), EDITABLE_UNIT_WIDTH)
            self.assertIn("π rad", radians.unit_combo.toolTip())
            self.assertAlmostEqual(radians.value(), 180.0)
            micro.unit_combo.setCurrentText("ms")
            self.assertAlmostEqual(micro.value(), 0.04)
            micro.unit_combo.setCurrentText("s")
            self.assertAlmostEqual(micro.value(), 40.0)
            collected = window.parameter_form.collect()
            self.assertAlmostEqual(
                float(collected["observation"]["transmit"]["pulse_width_s"]),
                float(window.config_data["observation"]["transmit"]["pulse_width_s"]),
            )
            widget.unit_combo.setCurrentText("ms")
            collected = window.parameter_form.collect()
            self.assertAlmostEqual(
                float(collected["observation"]["transmit"]["pulse_width_s"]),
                float(widget.edit.text()) * 1.0e-3,
            )
        finally:
            micro.close()
            milli.close()
            fixed.close()
            radians.close()
            micro.deleteLater()
            milli.deleteLater()
            fixed.deleteLater()
            radians.deleteLater()
            self._close_window(window)
            self.app.processEvents()

    def test_unit_value_focus_uses_border_not_fill(self):
        from rotation_gui.styling import GUI_STYLE

        self.assertNotIn("QWidget#unitValue QLineEdit:focus { background: #edf5ff; }", GUI_STYLE)
        widget = UnitValueWidget(1.0, (("s", 1.0),), label="duration")
        try:
            widget.show()
            self.app.processEvents()
            widget.edit.setFocus(Qt.FocusReason.OtherFocusReason)
            self.app.processEvents()
            self.assertTrue(widget.property("focused"))
            widget.edit.clearFocus()
            self.app.processEvents()
            self.assertFalse(widget.property("focused"))
        finally:
            widget.close()
            widget.deleteLater()
            self.app.processEvents()

    def test_schedule_preview_stays_stale_until_refresh(self):
        with mock.patch(
            "observation.src.campaign_planning.resolve_campaign_run_plan",
            wraps=resolve_campaign_run_plan,
        ) as resolve:
            window = self._make_window()
            try:
                window.show()
                for _ in range(8):
                    self.app.processEvents()
                form = window.parameter_form
                feedback = form.schedule_feedback
                self.assertIsNotNone(feedback)
                self.assertIn("请点击「刷新预览」", feedback.summary.text())
                self.assertEqual(resolve.call_count, 0)
                feedback.refresh_button.click()
                for _ in range(8):
                    self.app.processEvents()
                self.assertGreaterEqual(resolve.call_count, 1)
                after_refresh = resolve.call_count
                run_count = form.field_widgets["observation.schedule.run_count"]
                _set_widget_value(run_count, 2)
                run_count.editingFinished.emit()
                for _ in range(5):
                    self.app.processEvents()
                self.assertEqual(resolve.call_count, after_refresh)
                self.assertIn("参数已更新，请刷新预览", feedback.summary.text())
                feedback.refresh_button.click()
                for _ in range(8):
                    self.app.processEvents()
                self.assertGreater(resolve.call_count, after_refresh)
            finally:
                self._close_window(window)

    def test_cartesian_plan_card_contains_feedback_bottom(self):
        window = self._make_window()
        try:
            window.resize(1100, 720)
            window.show()
            for _ in range(8):
                self.app.processEvents()
            form = window.parameter_form
            _set_widget_value(form.field_widgets["observation.transmitter.state"], "geodetic")
            for _ in range(8):
                self.app.processEvents()
            _set_widget_value(form.field_widgets["observation.transmitter.state"], "cartesian")
            for _ in range(8):
                self.app.processEvents()
            form.schedule_feedback.refresh_button.click()
            for _ in range(10):
                self.app.processEvents()
            card = next(
                card
                for canvas in form._cards
                for card in canvas.cards
                if card.property("groupName") == "plan"
            )
            feedback = form.schedule_feedback
            margin_bottom = card.layout().contentsMargins().bottom()
            detail_local = feedback.detail.mapTo(card, feedback.detail.rect().bottomRight()).y()
            feedback_local = feedback.mapTo(card, feedback.rect().bottomRight()).y()
            self.assertLessEqual(detail_local + margin_bottom, card.height() + 1)
            self.assertLessEqual(feedback_local + margin_bottom, card.height() + 1)
            card_bottom = card.mapToGlobal(card.rect().bottomRight()).y()
            detail_bottom = feedback.detail.mapToGlobal(feedback.detail.rect().bottomRight()).y()
            feedback_bottom = feedback.mapToGlobal(feedback.rect().bottomRight()).y()
            self.assertLessEqual(detail_bottom, card_bottom + 1)
            self.assertLessEqual(feedback_bottom, card_bottom + 1)
            viewport = form.scroll.viewport()
            content_bottom = feedback.detail.mapTo(form.scroll.widget(), feedback.detail.rect().bottomLeft()).y()
            target = max(0, content_bottom - viewport.height() + 1)
            bar = form.scroll.verticalScrollBar()
            self.assertLessEqual(target, bar.maximum())
            bar.setValue(target)
            for _ in range(5):
                self.app.processEvents()
            self.assertLessEqual(
                feedback.detail.mapToGlobal(feedback.detail.rect().bottomRight()).y(),
                viewport.mapToGlobal(viewport.rect().bottomLeft()).y() + 1,
            )
        finally:
            self._close_window(window)

    def test_echo_compute_chunk_fields_use_readable_labels(self):
        window = self._make_window()
        try:
            window.config_path_edit.setText(
                str(storage.ROOT / "configs" / "chirp_mesh_target_test.json")
            )
            window._load_config_from_entry()
            window._select_stage("echo")
            for _ in range(8):
                self.app.processEvents()
            labels = [
                label.text()
                for label in window.parameter_form.findChildren(QLabel)
                if label.objectName() == "fieldLabel"
            ]
            self.assertIn("面元计算块", labels)
            self.assertIn("样点计算块", labels)
            self.assertIn("脉冲计算批次", labels)
            self.assertNotIn("facet_chunk_size", labels)
            self.assertNotIn("fast_sample_chunk_size", labels)
            self.assertNotIn("Chirp 脉冲批量", labels)
            widget = window.parameter_form.field_widgets["echo.facet_chunk_size"]
            self.assertIn("不改变物理模型", widget.toolTip())
            self.assertIn("echo.facet_chunk_size", widget.toolTip())
        finally:
            self._close_window(window)


if __name__ == "__main__":
    unittest.main()
