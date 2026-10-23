"""Exact linear-front-end reuse for scoped receiver-IQ Monte Carlo studies.

Supports compensated, all-valid, disjoint rows and uniform CPI times only.
No stochastic approximation to the feature distribution is made.
"""
from pathlib import Path
import sys
import numpy as np
from scipy import fft, signal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.inversion import _global_delay_grid
from inversion.src.radar_signal import chirp_reference_sample_count

FEATURE_NAMES = ('total_power','doppler_centroid','doppler_bandwidth',
                 'range_centroid','range_energy_width')


def reference_run_features(echo, config, rows, raw, crop_axis, full_axis):
    """Independent production NumPy/SciPy path, not the reuse kernel."""
    from inversion.src.inversion import _echo_pulse_chunk, prepare_chirp_pulse_profiles
    from inversion.src.radar_signal import (align_profiles_to_common_delay,
        centroid_delay_axes,range_doppler_cube,range_doppler_features)
    if not np.array_equal(rows,np.arange(rows[0],rows[-1]+1)):
        raise ValueError('参考Run必须连续')
    chunk = _echo_pulse_chunk(echo,int(rows[0]),int(rows[-1]+1),len(echo.iq))
    chunk.iq = raw
    prepared = prepare_chirp_pulse_profiles(chunk,config,pulse_features_only=True)
    fast = echo.fast_time_s
    step = float(np.median(np.diff(fast)))
    lag = chirp_reference_sample_count(echo.metadata['pulse_width_s'],step)-1
    axes = centroid_delay_axes(fast,len(rows),row_fast_time_offset_s=chunk.row_fast_time_offset_s)
    _, cropped = align_profiles_to_common_delay(prepared['full_compressed'][:,lag:lag+len(fast)],
        axes,valid=chunk.valid,common_grid=(crop_axis,step),method='fourier')
    _, full = align_profiles_to_common_delay(prepared['full_compressed'],prepared['full_delay_axes'],
        common_grid=(full_axis,step),preserve_support=True,method='fourier')
    count = max(2,int(np.ceil(config['cpi_duration_s']*echo.metadata['prf_hz'])))
    hop = max(1,int(np.ceil((config.get('cpi_hop_duration_s') or config['cpi_duration_s']/4)*echo.metadata['prf_hz'])))
    cube = range_doppler_cube(cropped,prepared['processing_times'],chunk.coherence_id,crop_axis,
        cpi_pulses=count,cpi_hop_pulses=hop,valid=chunk.valid,run_id=chunk.run_id,
        energy_iq=full,energy_delay_axis_s=full_axis)
    features = range_doppler_features(cube)
    return np.column_stack((features.total_power,features.doppler_centroid_hz,
        features.rms_bandwidth_hz,features.range_centroid_s,features.energy_range_width_90_s))


