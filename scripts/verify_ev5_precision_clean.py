"""Full production SVD searches on original and frozen cached clean EV5 inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace

for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key] = '1'
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.predictive_energy import ENERGY_CHANNELS,select_predictive_energy_period
from inversion.src.period_enhancements import effective_look_phase


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    evidence_path = ROOT/'docs/4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_MODELS.json'
    frozen = json.loads(evidence_path.read_text(encoding='utf-8'))['results']['features/clean_dense_protocol.json']['data']
    cases = [('70m','ev5_snr_20261016_70m','receiver_snr_ev5_70m_20261016'),
             ('400m','ev5_snr_longcpi_20261016_400m','receiver_snr_ev5_400m_20261016')]
    result = dict(utc=datetime.now(timezone.utc).isoformat(),command='conda run -n pytorch python '+
                  'scripts/verify_ev5_precision_clean.py --output '+str(args.output),
                  environment=dict(conda_env=os.environ.get('CONDA_DEFAULT_ENV'),numpy=np.__version__,
                                   python=sys.version,blas_threads=1),
                  source_sha256={str(path.relative_to(ROOT)):sha(path) for path in
                                 [Path(__file__),ROOT/'inversion/src/predictive_energy.py']},
                  golden_sha256=sha(evidence_path),rows=[])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    for case,run,cache in cases:
        obs_path = ROOT/'runs'/run/'inversion/period_observables.npz'
        cached_path = ROOT/'tmp'/cache/'clean_features.npy'
        a = np.load(obs_path)
        cfg = json.loads(str(a['metadata_json']))['inversion_config']
        off = None
        paths = [obs_path,cached_path]
        if cfg['los_phase_compensation']:
            echo_path = ROOT/'runs'/run/'echo/echo.npz'
            echo = np.load(echo_path)
            off = effective_look_phase(SimpleNamespace(**{k:echo[k] for k in
                ('scatter_elapsed_s','tx_los_icrs','rx_los_icrs')}),a['time_elapsed_s'],
                dict(spin_axis_ra_deg=cfg['spin_axis_ra_deg'],spin_axis_dec_deg=cfg['spin_axis_dec_deg'],
                     phase_period_convention=cfg['phase_period_convention']))
            paths.append(echo_path)
        original_names = ('total_power','doppler_centroid_hz','rms_bandwidth_hz','range_centroid_s','energy_range_width_90_s')
        original = dict(zip(a['feature_names'].tolist(),a['value'].T))
        inputs = [('original_value',np.column_stack([original[name] for name in original_names])),
                  ('frozen_clean_features',np.load(cached_path))]
        expected = next(row for row in frozen['cases'] if row['case']==case)['selected']['positive_skill_squared']
        for identity,values in inputs:
            started = time.perf_counter()
            selected = select_predictive_energy_period(a['time_elapsed_s'],dict(zip(ENERGY_CHANNELS,values.T)),
                a['run_id'],weights=a['effective_sample_count'],phase_offset=off,
                min_period=cfg['period_min_s'],max_period=cfg['period_max_s'],period_grid_size=cfg['period_grid_size'])
            row = dict(case=case,input=identity,period_s=selected['period_s'],score=selected['score'],
                       h=selected['diagnostics']['harmonics'],wall_seconds=time.perf_counter()-started,
                       input_sha256={str(path.relative_to(ROOT)):sha(path) for path in paths},
                       frozen=expected,period_difference_s=abs(selected['period_s']-expected['period_s']),
                       score_difference=abs(selected['score']+expected['score']))
            row['period_h_passed'] = bool(row['h']==expected['h'] and row['period_difference_s']<.01)
            row['identical_input_score_passed'] = (row['score_difference']<=1e-8 if identity=='frozen_clean_features' else None)
            result['rows'].append(row)
            args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(case,identity,row['period_s'],row['score'],row['h'],row['wall_seconds'],flush=True)
    result['passed'] = all(row['period_h_passed'] and row['identical_input_score_passed'] is not False for row in result['rows'])
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return int(not result['passed'])


if __name__=='__main__':
    raise SystemExit(main())
