"""Saved-feature model sensitivity probe: no IQ and no truth in search."""
import argparse,json,sys,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inversion.src.inversion import multi_harmonic_lomb_scargle
from inversion.src.result_views import file_identity


def design(t,period,h):
    phase=2*np.pi*(t-t.min())/period
    return np.column_stack([np.ones(len(t))]+[f(k*phase) for k in range(1,h+1) for f in (np.cos,np.sin)])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--observables',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();before=file_identity(args.observables)
    with np.load(args.observables,allow_pickle=False) as data:
        t=data['time_elapsed_s'];y=data['value'];runs=data['run_id'];names=data['feature_names'].tolist()
        metadata=json.loads(data['metadata_json'].item())
    records=[];start=time.perf_counter()
    for column,name in enumerate(names):
        finite=np.isfinite(t)&np.isfinite(y[:,column]);values=y[:,column]
        for h in (1,2,4):
            for fold in ('all',0,1):
                train=finite if fold=='all' else finite&(runs%2==fold)
                result=multi_harmonic_lomb_scargle(t[train],values[train],1800.,14400.,1200,harmonics=h,refine_period=True)
                period=float(result.best_period_s);matrix=design(t,period,h)
                coef=np.linalg.lstsq(matrix[train],values[train],rcond=None)[0]
                test=finite&~train
                error=float(np.mean((values[test]-matrix[test]@coef)**2)/np.var(values[train])) if test.any() else None
                records.append(dict(feature=name,harmonics=h,fold=fold,period_s=period,heldout_normalized_mse=error))
                print(f'{name} H={h} fold={fold}: {period:.6f}s',flush=True)
    if before!=file_identity(args.observables):raise ValueError('Saved features changed during probe')
    payload=dict(measured_utc=datetime.now(timezone.utc).isoformat(),source=before,metadata=metadata,
        protocol='1800..14400s; H1/2/4; all or even/odd whole Runs; no phase compensation; no truth used',
        seconds=time.perf_counter()-start,records=records)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(payload,indent=2),encoding='utf-8')


if __name__=='__main__':main()
