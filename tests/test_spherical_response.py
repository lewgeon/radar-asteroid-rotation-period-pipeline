"""Contract and independent group-deletion checks for known-pole response."""
import json
import hashlib
import os
import platform
from pathlib import Path
import time
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import numpy as np
from inversion.src.spherical_response import (ALPHAS, FEATURE_NAMES, _ResponseScore,
    _design, _geometry, select_spherical_response_period)


def fixture():
    rng = np.random.default_rng(22)
    t = np.linspace(0, 10000, 500)
    los = np.column_stack([np.cos(t/60000), np.sin(t/60000), .15+0*t])
    return dict(times=t, features=dict(zip(FEATURE_NAMES, rng.normal(size=(5, 500)))),
        run_ids=np.repeat(np.arange(100), 5), scatter_elapsed_s=t,
        tx_los_icrs=los, rx_los_icrs=los, spin_axis_ra_deg=105., spin_axis_dec_deg=-66.,
        period_min_s=1800., period_max_s=14400., period_grid_size=3)


class SphericalResponseTests(unittest.TestCase):
    def test_block_deletion_matches_independent_ridge_refits(self):
        d = fixture()
        z, phase, _ = _geometry(d['times'], d['scatter_elapsed_s'], d['tx_los_icrs'],
                                d['rx_los_icrs'], 105., -66.)
        y = np.column_stack(list(d['features'].values()))
        groups = np.array([np.flatnonzero(d['run_ids'] == g) for g in range(100)])
        scorer = _ResponseScore(d['times'], y, phase, z, groups, 3)
        result = scorer.evaluate(1/7300., True)
        x = _design(scorer.times, phase, scorer.terms, 1/7300.)
        errors = np.zeros((len(ALPHAS), 5))
        for g in groups:
            train = np.ones(500, dtype=bool)
            train[g] = False
            xm, ym = x[train].mean(0), scorer.y[train].mean(0)
            xc = x[train]-xm
            for i, alpha in enumerate(ALPHAS):
                # A direct augmented least squares fit is independent of hat deletion.
                a = np.vstack([xc, np.sqrt(alpha)*np.eye(x.shape[1])])
                b = np.vstack([scorer.y[train]-ym, np.zeros((x.shape[1], 5))])
                coefficients = np.linalg.lstsq(a, b, rcond=None)[0]
                residual = (scorer.y[g]-ym-(x[g]-xm)@coefficients)/scorer.y[train].std(0)
                errors[i] += np.sum(residual**2, axis=0)/500
        np.testing.assert_allclose(result['per_feature_min_cv'], errors.min(0), rtol=2e-9, atol=2e-9)
        np.testing.assert_array_equal(result['alpha_by_feature'], ALPHAS[errors.argmin(0)])
        # Guard the guard: regularization choices really produce different predictions.
        self.assertGreater(np.max(abs(errors[0]-errors[-1])), .001)

    def test_explicit_contract_failures(self):
        mutations = [dict(waveform='cw'), dict(spin_axis_ra_deg=None),
                     dict(effective_sample_count=np.zeros(500)),
                     dict(times=np.r_[np.nan, np.arange(499)]),
                     dict(run_ids=np.repeat(np.arange(50), 10)),
                     dict(scatter_elapsed_s=np.arange(500)+20000.),
                     dict(tx_los_icrs=np.zeros((500, 3))),
                     dict(period_grid_size=2), dict(period_min_s=20000)]
        for mutation in mutations:
            with self.subTest(fields=list(mutation)):
                with self.assertRaises(ValueError):
                    select_spherical_response_period(**dict(fixture(), **mutation))
        for bad in ('constant', 'duplicate', 'missing', 'nonfinite'):
            d = fixture()
            if bad == 'constant':
                d['features']['total_power'][:] = 1
            elif bad == 'duplicate':
                d['features']['total_power'] = -3*d['features']['doppler_centroid']+7
            elif bad == 'missing':
                d['features'].pop('total_power')
            else:
                d['features']['total_power'][8] = np.inf
            with self.subTest(kind=bad), self.assertRaises(ValueError):
                select_spherical_response_period(**d)

    def test_geometry_poles_and_bistatic_range(self):
        t = np.arange(500.)
        x = np.tile([1., 0., 0.], (500, 1))
        for ra, dec, tx, rx in [(0., 0., x, x), (90., 0., x, -x),
                                (90., 0., x, np.tile([0., 1., 0.], (500, 1)))]:
            with self.assertRaises(ValueError):
                _geometry(t, t, tx, rx, ra, dec)
        # Component interpolation across an antipodal LOS also needs rejection.
        with self.assertRaises(ValueError):
            _geometry(np.array([.5]), np.array([0., 1.]), np.array([[1., 0, 0], [-1., 0, 0]]),
                      np.array([[1., 0, 0], [-1., 0, 0]]), 105., -66.)

    def test_unsorted_runs_do_not_change_unit_weight_score(self):
        d = fixture()
        z, phase, _ = _geometry(d['times'], d['times'], d['tx_los_icrs'], d['rx_los_icrs'], 105., -66.)
        y = np.column_stack(list(d['features'].values()))
        ids = d['run_ids']
        indices = np.array([np.flatnonzero(ids == i) for i in range(100)])
        first = _ResponseScore(d['times'], y, phase, z, indices, 2).evaluate(1/6000)
        permutation = np.random.default_rng(2).permutation(500)
        indices = np.array([np.flatnonzero(ids[permutation] == i) for i in range(100)])
        second = _ResponseScore(d['times'][permutation], y[permutation], phase[permutation],
                                z[permutation], indices, 2).evaluate(1/6000)
        self.assertAlmostEqual(first, second, places=10)

    def test_public_extreme_feature_scales_preserve_score_and_alpha(self):
        from inversion.src import spherical_response as module
        d = fixture()
        result = select_spherical_response_period(**d)
        for scale in (1e-200, 1e200):
            scaled = dict(d, features={name: values*scale for name, values in d['features'].items()})
            with self.subTest(scale=scale):
                actual = select_spherical_response_period(**scaled)
                self.assertAlmostEqual(actual['score'], result['score'], places=10)
                self.assertEqual(actual['degree'], result['degree'])
                np.testing.assert_array_equal(actual['alpha_by_feature'], result['alpha_by_feature'])
        # Guard the guard: the original raw-std path is not scale safe.
        y = np.column_stack(list(d['features'].values()))
        indices = np.array([np.flatnonzero(d['run_ids'] == g) for g in range(100)])
        with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
            for scale in (1e-200, 1e200):
                with self.assertRaises(ValueError):
                    module._ResponseScore(d['times'], y*scale, np.zeros(500),
                                          np.zeros(500), indices, 1)

    def test_search_keeps_all_strict_minima_and_endpoints(self):
        from inversion.src import spherical_response as module
        d = fixture()
        d['period_grid_size'] = 9
        low, high = 1/d['period_max_s'], 1/d['period_min_s']
        calls = []

        class FakeScore:
            def __init__(self, *args):
                self.degree = args[-1]

            def evaluate(self, frequency, details=False):
                coordinate = (frequency-low)/(high-low)
                loss = (np.cos(8*np.pi*coordinate)+1)/2+self.degree*.01
                if details:
                    return dict(score=loss, per_feature_min_cv=[loss]*5,
                        alpha_by_feature=[.1]*5, singular_values=[1.], effective_dof=[2.]*5)
                return loss

        original_minimize = module.minimize_scalar

        def track(*args, **kwargs):
            calls.append(kwargs['bounds'])
            self.assertEqual(kwargs['options'], {'xatol': 1e-14})
            return original_minimize(*args, **kwargs)

        with patch.object(module, '_ResponseScore', FakeScore), patch.object(module, 'minimize_scalar', track):
            result = select_spherical_response_period(**d)
        # Four strict minima plus both endpoints for every one of five degrees.
        self.assertEqual(len(calls), 30)
        self.assertEqual(len(result['candidates']), 30)
        self.assertEqual(result['degree'], 1)
        self.assertEqual(result['diagnostics']['grid_count'], 9)

    @unittest.skipUnless(os.environ.get('EV5_SPHERICAL_GOLDEN') == '1', 'opt-in full frozen EV5 search')
    def test_frozen_ev5_clean_search(self):
        root = Path(__file__).resolve().parents[1]
        frozen = json.loads((root/'docs/4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_MODELS.json').read_text(encoding='utf8'))
        started = time.perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        source_path = root/'inversion/src/spherical_response.py'
        source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        evidence = []
        for tag, job, maximum, count, degree in [
            ('70m', 'ev5_snr_20261016_70m', 14400, 4000, 4),
            ('400m', 'ev5_snr_longcpi_20261016_400m', 28800, 8000, 6)]:
            geometry = root/'tmp/ev5_precision_solution_20261020/geometry'
            with np.load(geometry/f'{tag}_inputs.npz') as source:
                times, ids, y = source['times'], source['runs'], source['features']
            with np.load(root/'runs'/job/'echo/echo.npz') as echo:
                # Accessing these fields avoids materializing the much larger IQ.
                epochs, tx, rx = echo['scatter_elapsed_s'], echo['tx_los_icrs'], echo['rx_los_icrs']
            expected = frozen['results'][f'geometry/{tag}_full500_all_train.json']['data']
            best = min(expected['results'], key=lambda r: r['top10'][0]['cv_mean'])['top10'][0]
            result = select_spherical_response_period(times, dict(zip(FEATURE_NAMES, y.T)), ids,
                scatter_elapsed_s=epochs, tx_los_icrs=tx, rx_los_icrs=rx,
                spin_axis_ra_deg=105., spin_axis_dec_deg=-66., period_min_s=1800.,
                period_max_s=maximum, period_grid_size=count)
            self.assertEqual(result['degree'], degree)
            self.assertLess(abs(result['period_s']-best['period_s']), .01)
            self.assertLess(abs(result['score']-best['cv_mean']), 1e-8)
            np.testing.assert_array_equal(result['alpha_by_feature'], best['alpha_by_feature'])
            print(tag, result['period_s'], result['score'], result['degree'], flush=True)
            paths = [geometry/f'{tag}_inputs.npz', root/'runs'/job/'echo/echo.npz']
            identities = []
            for path in paths:
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(8*1024*1024), b''):
                        digest.update(block)
                identities.append(dict(path=path.relative_to(root).as_posix(), sha256=digest.hexdigest()))
            evidence.append(dict(case=tag, inputs=identities, actual=dict(period_s=result['period_s'],
                degree=result['degree'], score=result['score'], alpha_by_feature=result['alpha_by_feature']),
                expected=best, period_difference_s=result['period_s']-best['period_s'],
                score_difference=result['score']-best['cv_mean']))
            evidence_name = os.environ.get('EV5_SPHERICAL_EVIDENCE_NAME', 'spherical_golden.json')
            if Path(evidence_name).name != evidence_name or not evidence_name.endswith('.json'):
                raise ValueError('EV5_SPHERICAL_EVIDENCE_NAME 必须为 JSON 文件名')
            output = root/'tmp/ev5_production_acceptance'/evidence_name
            output.parent.mkdir(parents=True, exist_ok=True)
            record = dict(started_utc=timestamp, elapsed_s=time.perf_counter()-started,
                command='conda run --no-capture-output -n pytorch python -m unittest tests.test_spherical_response.SphericalResponseTests.test_frozen_ev5_clean_search -v',
                environment=dict(python=platform.python_version(), numpy=np.__version__,
                    EV5_SPHERICAL_GOLDEN=os.environ.get('EV5_SPHERICAL_GOLDEN'),
                    EV5_SPHERICAL_EVIDENCE_NAME=evidence_name,
                    OMP_NUM_THREADS=os.environ.get('OMP_NUM_THREADS'),
                    MKL_NUM_THREADS=os.environ.get('MKL_NUM_THREADS'),
                    OPENBLAS_NUM_THREADS=os.environ.get('OPENBLAS_NUM_THREADS')),
                source=dict(path=source_path.relative_to(root).as_posix(),
                            sha256=source_hash), cases=evidence)
            output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf8')

    @unittest.skipUnless(os.environ.get('EV5_SPHERICAL_GOLDEN') == '1', 'opt-in frozen EV5 noise inputs')
    def test_frozen_noise_scores_at_reference_candidates(self):
        # This checks the objective, not full noise search or general robustness.
        root = Path(__file__).resolve().parents[1]
        frozen = json.loads((root/'docs/4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_MODELS.json').read_text(encoding='utf8'))
        with np.load(root/'tmp/ev5_precision_solution_20261020/geometry/400m_inputs.npz') as d:
            times, phase, z, ids = d['times'], d['phase'], d['z'], d['runs']
        cache = np.load(root/'tmp/receiver_snr_ev5_400m_20261016/features.npy', mmap_mode='r')
        indices = np.array([np.flatnonzero(ids == group) for group in np.unique(ids)])
        for snr in (10, 20, 30):
            data = frozen['results'][f'geometry/400m_full500_all_train_snr{snr}_t0.json']['data']
            for entry in data['results']:
                expected = entry['top10'][0]
                score = _ResponseScore(times, cache[0, snr+60], phase, z, indices, entry['degree'])
                result = score.evaluate(1/expected['period_s'], True)
                self.assertLess(abs(result['score']-expected['cv_mean']), 1e-8)
                np.testing.assert_array_equal(result['alpha_by_feature'], expected['alpha_by_feature'])


if __name__ == '__main__':
    unittest.main()
