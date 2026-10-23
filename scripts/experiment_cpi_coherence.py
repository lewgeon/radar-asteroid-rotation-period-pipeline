"""Controlled CPI/coherence experiments; never overwrite pipeline results."""
import argparse,json,sys,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from inversion.src.inversion import prepare_chirp_pulse_profiles,multi_harmonic_lomb_scargle
from inversion.src.radar_signal import align_profiles_to_common_delay,range_doppler_cube,range_doppler_features


def summarize(aligned,times,axis):
    cube=range_doppler_cube(aligned,times,np.zeros(len(times),int),axis,
        cpi_pulses=len(times),cpi_hop_pulses=len(times))
    feature=range_doppler_features(cube);power=cube.power.sum(axis=1)[0]
    return dict(centroid=float(feature.doppler_centroid_hz[0]),rms=float(feature.rms_bandwidth_hz[0]),
        outside5=float(power[np.abs(cube.frequencies_hz)>5].sum()/power.sum()))


def controls(source,output):
    with np.load(source,allow_pickle=False) as data:
        offsets=data['row_fast_time_offset_s'][:100];fast=data['fast_time_s'];times=data['scatter_elapsed_s'][:100]
    fs=1/np.median(np.diff(fast));width=50e-6;records=[]
    for ratio in (.1,.5,.75,.95):
        bandwidth=ratio*fs
        for fd in (-2.3,0.,.2):
            for changing in (False,True):
                row=offsets if changing else np.full(100,offsets[0]);u=fast[None,:]+row[:,None]+3e-7
                phase=np.exp(2j*np.pi*fd*(times-times[0]))
                raw=np.where((u>=0)&(u<width),np.exp(1j*np.pi*bandwidth/width*(u-width/2)**2),0)*phase[:,None]
                echo=SimpleNamespace(iq=raw,valid=np.ones(raw.shape,bool),fast_time_s=fast,
                    row_fast_time_offset_s=row,elapsed_s=times,scatter_elapsed_s=times,
                    run_id=np.zeros(100,int),coherence_id=np.zeros(100,int),
                    metadata=dict(pulse_width_s=width,pulse_bandwidth_hz=bandwidth,echo_output_reference='centroid_compensated',prf_hz=100))
                prepared=prepare_chirp_pulse_profiles(echo,{})
                lag=prepared['full_compressed'].shape[1]-len(fast);native=prepared['full_compressed'][:,lag:lag+len(fast)]
                axes=prepared['full_delay_axes'][:,lag:lag+len(fast)];target=prepared['common_delay']
                delta=target+3e-7;support=np.maximum(width-np.abs(delta),0)
                analytic=fs*support*np.sinc(bandwidth/width*delta*support)
                reference=summarize(phase[:,None]*analytic[None,:],times,target)
                for method in ('linear','fourier'):
                    _,aligned=align_profiles_to_common_delay(native,axes,common_grid=(target,1/fs),method=method)
                    values=summarize(aligned,times,target)
                    records.append(dict(ratio=ratio,fd=fd,changing=changing,method=method,**values,
                        centroid_error=values['centroid']-reference['centroid'],rms_error=values['rms']-reference['rms'],reference_rms=reference['rms']))
        print('controlled bandwidth/fs',ratio,flush=True)
    (output/'controls.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records


def period_report(times,values,weights):
    result=multi_harmonic_lomb_scargle(times,values,1800.,14400.,4000,harmonics=1,weights=weights,refine_period=True)
    order=np.argsort(result.grid_periods_s)
    at_half=float(np.interp(5400.,result.grid_periods_s[order],result.grid_scores[order]))
    return dict(period=float(result.best_period_s),error=float(result.best_period_s-5400),
        half_score=at_half,max_score=float(np.max(result.grid_scores)),half_to_max=at_half/max(float(np.max(result.grid_scores)),1e-30))


def real(source,output,scan=False):
    from rotation_gui.window.inversion_feature_preview import _load_echo,_inversion_module
    from rotation_gui.window.result_service import compression_cache
    echo=_load_echo(source);core=_inversion_module();echo=core._pulse_feature_source(echo,len(echo.iq))
    offsets=echo.row_fast_time_offset_s;grid=core._global_delay_grid(echo.fast_time_s,offsets)
    settings=[(1.,.25)] if not scan else [(t,t*h) for t in (.25,.5,1.,2.) for h in (.25,.5,1.)]
    parts={(method,t,hop):[] for method in ('linear','fourier') for t,hop in settings}
    for number,run in enumerate(np.unique(echo.run_id)):
        rows=np.flatnonzero(echo.run_id==run);begin=int(rows[0]);end=int(rows[-1])+1
        local=core._echo_pulse_chunk(echo,begin,end,len(echo.iq))
        config=dict(motion_compensation='auto',period_time_role='scatter_centroid')
        cache=ROOT/'tmp/result_workflow_actual'/f'compression_run_{int(run)}.npz'
        native=compression_cache(source,config,cache,int(run))
        if native is None:
            prepared=core.prepare_chirp_pulse_profiles(local,config,pulse_features_only=True)
            lag=prepared['full_compressed'].shape[1]-len(echo.fast_time_s);native=prepared['full_compressed'][:,lag:lag+len(echo.fast_time_s)]
        axes=local.fast_time_s[None,:]+local.row_fast_time_offset_s[:,None]
        for method in ('linear','fourier'):
            _,aligned=align_profiles_to_common_delay(native,axes,valid=local.valid,common_grid=grid,method=method)
            for duration,hop in settings:
                cube=range_doppler_cube(aligned,local.scatter_elapsed_s,local.coherence_id,grid[0],
                    cpi_pulses=int(np.ceil(duration*100)),cpi_hop_pulses=int(np.ceil(hop*100)),
                    run_id=local.run_id,valid=local.valid,effective_pulse_weight=np.mean(local.valid,axis=1))
                feature=range_doppler_features(cube)
                parts[method,duration,hop].append(np.column_stack((feature.times_s,feature.total_power,feature.doppler_centroid_hz,feature.rms_bandwidth_hz,feature.effective_sample_count)))
                if run==0 and duration==1. and hop==.25:
                    np.savez_compressed(output/f'rd_{method}.npz',power=cube.power[0],delays=grid[0],frequencies=cube.frequencies_hz)
        if number%10==0:print('real Run',number+1,'/100',flush=True)
    records=[]
    for (method,duration,hop),pieces in parts.items():
        array=np.concatenate(pieces)
        np.savez_compressed(output/f'features_{method}_{duration}_{hop}.npz',values=array)
        for column,name in ((1,'power'),(2,'doppler_centroid'),(3,'doppler_rms')):
            records.append(dict(method=method,cpi_s=duration,hop_s=hop,feature=name,observations=len(array),
                **period_report(array[:,0],array[:,column],array[:,4])))
    (output/'real_periods.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records


def geometry(source,output):
    """Independent continuous-LFM response; frozen amplitude/rate within 2 s."""
    from rotation_gui.window.inversion_feature_preview import _load_echo
    from echo.src.mesh import load_mesh
    from echo.src.motion import body_basis,spin_axis_from_config
    echo=_load_echo(source)
    config=json.loads((source.parent.parent/'configs/echo.generated.json').read_text(encoding='utf-8'))
    config=config.get('echo',config)
    axis=spin_axis_from_config(config['target']);basis=body_basis(axis)
    model=Path(config['model_path']);model=model if model.is_absolute() else ROOT/'echo'/model
    mesh=load_mesh(model,device='cpu',dtype='float32')
    centers,normals,areas=[x.cpu().numpy().astype(float) for x in (mesh.centroids,mesh.normals,mesh.areas)]
    omega=2*np.pi/10800.;fc=1e9;speed=299792458.;width=50e-6;bandwidth=150e6
    fast=np.arange(-1.2e-6,1.2e-6,5e-9);dt=np.arange(200)*.01-.995
    runs=np.unique(echo.run_id);rows=[np.flatnonzero(echo.run_id==run) for run in runs]
    center_times=np.array([np.mean(echo.scatter_elapsed_s[index]) for index in rows])
    tx=np.array([echo.tx_los_icrs[index[len(index)//2]] for index in rows]);rx=np.array([echo.rx_los_icrs[index[len(index)//2]] for index in rows])
    records=[];pairs=[]
    def evaluate(t,look_tx,look_rx):
        angle=omega*t;c=np.cos(angle);s=np.sin(angle)
        rot=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
        pose=basis@rot;r=centers@pose.T;n=normals@pose.T
        weights=areas/areas.sum()*np.maximum(-n@look_tx,0)*np.maximum(-n@look_rx,0)
        path=r@(look_tx+look_rx);v=np.cross(omega*axis,r);fd=-fc/speed*(v@(look_tx+look_rx))
        power=weights**2;mu=np.sum(power*fd)/power.sum();rms=np.sqrt(np.sum(power*(fd-mu)**2)/power.sum())
        delay=fast[None,:]-path[:,None]/speed
        duration=np.maximum(width-np.abs(delay),0)
        response=duration/width*np.sinc(bandwidth/width*delay*duration)
        amplitude=weights*np.exp(-2j*np.pi*np.remainder(fc*path/speed,1))
        signal=(np.exp(2j*np.pi*dt[:,None]*fd[None,:])*amplitude[None,:])@response
        values={duration:summarize(signal[:int(100*duration)],t+dt[:int(100*duration)],fast) for duration in (1.,2.)}
        return mu,rms,values,signal
    for mode in ('fixed_look','changing_look'):
        for number,t in enumerate(center_times):
            look_tx=tx[0] if mode=='fixed_look' else tx[number];look_rx=rx[0] if mode=='fixed_look' else rx[number]
            mu,rms,values,signal=evaluate(t,look_tx,look_rx)
            records.append(dict(mode=mode,time=t,incoherent_centroid=mu,incoherent_rms=rms,**{f'{name}_{duration}':value for duration,v in values.items() for name,value in v.items()}))
            if number in (0,25,50,75):
                a,b,after,half_signal=evaluate(t+5400.,look_tx,look_rx)
                pairs.append(dict(mode=mode,run=number,signal_relative_l2=float(np.linalg.norm(signal-half_signal)/np.linalg.norm(signal)),
                    incoherent_centroid_delta=float(a-mu),incoherent_rms_delta=float(b-rms),
                    coherent_centroid_delta=after[1.]['centroid']-values[1.]['centroid'],coherent_rms_delta=after[1.]['rms']-values[1.]['rms']))
            if number%20==0:print('geometry',mode,number+1,'/100',flush=True)
    fits=[]
    for mode in ('fixed_look','changing_look'):
        group=[record for record in records if record['mode']==mode];times=np.array([record['time'] for record in group])
        for name in ('incoherent_centroid','incoherent_rms','centroid_1.0','rms_1.0','centroid_2.0','rms_2.0'):
            fits.append(dict(mode=mode,feature=name,**period_report(times,np.array([record[name] for record in group]),np.ones(len(group)))))
    (output/'geometry_reference.json').write_text(json.dumps(dict(records=records,half_turn=pairs,periods=fits),indent=2),encoding='utf-8')
    return fits


def noise_pilot(source,output,seeds=5,estimator='spectral_moments'):
    """Paired ideal two orthogonal range channels; not an ellipsoid simulation."""
    with np.load(source,allow_pickle=False) as data:
        times=data['scatter_elapsed_s'];runs=data['run_id']
    center=np.array([np.mean(times[runs==run]) for run in np.unique(runs)])
    phase=2*np.pi*center/5400.;amplitude=np.sqrt(1+.3*np.cos(phase))
    mu=.15*np.sin(phase);sigma=.08+.03*np.cos(phase)
    clean=np.empty((len(times),2),complex)
    for number,run in enumerate(np.unique(runs)):
        selected=np.flatnonzero(runs==run);dt=times[selected]-center[number]
        clean[selected]=amplitude[number]/np.sqrt(2)*np.exp(2j*np.pi*dt[:,None]*(mu[number]+sigma[number]*np.array([-1.,1.]))[None,:])
    records=[];settings=[(.25,.0625),(.5,.125),(1.,.25),(2.,.5),(1.,.5),(1.,1.)]
    def fit(t,value,weight):
        result=multi_harmonic_lomb_scargle(t,value,1800.,14400.,800,harmonics=1,weights=weight,refine_period=True)
        return float(result.best_period_s)
    for snr in (None,20.,40.):
        for seed in range(1 if snr is None else seeds):
            rng=np.random.default_rng(20261014+seed)
            std=0 if snr is None else np.sqrt(np.mean(abs(clean)**2)/10**(snr/10)/2)
            observed=clean+std*(rng.normal(size=clean.shape)+1j*rng.normal(size=clean.shape))
            period=fit(times,np.sum(abs(observed)**2,axis=1),np.ones(len(times)))
            records.append(dict(snr_db=snr,seed=seed,feature='pulse_power',cpi_s=0,hop_s=0,period=period,error=period-5400))
            for duration,hop in settings:
                count=int(np.ceil(duration*100));hop_count=int(np.ceil(hop*100))
                cube=range_doppler_cube(observed,times,np.zeros(len(times),int),np.arange(2),
                    cpi_pulses=count,cpi_hop_pulses=hop_count,run_id=runs,doppler_estimator=estimator)
                feature=range_doppler_features(cube)
                taper=np.hanning(count+1)[:-1]
                direct=np.array([count*np.sum(abs(observed[begin:end]*taper[:,None])**2)
                    for begin,end in zip(cube.cpi_start_pulse,cube.cpi_end_pulse)])
                error=float(np.max(abs(direct-feature.total_power)/np.maximum(direct,1e-30)))
                if error>1e-12:raise AssertionError('Parseval control failed')
                for name,value in (('cpi_power',feature.total_power),('doppler_centroid',feature.doppler_centroid_hz),('doppler_rms',feature.rms_bandwidth_hz)):
                    finite=np.isfinite(value)
                    period=fit(feature.times_s[finite],value[finite],feature.effective_sample_count[finite]) if finite.sum()>=5 else float('nan')
                    records.append(dict(snr_db=snr,seed=seed,feature=name,cpi_s=duration,hop_s=hop,period=period,error=period-5400,
                        parseval_relative_error=error,estimator=estimator,accepted_fraction=float(finite.mean())))
            print('noise pilot',snr,'seed',seed+1,flush=True)
    (output/f'noise_{estimator}.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records


def real_lag(source,output):
    from rotation_gui.window.inversion_feature_preview import _load_echo,_inversion_module
    from rotation_gui.window.result_service import compression_cache
    from inversion.src.radar_signal import narrowband_doppler_moments
    echo=_load_echo(source);core=_inversion_module();echo=core._pulse_feature_source(echo,len(echo.iq))
    grid=core._global_delay_grid(echo.fast_time_s,echo.row_fast_time_offset_s);rows=[]
    for number,run in enumerate(np.unique(echo.run_id)):
        indices=np.flatnonzero(echo.run_id==run);local=core._echo_pulse_chunk(echo,int(indices[0]),int(indices[-1])+1,len(echo.iq))
        config=dict(motion_compensation='auto',period_time_role='scatter_centroid')
        native=compression_cache(source,config,ROOT/'tmp/result_workflow_actual'/f'compression_run_{int(run)}.npz',int(run))
        if native is None:
            prepared=core.prepare_chirp_pulse_profiles(local,config,pulse_features_only=True)
            lag=prepared['full_compressed'].shape[1]-len(echo.fast_time_s);native=prepared['full_compressed'][:,lag:lag+len(echo.fast_time_s)]
        axes=local.fast_time_s[None,:]+local.row_fast_time_offset_s[:,None]
        _,aligned=align_profiles_to_common_delay(native,axes,valid=local.valid,common_grid=grid,method='fourier')
        for begin in range(0,len(local.iq)-100+1,25):
            times=local.scatter_elapsed_s[begin:begin+100]
            mu,sigma,quality=narrowband_doppler_moments(aligned[begin:begin+100],np.median(np.diff(times)))
            rows.append(dict(time=float(np.mean(times)),centroid=mu,rms=sigma,run=int(run),**quality))
        if number%20==0:print('lag estimator Run',number+1,'/100',flush=True)
    fits=[dict(feature=name,**period_report(np.array([row['time'] for row in rows]),np.array([row[name] for row in rows]),np.full(len(rows),25.))) for name in ('centroid','rms')]
    (output/'real_lag.json').write_text(json.dumps(dict(records=rows,periods=fits),indent=2),encoding='utf-8')
    return fits


def stripes(source,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with np.load(source,allow_pickle=False) as data:
        fast=data['fast_time_s'];offsets=data['row_fast_time_offset_s'][:100];times=data['scatter_elapsed_s'][:100]
    fs=1/np.median(np.diff(fast));bandwidth=150e6;width=50e-6
    delta=np.linspace(-100e-9,100e-9,4001)
    rectangle=np.sinc(bandwidth*delta)
    hamming=.54*rectangle+.23*np.sinc(bandwidth*delta-1)+.23*np.sinc(bandwidth*delta+1)
    hamming/=hamming.max()
    def metrics(values,first_null):
        side=abs(delta)>first_null
        selected=np.flatnonzero(abs(values)**2>=.5)
        return dict(side_db=float(20*np.log10(np.max(abs(values[side])))),fwhm_ns=float((delta[selected[-1]]-delta[selected[0]])*1e9))
    report=dict(rectangle=metrics(rectangle,1/bandwidth),hamming=metrics(hamming,2/bandwidth))
    figure,axes=plt.subplots(2,2,figsize=(12,7))
    axes[0,0].plot(delta*1e9,20*np.log10(np.maximum(abs(rectangle),1e-6)),label='Rectangular spectrum')
    axes[0,0].plot(delta*1e9,20*np.log10(np.maximum(abs(hamming),1e-6)),label='Hamming spectral weighting')
    axes[0,0].set_ylim(-60,1);axes[0,0].set_xlabel('Relative delay (ns)');axes[0,0].set_ylabel('Response (dB)');axes[0,0].legend()
    summary=[]
    for changing,method,axis in ((False,'fourier',axes[0,1]),(True,'linear',axes[1,0]),(True,'fourier',axes[1,1])):
        row=offsets if changing else np.full(100,offsets[0]);u=fast[None,:]+row[:,None]+300e-9
        iq=np.where((u>=0)&(u<width),np.exp(1j*np.pi*bandwidth/width*(u-width/2)**2),0)
        echo=SimpleNamespace(iq=iq,valid=np.ones(iq.shape,bool),fast_time_s=fast,row_fast_time_offset_s=row,
            elapsed_s=times,scatter_elapsed_s=times,run_id=np.zeros(100,int),coherence_id=np.zeros(100,int),
            metadata=dict(pulse_width_s=width,pulse_bandwidth_hz=bandwidth,echo_output_reference='centroid_compensated',prf_hz=100))
        prepared=prepare_chirp_pulse_profiles(echo,{},pulse_features_only=True)
        lag=prepared['full_compressed'].shape[1]-len(fast);native=prepared['full_compressed'][:,lag:lag+len(fast)]
        target=fast+np.median(row)
        _,aligned=align_profiles_to_common_delay(native,fast[None,:]+row[:,None],common_grid=(target,1/fs),method=method)
        cube=range_doppler_cube(aligned,times,echo.coherence_id,target,cpi_pulses=100,cpi_hop_pulses=100)
        power=cube.power[0];db=10*np.log10(np.maximum(power/power.max(),1e-12))
        axis.pcolormesh(cube.frequencies_hz,(target+300e-9)*1e9,db,shading='nearest',vmin=-45,vmax=0,cmap='magma')
        axis.set_ylim(-120,120);axis.set_xlim(-10,10);axis.set_xlabel('Doppler (Hz)');axis.set_ylabel('Delay from point (ns)')
        axis.set_title(('Fixed ADC phase' if not changing else 'Changing ADC phase')+' / '+method)
        summary.append(dict(changing=changing,method=method,**summarize(aligned,times,target)))
    figure.tight_layout();figure.savefig(output/'stripes_controls.png',dpi=180);plt.close(figure)
    report['controls']=summary
    (output/'stripes.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return summary


def saved_rd_stripes(source,html,output):
    """Reproduce the selected Run-1/CPI-1 report; do not alter pipeline artifacts."""
    import base64,re,subprocess,types
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from scipy.signal import find_peaks,get_window
    from rotation_gui.window.result_service import load_run
    from inversion.src.radar_signal import matched_filter_chirp
    text=html.read_text(encoding='utf-8')
    matches=list(re.finditer(r'Plotly\.newPlot\(\s*"[^"]+"\s*,',text))
    decoder=json.JSONDecoder();rest=text[matches[-1].end():].lstrip()
    traces,end=decoder.raw_decode(rest);layout,_=decoder.raw_decode(rest[end:].lstrip()[1:].lstrip())
    if not re.search(r'Run 1(?:\s|·)',layout['title']['text']) or '脉冲 [0,100)' not in layout['title']['text']:
        raise ValueError('此诊断协议仅适用Run 1的首100脉冲')
    def array(value):
        if isinstance(value,dict) and 'bdata' in value:
            result=np.frombuffer(base64.b64decode(value['bdata']),dtype=value['dtype'])
            return result.reshape(tuple(int(n) for n in value['shape'].split(','))) if 'shape' in value else result
        return np.asarray(value)
    frame=traces[-1];frequency=array(frame['x']);axis=array(frame['y'])*1e-9;html_db=array(frame['z'])
    if html_db.shape!=(len(axis),100) or len(frequency)!=100 or frame.get('visible',True) is False:
        raise ValueError('不是所选的100脉冲RD帧')
    echo,indices=load_run(source,0)
    if not np.array_equal(indices[:100],np.arange(100)):raise ValueError('首Run不是前100脉冲')
    center=float(np.mean(echo.scatter_elapsed_s[:100]))
    if f't={center:.9g}s' not in layout['title']['text']:raise ValueError('HTML时刻与输入脉冲不符')
    iq=echo.iq[:100];fast=echo.fast_time_s
    base=subprocess.check_output(['git','-C',str(ROOT/'inversion'),'-c','safe.directory='+(ROOT/'inversion').as_posix(),'show','HEAD:src/radar_signal.py'],cwd=ROOT)
    revision=subprocess.check_output(['git','-C',str(ROOT/'inversion'),'-c','safe.directory='+(ROOT/'inversion').as_posix(),'rev-parse','HEAD'],cwd=ROOT).decode().strip()
    old=types.ModuleType('rd_stripe_baseline');sys.modules[old.__name__]=old;exec(compile(base,'HEAD:radar_signal.py','exec'),old.__dict__)
    width=echo.metadata['pulse_width_s'];bandwidth=echo.metadata['pulse_bandwidth_hz']
    native=matched_filter_chirp(iq,fast,width,bandwidth)
    baseline=old.matched_filter_chirp(iq,fast,width,bandwidth)
    report=dict(title=layout['title']['text'],baseline_commit=revision,loaded_rows=len(echo.iq),computed_rows=100,
        matched_filter_max_abs_diff=float(np.max(abs(native-baseline))),variants=[])
    offsets=echo.row_fast_time_offset_s[:100];axes=fast[None,:]+offsets[:,None]
    taper=get_window('hann',100,fftbins=True)[:,None];roi=(axis*1e9>=-415)&(axis*1e9<=-40)
    fig,pics=plt.subplots(1,3,figsize=(14,5),sharey=True)
    for method,pic in zip(('linear','fourier'),pics[:2]):
        _,aligned=align_profiles_to_common_delay(native,axes,common_grid=(axis,float(np.median(np.diff(fast)))),method=method)
        power=abs(np.fft.fftshift(np.fft.fft(aligned*taper,axis=0),axes=0).T)**2
        db=10*np.log10(np.maximum(power/power.max(),1e-12))
        before=100*np.sum(abs(aligned*taper)**2,axis=0);after=power.sum(axis=1)
        np.testing.assert_allclose(before,after,rtol=1e-12,atol=1e-7)
        peaks,_=find_peaks(after[roi]/after.max(),prominence=.005)
        difference=float(np.max(abs(10**(html_db/10)-power/power.max())))
        report['variants'].append(dict(method=method,distance_local_peaks=len(peaks),
            parseval_max_relative_error=float(np.max(abs(before-after))/after.max()),html_power_max_abs_difference=difference))
        pic.pcolormesh(frequency,axis[roi]*1e9,db[roi],shading='nearest',cmap='magma',vmin=-45,vmax=0)
        pic.set_title('Full rows: '+method);pic.set_xlabel('Doppler (Hz)')
        if method=='fourier':
            if difference>1e-7:raise ValueError('当前单CPI重算未复现指定HTML，不能归因')
            zero=int(np.argmin(abs(frequency)))
            if frequency[zero]!=0:raise ValueError('所选帧没有零多普勒格')
            direct=abs(np.sum(aligned*taper,axis=0))**2
            np.testing.assert_allclose(power[:,zero],direct,rtol=1e-12,atol=1e-7)
            selected=10**(html_db[:,zero]/10)
            first=abs(aligned[0])**2;average=np.mean(abs(aligned)**2,axis=0)
            np.savez_compressed(output/'selected_rd_column.npz',delays_s=axis,
                html_column_relative_power=selected,first_aligned_pulse_power=first,
                mean_aligned_pulse_power=average,zero_bin_power=power[:,zero],
                frequencies_hz=frequency,column_index=zero)
            from matplotlib.font_manager import FontProperties
            font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
            with plt.rc_context({'font.family':font.get_name(),'axes.unicode_minus':False}):
                lines,panels=plt.subplots(2,1,figsize=(10,7),sharex=True)
                x=axis[roi]*1e9;profile=selected/selected.max()
                panels[0].plot(x,profile[roi],'.-',lw=1,ms=3,color='#2463a6')
                panels[0].set_ylabel('归一化功率');panels[0].set_ylim(0,1.06)
                panels[0].set_title(f'距离—多普勒图第{zero+1}/{len(frequency)}列：{frequency[zero]:g} Hz\nRun 1，脉冲[0,100)，CPI中心 {center:.7f} s')
                for values,label,color in ((selected,'FFT后：所选0 Hz列','#2463a6'),
                    (first,'FFT前：第1脉冲（已距离对齐）','#cf6d24'),
                    (average,'FFT前：100脉冲平均功率','#39805b')):
                    panels[1].plot(x,10*np.log10(np.maximum(values[roi]/values.max(),1e-12)),
                        label=label,color=color,lw=1.1)
                panels[1].set_ylim(-45,1);panels[1].set_ylabel('各曲线相对自身峰值（dB）')
                panels[1].set_xlabel('快时间：质心相对延迟（ns）');panels[1].legend(fontsize=9)
                for panel in panels:panel.set_xlim(-415,-40);panel.grid(alpha=.2)
                lines.tight_layout();lines.savefig(output/'selected_rd_column.png',dpi=180)
                lines.savefig(output/'selected_rd_column.svg');plt.close(lines)
            report['selected_column']=dict(index_zero_based=zero,ordinal_one_based=zero+1,
                frequency_hz=float(frequency[zero]),dc_direct_max_relative_difference=float(
                    np.max(abs(power[:,zero]-direct))/np.max(power[:,zero])),
                power_fraction_in_center_three_bins=float(power[:,zero-1:zero+2].sum()/power.sum()))
            keep=np.unique(np.linspace(0,len(axis)-1,655).astype(int));keep=keep[roi[keep]]
            pics[2].pcolormesh(frequency,axis[keep]*1e9,db[keep],shading='nearest',cmap='magma',vmin=-45,vmax=0)
            pics[2].set_title('Same Fourier data: simulated 655-row display');pics[2].set_xlabel('Doppler (Hz)')
    pics[0].set_ylabel('Centroid-relative delay (ns)')
    for pic in pics:pic.set_ylim(-415,-40);pic.set_xlim(-4,4)
    fig.tight_layout();fig.savefig(output/'selected_rd_stripes.png',dpi=160);plt.close(fig)
    (output/'selected_rd_stripes.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['controls','real','real-scan','geometry','noise','noise-lag','lag','stripes','saved-rd'],required=True)
    parser.add_argument('--seeds',type=int,default=5)
    parser.add_argument('--echo',type=Path,default=ROOT/'runs/seperate_observation_2/echo/echo.npz')
    parser.add_argument('--output',type=Path,default=ROOT/'tmp/cpi_coherence_20261014')
    parser.add_argument('--html',type=Path,default=ROOT/'.gui_state/previews/seperate_observation_2/rd_run_-1_cpi_0.html')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True);begin=time.perf_counter()
    from datetime import datetime,timezone
    import scipy,platform
    info=args.echo.stat()
    manifest=dict(start_utc=datetime.now(timezone.utc).isoformat(),mode=args.mode,seeds=args.seeds,
        source=dict(path=str(args.echo.resolve()),size=info.st_size,mtime_ns=info.st_mtime_ns),
        python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,
        estimator_scope='Fixed 100 Hz, 200 MHz / 150 MHz / 50 us / 1 GHz, P=10800 s controls')
    if args.mode=='saved-rd':
        manifest['estimator_scope']='Selected Run 1, pulses [0,100), HTML grid, Hann, current linear/fourier; no historical full-chain replay'
    (args.output/f'manifest_{args.mode}.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    records=(saved_rd_stripes(args.echo,args.html,args.output) if args.mode=='saved-rd' else controls(args.echo,args.output) if args.mode=='controls' else geometry(args.echo,args.output) if args.mode=='geometry' else noise_pilot(args.echo,args.output,args.seeds,'narrowband_lag' if args.mode=='noise-lag' else 'spectral_moments') if args.mode in ('noise','noise-lag') else real_lag(args.echo,args.output) if args.mode=='lag' else stripes(args.echo,args.output) if args.mode=='stripes' else real(args.echo,args.output,args.mode=='real-scan'))
    count=records['computed_rows'] if args.mode=='saved-rd' else len(records)
    print(json.dumps(dict(mode=args.mode,seconds=time.perf_counter()-begin,rows=count)),flush=True)
if __name__=='__main__':main()
