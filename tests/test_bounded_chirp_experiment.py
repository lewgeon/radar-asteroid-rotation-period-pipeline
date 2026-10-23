"""The small physical-input control must react to each declared perturbation."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('bounded_chirp_control',Path(__file__).parents[1]/'scripts/experiment_bounded_chirp.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)


def test_control_noise_and_coordinate_branches_are_distinguishable():
    clean=control.run_case(0.,count=3,search=False)
    noisy=control.run_case(1e-4,count=3,search=False)
    shifted=control.run_case(1e-4,.001,count=3,search=False)
    a=np.asarray(clean['observed_centroids_s']);b=np.asarray(noisy['observed_centroids_s'])
    c=np.asarray(shifted['observed_centroids_s'])
    assert np.max(abs(a-b))>1e-10
    assert np.allclose(c-b,.0005,rtol=0,atol=1e-17)
    assert np.max(noisy['error_components']['input_perturbation'])>np.max(clean['error_components']['input_perturbation'])
    assert shifted['error_components']['declared_coordinate_offset']==.001
    assert not clean['physical_model_error_validated']


def test_exact_convolution_has_an_independent_integer_golden():
    # Correlation [1, 2j, 3] with [1, 1j] at leading-edge indices.
    got=control.exact_compressed(np.array([[1,2j,3]],complex),np.array([1,1j]))
    assert got==[[(3,0),(0,-1),(3,0)]]


def test_control_declares_input_and_backend_boundaries():
    with pytest.raises(ValueError,match='nonnegative'):
        control.run_case(-1.,search=False)
    with pytest.raises(ValueError,match='integer count'):
        control.run_case(0.,count=True,search=False)
    token=control.compute_backend._active.set('cuda:0')
    try:
        with pytest.raises(ValueError,match='CPU path'):
            control.run_case(0.,search=False)
    finally:
        control.compute_backend._active.reset(token)
