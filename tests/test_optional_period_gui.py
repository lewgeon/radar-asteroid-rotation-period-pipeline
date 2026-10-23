"""Optional inversion controls: actual event loop, focus, scroll and JSON round-trip."""
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from PySide6.QtGui import QFontDatabase
from rotation_gui.window.parameter_form import ParameterForm
from rotation_gui.styling import GUI_STYLE
from inversion.src.dataset import normalize_inversion_policy


def pump(app):
    for _ in range(12):
        app.processEvents()


@pytest.mark.parametrize("width,height", [(650, 500), (1100, 850)])
def test_optional_controls_toggle_focus_scroll_reload_and_render(width, height):
    app = QApplication.instance() or QApplication([])
    # Windows offscreen plugin may not discover system fonts automatically.
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    cfg = json.loads(Path("configs/paras_for_70m_3h.json").read_text(encoding="utf-8"))
    # The echo pole must never fill the independent inversion pole.
    cfg["inversion"].pop("harmonics", None)
    form = ParameterForm()
    form.setStyleSheet(GUI_STYLE)
    form.resize(width, height)
    form.render(cfg, "inversion")
    form.show()
    form.activateWindow()
    pump(app)
    try:
        assert form.field_widgets["inversion.refine_period"].isChecked()
        assert "inversion.harmonics" not in form.field_widgets
        assert "inversion.spin_axis_ra_deg" not in form.field_widgets
        bar = form.scroll.verticalScrollBar()
        for key in ("los_phase_compensation", "multi_harmonic_enabled", "compare_methods"):
            path = "inversion."+key
            for on in (True, False, True):
                bar.setValue(min(50, bar.maximum()))
                before_value, before_max = bar.value(), bar.maximum()
                form.field_widgets[path].setChecked(on)
                pump(app)
                assert bar.value() == before_value
                assert bar.maximum() >= before_max
                assert form.field_widgets[path].checkbox.hasFocus()
        # No automatic truth copy. Blank input may be switched off again.
        assert form.field_widgets["inversion.spin_axis_ra_deg"].text() == ""
        collected = form.collect()
        with pytest.raises(ValueError, match="显式提供"):
            normalize_inversion_policy(collected["inversion"], "chirp")
        form.field_widgets["inversion.spin_axis_ra_deg"].setText("105")
        form.field_widgets["inversion.spin_axis_dec_deg"].setText("-66")
        form.field_widgets["inversion.harmonics"].setText("3")
        form.field_widgets["inversion.refine_period"].setChecked(False)
        estimator=form.field_widgets["inversion.doppler_estimator"]
        assert estimator.itemText(estimator.findData('spectral_moments'))=='FFT功率谱法（默认）'
        assert estimator.itemText(estimator.findData('narrowband_lag'))=='相关法（实验性）'
        estimator.setCurrentIndex(estimator.findData('narrowband_lag'))
        collected = json.loads(json.dumps(form.collect()))
        normalize_inversion_policy(collected["inversion"], "chirp")
        form.render(collected, "inversion", preserve_scroll=False)
        pump(app)
        assert form.collect()["inversion"] == collected["inversion"]
        assert collected['inversion']['doppler_estimator']=='narrowband_lag'
        assert float(form.field_widgets["inversion.spin_axis_ra_deg"].text()) == 105
        assert not form.field_widgets["inversion.refine_period"].isChecked()
        last = form.field_widgets["inversion.compare_methods"]
        bar.setValue(bar.maximum())
        pump(app)
        bottom = last.mapTo(form.scroll.viewport(), QPoint(0, last.height())).y()
        assert bottom <= form.scroll.viewport().height()
        # Peer checkboxes use a common left anchor and label follows checkbox.
        boxes = [form.field_widgets["inversion."+k].checkbox for k in
                 ("los_phase_compensation", "multi_harmonic_enabled", "refine_period", "compare_methods")]
        assert len({box.mapToGlobal(QPoint(0, 0)).x() for box in boxes}) == 1
        out = Path("tmp/optional_period_gui")
        out.mkdir(parents=True, exist_ok=True)
        assert form.grab().save(str(out/f"enabled_{width}.png"))
        for key in ("compare_methods", "multi_harmonic_enabled", "los_phase_compensation"):
            form.field_widgets["inversion."+key].setChecked(False)
            pump(app)
        assert "inversion.harmonics" not in form.field_widgets
        assert "inversion.spin_axis_ra_deg" not in form.field_widgets
        assert form.collect()["inversion"]["harmonics"] == 3
        assert form.grab().save(str(out/f"disabled_{width}.png"))
        form.field_widgets["inversion.multi_harmonic_enabled"].setChecked(True)
        pump(app)
        form.field_widgets["inversion.harmonics"].setText("")
        form.field_widgets["inversion.multi_harmonic_enabled"].setChecked(False)
        pump(app)
        assert "inversion.harmonics" not in form.field_widgets
        form.field_widgets["inversion.los_phase_compensation"].setChecked(True)
        pump(app)
        form.field_widgets["inversion.spin_axis_ra_deg"].setText("invalid")
        form.field_widgets["inversion.los_phase_compensation"].setChecked(False)
        pump(app)
        assert "inversion.spin_axis_ra_deg" not in form.field_widgets
        normalize_inversion_policy(form.collect()["inversion"], "chirp")
    finally:
        form.close()
        form.deleteLater()
        pump(app)
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


