"""Bounded grid + refinement control with the configured initial phase known.

Period truth is removed before prediction and used only for final evaluation.
This separates local joint-optimizer failure from same-model precision limits.
"""
import argparse
import copy
from datetime import datetime
import gc
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import minimize_scalar
import torch
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_geometry_template import subset_observation, affine_residual
from scripts.experiment_half_period_diagnosis import features
from scripts.experiment_period_harmonics import sha256
from echo.src.echo import generate_echo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--job', type=Path, default=ROOT/'runs/paras_for_70m_3h')
    args = parser.parse_args()
    out = args.experiment/'fixed_phase'
    if out.exists():
        raise ValueError('Fixed phase output exists')
    config = json.loads((args.job/'configs/echo.generated.json').read_text(encoding='utf-8'))
    inv = json.loads((args.job/'configs/inversion.generated.json').read_text(encoding='utf-8'))
    reference = config['target'].pop('rotation_period_s')/2
    known_phase = config['target']['initial_phase_deg']
    config.pop('output_path', None)
    config['compute'] = {'device': 'cuda:0' if torch.cuda.is_available() else 'cpu', 'dtype': 'float32'}
    prior = json.loads((args.experiment/'protocol.json').read_text(encoding='utf-8'))
    center = float(np.mean(prior['half_period_bounds_s']))
    with np.load(args.experiment/'input_features.npz') as f:
        times, observed = f['time'], f['value'][:, 1]
    with np.load(args.job/'observation_info.npz') as f:
        obs = {k: f[k].copy() for k in f.files}
    indexes = np.linspace(0, len(times)-1, 32, dtype=int)
    out.mkdir()
    np.savez_compressed(out/'observation.npz', **subset_observation(obs, indexes))
    hashes = dict(prior['sha256'])
    hashes.update({str(Path(__file__).resolve()): sha256(__file__),
                   str((out/'observation.npz').resolve()): sha256(out/'observation.npz')})
    if not all(sha256(p) == v for p, v in hashes.items()):
        raise ValueError('Parent input/source hashes changed')
    start = time.perf_counter()
    result = {'created_at': datetime.now().astimezone().isoformat(), 'sha256': hashes,
        'scope': 'same-model noiseless, known mesh/pole/scattering AND initial phase; local period grid',
        'known_phase_deg': known_phase, 'bounds_s': [center-5, center+5], 'grid_size': 65,
        'training_count': len(indexes), 'evaluations': []}
    def save():
        result['elapsed_s'] = time.perf_counter()-start
        (out/'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    cache = {}
    bar = tqdm(total=65, desc='fixed phase grid', unit='template')
    def predict(period, full=False):
        cfg = copy.deepcopy(config)
        cfg['target']['rotation_period_s'] = 2*float(period)
        cfg['observation_info_path'] = str((args.job/'observation_info.npz').resolve() if full else (out/'observation.npz').resolve())
        elapsed = time.perf_counter()
        generated = generate_echo(cfg)
        np.testing.assert_array_equal(generated.scatter_elapsed_s, times if full else times[indexes])
        values = features(generated, inv)
        result['evaluations'].append({'period_s': float(period), 'full': full, 'elapsed_s': time.perf_counter()-elapsed})
        save()
        del generated
        gc.collect()
        return values
    def loss(period):
        key = float(period)
        if key not in cache:
            prediction = predict(period)[:, 1]
            residual = affine_residual(prediction, observed[indexes])
            cache[key] = float(residual@residual)
        return cache[key]
    periods = np.linspace(center-5, center+5, 65)
    scores = []
    for p in periods:
        scores.append(loss(p)); bar.update(1)
    bar.close()
    i = int(np.argmin(scores))
    low, high = periods[max(i-1, 0)], periods[min(i+1, len(periods)-1)]
    optimized = minimize_scalar(loss, bounds=(low, high), method='bounded', options={'xatol': 1e-6, 'maxiter': 40})
    choices = [(scores[i], float(periods[i])), (loss(optimized.x), float(optimized.x))]
    cost, best = min(choices)
    result['grid_period_s'], result['grid_sse'] = periods.tolist(), scores
    result['optimizer'] = {'success': bool(optimized.success), 'message': str(optimized.message), 'nfev': optimized.nfev}
    result['best_period_s'], result['training_sse'] = best, cost
    # Fix selected estimate before opening the reference for evaluation.
    final = predict(best, full=True)
    np.savez_compressed(out/'final_features.npz', time=times, value=final, training=indexes)
    holdout = np.setdiff1d(np.arange(len(times)), indexes)
    for name, ids in [('training', indexes), ('holdout', holdout), ('all', np.arange(len(times)))]:
        result[name] = {'normalized_rmse': float(np.sqrt(np.mean(affine_residual(final[ids, 1], observed[ids])**2))),
                       'raw_rmse_s': float(np.sqrt(np.mean((final[ids, 1]-observed[ids])**2)))}
    result['reference_half_period_s'], result['error_s'] = reference, best-reference
    result['hashes_unchanged'] = all(sha256(p) == v for p, v in hashes.items())
    if not result['hashes_unchanged']:
        raise RuntimeError('Hashes changed')
    result['completed'] = True
    save()
    print(json.dumps({k: result[k] for k in ['best_period_s', 'error_s', 'training', 'holdout', 'elapsed_s']}, indent=2))


if __name__ == '__main__':
    main()
