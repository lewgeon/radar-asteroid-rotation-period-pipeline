"""Controlled half-period diagnosis of the frozen, noiseless ellipsoid job.

Diagnostic interventions are not regenerated astronomical observation plans.
Production defaults and source artifacts are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import gc
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy import optimize, signal
import torch
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_period_harmonics import sha256, fit_model
from inversion.src.dataset import load_echo
from inversion.src.inversion import chirp_pulse_range_features, multi_harmonic_lomb_scargle
from echo.src.echo import generate_echo
from echo.src.motion import body_basis, spin_axis_from_config

NAMES = ['total_power', 'centroid_delay_s', 'energy_width_90_s']
ORDERS = (1, 2, 3, 6)


def phase_design(times, period, harmonics, offset):
    phase = 2*np.pi*(times-times[0])/period + offset
    return np.column_stack([np.ones(len(times))] +
        [f(h*phase) for h in range(1,harmonics+1) for f in (np.cos,np.sin)])


def phase_search(times, values, offset, harmonics, config):
    """Experimental shared-intercept search with a supplied geometric phase.

    Same grid and refinement tolerances as production; includes grid endpoints.
    Geometry offset uses the configured pole, never the period truth.
    """
    times, values, offset = (np.asarray(x,dtype=float) for x in (times,values,offset))
    if times.ndim != 1 or values.shape != times.shape or offset.shape != times.shape:
        raise ValueError('phase search arrays must have matching one-dimensional shapes')
    if not np.all(np.isfinite([times,values,offset])) or np.ptp(values)==0:
        raise ValueError('phase search requires finite, varying data')
    order=np.argsort(times)
    times,values,offset=times[order],values[order],offset[order]
    values=(values-values.mean())/values.std()
    baseline=float(values@values)
    def sse(period):
        x=phase_design(times,period,harmonics,offset)
        beta,_,rank,_=np.linalg.lstsq(x,values,rcond=None)
        if rank!=x.shape[1]:
            return np.inf
        error=values-x@beta
        return float(error@error)
    frequencies=np.linspace(1/config['period_max_s'],1/config['period_min_s'],config['period_grid_size'])
    periods=1/frequencies
    scores=np.array([1-sse(p)/baseline for p in periods])
    indexes=signal.find_peaks(scores)[0].tolist()
    indexes += [0,len(periods)-1]
    indexes=sorted(indexes,key=lambda i:scores[i],reverse=True)[:5]
    candidates=[]
    for i in indexes:
        lo,hi=sorted([periods[max(i-1,0)],periods[min(i+1,len(periods)-1)]])
        result=optimize.minimize_scalar(sse,bounds=(lo,hi),method='bounded')
        choices=[(sse(periods[i]),float(periods[i]))]
        if result.success:
            choices.append((float(result.fun),float(result.x)))
        error,p=min(choices)
        candidates.append((error,p))
    error,p=min(candidates)
    x=phase_design(times,p,harmonics,offset)
    beta=np.linalg.lstsq(x,values,rcond=None)[0]
    amplitudes=np.hypot(beta[1::2],beta[2::2])
    dominant=int(np.argmax(amplitudes)+1)
    return {'base_period_s':p,'dominant_harmonic':dominant,
            'component_period_s':p/dominant,'score':1-error/baseline,
            'grid_maximum_is_interior':bool(0<np.nanargmax(scores)<len(scores)-1)}


def look_longitude(tx, rx, target):
    # The half-period feature repeats twice per full spin longitude.
    projected=(np.asarray(tx)+np.asarray(rx))@body_basis(spin_axis_from_config(target))
    if np.any(np.hypot(projected[:,0],projected[:,1]) < 1e-8):
        raise ValueError('look longitude undefined near the configured spin pole')
    longitude=np.unwrap(np.arctan2(projected[:,1],projected[:,0]))
    return longitude-longitude[0]


def controlled_observation(original, *, fixed_los=False, fixed_adc=False):
    """One-factor interventions; event epochs and ranges remain untouched."""
    data={name:value.copy() for name,value in original.items()}
    if fixed_los:
        for name in ('tx_los_icrs','rx_los_icrs'):
            data[name][:]=data[name][0]
    if fixed_adc:
        meta=json.loads(str(data['metadata_json'].item()))
        fs=meta['fast_sample_rate_hz']
        duration=data['rx_adc_stop_elapsed_s']-data['rx_adc_start_elapsed_s']
        first=float(data['row_fast_time_offset_s'][0])
        data['rx_adc_start_elapsed_s']=data['elapsed_s']+first-data['row_start_sample']/fs
        data['rx_adc_stop_elapsed_s']=data['rx_adc_start_elapsed_s']+duration
        data['row_fast_time_offset_s']=(data['rx_adc_start_elapsed_s']+
            data['row_start_sample']/fs-data['elapsed_s'])
        data['centroid_fractional_offset_s'][:]=data['centroid_fractional_offset_s'][0]
    return data


def features(echo, config):
    f,role,_=chirp_pulse_range_features(echo,config)
    if role!='scatter_elapsed_s':
        raise ValueError('diagnosis requires the scatter time axis')
    return np.column_stack([getattr(f,name) for name in NAMES])


def search_all(times, values, config, reference, label):
    results={}
    for i,name in enumerate(NAMES):
        for h in ORDERS:
            e=multi_harmonic_lomb_scargle(times,values[:,i],config['period_min_s'],
                config['period_max_s'],config['period_grid_size'],harmonics=h)
            model=fit_model(times,values[:,i],e.best_period_s,h)
            beta=np.array(model['beta'])
            dominant=int(np.argmax(np.hypot(beta[1::2],beta[2::2]))+1)
            rec={'base_period_s':e.best_period_s,'dominant_harmonic':dominant,
                 'component_period_s':e.best_period_s/dominant,'score':e.candidates[0].score,
                 'grid_maximum_is_interior':bool(0<np.nanargmax(e.grid_scores)<len(e.grid_scores)-1)}
            rec['error_s']=rec['component_period_s']-reference
            results[f'{name}:H{h}']=rec
            print(f'{label} {name} H={h}: P={rec["component_period_s"]:.9f}s error={rec["error_s"]:+.9f}s',flush=True)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,default=ROOT/'runs/paras_for_70m_3h')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('Output exists; choose a new directory')
    start=time.perf_counter()
    files=[args.job/'echo/echo.npz',args.job/'observation_info.npz',
           args.job/'configs/echo.generated.json',args.job/'configs/inversion.generated.json',
           args.job/'inversion_batch1_20261011_final/period_observables.npz']
    hashes={str(p):sha256(p) for p in files}
    if hashes[str(files[0])]!='add62990c10ab7c4d74f5e2e5d50611cd9201d967399b3b2ed26ee195ee6ba3a':
        raise ValueError('This protocol requires the frozen batch-1 echo')
    echo_config=json.loads(files[2].read_text(encoding='utf-8'))
    inv_config=json.loads(files[3].read_text(encoding='utf-8'))
    if inv_config['period_grid_size']!=4000 or echo_config['snr_db'] is not None:
        raise ValueError('Frozen protocol requires 4000 grid and no receiver noise')
    args.output.mkdir(parents=True)
    sources=[Path(__file__),ROOT/'scripts/experiment_period_harmonics.py',ROOT/'inversion/src/inversion.py',ROOT/'inversion/src/radar_signal.py',
             ROOT/'inversion/src/dataset.py',ROOT/'echo/src/echo.py',ROOT/'echo/src/mesh.py',ROOT/'echo/src/motion.py']
    protocol={'created_at':datetime.now().astimezone().isoformat(),'input_sha256':hashes,
        'source_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in sources},
        'scope':'frozen noiseless ellipsoid; synthetic diagnostic geometry interventions',
        'orders':list(ORDERS),'grid':4000,'search_bounds_s':[inv_config['period_min_s'],inv_config['period_max_s']],
        'python':sys.version,'numpy':np.__version__,'torch':torch.__version__,
        'device':'cuda:0' if torch.cuda.is_available() else 'cpu',
        'selection':'blind search; known half-period used for evaluation only',
        'phase_correction':'minus twice the configured-pole look longitude; no period truth used',
        'interventions':['original float64','fixed LOS float32','fixed LOS and ADC offset float32']}
    (args.output/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    reference=float(echo_config['target']['rotation_period_s'])/2
    echo=load_echo(files[0])
    times=echo.scatter_elapsed_s.copy()
    if len(times)!=2000 or len(np.unique(echo.run_id))!=2000 or not np.all(echo.valid):
        raise ValueError('Protocol requires 2000 valid singleton runs')
    values=features(echo,inv_config)
    with np.load(files[4]) as frozen:
        if frozen['feature_names'].tolist()!=NAMES or not np.array_equal(frozen['time_elapsed_s'],times):
            raise ValueError('Frozen feature axes changed')
        extraction_delta=np.max(np.abs(values-frozen['value']),axis=0).tolist()
        np.testing.assert_allclose(values,frozen['value'],rtol=1e-12,atol=0)
    longitude=look_longitude(echo.tx_los_icrs,echo.rx_los_icrs,echo_config['target'])
    slope=float(np.polyfit(times-times[0],longitude,1)[0])
    result={'reference_half_period_s':reference,'iq_equals_clean':bool(np.array_equal(echo.iq,echo.clean_iq)),
        'iq_clean_max_abs_difference':float(np.max(np.abs(echo.iq-echo.clean_iq))),
        'feature_reextraction_max_abs_difference':extraction_delta,
        'look_longitude_span_deg':float(np.rad2deg(np.ptp(longitude))),
        'look_longitude_fitted_rate_rad_s':slope,
        'constant_longitude_rate_apparent_half_period_s':1/(1/reference-slope/np.pi),
        'actual':{},'ideal':[],'phase_corrected':{},'controlled':{}}
    def checkpoint():
        result['elapsed_s']=time.perf_counter()-start
        (args.output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    result['actual']=search_all(times,values,inv_config,reference,'original')
    np.savez_compressed(args.output/'original_features.npz',time=times,value=values)
    for period in (3600.,5400.,7200.):
        for h in (1,2,3):
            phase=2*np.pi*(times-times[0])/period
            y=3+np.cos(phase)
            if h>1:
                y=y+.35*np.cos(2*phase+.3)
            if h>2:
                y=y+.15*np.sin(3*phase-.2)
            e=multi_harmonic_lomb_scargle(times,y,1800,14400,4000,harmonics=h)
            model=fit_model(times,y,e.best_period_s,h)
            beta=np.array(model['beta'])
            dominant=int(np.argmax(np.hypot(beta[1::2],beta[2::2]))+1)
            result['ideal'].append({'period_s':period,'harmonics':h,'base_period_s':e.best_period_s,
                'component_period_s':e.best_period_s/dominant,'error_s':e.best_period_s/dominant-period})
    # Mismatched waveform with no noise, on exactly the same time samples.
    phase=2*np.pi*(times-times[0])/reference
    y=3+np.cos(phase)+.35*np.cos(2*phase+.3)+.15*np.sin(3*phase-.2)
    e=multi_harmonic_lomb_scargle(times,y,1800,14400,4000,harmonics=1)
    result['ideal_waveform_mismatch_h1']={'period_s':e.best_period_s,'error_s':e.best_period_s-reference}
    checkpoint()
    for i,name in enumerate(NAMES):
        for h in ORDERS:
            rec=phase_search(times,values[:,i],-2*longitude,h,inv_config)
            rec['error_s']=rec['component_period_s']-reference
            result['phase_corrected'][f'{name}:H{h}']=rec
            print(f'phase corrected {name} H={h}: error={rec["error_s"]:+.9f}s',flush=True)
    checkpoint()
    del echo
    gc.collect()
    with np.load(files[1]) as data:
        original={key:data[key].copy() for key in data.files}
    cases=[('original_float64',False,False,'float64'),
           ('fixed_los_float32',True,False,'float32'),
           ('fixed_los_fixed_adc_float32',True,True,'float32')]
    for label,fixed_los,fixed_adc,dtype in cases:
        controlled=controlled_observation(original,fixed_los=fixed_los,fixed_adc=fixed_adc)
        changed=[key for key in original if np.issubdtype(original[key].dtype,np.number)
                 and not np.array_equal(original[key],controlled[key],equal_nan=True)]
        obs_path=args.output/f'{label}_observation.npz'
        np.savez_compressed(obs_path,**controlled)
        cfg=json.loads(json.dumps(echo_config))
        cfg['observation_info_path']=str(obs_path.resolve())
        cfg['compute']={'device':protocol['device'],'dtype':dtype}
        cfg.pop('output_path',None)
        (args.output/f'{label}_config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'Generating {label}: changed observation arrays={changed}',flush=True)
        generation_start=time.perf_counter()
        bar=tqdm(total=100,desc=label,unit='%')
        last=[0]
        def progress(stage,percent,message):
            if percent>last[0]:
                bar.update(percent-last[0]);last[0]=percent
        generated=generate_echo(cfg,progress_callback=progress)
        bar.update(100-last[0]);bar.close()
        generated_features=features(generated,inv_config)
        np.savez_compressed(args.output/f'{label}_features.npz',time=times,value=generated_features)
        relative_feature_change=np.linalg.norm(generated_features-values,axis=0)/np.linalg.norm(values,axis=0)
        result['controlled'][label]={'changed_observation_arrays':changed,
            'echo_metadata':generated.metadata,'generation_elapsed_s':time.perf_counter()-generation_start,
            'relative_feature_change_from_original':relative_feature_change.tolist(),
            'estimates':search_all(times,generated_features,inv_config,reference,label)}
        checkpoint()
        del generated,generated_features,controlled
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    result['input_hashes_unchanged']=all(sha256(p)==digest for p,digest in hashes.items())
    result['source_hashes_unchanged']=all(sha256(ROOT/p)==digest for p,digest in protocol['source_sha256'].items())
    if not result['input_hashes_unchanged'] or not result['source_hashes_unchanged']:
        raise RuntimeError('Sources or inputs changed during the experiment')
    checkpoint()
    print(f'Completed half-period diagnosis in {result["elapsed_s"]:.2f}s',flush=True)


if __name__=='__main__':
    main()
