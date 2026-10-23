"""Audit full-data predictions against training-only calibration and frozen data."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_period_harmonics import sha256
from scripts.experiment_half_period_diagnosis import features
from inversion.src.dataset import load_echo


def calibrated_prediction(predicted, observed, training):
    p, y = predicted[training], observed[training]
    pc, yc = p-p.mean(), y-y.mean()
    scale = float(pc@yc/(pc@pc))
    intercept = float(y.mean()-scale*p.mean())
    return intercept+scale*predicted, scale, intercept


def job_from_protocol(protocol):
    echoes = [Path(p) for p in protocol['sha256'] if Path(p).name == 'echo.npz']
    if len(echoes) != 1:
        raise ValueError('Protocol must identify exactly one frozen echo')
    return echoes[0].parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    args = parser.parse_args()
    out = args.experiment
    dest = out/'audit.json'
    if dest.exists():
        raise ValueError('Audit exists')
    joint = json.loads((out/'results.json').read_text(encoding='utf-8'))
    fixed = json.loads((out/'fixed_phase/results.json').read_text(encoding='utf-8'))
    if not all(r.get('completed') and r.get('hashes_unchanged') for r in [joint, fixed]):
        raise ValueError('Both experiments must have completed with unchanged hashes')
    if np.ptp(fixed['grid_sse']) <= 1e-6:
        raise ValueError('Period grid is insensitive; this is a degenerate control')
    paths = [out/'results.json', out/'fixed_phase/results.json', out/'input_features.npz',
        out/'final_features.npz', out/'golden_features.npz', out/'fixed_phase/final_features.npz', Path(__file__)]
    paths += [out/'protocol.json', out/'parent_artifact_timing_note.json']
    hashes = {str(p.resolve()): sha256(p) for p in paths}
    with np.load(out/'input_features.npz') as f:
        y, joint_train, all_features = f['value'][:, 1], f['training'], f['value']
    audit = {'sha256': hashes, 'calibration': 'one affine scale/intercept from training, applied unchanged to all samples',
             'fixed_phase_grid_sse_range': float(np.ptp(fixed['grid_sse']))}
    note = json.loads((out/'parent_artifact_timing_note.json').read_text(encoding='utf-8-sig'))
    audit['supplemental_parent_hashes_unchanged'] = all(sha256(p) == v for p, v in note['sha256'].items())
    audit['supplemental_hash_scope'] = note['scope']
    if not audit['supplemental_parent_hashes_unchanged']:
        raise ValueError('Supplemental parent artifact hashes changed')
    protocol = json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    job = job_from_protocol(protocol)
    inv = json.loads((job/'configs/inversion.generated.json').read_text(encoding='utf-8'))
    reextracted = features(load_echo(job/'echo/echo.npz'), inv)
    audit['input_features_match_original_exactly'] = bool(np.array_equal(reextracted, all_features))
    if not audit['input_features_match_original_exactly']:
        raise ValueError('Parent features differ from frozen echo')
    for name, path, record, train in [
        ('joint', out/'final_features.npz', joint, joint_train),
        ('fixed_phase', out/'fixed_phase/final_features.npz', fixed, None)]:
        with np.load(path) as f:
            p = f['value'][:, 1]
            if train is None:
                train = f['training']
        holdout = np.setdiff1d(np.arange(len(y)), train)
        calibrated, scale, intercept = calibrated_prediction(p, y, train)
        training_sse = float(np.sum(((calibrated[train]-y[train])/np.std(y[train]))**2))
        expected_sse = 2*joint['best']['cost'] if name == 'joint' else fixed['training_sse']
        audit[name] = {'scale': scale, 'intercept_s': intercept,
            'full_generated_training_sse': training_sse, 'subset_generated_training_sse': expected_sse,
            'sse_difference': training_sse-expected_sse,
            'holdout_calibrated_rmse_normalized': float(np.sqrt(np.mean((calibrated[holdout]-y[holdout])**2))/np.std(y[holdout])),
            'holdout_raw_rmse_s': float(np.sqrt(np.mean((p[holdout]-y[holdout])**2)))}
        if not np.isclose(training_sse, expected_sse, rtol=2e-6, atol=1e-10):
            raise ValueError(f'{name} subset/full prediction mismatch')
    with np.load(out/'golden_features.npz') as f:
        golden = f['value']
    audit['golden_exact_equal'] = bool(np.array_equal(golden, all_features))
    audit['golden_max_abs_difference_by_feature'] = np.max(np.abs(golden-all_features), axis=0).tolist()
    if not audit['golden_exact_equal']:
        raise ValueError('Same-model golden did not reproduce frozen data')
    audit['hashes_unchanged'] = all(sha256(p) == v for p, v in hashes.items())
    if not audit['hashes_unchanged']:
        raise RuntimeError('Audit input hashes changed')
    dest.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
