from types import SimpleNamespace
import numpy as np
import pytest
from scripts.monte_carlo_receiver import LinearReceiver, reference_run_features


@pytest.mark.parametrize('convention',['centered','zero_to_bandwidth'])
@pytest.mark.parametrize('device',['cpu','cuda:0'])
def test_power_reuse_matches_independent_frontend(convention,device):
    import torch
    if device=='cuda:0' and not torch.cuda.is_available():pytest.skip('CUDA unavailable')
    rng=np.random.default_rng(1717)
    rows=np.arange(16)
    fast=np.arange(80)/1000
    clean=rng.normal(size=(16,80))+1j*rng.normal(size=(16,80))
    offset=np.linspace(-.0008,.0006,16)
    echo=SimpleNamespace(iq=clean,fast_time_s=fast,row_fast_time_offset_s=offset,
        row_start_sample=rows*100,valid=np.ones((16,80),bool),
        run_id=np.zeros(16,int),coherence_id=np.zeros(16,int),
        elapsed_s=rows/10,scatter_elapsed_s=rows/10,
        metadata=dict(echo_output_reference='centroid_compensated',
            pulse_width_s=.02,pulse_bandwidth_hz=400.,prf_hz=10.,baseband_convention=convention))
    cfg=dict(cpi_duration_s=.8,cpi_hop_duration_s=.2)
    receiver=LinearReceiver(echo,cfg,device)
    receiver.check_rows(rows)
    with pytest.raises(ValueError,match='scatter_centroid'):
        LinearReceiver(echo,dict(cfg,period_time_role='receive_centroid'),device)
    original_times=echo.scatter_elapsed_s.copy()
    echo.scatter_elapsed_s[5]+=.03
    with pytest.raises(ValueError,match='慢时间插值'):receiver.check_rows(rows)
    echo.scatter_elapsed_s=original_times
    noise=(rng.normal(size=clean.shape)+1j*rng.normal(size=clean.shape))/np.sqrt(2)
    native_noise=torch.as_tensor(noise,device=device,dtype=torch.complex128)
    transformed_native=receiver.transform(native_noise,rows)
    transformed_numpy=receiver.transform(noise,rows)
    for native,reference in zip(transformed_native,transformed_numpy):
        torch.testing.assert_close(native,reference,rtol=0,atol=0)
    a=10**(-np.array([5.,30.])/20)
    result=receiver.features(receiver.coefficients(receiver.transform(clean,rows),receiver.transform(noise,rows),rows),a)
    for k,amplitude in enumerate(a):
        expected=reference_run_features(echo,cfg,rows,clean+amplitude*noise,
            receiver.crop_axis,receiver.full_axis)
        np.testing.assert_allclose(result[k],expected,rtol=2e-10,atol=2e-12)
    assert np.max(abs(result[0]-result[1]))>1, 'noise fixture must distinguish SNR branches'
    echo.row_start_sample=rows*10
    with pytest.raises(ValueError,match='共享ADC'):receiver.check_rows(rows)


def test_cached_svd_grid_and_all_refined_candidates_match_production():
    from scripts.monte_carlo_period import FixedPredictiveSearch
    rng=np.random.default_rng(1919)
    starts=np.sort(rng.uniform(0,240,20))
    t=np.repeat(starts,3)+np.tile([0,.2,.4],20)
    runs=np.repeat(np.arange(20),3)
    weights=rng.uniform(.2,1,len(t))
    y=np.column_stack([np.cos(2*np.pi*t/p+phase)+.1*rng.normal(size=len(t))
        for p,phase in zip([20,20,20,13.7,13.7],[0,.3,.7,.5,.9])])
    search=FixedPredictiveSearch(t,runs,weights,10,26,100)
    z=search.normalize(y)
    fast=search.score_grid(z)
    reference=np.array([search.scalar(period,z) for period in search.grid])
    np.testing.assert_allclose(fast,reference,atol=3e-13,rtol=3e-13)
    after=search.select(y)
    before=search.production(y)
    assert abs(after['period_s']-before['period_s'])<1e-5
    np.testing.assert_allclose([r['period_s'] for r in after['candidates']],
        [r['period_s'] for r in before['candidates']],rtol=1e-5,atol=1e-4)
    assert np.max(abs(fast[:,0]-fast[:,4]))>.3


