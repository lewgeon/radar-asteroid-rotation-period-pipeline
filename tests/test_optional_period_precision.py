"""Guard experimental noise semantics and period-option sensitivity."""
from types import SimpleNamespace
from dataclasses import dataclass
import numpy as np
import pytest
from scripts.experiment_optional_period_precision import receiver_noise, search

@dataclass
class Fixture:
    iq: np.ndarray
    clean_iq: np.ndarray
    run_id: np.ndarray
    valid: np.ndarray

def test_receiver_noise_is_paired_and_preserves_clean_input():
    clean = np.ones((2,100000), dtype=complex)
    e = Fixture(clean.copy(),clean,np.arange(2),np.ones(clean.shape,bool))
    a, b = receiver_noise(e,20,17), receiver_noise(e,20,17)
    np.testing.assert_array_equal(a.iq,b.iq)
    np.testing.assert_array_equal(e.iq,clean)
    n = a.iq-clean
    assert abs(np.mean(np.abs(n)**2)-.01)<.0002
    assert abs(np.mean(n.real*n.imag))<.0001
    assert np.max(np.abs(n))>0
    assert np.mean(np.abs(receiver_noise(e,40,17).iq-clean)**2)<.00011

def test_noise_refuses_shared_or_invalid_rows():
    clean = np.ones((2,4),complex)
    with pytest.raises(ValueError,match='singleton'):
        receiver_noise(Fixture(clean,clean,np.zeros(2),np.ones(clean.shape,bool)),20,1)
    with pytest.raises(ValueError,match='all-valid'):
        receiver_noise(Fixture(clean,clean,np.arange(2),np.zeros(clean.shape,bool)),20,1)

def test_known_phase_fixture_separates_branches():
    t = np.linspace(0,35000,360)
    offset = -.2*(t/t[-1])**2
    y = np.cos(2*np.pi*t/5400+offset)+.25*np.sin(4*np.pi*t/5400+2*offset)
    corrected = search(t,y,offset,2,True,4000)['period_s']
    raw = search(t,y,None,2,True,4000)['period_s']
    h1 = search(t,y,offset,1,True,4000)['period_s']
    coarse = search(t,y,offset,2,False,4000)['period_s']
    assert abs(corrected-5400)<.001
    assert abs(raw-corrected)>1
    assert abs(h1-corrected)>.01
    assert abs(coarse-corrected)>.01
