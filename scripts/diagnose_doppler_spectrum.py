"""Unaltered/diagnostic-tail/longer-CPI comparisons on the same clean IQ.

No diagnostic cut is installed as a production estimator.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
from scipy import signal
from tqdm import tqdm

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.dataset import load_echo
from inversion.src.inversion import multi_harmonic_lomb_scargle
from scripts.monte_carlo_receiver import LinearReceiver


def main():
    import torch
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--echo',type=Path,default=ROOT/'runs/seperate_observation_2/echo/echo.npz')
    p.add_argument('--snapshot',type=Path,default=ROOT/'runs/seperate_observation_2/inversion_upgrade_20261016/period_observables.npz')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    with np.load(args.snapshot) as d:cfg=json.loads(d['metadata_json'].item())['inversion_config']
    echo=load_echo(args.echo,mapped_directory=args.output/'mapped',load_clean=False)
    start=time.perf_counter();records=[]
    receiver=LinearReceiver(echo,cfg,'cuda:0')
    try:
        with torch.inference_mode():
            for run in tqdm(np.unique(echo.run_id),desc='Doppler diagnosis',file=sys.stdout):
                rows=np.flatnonzero(echo.run_id==run)
                receiver.check_rows(rows)
                crop,full=receiver.transform(np.asarray(echo.iq[rows],complex),rows)
                del full
                for duration in (.5,1.,2.):
                    count=int(np.ceil(duration*echo.metadata['prf_hz']));hop=int(np.ceil(count/4))
                    for window in ('hann','boxcar') if duration==1 else ('hann',):
                        taper=torch.as_tensor(signal.get_window(window,count),device=crop.device,dtype=torch.float64)
                        for begin in range(0,len(rows)-count+1,hop):
                            times=echo.scatter_elapsed_s[rows[begin:begin+count]]
                            prt=float(np.median(np.diff(times)))
                            frequency=np.fft.fftshift(np.fft.fftfreq(count,d=prt))
                            spectrum=torch.fft.fftshift(torch.fft.fft(crop[begin:begin+count]*taper[:,None],dim=0),dim=0)
                            power=spectrum.abs().square().sum(1).cpu().numpy()
                            total=power.sum();mu=power@frequency/total
                            variance=power@(frequency-mu)**2/total
                            tail=abs(frequency)>=5.
                            kept=~tail
                            tm=power[kept]@frequency[kept]/power[kept].sum()
                            tv=power[kept]@(frequency[kept]-tm)**2/power[kept].sum()
                            wp=abs(np.fft.fftshift(np.fft.fft(taper.cpu().numpy())))**2
                            wm=wp@frequency/wp.sum();wv=wp@(frequency-wm)**2/wp.sum()
                            records.append(dict(run=int(run),duration_s=duration,window=window,
                                time_s=float(np.mean(times)),centroid_hz=float(mu),width_hz=float(np.sqrt(variance)),
                                diagnostic_under_5hz_width=float(np.sqrt(tv)),
                                tail_power_fraction=float(power[tail].sum()/total),
                                tail_second_moment_fraction=float((power[tail]@(frequency[tail]-mu)**2)/(total*variance)),
                                window_rms_hz=float(np.sqrt(wv))))
        summaries=[];curves={}
        for duration,window in sorted(set((r['duration_s'],r['window']) for r in records)):
            rows=[r for r in records if r['duration_s']==duration and r['window']==window]
            t=np.array([r['time_s'] for r in rows])
            for key in ('centroid_hz','width_hz','diagnostic_under_5hz_width'):
                y=np.array([r[key] for r in rows])
                fit=multi_harmonic_lomb_scargle(t,y,cfg['period_min_s'],cfg['period_max_s'],cfg['period_grid_size'],refine_period=True)
                # Score the predeclared 5400s reference without selecting by truth.
                x=np.column_stack((np.ones(len(t)),np.cos(2*np.pi*(t-t.min())/5400),np.sin(2*np.pi*(t-t.min())/5400)))
                residual=y-x@np.linalg.lstsq(x,y,rcond=None)[0]
                score=1-float(residual@residual)/float((y-y.mean())@(y-y.mean()))
                label=f'{duration}_{window}_{key}'
                curves[label]=dict(period_s=fit.grid_periods_s.tolist(),score=fit.grid_scores.tolist())
                summaries.append(dict(duration_s=duration,window=window,observable=key,
                    observations=len(rows),best_period_s=fit.best_period_s,best_score=fit.candidates[0].score,
                    reference_5400_fit_score=score,std=float(y.std()),
                    tail_power_minmax=[min(r['tail_power_fraction'] for r in rows),max(r['tail_power_fraction'] for r in rows)],
                    tail_second_moment_minmax=[min(r['tail_second_moment_fraction'] for r in rows),max(r['tail_second_moment_fraction'] for r in rows)],
                    window_rms_minmax=[min(r['window_rms_hz'] for r in rows),max(r['window_rms_hz'] for r in rows)]))
        result=dict(scope='same noiseless saved IQ; diagnostic cuts/window/CPI comparisons, no production changes',
            config=cfg,records=records,summary=summaries,curves=curves,seconds=time.perf_counter()-start,
            reference='https://docs.scipy.org/doc/scipy/tutorial/signal.html#spectral-analysis')
        (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(json.dumps(summaries,ensure_ascii=False,indent=2))
    finally:echo.close()


if __name__=='__main__':main()
