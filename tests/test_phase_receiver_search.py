import numpy as np
import pytest
from scripts.monte_carlo_period import FixedPredictiveSearch
from scripts.monte_carlo_refinement import BatchedPredictiveSearch


@pytest.mark.parametrize('device',['cpu','cuda:0'])
def test_fixed_geometry_phase_uses_same_full_grid_and_refinement_as_production(device):
    import torch
    if device=='cuda:0' and not torch.cuda.is_available():pytest.skip('CUDA unavailable')
    rng=np.random.default_rng(4611)
    t=np.repeat(np.sort(rng.uniform(0,240,20)),3)+np.tile([0,.2,.4],20)
    runs=np.repeat(np.arange(20),3);weights=rng.uniform(.3,1,len(t))
    offset=2*(t/t.max())**2+.2*np.sin(t/7)
    y=np.column_stack([np.cos(2*np.pi*t/period+offset+k*.3)+.03*rng.normal(size=len(t))
        for k,period in enumerate((20,20,20,13.7,13.7))])
    search=BatchedPredictiveSearch(t,runs,weights,10,26,256,device=device,phase_offset=offset)
    actual=search.select(y);reference=search.production(y)
    assert abs(actual['period_s']-reference['period_s'])<1e-5
    assert search.device==device
    z=search.normalize(y)
    np.testing.assert_allclose(search.score_grid(z),np.array([search.scalar(p,z) for p in search.grid]),atol=1e-12)
    without=FixedPredictiveSearch(t,runs,weights,10,26,256).select(y)
    assert abs(actual['period_s']-without['period_s'])>.1,'fixture must distinguish geometry compensation'
    assert reference['diagnostics']['phase_compensation']


def test_geometry_phase_shape_and_finiteness_are_validated():
    t=np.arange(60.);runs=np.repeat(np.arange(20),3)
    for offset in (np.zeros(59),np.full(60,np.nan)):
        with pytest.raises(ValueError,match='phase'):
            FixedPredictiveSearch(t,runs,np.ones(60),10,26,100,phase_offset=offset)


def test_production_los_phase_has_analytic_negative_longitude_and_half_full_multiplier():
    from types import SimpleNamespace
    from inversion.src.period_enhancements import effective_look_phase
    times=np.array([100.,110.,120.])
    longitude=np.array([.2,.4,.6])
    los=np.column_stack((np.cos(longitude),np.sin(longitude),np.zeros(3)))
    echo=SimpleNamespace(scatter_elapsed_s=times,tx_los_icrs=los,rx_los_icrs=los)
    requested=np.array([105.,115.])
    cfg=dict(spin_axis_ra_deg=0.,spin_axis_dec_deg=90.,phase_period_convention='full_rotation')
    # Pole +Z: arbitrary reference-basis longitude cancels; no truth period supplied.
    full=effective_look_phase(echo,requested,cfg)
    np.testing.assert_allclose(full,[-.1,-.3],atol=1e-15)
    half=effective_look_phase(echo,requested,dict(cfg,phase_period_convention='half_rotation'))
    np.testing.assert_allclose(half,2*full,atol=1e-15)
    assert not np.array_equal(full,half)