class LinearReceiver:
    def __init__(self, echo, config, device='cpu'):
        import torch
        self.torch = torch
        self.device = device if device != 'cuda:0' or torch.cuda.is_available() else 'cpu'
        if echo.metadata.get('echo_output_reference') != 'centroid_compensated':
            raise ValueError('研究复用核要求已经补偿的复基带')
        if config.get('doppler_estimator','spectral_moments') != 'spectral_moments':
            raise ValueError('功率二次展开不适用于narrowband_lag')
        if config.get('motion_compensation','auto') not in ('auto','none','centroid_geometry'):
            raise ValueError('不支持此补偿策略')
        self.echo, self.config = echo, config
        if config.get('period_time_role','scatter_centroid')!='scatter_centroid':
            raise ValueError('此研究复用核仅支持scatter_centroid时标')
        self.fast = np.asarray(echo.fast_time_s)
        self.offset = np.asarray(echo.row_fast_time_offset_s)
        self.step = float(np.median(np.diff(self.fast)))
        self.reference_count = chirp_reference_sample_count(echo.metadata['pulse_width_s'],self.step)
        self.lag = self.reference_count-1
        full_fast = self.fast[0]+(np.arange(len(self.fast)+self.lag)-self.lag)*self.step
        self.crop_axis = _global_delay_grid(self.fast,self.offset)[0]
        self.full_axis = _global_delay_grid(full_fast,self.offset,preserve_support=True)[0]
        t = np.arange(self.reference_count)*self.step
        if echo.metadata.get('baseband_convention','centered') == 'centered':
            t = t-.5*echo.metadata['pulse_width_s']
        elif echo.metadata['baseband_convention'] != 'zero_to_bandwidth':
            raise ValueError('未知基带约定')
        reference = np.exp(1j*np.pi*echo.metadata['pulse_bandwidth_hz']/echo.metadata['pulse_width_s']*t**2)
        self.filter_length = fft.next_fast_len(len(self.fast)+self.lag)
        self.kernel = torch.fft.fft(self.tensor(reference[::-1].conj().copy()), n=self.filter_length)
        self.count = max(2,int(np.ceil(config['cpi_duration_s']*echo.metadata['prf_hz'])))
        hop_s = config.get('cpi_hop_duration_s') or config['cpi_duration_s']/4
        self.hop = max(1,int(np.ceil(hop_s*echo.metadata['prf_hz'])))
        self.window = self.tensor(signal.get_window('hann',self.count),complex=False)
        self.full_axis_tensor = self.tensor(self.full_axis,complex=False)

    def tensor(self, values, complex=True):
        return self.torch.as_tensor(values,device=self.device,
            dtype=self.torch.complex128 if complex else self.torch.float64)

    def check_rows(self, rows):
        e = self.echo
        valid = np.asarray(e.valid[rows])
        if not np.all(valid):raise ValueError('此研究核要求全部有效ADC样点')
        starts = np.asarray(e.row_start_sample[rows],dtype=np.int64)
        if np.any(np.diff(starts)<len(self.fast)):
            raise ValueError('保存行共享ADC索引，禁止生成逐行独立噪声')
        times = np.asarray(e.scatter_elapsed_s[rows])
        for start in range(0,len(rows)-self.count+1,self.hop):
            local = times[start:start+self.count]
            if not np.allclose(np.diff(local),np.median(np.diff(local)),rtol=1e-3,atol=1e-9):
                raise ValueError('此研究核不覆盖慢时间插值路径')
        if len(np.unique(e.coherence_id[rows])) != 1:
            raise ValueError('Run包含多个相干块，请使用生产前端')

    def align(self, iq, rows, axis, full=False):
        torch = self.torch
        origin = self.fast[0]+self.offset[rows]-(self.lag*self.step if full else 0.)
        shifts = (axis[0]-origin)/self.step
        guards = 128+np.ceil(abs(shifts)).astype(int)
        output = torch.empty((len(rows),len(axis)),device=self.device,dtype=torch.complex128)
        for guard in np.unique(guards):
            selected = np.flatnonzero(guards==guard)
            idx = torch.as_tensor(selected,device=self.device)
            length = fft.next_fast_len(max(iq.shape[1],len(axis))+2*int(guard))
            padded = torch.zeros((len(selected),length),device=self.device,dtype=torch.complex128)
            padded[:,guard:guard+iq.shape[1]] = iq[idx]
            # Match the production scipy.fft frequency values and padding.
            frequency = self.tensor(fft.fftfreq(length),complex=False)
            phase = self.tensor(shifts[selected],complex=False)[:,None]*frequency
            moved = torch.fft.ifft(torch.fft.fft(padded,dim=-1)*torch.exp(2j*np.pi*phase),dim=-1)
            output[idx] = moved[:,guard:guard+len(axis)]
        return output

    def transform(self, raw, rows):
        torch = self.torch
        raw = self.tensor(raw) if not isinstance(raw,torch.Tensor) else raw
        compressed = torch.fft.ifft(torch.fft.fft(raw,n=self.filter_length,dim=-1)*self.kernel,dim=-1)
        compressed = compressed[:,:len(self.fast)+self.lag]
        return (self.align(compressed[:,self.lag:self.lag+len(self.fast)],rows,self.crop_axis),
                self.align(compressed,rows,self.full_axis,full=True))

    def coefficients(self, clean, noisy, rows):
        """Return per-CPI range/frequency powers for 1, a and a**2."""
        torch = self.torch
        cs, ce = clean
        ns, ne = noisy
        for start in range(0,len(rows)-self.count+1,self.hop):
            stop = start+self.count
            win = self.window[:,None]
            s = torch.fft.fftshift(torch.fft.fft(cs[start:stop]*win,dim=0),dim=0)
            n = torch.fft.fftshift(torch.fft.fft(ns[start:stop]*win,dim=0),dim=0)
            doppler = torch.stack((s.abs().square().sum(1),
                2*(s*n.conj()).real.sum(1),n.abs().square().sum(1)))
            s, n = ce[start:stop]*win, ne[start:stop]*win
            ranges = self.count*torch.stack((s.abs().square().sum(0),
                2*(s*n.conj()).real.sum(0),n.abs().square().sum(0)))
            local = self.echo.scatter_elapsed_s[rows[start:stop]]
            prt = float(np.median(np.diff(local)))
            frequencies = self.tensor(np.fft.fftshift(np.fft.fftfreq(self.count,d=prt)),complex=False)
            yield ranges,doppler,frequencies

    def features(self, coefficients, amplitudes):
        torch = self.torch
        a = self.tensor(amplitudes,complex=False)
        scales = torch.stack((torch.ones_like(a),a,a*a),dim=1)
        frames = []
        for ranges,doppler,f in coefficients:
            rp = (scales@ranges).clamp(min=0)
            dp = (scales@doppler).clamp(min=0)
            total = rp.sum(1)
            dt = dp.sum(1)
            mu = (dp*f).sum(1)/dt
            width = torch.sqrt((dp*(f[None,:]-mu[:,None]).square()).sum(1)/dt)
            centroid = (rp*self.full_axis_tensor).sum(1)/total
            cumulative = torch.cumsum(rp,dim=1)
            # Same first-sample crossing convention as power_energy_width_90_s.
            index = torch.searchsorted(cumulative.contiguous(),(.05*total)[:,None]).squeeze(1)
            upper = torch.searchsorted(cumulative.contiguous(),(.95*total)[:,None]).squeeze(1)
            energy_width = self.full_axis_tensor[upper]-self.full_axis_tensor[index]
            frames.append(torch.stack((total,mu,width,centroid,energy_width),dim=1))
        return torch.stack(frames,dim=1).cpu().numpy()
