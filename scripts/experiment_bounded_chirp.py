"""Controlled discrete point target: IQ bounds -> production CPI -> period cover.

This is a calibrated discrete control, not an asteroid or real receiver model.
Exact rational convolution certifies numerical discrepancies for this input only.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from fractions import Fraction as F
from pathlib import Path

import numpy as np
from scipy.signal import get_window

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.bounded_period import Interval, _HIGH, _outward_float, outer_period_set, trig_enclosure
from inversion.src.bounded_features import range_centroid_budget
from inversion.src.radar_signal import matched_filter_chirp, range_doppler_cube, range_doppler_features
from inversion.src.inversion import multi_harmonic_lomb_scargle
from inversion.src import compute_backend


def upward(value):
    return _outward_float(F(value), True)


def sqrt_upper(value):
    interval = Interval.rational(value)
    return upward(_HIGH.sqrt(interval.high).next_plus(context=_HIGH))


def pair(value):
    return F(float(value.real)), F(float(value.imag))


def exact_compressed(iq, reference):
    """Leading-edge cropped correlation, using exact encoded binary64 inputs."""
    h = [pair(z) for z in reference]
    result = []
    for row in iq:
        x = [pair(z) for z in row]
        output = []
        for n in range(len(row)):
            real, imag = F(0), F(0)
            for j, (hr, hi) in enumerate(h):
                if n + j < len(row):
                    xr, xi = x[n + j]
                    real += xr * hr + xi * hi
                    imag += xi * hr - xr * hi
            output.append((real, imag))
        result.append(output)
    return result


def certify_frame(iq, compressed, delays, taper, reference, input_entry_bound, reported_centroid):
    """A posteriori numerical certification, independent of period-fit residuals."""
    exact = exact_compressed(iq, reference)
    difference_energy, energy, moment = F(0), F(0), F(0)
    weighted = compressed * taper[:, None]
    for m, row in enumerate(exact):
        w = F(float(taper[m]))
        for k, (real, imag) in enumerate(row):
            zr, zi = pair(weighted[m, k])
            difference_energy += (zr - w * real) ** 2 + (zi - w * imag) ** 2
            p = zr ** 2 + zi ** 2
            energy += p
            moment += F(float(delays[k])) * p
    # Young's inequality ||h*x||2 <= ||h||1 ||x||2; cropping is a contraction.
    # Hann is interpreted as its encoded binary64 coefficients.
    gain = Interval(0)
    for z in reference:
        r, i = pair(z)
        gain = gain + Interval.rational(F(sqrt_upper(r*r+i*i)))
    eta_iq = sqrt_upper(F(float(input_entry_bound)) ** 2 * iq.size)
    propagated = upward((gain * Interval.rational(F(eta_iq)) *
                         Interval.rational(F(float(np.max(abs(taper)))))).high)
    numerical = sqrt_upper(difference_energy)
    budget = range_centroid_budget(weighted.ravel(), np.tile(delays, len(iq)),
        {'bounded_input_after_convolution': propagated, 'certified_frontend_roundoff': numerical})
    if budget['centroid_error_bound_s'] is None:
        raise ValueError('Control has insufficient energy for a finite centroid bound')
    # Parseval supplies the exact centroid of the mathematical FFT. Comparison
    # with rational time-domain power includes FFT, power and moment roundoff.
    fft_moment = upward(abs(F(float(reported_centroid)) - moment / energy))
    return dict(input_centroid_bound_s=budget['centroid_error_bound_s'],
        fft_moment_roundoff_bound_s=fft_moment, frontend_l2_roundoff_bound=numerical,
        propagated_input_l2_bound=propagated)


def run_case(entry_bound, coordinate_bound=0., *, count=24, search=True):
    if compute_backend.is_cuda():
        raise ValueError('This fixed control declares the CPU path; CUDA requires a separate audit')
    if not np.isfinite(entry_bound) or entry_bound<0 or not np.isfinite(coordinate_bound) or coordinate_bound<0:
        raise ValueError('Finite nonnegative input and coordinate bounds required')
    if isinstance(count,bool) or not isinstance(count,int) or not 2<=count<=90*1024:
        raise ValueError('Control requires an integer count from 2 through 92160')
    # Dyadic axes remove time-coordinate rounding from this control.
    dt, spacing, pulses, columns, length = 1/1024, 1/128, 8, 64, 16
    truth = 7.3
    rng = np.random.default_rng(71)
    starts = np.r_[0., np.sort(rng.choice(np.arange(1,90*1024), count-1, replace=False))/1024]
    times = starts[:,None] + np.arange(pulses)[None,:]*spacing
    axis = np.arange(columns)*dt
    local = np.arange(length)*dt
    reference = np.exp(1j*np.pi*(256/(length*dt))*(local-length*dt/2)**2)
    delay = 24*dt+4*dt*np.cos(2*np.pi*times/truth)+2*dt*np.sin(2*np.pi*times/truth)
    indices = np.rint(delay/dt).astype(int)
    # Rounding guard is predeclared and checked against analytic interval truth.
    quantization = dt/2 + dt*1e-10
    for t, index in zip(times.ravel(), indices.ravel()):
        sine, cosine = trig_enclosure(F(float(t))/F(truth))
        actual = Interval.rational(F(24*dt))+4*dt*cosine+2*dt*sine
        assert (Interval.rational(F(int(index)*dt))-actual).magnitude() <= F(quantization)
    clean = np.zeros((count*pulses,columns), complex)
    for row,index in zip(clean,indices.ravel()):
        assert index-(length-1)>=0 and index+length-1<columns
        row[index:index+length] = reference
    # Strict complex magnitude bound, with slack for floating addition.
    perturbation = entry_bound*.25*(rng.uniform(-1,1,clean.shape)+1j*rng.uniform(-1,1,clean.shape))
    iq = clean+perturbation
    for observed,ideal in zip(iq.ravel(),clean.ravel()):
        r,i=pair(observed);cr,ci=pair(ideal)
        assert (r-cr)**2+(i-ci)**2 <= F(float(entry_bound))**2
    compressed = matched_filter_chirp(iq,axis,length*dt,256)
    # Common coordinates are already aligned by construction. No unknown
    # ephemeris, carrier motion, interpolation or cross-Run phase is assumed.
    groups = np.repeat(np.arange(count),pulses)
    cube = range_doppler_cube(compressed,times.ravel(),groups,axis,
        cpi_pulses=pulses,cpi_hop_pulses=pulses,run_id=groups)
    features = range_doppler_features(cube)
    taper = get_window('hann',pulses,fftbins=True)
    rows=[]
    for n in range(count):
        block=slice(n*pulses,(n+1)*pulses)
        rows.append(certify_frame(iq[block],compressed[block],axis,taper,reference,
            entry_bound,features.range_centroid_s[n]))
    components={'input_perturbation': [r['input_centroid_bound_s'] for r in rows],
        'fft_and_moment_roundoff': [r['fft_moment_roundoff_bound_s'] for r in rows],
        'discrete_delay_quantization': quantization,
        'declared_coordinate_offset': coordinate_bound}
    # This deliberate coordinate shift is bounded independently of the IQ seam.
    values=features.range_centroid_s+coordinate_bound/2
    components['coordinate_addition_roundoff']=[upward(abs(F(float(v))-F(float(c))-F(float(coordinate_bound/2))))
        for v,c in zip(values,features.range_centroid_s)]
    # The exact Hann-squared weighted smooth delay is H1 with common coefficients.
    # Symmetric full autocorrelation is wholly within the retained delay support.
    for n,value in enumerate(values):
        ideal=Interval(0);weight_sum=F(0)
        for t,w in zip(times[n],taper):
            weight=F(float(w))**2;weight_sum+=weight
            sine,cosine=trig_enclosure(F(float(t))/F(truth))
            ideal=ideal+weight*(Interval.rational(F(24*dt))+4*dt*cosine+2*dt*sine)
        ideal=ideal*Interval.rational(1/weight_sum)
        declared=sum(F(float(np.broadcast_to(v,(count,))[n])) for v in components.values())
        assert (Interval.rational(F(float(value)))-ideal).magnitude()<=declared
    estimate=(multi_harmonic_lomb_scargle(features.times_s,values,5,10,500,refine_period=True).best_period_s
        if search else None)
    report=dict(scope='Discrete known-waveform point target; CPU; exact per-input frontend audit; not a physical asteroid calibration',
        measured_utc=datetime.now(timezone.utc).isoformat(),input_entry_bound=entry_bound,
        coordinate_bound_s=coordinate_bound,truth_for_control_validation_only_s=truth,
        frame_count=count,pulses_per_frame=pulses,feature_times_s=features.times_s.tolist(),
        observed_centroids_s=values.tolist(),frame_certificates=rows,error_components=components,
        point_estimate_s=estimate,physical_model_error_validated=False)
    if search:
        report['period_cover']=outer_period_set(features.times_s,values,5.,10.,[.04,.01,.01],components,
            resolution_s=.04,max_boxes=5000,estimate_s=estimate)
        assert any(a<=truth<=b for a,b in report['period_cover']['outer_intervals_s'])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    for name,noise,coordinate in [('clean',0.,0.),('bounded_iq',1e-4,0.),('coordinate',1e-4,.001)]:
        start=time.perf_counter();report=run_case(noise,coordinate)
        report['seconds']=time.perf_counter()-start
        (args.output/f'{name}.json').write_bytes(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
        print(name,report['period_cover']['outer_intervals_s'],report['period_cover']['conditional_error_bound_s'],report['seconds'],flush=True)


if __name__=='__main__':main()
