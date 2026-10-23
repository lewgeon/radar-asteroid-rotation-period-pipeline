import json
from types import SimpleNamespace
import numpy as np
import pytest
from scripts.generate_layered_period_controls import control_observation,rotate_about_axis,C
from scripts.layered_period_estimators import fourier_basis,fourier_fit,fourier_search
from scripts.experiment_layered_period import compensation

TARGET={'spin_pole_frame':'equatorial','spin_pole_icrs_deg':[105.,-66.]}

def fixture():
    t=np.linspace(47000,81000,12)
    v=np.column_stack((np.cos(.4+1e-7*t),np.sin(.4+1e-7*t),np.ones(len(t))*.4))
    v/=np.linalg.norm(v,axis=1)[:,None]
    return {'metadata_json':np.array(json.dumps({'fast_sample_rate_hz':2e8,'fast_sample_count':10403,'pulse_width_s':5e-5})),
        'scatter_elapsed_s':t,'emit_elapsed_s':t-2.,'elapsed_s':t+2.,'tx_los_icrs':v,'rx_los_icrs':v.copy(),
        'tx_range_m':np.linspace(C*2,C*2.1,len(t)),'rx_range_m':np.linspace(C*2,C*2.1,len(t)),
        'row_start_sample':np.zeros(len(t),int),'run_id':np.arange(len(t)),
        'common_path_rate_m_s':np.ones(len(t))*100.,'scatter_receive_rate':np.ones(len(t))*1.001,
        'rx_adc_start_elapsed_s':t+2-1e-6,'rx_adc_stop_elapsed_s':t+2+52e-6,
        'row_fast_time_offset_s':np.ones(len(t))*-1e-6,'centroid_fractional_offset_s':np.zeros(len(t)),
        'signal_echo_overlap':np.zeros(len(t),bool),'window_overlap':np.zeros(len(t),bool),
        'row_valid':np.ones((len(t),10403),bool),'valid_plan':np.ones((len(t),10403),bool),
        'ephemeris_source':np.array('inherited'),'duration_s':np.array(np.ptp(t))}

def test_controls_three_events_adc_and_non_degenerate_intervention():
    original=fixture()
    stationary=control_observation(original,'stationary',TARGET)
    azimuth=control_observation(original,'azimuth_only',TARGET)
    for data in (stationary,azimuth):
        np.testing.assert_allclose(data['scatter_elapsed_s']-data['emit_elapsed_s'],data['tx_range_m']/C,atol=1e-11)
        np.testing.assert_allclose(data['elapsed_s']-data['scatter_elapsed_s'],data['rx_range_m']/C,atol=1e-11)
        assert np.ptp(data['row_fast_time_offset_s'])<=2*np.spacing(np.max(np.abs(data['elapsed_s'])))
        assert np.all(data['common_path_rate_m_s']==0)
        assert np.all(data['scatter_receive_rate']==1)
        np.testing.assert_array_equal(data['scatter_elapsed_s'],original['scatter_elapsed_s'])
    assert np.linalg.norm(azimuth['tx_los_icrs']-stationary['tx_los_icrs'])>1e-4
    assert np.ptp(original['tx_range_m'])>0
    assert np.ptp(stationary['tx_range_m'])==0
    assert np.ptp(original['tx_los_icrs'][:,0])>0

def test_rodrigues_matches_independent_z_axis_geometry():
    angles=np.array([0.,.3,1.2])
    vectors=rotate_about_axis(np.array([.6,0.,.8]),[0.,0.,1.],angles)
    np.testing.assert_allclose(vectors,np.column_stack((.6*np.cos(angles),.6*np.sin(angles),np.full(3,.8))),atol=1e-15)
    other=rotate_about_axis(np.array([0.,.8,.6]),[0.,0.,1.],angles)
    np.testing.assert_allclose(np.sum(vectors*other,axis=1),.48,atol=1e-15)

def test_fourier_cost_independent_augmented_least_squares():
    rng=np.random.default_rng(7)
    t=np.sort(rng.uniform(0,20000,140))
    y=rng.normal(size=(len(t),3))
    off=.02*np.sin(t/10000)
    period,h,penalty=5400.,4,.003
    cost,beta=fourier_fit(t,y,off,period,h,penalty,t.min())
    phase=2*np.pi*(t-t.min())/period+off
    x=np.column_stack([np.ones(len(t))]+[np.cos(k*phase) for k in range(1,h+1)]+[np.sin(k*phase) for k in range(1,h+1)])
    weights=np.r_[0.,np.tile((np.arange(1,h+1)/h)**4,2)]
    root=np.diag(np.sqrt(penalty*len(t)*weights))
    golden=np.linalg.lstsq(np.vstack((x,root)),np.vstack((y,np.zeros((2*h+1,3)))),rcond=None)[0]
    np.testing.assert_allclose(beta,golden,atol=1e-13)
    explicit=(np.sum((y-x@golden)**2)+np.sum((root@golden)**2))/len(t)
    assert abs(cost-explicit)<1e-13

def test_fourier_constant_phase_origin_invariant_and_waveform_guard():
    rng=np.random.default_rng(12)
    t=np.sort(rng.uniform(0,33000,401))
    phase=2*np.pi*t/5400.
    y=np.cos(phase)+.7*np.sin(3*phase+.2)
    exact=fourier_search(t,y,None,5405,harmonics=4)
    shifted=fourier_search(t,y,np.full(len(t),.713),5405,harmonics=4)
    mismatch=fourier_search(t,y,None,5405,harmonics=1)
    assert abs(exact['period_s']-5400)<.001
    assert abs(exact['period_s']-shifted['period_s'])<1e-4
    assert abs(mismatch['period_s']-exact['period_s'])>.1

def test_fourier_training_scale_ignores_heldout_values():
    t=np.linspace(0,32000,201)
    y=np.cos(2*np.pi*t/5400)
    train=np.arange(len(t))<150
    modified=y.copy()
    modified[~train]+=1e4
    one=fourier_search(t,y,None,5405,harmonics=2,train=train)
    two=fourier_search(t,modified,None,5405,harmonics=2,train=train)
    assert one['period_s']==two['period_s']
    assert one['train_rmse']==two['train_rmse']
    assert two['test_rmse']>1000

def test_stationary_compensation_zero_and_linear_vs_epoch_distinct():
    t=np.linspace(0,30000,101)
    v=np.tile([1.,.2,.3],(len(t),1))
    echo=SimpleNamespace(scatter_elapsed_s=t,tx_los_icrs=v,rx_los_icrs=v)
    np.testing.assert_array_equal(compensation(echo,t,'per_epoch'),np.zeros(len(t)))
    assert compensation(echo,t,'off') is None
    angle=1e-7*t+1e-11*t*t
    moved=np.column_stack((np.cos(angle),np.sin(angle),np.full(len(t),.3)))
    echo.tx_los_icrs=echo.rx_los_icrs=moved
    assert np.linalg.norm(compensation(echo,t,'linear')-compensation(echo,t,'per_epoch'))>1e-4

def test_invalid_harmonics_and_control_mode_rejected():
    with pytest.raises(ValueError):
        fourier_basis(np.arange(4),0)
    with pytest.raises(ValueError):
        control_observation(fixture(),'unknown',TARGET)
