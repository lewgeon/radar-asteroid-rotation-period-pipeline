import numpy as np
import pytest
from scripts.receiver_noise import receiver_noise


def test_numpy_noise_retains_original_independent_golden_stream():
    shape=(10,20);power=.3
    reference=np.random.default_rng(np.random.SeedSequence([1234,5,7]))
    expected=np.sqrt(power/2)*(reference.standard_normal(shape)+1j*reference.standard_normal(shape))
    actual=receiver_noise(shape,power,1234,5,7)
    np.testing.assert_array_equal(actual,expected)


@pytest.mark.parametrize('device',['cpu','cuda:0'])
def test_torch_noise_is_repeatable_independent_and_has_declared_complex_variance(device):
    import torch
    if device=='cuda:0' and not torch.cuda.is_available():pytest.skip('CUDA unavailable')
    first=receiver_noise((500000,),.3,1234,5,7,engine='torch',device=device)
    repeated=receiver_noise((500000,),.3,1234,5,7,engine='torch',device=device)
    different=receiver_noise((500000,),.3,1234,6,7,engine='torch',device=device)
    assert torch.equal(first,repeated)
    assert not torch.equal(first,different)
    values=first.cpu().numpy()
    assert abs(values.real.mean())<.003 and abs(values.imag.mean())<.003
    np.testing.assert_allclose([values.real.var(),values.imag.var()],[.15,.15],rtol=.01)
    assert abs(np.mean(values.real*values.imag))<.002
    assert float(first.abs().square().mean())!=float(different.abs().square().mean()),'do not normalize realizations'
