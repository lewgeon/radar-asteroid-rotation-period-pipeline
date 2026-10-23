import numpy as np
import pytest
from scipy.optimize import least_squares

from scripts.experiment_geometry_template import affine_residual, finite_jacobian, subset_observation
from scripts.experiment_geometry_centroid_proxy import centroid_proxy
from scripts.audit_geometry_template import calibrated_prediction, job_from_protocol


def test_affine_profile_has_one_shared_baseline_and_detects_shape_change():
    p = np.array([0., 1., 4., 2., -1.])
    y = 3*p+7
    np.testing.assert_allclose(affine_residual(p, y), 0, atol=1e-15)
    altered = p.copy(); altered[2] += .2
    assert np.linalg.norm(affine_residual(altered, y)) > .01
    with pytest.raises(ValueError):
        affine_residual(np.ones(5), y)


def test_finite_jacobian_separates_period_and_initial_phase():
    t = np.linspace(0, 30000, 200)
    x = np.array([.2, .3])
    def evaluate(v):
        return np.sin(2*np.pi*t/(5400+10*v[0])+np.deg2rad(2*v[1]))
    j = finite_jacobian(evaluate, x, np.array([1e-5, 1e-5]))
    phase = 2*np.pi*t/(5400+10*x[0])+np.deg2rad(2*x[1])
    independent = np.column_stack([-np.cos(phase)*2*np.pi*t*10/(5400+10*x[0])**2,
                                   np.cos(phase)*np.deg2rad(2)])
    # Forward differences have O(step) truncation error (below 3e-8 here).
    np.testing.assert_allclose(j, independent, atol=3e-8, rtol=1e-5)
    assert np.linalg.svd(j, compute_uv=False)[-1] > .03
    assert np.linalg.norm(j[:, 0]-j[:, 1]) > .1


def test_subsetting_preserves_epochs_and_whole_runs():
    data = {'elapsed_s': np.arange(6.)+1000, 'run_id': np.arange(6),
            'tx_los_icrs': np.arange(18.).reshape(6, 3), 'metadata_json': np.array('{}')}
    original = {k: v.copy() for k, v in data.items()}
    indexes = np.array([0, 2, 5])
    sub = subset_observation(data, indexes)
    np.testing.assert_array_equal(sub['elapsed_s'], [1000, 1002, 1005])
    np.testing.assert_array_equal(sub['tx_los_icrs'], data['tx_los_icrs'][indexes])
    sub['tx_los_icrs'][0] = -1
    for k in data:
        np.testing.assert_array_equal(data[k], original[k])
    data['run_id'][1] = 0
    with pytest.raises(ValueError, match='singleton'):
        subset_observation(data, indexes)


@pytest.mark.parametrize('period,phase_deg', [(3600., -.6), (5400., .2), (7200., .7)])
def test_local_fit_on_independent_moving_geometry_signal(period, phase_deg):
    times = np.linspace(0, 34000, 200)
    longitude = .01*times/times[-1]
    latitude = .3+.02*np.sin(times/20000)
    def waveform(p, ph):
        theta = 2*np.pi*times/p+np.deg2rad(2*ph)-2*longitude
        return (1+latitude)*np.cos(theta)+.2*np.cos(2*theta+.5*latitude)
    observed = 4+3*waveform(period, phase_deg)
    center = period+6
    def residual(x):
        return affine_residual(waveform(center+10*x[0], x[1]), observed)
    fitted = least_squares(residual, [.2, -.3],
        jac=lambda x: finite_jacobian(residual, x, np.array([.005, .005])),
        bounds=([-3, -2], [3, 2]), max_nfev=12, ftol=1e-9, xtol=1e-9, gtol=1e-9)
    assert fitted.success
    assert abs(center+10*fitted.x[0]-period) < 1e-4
    assert abs(fitted.x[1]-phase_deg) < 1e-4
    assert np.linalg.norm(residual([0, 0])) > .01


def test_incoherent_centroid_uses_squared_amplitude_and_is_pose_sensitive():
    tx = rx = np.array([[-1., 0., 0.]])
    centers = np.array([[-2., 0., 0.], [4., 0., 0.]])
    normals = np.array([[1., 0., 0.], [1., 0., 0.]])
    args = (tx, rx, centers, normals, np.array([1., 2.]), [1., 1.])
    zero = centroid_proxy(np.array([0.]), 5400., 0., *args)
    np.testing.assert_allclose(zero, [(-2*(-2)+4*(-2*4))/5/299792458.], rtol=1e-15)
    rotated = centroid_proxy(np.array([0.]), 5400., 30., *args)
    np.testing.assert_allclose(rotated, zero*np.cos(np.deg2rad(30)), rtol=1e-15)
    assert abs(rotated[0]-zero[0]) > 1e-9


def test_calibration_does_not_fit_holdout_values():
    prediction = np.array([1., 2., 3., 4., 5.])*1e-7
    observed = 3*prediction+7e-7
    train = np.array([0, 2, 4])
    calibrated, scale, intercept = calibrated_prediction(prediction, observed, train)
    np.testing.assert_allclose(calibrated, observed, rtol=1e-15)
    assert scale == pytest.approx(3)
    assert intercept == pytest.approx(7e-7, abs=1e-20)
    changed = observed.copy(); changed[[1, 3]] += 1.
    calibrated_changed, _, _ = calibrated_prediction(prediction, changed, train)
    np.testing.assert_array_equal(calibrated_changed, calibrated)


def test_proxy_relative_illumination_weights_change_with_pose():
    tx, rx = np.array([[-1., 0., 0.]]), np.array([[-.8, -.6, 0.]])
    centers = np.array([[-2., 1., 0.], [4., 2., 0.]])
    angles = np.deg2rad([10, 60])
    normals = np.column_stack([np.cos(angles), np.sin(angles), np.zeros(2)])
    areas = np.array([1., 2.])
    references, weight_ratios = [], []
    for phase in [0., 20.]:
        a = np.deg2rad(phase)
        r = np.array([[np.cos(a), np.sin(a), 0.], [-np.sin(a), np.cos(a), 0.], [0., 0., 1.]])
        t, u = r@tx[0], r@rx[0]
        weights = [(area*max(-t@n, 0)*max(-u@n, 0))**2 for area, n in zip(areas, normals)]
        expected = sum(w*((t+u)@p) for w, p in zip(weights, centers))/sum(weights)/299792458.
        got = centroid_proxy(np.array([0.]), 5400., phase, tx, rx, centers, normals, areas, [1., 1.])[0]
        assert got == pytest.approx(expected, abs=1e-22)
        references.append(expected); weight_ratios.append(weights[0]/weights[1])
    assert abs(references[0]-references[1]) > 1e-9
    assert abs(weight_ratios[0]-weight_ratios[1]) > .1


def test_audit_locates_job_from_protocol_not_output_directory(tmp_path):
    job = tmp_path/'original_job'
    protocol = {'sha256': {str(job/'echo/echo.npz'): 'digest', str(tmp_path/'src/echo.py'): 'other'}}
    assert job_from_protocol(protocol) == job
    with pytest.raises(ValueError, match='exactly one'):
        job_from_protocol({'sha256': {}})
