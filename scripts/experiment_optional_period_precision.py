"""Paired option assessment on one frozen Chirp dataset; no production edits."""
from __future__ import annotations
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.dataset import load_echo
from inversion.src.inversion import chirp_pulse_range_features, multi_harmonic_lomb_scargle
from inversion.src.period_enhancements import effective_look_phase

FEATURES = ('total_power', 'centroid_delay_s', 'energy_width_90_s')

def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def receiver_noise(echo, snr_db, seed):
    """Independent ADC noise is legal only for disjoint singleton Run rows."""
    if len(np.unique(echo.run_id)) != len(echo.run_id) or not np.all(echo.valid):
        raise ValueError('Noise experiment requires singleton Runs and all-valid samples')
    clean = echo.clean_iq
    if clean is None or not np.isfinite(snr_db) or not np.all(np.isfinite(clean)):
        raise ValueError('Finite clean IQ and SNR are required')
    power = float(np.mean(np.abs(clean.astype(np.complex128))**2))
    if power <= 0:
        raise ValueError('Nonzero clean signal required')
    rng = np.random.default_rng(seed)
    sigma = np.sqrt(power/10**(snr_db/10)/2)
    noise = sigma*(rng.standard_normal(clean.shape)+1j*rng.standard_normal(clean.shape))
    return replace(echo, iq=clean+noise)

def search(times, values, offset, h, refine, grid):
    # Truth is deliberately absent from the search function.
    result = multi_harmonic_lomb_scargle(times, values, 1800., 14400., grid,
        harmonics=h, phase_offset=offset, refine_period=refine)
    return {'period_s': float(result.best_period_s), 'score': float(result.candidates[0].score)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=ROOT/'runs/paras_for_70m_3h/echo/echo.npz')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    echo = load_echo(args.input)
    input_hash = sha256(args.input)
    if input_hash != 'add62990c10ab7c4d74f5e2e5d50611cd9201d967399b3b2ed26ee195ee6ba3a':
        raise ValueError('This protocol is scoped to the frozen 3-hour dataset')
    if not np.array_equal(echo.iq, echo.clean_iq):
        raise ValueError('The baseline must be noiseless')
    cfg = {'spin_axis_ra_deg':105., 'spin_axis_dec_deg':-66., 'phase_period_convention':'half_rotation'}
    feature = chirp_pulse_range_features(echo, {'motion_compensation':'auto'})[0]
    # Use the actual feature time field, not receive clock.
    times = feature.times_s
    offset = effective_look_phase(echo, times, cfg)
    records = []
    def add(f, t, off, h, refine, grid, **labels):
        for name in FEATURES:
            rec = search(t, getattr(f,name), off, h, refine, grid)
            records.append(dict(labels, feature=name, phase=off is not None, harmonics=h,
                refine=refine, grid=grid, **rec, error_s=rec['period_s']-5400.))
    for grid in tqdm((4000,8000,16000), desc='Grid assessment'):
        for phase in (False, True):
            for h in (1,2):
                for refine in (False,True):
                    add(feature,times,offset if phase else None,h,refine,grid,stage='grid')
    for snr in tqdm((40.,20.), desc='Paired IQ noise'):
        for seed in (20261011,20261012,20261013):
            noisy = receiver_noise(echo,snr,seed)
            nf = chirp_pulse_range_features(noisy, {'motion_compensation':'auto'})[0]
            if not np.array_equal(nf.times_s,times):
                raise ValueError('Feature sampling clock changed')
            for phase in (False,True):
                for h in (1,2):
                    add(nf,times,offset if phase else None,h,True,4000,stage='noise',snr_db=snr,seed=seed)
            del noisy, nf
    for key in ('spin_axis_ra_deg','spin_axis_dec_deg'):
        for delta in (-5.,-1.,1.,5.):
            changed = dict(cfg)
            changed[key] += delta
            add(feature,times,effective_look_phase(echo,times,changed),1,True,4000,
                stage='pole',pole_parameter=key,pole_error_deg=delta)
    summary = {'created_utc':datetime.now(timezone.utc).isoformat(), 'input_sha256':input_hash,
        'source_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in [Path(__file__),
            ROOT/'inversion/src/inversion.py',ROOT/'inversion/src/period_enhancements.py']},
        'scope':'one noiseless 3-hour ellipsoid, known pole; no shape or initial phase passed to inversion',
        'truth_half_period_s':5400.,'iq_shape':list(echo.iq.shape),'times_span_s':float(np.ptp(times)),
        'seconds':time.perf_counter()-start,'records':records}
    (args.output/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({'records':len(records),'seconds':summary['seconds'],'output':str(args.output)}))

if __name__ == '__main__':
    main()
