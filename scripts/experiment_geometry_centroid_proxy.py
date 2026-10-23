"""Smooth incoherent facet-centroid proxy, as a control for template fitting.

This is not the coherent matched-filter forward model; it deliberately averages
power over facets and omits interference and pulse/ADC response.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_geometry_template import affine_residual
from scripts.experiment_period_harmonics import sha256
from echo.src.mesh import load_mesh
from echo.src.motion import body_basis, spin_axis_from_config


def centroid_proxy(times, period, phase_deg, tx, rx, centers, normals, areas, powers):
    phase = np.pi*np.asarray(times)/period+np.deg2rad(phase_deg)
    c, s = np.cos(phase), np.sin(phase)
    def rotate_inverse(v):
        return np.column_stack([c*v[:, 0]+s*v[:, 1], -s*v[:, 0]+c*v[:, 1], v[:, 2]])
    tx, rx = rotate_inverse(tx), rotate_inverse(rx)
    illumination = np.maximum(-tx@normals.T, 0)**powers[0]
    reception = np.maximum(-rx@normals.T, 0)**powers[1]
    weights = (areas[None, :]*illumination*reception)**2
    sums = weights.sum(axis=1)
    if np.any(sums <= 0):
        raise ValueError('No illuminated/receptive power for a sample')
    return (weights*((tx+rx)@centers.T)).sum(axis=1)/sums/299792458.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--job', type=Path, default=ROOT/'runs/paras_for_70m_3h')
    args = parser.parse_args()
    dest = args.experiment/'centroid_proxy.json'
    if dest.exists():
        raise ValueError('Proxy output exists')
    config = json.loads((args.job/'configs/echo.generated.json').read_text(encoding='utf-8'))
    reference = config['target'].pop('rotation_period_s')/2
    config['target'].pop('initial_phase_deg')
    protocol = json.loads((args.experiment/'protocol.json').read_text(encoding='utf-8'))
    center = np.mean(protocol['half_period_bounds_s'])
    with np.load(args.experiment/'input_features.npz') as f:
        times, y, train, holdout = f['time'], f['value'][:, 1], f['training'], f['holdout']
    with np.load(args.job/'observation_info.npz') as f:
        basis = body_basis(spin_axis_from_config(config['target']))
        tx, rx = f['tx_los_icrs']@basis, f['rx_los_icrs']@basis
    mesh = load_mesh(config['model_path'], device='cpu', dtype='float32')
    centers, normals, areas = [v.cpu().numpy().astype(float) for v in [mesh.centroids, mesh.normals, mesh.areas]]
    hashes = {str(p): sha256(p) for p in [Path(__file__), Path(config['model_path']),
        args.job/'observation_info.npz', args.job/'configs/echo.generated.json', args.experiment/'input_features.npz',
        ROOT/'echo/src/mesh.py', ROOT/'echo/src/motion.py', ROOT/'scripts/experiment_geometry_template.py']}
    result = {'created_at': datetime.now().astimezone().isoformat(), 'sha256': hashes,
        'scope': 'smooth incoherent geometric centroid; no coherent pulse or ADC model', 'fits': []}
    start = time.perf_counter()
    def predict(p, ph, indexes):
        return centroid_proxy(times[indexes], p, ph, tx[indexes], rx[indexes], centers, normals, areas, config['scattering_power'])
    def residual(x):
        return affine_residual(predict(center+10*x[0], x[1], train), y[train])
    with np.errstate(over='raise', invalid='raise'):
        for x0 in protocol['starts']:
            fitted = least_squares(residual, x0, bounds=([-3, -2], [3, 2]),
                max_nfev=100, ftol=1e-10, xtol=1e-10, gtol=1e-10)
            result['fits'].append({'start': x0, 'period_s': center+10*fitted.x[0],
                'phase_deg': fitted.x[1], 'error_s': center+10*fitted.x[0]-reference,
                'cost': fitted.cost, 'success': bool(fitted.success), 'nfev': fitted.nfev})
        best = min(result['fits'], key=lambda f: f['cost'])
        prediction = predict(best['period_s'], best['phase_deg'], np.arange(len(times)))
    result['best'] = best
    result['normalized_rmse_training'] = float(np.sqrt(np.mean(affine_residual(prediction[train], y[train])**2)))
    result['normalized_rmse_holdout'] = float(np.sqrt(np.mean(affine_residual(prediction[holdout], y[holdout])**2)))
    result['elapsed_s'] = time.perf_counter()-start
    result['hashes_unchanged'] = all(sha256(p) == digest for p, digest in hashes.items())
    if not result['hashes_unchanged']:
        raise RuntimeError('Proxy inputs changed')
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['best', 'normalized_rmse_training', 'normalized_rmse_holdout', 'elapsed_s']}, indent=2))


if __name__ == '__main__':
    main()
