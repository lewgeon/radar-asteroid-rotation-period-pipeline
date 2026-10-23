"""Regenerate full Chirp IQ for stationary and azimuth-only controls."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import json
import time
from datetime import datetime,timezone
import gc
import numpy as np
import torch
from tqdm import tqdm
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from echo.src.echo import generate_echo
from echo.src.dataset import save_echo
from echo.src.motion import spin_axis_from_config
from scripts.experiment_optional_period_precision import sha256
from scripts.experiment_half_period_diagnosis import look_longitude

C=299792458.

def rotate_about_axis(vector,axis,angles):
    axis=np.asarray(axis,float)
    axis=axis/np.linalg.norm(axis)
    vector=np.asarray(vector,float)
    angles=np.asarray(angles,float)
    return (np.cos(angles)[:,None]*vector+np.sin(angles)[:,None]*np.cross(axis,vector)+
        (1-np.cos(angles))[:,None]*np.dot(axis,vector)*axis)

def control_observation(original,mode,target):
    if mode not in ('stationary','azimuth_only'):
        raise ValueError('Unknown control mode')
    data={k:v.copy() for k,v in original.items()}
    meta=json.loads(str(data['metadata_json'].item()))
    count=len(data['scatter_elapsed_s'])
    if len(np.unique(data['run_id']))!=count or np.any(data['row_start_sample']!=0):
        raise ValueError('Controls require singleton Runs starting at global ADC index zero')
    angles=look_longitude(original['tx_los_icrs'],original['rx_los_icrs'],target)
    axis=spin_axis_from_config(target)
    for name in ('tx_los_icrs','rx_los_icrs'):
        data[name]=np.repeat(original[name][:1],count,axis=0) if mode=='stationary' else rotate_about_axis(original[name][0],axis,angles)
    for name in ('tx_range_m','rx_range_m'):
        data[name][:]=original[name][0]
    # A virtual static-range three-event geometry; only the target rotates.
    data['emit_elapsed_s']=data['scatter_elapsed_s']-data['tx_range_m']/C
    data['elapsed_s']=data['scatter_elapsed_s']+data['rx_range_m']/C
    data['common_path_rate_m_s'][:]=0.
    data['scatter_receive_rate'][:]=1.
    offset=float(original['row_fast_time_offset_s'][0])
    fs=float(meta['fast_sample_rate_hz'])
    nfast=int(meta['fast_sample_count'])
    data['rx_adc_start_elapsed_s']=data['elapsed_s']+offset
    # Half-cell margin includes the final ADC sample despite epoch subtraction roundoff.
    data['rx_adc_stop_elapsed_s']=data['rx_adc_start_elapsed_s']+(nfast-.5)/fs
    data['row_fast_time_offset_s']=data['rx_adc_start_elapsed_s']-data['elapsed_s']
    data['centroid_fractional_offset_s'][:]=0.
    for key in ('signal_echo_overlap','window_overlap'):
        data[key][:]=False
    data['row_valid'][:]=True
    data['valid_plan'][:]=True
    keep=('artifact_contract_version','time_axis_role','data_layout','pulse_fiducial','prf_hz','pulse_width_s',
          'fast_sample_rate_hz','fast_sample_count','target_extent_path_m','receiver_sampling','valid_plan_field','overlap_fields')
    newmeta={k:meta[k] for k in keep if k in meta}
    newmeta.update(ephemeris_source='synthetic layered control, not a Horizons observation plan',
        experimental_control=mode,independent_time_axis='inherited scatter epochs',mode='monostatic_switching',
        frame='inherited ICRS directions',duration_s=float(np.ptp(data['elapsed_s'])))
    data['metadata_json']=np.array(json.dumps(newmeta))
    data['ephemeris_source']=np.array(newmeta['ephemeris_source'])
    data['duration_s']=np.array(np.ptp(data['elapsed_s']))
    return data

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    job=ROOT/'runs/paras_for_70m_3h'
    cfg=json.loads((job/'configs/echo.generated.json').read_text(encoding='utf-8'))
    cfg.pop('output_path',None)
    cfg['compute']['device']='cuda:0' if torch.cuda.is_available() else 'cpu'
    source_paths=[Path(__file__)]+list((ROOT/'echo/src').glob('*.py'))+[
        ROOT/'scripts/experiment_half_period_diagnosis.py',ROOT/'scripts/experiment_optional_period_precision.py']
    source_hashes={str(p.relative_to(ROOT)):sha256(p) for p in source_paths}
    inputs=[job/'observation_info.npz',job/'configs/echo.generated.json',Path(cfg['model_path'])]
    input_hashes={str(p.relative_to(ROOT)):sha256(p) for p in inputs}
    with np.load(inputs[0]) as d:
        original={k:d[k].copy() for k in d.files}
    records=[]
    start=time.perf_counter()
    for mode in ('stationary','azimuth_only'):
        folder=args.output/mode
        folder.mkdir()
        controlled=control_observation(original,mode,cfg['target'])
        obs=folder/'observation_info.npz'
        np.savez_compressed(obs,**controlled)
        config=json.loads(json.dumps(cfg))
        config['observation_info_path']=str(obs.resolve())
        (folder/'echo_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        bar=tqdm(total=100,desc=mode,unit='%')
        last=[0]
        def progress(stage,percent,message):
            if percent>last[0]:
                bar.update(percent-last[0]);last[0]=percent
        begun=time.perf_counter()
        echo=generate_echo(config,progress_callback=progress)
        bar.update(100-last[0]);bar.close()
        if not np.all(echo.valid) or not np.array_equal(echo.scatter_elapsed_s,original['scatter_elapsed_s']):
            raise ValueError('Control changed scatter epochs or dropped ADC samples')
        save_echo(folder/'echo.npz',echo)
        longitude=look_longitude(echo.tx_los_icrs,echo.rx_los_icrs,cfg['target'])
        records.append({'mode':mode,'seconds':time.perf_counter()-begun,'echo_sha256':sha256(folder/'echo.npz'),
            'observation_sha256':sha256(obs),'longitude_span_deg':float(np.rad2deg(np.ptp(longitude))),
            'valid_samples':int(echo.valid.sum()),'compute_dtype':echo.metadata['compute_dtype'],
            'changed_arrays':[k for k in original if not np.array_equal(original[k],controlled[k])]})
        if any(sha256(ROOT/k)!=v for k,v in {**source_hashes,**input_hashes}.items()):
            raise ValueError('Inputs or source changed during generation')
        result={'created_utc':datetime.now(timezone.utc).isoformat(),'source_hashes':source_hashes,
            'input_hashes':input_hashes,'device':cfg['compute']['device'],'seconds':time.perf_counter()-start,'records':records}
        (args.output/'generation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        del echo,controlled
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    print(json.dumps({'output':str(args.output),'seconds':time.perf_counter()-start}))

if __name__=='__main__':
    main()
