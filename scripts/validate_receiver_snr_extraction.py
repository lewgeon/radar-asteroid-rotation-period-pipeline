"""Certify completed Monte Carlo arrays against both production precisions.

Can finish metadata after a legacy-precision comparison rejected an otherwise
complete extraction. Keeps its failure log and original source copies intact.
"""
import argparse,hashlib,json,sys,time,os
from datetime import datetime,timezone
from pathlib import Path
for setting in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[setting]='1'
import numpy as np
from tqdm import tqdm
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_receiver_snr import hashes,write,validate_protocol
from scripts.monte_carlo_receiver import LinearReceiver,reference_run_features,FEATURE_NAMES
from inversion.src.dataset import load_echo


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--echo',type=Path,default=ROOT/'runs/seperate_observation_2/echo/echo.npz')
    p.add_argument('--snapshot',type=Path,default=ROOT/'runs/seperate_observation_2/inversion_upgrade_20261016/period_observables.npz')
    p.add_argument('--seed',type=int,default=20261016)
    args=p.parse_args();folder=args.output;started=time.perf_counter()
    if (folder/'extraction.json').exists():raise FileExistsError('已存在验收，不覆盖')
    progress=json.loads((folder/'progress.json').read_text(encoding='utf-8'))
    if progress['runs_completed']!=progress['total_runs']:raise ValueError('前端尚未完成')
    feature=np.load(folder/'features.npy',mmap_mode='r');clean=np.load(folder/'clean_features.npy')
    if not np.all(np.isfinite(feature)) or not np.all(np.isfinite(clean)):raise ValueError('前端有未完成或无效数据')
    if feature.shape[1]!=26:raise ValueError('SNR形状不匹配')
    with np.load(args.snapshot) as d:
        metadata=json.loads(d['metadata_json'].item());cfg=metadata['inversion_config']
        baseline=d['value'];times=d['time_elapsed_s'];runs=d['run_id'];weights=d['effective_sample_count']
    validate_protocol(cfg)
    initial=hashes();echo=load_echo(args.echo,mapped_directory=folder/'validation_mapped',load_clean=False)
    try:
        receiver=LinearReceiver(echo,cfg,'cpu');groups=np.unique(echo.run_id)
        power=0.;samples=0;rowsets=[]
        for run in groups:
            rows=np.flatnonzero(echo.run_id==run);receiver.check_rows(rows)
            raw=np.asarray(echo.iq[rows],complex);power+=float(np.vdot(raw,raw).real);samples+=raw.size
            rowsets.append(rows)
        power/=samples
        checks=[];offset=0;zero_delta=np.zeros(5);legacy_delta=np.zeros(5)
        for index,rows in enumerate(tqdm(rowsets,desc='Independent precision validation',file=sys.stdout)):
            raw=np.array(echo.iq[rows]);count=(len(rows)-receiver.count)//receiver.hop+1
            expected=reference_run_features(echo,dict(cfg,compute_device='cpu'),rows,raw.astype(complex),receiver.crop_axis,receiver.full_axis)
            old=reference_run_features(echo,cfg,rows,raw,receiver.crop_axis,receiver.full_axis)
            current=clean[offset:offset+count]
            np.testing.assert_allclose(current,expected,rtol=2e-9,atol=1e-14)
            np.testing.assert_allclose(old,baseline[offset:offset+count],rtol=2e-9,atol=1e-14)
            zero_delta=np.maximum(zero_delta,np.max(abs(current-expected)/np.maximum(np.max(abs(expected),axis=0),1e-25),axis=0))
            legacy_delta=np.maximum(legacy_delta,np.max(abs(old-baseline[offset:offset+count]),axis=0))
            starts=np.arange(0,len(rows)-receiver.count+1,receiver.hop)
            np.testing.assert_allclose(times[offset:offset+count],[np.mean(echo.scatter_elapsed_s[rows[s:s+receiver.count]]) for s in starts],atol=1e-9,rtol=0)
            np.testing.assert_allclose(weights[offset:offset+count],receiver.count/np.ceil(receiver.count/receiver.hop))
            if index in (0,len(rowsets)//2,len(rowsets)-1):
                for trial in (0,feature.shape[0]//2,feature.shape[0]-1):
                    rng=np.random.default_rng(np.random.SeedSequence([args.seed,trial,int(groups[index])]))
                    noise=np.sqrt(power/2)*(rng.standard_normal(raw.shape)+1j*rng.standard_normal(raw.shape))
                    for j in (0,13,25):
                        snr=5+j;amplitude=10**(-snr/20)
                        direct=reference_run_features(echo,dict(cfg,compute_device='cpu'),rows,raw.astype(complex)+amplitude*noise,receiver.crop_axis,receiver.full_axis)
                        saved=feature[trial,j,offset:offset+count]
                        relative=np.max(abs(direct-saved)/np.maximum(np.max(abs(direct),axis=0),1e-25),axis=0)
                        if np.any(relative>2e-9):raise AssertionError(f'含噪CPU独立前端不一致: {relative}')
                        checks.append(dict(run=int(groups[index]),trial=trial,snr_db=snr,max_scale_relative_delta=relative.tolist()))
            offset+=count
            write(folder/'validation_progress.json',dict(runs_completed=index+1,total_runs=len(rowsets),seconds=time.perf_counter()-started))
        if offset!=feature.shape[2]:raise AssertionError('完整帧数量不一致')
        snr=np.arange(5.,31.)
        np.savez(folder/'design.npz',times=times,runs=runs,weights=weights,snr_db=snr)
        evidence_sources=folder/'failed_extraction_sources'
        original={p.name:digest(p) for p in evidence_sources.glob('*.py')}
        manifest=dict(measured_utc=datetime.now(timezone.utc).isoformat(),input=dict(path=str(args.echo.resolve()),size_bytes=args.echo.stat().st_size,mtime_ns=args.echo.stat().st_mtime_ns),
            input_sha256=digest(args.echo),snapshot_sha256=digest(args.snapshot),
            source_hashes_at_start=initial,source_hashes_at_end=hashes(),
            source_identity_scope='independent full-array validation after completed extraction rejected legacy float32 FFT roundoff',
            extraction_sources_archived_after_failure=original,
            config=dict(cfg,compute_device='cuda:0'),feature_names=list(FEATURE_NAMES),snr_db=snr.tolist(),
            trials=feature.shape[0],seed=args.seed,run_count=len(groups),cpi_count=offset,
            power_definition='mean clean power over unique valid saved ADC samples; not the full Run continuous-ADC aperture',
            signal_power=power,noise_real_imag_variance_at_0_db=power/2,
            noise='circular complex iid Gaussian at receive IQ, disjoint global ADC indices asserted per Run; no per-realization normalization',
            snr_pairing='same unit noise for all 26 SNR points within trial; independent trial/run SeedSequence',
            actual_device='cuda:0',dtype='complex128/float64',truth_repetition_s=5400.,full_rotation_s=echo.metadata.get('truth_period_s'),
            baseline_max_scale_relative_delta=np.max(abs(clean-baseline)/np.maximum(np.max(abs(baseline),axis=0),1e-25),axis=0).tolist(),
            independently_checked_clean_float64_max_scale_relative_delta=zero_delta.tolist(),
            independently_checked_legacy_float32_max_abs_delta=legacy_delta.tolist(),
            baseline_precision='legacy raw complex64 uses float32 input FFT in SciPy; adding complex128 IQ noise promotes FFT; both paths independently verified for every Run',
            independent_frontend_validation=checks,initial_extraction_seconds=progress['seconds'],
            validation_seconds=time.perf_counter()-started,seconds=progress['seconds']+time.perf_counter()-started,pilot=False,
            features_sha256=digest(folder/'features.npy'),clean_features_sha256=digest(folder/'clean_features.npy'))
        if initial!=hashes():raise AssertionError('验证期间源码变化')
        write(folder/'extraction.json',manifest)
        print(json.dumps(dict(validation_seconds=manifest['validation_seconds'],legacy_max=legacy_delta.tolist(),float64_max=zero_delta.tolist())))
    finally:echo.close()


if __name__=='__main__':main()
