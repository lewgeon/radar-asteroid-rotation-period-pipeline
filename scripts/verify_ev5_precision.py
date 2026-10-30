"""Re-run the frozen EV5 A search on cached paired noisy features.

Run under conda pytorch. No IQ simulation or truth-based selection occurs.
The output records every comparison, including failures; it never edits goldens.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

# This command owns its process and requests one CPU BLAS thread before NumPy.
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[_key] = '1'

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.predictive_energy import PredictiveEnergyEnsemble
from inversion.src.period_enhancements import effective_look_phase
from types import SimpleNamespace

CASES = {'70m':('ev5_snr_20261016_70m','receiver_snr_ev5_70m_20261016'),
         '400m':('ev5_snr_longcpi_20261016_400m','receiver_snr_ev5_400m_20261016')}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=list(CASES),required=True)
    parser.add_argument('--device',default='cpu')
    parser.add_argument('--trials',type=int,default=100)
    parser.add_argument('--snrs',type=float,nargs='+',default=[0,10,20,30])
    parser.add_argument('--batch-size',type=int,default=32)
    parser.add_argument('--cpu-threads',type=int,default=1)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if not 1 <= args.trials <= 100:
        parser.error('--trials must be between 1 and 100')
    if args.cpu_threads < 1:
        parser.error('--cpu-threads must be positive')
    import torch
    torch.set_num_threads(args.cpu_threads)
    run,cache = CASES[args.case]
    obs_path = ROOT/'runs'/run/'inversion/period_observables.npz'
    design_path = ROOT/'tmp'/cache/'design.npz'
    values_path = ROOT/'tmp'/cache/'features.npy'
    golden_path = ROOT/'docs/4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_NOISE.csv'
    obs,design = np.load(obs_path),np.load(design_path)
    config = json.loads(str(obs['metadata_json']))['inversion_config']
    source = np.load(values_path,mmap_mode='r')
    snr_indices = [int(np.flatnonzero(design['snr_db']==snr).item()) for snr in args.snrs]
    ys = np.asarray(source[:args.trials,snr_indices]).transpose(1,0,2,3).reshape(-1,len(obs['time_elapsed_s']),5)
    identities = [(snr,trial) for snr in args.snrs for trial in range(args.trials)]
    offset = None
    input_paths = [obs_path,design_path,values_path,golden_path]
    if config['los_phase_compensation']:
        echo_path = ROOT/'runs'/run/'echo/echo.npz'
        echo = np.load(echo_path)
        obj = SimpleNamespace(**{key:echo[key] for key in ('scatter_elapsed_s','tx_los_icrs','rx_los_icrs')})
        offset = effective_look_phase(obj,obs['time_elapsed_s'],dict(
            spin_axis_ra_deg=config['spin_axis_ra_deg'],spin_axis_dec_deg=config['spin_axis_dec_deg'],
            phase_period_convention=config['phase_period_convention']))
        input_paths.append(echo_path)
    with golden_path.open(encoding='utf-8',newline='') as stream:
        goldens = {(float(row['snr_db']),int(row['trial'])):row for row in csv.DictReader(stream)
                   if row['case']==args.case and row['method']=='positive_skill_squared'}
    started = time.perf_counter()
    result = dict(case=args.case,utc=datetime.now(timezone.utc).isoformat(),device=args.device,
                  strategy='predictive_skill_energy',search_protocol='dense8_top3_endpoints',
                  source_sha256={str(path.relative_to(ROOT)):sha(path) for path in
                                 [Path(__file__),ROOT/'inversion/src/predictive_energy.py']},
                  input_sha256={str(path.relative_to(ROOT)):sha(path) for path in input_paths},
                  snrs=args.snrs,trials=args.trials,cpu_threads=args.cpu_threads,rows=[],failures=[],
                  phase_prior_from_inversion_config={key:config.get(key) for key in
                      ('los_phase_compensation','spin_axis_ra_deg','spin_axis_dec_deg','phase_period_convention')})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def save():
        result['wall_seconds'] = time.perf_counter()-started
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def progress(h, rows):
        result['completed_harmonic'] = h
        save()
        print(args.case,'H',h,'elapsed',round(time.perf_counter()-started,2),flush=True)
    try:
        scorer = PredictiveEnergyEnsemble(obs['time_elapsed_s'],ys,obs['run_id'],
            weights=obs['effective_sample_count'],phase_offset=offset,device=args.device,batch_size=args.batch_size)
        winners = scorer.search(min_period=config['period_min_s'],max_period=config['period_max_s'],
                                 period_grid_size=config['period_grid_size'],progress=progress)
        for i,(winner,identity) in enumerate(zip(winners,identities)):
            expected = goldens[identity]
            cpu_score = scorer.scorers[i].evaluate(winner['period_s'],winner['h'])
            row = dict(snr_db=identity[0],trial=identity[1],**winner,
                frozen_period_s=float(expected['period_s']),frozen_h=int(expected['order']),
                frozen_negative_score=float(expected['score']),
                period_difference_s=abs(winner['period_s']-float(expected['period_s'])),
                score_difference=abs(winner['score']+float(expected['score'])),
                cpu_svd_score_difference=abs(cpu_score-winner['score']))
            row['passed'] = bool(row['period_difference_s'] < .01 and row['h']==row['frozen_h']
                                 and row['score_difference'] <= 1e-8 and row['cpu_svd_score_difference'] <= 1e-8)
            result['rows'].append(row)
        result['passed_count'] = sum(row['passed'] for row in result['rows'])
        result['failed_count'] = len(result['rows'])-result['passed_count']
    except Exception as error:
        result['failures'].append(dict(type=type(error).__name__,message=str(error)))
        save()
        raise
    save()
    print(args.case,result['passed_count'],'passed;',result['failed_count'],'failed;',result['wall_seconds'],'seconds',flush=True)
    return int(result['failed_count'] != 0)


if __name__=='__main__':
    raise SystemExit(main())
