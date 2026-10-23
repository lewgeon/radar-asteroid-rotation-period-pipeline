"""Research-only periodic splines and sampled correntropy objectives.

These estimators refine a data-derived candidate; they are not global searches.
"""
from __future__ import annotations
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import minimize_scalar

def checked(times, values, offset):
    t, y = np.asarray(times,float), np.asarray(values,float)
    if y.ndim == 1:
        y = y[:,None]
    off = np.zeros(len(t)) if offset is None else np.asarray(offset,float)
    if t.ndim != 1 or y.ndim != 2 or y.shape[0] != len(t) or off.shape != t.shape:
        raise ValueError('Incompatible time, channel or phase dimensions')
    if len(t)<8 or not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)) or not np.all(np.isfinite(off)):
        raise ValueError('At least eight finite observations required')
    if np.ptp(t)<=0 or np.linalg.norm(y-y.mean(axis=0))<=0:
        raise ValueError('Time span and feature variation must be nonzero')
    return t,y,off

def refine_objective(objective, center, fraction=.02, grid=161):
    if not np.isfinite(center) or center<=0 or not 0<fraction<1 or grid<3:
        raise ValueError('Invalid local search domain')
    periods = np.linspace(center*(1-fraction),center*(1+fraction),grid)
    costs = np.array([objective(p) for p in periods])
    if not np.all(np.isfinite(costs)):
        raise ValueError('Nonfinite research objective')
    j = int(np.argmin(costs))
    lo, hi = periods[max(0,j-1)], periods[min(len(periods)-1,j+1)]
    result = minimize_scalar(objective,bounds=(lo,hi),method='bounded',options={'xatol':1e-7})
    p = float(result.x) if result.success and result.fun<=costs[j] else float(periods[j])
    return {'period_s':p,'cost':float(objective(p)),
        'bounds_s':[float(periods[0]),float(periods[-1])],
        'boundary':bool(j in (0,len(periods)-1))}

def spline_basis(phase, knots):
    if isinstance(knots,bool) or int(knots)!=knots or knots<4:
        raise ValueError('At least four integer periodic knots required')
    knots = int(knots)
    nodes = np.linspace(0,2*np.pi,knots+1)
    coefficients = np.vstack([np.eye(knots),np.eye(knots)[0]])
    return CubicSpline(nodes,coefficients,bc_type='periodic')(np.mod(phase,2*np.pi))

def spline_fit(times, values, offset, period, knots, penalty, origin):
    if not np.isfinite(penalty) or penalty<0:
        raise ValueError('Nonnegative finite penalty required')
    x = spline_basis(2*np.pi*(times-origin)/period+offset,knots)
    d = np.roll(np.eye(knots),1,axis=0)-2*np.eye(knots)+np.roll(np.eye(knots),-1,axis=0)
    reg = penalty*len(times)/knots*(d.T@d)
    matrix = x.T@x+reg
    rhs = x.T@values
    beta = np.linalg.solve(matrix,rhs)
    # Normal-equation identity avoids an N x channels prediction at each trial.
    cost = (np.sum(values**2)-np.sum(beta*rhs))/len(times)
    return float(cost), beta

def spline_search(times, values, offset, center, knots=16, penalty=.1, grid=161, train=None):
    t,y,off = checked(times,values,offset)
    train = np.ones(len(t),bool) if train is None else np.asarray(train,bool)
    if train.shape != t.shape or np.count_nonzero(train)<knots+3:
        raise ValueError('Insufficient training rows for periodic spline')
    mean = y[train].mean(axis=0)
    scale = float(np.sqrt(np.mean((y[train]-mean)**2)))
    if scale<=0:
        raise ValueError('Training channels are constant')
    z = (y-mean)/scale
    objective = lambda p:spline_fit(t[train],z[train],off[train],p,knots,penalty,t.min())[0]
    rec = refine_objective(objective,center,grid=grid)
    _, beta = spline_fit(t[train],z[train],off[train],rec['period_s'],knots,penalty,t.min())
    predicted = spline_basis(2*np.pi*(t-t.min())/rec['period_s']+off,knots)@beta
    test = ~train
    rec.update(knots=int(knots),penalty=float(penalty),
        train_rmse=float(np.sqrt(np.mean((z[train]-predicted[train])**2))),
        test_rmse=None if not test.any() else float(np.sqrt(np.mean((z[test]-predicted[test])**2))))
    return rec

def pair_indices(count, limit, seed=20261011):
    if count<2 or limit<1:
        raise ValueError('Pair count and limit must be positive')
    i,j = np.triu_indices(count,1)
    if len(i)>limit:
        take = np.random.default_rng(seed).choice(len(i),int(limit),replace=False)
        i,j = i[take],j[take]
    return i,j

def kernel_search(times, values, offset, center, *, pairs=40000, time_width=.5,
                  value_width=1., grid=161, seed=20261011):
    t,y,off = checked(times,values,offset)
    if not np.isfinite(time_width) or not np.isfinite(value_width) or min(time_width,value_width)<=0:
        raise ValueError('Positive finite kernel widths required')
    i,j = pair_indices(len(t),pairs,seed)
    dt, dp = t[i]-t[j],off[i]-off[j]
    distances = np.empty(len(i))
    for start in range(0,len(i),16384):
        sl = slice(start,start+16384)
        distances[sl] = np.sqrt(np.sum((y[i[sl]]-y[j[sl]])**2,axis=1))
    width = np.median(distances)*value_width
    if width<=0:
        raise ValueError('Pairwise median feature distance is zero')
    similarity = np.exp(-.5*(distances/width)**2)
    similarity -= similarity.mean()
    taper = .54+.46*np.cos(np.pi*dt/np.ptp(t))
    def objective(p):
        phase = 2*np.pi*dt/p+dp
        periodic = np.exp(-2*np.sin(phase/2)**2/time_width**2)
        return -float(np.mean(similarity*periodic*taper))
    rec = refine_objective(objective,center,grid=grid)
    rec.update(pairs=int(len(i)),time_width=float(time_width),value_width=float(value_width))
    return rec

def integrated_profile(prepared, extent_path_m, bins=64):
    """Conserve all native power; fine fixed central bins and two tail bins.

    Samples represent equal-width cells centered on physical delay epochs.
    Tail bins retain all power beyond the acquisition extent, without a gate.
    """
    if not np.isfinite(extent_path_m) or extent_path_m<=0 or bins<4:
        raise ValueError('Positive acquisition extent and at least four bins required')
    axes = prepared['full_delay_axes']
    iq = prepared['full_compressed']
    dt = float(np.median(np.diff(axes[0])))
    extent = extent_path_m/299792458.
    lo, hi = float(axes.min()-dt/2),float(axes.max()+dt/2)
    if not lo < -extent < extent < hi:
        raise ValueError('Full native correlation does not cover central profile bins')
    edges = np.r_[lo,np.linspace(-extent,extent,int(bins)+1),hi]
    output = np.empty((len(axes),len(edges)-1))
    for row,(axis,signal) in enumerate(zip(axes,iq)):
        power = np.abs(signal.astype(np.complex128))**2
        cumulative = np.r_[0.,np.cumsum(power)]
        cell_edges = np.r_[axis[0]-dt/2,axis+dt/2]
        output[row] = np.diff(np.interp(edges,cell_edges,cumulative,left=0.,right=cumulative[-1]))
        if not np.isclose(output[row].sum(),power.sum(),rtol=1e-11,atol=1e-12):
            raise ValueError('Native power not conserved')
    return output,edges
