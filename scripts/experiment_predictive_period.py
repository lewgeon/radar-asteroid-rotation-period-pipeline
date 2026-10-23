"""Paired truth-blind period-selection controls and optional saved-feature replay.

Selection always searches 10..30 seconds in synthetic controls. Truth belongs
only to the generator and final scorer. The two-of-five scenario deliberately
violates the robust majority assumption and is retained as a negative control.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.inversion import multi_harmonic_lomb_scargle
from inversion.src.joint_period import select_predictive_period, PREDICTIVE_POLICY
from inversion.src.period_consensus import _cross_feature_consensus, CONSENSUS_POLICY
from inversion.src.period_uncertainty import candidate_summary


def generated_control(seed, noise, good_count):
    rng = np.random.default_rng(seed)
    truth = float(rng.uniform(16., 24.))
    # A separate strong periodic contaminant never uses the target to initialize
    # the estimator. Its disjoint range ensures the fixture is nondegenerate.
    contaminant = float(rng.uniform(10., 12.))
    starts = np.sort(rng.uniform(0., 260., 40))
    t = np.repeat(starts, 3)+np.tile([0., .1, .2], 40)
    runs = np.repeat(np.arange(40), 3)
    w = rng.uniform(.7, 1.3, len(t))
    shared_run_noise = np.repeat(rng.normal(size=40), 3)
    features = {}
    for channel in range(5):
        period = truth if channel < good_count else contaminant
        phase = 2*np.pi*t/period + .47*channel
        independent_run_noise = np.repeat(rng.normal(size=40), 3)
        error = noise*(.5*shared_run_noise+.6*independent_run_noise+.3*rng.normal(size=len(t)))
        # Fixed mild non-sinusoidal shape makes the H1 model intentionally
        # imperfect; phase and shape are not retuned after truth scoring.
        values = np.cos(phase)+.12*np.sin(2*phase+.13*channel)+error
        values[rng.random(len(t)) < .03] = np.nan
        features[f'channel_{channel}'] = values
    return t, features, runs, w, truth, contaminant


def paired(t, features, runs, weights, minimum, maximum, grid, harmonics=1):
    estimates = {name: multi_harmonic_lomb_scargle(t, values, minimum, maximum, grid,
        weights=weights, harmonics=harmonics, refine_period=True, compute_device='cpu')
        for name, values in features.items()}
    before = _cross_feature_consensus({name: candidate_summary(value) for name, value in estimates.items()})
    start = time.perf_counter()
    after = select_predictive_period(t, features, runs, estimates, weights=weights,
        harmonics=harmonics, min_period=minimum, max_period=maximum)
    elapsed = time.perf_counter()-start
    return dict(legacy_period_s=float(before[0]), predictive_period_s=after['period_s'],
        score=after['score'], status=after['status'], warnings=after['warnings'],
        predictive_selection_seconds=elapsed, evidence=after['evidence'],
        candidates=after['candidates'], diagnostics=after['diagnostics'])


def controls(trials, grid):
    records = []
    for good_count in (3, 2):
        for noise in (.03, .2, .6):
            for repeat in range(trials):
                seed = 26101600+repeat
                t, features, runs, w, truth, contaminant = generated_control(seed, noise, good_count)
                row = paired(t, features, runs, w, 10., 30., grid)
                row.update(seed=seed, noise_scale=noise, target_channel_count=good_count,
                    reference_period_s=truth, contaminant_period_s=contaminant,
                    legacy_error_s=row['legacy_period_s']-truth,
                    predictive_error_s=row['predictive_period_s']-truth)
                records.append(row)
            print(f'completed target_channels={good_count}, noise={noise}, trials={trials}', flush=True)
    summary = []
    for good_count in (3, 2):
        for noise in (.03, .2, .6):
            subset = [r for r in records if r['target_channel_count'] == good_count and r['noise_scale'] == noise]
            row = dict(target_channel_count=good_count, noise_scale=noise, trials=len(subset),
                       scope='majority_target' if good_count == 3 else 'negative_minority_target')
            for method in ('legacy', 'predictive'):
                error = np.array([r[f'{method}_error_s'] for r in subset])
                truth = np.array([r['reference_period_s'] for r in subset])
                row[method] = dict(bias_s=float(error.mean()), rmse_s=float(np.sqrt(np.mean(error**2))),
                    median_absolute_error_s=float(np.median(abs(error))),
                    errors_over_5_percent=int(np.count_nonzero(abs(error/truth) > .05)))
            summary.append(row)
    return dict(records=records, summary=summary)


def saved(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path, allow_pickle=False) as data:
        t = data['time_elapsed_s']; runs = data['run_id']; weights = data['effective_sample_count']
        features = dict(zip(data['feature_names'].tolist(), data['value'].T))
        metadata = json.loads(data['metadata_json'].item())
    cfg = metadata['inversion_config']
    if cfg.get('los_phase_compensation', False):
        raise ValueError('Saved replay does not reconstruct phase geometry; use an explicitly uncompensated snapshot')
    result = paired(t, features, runs, weights, cfg['period_min_s'], cfg['period_max_s'], cfg['period_grid_size'],
                    cfg.get('harmonics', 1) if cfg.get('multi_harmonic_enabled', True) else 1)
    if digest != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('Saved observations changed during replay')
    result.update(source=str(path.resolve()), sha256=digest, metadata=metadata)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=30)
    parser.add_argument('--grid', type=int, default=240)
    parser.add_argument('--observables', type=Path)
    args = parser.parse_args()
    if args.trials < 1 or args.grid < 10:
        parser.error('trials >= 1 and grid >= 10 required')
    args.output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    result = controls(args.trials, args.grid)
    if args.observables:
        result['saved'] = saved(args.observables)
    result.update(measured_utc=started, legacy_policy=CONSENSUS_POLICY, predictive_policy=PREDICTIVE_POLICY,
        protocol='30 default fixed seeds x three noise scales x target majority/minority; 10..30s full search; H1; five whole-Run folds; identical feature inputs for paired selection; truth only generator/final scorer; no confidence coverage claim',
        grid_size=args.grid,
        source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            Path(__file__), ROOT/'inversion/src/joint_period.py', ROOT/'inversion/src/period_consensus.py',
            ROOT/'inversion/src/inversion.py')})
    (args.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
