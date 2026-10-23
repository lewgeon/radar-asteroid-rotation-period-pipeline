"""Candidate tracing must preserve the estimator and identify failed searches."""
from types import SimpleNamespace
import json

import numpy as np
import pytest

from scripts import experiment_period_uncertainty as experiment
from inversion.src import period_uncertainty, joint_period
from inversion.src.inversion import PeriodSearchUnavailable


@pytest.mark.parametrize('policy', ['predictive_joint', 'legacy_consensus'])
def test_saved_trace_labels_failures_without_changing_results(tmp_path, monkeypatch, policy):
    runs = np.repeat(np.arange(12), 3)
    t = np.repeat(np.arange(12)*7.13, 3) + np.tile([0., .4, .8], 12)
    values = np.column_stack((np.cos(2*np.pi*t/20), np.sin(2*np.pi*t/20)))
    cfg = dict(period_min_s=10., period_max_s=44., period_grid_size=60,
               refine_period=True, period_selection='legacy_consensus', compute_device='cpu')
    source = tmp_path/'observables.npz'
    np.savez(source, time_elapsed_s=t, value=values, run_id=runs,
             feature_names=np.array(['total_power', 'range_centroid_s']),
             effective_sample_count=np.ones(len(t)),
             metadata_json=json.dumps(dict(inversion_config=cfg,
                 search_diagnostics=dict(processing_path='cpi'))))
    search = period_uncertainty.multi_harmonic_lomb_scargle
    select = joint_period.select_predictive_period
    results = []
    for tracing in (False, True):
        calls = {'search': 0, 'select': 0}
        def failing_search(*args, **kwargs):
            calls['search'] += 1
            if calls['search'] == 1:
                raise PeriodSearchUnavailable('control_failure', 'injected feature failure', {})
            return search(*args, **kwargs)
        def failing_select(*args, **kwargs):
            calls['select'] += 1
            if calls['select'] == 3:
                raise joint_period.JointPeriodUnavailable('injected joint failure')
            return select(*args, **kwargs)
        monkeypatch.setattr(period_uncertainty, 'multi_harmonic_lomb_scargle', failing_search)
        monkeypatch.setattr(joint_period, 'select_predictive_period', failing_select)
        report = experiment.saved(SimpleNamespace(observables=source, replicates=30,
            compute_device='cpu', period_selection=policy, feature_set='all',
            trace_candidates=tracing, output=tmp_path/str(tracing)))
        assert report['config']['period_selection'] == policy
        assert period_uncertainty.multi_harmonic_lomb_scargle is failing_search
        assert joint_period.select_predictive_period is failing_select
        results.append(report)
    assert results[0]['bootstrap_consensus_samples_s'] == results[1]['bootstrap_consensus_samples_s']
    assert results[0]['feature_candidates'] == results[1]['feature_candidates']
    assert any(candidate['source'].endswith((':half', ':double'))
               for item in results[1]['feature_candidates'].values()
               for candidate in item['candidates'])
    trace = results[1]['candidate_trace']
    rows = trace['feature_searches']
    assert len(rows) == 62
    assert rows[2]['replicate'] == 1 and rows[2]['feature'] == 'total_power'
    assert rows[2]['status'] == 'unavailable'
    assert rows[3]['replicate'] == 1 and rows[3]['feature'] == 'range_centroid'
    assert rows[-1]['replicate'] == 30
    assert all('replicate' in row for row in trace['joint_selections'])
    if policy == 'predictive_joint':
        failures = [row for row in trace['joint_selections'] if row['status'] == 'unavailable']
        assert len(failures) == 1 and failures[0]['replicate'] == 2
        assert results[1]['bootstrap_consensus_samples_s'][1] is None
    else:
        assert all(row['status'] == 'not_applicable' for row in trace['joint_selections'])
