"""Real CLI serialization of the common consensus policy on both layouts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from tests.test_gui_schema_v4 import _workspace_tmp
from inversion.src.period_consensus import CONSENSUS_POLICY, _cross_feature_consensus


@pytest.mark.parametrize('layout,device,selection', [('cw','cpu','legacy_consensus')] + [
    (layout, device, selection) for layout in ('chirp_cpi', 'chirp_fallback')
    for device in ('cpu', 'cuda:0') for selection in ('predictive_joint', 'legacy_consensus')])
def test_cli_writes_current_selection_policy_and_matching_consensus(layout,device,selection):
    with _workspace_tmp('consensus_cli_'+layout) as folder:
        source = folder/'echo/echo.npz'
        if layout == 'cw':
            source.parent.mkdir()
            t = np.arange(0., 120., .05)
            iq = (1+.35*np.cos(2*np.pi*t/20))*np.exp(.15j*np.sin(2*np.pi*t/7))
            np.savez(source, elapsed_s=t, iq=iq, clean_iq=iq, valid=np.ones(len(t), bool),
                coherence_id=np.zeros(len(t), int), tx_los_icrs=np.zeros((len(t), 3)),
                rx_los_icrs=np.zeros((len(t), 3)), tx_range_m=np.zeros(len(t)), rx_range_m=np.zeros(len(t)),
                scatter_elapsed_s=t, emit_elapsed_s=t, metadata_json=json.dumps({'sample_rate_hz': 20.}))
            config = dict(stft_window_samples=128, stft_overlap_fraction=.75,
                period_min_s=10., period_max_s=30., period_grid_size=160)
        else:
            from tests.test_inversion_feature_preview import InversionFeaturePreviewTests
            InversionFeaturePreviewTests().write_echo(source)
            config = dict(cpi_duration_s=1.6 if layout=='chirp_cpi' else 20.,
                cpi_hop_duration_s=.4, period_min_s=1., period_max_s=3., period_grid_size=80,compute_device=device,
                period_selection=selection)
        path = folder/'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        output = folder/'result'
        root = Path(__file__).resolve().parents[1]
        done = subprocess.run([sys.executable, str(root/'inversion/scripts/estimate_period.py'),
            '--echo', str(source), '--config', str(path), '--output', str(output)],
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen'),
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90)
        assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
        best = json.loads((output/'best_summary.json').read_text(encoding='utf-8'))
        summaries = json.loads((output/'summary.json').read_text(encoding='utf-8'))
        if selection == 'legacy_consensus':
            assert best['consensus_policy'] == CONSENSUS_POLICY
            assert best['best_period_s'] == _cross_feature_consensus(summaries)[0]
        else:
            from inversion.src.joint_period import PREDICTIVE_POLICY
            assert best['consensus_policy'] == PREDICTIVE_POLICY
            report = json.loads((output/'period_selection.json').read_text(encoding='utf-8'))
            assert report['period_s'] == best['best_period_s']
            assert report['diagnostics']['validation_mode'] == 'shared_fit_fallback'
            assert (output/'period_selection.html').is_file()
            assert best['false_alarm_probability'] is None
            if layout == 'chirp_cpi':
                with np.load(output/'period_observables.npz') as data:
                    assert data['doppler_window_rms_hz'].shape == data['time_elapsed_s'].shape
                    assert np.all(data['doppler_window_rms_hz'] > 0)
        assert best['final_3sigma_interval_s'] is None
        if layout != 'cw':
            assert best['search_diagnostics']['processing_path'] == ('cpi' if layout=='chirp_cpi' else 'pulse_fallback')
            from inversion.src.compute_backend import resolve_device
            expected=resolve_device({'compute_device':device})['actual']
            assert all(item['search_diagnostics']['period_compute']['actual']==expected for item in summaries.values())
