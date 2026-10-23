"""Reproducible uncertainty controls and saved-feature assessment; no truth selection."""
import argparse,json,sys,time
from contextlib import ExitStack
from unittest.mock import patch
import hashlib
import copy
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inversion.src.inversion import estimate_rotation,multi_harmonic_lomb_scargle,add_harmonics,PeriodSearchUnavailable
from inversion.src.period_uncertainty import assess_period_uncertainty,write_uncertainty_report,candidate_summary
from inversion.src.period_consensus import _cross_feature_consensus
from inversion.src.result_views import file_identity


def wilson(success,n):
    p=success/n;z=1.95996398454;d=1+z*z/n
    c=(p+z*z/(2*n))/d;r=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [c-r,c+r]


def config():
    return dict(period_min_s=18.,period_max_s=22.,period_grid_size=120,harmonics=1,refine_period=True,
        period_selection='legacy_consensus',
        uncertainty_method='run_bootstrap',uncertainty_replicates=30,uncertainty_seed=20261015,
        cpi_duration_s=.8,cpi_hop_duration_s=.4,motion_compensation='centroid_geometry')


def receiver_echo(seed):
    """Analytic two-scatterer receiver control, not an asteroid shape simulation."""
    rng=np.random.default_rng(seed);runs=np.repeat(np.arange(30),16)
    t=np.repeat(np.arange(30)*6.,16)+np.tile(np.arange(16)/10,30)
    fast=np.arange(80)/1000;phase=2*np.pi*t/20
    iq=np.zeros((len(t),len(fast)),complex)
    for delay,amplitude in ((.015+.003*np.sin(phase),1+.35*np.cos(phase)),(.045+.004*np.cos(phase),.6+.2*np.sin(phase))):
        u=fast[None,:]-delay[:,None]
        iq+=amplitude[:,None]*np.where((u>=0)&(u<.02),np.exp(1j*np.pi*400/.02*(u-.01)**2),0)
    # A Run-level gain error correlates all pulses/CPI in that Run.
    iq*=np.repeat(1+rng.normal(0,.03,30),16)[:,None]
    iq+=.025*(rng.normal(size=iq.shape)+1j*rng.normal(size=iq.shape))
    return SimpleNamespace(elapsed_s=t+1,scatter_elapsed_s=t,iq=iq,valid=np.ones(iq.shape,bool),
        run_id=runs,coherence_id=runs,fast_time_s=fast,row_fast_time_offset_s=np.zeros(len(t)),
        centroid_fractional_offset_s=np.zeros(len(t)),tx_range_m=np.full(len(t),149896229.),rx_range_m=np.full(len(t),149896229.),
        metadata=dict(data_layout='pulse_adc_windows',echo_output_reference='centroid_compensated',carrier_frequency_hz=1e9,
        pulse_width_s=.02,pulse_bandwidth_hz=400.,fast_sample_rate_hz=1000.,prf_hz=10.,baseband_convention='centered'))


def coverage(args):
    cfg=config();records=[];start=time.perf_counter()
    for trial in range(args.trials):
        rng=np.random.default_rng(7100+trial)
        runs=np.repeat(np.arange(40),3);t=np.repeat(np.sort(rng.uniform(0,180,40)),3)+np.tile([0,.1,.2],40)
        for case in ('correct_waveform','unmodeled_harmonic'):
            y=np.cos(2*np.pi*t/20)+np.repeat(rng.normal(0,.15,40),3)+rng.normal(0,.04,len(t))
            if case=='unmodeled_harmonic':y+=.5*np.cos(4*np.pi*t/20+.8)
            estimate=add_harmonics(multi_harmonic_lomb_scargle(t,y,18,22,120,refine_period=True),18,22)
            report=assess_period_uncertainty(t,{'range_centroid':y},runs,{'range_centroid':estimate},cfg)
            records.append(record(case,trial,estimate.best_period_s,report))
        if trial<args.receiver_trials:
            result=estimate_rotation(receiver_echo(17100+trial),cfg)
            center=_cross_feature_consensus({k:candidate_summary(v) for k,v in result.periods.items()})[0]
            records.append(record('receiver_to_full_consensus',trial,center,result.uncertainty_report))
        if trial%10==0:print('coverage trial',trial+1,'/',args.trials,flush=True)
    summary={}
    for case in sorted({r['case'] for r in records}):
        rows=[r for r in records if r['case']==case];errors=np.array([r['period_s']-20 for r in rows])
        usable=[r for r in rows if r['bootstrap95_contains_truth'] is not None]
        n=len(usable);success=sum(r['bootstrap95_contains_truth'] for r in usable)
        local=[r for r in rows if r['range_centroid_local3sigma_contains_truth'] is not None]
        feature=[r for r in rows if r['range_centroid_bootstrap95_contains_truth'] is not None]
        summary[case]=dict(trials=len(rows),bias_s=float(errors.mean()),rmse_s=float(np.sqrt(np.mean(errors**2))),
            bootstrap95_available=n,bootstrap95_coverage=success/n if n else None,bootstrap95_coverage_wilson95=wilson(success,n) if n else None,
            range_centroid_local3sigma_available=len(local),range_centroid_local3sigma_coverage=sum(r['range_centroid_local3sigma_contains_truth'] for r in local)/len(local) if local else None,
            range_centroid_bootstrap95_available=len(feature),range_centroid_bootstrap95_coverage=sum(r['range_centroid_bootstrap95_contains_truth'] for r in feature)/len(feature) if feature else None)
    return dict(measured_utc=datetime.now(timezone.utc).isoformat(),seconds=time.perf_counter()-start,config=cfg,
        protocol='predeclared 20s truth for scoring only; 18..22 search; 40 Runs x3 correlated observations; H1 correct/misspecified; receiver control30Runs x16pulses x80samples uses full frontend, five features, search and consensus; fixed seeds',
        limitation='controls only; not real asteroid geometry/noise coverage; too few trials to calibrate99.73%; no final3sigma guarantee',summary=summary,records=records)


