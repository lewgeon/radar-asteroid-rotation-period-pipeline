"""Target-size CPU/CUDA A/B of science and search, without output/cache writes."""
import argparse,json,sys,time,platform
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inversion.src.dataset import load_echo
from inversion.src.inversion import estimate_rotation
from inversion.src.compute_backend import resolve_device
from inversion.src.result_views import file_identity


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--echo',type=Path,required=True);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    config=json.loads(args.config.read_text(encoding='utf-8'));config.pop('output_path',None)
    config['uncertainty_method']='none';config['compare_methods']=False
    config['doppler_estimator']='spectral_moments'
    identity=file_identity(args.echo)
    echo=load_echo(args.echo,mapped_directory=args.echo.parent/'processing_cache/mapped',load_clean=False)
    if hasattr(echo,'_processing_store'):del echo._processing_store
    if resolve_device({'compute_device':'cuda:0'})['actual']!='cuda:0':raise RuntimeError('CUDA is required for paired comparison')
    import torch
    records=[];results={}
    for device in ('cpu','cuda:0'):
        cfg={**config,'compute_device':device}
        def progress(stage,percent,message):
            if percent%10==0:print(device,percent,message,flush=True)
        torch.cuda.synchronize();start=time.perf_counter()
        result=estimate_rotation(echo,cfg,progress)
        torch.cuda.synchronize();elapsed=time.perf_counter()-start
        results[device]=result
        records.append(dict(device=device,seconds=elapsed,periods={k:v.best_period_s for k,v in result.periods.items()},diagnostics=result.search_diagnostics))
        print(device,'completed',elapsed,flush=True)
        with (args.output/'records.json').open('w',encoding='utf-8') as stream:json.dump(records,stream,indent=2)
    differences={}
    for name in vars(results['cpu'].features):
        a=getattr(results['cpu'].features,name);b=getattr(results['cuda:0'].features,name)
        if isinstance(a,np.ndarray):
            finite=np.isfinite(a)&np.isfinite(b)
            differences[name]=dict(max_abs=float(np.max(abs(a[finite]-b[finite]))) if finite.any() else None,
                finite_mask_equal=bool(np.array_equal(np.isfinite(a),np.isfinite(b))))
    if file_identity(args.echo)!=identity:raise ValueError('Input changed during benchmark')
    payload=dict(measured_utc=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),source=identity,
        config=config,gpu=torch.cuda.get_device_name(0),shape=list(echo.iq.shape),records=records,differences=differences,
        scope='one same-session pair; mapped IQ already loaded; full scientific feature extraction and search; no science cache reads/writes, inspection export or HTML')
    (args.output/'result.json').write_bytes(json.dumps(payload,indent=2).encode('utf-8'))
    print(json.dumps(differences,indent=2),flush=True)


if __name__=='__main__':main()
