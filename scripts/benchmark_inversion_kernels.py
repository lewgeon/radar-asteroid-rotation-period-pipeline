"""Research-only paired CPU/CUDA kernel probe; never updates pipeline results."""
import sys,json,time,cProfile,pstats,argparse,platform,scipy
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from scipy import fft
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rotation_gui.window.result_service import load_run
from inversion.src.inversion import _compute_chirp_observations
from inversion.src.radar_signal import matched_filter_chirp,chirp_reference_sample_count,align_profiles_to_common_delay
parser=argparse.ArgumentParser()
parser.add_argument('--echo',type=Path,default=ROOT/'runs/seperate_observation_2/echo/echo.npz')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();source=args.echo.resolve()
if not torch.cuda.is_available():raise SystemExit('This research benchmark requires CUDA; production CPU execution remains available.')
echo,indices=load_run(source,0)
if (len(echo.iq)!=200 or echo.iq.shape[1]!=10403 or not np.all(echo.valid)
    or float(echo.metadata.get('prf_hz',0))!=100
    or echo.metadata.get('echo_output_reference')!='centroid_compensated'
    or echo.metadata.get('baseband_convention','centered')!='centered'):
    raise ValueError('Probe is scoped to the first all-valid 200x10403 centroid-compensated, centered Run at 100 Hz')
cfg=dict(cpi_duration_s=1.,cpi_hop_duration_s=.25,doppler_estimator='spectral_moments',motion_compensation='auto',period_time_role='scatter_centroid')
profiler=cProfile.Profile();start=time.perf_counter();profiler.enable()
stage=_compute_chirp_observations(echo,cfg)
profiler.disable();elapsed=time.perf_counter()-start
stats=pstats.Stats(profiler)
costs=[]
for (file,line,name),value in stats.stats.items():
    if name in ('matched_filter_chirp','align_profiles_to_common_delay','range_doppler_cube','range_doppler_features','_native_pulse_range_features'):
        costs.append(dict(function=name,calls=value[1],self_seconds=value[2],cumulative_seconds=value[3]))
count=100;iq=echo.iq[:count];fast=echo.fast_time_s
dt=float(np.median(np.diff(fast)));n=chirp_reference_sample_count(echo.metadata['pulse_width_s'],dt)
t=np.arange(n)*dt;phase=t-.5*echo.metadata['pulse_width_s']
reference=np.exp(1j*np.pi*echo.metadata['pulse_bandwidth_hz']/echo.metadata['pulse_width_s']*phase**2)
kernel=np.conj(reference[::-1]).copy();length=fft.next_fast_len(iq.shape[1]+n-1)
cpu=lambda:matched_filter_chirp(iq,fast,echo.metadata['pulse_width_s'],echo.metadata['pulse_bandwidth_hz'],full_output=True)
expected=cpu();records=[]
device='cuda:0' if torch.cuda.is_available() else 'cpu'
def gpu():
    values=torch.as_tensor(iq,device=device)
    local=torch.as_tensor(kernel,device=device)
    return torch.fft.ifft(torch.fft.fft(values,n=length,dim=-1)*torch.fft.fft(local,n=length),dim=-1)[:,:iq.shape[1]+n-1].cpu().numpy()
def synchronize():
    if torch.cuda.is_available():torch.cuda.synchronize()
actual=gpu();synchronize()
assert np.max(abs(actual-expected))/np.max(abs(expected))<1e-5
for repetition in range(5):
    for name,call in (('cpu_matched_filter',cpu),('gpu_matched_filter_with_transfers',gpu)):
        synchronize();start=time.perf_counter();result=call();synchronize()
        records.append(dict(repetition=repetition,kernel=name,seconds=time.perf_counter()-start))
