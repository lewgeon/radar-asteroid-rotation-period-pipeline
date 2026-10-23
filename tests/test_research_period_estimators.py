import numpy as np
import pytest
from scripts.research_period_estimators import spline_basis, spline_fit, spline_search, kernel_search, integrated_profile, pair_indices

def fixture():
    t = np.sort(np.random.default_rng(19).uniform(0,34000,320))
    off = -.09*(t/t.max())**2
    p = 2*np.pi*t/5400+off
    y = np.exp(1.2*np.cos(p))+.3*np.sin(3*p+.4)
    return t,off,y

def test_spline_partition_and_periodicity():
    p = np.linspace(-3,12,67)
    x = spline_basis(p,16)
    np.testing.assert_allclose(x.sum(axis=1),1,atol=1e-14)
    np.testing.assert_allclose(x,spline_basis(p+2*np.pi,16),atol=1e-14)

def test_penalized_projection_matches_independent_augmented_lstsq():
    t,off,y = fixture()
    y = np.column_stack([y,np.sin(t/831)])
    x = spline_basis(2*np.pi*(t-t.min())/5410+off,16)
    d = np.roll(np.eye(16),1,axis=0)-2*np.eye(16)+np.roll(np.eye(16),-1,axis=0)
    penalty=.1
    augmented = np.vstack([x,np.sqrt(penalty*len(t)/16)*d])
    target = np.vstack([y,np.zeros((16,2))])
    beta=np.linalg.lstsq(augmented,target,rcond=None)[0]
    cost,actual=spline_fit(t,y,off,5410,16,penalty,t.min())
    np.testing.assert_allclose(actual,beta,rtol=1e-10,atol=1e-10)
    assert abs(cost-np.sum((target-augmented@beta)**2)/len(t))<1e-12

def test_unknown_waveform_and_phase_sensitive_guard():
    t,off,y = fixture()
    correct = spline_search(t,y,off,5405,knots=32,penalty=1e-6,grid=61)
    raw = spline_search(t,y,None,5405,knots=32,penalty=1e-6,grid=61)
    coarse = spline_search(t,y,off,5405,knots=8,penalty=10,grid=61)
    assert abs(correct['period_s']-5400)<.05
    assert abs(raw['period_s']-correct['period_s'])>1
    assert abs(coarse['period_s']-correct['period_s'])>.1

def test_knots_and_penalty_independently_separate():
    t,off,y=fixture()
    base=spline_search(t,y,off,5405,knots=8,penalty=.1,grid=61)
    more=spline_search(t,y,off,5405,knots=32,penalty=.1,grid=61)
    ridge=spline_search(t,y,off,5405,knots=8,penalty=10,grid=61)
    assert abs(base['period_s']-more['period_s'])>.01
    assert abs(base['period_s']-ridge['period_s'])>.01

def test_held_out_values_do_not_change_fitted_period_or_training_scale():
    t,off,y=fixture()
    train=np.ones(len(t),bool)
    train[-60:]=False
    changed=y.copy()
    changed[~train]+=1e6
    a=spline_search(t,y,off,5405,knots=16,penalty=.1,grid=61,train=train)
    b=spline_search(t,changed,off,5405,knots=16,penalty=.1,grid=61,train=train)
    assert a['period_s']==b['period_s']
    assert a['train_rmse']==b['train_rmse']
    assert b['test_rmse']>1e5*a['test_rmse']

def test_kernel_pairing_and_bandwidth_sensitive_guard():
    t,off,y = fixture()
    i,j = pair_indices(len(t),4000)
    assert np.all(i<j) and len(np.unique(i*len(t)+j))==4000
    np.testing.assert_array_equal(i,pair_indices(len(t),4000)[0])
    a = kernel_search(t,y,off,5405,pairs=4000,time_width=.2,grid=61)
    b = kernel_search(t,y,off,5405,pairs=4000,time_width=1,grid=61)
    assert abs(a['period_s']-b['period_s'])>.01

def test_native_power_conserved_with_shifted_cells():
    axis = np.linspace(-3e-6,3e-6,81)
    axes = np.array([axis,axis+2e-8])
    iq = np.array([np.exp(-(axis/5e-7)**2),2*np.exp(-((axis-1e-7)/5e-7)**2)],complex)
    out,_ = integrated_profile({'full_delay_axes':axes,'full_compressed':iq},300.,16)
    np.testing.assert_allclose(out.sum(axis=1),np.sum(abs(iq)**2,axis=1),rtol=1e-12)
    assert np.linalg.norm(out[0]-out[1])>1

def test_native_cell_distribution_independent_golden():
    # Extent=1s; central edges -1,-.5,0,.5,1. A cell at zero
    # spans [-.5,.5] and contributes equally to the two central bins.
    axis=np.arange(-3.,4.)
    iq=np.zeros((1,7),complex)
    iq[0,3]=1
    iq[0,0]=2
    out,_=integrated_profile({'full_delay_axes':axis[None,:],'full_compressed':iq},299792458.,4)
    np.testing.assert_allclose(out[0],[4.,0.,.5,.5,0.,0.],atol=1e-15)

def test_kernel_phase_origin_cancels():
    t,off,y=fixture()
    a=kernel_search(t,y,off,5405,pairs=4000,grid=61)
    b=kernel_search(t,y,off+.4,5405,pairs=4000,grid=61)
    assert abs(a['period_s']-b['period_s'])<1e-4

def test_invalid_constant_and_kernel_width():
    with pytest.raises(ValueError,match='variation'):
        spline_search(np.arange(20),np.ones(20),None,5,knots=8)
    t,o,y = fixture()
    with pytest.raises(ValueError,match='width'):
        kernel_search(t,y,o,5405,time_width=0)
