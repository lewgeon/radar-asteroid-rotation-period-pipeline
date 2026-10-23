"""Explicit-budget continuous-period exclusions; never infer truth error from fit residuals."""
import argparse,json,sys,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from fractions import Fraction
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inversion.src.bounded_period import outer_period_set,Interval,trig_enclosure
from inversion.src.inversion import multi_harmonic_lomb_scargle
from inversion.src.result_views import file_identity


def save(path,result):path.write_bytes(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))


def controls(output):
    """Fixed controls: known and bounded generation errors, and exact alias."""
    rng=np.random.default_rng(17)
    schedules={'regular':np.linspace(0,90,24),'irregular':np.r_[0.,np.sort(rng.uniform(0,90,23))]}
    records=[]
    for schedule,times in schedules.items():
        signal=.2+np.cos(2*np.pi*times/7.3)+.3*np.sin(2*np.pi*times/7.3)
        # These are constructed bounded feature-level errors, not physical IQ.
        noise=.001*np.sin(1.21*times);model=.001*np.cos(.47*times)
        y=signal+noise+model
        # Independently enclose the analytic truth to validate the predeclared
        # generation envelope, including floating synthesis, for this control.
        for t,value in zip(times,y):
            sine,cosine=trig_enclosure(Fraction(float(t))/Fraction(7.3))
            expected=Interval.rational(Fraction(.2))+cosine+Interval.rational(Fraction(.3))*sine
            difference=Interval.rational(Fraction(float(value)))-expected
            assert difference.magnitude()<=Interval.rational(Fraction(.002)).low
        estimate=multi_harmonic_lomb_scargle(times,y,5,10,500,refine_period=True).best_period_s
        for error in (.002,.02):
            start=time.perf_counter()
            result=outer_period_set(times,y,5.,10.,[1.,2.,2.],
                {'declared_noise_and_model_envelope':error},resolution_s=.02,max_boxes=5000,estimate_s=estimate)
            result.update(case=schedule,budget=error,measured_utc=datetime.now(timezone.utc).isoformat(),seconds=time.perf_counter()-start,
                truth_used_only_for_scoring_s=7.3,truth_in_outer_cover=any(a<=7.3<=b for a,b in result['outer_intervals_s']),
                budget_provenance='Constructed .001*sin noise + .001*cos model term; predeclared .002 envelope independently checked by interval truth evaluation, including floating synthesis for every generated sample; not a physical receiver bound')
            save(output/f'{schedule}_{error}.json',result)
            records.append({k:result[k] for k in ('case','budget','outer_intervals_s','conditional_error_bound_s','visited_boxes','status','truth_in_outer_cover','seconds')})
            print(records[-1],flush=True)
    save(output/'summary.json',dict(scope='Feature harmonic controls only; not calibrated physical radar',records=records))


def saved(args):
    before=file_identity(args.observables)
    with np.load(args.observables,allow_pickle=False) as data:
        names=data['feature_names'].tolist();times=data['time_elapsed_s'];values=data['value'][:,names.index(args.feature)]
        metadata=json.loads(data['metadata_json'].item())
    cfg=metadata['inversion_config']
    if cfg.get('los_phase_compensation'):raise ValueError('This bounded harmonic model does not include geometry phase compensation')
    if cfg.get('multi_harmonic_enabled',False) or cfg.get('harmonics',1)!=1:raise ValueError('This saved experiment currently declares H1 only')
    budget=json.loads(args.budget.read_text(encoding='utf-8'))
    if not budget.get('provenance'):raise ValueError('Budget provenance must explicitly describe external justification or hypothetical scope')
    finite=np.isfinite(times)&np.isfinite(values);times=times[finite];values=values[finite]
    if len(times)!=len(finite):raise ValueError('Nonfinite saved observations require a separately declared exclusion policy')
    estimate=multi_harmonic_lomb_scargle(times,values,cfg['period_min_s'],cfg['period_max_s'],cfg['period_grid_size'],refine_period=cfg.get('refine_period')).best_period_s
    start=time.perf_counter()
    report=outer_period_set(times,values,cfg['period_min_s'],cfg['period_max_s'],budget['coefficient_caps'],budget['error_components'],
        resolution_s=args.resolution,max_boxes=args.max_boxes,estimate_s=estimate,
        progress=lambda visited,pending:print('boxes',visited,'pending',pending,flush=True))
    if file_identity(args.observables)!=before:raise ValueError('Source changed during experiment')
    report.update(source=before,feature=args.feature,budget_provenance=budget['provenance'],
        measured_utc=datetime.now(timezone.utc).isoformat(),seconds=time.perf_counter()-start,
        warning_scope='Conditional sensitivity to supplied budget and coefficient caps. No physical error envelope is inferred or validated by this run.')
    save(args.output/'result.json',report)
    print({k:report[k] for k in ('status','outer_intervals_s','conditional_error_bound_s','seconds')},flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['controls','saved'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--observables',type=Path)
    p.add_argument('--feature',default='range_centroid_s');p.add_argument('--budget',type=Path)
    p.add_argument('--resolution',type=float,default=1.);p.add_argument('--max-boxes',type=int,default=2000)
    args=p.parse_args()
    if args.mode=='saved' and (args.observables is None or args.budget is None):p.error('saved requires --observables and an explicit --budget')
    args.output.mkdir(parents=True,exist_ok=False)
    controls(args.output) if args.mode=='controls' else saved(args)


if __name__=='__main__':main()
