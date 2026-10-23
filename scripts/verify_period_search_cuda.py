"""Reproduce the independent 81-case CPU/CUDA review scan.

Run from the repository root in the pytorch environment. This is a
reconstruction of the already executed inline script, not another execution.
The optional output includes details that the original console summary did
not retain, such as the actual unavailability reason.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.inversion import multi_harmonic_lomb_scargle as search
from inversion.src.inversion import PeriodSearchUnavailable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rows = defaultdict(list)
    detailed = []
    for n in (32, 137, 500):
        for h in (1, 2, 4):
            for span in (93., 3., .03):
                for weight_decades in (0, 6, 20):
                    rng = np.random.default_rng(895+n+h)
                    t = np.sort(rng.uniform(0, span, n))
                    off = .13*np.sin(t/9)
                    y = (np.cos(2*np.pi*t/7.31+off)
                         + .27*np.sin(4*np.pi*t/7.31+2*off)
                         + rng.normal(0, .01, n))
                    w = np.geomspace(10.**(-weight_decades), 1., n)
                    kw = dict(harmonics=h, weights=w, phase_offset=off,
                              refine_period=False)
                    vals = []
                    for device in ('cpu', 'cuda:0'):
                        try:
                            vals.append(search(t, y, 6., 9., 81,
                                               compute_device=device, **kw))
                        except PeriodSearchUnavailable as error:
                            vals.append(error.reason)
                    record = dict(n=n, harmonics=h, span_s=span,
                                  weight_decades=weight_decades)
                    if isinstance(vals[0], str) or isinstance(vals[1], str):
                        assert vals[0] == vals[1], (n, h, span, weight_decades, vals)
                        rows[n, h, span].append((weight_decades, None, None, None))
                        record.update(status='both_unavailable', reason=vals[0])
                    else:
                        a, b = vals
                        np.testing.assert_array_equal(np.isnan(a.grid_scores),
                                                      np.isnan(b.grid_scores))
                        delta = float(np.nanmax(abs(a.grid_scores-b.grid_scores)))
                        assert delta < 2e-11, (n, h, span, weight_decades, delta)
                        assert ([c.period_s for c in a.candidates]
                                == [c.period_s for c in b.candidates]), (n, h, span, weight_decades)
                        info = b.search_diagnostics['period_compute']
                        guard = info['cpu_guard_grid_count']
                        peaks = info.get('cpu_peak_check_count', 0)
                        rows[n, h, span].append((weight_decades, delta, guard, peaks))
                        record.update(status='available', max_abs_score_difference=delta,
                                      cpu_guard_grid_count=guard,
                                      cpu_peak_check_count=peaks,
                                      candidate_periods_equal=True, nan_positions_equal=True)
                    detailed.append(record)
    print('N H span_s | weight_decades:max_abs_score_diff/CPUguard_grid (grid81; peak checks separate)')
    for key, results in rows.items():
        print(key, results)
    if args.output:
        args.output.write_text(json.dumps(dict(cases=detailed), indent=2,
                                          allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