# Slow-time FFT input remains on GPU between repetitions; also measure transfers.
aligned=expected[:,n-1:n-1+iq.shape[1]].copy();taper=np.hanning(101)[:-1,None]
values=torch.as_tensor(aligned,device=device);window=torch.as_tensor(taper,device=device)
cpu_fft=lambda:np.fft.fftshift(np.fft.fft(aligned*taper,axis=0),axes=0)
gpu_fft=lambda:torch.fft.fftshift(torch.fft.fft(values*window,dim=0),dim=0)
np.testing.assert_allclose(gpu_fft().cpu().numpy(),cpu_fft(),rtol=1e-9,atol=1e-7)
for repetition in range(5):
    for name,call in (('cpu_slow_fft',cpu_fft),('gpu_slow_fft_device_resident',gpu_fft)):
        synchronize();start=time.perf_counter();result=call();synchronize()
        records.append(dict(repetition=repetition,kernel=name,seconds=time.perf_counter()-start))
# Group equal padding lengths without changing each row's shift or guard.
axes=fast[None,:]+echo.row_fast_time_offset_s[:100,None]
axis=fast+np.median(echo.row_fast_time_offset_s[:100]);step=float(np.median(np.diff(fast)))
shifts=(axis[0]-axes[:,0])/step;guards=128+np.ceil(abs(shifts)).astype(int)
def cpu_align():return align_profiles_to_common_delay(aligned,axes,common_grid=(axis,step),method='fourier')[1]
def gpu_align():
    source=torch.as_tensor(aligned,device=device);out=torch.empty_like(source)
    for guard in np.unique(guards):
        ids=np.flatnonzero(guards==guard);length=fft.next_fast_len(len(fast)+2*guard)
        index=torch.as_tensor(ids,device=device);padded=torch.zeros((len(ids),length),dtype=torch.complex128,device=device)
        padded[:,guard:guard+len(fast)]=source[index]
        frequencies=torch.as_tensor(fft.fftfreq(length),device=device)
        shift=torch.as_tensor(shifts[ids],device=device)
        corrected=torch.fft.ifft(torch.fft.fft(padded,dim=-1)*torch.exp(2j*np.pi*shift[:,None]*frequencies),dim=-1)
        out[index]=corrected[:,guard:guard+len(fast)]
    return out.cpu().numpy()
align_reference=cpu_align();align_actual=gpu_align()
np.testing.assert_allclose(align_actual,align_reference,rtol=1e-10,atol=1e-10)
for repetition in range(5):
    for name,call in (('cpu_fourier_alignment',cpu_align),('gpu_fourier_alignment_with_transfers',gpu_align)):
        synchronize();start=time.perf_counter();result=call();synchronize()
        records.append(dict(repetition=repetition,kernel=name,seconds=time.perf_counter()-start))
payload=dict(measured_utc=datetime.now(timezone.utc).isoformat(),source=dict(path=str(source),size=source.stat().st_size,mtime_ns=source.stat().st_mtime_ns),
    python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,cpu=platform.processor(),
    iq_shape=list(echo.iq.shape),cuda_runtime=torch.version.cuda,
    gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,torch=torch.__version__,dtype='production complex64 input FFT, complex128 template and output; slow FFT complex128',
    profiled_pulses=200,cpi_pulses=100,cpi_count=len(stage['features'].times_s),run_total_seconds=elapsed,
    scope='single real Run science only; no NPZ stage writes, inspection export, search, HTML or disk read timing; GPU kernels are experimental and not installed',
    matched_filter_max_abs_difference=float(np.max(abs(actual-expected))),
    matched_filter_max_difference_over_peak=float(np.max(abs(actual-expected))/np.max(abs(expected))),
    alignment_max_abs_difference=float(np.max(abs(align_actual-align_reference))),costs=costs,records=records)
folder=args.output;folder.mkdir(parents=True,exist_ok=False)
(folder/'result.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in payload.items() if k!='records'},indent=2))
for name in dict.fromkeys(r['kernel'] for r in records):
    print(name,float(np.median([r['seconds'] for r in records if r['kernel']==name])))
