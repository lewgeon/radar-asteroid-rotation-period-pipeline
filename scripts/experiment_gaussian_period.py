"""Predeclared Gaussian-feature controls; does not calibrate asteroid IQ noise."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.gaussian_period import gaussian_outer_period_set


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    schedules = {'regular': np.linspace(0., 90., 24),
        'irregular': np.r_[0., np.sort(np.random.default_rng(17).uniform(0., 90., 23))]}
    records = []
    for name, t in schedules.items():
        # Fixed feature model and input, not selected using the recovery result.
        sigma = np.full(len(t), .001)
        noise = np.random.default_rng(11).normal(0., sigma)
        y = .2+np.cos(2*np.pi*t/7.3)+.3*np.sin(2*np.pi*t/7.3)+.0005*np.cos(.47*t)+noise
        for alpha in (.05, .0027):
            result = gaussian_outer_period_set(t, y, 5., 10., [1., 2., 2.],
                {'declared_systematic': .001, 'synthesis_rounding': 1e-12}, sigma,
                calibration_provenance='解析特征控制：生成sigma=.001与有界.0005*cos项；非实测校准',
                alpha=alpha, resolution_s=.04, max_boxes=3000, estimate_s=7.31)
            result.update(schedule=name, measured_utc=datetime.now(timezone.utc).isoformat(),
                times=t.tolist(), values=y.tolist(), standard_deviations=sigma.tolist(),
                truth_used_only_for_generation_and_scoring_s=7.3,
                truth_in_cover=any(a<=7.3<=b for a,b in result['outer_intervals_s']),
                declared_noise_event_observed=bool(np.all(abs(noise)<=result['gaussian_budget']['pointwise_absolute_bounds'])))
            path = args.output/f'{name}_{alpha}.json'
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
            record = {key: result[key] for key in ('schedule', 'requested_failure_probability',
                'outer_intervals_s', 'conditional_error_bound_s', 'truth_in_cover', 'declared_noise_event_observed', 'status')}
            record['k_sigma'] = result['gaussian_budget']['k_sigma']
            records.append(record)
            print(record, flush=True)
    payload = dict(measured_utc=datetime.now(timezone.utc).isoformat(), records=records,
        scope='Four declared feature-model cases; not empirical coverage calibration or physical IQ propagation',
        source_sha256={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), ROOT/'inversion/src/gaussian_period.py', ROOT/'inversion/src/bounded_period.py')})
    (args.output/'summary.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
