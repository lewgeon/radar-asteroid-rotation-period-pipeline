"""Select on stationary full-IQ controls, freeze models, then test geometry."""
from __future__ import annotations
import os
for variable in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[variable]='1'
import argparse
import json
from pathlib import Path
import sys
import time
from datetime import datetime,timezone
import gc
import numpy as np
from tqdm import tqdm
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_cross_domain_period import extract,load_echo,effective_look_phase
from scripts.experiment_optional_period_precision import search,sha256,receiver_noise
from scripts.research_period_estimators import spline_search,kernel_search
from scripts.layered_period_estimators import fourier_search

POLE={'spin_axis_ra_deg':105.,'spin_axis_dec_deg':-66.,'phase_period_convention':'half_rotation'}

def compensation(echo,times,mode):
    if mode=='off':
        return None
    exact=effective_look_phase(echo,times,POLE)
    if mode=='per_epoch':
        return exact
    if mode=='linear':
        dt=times-times.min()
        slope=np.polyfit(dt,exact,1)[0]
        return slope*dt
    raise ValueError('Unknown compensation')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--controls',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    files=[args.controls/'generation.json',args.controls/'stationary/echo.npz',args.controls/'azimuth_only/echo.npz',
        ROOT/'runs/paras_for_70m_3h/echo/echo.npz']
    inputs={str(path.resolve()):sha256(path) for path in files}
    generation=json.loads(files[0].read_text(encoding='utf-8'))
    for r in generation['records']:
        if sha256(args.controls/r['mode']/'echo.npz')!=r['echo_sha256']:
            raise ValueError('Generated control changed')
    source_paths=[Path(__file__),ROOT/'scripts/layered_period_estimators.py',ROOT/'scripts/research_period_estimators.py',
        ROOT/'scripts/experiment_cross_domain_period.py',ROOT/'scripts/experiment_optional_period_precision.py']+list((ROOT/'inversion/src').glob('*.py'))
    sources={str(path.relative_to(ROOT)):sha256(path) for path in source_paths}
    rows=[]
    selected={}
    start=time.perf_counter()
    def save():
        if any(sha256(ROOT/k)!=v for k,v in sources.items()) or any(sha256(k)!=v for k,v in inputs.items()):
            raise ValueError('Frozen source or input changed during experiment')
        (args.output/'results.json').write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),
            'seconds':time.perf_counter()-start,'source_hashes':sources,'input_hashes':inputs,
            'generation':generation,'selected':selected,'records':rows},indent=2),encoding='utf-8')
    def add(rec,**labels):
        rows.append(dict(rec,**labels,error_s=rec['period_s']-5400.))
    stationary=load_echo(files[1])
    t,values,_=extract(stationary)
    reps=('centroid','profile_shape')
    baseline=search(t,values['centroid'][:,0],None,1,True,4000)
    center=baseline['period_s']
    for name in tqdm(reps,desc='Stationary blocked model selection'):
        y=values[name]
        for method,solver,configs in [
            ('fourier',fourier_search,[{'harmonics':h,'penalty':lam} for h in (1,2,4,8,16) for lam in (0.,.001,.1)]),
            ('spline',spline_search,[{'knots':k,'penalty':lam} for k in (8,16,32,64) for lam in (.001,.1,10.)])]:
            candidates=[]
            for cfg in configs:
                rec=solver(t,y,None,center,**cfg)
                folds=[]
                for test in np.array_split(np.arange(len(t)),5):
                    train=np.ones(len(t),bool)
                    train[test]=False
                    folds.append(solver(t,y,None,center,grid=81,train=train,**cfg))
                rec.update(cv_mse=float(np.mean([r['test_rmse']**2 for r in folds])),folds=folds)
                add(rec,stage='static_selection',geometry='stationary',representation=name,method=method,compensation='off')
                candidates.append((rec,cfg))
            best,cfg=min(candidates,key=lambda pair:pair[0]['cv_mse'])
            selected[f'{method}:{name}']=cfg
            add({k:v for k,v in best.items() if k!='folds'},stage='selected',geometry='stationary',representation=name,method=method,compensation='off')
            save()
    for geometry,path in [('stationary',files[1]),('azimuth_only',files[2]),('original_dynamic',files[3])]:
        echo=stationary if geometry=='stationary' else load_echo(path)
        times,nv,_=extract(echo)
        if not np.array_equal(times,t):
            raise ValueError('Controls must share scatter epochs')
        phase=compensation(echo,t,'per_epoch')
        if geometry=='stationary' and np.max(np.abs(phase))>1e-12:
            raise ValueError('Stationary control has varying phase')
        for mode in tqdm(('off','linear','per_epoch'),desc=geometry):
            off=compensation(echo,t,mode)
            rec=search(t,nv['centroid'][:,0],off,1,True,4000)
            add(rec,stage='comparison',geometry=geometry,representation='centroid',method='H1',compensation=mode)
            c=rec['period_s']
            for name in reps:
                y=nv[name]
                add(fourier_search(t,y,off,c,harmonics=1,penalty=0.),stage='comparison',geometry=geometry,
                    representation=name,method='fourier_H1',compensation=mode)
                for method,solver in [('fourier',fourier_search),('spline',spline_search)]:
                    add(solver(t,y,off,c,**selected[f'{method}:{name}']),stage='comparison',geometry=geometry,
                        representation=name,method=method,compensation=mode)
                add(kernel_search(t,y,off,c,pairs=len(t)*(len(t)-1)//2,time_width=.5,grid=81),stage='comparison',
                    geometry=geometry,representation=name,method='kernel_all',compensation=mode)
            save()
        del nv
        if geometry!='stationary':
            del echo
        gc.collect()
    for seed in tqdm((20261031,20261032,20261033),desc='Stationary paired IQ noise 20 dB'):
        noisy=receiver_noise(stationary,20.,seed)
        nt,nv,_=extract(noisy)
        if not np.array_equal(nt,t):
            raise ValueError('Noise changed epochs')
        rec=search(t,nv['centroid'][:,0],None,1,True,4000)
        add(rec,stage='noise',geometry='stationary',method='H1',representation='centroid',compensation='off',seed=seed)
        for name in reps:
            for method,solver in [('fourier',fourier_search),('spline',spline_search)]:
                add(solver(t,nv[name],None,rec['period_s'],**selected[f'{method}:{name}']),stage='noise',geometry='stationary',
                    method=method,representation=name,compensation='off',seed=seed)
            add(kernel_search(t,nv[name],None,rec['period_s'],pairs=len(t)*(len(t)-1)//2,time_width=.5,grid=81),
                stage='noise',geometry='stationary',method='kernel_all',representation=name,compensation='off',seed=seed)
        del noisy,nv
        gc.collect()
        save()
    save()
    print(json.dumps({'records':len(rows),'seconds':time.perf_counter()-start,'output':str(args.output)}))

if __name__=='__main__':
    main()
