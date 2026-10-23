"""Receiver IQ Monte Carlo for a fixed compensated, disjoint-row Chirp job."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import os
from contextlib import nullcontext

for thread_setting in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
    os.environ[thread_setting]='1'

import numpy as np
from tqdm import tqdm
def threadpool_limits(**_):return nullcontext()

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.dataset import load_echo
from scripts.monte_carlo_receiver import LinearReceiver,reference_run_features,FEATURE_NAMES
from scripts.monte_carlo_period import FixedPredictiveSearch
from scripts.receiver_noise import receiver_noise
from inversion.src.period_enhancements import effective_look_phase


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')


def file_sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def snr_values(lower,upper,step):
    count=int(np.floor((upper-lower)/step+1e-12))+1
    return np.minimum(lower+step*np.arange(count),upper)


def validate_snapshot_names(names):
    expected=['total_power','doppler_centroid_hz','rms_bandwidth_hz',
              'range_centroid_s','energy_range_width_90_s']
    if names!=expected:raise ValueError('snapshot feature column order differs from receiver contract')


def bound_truth(explicit,manifest):
    truth=float(manifest['truth_repetition_s'])
    if not np.isfinite(truth) or truth<=0:raise ValueError('invalid extraction truth')
    if explicit is not None and explicit!=truth:raise ValueError('search truth differs from extraction truth')
    return truth


def selected_with_fallback(scorer,values,return_grid=False):
    try:return dict(scorer.select(values,return_grid=return_grid),search_route='fixed_design_accelerator')
    except ValueError as error:
        reference=scorer.production(values)
        return dict(period_s=reference['period_s'],score=reference['score'],candidates=reference['candidates'],
            production_status=reference['status'],production_warnings=reference.get('warnings',[]),
            excluded_channels=reference.get('diagnostics',{}).get('excluded_channels',{}),
            search_route='production_fallback',accelerator_rejection=str(error))


def validate_protocol(config):
    from inversion.src.period_enhancements import method_options
    options=method_options(config)
    if (config.get('period_time_role','scatter_centroid')!='scatter_centroid'
            or config.get('period_selection','predictive_joint')!='predictive_joint'
            or not options['refine_period'] or options['harmonics']!=1
            or config.get('doppler_estimator','spectral_moments')!='spectral_moments'):
        raise ValueError('本协议仅支持scatter_centroid、predictive_joint、H1、细化及FFT谱矩')
    if options['los_phase_compensation']:
        for key,lower,upper in [('spin_axis_ra_deg',0,360),('spin_axis_dec_deg',-90,90)]:
            value=config.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or not lower<=value<=upper:
                raise ValueError('本协议仅支持具有有限且范围有效已知自转轴的LOS补偿')
        if config.get('phase_period_convention','half_rotation') not in ('half_rotation','full_rotation'):
            raise ValueError('LOS相位周期约定无效')


def hashes():
    names=['scripts/experiment_receiver_snr.py','scripts/monte_carlo_receiver.py',
           'scripts/monte_carlo_period.py','inversion/src/joint_period.py',
           'inversion/src/radar_signal.py','inversion/src/inversion.py',
           'scripts/receiver_noise.py','inversion/src/period_enhancements.py']
    return {n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}


def extract(args):
    import torch
    args.output.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    snapshot=args.snapshot
    with np.load(snapshot,allow_pickle=False) as data:
        metadata=json.loads(data['metadata_json'].item())
        config=metadata['inversion_config']
        times=data['time_elapsed_s'];runs=data['run_id'];weights=data['effective_sample_count']
        baseline=data['value'];names=data['feature_names'].tolist()
    validate_snapshot_names(names)
    config=dict(config,compute_device=args.device,uncertainty_method='none')
    validate_protocol(config)
    echo=load_echo(args.echo,mapped_directory=args.output/'mapped',load_clean=False)
    try:
        if echo.metadata.get('snr_db') is not None:raise ValueError('输入必须为无噪声IQ')
        receiver=LinearReceiver(echo,config,args.device)
        phase_offset=effective_look_phase(echo,times,config) if config.get('los_phase_compensation',False) else None
        groups=np.unique(echo.run_id)
        if args.run_limit:groups=groups[:args.run_limit]
        records=[];power_sum=0.;sample_count=0
        for run in groups:
            rows=np.flatnonzero(echo.run_id==run)
            receiver.check_rows(rows)
            if not np.array_equal(rows,np.arange(rows[0],rows[-1]+1)):raise ValueError('Run必须连续')
            raw=np.asarray(echo.iq[rows],dtype=np.complex128)
            power_sum+=float(np.vdot(raw,raw).real);sample_count+=raw.size
            records.append((int(run),rows))
        # Use the complete campaign power even for a timing pilot.
        power=(power_sum/sample_count if not args.run_limit else float(echo.metadata['valid_signal_power']))
        snr=(np.asarray(args.snr_points,float) if args.snr_points is not None else
            snr_values(args.snr_min,args.snr_max,args.snr_step))
        amplitudes=np.r_[0.,10**(-snr/20)]
        nframes=sum(max(0,(len(rows)-receiver.count)//receiver.hop+1) for _,rows in records)
        feature=np.lib.format.open_memmap(args.output/'features.npy',mode='w+',dtype='float64',
            shape=(args.trials,len(snr),nframes,5))
        clean=np.empty((nframes,5));validation=[];noise_energy=np.zeros(args.trials)
        identity=dict(path=str(args.echo.resolve()),size_bytes=args.echo.stat().st_size,mtime_ns=args.echo.stat().st_mtime_ns)
        input_hash=file_sha256(args.echo)
        source_hashes=hashes()
        offset=0
        with torch.inference_mode(),threadpool_limits(limits=1):
            progress=tqdm(records,desc='Receiver Runs',file=sys.stdout)
            for position,(run,rows) in enumerate(progress):
                clean_raw=np.asarray(echo.iq[rows],dtype=np.complex128)
                linear_clean=receiver.transform(clean_raw,rows)
                frame_count=(len(rows)-receiver.count)//receiver.hop+1
                for trial in range(args.trials):
                    noise=receiver_noise(clean_raw.shape,power,args.seed,trial,run,
                        engine=args.noise_engine,device=receiver.device)
                    noise_energy[trial]+=float(np.vdot(noise,noise).real) if isinstance(noise,np.ndarray) else float(torch.vdot(noise.flatten(),noise.flatten()).real.item())
                    linear_noise=receiver.transform(noise,rows)
                    values=receiver.features(receiver.coefficients(linear_clean,linear_noise,rows),amplitudes)
                    feature[trial,:,offset:offset+frame_count]=values[1:]
                    if trial==0:
                        clean[offset:offset+frame_count]=values[0]
                        reference=reference_run_features(echo,dict(config,compute_device='cpu'),rows,clean_raw,
                            receiver.crop_axis,receiver.full_axis)
                        np.testing.assert_allclose(values[0],reference,rtol=2e-9,atol=1e-14)
                        if not args.run_limit:
                            legacy=reference_run_features(echo,metadata['inversion_config'],rows,np.array(echo.iq[rows]),
                                receiver.crop_axis,receiver.full_axis)
                            np.testing.assert_allclose(legacy,baseline[offset:offset+frame_count],rtol=2e-9,atol=1e-14)
                    if trial==0 and position in (0,len(records)//2,len(records)-1):
                        noise_cpu=noise if isinstance(noise,np.ndarray) else noise.detach().cpu().numpy()
                        for snr_index in sorted({0,len(snr)-1}):
                            reference=reference_run_features(echo,dict(config,compute_device='cpu'),rows,clean_raw+amplitudes[snr_index+1]*noise_cpu,
                                receiver.crop_axis,receiver.full_axis)
                            delta=abs(reference-values[snr_index+1])
                            scaled=np.max(delta/np.maximum(np.max(abs(reference),axis=0),1e-25),axis=0)
                            validation.append(dict(run=run,snr_db=float(snr[snr_index]),max_scale_relative_delta=scaled.tolist()))
                            if np.any(scaled>2e-9):raise AssertionError(f'独立生产前端不一致: {scaled}')
                offset+=frame_count
                feature.flush()
                write(args.output/'progress.json',dict(runs_completed=position+1,total_runs=len(records),
                    trials=args.trials,seconds=time.perf_counter()-start))
                del linear_clean,linear_noise
        feature.flush()
        np.save(args.output/'clean_features.npy',clean)
        if not args.run_limit:
            if clean.shape!=baseline.shape:raise AssertionError('CPI计数或五特征形状改变')
            relative=np.max(abs(clean-baseline)/np.maximum(np.max(abs(baseline),axis=0),1e-25),axis=0)
            # The legacy complex64 input takes a single-precision first FFT in
            # scipy.fftconvolve. Adding complex128 IQ noise promotes that FFT.
            # Every clean float64 path and the legacy path were independently
            # certified above, so their difference is recorded, not conflated.
        else:relative=None
        phase_fields={} if phase_offset is None else dict(phase_offset=phase_offset)
        np.savez(args.output/'design.npz',times=times,runs=runs,weights=weights,snr_db=snr,**phase_fields)
        manifest=dict(measured_utc=datetime.now(timezone.utc).isoformat(),input=identity,
            input_sha256=input_hash,
            snapshot_sha256=hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            source_hashes_at_start=source_hashes,source_hashes_at_end=hashes(),
            config=config,feature_names=list(FEATURE_NAMES),snr_db=snr.tolist(),trials=args.trials,seed=args.seed,
            power_definition='mean clean power over unique valid saved ADC samples; not the full Run continuous-ADC aperture',
            signal_power=power,noise_real_imag_variance_at_0_db=power/2,
            unit_noise_power_by_trial=(noise_energy/(sample_count*power)).tolist(),
            noise='circular complex iid Gaussian at receive IQ, disjoint global ADC indices asserted per Run; no per-realization power normalization',
            snr_pairing='same unit noise for all SNR points within each trial; independent trial seeds',
            noise_engine=args.noise_engine,noise_numpy_version=np.__version__,noise_torch_version=torch.__version__,
            noise_seed_mapping=('PCG64 SeedSequence[seed,trial,run]' if args.noise_engine=='numpy' else
                'torch local Generator(actual_device), SeedSequence[seed,trial,run].generate_state(1,uint64)[0]; independent float64 real/imag draws'),
            phase_compensation=('production effective_look_phase from recorded LOS and supplied pole; no period truth' if phase_offset is not None else 'none'),
            actual_device=receiver.device,dtype='complex128/float64',
            run_count=len(records),cpi_count=nframes,truth_repetition_s=args.truth,
            full_rotation_s=echo.metadata.get('truth_period_s'),
            baseline_max_scale_relative_delta=None if relative is None else relative.tolist(),
            baseline_precision='legacy raw complex64 FFT versus noisy-IQ complex128 FFT; independently checked per Run',
            independent_frontend_validation=validation,seconds=time.perf_counter()-start,pilot=bool(args.run_limit))
        if source_hashes!=hashes():raise AssertionError('实验运行期间科研源码变化')
        if file_sha256(args.echo)!=input_hash:raise AssertionError('input IQ changed during extraction')
        write(args.output/'extraction.json',manifest)
        print(json.dumps(dict(seconds=manifest['seconds'],runs=len(records),trials=args.trials,device=receiver.device)),flush=True)
    finally:echo.close()


def wilson(success,n):
    p=success/n;z=1.95996398454;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    radius=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [center-radius,center+radius]


def search(args):
    search_source_hashes=hashes()
    folder=args.output
    manifest=json.loads((folder/'extraction.json').read_text(encoding='utf-8'))
    args.truth=bound_truth(args.truth,manifest)
    if (folder/'result.json').exists():raise FileExistsError(folder/'result.json')
    if manifest['pilot']:raise ValueError('不能把计时pilot当完整实验')
    start=time.perf_counter()
    values=np.load(folder/'features.npy',mmap_mode='r')
    baseline=np.load(folder/'clean_features.npy')
    with np.load(folder/'design.npz') as design:
        times=design['times'];runs=design['runs'];weights=design['weights'];snr=design['snr_db']
        phase_offset=design['phase_offset'] if 'phase_offset' in design else None
    cfg=manifest['config']
    validate_protocol(cfg)
    if bool(cfg.get('los_phase_compensation',False))!=(phase_offset is not None):raise ValueError('LOS config/design mismatch')
    records=[];validation=[]
    with threadpool_limits(limits=1):
        scorer=FixedPredictiveSearch(times,runs,weights,cfg['period_min_s'],cfg['period_max_s'],cfg['period_grid_size'],phase_offset=phase_offset)
        clean=selected_with_fallback(scorer,baseline,return_grid=True)
        ref=scorer.production(baseline)
        if abs(clean['period_s']-ref['period_s'])>1e-3:raise AssertionError('无噪声选择不一致')
        for trial in tqdm(range(values.shape[0]),desc='Monte Carlo full-grid search',file=sys.stdout):
            for j,db in enumerate(snr):
                y=np.asarray(values[trial,j])
                try:
                    estimate=selected_with_fallback(scorer,y)
                    row=dict(trial=trial,snr_db=float(db),status='selected',**estimate)
                    if trial==0 and j in (0,len(snr)//2,len(snr)-1):
                        reference=scorer.production(y)
                        if abs(reference['period_s']-estimate['period_s'])>1e-3:raise AssertionError('联合选择与生产不一致')
                        np.testing.assert_allclose([c['period_s'] for c in estimate['candidates']],
                            [c['period_s'] for c in reference['candidates']],rtol=2e-6,atol=.001)
                        delta=None
                        if estimate['search_route']=='fixed_design_accelerator':
                            z=scorer.normalize(y)
                            # Every grid point/channel, independent scalar SVD.
                            exact=np.array([scorer.scalar(p,z) for p in scorer.grid])
                            delta=float(np.max(abs(exact-scorer.score_grid(z))))
                            if delta>1e-10:raise AssertionError('完整评分网格不一致')
                        validation.append(dict(trial=trial,snr_db=float(db),grid_max_abs_delta=delta,
                            period_delta_s=estimate['period_s']-reference['period_s']))
                    row['relative_error']=abs(row['period_s']/args.truth-1)
                except ValueError as error:
                    # Preserve failures rather than silently reducing the denominator.
                    row=dict(trial=trial,snr_db=float(db),status='unavailable',reason=str(error),period_s=None,relative_error=None)
                records.append(row)
            write(folder/'search_progress.json',dict(trials_completed=trial+1,total_trials=len(values),seconds=time.perf_counter()-start))
    summary=[]
    for db in snr:
        selected=[r for r in records if r['snr_db']==db]
        errors=np.array([r['relative_error'] if r['relative_error'] is not None else np.inf for r in selected])
        finite=errors[np.isfinite(errors)]
        stats=dict(snr_db=float(db),trials=len(errors),failures=int(np.sum(~np.isfinite(errors))),
            relative_error_median=float(np.median(finite)) if len(finite) else None,
            relative_error_rmse=float(np.sqrt(np.mean(finite**2))) if len(finite) else None,
            relative_error_q95=float(np.quantile(finite,.95)) if len(finite) else None,
            max_relative_error=float(np.max(finite)) if len(finite) else None,success={})
        for threshold in (.1,.01,.001):
            count=int(np.sum(errors<=threshold))
            stats['success'][str(threshold)]=dict(count=count,fraction=count/len(errors),wilson95=wilson(count,len(errors)))
        summary.append(stats)
    thresholds={}
    for tolerance in (.1,.01,.001):
        eligible=[i for i in range(len(summary)) if all(row['success'][str(tolerance)]['fraction']>=.95 for row in summary[i:])]
        index=eligible[0] if eligible else None
        thresholds[str(tolerance)]=dict(minimum_scanned_snr_db=None if index is None else summary[index]['snr_db'],
            censoring=('noiseless_baseline_fails' if abs(clean['period_s']/args.truth-1)>tolerance else
                'above_scan_maximum' if index is None else 'at_or_below_scan_minimum' if index==0 else 'sampled_snr_scan'),
            clean_baseline_passes=abs(clean['period_s']/args.truth-1)<=tolerance,
            success_criterion='empirical success fraction >=0.95 at this and every higher scanned SNR; not a simultaneous confidence guarantee')
    result=dict(manifest=manifest,search_seconds=time.perf_counter()-start,
        clean_period_s=clean['period_s'],truth_repetition_s=args.truth,
        clean_relative_error=abs(clean['period_s']/args.truth-1),
        scope='fixed shape, geometry, schedule and deterministic clean simulation; receiver AWGN only, not total physical error',
        scoring_validation=validation,summary=summary,thresholds=thresholds,records=records,
        final_source_hashes=hashes())
    if search_source_hashes!=hashes():raise AssertionError('scientific source changed during search')
    result['search_source_hashes_at_start']=search_source_hashes
    write(folder/'result.json',result)
    print(json.dumps(dict(thresholds=thresholds,seconds=result['search_seconds']),ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['extract','search'],required=True)
    p.add_argument('--echo',type=Path,default=ROOT/'runs/seperate_observation_2/echo/echo.npz')
    p.add_argument('--snapshot',type=Path,default=ROOT/'runs/seperate_observation_2/inversion_upgrade_20261016/period_observables.npz')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',choices=['cpu','cuda:0'],default='cuda:0')
    p.add_argument('--noise-engine',choices=['numpy','torch'],default='numpy')
    p.add_argument('--trials',type=int,default=100)
    p.add_argument('--seed',type=int,default=20261016)
    p.add_argument('--snr-min',type=float,default=5.)
    p.add_argument('--snr-max',type=float,default=30.)
    p.add_argument('--snr-step',type=float,default=1.)
    p.add_argument('--snr-points',nargs='+',type=float,help='显式升序SNR点，用于补算扫描边界')
    p.add_argument('--truth',type=float,default=None)
    p.add_argument('--run-limit',type=int,help='仅计时pilot；不能用于完整搜索')
    args=p.parse_args()
    if args.phase=='extract' and args.truth is None:args.truth=5400.
    if args.trials<1 or args.seed<0 or (args.truth is not None and (not np.isfinite(args.truth) or args.truth<=0)):p.error('次数、种子和真值非法')
    if (not np.all(np.isfinite([args.snr_min,args.snr_max,args.snr_step]))
            or args.snr_min>args.snr_max or args.snr_step<=0
            or (args.snr_max-args.snr_min)/args.snr_step>1000):p.error('SNR扫描范围或步长非法')
    if args.snr_points is not None:
        if (len(args.snr_points)>1001 or not np.all(np.isfinite(args.snr_points))
                or np.any(np.diff(args.snr_points)<=0)):p.error('显式SNR点必须有限、升序且不重复')
        if (args.snr_min,args.snr_max,args.snr_step)!=(5.,30.,1.):p.error('显式SNR点不能与范围选项混用')
    endpoints=args.snr_points if args.snr_points is not None else [args.snr_min,args.snr_max]
    if min(endpoints)<-300 or max(endpoints)>300:p.error('本研究驱动限定SNR在-300至300dB内')
    extract(args) if args.phase=='extract' else search(args)


if __name__=='__main__':main()
