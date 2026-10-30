"""Production dispatch, policy serialization and live Qt precision controls."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from inversion.src.dataset import normalize_inversion_policy
from inversion.src.precision_selection import select_precision_period
from inversion.src.period_uncertainty import assess_period_uncertainty
from inversion.src.selection_report import write_selection_report


@pytest.mark.parametrize('policy', ['predictive_skill_energy', 'spherical_response'])
def test_precision_configuration_contract_and_uncertainty(policy, tmp_path):
    cfg = dict(cpi_duration_s=16, period_selection=policy,
               spin_axis_ra_deg=105, spin_axis_dec_deg=-66)
    assert normalize_inversion_policy(cfg, 'chirp')['period_selection'] == policy
    with pytest.raises(ValueError):
        normalize_inversion_policy(cfg, 'cw')
    with pytest.raises(ValueError, match='scatter_centroid'):
        normalize_inversion_policy(dict(cfg, period_time_role='receive_centroid'), 'chirp')
    if policy == 'spherical_response':
        with pytest.raises(ValueError, match='显式提供'):
            normalize_inversion_policy(dict(cpi_duration_s=16, period_selection=policy), 'chirp')
    for method in ('none', 'run_bootstrap'):
        report = assess_period_uncertainty([], {}, [], {}, dict(cfg, uncertainty_method=method))
        assert report['final_3sigma_interval_s'] is None
        assert report['selection_policy'] == policy
        assert report['enabled'] == (method != 'none')
        assert report['status'] == ('unavailable' if method != 'none' else 'not_evaluated')
        from inversion.src.period_uncertainty import write_uncertainty_report
        write_uncertainty_report(tmp_path, report)
        page = (tmp_path/'period_uncertainty.html').read_text(encoding='utf-8')
        assert '本次没有执行Run重采样' in page
        assert '新精度策略本次未计算这项诊断' in page
        assert '重采样在原始周期搜索范围内重新搜索并执行原共识规则' not in page
    with pytest.raises(ValueError, match='spectral_moments'):
        normalize_inversion_policy(dict(cfg, doppler_estimator='narrowband_lag'), 'chirp')


def test_full_rotation_phase_contract_and_default_unchanged():
    cfg = dict(cpi_duration_s=16, period_selection='predictive_skill_energy',
               los_phase_compensation=True, spin_axis_ra_deg=105, spin_axis_dec_deg=-66)
    with pytest.raises(ValueError, match='full_rotation'):
        normalize_inversion_policy(cfg, 'chirp')
    normalize_inversion_policy(dict(cfg, phase_period_convention='full_rotation'), 'chirp')
    assert 'period_selection' not in normalize_inversion_policy(dict(cpi_duration_s=16), 'chirp')


@pytest.mark.parametrize('extra', [
    {'period_selection': 'profile_confidence_set'},
    {'profile_confidence': {'harmonics': [1]}},
])
def test_archived_research_configuration_is_rejected(extra):
    with pytest.raises(ValueError):
        normalize_inversion_policy(dict(cpi_duration_s=16, **extra), 'chirp')


@pytest.mark.parametrize('policy', ['predictive_skill_energy', 'spherical_response'])
def test_dispatch_retains_identity_and_rejects_unvalidated_paths(policy):
    t = np.arange(20.)
    echo = SimpleNamespace(scatter_elapsed_s=t, tx_los_icrs=np.ones((20, 3)),
                           rx_los_icrs=np.ones((20, 3)))
    cfg = dict(period_selection=policy, period_min_s=3., period_max_s=10.,
               period_grid_size=20, harmonics=99, spin_axis_ra_deg=105,
               spin_axis_dec_deg=-66, los_phase_compensation=True, refine_period=False)
    features = {'total_power': t}
    weights = np.ones(20)
    target = ('inversion.src.predictive_energy.select_predictive_energy_period' if policy == 'predictive_skill_energy'
              else 'inversion.src.spherical_response.select_spherical_response_period')
    with patch(target, return_value={'policy': policy}) as choose:
        result = select_precision_period(t, features, t, weights, echo, cfg,
                                         processing_path='cpi', phase_offset=t)
        assert result['policy'] == policy
        args, kwargs = choose.call_args
        assert args[1] is features
        assert 'harmonics' not in kwargs
        if policy == 'predictive_skill_energy':
            assert kwargs['weights'] is weights
            assert kwargs['phase_offset'] is t
            assert kwargs['refine_period'] is False
        else:
            assert kwargs['scatter_elapsed_s'] is echo.scatter_elapsed_s
            assert kwargs['effective_sample_count'] is weights
    with pytest.raises(ValueError, match='逐脉冲'):
        select_precision_period(t, features, t, weights, echo, cfg, processing_path='pulse_fallback')
    for field in ('window_overlap', 'signal_echo_overlap'):
        setattr(echo, field, np.array([True]))
        with pytest.raises(ValueError, match='重叠'):
            select_precision_period(t, features, t, weights, echo, cfg, processing_path='cpi')
        setattr(echo, field, np.array([False]))


def test_response_production_path_does_not_apply_unrelated_longitude_tolerance():
    from inversion.src import inversion as core
    t = np.arange(500.)
    runs = np.repeat(np.arange(100), 5)
    values = np.sin(t/17)
    features = SimpleNamespace(times_s=t, total_power=values, doppler_centroid_hz=values,
        rms_bandwidth_hz=values, range_centroid_s=values, energy_range_width_90_s=values,
        effective_sample_count=np.r_[0., np.ones(499)],
        doppler_window_rms_hz=np.ones(500), doppler_nyquist_edge_fraction=np.zeros(500),
        doppler_nyquist_edge_half_width_hz=np.ones(500))
    dynamic = SimpleNamespace(times_s=t, delays_s=np.array([0.]))
    stage = dict(aligned=None, dynamic=dynamic, features=features, feature_times=t,
        processing_times=t, processing_path='cpi', weights=np.ones(500), time_axis_role='scatter_elapsed_s',
        notices=[], run_id=runs, pulse_count=500, profiles=dynamic,
        cpi_windows=np.column_stack([np.arange(500), np.arange(500)+1]))
    los = np.tile([1e-10, 0., 1.], (500, 1))
    echo = SimpleNamespace(iq=np.zeros((500, 1)), scatter_elapsed_s=t, tx_los_icrs=los, rx_los_icrs=los)
    cfg = dict(period_selection='spherical_response', los_phase_compensation=True,
        spin_axis_ra_deg=0., spin_axis_dec_deg=90., period_min_s=10., period_max_s=100., period_grid_size=20)
    estimate = core.PeriodEstimate(50., (), np.array([10., 100.]), np.array([0., 1.]))
    report = dict(policy='spherical_response', period_s=50., status='candidate')
    with patch.object(core, 'prepare_chirp_observations', return_value=stage), \
         patch.object(core, 'multi_harmonic_lomb_scargle', return_value=estimate), \
         patch.object(core, 'add_harmonics', side_effect=lambda result, *args: result), \
         patch.object(core, 'effective_look_phase', side_effect=AssertionError('unrelated old tolerance')), \
         patch('inversion.src.precision_selection.select_precision_period', return_value=report) as select:
        result = core._estimate_chirp_rotation(echo, cfg)
    assert result.selection_report == report
    assert not result.search_diagnostics['method_options']['los_phase_compensation']
    assert select.call_args.args[3][0] == 0.  # Do not hide invalid raw counts behind epsilon clipping.


@pytest.mark.parametrize('policy', ['predictive_skill_energy', 'spherical_response'])
def test_real_cli_rejects_unsupported_cpi_and_preserves_failure_status(tmp_path, policy):
    import subprocess
    import sys
    from tests.test_inversion_feature_preview import InversionFeaturePreviewTests
    source = tmp_path/'echo/echo.npz'
    InversionFeaturePreviewTests().write_echo(source)
    cfg = dict(cpi_duration_s=20., cpi_hop_duration_s=.4, period_min_s=1.,
        period_max_s=3., period_grid_size=20, period_selection=policy,
        spin_axis_ra_deg=105., spin_axis_dec_deg=-66.)
    path = tmp_path/'config.json'
    path.write_text(json.dumps(cfg), encoding='utf-8')
    output = tmp_path/'result'
    done = subprocess.run([sys.executable, 'inversion/scripts/estimate_period.py',
        '--echo', str(source), '--config', str(path), '--output', str(output)],
        capture_output=True, encoding='utf-8', errors='replace', timeout=90)
    assert done.returncode != 0
    failure = json.loads((output/'period_selection_failure.json').read_text(encoding='utf-8'))
    assert failure['policy'] == policy
    assert failure['status'] == 'failed'
    assert '逐脉冲' in failure['message']
    assert not (output/'inversion_complete.json').exists()


@pytest.mark.parametrize('width,height', [(650, 500), (1100, 850)])
def test_precision_gui_toggle_axis_focus_save_reload(width, height, tmp_path):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtCore import QPoint
    from rotation_gui.window.parameter_form import ParameterForm
    from rotation_gui.styling import GUI_STYLE
    from tests.test_optional_period_gui import pump
    app = QApplication.instance() or QApplication([])
    font_id = QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    cfg = json.loads(Path('configs/paras_for_70m_3h.json').read_text(encoding='utf-8'))
    form = ParameterForm()
    form.setStyleSheet(GUI_STYLE)
    form.resize(width, height)
    form.render(cfg, 'inversion')
    form.show()
    form.activateWindow()
    pump(app)
    try:
        for policy in ('predictive_skill_energy', 'spherical_response', 'predictive_joint',
                       'spherical_response', 'predictive_skill_energy'):
            control = form.field_widgets['inversion.period_selection']
            assert [control.itemData(i) for i in range(control.count())] == [
                'predictive_joint', 'legacy_consensus',
                'predictive_skill_energy', 'spherical_response']
            form.scroll.ensureWidgetVisible(control)
            control.setFocus()
            pump(app)
            before = form.scroll.verticalScrollBar().value()
            control.setCurrentIndex(control.findData(policy))
            pump(app)
            assert form.scroll.verticalScrollBar().value() == before
            assert form.field_widgets['inversion.period_selection'].hasFocus()
            assert ('inversion.spin_axis_ra_deg' in form.field_widgets) == (policy == 'spherical_response')
            if policy == 'spherical_response':
                for key, value in (('spin_axis_ra_deg', '105'), ('spin_axis_dec_deg', '-66')):
                    form.field_widgets['inversion.'+key].setText(value)
            data = form.collect()
            assert data['inversion']['period_selection'] == policy
            normalize_inversion_policy(data['inversion'], 'chirp')
            path = tmp_path/'roundtrip.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            form.render(json.loads(path.read_text(encoding='utf-8')), 'inversion')
            pump(app)
            assert form.collect()['inversion'] == data['inversion']
            if policy == 'spherical_response':
                folder = Path('tmp/precision_gui')
                folder.mkdir(parents=True, exist_ok=True)
                form.scroll.verticalScrollBar().setValue(form.scroll.verticalScrollBar().maximum())
                pump(app)
                assert form.grab().save(str(folder/f'spherical_{width}.png'))
        form.scroll.verticalScrollBar().setValue(form.scroll.verticalScrollBar().maximum())
        pump(app)
        last = form.field_widgets['inversion.compare_methods']
        assert last.mapTo(form.scroll.viewport(), QPoint(0, last.height())).y() <= form.scroll.viewport().height()
        folder = Path('tmp/precision_gui')
        folder.mkdir(parents=True, exist_ok=True)
        assert form.grab().save(str(folder/f'precision_{width}.png'))
    finally:
        form.close()
        form.deleteLater()
        pump(app)
        if font_id >= 0:
            QFontDatabase.removeApplicationFont(font_id)


@pytest.mark.parametrize('policy,needle', [('predictive_skill_energy', 'J越大越好'), ('spherical_response', '损失越小越好')])
def test_selection_html_describes_actual_strategy(tmp_path, policy, needle):
    report = dict(period_s=100., policy=policy, status='candidate', diagnostics={})
    write_selection_report(tmp_path, report)
    assert json.loads((tmp_path/'period_selection.json').read_text(encoding='utf-8')) == report
    text = (tmp_path/'period_selection.html').read_text(encoding='utf-8')
    assert needle in text
    assert '不同特征的改善取中位数' not in text