def record(case,trial,period,report):
    interval=report.get('conditional_same_mode_95_interval_s')
    local=report.get('local_features',{}).get('range_centroid',{}).get('conditional_3sigma_interval_s')
    values=[v for v in report.get('bootstrap_feature_samples_s',{}).get('range_centroid',[]) if v is not None]
    feature_interval=np.quantile(values,[.025,.975]).tolist() if values else None
    return dict(case=case,trial=trial,period_s=report.get('baseline_consensus_period_s',float(period)),
        range_centroid_period_s=report.get('local_features',{}).get('range_centroid',{}).get('period_s'),
        bootstrap95_contains_truth=None if interval is None else interval[0]<=20<=interval[1],
        range_centroid_bootstrap95_contains_truth=None if feature_interval is None else feature_interval[0]<=20<=feature_interval[1],
        range_centroid_bootstrap95_interval_s=feature_interval,
        range_centroid_local3sigma_contains_truth=None if local is None else local[0]<=20<=local[1],bootstrap95_interval_s=interval,
        range_centroid_local3sigma_interval_s=local,failure_fraction=report.get('bootstrap_failure_fraction'))


def saved(args):
    before=file_identity(args.observables)
    code_files = [Path(__file__), ROOT/'inversion/src/period_uncertainty.py',
        ROOT/'inversion/src/joint_period.py', ROOT/'inversion/src/inversion.py']
    code_before = {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files}
    with np.load(args.observables,allow_pickle=False) as data:
        t=data['time_elapsed_s'];values=data['value'];runs=data['run_id'];names=data['feature_names'].tolist()
        weights=data['effective_sample_count'];metadata=json.loads(data['metadata_json'].item())
    cfg={**metadata['inversion_config'],'uncertainty_method':'run_bootstrap','uncertainty_replicates':args.replicates,'uncertainty_seed':20261015}
    if getattr(args,'period_selection',None) is not None:cfg['period_selection']=args.period_selection
    if getattr(args,'compute_device',None) is not None:cfg['compute_device']=args.compute_device
    if metadata.get('search_diagnostics',{}).get('processing_path')!='cpi':raise ValueError('Saved-only experiment requires CPI weights; legacy fallback snapshots do not preserve row weights')
    if cfg.get('los_phase_compensation',False):raise ValueError('This saved-only experiment requires disabled LOS compensation')
    mapping=dict(total_power='total_power',doppler_centroid_hz='doppler_centroid',rms_bandwidth_hz='doppler_bandwidth',range_centroid_s='range_centroid',centroid_delay_s='range_centroid',energy_width_90_s='range_energy_width',energy_range_width_90_s='range_energy_width')
    features={mapping[n]:values[:,i] for i,n in enumerate(names) if n in mapping};periods={}
    feature_set=getattr(args,'feature_set','all')
    if feature_set=='range':features={name:y for name,y in features.items() if name in ('total_power','range_centroid','range_energy_width')}
    from inversion.src.period_enhancements import method_options
    for name,y in features.items():
        try:periods[name]=add_harmonics(multi_harmonic_lomb_scargle(t,y,cfg['period_min_s'],cfg['period_max_s'],cfg['period_grid_size'],harmonics=method_options(cfg)['harmonics'],weights=weights,refine_period=cfg.get('refine_period'),compute_device=cfg.get('compute_device')),cfg['period_min_s'],cfg['period_max_s'])
        except PeriodSearchUnavailable:continue
    if not periods:raise ValueError('No estimable saved feature')
    start=time.perf_counter()
    trace = {'feature_searches': [], 'joint_selections': []}
    trace_state = {'calls': 0, 'replicate': 0}
    def progress(repeat, total):
        if getattr(args,'trace_candidates',False) and not any(
                row['replicate'] == repeat for row in trace['joint_selections']):
            predictive = cfg.get('period_selection','predictive_joint') == 'predictive_joint'
            trace['joint_selections'].append(dict(replicate=repeat,
                status='unavailable' if predictive else 'not_applicable',
                reason='no_estimable_individual_features' if predictive else 'legacy_candidate_voting'))
        if repeat % 10 == 0:print('resample',repeat,'/',total,flush=True)
    with ExitStack() as stack:
        if getattr(args,'trace_candidates',False):
            from inversion.src import period_uncertainty, joint_period
            original_search = period_uncertainty.multi_harmonic_lomb_scargle
            original_select = joint_period.select_predictive_period
            order = list(periods)
            trace['feature_searches'] = [dict(replicate=0,feature=name,status='searched',
                result=candidate_summary(estimate)) for name,estimate in periods.items()]
            def traced_search(*positional, **keywords):
                call = trace_state['calls']
                trace_state['calls'] += 1
                repeat = call // len(order) + 1
                trace_state['replicate'] = repeat
                entry = dict(replicate=repeat,feature=order[call % len(order)])
                try:
                    item = original_search(*positional, **keywords)
                except PeriodSearchUnavailable as error:
                    trace['feature_searches'].append(dict(**entry,status='unavailable',reason=str(error)))
                    raise
                # The caller adds deterministic half/double aliases afterwards.
                summary = candidate_summary(add_harmonics(copy.copy(item),cfg['period_min_s'],cfg['period_max_s']))
                trace['feature_searches'].append(dict(**entry,status='searched',result=summary))
                return item
            def traced_select(*positional, **keywords):
                from inversion.src.joint_period import JointPeriodUnavailable
                entry = dict(replicate=trace_state['replicate'])
                try:
                    item = original_select(*positional, **keywords)
                except JointPeriodUnavailable as error:
                    trace['joint_selections'].append(dict(**entry,status='unavailable',reason=str(error)))
                    raise
                trace['joint_selections'].append(dict(**entry,status='selected',result=item))
                return item
            stack.enter_context(patch.object(period_uncertainty,'multi_harmonic_lomb_scargle',traced_search))
            stack.enter_context(patch.object(joint_period,'select_predictive_period',traced_select))
        report=assess_period_uncertainty(t,features,runs,periods,cfg,weights,progress=progress)
    if getattr(args,'trace_candidates',False):
        report['candidate_trace'] = dict(**trace,feature_order=list(periods),
            ordering='replicate=0 is baseline; 1..N map to bootstrap samples; every attempted feature search and joint failure is labelled',
            scope='all candidates returned by production APIs, including their existing candidate-count caps; not all grid points')
    if before!=file_identity(args.observables):raise ValueError('Saved observations changed')
    report.update(source=before,measured_utc=datetime.now(timezone.utc).isoformat(),seconds=time.perf_counter()-start,config=cfg,
        experiment_feature_set=feature_set,feature_candidates={name:candidate_summary(estimate) for name,estimate in periods.items()},
        source_hashes_at_start=code_before,
        source_hashes_at_end={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in code_files},
        observables_sha256=hashlib.sha256(args.observables.read_bytes()).hexdigest())
    write_uncertainty_report(args.output,report)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['coverage','saved'],required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--observables',type=Path);p.add_argument('--replicates',type=int,default=100)
    p.add_argument('--trials',type=int,default=200);p.add_argument('--receiver-trials',type=int,default=32)
    p.add_argument('--feature-set',choices=['all','range'],default='all',help='saved模式：全部特征，或仅总能量／距离质心／能量宽度')
    p.add_argument('--compute-device',choices=['cpu','cuda:0'],help='saved模式周期搜索及重采样设备；省略时沿用快照配置')
    p.add_argument('--trace-candidates',action='store_true',help='saved模式保留基线及重采样各次生产API返回的全部候选与联合诊断')
    p.add_argument('--period-selection',choices=['predictive_joint','legacy_consensus'],help='saved模式显式固定融合规则；复现旧快照投票实验时指定legacy_consensus')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    result=coverage(args) if args.mode=='coverage' else saved(args)
    (args.output/'result.json').write_bytes(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
    print(json.dumps(result.get('summary',{}),indent=2),flush=True)


if __name__=='__main__':main()
