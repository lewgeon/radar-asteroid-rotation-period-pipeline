"""Local half-period refinement using the existing complete Chirp forward model.

Research experiment only: known mesh/pole/scattering, noiseless singleton Runs.
Initial phase is fitted, rather than copied from the simulation truth.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime
import gc
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import least_squares
import torch
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_half_period_diagnosis import features, look_longitude, phase_search
from scripts.experiment_period_harmonics import sha256
from echo.src.echo import generate_echo
from inversion.src.dataset import load_echo
from inversion.src.inversion import multi_harmonic_lomb_scargle


def subset_observation(data, indexes):
    """Preserve entire singleton Runs and absolute event epochs, not retime them."""
    n = len(data['elapsed_s'])
    if len(np.unique(data['run_id'])) != n:
        raise ValueError('Subsampling is restricted to singleton Runs')
    indexes = np.asarray(indexes)
    if indexes.ndim != 1 or not np.issubdtype(indexes.dtype, np.integer):
        raise ValueError('Indexes must be a one-dimensional integer array')
    if len(indexes) < 3 or np.any(np.diff(indexes) <= 0) or indexes[0] < 0 or indexes[-1] >= n:
        raise ValueError('Indexes must be strictly increasing and in range')
    return {k: v[indexes].copy() if v.ndim > 0 and len(v) == n else v.copy()
            for k, v in data.items()}


def affine_residual(predicted, observed):
    """Profile one global scale/intercept, never per-Run coefficients."""
    predicted, observed = np.asarray(predicted), np.asarray(observed)
    if predicted.ndim != 1 or predicted.shape != observed.shape:
        raise ValueError('Feature arrays must match')
    if not np.all(np.isfinite([predicted, observed])) or min(np.std(predicted), np.std(observed)) <= 0:
        raise ValueError('Features must be finite and varying')
    p = (predicted - predicted.mean()) / predicted.std()
    y = (observed - observed.mean()) / observed.std()
    scale = float(p @ y / (p @ p))
    return scale*p - y


def finite_jacobian(evaluate, x, steps):
    base = evaluate(x)
    return np.column_stack([(evaluate(x + np.eye(len(x))[i]*steps[i])-base)/steps[i]
                            for i in range(len(x))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, default=ROOT/'runs/paras_for_70m_3h')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--training-count', type=int, default=200)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output exists; choose a new directory')
    root = args.job
    config = json.loads((root/'configs/echo.generated.json').read_text(encoding='utf-8'))
    inv = json.loads((root/'configs/inversion.generated.json').read_text(encoding='utf-8'))
    echo = load_echo(root/'echo/echo.npz')
    with np.load(root/'observation_info.npz') as f:
        observation = {k: f[k].copy() for k in f.files}
    if config['snr_db'] is not None or not np.array_equal(echo.iq, echo.clean_iq):
        raise ValueError('This experiment requires noiseless input')
    if len(echo.elapsed_s) != 2000 or len(np.unique(echo.run_id)) != 2000 or not np.all(echo.valid):
        raise ValueError('Frozen 2000 valid singleton Runs required')
    if not 20 <= args.training_count < len(echo.elapsed_s):
        raise ValueError('Training count must be between 20 and 1999')
    # Truth parameters are removed before creating any optimization model.
    truth_period = config['target'].pop('rotation_period_s')/2
    truth_phase = config['target'].pop('initial_phase_deg')
    config.pop('output_path', None)
    config['compute'] = {'device': 'cuda:0' if torch.cuda.is_available() else 'cpu', 'dtype': 'float32'}
    paths = [root/'echo/echo.npz', root/'observation_info.npz', root/'configs/echo.generated.json',
             root/'configs/inversion.generated.json', Path(config['model_path']), Path(__file__)]
    paths += list((ROOT/'echo/src').glob('*.py')) + list((ROOT/'inversion/src').glob('*.py'))
    paths += [ROOT/'scripts/experiment_half_period_diagnosis.py', ROOT/'scripts/experiment_period_harmonics.py']
    hashes = {str(p.resolve()): sha256(p) for p in paths}
    args.output.mkdir(parents=True)
    start = time.perf_counter()
    all_features = features(echo, inv)
    observed = all_features[:, 1]
    training = np.linspace(0, len(observed)-1, args.training_count, dtype=int)
    holdout = np.setdiff1d(np.arange(len(observed)), training)
    train_path = args.output/'training_observation.npz'
    np.savez_compressed(train_path, **subset_observation(observation, training))
    longitude = look_longitude(echo.tx_los_icrs, echo.rx_los_icrs, config['target'])
    plain = multi_harmonic_lomb_scargle(echo.scatter_elapsed_s, observed,
        inv['period_min_s'], inv['period_max_s'], inv['period_grid_size'], harmonics=1)
    phase = phase_search(echo.scatter_elapsed_s, observed, -2*longitude, 1, inv)
    center = phase['base_period_s']
    if phase['dominant_harmonic'] != 1:
        raise ValueError('Initial estimate is outside the half-period phase-model branch')
    protocol = {'created_at': datetime.now().astimezone().isoformat(), 'sha256': hashes,
        'scope': 'local known-mesh/pole/scattering noiseless refinement; phase jointly fitted',
        'initialization': 'H1 geometric phase correction on all observations; no period truth',
        'training_count': len(training), 'holdout_count': len(holdout),
        'holdout_scope': 'excluded from physical-template parameter fitting, not from coarse initialization',
        'half_period_bounds_s': [center-30, center+30], 'phase_bounds_deg': [-2, 2],
        'starts': [[0, .35], [-.8, -.35], [.8, .7]],
        'parameterization': 'half period = center + 10*x[0]; phase_deg = x[1]',
        'finite_difference_steps': [.005, .005], 'maximum_nfev_per_start': 12,
        'device': config['compute']['device'], 'dtype': 'float32',
        'python': sys.version, 'numpy': np.__version__, 'torch': torch.__version__}
    (args.output/'protocol.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2), encoding='utf-8')
    result = {'plain_period_s': plain.best_period_s, 'phase_period_s': center,
              'evaluations': [], 'fits': []}
    np.savez_compressed(args.output/'input_features.npz', time=echo.scatter_elapsed_s,
        value=all_features, training=training, holdout=holdout)

    def checkpoint():
        result['elapsed_s'] = time.perf_counter()-start
        (args.output/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    def predict(half_period, phase_deg, full=False, tag='fit'):
        cfg = copy.deepcopy(config)
        cfg['target'].update(rotation_period_s=2*float(half_period), initial_phase_deg=float(phase_deg))
        cfg['observation_info_path'] = str((root/'observation_info.npz').resolve() if full else train_path.resolve())
        elapsed = time.perf_counter()
        bar = tqdm(total=100, desc=f'{tag} P={half_period:.6f} phase={phase_deg:.5f}', unit='%')
        last = [0]
        def progress(stage, percent, message):
            if percent > last[0]:
                bar.update(percent-last[0]); last[0] = percent
        generated = generate_echo(cfg, progress_callback=progress)
        bar.update(100-last[0]); bar.close()
        expected_times = echo.scatter_elapsed_s if full else echo.scatter_elapsed_s[training]
        np.testing.assert_array_equal(generated.scatter_elapsed_s, expected_times)
        values = features(generated, inv)
        result['evaluations'].append({'half_period_s': float(half_period), 'phase_deg': float(phase_deg),
            'full': full, 'tag': tag, 'elapsed_s': time.perf_counter()-elapsed})
        checkpoint()
        if full:
            np.savez_compressed(args.output/f'{tag}_features.npz', time=expected_times, value=values)
        del generated
        gc.collect()
        return values[:, 1]

    cache = {}
    def residual(x):
        key = tuple(float(v) for v in x)
        if key not in cache:
            p = center+10*x[0]
            cache[key] = affine_residual(predict(p, x[1]), observed[training])
        return cache[key]

    def jac(x):
        return finite_jacobian(residual, x, np.array([.005, .005]))

    for x0 in protocol['starts']:
        fitted = least_squares(residual, x0, jac=jac, bounds=([-3, -2], [3, 2]),
            max_nfev=12, ftol=1e-9, xtol=1e-9, gtol=1e-9, x_scale='jac', verbose=1)
        singular = np.linalg.svd(fitted.jac, compute_uv=False)
        result['fits'].append({'start': x0, 'half_period_s': center+10*float(fitted.x[0]),
            'phase_deg': float(fitted.x[1]), 'cost': float(fitted.cost), 'success': bool(fitted.success),
            'status': int(fitted.status), 'message': fitted.message, 'nfev': fitted.nfev,
            'optimality': float(fitted.optimality), 'jacobian_singular_values': singular.tolist()})
        checkpoint()
    best = min(result['fits'], key=lambda f: f['cost'])
    final = predict(best['half_period_s'], best['phase_deg'], full=True, tag='final')
    baseline = predict(center, .35, full=True, tag='initial')
    # Truth is accessed only after all fitted parameters have been fixed.
    golden = predict(truth_period, truth_phase, full=True, tag='golden')
    result['evaluation_reference'] = {'half_period_s': truth_period, 'initial_phase_deg': truth_phase,
        'golden_feature_max_difference': float(np.max(np.abs(golden-observed))),
        'golden_feature_exact_equal': bool(np.array_equal(golden, observed))}
    result['best'] = dict(best, error_s=best['half_period_s']-truth_period,
        phase_error_deg=best['phase_deg']-truth_phase)
    result['plain_error_s'] = plain.best_period_s-truth_period
    result['phase_error_s'] = center-truth_period
    result['validation'] = {}
    for name, indexes in [('training', training), ('holdout', holdout), ('all', np.arange(len(observed)))]:
        result['validation'][name] = {'final_normalized_rmse': float(np.sqrt(np.mean(affine_residual(final[indexes], observed[indexes])**2))),
            'initial_normalized_rmse': float(np.sqrt(np.mean(affine_residual(baseline[indexes], observed[indexes])**2))),
            'final_raw_rmse_s': float(np.sqrt(np.mean((final[indexes]-observed[indexes])**2)))}
    result['hashes_unchanged'] = all(sha256(p) == digest for p, digest in hashes.items())
    if not result['hashes_unchanged']:
        raise RuntimeError('Inputs or code changed during the experiment')
    result['completed'] = True
    checkpoint()
    print(json.dumps({k: result[k] for k in ['best', 'plain_error_s', 'phase_error_s', 'validation', 'elapsed_s']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
