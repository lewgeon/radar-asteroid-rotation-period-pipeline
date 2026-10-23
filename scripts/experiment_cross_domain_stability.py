"""Predeclared stability extension; hyperparameters selected by blocked prediction."""
from __future__ import annotations
import os
for variable in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):
    os.environ[variable]='1'
import argparse
import gc
import json
import time
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from tqdm import tqdm
from scripts.experiment_cross_domain_period import ROOT,extract,load_echo,effective_look_phase,sha256,receiver_noise,search
from scripts.research_period_estimators import spline_search,kernel_search,pair_indices

def distances(y,i,j):
    output=np.empty(len(i))
    for start in range(0,len(i),16384):
        sl=slice(start,start+16384)
        output[sl]=np.sqrt(np.sum((y[i[sl]]-y[j[sl]])**2,axis=1))
    return output

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    base=json.loads(args.base.read_text(encoding='utf-8'))
    start=time.perf_counter()
    dependencies=list(base['source_hashes'])+[str(Path(__file__).relative_to(ROOT))]
    hashes={name:sha256(ROOT/name) for name in dependencies}
    if any(hashes[name]!=digest for name,digest in base['source_hashes'].items()):
        raise ValueError('Shared dependencies differ from baseline CV')
    base_hash=sha256(args.base)
    path=ROOT/'runs/paras_for_70m_3h/echo/echo.npz'
    if sha256(path)!=base['input_sha256']:
        raise ValueError('Frozen input changed')
    echo=load_echo(path)
    t,values,_=extract(echo)
    offset=effective_look_phase(echo,t,{'spin_axis_ra_deg':105.,'spin_axis_dec_deg':-66.,'phase_period_convention':'half_rotation'})
    rows=[]
    chosen={}
    def add(rec,**labels):
        rows.append(dict(rec,**labels,error_s=rec['period_s']-5400.))
    def save():
        if any(sha256(ROOT/k)!=v for k,v in hashes.items()) or sha256(args.base)!=base_hash:
            raise ValueError('Source or baseline changed during experiment')
        result={'created_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':hashes,
            'input_sha256':base['input_sha256'],'base_sha256':base_hash,'seconds':time.perf_counter()-start,
            'selected':chosen,'records':rows}
        (args.output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    for phase in tqdm((False,True),desc='Extend spline CV to 64 knots'):
        off=offset if phase else None
        center=base['centers'][str(int(phase))]
        for name,y in values.items():
            candidates=[r for r in base['records'] if r['stage']=='spline_scan' and r['phase']==phase and r['representation']==name]
            for penalty in (.001,.1,10.):
                rec=spline_search(t,y,off,center,64,penalty)
                folds=[]
                for test in np.array_split(np.arange(len(t)),5):
                    train=np.ones(len(t),bool)
                    train[test]=False
                    folds.append(spline_search(t,y,off,center,64,penalty,grid=81,train=train))
                rec.update(cv_mse=float(np.mean([f['test_rmse']**2 for f in folds])),folds=folds)
                add(rec,stage='extended_scan',representation=name,phase=phase)
                candidates.append(rec)
            best=min(candidates,key=lambda r:r['cv_mse'])
            cfg={k:best[k] for k in ('knots','penalty')}
            chosen[f'{name}:phase{int(phase)}']=cfg
            add({k:v for k,v in best.items() if k!='folds'},stage='extended_selected',representation=name,phase=phase)
            for family,settings in [('initial',base['selected'][f'{name}:phase{int(phase)}']),('extended',cfg)]:
                for fraction in (0.,.25,.5,.75):
                    shifted=(np.zeros(len(t)) if off is None else off)+fraction*2*np.pi/settings['knots']
                    add(spline_search(t,y,shifted,center,**settings),stage='origin',representation=name,phase=phase,
                        family=family,knot_fraction=fraction)
            save()
    for bins in tqdm((64,128,256,512),desc='Fixed profile resolution scan'):
        current=values if bins==64 else extract(echo,bins)[1]
        for phase in (False,True):
            for name in ('profile_power','profile_shape'):
                for family,settings in [('initial',base['selected'][f'{name}:phase{int(phase)}']),
                    ('extended',chosen[f'{name}:phase{int(phase)}'])]:
                    add(spline_search(t,current[name],offset if phase else None,base['centers'][str(int(phase))],**settings),
                        stage='bins',representation=name,phase=phase,family=family,bins=bins)
        del current
        gc.collect()
        save()
    for name in tqdm(('centroid','profile_shape'),desc='Controlled kernel pair sampling'):
        y=values[name]
        total=len(t)*(len(t)-1)//2
        i,j=pair_indices(len(t),total)
        absolute_width=float(np.median(distances(y,i,j)))
        for count in (40000,160000,total):
            for seed in ((20261011,) if count==total else (20261011,20261111,20261211)):
                i,j=pair_indices(len(t),count,seed)
                ratio=absolute_width/float(np.median(distances(y,i,j)))
                add(kernel_search(t,y,offset,base['centers']['1'],pairs=count,time_width=.5,value_width=ratio,grid=81,seed=seed),
                    stage='controlled_kernel',representation=name,phase=True,seed=seed,absolute_width=absolute_width)
        save()
    for seed in tqdm(range(20261021,20261026),desc='Extended selected models paired noise'):
        noisy=receiver_noise(echo,20.,seed)
        nt,nv,_=extract(noisy)
        if not np.array_equal(t,nt):
            raise ValueError('Noise changed times')
        for phase in (False,True):
            off=offset if phase else None
            center=search(t,nv['centroid'][:,0],off,1,True,4000)['period_s']
            for name,y in nv.items():
                add(spline_search(t,y,off,center,**chosen[f'{name}:phase{int(phase)}']),
                    stage='extended_noise',representation=name,phase=phase,seed=seed)
        del noisy,nv
        gc.collect()
        save()
    print(json.dumps({'records':len(rows),'seconds':time.perf_counter()-start,'output':str(args.output)}))

if __name__=='__main__':
    main()
