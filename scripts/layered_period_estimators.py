"""Research Fourier projection with paired sine/cosine shrinkage."""
from __future__ import annotations
import numpy as np
from scripts.research_period_estimators import checked,refine_objective

def fourier_basis(phase,harmonics):
    if isinstance(harmonics,bool) or int(harmonics)!=harmonics or harmonics<1:
        raise ValueError('Positive integer harmonic count required')
    phase=np.asarray(phase,float)
    h=np.arange(1,int(harmonics)+1)
    trig=phase[:,None]*h
    return np.column_stack((np.ones(len(phase)),np.cos(trig),np.sin(trig)))

def fourier_fit(times,values,offset,period,harmonics,penalty,origin):
    if not np.isfinite(penalty) or penalty<0:
        raise ValueError('Nonnegative finite Fourier penalty required')
    x=fourier_basis(2*np.pi*(times-origin)/period+offset,harmonics)
    weights=np.r_[0.,np.tile((np.arange(1,harmonics+1)/harmonics)**4,2)]
    regularizer=penalty*len(times)*weights
    rhs=x.T@values
    beta=np.linalg.solve(x.T@x+np.diag(regularizer),rhs)
    cost=float((np.sum(values**2)-np.sum(rhs*beta))/len(times))
    return cost,beta

def fourier_search(times,values,offset,center,harmonics=4,penalty=0.,grid=161,train=None):
    t,y,off=checked(times,values,offset)
    train=np.ones(len(t),bool) if train is None else np.asarray(train,bool)
    if train.shape!=t.shape or np.count_nonzero(train)<2*harmonics+4:
        raise ValueError('Insufficient Fourier training observations')
    mean=y[train].mean(axis=0)
    scale=float(np.sqrt(np.mean((y[train]-mean)**2)))
    if scale<=0:
        raise ValueError('Constant training observations')
    z=(y-mean)/scale
    objective=lambda p:fourier_fit(t[train],z[train],off[train],p,harmonics,penalty,t.min())[0]
    rec=refine_objective(objective,center,grid=grid)
    _,beta=fourier_fit(t[train],z[train],off[train],rec['period_s'],harmonics,penalty,t.min())
    prediction=fourier_basis(2*np.pi*(t-t.min())/rec['period_s']+off,harmonics)@beta
    test=~train
    rec.update(harmonics=int(harmonics),penalty=float(penalty),
        train_rmse=float(np.sqrt(np.mean((z[train]-prediction[train])**2))),
        test_rmse=None if not test.any() else float(np.sqrt(np.mean((z[test]-prediction[test])**2))))
    return rec
