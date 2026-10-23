"""Render standalone PNG/SVG Monte Carlo and Doppler diagnosis figures."""
import argparse,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def setup():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,
        'axes.spines.right':False,'savefig.dpi':220,'svg.fonttype':'none'})


def save(figure,output,name):
    output.mkdir(parents=True,exist_ok=True)
    for ext in ('png','svg'):
        path=output/f'{name}.{ext}'
        if path.exists():raise FileExistsError(path)
        figure.savefig(path,bbox_inches='tight')
    plt.close(figure)


def monte_carlo(data,output):
    rows=data['summary'];x=np.array([r['snr_db'] for r in rows])
    fig,(a,b)=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for key,label,color in [('relative_error_rmse','RMSE (available estimates)','#2563a6'),
            ('relative_error_median','Median absolute error','#16856c'),
            ('relative_error_q95','95th percentile absolute error','#c47a19')]:
        a.semilogy(x,[100*r[key] if r[key] is not None else np.nan for r in rows],'-o',
            label=label,color=color,markersize=3)
    for tolerance in (10,1,.1):a.axhline(tolerance,color='#8c94a0',lw=.8,ls='--')
    a.set(xlabel='Receiver IQ SNR (dB)',ylabel='Period error (%; available estimates)',
        title=f"Error against {data['truth_repetition_s']:g} s target period")
    a.legend(fontsize=9);a.grid(alpha=.2,which='both')
    for index,(tol,label,color) in enumerate(zip((.1,.01,.001),('Error ≤ 10%','Error ≤ 1%','Error ≤ 0.1%'),
            ('#2563a6','#16856c','#c47a19'))):
        y=np.array([r['success'][str(tol)]['fraction'] for r in rows])*100
        low=np.array([r['success'][str(tol)]['wilson95'][0] for r in rows])*100
        high=np.array([r['success'][str(tol)]['wilson95'][1] for r in rows])*100
        b.plot(x,y,'-o',label=label,color=color,markersize=3)
        b.fill_between(x,low,high,color=color,alpha=.10)
    b.axhline(95,color='#606b79',lw=1,ls='--',label='95% empirical success target')
    b.set(xlabel='Receiver IQ SNR (dB)',ylabel='Successful realizations (%)',ylim=(-2,102),
          title=f"{rows[0]['trials']} independent realizations per SNR")
    b.legend(fontsize=9);b.grid(alpha=.2)
    fig.suptitle('Fixed geometry and clean IQ; circular complex receiver AWGN',fontsize=13)
    save(fig,output,'period_error_vs_snr')


def diagnosis(data,output):
    fig,(a,b)=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
    colors=['#b34848','#16856c','#2563a6']
    settings=[('1.0_hann_width_hz','1 s full spectral RMS'),
              ('1.0_hann_diagnostic_under_5hz_width','1 s diagnostic |f| < 5 Hz'),
              ('2.0_hann_width_hz','2 s full spectral RMS')]
    for (key,label),color in zip(settings,colors):
        curve=data['curves'][key]
        a.plot(np.array(curve['period_s'])/3600,curve['score'],label=label,color=color,lw=1.1)
    a.axvline(1.5,color='#606b79',ls='--',lw=1)
    a.set(xlabel='Candidate repetition period (h)',ylabel='H1 residual improvement',
          title='No receiver noise: the RMS peak is still wrong')
    a.legend(fontsize=8);a.grid(alpha=.2)
    rows=[r for r in data['records'] if r['duration_s']==1 and r['window']=='hann']
    x=np.array([r['tail_power_fraction'] for r in rows])*100
    y=np.array([r['tail_second_moment_fraction'] for r in rows])*100
    b.scatter(x,y,c=np.array([r['width_hz'] for r in rows]),cmap='viridis',s=13,alpha=.7)
    b.set(xlabel='Power outside |f| ≥ 5 Hz (%)',ylabel='Share of RMS variance from that tail (%)',
          title='Very weak remote tails carry a large second moment')
    b.grid(alpha=.2)
    fig.suptitle('Diagnostic frequency restriction is not a production correction',fontsize=12)
    save(fig,output,'doppler_bandwidth_diagnosis')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--kind',choices=['snr','diagnosis'],required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();setup()
    data=json.loads(args.input.read_text(encoding='utf-8'))
    (monte_carlo if args.kind=='snr' else diagnosis)(data,args.output)


if __name__=='__main__':main()
