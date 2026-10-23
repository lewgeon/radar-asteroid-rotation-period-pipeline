"""One bounded, cancellable worker for Run-level result views.

Scientific algorithms live in inversion/src; this service owns selection, IO,
resource bounds and derived-view publication. No campaign IQ is materialized.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse
import json
import sys
import zipfile
import numpy as np
from .inversion_feature_preview import _inversion_module, _views

RUN_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 32 * 1024 * 1024
CPI_BYTES = 512 * 1024 * 1024


def result_menu_snapshot(source,run_id=-1,cpi_index=-1):
    """Read-only menu status, called outside the GUI thread."""
    source=Path(source)
    try:
        chirp=len(array_header(source,'iq')[0])==2
        catalog=run_catalog(source)
    except (OSError,ValueError,KeyError,zipfile.BadZipFile):
        return dict(chirp=False,runs=[],cpis=[],available={},context=None,error='无有效回波',run_id=None,cpi_index=None,
            source_exists=source.is_file())
    if run_id not in {-1,*[row[0] for row in catalog]}:
        run_id=-1 if chirp else 0
    context=completed_inversion(source)
    cpis=cpi_catalog(source,context['config'],run_id) if context is not None and chirp else []
    actual_cpis=[index for index,_ in cpis if index>=0]
    if cpi_index not in actual_cpis:cpi_index=actual_cpis[0] if actual_cpis else -1
    kinds=('compression','saved','pulse','rd','period','selection','uncertainty')
    available={kind:saved_view_available(source,kind,run_id,cpi_index if kind=='rd' else -1)
        if chirp or kind in ('saved','period','selection','uncertainty') else False for kind in kinds}
    return dict(chirp=chirp,runs=catalog,cpis=cpis,available=available,context=context,error=None,
        run_id=run_id,cpi_index=cpi_index,source_exists=True)


def completed_inversion(source):
    """Return a saved result context; never process IQ or current GUI parameters."""
    folder=Path(source).parent.parent/'inversion'
    if (folder/'inversion_in_progress.json').is_file():return None
    observables=folder/'period_observables.npz'
    if not observables.is_file() or not (folder/'best_summary.json').is_file():return None
    marker=folder/'inversion_complete.json'
    try:
        if marker.is_file():
            stamp=json.loads(marker.read_text(encoding='utf-8'))
            if stamp['observables']!=_views().file_identity(observables):return None
        elif not (folder/'periodogram.html').is_file():return None
        with np.load(observables,allow_pickle=False) as data:
            metadata=json.loads(data['metadata_json'].item())
            observations=int(data['time_elapsed_s'].shape[0])
        return dict(folder=folder,config=metadata.get('inversion_config',{}),observations=observations,
            source_identity=metadata.get('echo_identity'),path=metadata.get('search_diagnostics',{}).get('processing_path'))
    except (OSError,ValueError,KeyError,TypeError,AttributeError,IndexError,zipfile.BadZipFile):return None


def saved_view_available(source,kind,run_id=-1,cpi_index=-1):
    context=completed_inversion(source)
    if context is None:return False
    if kind=='saved':return True
    if kind=='period':return (context['folder']/'periodogram.html').is_file()
    if kind=='selection':
        try:
            folder = context['folder']
            stamp = json.loads((folder/'inversion_complete.json').read_text(encoding='utf-8'))
            return ((folder/'period_selection.html').is_file()
                    and stamp.get('selection_report_identity') == _views().file_identity(folder/'period_selection.json')
                    and stamp.get('selection_html_identity') == _views().file_identity(folder/'period_selection.html'))
        except (OSError, ValueError, TypeError):
            return False
    if kind=='uncertainty':
        try:
            return (context['folder']/'period_uncertainty.html').is_file() and bool(json.loads((context['folder']/'period_uncertainty.json').read_text(encoding='utf-8')).get('enabled'))
        except (OSError,ValueError):return False
    if not Path(source).is_file():return False
    if context['source_identity'] is not None and context['source_identity']!=_views().file_identity(source):return False
    _inversion_module()
    if kind in ('pulse','compression'):
        from inspection_store import ready_inspection
        folder=ready_inspection(source,context['config'])
        if folder is not None:
            return (folder/('pulse_observables.npz' if kind=='pulse' else
                'compression_campaign.npz' if run_id==-1 else f'compression_run_{int(run_id)}.npz')).is_file()
        from .. import storage
        legacy=storage.PREVIEW_DIR/Path(source).parent.parent.name.replace(' ','_')
        if kind=='compression':return cached(source,context['config'],legacy/f'compression_run_{run_id}.html','compression',run_id)
        from .inversion_feature_preview import cached_feature_html
        path=legacy/'inversion_features.html'
        return cached_feature_html(source,context['config'],path) or cached(source,context['config'],path,'pulse',0)
    if kind=='rd':
        if context['path']!='cpi':return False
        from processing_store import identity,cpi_folder_candidates,cpi_key_matches
        from cpi_display import frame_header
        token=SimpleNamespace(_source_identity=identity(source),_processing_store=Path(source).parent/'processing_cache')
        indices=[index for index,_ in cpi_catalog(source,context['config'],run_id) if index>=0 and cpi_index in (-1,index)]
        for index in indices:
            try:
                for folder in cpi_folder_candidates(token,context['config']):
                    frame=folder/f'{index}.npz'
                    if not frame.is_file():continue
                    with np.load(frame,allow_pickle=False) as data:
                        if not cpi_key_matches(json.loads(data['key'].item()),token,context['config']):continue
                        frame_header(frame,CPI_BYTES)
                        return True
            except (OSError,ValueError,KeyError,zipfile.BadZipFile,IndexError):continue
        return False
    return False


def array_header(path, name):
    with zipfile.ZipFile(path) as archive, archive.open(name + '.npy') as stream:
        version=np.lib.format.read_magic(stream)
        shape, order, dtype=np.lib.format._read_array_header(stream,version)
    if dtype.hasobject:
        raise ValueError('结果读取不支持对象数组')
    return shape, order, dtype


def cpi_catalog(source,config,run_id=-1):
    with np.load(source,allow_pickle=False) as data:
        if 'run_id' not in data.files:return []
        runs=data['run_id'];groups=data['coherence_id'];metadata=json.loads(data['metadata_json'].item())
        times=data['scatter_elapsed_s'] if config.get('period_time_role','scatter_centroid')=='scatter_centroid' else data['elapsed_s']
    prf=float(metadata.get('prf_hz',0));duration=float(config.get('cpi_duration_s',0))
    if min(prf,duration)<=0:return []
    count=max(2,int(np.ceil(prf*duration)));hop=max(1,int(np.ceil(prf*float(config.get('cpi_hop_duration_s') or duration/4))))
    windows=[];actual=False
    cache=Path(source).parent/'processing_cache/observations.npz'
    try:
        _inversion_module()
        from processing_store import stage_key,identity,cpi_key_matches
        with np.load(cache,allow_pickle=False) as data:
            manifest=json.loads(data['manifest'].item())
            expected=stage_key(SimpleNamespace(_source_identity=identity(source)),config)
            if manifest['key']==expected or cpi_key_matches(manifest['key'], SimpleNamespace(_source_identity=identity(source)), config):
                windows=data['cpi_windows'].tolist();actual=True
    except (OSError,ValueError,KeyError,TypeError,AttributeError,zipfile.BadZipFile):pass
    if not actual:
        # Do not guess validity or start a large decompression on the UI thread.
        # The first request creates the same scientific stage as inversion.
        return [(-1,'生成反演中间结果后选择CPI窗口')]
    # After preprocessing, actual valid-window selection replaces the plan.
    return [(index,f"Run {int(runs[begin])+1} · 脉冲 [{begin},{end}) · t={np.mean(times[begin:end]):.7g}s")
        for index,(begin,end) in enumerate(windows) if run_id in (-1,None) or runs[begin]==run_id]


def scientific_rd(source,config,run_id,cpi_index,progress=None):
    core=_inversion_module()
    from processing_store import identity
    token=SimpleNamespace(_source_identity=identity(source),
        _processing_store=Path(source).parent/'processing_cache')
    selected=cpi_index
    if selected<0:
        catalog=cpi_catalog(source,config,run_id)
        selected=catalog[0][0] if catalog else -1
    if selected>=0:
        figure=_cached_scientific_rd(token,config,run_id,selected)
        if figure is not None:
            if progress:progress(90,'读取选定CPI的已保存频谱；无需载入全场中间结果')
            return figure
    from .inversion_feature_preview import _load_echo
    echo=_load_echo(source)
    stage=core.prepare_chirp_observations(echo,config,
        lambda stage,percent,message:progress(percent,message) if progress else None)
    if stage['processing_path']!='cpi':raise ValueError('周期反演当前走逐脉冲路线，没有慢时间FFT；请查看实际特征')
    if cpi_index<0:
        windows=stage['cpi_windows']
        choices=np.flatnonzero(np.ones(len(windows),bool) if run_id==-1 else stage['run_id'][windows[:,0]]==run_id)
        if not len(choices):raise ValueError('该Run没有可用CPI')
        cpi_index=int(choices[0])
    figure=_cached_scientific_rd(echo,config,run_id,cpi_index)
    if figure is None:raise ValueError('选定CPI频谱缺失或来源失效，请重新生成反演中间结果')
    return figure


def _cached_scientific_rd(echo,config,run_id,cpi_index):
    """Read one certified frame, never the campaign observation arrays."""
    from processing_store import cpi_folder_candidates,cpi_key_matches,identity
    from cpi_display import read_display
    saved=None
    for folder in cpi_folder_candidates(echo,config):
        frame=folder/f'{cpi_index}.npz'
        if not frame.is_file():continue
        try:
            with np.load(frame,allow_pickle=False) as data:
                if not cpi_key_matches(json.loads(data['key'].item()),echo,config):continue
            saved=read_display(frame,CPI_BYTES)
        except (OSError,ValueError,KeyError,TypeError,IndexError,zipfile.BadZipFile):continue
        break
    if saved is None:return None
    run=saved['run_id'];begin=saved['begin'];end=saved['end']
    if run_id!=-1 and run_id!=run:raise ValueError('CPI列表已变化，请重新选择窗口')
    delays=saved['delays_s'];frequencies=saved['frequencies_hz'];time=saved['time_s']
    figure=_views().processing_figure(dict(times_s=np.array([time]),delays_s=delays,
        range_time_power=saved['range_power'][None,:],rd_power_db=saved['power_db'][None,:,:],
        rd_frequencies_hz=frequencies[None,:],rd_times_s=[time],cpi_start_pulse=[begin],cpi_end_pulse=[end]))
    figure.layout.annotations[0].text='所选CPI的一维距离功率（FFT功率沿频率求和；不是逐脉冲序列）'
    figure.layout.annotations[1].text='反演中间结果：距离—多普勒功率'
    figure.update_layout(title=f'周期反演共享中间结果 · Run {run+1} · 脉冲 [{begin},{end}) · t={time:.9g}s<br>Hann窗；完整距离列；公共全场网格；不是独立重算单Run')
    if identity(echo._source_identity['path'])!=echo._source_identity:
        raise ValueError('读取CPI期间回波发生变化，请重新查看')
    return figure


def scientific_features(source,config,path,progress=None):
    before=request_key(source,config,'scientific_features',0,0)
    from .inversion_feature_preview import _load_echo
    echo=_load_echo(source);core=_inversion_module()
    stage=core.prepare_chirp_observations(echo,config,
        lambda stage,percent,message:progress(percent,message) if progress else None)
    features=stage['features']
    if stage['processing_path']=='cpi':
        names=['total_power','doppler_centroid_hz','rms_bandwidth_hz','range_centroid_s','energy_range_width_90_s']
        windows=stage['cpi_windows'];runs=stage['run_id'][windows[:,0]]
    else:
        names=['total_power','centroid_delay_s','energy_width_90_s'];runs=stage['run_id']
    output=echo._processing_store/'period_observables.npz'
    np.savez_compressed(output,time_elapsed_s=features.times_s,
        value=np.column_stack([getattr(features,name) for name in names]),feature_names=names,run_id=runs,
        metadata_json=np.array(json.dumps(dict(search_diagnostics=dict(processing_path=stage['processing_path']),
            time_axis_role=stage['time_axis_role'],inversion_config=config,echo_identity=_views().file_identity(source)))))
    figure=_views().saved_feature_figure(output,current_config=config,current_echo_identity=_views().file_identity(source))
    figure.layout.title.text += '；已生成共享中间结果，周期搜索尚未执行'
    def validate():
        if request_key(source,config,'scientific_features',0,0)!=before:raise ValueError('绘图期间回波改变')
    _views().write_html_atomic(figure,path,validate=validate,standalone=False)
    path.with_suffix('.view.json').write_text(json.dumps(before),encoding='utf-8')
    return path


def run_catalog(path):
    shape,order,dtype=array_header(path,'iq')
    if len(shape) not in (1,2) or not shape[0]:
        raise ValueError('回波必须是一维CW或二维Chirp且非空')
    if len(shape)==1:
        return [(0,min(shape[0],20000))]
    with np.load(path,allow_pickle=False) as data:
        ids=data['run_id'] if 'run_id' in data.files else np.zeros(shape[0],int)
    if ids.shape!=(shape[0],):
        raise ValueError('run_id与IQ脉冲数不一致')
    return [(int(run),int(count)) for run,count in zip(*np.unique(ids,return_counts=True))]


def read_rows(path,name,indices,progress=None):
    """Map stored members directly; bounded sequential fallback for compressed ZIP."""
    shape,order,dtype=array_header(path,name)
    if order:
        raise ValueError(f'{name}为Fortran存储；当前有界读取仅支持C顺序')
    indices=np.asarray(indices,dtype=np.int64)
    if not len(shape) or np.any(indices<0) or np.any(indices>=shape[0]) or np.any(np.diff(indices)<=0):
        raise ValueError(f'{name}的行选择必须有效、严格递增')
    width=int(np.prod(shape[1:],dtype=np.int64)) if len(shape)>1 else 1
    row_bytes=width*dtype.itemsize
    if len(indices)*row_bytes>RUN_BYTES:
        raise ValueError('选定Run超过256 MiB读取预算；请缩短Run或另行规划磁盘流式产物')
    _inversion_module()
    from npz_mapping import try_map_npz_member,source_identity
    before=source_identity(path)
    mapped=try_map_npz_member(path,name,expected_identity=before)
    if mapped is not None:
        try:
            # Fancy indexing already owns a bounded copy; avoid copying twice.
            result=np.asarray(mapped[indices])
            if source_identity(path)!=before:raise ValueError('读取期间回波发生变化')
            return result
        finally:mapped._mmap.close()
    result=np.empty((len(indices),*shape[1:]),dtype=dtype)
    with zipfile.ZipFile(path) as archive,archive.open(name+'.npy') as stream:
        version=np.lib.format.read_magic(stream)
        np.lib.format._read_array_header(stream,version)
        row=0
        for target, source in enumerate(indices):
            skip=(int(source)-row)*row_bytes
            while skip:
                data=stream.read(min(skip,1024*1024))
                if not data:
                    raise ValueError(f'{name}数据截断')
                skip-=len(data)
            view=memoryview(result[target:target+1]).cast('B')
            offset=0
            while offset<row_bytes:
                data=stream.read(min(row_bytes-offset,1024*1024))
                if not data:
                    raise ValueError(f'{name}数据截断')
                view[offset:offset+len(data)]=data
                offset+=len(data)
            row=int(source)+1
            if progress:
                progress(target+1,len(indices))
    return result


def load_run(path,run_id,progress=None):
    shape,order,dtype=array_header(path,'iq')
    with np.load(path,allow_pickle=False) as data:
        metadata=json.loads(str(data['metadata_json'].item())) if 'metadata_json' in data.files else {}
        ids=(data['run_id'] if 'run_id' in data.files else np.zeros(shape[0],int))
        if len(shape)==1:
            if run_id!=0:
                raise ValueError('CW仅提供前20000样点诊断段')
            indices=np.arange(min(20000,shape[0]))
        else:
            if ids.shape!=(shape[0],):
                raise ValueError('run_id与脉冲数不一致')
            indices=np.flatnonzero(ids==run_id)
        if not len(indices):
            raise ValueError('选定Run不存在')
        fields={'metadata':metadata}
        # Validate offset precedence on the whole small axis before slicing.
        from .inversion_feature_preview import _inversion_module
        _inversion_module()
        from radar_signal import centroid_delay_axes
        if len(shape)==2:
            centroid_delay_axes(np.array([0.]),shape[0],
                row_fast_time_offset_s=data['row_fast_time_offset_s'] if 'row_fast_time_offset_s' in data.files else None,
                centroid_fractional_offset_s=data['centroid_fractional_offset_s'] if 'centroid_fractional_offset_s' in data.files else None)
        # Only small axes and geometry may be materialized. Never load clean_iq.
        keys=('elapsed_s','fast_time_s','scatter_elapsed_s','emit_elapsed_s',
            'coherence_id','tx_range_m','rx_range_m','row_fast_time_offset_s',
            'centroid_fractional_offset_s','common_path_rate_m_s')
        for key in keys:
            if key not in data.files:
                continue
            value=data[key]
            if key!='fast_time_s':
                if value.shape!=(shape[0],):
                    raise ValueError(f'{key}与脉冲数不一致')
                # Preserve the original whole-input fallback for invalid rates.
                if key=='common_path_rate_m_s' and not np.all(np.isfinite(value)):
                    value=np.zeros_like(value)
                value=value[indices]
            fields[key]=value
    if len(shape)==2 and 'elapsed_s' not in fields:
        raise ValueError('缺少脉冲接收时标')
    fields['iq']=read_rows(path,'iq',indices,progress)
    fields['run_id']=np.full(len(indices),run_id,int)
    fields.setdefault('elapsed_s',np.arange(len(indices),dtype=float))
    fields.setdefault('scatter_elapsed_s',fields['elapsed_s'])
    fields.setdefault('coherence_id',np.zeros(len(indices),int))
    with zipfile.ZipFile(path) as archive:
        fields['valid']=(read_rows(path,'valid',indices).astype(bool)
                         if 'valid.npy' in archive.namelist() else np.ones(fields['iq'].shape,bool))
    if fields['valid'].shape not in (fields['iq'].shape,(len(indices),)):
        raise ValueError('valid维度与选定回波不一致')
    if len(shape)==2:
        fast=fields.get('fast_time_s')
        if fast is None or fast.shape!=(shape[1],) or len(fast)<2 or not np.all(np.isfinite(fast)) or np.any(np.diff(fast)<=0):
            raise ValueError('需要有效、递增的完整快时间轴')
        if not np.all(np.isfinite(fields['elapsed_s'])):
            raise ValueError('脉冲接收时标必须有限')
    return SimpleNamespace(**fields),indices


def compressed_run(echo,config,progress=None):
    if echo.iq.size*16>RUN_BYTES:
        raise ValueError('脉压Run输出超过256 MiB；请缩短Run')
    core=_inversion_module()
    source=core._pulse_feature_source(echo,len(echo.iq))
    chunk=min(128,core.bounded_pulse_chunk_size(source,CHUNK_BYTES))
    samples=np.empty(echo.iq.shape,complex)
    for begin in range(0,len(echo.iq),chunk):
        end=min(begin+chunk,len(echo.iq))
        selected=core._echo_pulse_chunk(source,begin,end,len(echo.iq))
        prepared=core.prepare_chirp_pulse_profiles(selected,config,pulse_features_only=True)
        lag=prepared['full_compressed'].shape[1]-echo.iq.shape[1]
        samples[begin:end]=prepared['full_compressed'][:,lag:lag+echo.iq.shape[1]]
        del prepared
        if progress:
            progress(begin+len(selected.iq),len(echo.iq))
    return samples


def matrix_figure(echo,values,kind,run_id,config,mean_power=None):
    return _views().matrix_figure(echo,values,kind,run_id,config,mean_power=mean_power)


def campaign_matrix(source,config,kind,folder,progress=None):
    from .inversion_feature_preview import _load_echo
    echo=_load_echo(source)
    core=_inversion_module();echo=core._pulse_feature_source(echo,len(echo.iq))
    display=[];values=[];total=None;count=0
    runs=np.unique(echo.run_id)
    for number,run in enumerate(runs):
        indices=np.flatnonzero(echo.run_id==run)
        if np.any(np.diff(indices)!=1):raise ValueError('全场概览要求Run脉冲连续存储')
        if len(indices)*echo.iq.shape[1]*max(echo.iq.dtype.itemsize,16)>RUN_BYTES:
            raise ValueError('单Run超过图像读取预算，需要进一步分块显示')
        selected=core._echo_pulse_chunk(echo,int(indices[0]),int(indices[-1])+1,len(echo.iq))
        samples=(selected.iq if kind=='raw' else compression_cache(source,config,folder/f'compression_run_{int(run)}.npz',int(run),selected))
        valid=selected.valid[:,None] if selected.valid.ndim==1 else selected.valid
        power=np.where(valid,np.abs(samples)**2,0.)
        summed=power.sum(axis=0);total=summed if total is None else total+summed;count+=len(samples)
        chosen=np.unique(np.linspace(0,len(samples)-1,min(len(samples),max(2,1000//len(runs))),dtype=int))
        display.extend(indices[chosen]);values.append(np.array(samples[chosen]))
        if progress:progress(int(10+75*(number+1)/len(runs)),f'全场图像 Run {number+1}/{len(runs)}')
    display=np.array(display)
    shown=core._echo_pulse_chunk(echo,0,len(echo.iq),len(echo.iq))
    for name in core._PULSE_ROW_FIELDS:
        value=getattr(shown,name,None)
        if value is not None:setattr(shown,name,value[display])
    shown.display_indices=display
    return matrix_figure(shown,np.concatenate(values),kind,-1,config,mean_power=total/count)


def rd_figure(echo,indices,config,run_id,cpi_index,compressed=None):
    core=_inversion_module()
    from radar_signal import range_doppler_cube,align_profiles_to_common_delay
    prf=float(echo.metadata.get('prf_hz',0))
    duration=float(config.get('cpi_duration_s',0))
    hop_duration=float(config.get('cpi_hop_duration_s') or duration/4)
    if not np.isfinite(prf*duration*hop_duration) or min(prf,duration,hop_duration)<=0:
        raise ValueError('需要有效PRF、CPI和步长')
    count=max(2,int(np.ceil(duration*prf)));hop=max(1,int(np.ceil(hop_duration*prf)))
    valid=np.any(echo.valid,axis=1) if echo.valid.ndim==2 else echo.valid
    windows=[]
    for group in np.unique(echo.coherence_id):
        rows=np.flatnonzero((echo.coherence_id==group)&valid)
        seams=(np.diff(rows)!=1)|(np.diff(indices[rows])!=1)
        for block in np.split(rows,np.flatnonzero(seams)+1):
            for start in range(0,len(block)-count+1,hop):
                windows.append(block[start:start+count])
    if not windows:
        raise ValueError('该Run有效连续相干脉冲不足，无法形成CPI；不跨Run补齐')
    if not 0<=cpi_index<len(windows):
        raise ValueError(f'CPI序号超范围；该Run共{len(windows)}窗')
    # Avoid an unbounded single-CPI spectral allocation.
    full=core._full_correlation_sample_count(echo)
    if count*full*16*6>CPI_BYTES:
        raise ValueError('该CPI超过512 MiB工作区估算预算；请另行规划更大的相干孔径处理')
    source=core._pulse_feature_source(echo,len(echo.iq))
    selection=windows[cpi_index]
    chunk=core._echo_pulse_chunk(source,int(selection[0]),int(selection[-1])+1,len(echo.iq))
    # Use whole selected Run grids, so moving among CPIs does not change axes.
    from radar_signal import centroid_delay_axes
    offsets=centroid_delay_axes(np.array([0.]),len(echo.iq),
        row_fast_time_offset_s=getattr(echo,'row_fast_time_offset_s',None),
        centroid_fractional_offset_s=getattr(echo,'centroid_fractional_offset_s',None))[:,0]
    grid=core._global_delay_grid(echo.fast_time_s,offsets)
    if compressed is None:
        prepared=core.prepare_chirp_pulse_profiles(chunk,config,pulse_features_only=True)
        lag=prepared['full_compressed'].shape[1]-echo.iq.shape[1]
        values=prepared['full_compressed'][:,lag:lag+echo.iq.shape[1]]
    else:
        values=compressed[selection]
    axes=centroid_delay_axes(echo.fast_time_s,len(chunk.iq),
        row_fast_time_offset_s=getattr(chunk,'row_fast_time_offset_s',None),
        centroid_fractional_offset_s=getattr(chunk,'centroid_fractional_offset_s',None))
    times,role=processing_times(chunk,config)
    _,aligned=align_profiles_to_common_delay(values,
        axes,valid=chunk.valid,common_grid=grid,method='fourier')
    cube=range_doppler_cube(aligned,times,chunk.coherence_id,grid[0],
        cpi_pulses=count,cpi_hop_pulses=count,run_id=chunk.run_id,valid=chunk.valid)
    if len(cube.times_s)!=1:
        raise ValueError('选定CPI未形成一个独立谱')
    arrays=dict(times_s=cube.times_s,delays_s=cube.delays_s,range_time_power=cube.power.sum(axis=2),
        rd_power=cube.power,rd_frequencies_hz=cube.frame_frequencies_hz,rd_times_s=cube.times_s,
        cpi_start_pulse=[int(indices[selection[0]])],cpi_end_pulse=[int(indices[selection[-1]])+1])
    figure=_views().processing_figure(arrays)
    for annotation,text in zip(figure.layout.annotations,(
            '选定CPI的距离能量（加窗慢时间FFT功率沿频率求和）',
            '选定CPI的距离—多普勒功率（完整距离列与频率格）')):
        annotation.text=text
    figure.update_xaxes(title_text='选定CPI（悬停查看中心时刻）',row=1,col=1)
    figure.update_layout(title=f'距离—多普勒 · run_id={run_id} · CPI {cpi_index+1}/{len(windows)} · t={cube.times_s[0]:.9g}s<br>{role}；{count}脉冲；当前参数、选定Run网格；公共补偿={config.get("motion_compensation","auto")}')
    return figure


def processing_times(echo,config):
    return _views().processing_times(echo,config)


def compression_cache(source,config,path,run_id,echo=None,progress=None):
    """Reuse the same native cropped compression across matrix and CPI views."""
    key=request_key(source,config,'compression',run_id,0)
    try:
        if cached(source,config,path,'compression',run_id):
            shape,_,dtype=array_header(path,'compressed')
            if np.prod(shape)*dtype.itemsize<=RUN_BYTES:
                with np.load(path,allow_pickle=False) as data:
                    return data['compressed']
    except (OSError,ValueError,KeyError):
        pass
    if echo is None:
        return None
    values=compressed_run(echo,config,progress)
    path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix('.pending.npz')
    try:
        np.savez(pending,compressed=values)
        if request_key(source,config,'compression',run_id,0)!=key:
            raise ValueError('脉压期间回波文件变化')
        pending.replace(path)
        path.with_suffix('.view.json').write_text(json.dumps(key),encoding='utf-8')
    finally:
        pending.unlink(missing_ok=True)
    return values


def request_key(source,config,kind,run_id,cpi_index):
    policy=({k:config.get(k) for k in ('period_time_role',)} if kind=='raw'
            else {k:config.get(k) for k in ('motion_compensation','period_time_role')})
    if kind in ('rd','scientific_features'):
        policy.update({k:config.get(k) for k in ('cpi_duration_s','cpi_hop_duration_s')})
        policy['doppler_estimator']=config.get('doppler_estimator','spectral_moments')
    if kind=='scientific_features':policy=dict(config)
    if kind=='rd':policy['compute_device']=config.get('compute_device','cpu')
    return dict(version=6 if kind=='rd' else 5 if kind=='scientific_features' else 4,source=_views().file_identity(source),kind=kind,run_id=run_id,
                cpi_index=cpi_index if kind=='rd' else None,policy=policy)


def cached(source,config,path,kind,run_id,cpi_index=0):
    try:
        return path.is_file() and json.loads(path.with_suffix('.view.json').read_text(encoding='utf-8'))==request_key(source,config,kind,run_id,cpi_index)
    except (OSError,ValueError):
        return False


def build_view(source,config,path,*,kind,run_id=0,cpi_index=0,progress=None,read_only=False):
    if read_only and kind!='raw':
        return build_saved_view(source,path,kind,run_id,cpi_index,progress)
    if kind=='scientific_features':
        if cached(source,config,path,kind,0,0):return path
        return scientific_features(source,config,path,progress)
    if kind in ('pulse','saved'):
        from .inversion_feature_preview import build_inversion_feature_html
        observables=source.parent.parent/'inversion/period_observables.npz' if kind=='saved' else None
        if observables is not None and not observables.is_file():
            raise ValueError('尚无保存的实际反演特征')
        return build_inversion_feature_html(source,config,path,observables=observables,progress_callback=progress)
    if kind not in ('raw','compression','rd'):
        raise ValueError('未知图像请求')
    key=request_key(source,config,kind,run_id,cpi_index)
    if cached(source,config,path,kind,run_id,cpi_index):
        return path
    if progress:progress(0,'读取周期反演共享阶段；首次需要计算全场中间结果' if kind=='rd' else '读取图像数据；压缩文件首次需要解压')
    if kind=='rd':
        figure=scientific_rd(source,config,run_id,cpi_index,progress)
        def validate_rd():
            if request_key(source,config,kind,run_id,cpi_index)!=key:raise ValueError('绘图期间回波改变')
        _views().write_html_atomic(figure,path,validate=validate_rd,standalone=False)
        path.with_suffix('.view.json').write_text(json.dumps(key),encoding='utf-8')
        return path
    if kind in ('raw','compression') and run_id==-1:
        figure=campaign_matrix(source,config,kind,path.parent,progress)
        def validate_campaign():
            if request_key(source,config,kind,run_id,cpi_index)!=key:raise ValueError('绘图期间回波改变')
        _views().write_html_atomic(figure,path,validate=validate_campaign,standalone=False)
        path.with_suffix('.view.json').write_text(json.dumps(key),encoding='utf-8')
        return path
    echo,indices=load_run(source,run_id,
        lambda done,total: progress(5+int(30*done/total),f'读取Run {done}/{total}') if progress else None)
    if echo.iq.ndim==1:
        if kind!='raw':raise ValueError('此图仅适用Chirp')
        from .echo_preview import _cw_preview_figure
        figure=_cw_preview_figure(echo.elapsed_s,echo.iq,echo.metadata)
        figure.update_layout(title=f'CW原始回波：前{len(echo.iq)}样点诊断段')
    elif kind=='rd':
        if progress:progress(40,'计算选定Run中的独立CPI')
        values=compression_cache(source,config,path.parent/f'compression_run_{run_id}.npz',run_id)
        figure=rd_figure(echo,indices,config,run_id,cpi_index,compressed=values)
    else:
        if kind=='raw':values=echo.iq
        else:
            if echo.iq.size*16>RUN_BYTES:
                raise ValueError('脉压Run输出超过256 MiB；请缩短Run')
            values=compression_cache(source,config,path.parent/f'compression_run_{run_id}.npz',run_id,echo,
                lambda done,total:progress(40+int(45*done/total),f'脉压 {done}/{total}') if progress else None)
        figure=matrix_figure(echo,values,kind,run_id,config)
    def validate():
        if request_key(source,config,kind,run_id,cpi_index)!=key:
            raise ValueError('绘图期间回波文件变化，旧图保持不变')
    if progress:progress(95,'写入完整图像')
    _views().write_html_atomic(figure,path,validate=validate,standalone=False)
    path.with_suffix('.view.json').write_text(json.dumps(key),encoding='utf-8')
    if progress:progress(100,'图像已生成')
    return path


def build_saved_view(source,path,kind,run_id,cpi_index,progress=None):
    context=completed_inversion(source)
    if context is None:raise ValueError('尚无完成的周期反演结果；请先运行周期反演')
    if kind!='saved' and not saved_view_available(source,kind,run_id,cpi_index):
        raise ValueError('缺少与已完成反演一致的保存检查结果；请运行周期反演补齐')
    config=context['config'];before=_views().file_identity(context['folder']/'period_observables.npz')
    requested_cpi=cpi_index
    key=request_key(source,config,kind,run_id,cpi_index) if Path(source).is_file() else None
    if kind=='saved':
        from .inversion_feature_preview import build_inversion_feature_html
        return build_inversion_feature_html(source,config,path,observables=context['folder']/'period_observables.npz')
    _inversion_module()
    if kind in ('pulse','compression'):
        from inspection_store import ready_inspection
        if ready_inspection(source,config) is None:
            from .. import storage
            from .inversion_feature_preview import cached_feature_html
            legacy=storage.PREVIEW_DIR/Path(source).parent.parent.name.replace(' ','_')
            old=legacy/('inversion_features.html' if kind=='pulse' else f'compression_run_{run_id}.html')
            old_identity=_views().file_identity(old)
            text=old.read_text(encoding='utf-8')
            valid=(cached_feature_html(source,config,old) or cached(source,config,old,'pulse',0)) if kind=='pulse' else cached(source,config,old,'compression',run_id)
            if not valid or _views().file_identity(old)!=old_identity or request_key(source,config,kind,run_id,cpi_index)!=key:
                raise ValueError('历史图像来源改变')
            path.parent.mkdir(parents=True,exist_ok=True)
            pending=path.with_suffix('.html.part');pending.write_text(text,encoding='utf-8')
            pending.replace(path)
            path.with_suffix('.view.json').write_text(json.dumps(key),encoding='utf-8')
            return path
    if kind=='pulse':
        from inspection_store import ready_inspection
        folder=ready_inspection(source,config)
        if folder is None:raise ValueError('历史反演未保存逐脉冲检查；请通过运行周期反演补齐，不在看图时计算')
        with np.load(folder/'pulse_observables.npz',allow_pickle=False) as data:
            from .inversion_feature_preview import pulse_feature_figure
            values=data['value'];metadata=json.loads(data['metadata_json'].item())
            features=SimpleNamespace(times_s=data['time_elapsed_s'],total_power=values[:,0],
                centroid_delay_s=values[:,1],energy_width_90_s=values[:,2])
            figure=pulse_feature_figure(features,metadata['time_axis_role'],data['run_id'])
    elif kind=='compression':
        from inspection_store import compression_figure
        figure=compression_figure(source,config,run_id)
    elif kind=='rd':
        from processing_store import identity
        token=SimpleNamespace(_source_identity=identity(source),_processing_store=Path(source).parent/'processing_cache')
        if cpi_index<0:
            catalog=[i for i,_ in cpi_catalog(source,config,run_id) if i>=0 and saved_view_available(source,'rd',run_id,i)]
            if not catalog:raise ValueError('保存结果没有可用CPI频谱')
            cpi_index=catalog[0]
        figure=_cached_scientific_rd(token,config,run_id,cpi_index)
        if figure is None:raise ValueError('保存的CPI频谱缺失；请运行周期反演补齐')
    else:raise ValueError('看图入口不能启动科学特征计算')
    def validate():
        if _views().file_identity(context['folder']/'period_observables.npz')!=before:raise ValueError('绘图期间反演结果改变')
        if key is not None and request_key(source,config,kind,run_id,requested_cpi)!=key:raise ValueError('绘图期间回波改变')
    # Only render saved arrays/figures. No MF, FFT or feature extraction here.
    if progress:progress(95,'渲染已保存的反演检查结果，不进行科学计算')
    _views().write_html_atomic(figure,path,validate=validate,standalone=False)
    if key is not None:path.with_suffix('.view.json').write_text(json.dumps(key),encoding='utf-8')
    return path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--echo',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config-json',required=True);parser.add_argument('--kind',required=True)
    parser.add_argument('--run-id',type=int,default=0);parser.add_argument('--cpi-index',type=int,default=0)
    parser.add_argument('--read-only',action='store_true',default=True)
    args=parser.parse_args()
    def progress(percent,message):
        print('__PROGRESS__ '+json.dumps(dict(percent=percent,message=message)),flush=True)
    try:
        build_view(args.echo,json.loads(args.config_json),args.output,kind=args.kind,
            run_id=args.run_id,cpi_index=args.cpi_index,progress=progress,read_only=args.read_only)
    except Exception as exc:
        print(str(exc),file=sys.stderr,flush=True);return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
