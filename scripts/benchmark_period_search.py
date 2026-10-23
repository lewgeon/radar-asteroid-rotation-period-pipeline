"""Same-session CPU/CUDA full-grid and whole-Run bootstrap A/B on saved features."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.inversion import multi_harmonic_lomb_scargle, add_harmonics
from inversion.src.period_uncertainty import assess_period_uncertainty, candidate_summary
from inversion.src.period_consensus import _cross_feature_consensus
from inversion.src.period_enhancements import method_options
from inversion.src.result_views import file_identity


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--observables',type=Path,default=ROOT/'runs/seperate_observation_2/inversion/period_observables.npz')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--bootstrap-replicates',type=int,default=30)
    args=parser.parse_args()
    if args.repeats<1 or args.bootstrap_replicates<30:parser.error('repeats>=1 and bootstrap-replicates>=30 required')
    import torch
    if not torch.cuda.is_available():raise RuntimeError('A/B requires CUDA')
    args.output.mkdir(parents=True,exist_ok=False)
    code_paths=(Path(__file__),ROOT/'inversion/src/compute_backend.py',ROOT/'inversion/src/inversion.py',ROOT/'inversion/src/period_uncertainty.py')
    code_identity={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths}
    identity=file_identity(args.observables)
    with np.load(args.observables,allow_pickle=False) as data:
        t=data['time_elapsed_s'];values=data['value'];names=data['feature_names'].tolist()
        runs=data['run_id'];w=data['effective_sample_count'];metadata=json.loads(data['metadata_json'].item())
    cfg=metadata['inversion_config']
    if cfg.get('los_phase_compensation'):raise ValueError('Saved benchmark needs explicit phase geometry; this input must have compensation disabled')
    mapping=dict(total_power='total_power',doppler_centroid_hz='doppler_centroid',rms_bandwidth_hz='doppler_bandwidth',
        range_centroid_s='range_centroid',centroid_delay_s='range_centroid',energy_width_90_s='range_energy_width',energy_range_width_90_s='range_energy_width')
    features={mapping[name]:values[:,i] for i,name in enumerate(names) if name in mapping}
    h=method_options(cfg)['harmonics']
    def search(device):
        return {name:add_harmonics(multi_harmonic_lomb_scargle(t,y,cfg['period_min_s'],cfg['period_max_s'],
            cfg['period_grid_size'],harmonics=h,weights=w,refine_period=cfg.get('refine_period'),compute_device=device),
            cfg['period_min_s'],cfg['period_max_s']) for name,y in features.items()}
    # Initialize libraries/device outside timing, then interleave paired order.
    cpu=search('cpu');gpu=search('cuda:0');torch.cuda.synchronize()
    differences={}
    for name in cpu:
        differences[name]=dict(max_grid_score_difference=float(np.nanmax(abs(cpu[name].grid_scores-gpu[name].grid_scores))),
            cpu_best_period_s=cpu[name].best_period_s,gpu_best_period_s=gpu[name].best_period_s,
            candidate_max_period_difference_s=float(np.max(abs(np.array([c.period_s for c in cpu[name].candidates])-np.array([c.period_s for c in gpu[name].candidates])))),
            compute=gpu[name].search_diagnostics['period_compute'])
    records=[]
    for repetition in range(args.repeats):
        for device in (('cpu','cuda:0') if repetition%2==0 else ('cuda:0','cpu')):
            torch.cuda.synchronize();start=time.perf_counter();search(device);torch.cuda.synchronize()
            records.append(dict(repetition=repetition,device=device,seconds=time.perf_counter()-start))
            print(records[-1],flush=True)
    bootstrap={}
    for device,periods in (('cpu',cpu),('cuda:0',gpu)):
        config={**cfg,'compute_device':device,'uncertainty_method':'run_bootstrap',
            'uncertainty_replicates':args.bootstrap_replicates,'uncertainty_seed':20261015}
        torch.cuda.synchronize();start=time.perf_counter()
        report=assess_period_uncertainty(t,features,runs,periods,config,weights=w)
        torch.cuda.synchronize()
        bootstrap[device]=dict(seconds=time.perf_counter()-start,report=report)
        print('bootstrap',device,bootstrap[device]['seconds'],flush=True)
    if identity!=file_identity(args.observables):raise ValueError('input changed')
    if code_identity!={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in code_paths}:
        raise ValueError('source changed during benchmark; refusing a mixed-version record')
    result=dict(measured_utc=datetime.now(timezone.utc).isoformat(),source=identity,shape=list(values.shape),config=cfg,
        python=platform.python_version(),numpy=np.__version__,torch=torch.__version__,gpu=torch.cuda.get_device_name(0),
        scope='Saved native features, full original grid and local CPU refinement; transfers included; no IQ frontend or export; warm timings',
        records=records,differences=differences,bootstrap=bootstrap,
        medians_s={d:float(np.median([r['seconds'] for r in records if r['device']==d])) for d in ('cpu','cuda:0')},
        consensus={d:_cross_feature_consensus({k:candidate_summary(v) for k,v in p.items()})[0] for d,p in (('cpu',cpu),('cuda:0',gpu))},
        source_sha256=code_identity)
    (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('medians_s','consensus','differences')},indent=2),flush=True)


if __name__=='__main__':main()