@pytest.mark.parametrize('device',['cpu','cuda:0'])
def test_batched_all_peak_proposals_keep_reference_winner(device):
    import torch
    from scripts.monte_carlo_refinement import BatchedPredictiveSearch
    from scripts.monte_carlo_period import FixedPredictiveSearch
    if device=='cuda:0' and not torch.cuda.is_available():pytest.skip('CUDA unavailable')
    rng=np.random.default_rng(2323)
    t=np.repeat(np.sort(rng.uniform(0,240,20)),3)+np.tile([0,.2,.4],20)
    runs=np.repeat(np.arange(20),3);w=rng.uniform(.2,1,len(t))
    search=BatchedPredictiveSearch(t,runs,w,10,26,100,device=device)
    for noise in (.01,.5):
        y=np.column_stack([np.cos(2*np.pi*t/p+k*.3)+noise*rng.normal(size=len(t))
            for k,p in enumerate((20,20,20,13.7,13.7))])
        result=search.select(y)
        ref=FixedPredictiveSearch.select(search,y)
        assert abs(result['period_s']-ref['period_s'])<1e-7
        np.testing.assert_allclose([r['period_s'] for r in result['candidates']],
            [r['period_s'] for r in ref['candidates']],rtol=1e-5,atol=.001)
        z=search.normalize(y)
        denominator=np.zeros(5)
        for train,test,*_ in search.blocks:
            mean=np.average(z[train],weights=search.w[train],axis=0)
            denominator+=np.sum(search.w[test,None]*(z[test]-mean)**2,axis=0)
        periods=np.linspace(10,26,97)
        expected=np.array([np.median(search.scalar(p,z)) for p in periods])
        np.testing.assert_allclose(search.objective_many(periods,z,denominator),expected,atol=1e-11)


@pytest.mark.parametrize('change',[
    {'period_time_role':'receive_centroid'}, {'period_selection':'legacy_consensus'},
    {'refine_period':False}, {'harmonics':2}, {'los_phase_compensation':True},
    {'doppler_estimator':'narrowband_lag'},
])
def test_receiver_protocol_rejects_incompatible_policies(change):
    from scripts.experiment_receiver_snr import validate_protocol
    validate_protocol({})
    with pytest.raises(ValueError,match='本协议仅支持'):validate_protocol(change)


def test_batched_bounded_brent_matches_scipy_on_multimodal_brackets():
    from scipy.optimize import minimize_scalar
    from scripts.scipy_bounded_batch import bounded_many
    offsets=np.arange(20)*.137
    lower=np.linspace(1,10,20);upper=lower+np.linspace(.1,10,20)
    def objective(x):return np.sin(x*17+offsets)+.1*np.cos(x*3-offsets)
    points,values,success,_=bounded_many(objective,lower,upper)
    expected=[minimize_scalar(lambda x:np.sin(x*17+offsets[i])+.1*np.cos(x*3-offsets[i]),
        bounds=(lower[i],upper[i]),method='bounded') for i in range(20)]
    assert success.all()
    np.testing.assert_allclose(points,[r.x for r in expected],atol=1e-12,rtol=1e-12)
    np.testing.assert_allclose(values,[r.fun for r in expected],atol=1e-12,rtol=1e-12)


def test_coarse_multimodal_search_keeps_reference_winner():
    from scripts.monte_carlo_period import FixedPredictiveSearch
    from scripts.monte_carlo_refinement import BatchedPredictiveSearch
    rng=np.random.default_rng(991)
    t=np.sort(rng.uniform(0,2000,60));runs=np.repeat(np.arange(20),3);w=np.ones(60)
    reference=FixedPredictiveSearch(t,runs,w,10,26,10)
    batched=BatchedPredictiveSearch(t,runs,w,10,26,10)
    for trial in range(10):
        y=np.column_stack([np.cos(2*np.pi*t/p+phase)+rng.normal(size=60)*.2
            for p,phase in zip(rng.uniform(10,26,5),rng.uniform(0,6,5))])
    # Trial 9 distinguishes bounded Brent from golden-section proposals:
    # the latter selects 10.179 s instead of the reference 12.133 s.
    actual=batched.select(y);expected=reference.select(y)
    assert abs(expected['period_s']-12.13288162605117)<1e-7
    assert abs(actual['period_s']-expected['period_s'])<1e-7
