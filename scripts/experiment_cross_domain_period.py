"""First candidate-conditioned unknown-waveform and profile-kernel experiment."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import gc
import json
import os
from pathlib import Path
import sys
import time
for thread_variable in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[thread_variable]='1'
import numpy as np
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.dataset import load_echo
from inversion.src.inversion import prepare_chirp_pulse_profiles, _native_pulse_range_features
from inversion.src.period_enhancements import effective_look_phase
from scripts.experiment_optional_period_precision import sha256,receiver_noise,search
from scripts.research_period_estimators import spline_search,kernel_search,integrated_profile

def extract(echo,bins=64):
    prepared = prepare_chirp_pulse_profiles(echo,{'motion_compensation':'auto'})
    f = _native_pulse_range_features(prepared)
    power,edges = integrated_profile(prepared,echo.metadata['planned_target_extent_path_m'],bins)
    total = power.sum(axis=1)
    if np.any(total<=0):
        raise ValueError('Nonzero pulse power required')
    values = {'centroid':f.centroid_delay_s[:,None], 'profile_power':power,
              'profile_shape':power/total[:,None]}
    times = f.times_s.copy()
    del prepared
    gc.collect()
    return times,values,edges

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    path=ROOT/'runs/paras_for_70m_3h/echo/echo.npz'
    input_hash=sha256(path)
    if input_hash!='add62990c10ab7c4d74f5e2e5d50611cd9201d967399b3b2ed26ee195ee6ba3a':
        raise ValueError('Frozen input changed')
    start=time.perf_counter()
    echo=load_echo(path)
    if not np.array_equal(echo.iq,echo.clean_iq):
        raise ValueError('Baseline must be noiseless')
    times,values,edges=extract(echo)
    pole={'spin_axis_ra_deg':105.,'spin_axis_dec_deg':-66.,'phase_period_convention':'half_rotation'}
    offset=effective_look_phase(echo,times,pole)
    rows=[]
    chosen={}
    centers={}
    source_paths=[Path(__file__),ROOT/'scripts/research_period_estimators.py',
        ROOT/'scripts/experiment_optional_period_precision.py',ROOT/'inversion/src/inversion.py',
        ROOT/'inversion/src/period_enhancements.py',ROOT/'inversion/src/dataset.py',ROOT/'inversion/src/radar_signal.py']
    source_hashes={str(p.relative_to(ROOT)):sha256(p) for p in source_paths}
    def save():
        if any(sha256(ROOT/k)!=v for k,v in source_hashes.items()):
            raise ValueError('Loaded experiment source changed during execution')
        record={'created_utc':datetime.now(timezone.utc).isoformat(),'input_sha256':input_hash,
            'source_hashes':source_hashes,
            'scope':'candidate-conditioned, 3h ellipsoid, known pole, no shape/initial phase',
            'seconds':time.perf_counter()-start,'centers':centers,'selected':chosen,
            'profile_edges_s':edges.tolist(),'records':rows}
        (args.output/'results.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    def add(rec,**labels):
        rows.append(dict(labels,**rec,error_s=rec['period_s']-5400.))
    for phase in (False,True):
        off=offset if phase else None
        baseline=search(times,values['centroid'][:,0],off,1,True,4000)
        golden=5401.5967670188475 if phase else 5404.493479588764
        if abs(baseline['period_s']-golden)>.001:
            raise ValueError('Independent frozen baseline golden mismatch')
        centers[str(int(phase))]=baseline['period_s']
        add(baseline,stage='baseline',method='H1',representation='centroid',phase=phase)
    for phase in tqdm((False,True),desc='Spline / blocked selection'):
        off=offset if phase else None
        center=centers[str(int(phase))]
        for name,y in values.items():
            candidates=[]
            for knots in (8,16,32):
                for penalty in (.001,.1,10.):
                    rec=spline_search(times,y,off,center,knots,penalty)
                    folds=[]
                    for test in np.array_split(np.arange(len(times)),5):
                        train=np.ones(len(times),bool)
                        train[test]=False
                        fold=spline_search(times,y,off,center,knots,penalty,grid=81,train=train)
                        folds.append(fold)
                    score=float(np.mean([f['test_rmse']**2 for f in folds]))
                    rec.update(cv_mse=score,folds=folds)
                    add(rec,stage='spline_scan',method='spline',representation=name,phase=phase)
                    candidates.append(rec)
            best=min(candidates,key=lambda x:x['cv_mse'])
            chosen[f'{name}:phase{int(phase)}']={'knots':best['knots'],'penalty':best['penalty']}
            add({k:v for k,v in best.items() if k!='folds'},stage='selected',method='spline',representation=name,phase=phase)
            save()
    for phase in tqdm((False,True),desc='Kernel width and pair scan'):
        off=offset if phase else None
        center=centers[str(int(phase))]
        for name,y in values.items():
            for width in (.2,.5,1.):
                rec=kernel_search(times,y,off,center,time_width=width)
                add(rec,stage='kernel_scan',method='kernel',representation=name,phase=phase)
            for count in (160000,len(times)*(len(times)-1)//2):
                # Same data-derived ±2% domain; reduced grid followed by continuous optimization.
                rec=kernel_search(times,y,off,center,pairs=count,time_width=.5,grid=81)
                add(rec,stage='pair_stability',method='kernel',representation=name,phase=phase)
            save()
    _,higher,_=extract(echo,128)
    for phase in (False,True):
        for name in ('profile_power','profile_shape'):
            cfg=chosen[f'{name}:phase{int(phase)}']
            rec=spline_search(times,higher[name],offset if phase else None,centers[str(int(phase))],**cfg)
            add(rec,stage='bin_stability',method='spline',representation=name,phase=phase,bins=128)
    del higher
    for seed in tqdm(range(20261021,20261026),desc='Paired receiver noise 20 dB'):
        noisy=receiver_noise(echo,20.,seed)
        nt,nv,_=extract(noisy)
        if not np.array_equal(nt,times):
            raise ValueError('Feature time changed')
        for phase in (False,True):
            off=offset if phase else None
            baseline=search(times,nv['centroid'][:,0],off,1,True,4000)
            center=baseline['period_s']
            add(baseline,stage='noise',method='H1',representation='centroid',phase=phase,seed=seed)
            for name,y in nv.items():
                cfg=chosen[f'{name}:phase{int(phase)}']
                add(spline_search(times,y,off,center,**cfg),stage='noise',method='spline',representation=name,phase=phase,seed=seed)
                add(kernel_search(times,y,off,center,time_width=.5,pairs=160000,grid=81),
                    stage='noise',method='kernel',representation=name,phase=phase,seed=seed)
        del noisy,nv
        gc.collect()
        save()
    for truth in (3600.,5400.,7200.):
        for regime in ('stationary','known_phase','amplitude_drift'):
            imposed=offset if regime!='stationary' else np.zeros(len(times))
            p=2*np.pi*(times-times.min())/truth+imposed
            y=np.exp(1.2*np.cos(p))+.3*np.sin(3*p+.4)
            if regime=='amplitude_drift':
                y *= 1+.08*(times-times.min())/np.ptp(times)
            base=search(times,y,imposed,1,True,4000)
            rec=spline_search(times,y,imposed,base['period_s'],knots=32,penalty=.001)
            rows.append(dict(stage='synthetic',method='spline',regime=regime,truth_s=truth,**rec,error_s=rec['period_s']-truth))
    save()
    print(json.dumps({'records':len(rows),'seconds':time.perf_counter()-start,'output':str(args.output)}),flush=True)

if __name__=='__main__':
    main()