def test_cw_hides_and_strips_chirp_enhancements():
    app = QApplication.instance() or QApplication([])
    cfg = {"echo": {"waveform": {"type": "continuous_wave"}},
           "inversion": {"period_min_s": 1, "period_max_s": 3, "period_grid_size": 50,
                         "refine_period": False, "compare_methods": True,
                         "los_phase_compensation": True, "harmonics": 3,"doppler_estimator":"narrowband_lag"}}
    form = ParameterForm()
    form.render(cfg, "inversion")
    pump(app)
    try:
        assert "inversion.refine_period" not in form.field_widgets
        assert "inversion.compare_methods" not in form.field_widgets
        assert "refine_period" not in form.collect()["inversion"]
        assert 'doppler_estimator' not in form.collect()['inversion']
    finally:
        form.close()
        form.deleteLater()
        pump(app)


@pytest.mark.parametrize("width,height", [(650, 500), (1100, 850)])
def test_compute_and_uncertainty_controls_event_loop_round_trip(width, height, tmp_path):
    app = QApplication.instance() or QApplication([])
    font_id = QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    cfg = json.loads(Path("configs/paras_for_70m_3h.json").read_text(encoding="utf-8"))
    cfg["inversion"].update(compute_device="cpu", uncertainty_method="none")
    form = ParameterForm()
    form.setStyleSheet(GUI_STYLE)
    form.resize(width, height)
    form.render(cfg, "inversion")
    form.show()
    form.activateWindow()
    pump(app)
    try:
        device = form.field_widgets["inversion.compute_device"]
        assert device.currentData() == "cpu"
        assert device.itemText(device.findData('cpu'))=='CPU（默认）'
        assert device.itemText(device.findData('cuda:0'))=='GPU（CUDA:0）'
        fusion = form.field_widgets['inversion.period_selection']
        assert fusion.currentData() == 'predictive_joint'
        for choice in ('legacy_consensus', 'predictive_joint', 'legacy_consensus'):
            fusion.setFocus()
            fusion.setCurrentIndex(fusion.findData(choice))
            pump(app)
            assert fusion.hasFocus()
            assert form.collect()['inversion']['period_selection'] == choice
        assert "inversion.uncertainty_replicates" not in form.field_widgets
        for choice in ("cuda:0", "cpu", "cuda:0"):
            device.setFocus()
            device.setCurrentIndex(device.findData(choice))
            pump(app)
            assert device.hasFocus()
            assert form.collect()["inversion"]["compute_device"] == choice
        bar = form.scroll.verticalScrollBar()
        path = "inversion.uncertainty_method"
        for choice in ("run_bootstrap", "none", "run_bootstrap", "none", "run_bootstrap"):
            control = form.field_widgets[path]
            form.scroll.ensureWidgetVisible(control)
            pump(app)
            before_value, before_max = bar.value(), bar.maximum()
            control.setCurrentIndex(control.findData(choice))
            pump(app)
            assert bar.value() == before_value
            assert bar.maximum() >= before_max
            assert form.field_widgets[path].hasFocus()
            assert ("inversion.uncertainty_replicates" in form.field_widgets) == (choice == "run_bootstrap")
            assert ("inversion.uncertainty_seed" in form.field_widgets) == (choice == "run_bootstrap")
            if choice == "run_bootstrap":
                bar.setValue(bar.maximum())
                pump(app)
                last = form.field_widgets["inversion.uncertainty_seed"]
                bottom = last.mapTo(form.scroll.viewport(), QPoint(0, last.height())).y()
                assert bottom <= form.scroll.viewport().height()
                assert bottom > 0
        form.field_widgets["inversion.uncertainty_replicates"].setText("37")
        form.field_widgets["inversion.uncertainty_seed"].setText("765")
        collected = form.collect()
        normalize_inversion_policy(collected["inversion"], "chirp")
        output = tmp_path / "gpu_uncertainty.json"
        output.write_text(json.dumps(collected), encoding="utf-8")
        restored = json.loads(output.read_text(encoding="utf-8"))
        form.render(restored, "inversion")
        pump(app)
        assert form.collect()["inversion"] == collected["inversion"]
        assert form.field_widgets["inversion.compute_device"].currentData() == "cuda:0"
        assert form.field_widgets[path].currentData() == "run_bootstrap"
        assert form.field_widgets['inversion.period_selection'].currentData() == 'legacy_consensus'
        peers = [form.field_widgets['inversion.' + key] for key in
                 ('period_selection', 'uncertainty_method', 'uncertainty_replicates', 'uncertainty_seed')]
        assert len({widget.mapToGlobal(QPoint(0, 0)).x() for widget in peers}) == 1
        gaps = [lower.mapToGlobal(QPoint(0, 0)).y() -
                upper.mapToGlobal(QPoint(0, upper.height())).y()
                for upper, lower in zip(peers, peers[1:])]
        assert len(set(gaps)) == 1
        form.scroll.ensureWidgetVisible(form.field_widgets['inversion.period_selection'])
        pump(app)
        screenshots = Path('tmp/period_upgrade_20261016')
        screenshots.mkdir(parents=True, exist_ok=True)
        assert form.grab().save(str(screenshots/f'fusion_gui_{width}_visual_final.png'))
        assert form.field_widgets["inversion.uncertainty_replicates"].text() == "37"
        assert form.field_widgets["inversion.uncertainty_seed"].text() == "765"
        restored["echo"]["waveform"]["type"] = "continuous_wave"
        form.render(restored, "inversion")
        pump(app)
        stripped = form.collect()["inversion"]
        for key in ("compute_device", "uncertainty_method", "uncertainty_replicates", "uncertainty_seed", "period_selection"):
            assert "inversion." + key not in form.field_widgets
            assert key not in stripped
        assert form.grab().save(str(screenshots/f'fusion_gui_cw_{width}_visual_final.png'))
    finally:
        form.close()
        form.deleteLater()
        pump(app)
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)
