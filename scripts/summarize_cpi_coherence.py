"""Summarize paired controls without recomputing echo or changing pipeline output."""
import json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.inversion import multi_harmonic_lomb_scargle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    source=ROOT/'tmp/cpi_coherence_20261014'
    out=source/'figures';out.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
    lag=json.loads((source/'real_lag.json').read_text(encoding='utf-8'))['records']
    for method,label in (('linear','Linear alignment / Hann spectrum'),('fourier','Fourier alignment / Hann spectrum'),('lag','Fourier alignment / low-frequency fit')):
        if method=='lag':
            values=np.array([[r['time'],0,r['centroid'],r['rms'],25] for r in lag])
        else:values=np.load(source/f'features_{method}_1.0_0.25.npz')['values']
        for axis,column in zip(axes,(2,3)):
            result=multi_harmonic_lomb_scargle(values[:,0],values[:,column],1800,14400,4000,harmonics=1,weights=values[:,4],refine_period=True)
            order=np.argsort(result.grid_periods_s)
            axis.plot(result.grid_periods_s[order],result.grid_scores[order],label=label)
            axis.axvline(5400,color='black',ls='--',lw=1)
            axis.set_xlim(1800,7000);axis.set_ylabel('LS score');axis.grid(alpha=.2)
    axes[0].set_title('Doppler centroid / 100 runs, CPI 1 s, hop 0.25 s')
    axes[1].set_title('Doppler width: spectral RMS and low-frequency effective width')
    axes[0].legend(fontsize=8);axes[1].set_xlabel('Candidate period (s)')
    fig.tight_layout();fig.savefig(out/'period_comparison.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),sharex=True,sharey=True)
    for axis,method in zip(axes,('linear','fourier')):
        with np.load(source/f'rd_{method}.npz') as data:
            print(method,data.files)
            power=data['power'];freq=data['frequencies'];delay=data['delays']
        if power.ndim==3:power=power[0]
        if freq.ndim==2:freq=freq[0]
        db=10*np.log10(np.maximum(power/power.max(),1e-12))
        mesh=axis.pcolormesh(delay*1e9,freq,db.T,vmin=-45,vmax=0,cmap='magma',shading='nearest')
        axis.set_xlim(-800,200);axis.set_ylim(-10,10);axis.set_title(method+' / same first CPI')
        axis.set_xlabel('Centroid-relative delay (ns)')
    axes[0].set_ylabel('Doppler (Hz)')
    fig.subplots_adjust(left=.08,right=.84,bottom=.16,top=.88,wspace=.18)
    colorbar_axis=fig.add_axes([.88,.18,.018,.66])
    fig.colorbar(mesh,cax=colorbar_axis,label='Relative power (dB)')
    fig.savefig(out/'real_rd_alignment.png',dpi=180);plt.close(fig)
    import shutil
    shutil.copyfile(source/'stripes_controls.png',out/'stripes_controls.png')
    rows=[]
    for estimator,path in (('spectral',ROOT/'tmp/cpi_noise_30_20261014/noise_pilot.json'),('low_frequency',ROOT/'tmp/cpi_noise_lag_30_20261014/noise_narrowband_lag.json')):
        if estimator=='spectral' and not path.exists():path=path.with_name('noise_spectral_moments.json')
        if not path.exists():continue
        records=json.loads(path.read_text(encoding='utf-8'))
        keys={(r['snr_db'],r['cpi_s'],r['hop_s'],r['feature']) for r in records}
        for snr,cpi,hop,feature in sorted(keys,key=str):
            group=[r for r in records if (r['snr_db'],r['cpi_s'],r['hop_s'],r['feature'])==(snr,cpi,hop,feature)]
            errors=np.array([r['error'] for r in group]);finite=np.isfinite(errors)
            rows.append(dict(estimator=estimator,snr_db=snr,cpi_s=cpi,hop_s=hop,feature=feature,seeds=len(group),valid_fits=int(finite.sum()),
                median_abs_error=float(np.nanmedian(abs(errors))),p95_abs_error=float(np.nanquantile(abs(errors),.95)),
                rmse=float(np.sqrt(np.nanmean(errors**2))),hit_5s=float(np.mean(finite&(abs(errors)<=5))),
                accepted_fraction=float(np.mean([r.get('accepted_fraction',1) for r in group]))))
    (source/'noise_summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    import csv
    evidence=source
    for name,records in (('2026-10-14_CPI_COHERENCE_NOISE',rows),
                         ('2026-10-14_CPI_COHERENCE_REAL_SCAN',json.loads((ROOT/'tmp/cpi_scan_20261014/real_periods.json').read_text(encoding='utf-8')))):
        with (evidence/(name+'.csv')).open('w',encoding='utf-8',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    print('Saved figures and paired tables under tmp; review before archiving')
if __name__=='__main__':main()
