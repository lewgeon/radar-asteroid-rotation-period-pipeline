"""Independent least-squares checks and strict EV5 strategy contract."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from inversion.src.joint_period import JointPeriodUnavailable
from inversion.src.predictive_energy import (ENERGY_CHANNELS, PredictiveEnergyScorer,
                                             PredictiveEnergyEnsemble, select_predictive_energy_period)


def fixture():
    rng = np.random.default_rng(117)
    runs = np.repeat(np.arange(15), 4)
    times = np.repeat(np.sort(rng.uniform(0, 2800, 15)), 4)+np.tile(np.arange(4)*3, 15)
    phase = 2*np.pi*times/371
    values = np.column_stack([np.cos(phase+.2*j)+.2*np.sin((j+2)*phase)+rng.normal(0,.02,len(times))
                              for j in range(5)])
    weights = rng.uniform(.3, 3, len(times))
    return times, dict(zip(ENERGY_CHANNELS, values.T)), runs, weights


def test_batched_svd_matches_independent_five_fold_lstsq():
    t, f, g, w = fixture()
    off = .7*(t/t.max())**2
    scorer = PredictiveEnergyScorer(t, f, g, weights=w, phase_offset=off)
    actual = scorer.channel_errors([371, 432], 4)
    reference = []
    for p in [371, 432]:
        phase = 2*np.pi*t/p+off
        x = np.column_stack([np.ones(len(t))]+[fun(h*phase) for h in range(1,5) for fun in (np.cos,np.sin)])
        num = np.zeros(5)
        for train, test, rhs in scorer.blocks:
            beta = np.linalg.lstsq(x[train]*scorer.root[train,None], rhs, rcond=None)[0]
            num += np.sum(scorer.w[test,None]*(scorer.y[test]-x[test]@beta)**2,axis=0)
        reference.append(num/scorer.denominator)
    np.testing.assert_allclose(actual, reference, atol=1e-11, rtol=1e-11)
    assert np.max(abs(actual[0]-actual[1])) > .1  # Guard that periods exercise different fits.
    plain = PredictiveEnergyScorer(t,f,g,weights=w).evaluate(371,4)
    assert abs(plain-scorer.evaluate(371,4)) > .001  # LOS branch is observable.


def test_affine_invariance_and_search_metadata():
    t, f, g, w = fixture()
    affine = {name: (j+1)*(-1)**j*value+10 for j,(name,value) in enumerate(f.items())}
    a, b = PredictiveEnergyScorer(t,f,g,weights=w), PredictiveEnergyScorer(t,affine,g,weights=w)
    np.testing.assert_allclose(a.channel_errors([371,432],2), b.channel_errors([371,432],2), atol=2e-13)
    result = select_predictive_energy_period(t,f,g,weights=w,min_period=340,max_period=410,
                                              period_grid_size=8,refine_period=False)
    assert result['diagnostics']['search_protocol'] == 'dense8_top3_endpoints'
    assert result['diagnostics']['grid_size'] == 57
    assert result['diagnostics']['refinement_iterations'] == 42
    assert result['diagnostics']['refine_period']
    assert abs(result['period_s']-371) < .8
    assert result['score'] == sum(result['diagnostics']['channel_positive_skill_squared'])
    assert all(len(row['bracket_period_s']) == 2 for row in result['candidates'])


@pytest.mark.parametrize('case', ['nan','weight','constant','duplicate','trend','missing','runs','rank'])
def test_explicitly_refuses_unsupported_inputs(case):
    t,f,g,w = fixture()
    if case == 'nan': f[ENERGY_CHANNELS[0]][0] = np.nan
    elif case == 'weight': w[0] = 0
    elif case == 'constant': f[ENERGY_CHANNELS[0]][:] = 1
    elif case == 'duplicate': f[ENERGY_CHANNELS[1]] = 7-3*f[ENERGY_CHANNELS[0]]
    elif case == 'trend': f[ENERGY_CHANNELS[0]] = 2*t+7
    elif case == 'missing': f.pop(ENERGY_CHANNELS[-1])
    elif case == 'runs': g = g%9
    elif case == 'rank': t = np.floor(t/1000)*371
    with pytest.raises(JointPeriodUnavailable):
        scorer = PredictiveEnergyScorer(t,f,g,weights=w)
        scorer.evaluate(371,8)


def test_run_chronology_uses_mean_not_identifier_or_median():
    t,f,g,w = fixture()
    t[g==0] = [0,1,2,5000]
    scorer = PredictiveEnergyScorer(t,f,g,weights=w)
    expected = sorted(np.unique(g), key=lambda key: np.mean(t[g==key]))
    assert scorer.folds[0]['test_runs'] == expected[::5]
    assert expected != sorted(np.unique(g), key=lambda key: np.median(t[g==key]))


def test_full_sample_count_still_rejects_phase_rank_deficiency():
    _,f,g,w = fixture()
    t = np.arange(len(g), dtype=float)*371
    scorer = PredictiveEnergyScorer(t,f,g,weights=w)
    with pytest.raises(JointPeriodUnavailable, match='秩亏'):
        scorer.evaluate(371,8)


def test_no_positive_gain_is_not_reported_as_a_period(monkeypatch):
    t,f,g,w = fixture()
    monkeypatch.setattr(PredictiveEnergyScorer, 'channel_errors',
                        lambda self,p,h: np.full((len(np.atleast_1d(p)),5),2.))
    with pytest.raises(JointPeriodUnavailable, match='全域无正'):
        select_predictive_energy_period(t,f,g,weights=w,min_period=340,max_period=410,period_grid_size=2)


def test_finite_large_weights_do_not_overflow_run_normalization():
    t,f,g,w = fixture()
    ordinary = PredictiveEnergyScorer(t,f,g,weights=w)
    large = PredictiveEnergyScorer(t,f,g,weights=w*1e307)
    np.testing.assert_allclose(ordinary.channel_errors([371],8),large.channel_errors([371],8),atol=1e-12)


def test_unrepresentable_normalized_weights_are_explicitly_rejected():
    t,f,g,w = fixture()
    w[:2] = [1e-320,1e308]
    with pytest.raises(JointPeriodUnavailable,match='动态范围'):
        PredictiveEnergyScorer(t,f,g,weights=w)


def test_fixed_order_objective_clips_and_squares_positive_skills(monkeypatch):
    t,f,g,w = fixture()
    scorer = PredictiveEnergyScorer(t,f,g,weights=w)
    monkeypatch.setattr(scorer,'channel_errors',lambda p,h:np.array([[1.2,.5,.1,.8,1.3]]))
    assert scorer.evaluate(371,2) == pytest.approx(1.1)


def test_search_keeps_only_three_best_local_peaks_and_both_endpoints(monkeypatch):
    from inversion.src import predictive_energy as module
    low, high = 340., 410.
    grid = np.sort(1/np.linspace(1/high, 1/low, 9))
    curve = np.array([.1, .8, .1, .7, .1, .6, .1, .5, .1])

    class FakeScorer:
        folds = []
        run_count = 15

        def __init__(self, *args, **kwargs):
            pass

        def channel_errors(self, periods, h):
            scores = np.interp(periods, grid, curve)
            return np.repeat((1-np.sqrt(scores/5))[:, None], 5, axis=1)

        def evaluate(self, period, h, details=False):
            errors = self.channel_errors([period], h)[0]
            return errors if details else float(np.sum((1-errors)**2))

    monkeypatch.setattr(module, 'PredictiveEnergyScorer', FakeScorer)
    result = select_predictive_energy_period([], {}, [], min_period=low,
        max_period=high, period_grid_size=2)
    assert result['diagnostics']['harmonics'] == 1  # Exact ties choose smaller H.
    for h in (1, 2, 4, 8):
        rows = [r for r in result['candidates'] if r['harmonics'] == h]
        assert {r['grid_index'] for r in rows} == {0, 1, 3, 5, 8}
        assert all(r['refinement_iterations'] == 42 for r in rows)
        assert all(r['bracket_period_s'][0] <= r['period_s'] <= r['bracket_period_s'][1] for r in rows)
    assert result['period_s'] == grid[1]


@pytest.mark.parametrize('device',['cpu','cuda:0'])
def test_shared_qr_ensemble_matches_cpu_svd(device):
    import torch
    if device.startswith('cuda') and not torch.cuda.is_available():
        pytest.skip('CUDA unavailable; CPU fallback tested separately')
    t,f,g,w = fixture()
    y = np.column_stack([f[name] for name in ENERGY_CHANNELS])
    ys = np.stack([y,y+np.random.default_rng(3).normal(0,.07,y.shape)])
    ensemble = PredictiveEnergyEnsemble(t,ys,g,weights=w,batch_size=2,device=device)
    errors = ensemble.grid_errors([371,392],8)
    assert np.max(abs(errors[:,0]-errors[:,1])) > 1e-4
    for trial,scorer in enumerate(ensemble.scorers):
        np.testing.assert_allclose(errors[:,trial],scorer.channel_errors([371,392],8),atol=1e-11)
    expected = [ensemble.scorers[j].evaluate(p,4) for j,p in enumerate([371,392])]
    np.testing.assert_allclose(ensemble.paired_scores([371,392],[0,1],4),expected,atol=1e-11)
    winners = ensemble.search(min_period=340,max_period=410,period_grid_size=8)
    for trial in range(2):
        reference = select_predictive_energy_period(t,dict(zip(ENERGY_CHANNELS,ys[trial].T)),g,
            weights=w,min_period=340,max_period=410,period_grid_size=8)
        assert winners[trial]['h'] == reference['diagnostics']['harmonics']
        assert abs(winners[trial]['period_s']-reference['period_s']) < 1e-4
        assert abs(winners[trial]['score']-reference['score']) < 1e-11


@pytest.mark.skipif(os.environ.get('EV5_FULL_REGRESSION') != '1', reason='Full frozen EV5 arrays are local research inputs; opt in with EV5_FULL_REGRESSION=1')
@pytest.mark.parametrize('case,run,cache', [
    ('70m','ev5_snr_20261016_70m','receiver_snr_ev5_70m_20261016'),
    ('400m','ev5_snr_longcpi_20261016_400m','receiver_snr_ev5_400m_20261016')])
def test_frozen_clean_full_search(case,run,cache):
    from inversion.src.period_enhancements import effective_look_phase
    root = Path(__file__).resolve().parents[1]
    a = np.load(root/'runs'/run/'inversion/period_observables.npz')
    cfg = json.loads(str(a['metadata_json']))['inversion_config']
    names = dict(zip(a['feature_names'].tolist(), a['value'].T))
    original_names = ('total_power','doppler_centroid_hz','rms_bandwidth_hz','range_centroid_s','energy_range_width_90_s')
    original = dict(zip(ENERGY_CHANNELS, [names[name] for name in original_names]))
    # The immutable reference was computed from the frozen clean feature cache,
    # not the slightly different period_observables re-extraction. Keep identity.
    f = dict(zip(ENERGY_CHANNELS,np.load(root/'tmp'/cache/'clean_features.npy').T))
    off = None
    if cfg['los_phase_compensation']:
        echo = np.load(root/'runs'/run/'echo/echo.npz')
        obj = SimpleNamespace(**{key:echo[key] for key in ('scatter_elapsed_s','tx_los_icrs','rx_los_icrs')})
        off = effective_look_phase(obj,a['time_elapsed_s'],dict(spin_axis_ra_deg=105.,spin_axis_dec_deg=-66.,phase_period_convention='full_rotation'))
    result = select_predictive_energy_period(a['time_elapsed_s'],f,a['run_id'],weights=a['effective_sample_count'],
        phase_offset=off,min_period=cfg['period_min_s'],max_period=cfg['period_max_s'],period_grid_size=cfg['period_grid_size'])
    evidence = json.loads((root/'docs/4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_MODELS.json').read_text(encoding='utf-8'))
    frozen = evidence['results']['features/clean_dense_protocol.json']['data']
    expected = next(row for row in frozen['cases'] if row['case']==case)['selected']['positive_skill_squared']
    print(case, result['period_s'],result['score'],result['diagnostics']['harmonics'], flush=True)
    assert result['diagnostics']['harmonics'] == expected['h']
    assert abs(result['period_s']-expected['period_s']) < .01
    assert abs(result['score']+expected['score']) <= 1e-8  # Frozen CSV uses -J.
    original_score = PredictiveEnergyScorer(a['time_elapsed_s'],original,a['run_id'],
        weights=a['effective_sample_count'],phase_offset=off).evaluate(result['period_s'],expected['h'])
    print(case,'original_reextracted_score',original_score,'cached_score',result['score'],flush=True)
