"""Paired read-only storage-layout probes. Writes only a new evidence folder."""
import argparse,json,sys,time,zipfile,subprocess
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from inversion.src import processing_store as store,result_views as views
from inversion.src.cpi_display import display_arrays,read_display


def frame_figure(path):
    a=read_display(path)
    return views.processing_figure(dict(times_s=np.array([a['time_s']]),delays_s=a['delays_s'],
        range_time_power=a['range_power'][None],rd_power_db=a['power_db'][None],
        rd_frequencies_hz=a['frequencies_hz'][None],rd_times_s=[a['time_s']],
        cpi_start_pulse=[a['begin']],cpi_end_pulse=[a['end']]))


def inspection(source,output):
    import base64
    import plotly.io as pio
    from inversion.src.inspection_store import save_compression_figure,load_compression_figure
    output.mkdir(parents=True,exist_ok=False)
    before=store.identity(source)
    with np.load(source) as data:
        figure=pio.from_json(data['figure_json'].item());key=json.loads(data['key'].item())
    def decode(value):
        if isinstance(value,dict) and 'bdata' in value:
            a=np.frombuffer(base64.b64decode(value['bdata']),dtype=value['dtype']).copy()
            return a.reshape(tuple(int(v.strip()) for v in value['shape'].split(','))) if 'shape' in value else a
        return np.asarray(value)
    for trace in figure.data:
        if trace.type=='heatmap':trace.z=decode(trace.z);trace.customdata=decode(trace.customdata)
    compact=output/'compact.npz';save_compression_figure(compact,figure,key)
    with np.load(compact) as data:restored=load_compression_figure(data)
    a=np.asarray(figure.data[0].z);b=np.asarray(restored.data[0].z)
    np.testing.assert_array_equal(restored.data[0].customdata,figure.data[0].customdata)
    np.testing.assert_array_equal(np.isnan(a),np.isnan(b))
    assert np.all(abs(a[np.isfinite(a)]-b[np.isfinite(a)])<=np.maximum(abs(a[np.isfinite(a)])*2**-24,np.finfo(np.float32).tiny))
    times={'legacy':[],'compact':[]}
    for sequence in [('legacy','compact'),('compact','legacy')]*2:
        for name in sequence:
            start=time.perf_counter()
            with np.load(source if name=='legacy' else compact) as data:load_compression_figure(data)
            times[name].append(time.perf_counter()-start)
    if store.identity(source)!=before:raise ValueError('Source changed')
    report=dict(measured_utc=datetime.now(timezone.utc).isoformat(),source=before,old_bytes=source.stat().st_size,
        new_bytes=compact.stat().st_size,shape=list(a.shape),max_db_error=float(np.nanmax(abs(a-b))),
        row_metadata_exact=True,load_seconds=times)
    (output/'result.json').write_bytes(json.dumps(report,indent=2,allow_nan=False).encode('utf-8'))
    print(json.dumps(report),flush=True)


def run(source,output):
    source=source.resolve();output.mkdir(parents=True,exist_ok=False)
    before=store.identity(source);cache=source.parent/'processing_cache'
    observations=source.parent.parent/'inversion/period_observables.npz'
    with np.load(observations) as data:config=json.loads(data['metadata_json'].item())['inversion_config']
    echo=SimpleNamespace(_source_identity=before,_processing_store=cache)
    folders=store.cpi_folder_candidates(echo,config)
    candidates=[]
    for folder in folders:
        if not folder.is_dir():continue
        paths=sorted(folder.glob('*.npz'),key=lambda p:int(p.stem))
        if not paths:continue
        with np.load(paths[0]) as data:
            if 'power' in data.files and 'power_db' not in data.files and store.cpi_key_matches(json.loads(data['key'].item()),echo,config):
                candidates=paths;break
    if not candidates:raise ValueError('No compatible legacy scientific CPI files for a same-input comparison')
    records=[];switches=[]
    for index in sorted(set((0,len(candidates)//2,len(candidates)-1))):
        old=candidates[index]
        with np.load(old) as data:
            power=data['power'];metadata={name:data[name] for name in data.files if name!='power'}
        compact=output/f'cpi_{index}.npz'
        start=time.perf_counter();np.savez_compressed(compact,**metadata,**display_arrays(power));write=time.perf_counter()-start
        expected=views._db(power);actual=read_display(compact)
        np.testing.assert_array_equal(actual['range_power'],power.sum(axis=1))
        error=float(np.max(abs(actual['power_db'].astype(float)-expected)))
        assert np.all(abs(actual['power_db'].astype(float)-expected)<=np.maximum(abs(expected)*2**-24,np.finfo(np.float32).tiny))
        times={'legacy':[],'compact':[]}
        for order in [('legacy','compact'),('compact','legacy')]*2:
            for name in order:
                start=time.perf_counter();figure=frame_figure(old if name=='legacy' else compact)
                times[name].append(time.perf_counter()-start)
        # First/second publication exercise shared local JS and hover/axis data.
        html={}
        for name,mode in [('legacy',True),('compact',False)]:
            view=output/f'{name}_{index}.html';start=time.perf_counter()
            views.write_html_atomic(frame_figure(old if name=='legacy' else compact),view,standalone=mode)
            html[name]=dict(seconds=time.perf_counter()-start,bytes=view.stat().st_size)
        restart={}
        for name,path in [('legacy',old),('compact',compact)]:
            completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker',str(path)],capture_output=True,text=True,check=True)
            restart[name]=json.loads(completed.stdout)
        records.append(dict(index=index,legacy_source=store.identity(old),shape=list(power.shape),
            old_bytes=old.stat().st_size,new_bytes=compact.stat().st_size,max_display_error_db=error,
            range_power_exact=True,compact_write_s=write,figure_seconds=times,html=html,fresh_process=restart))
        switches.append((old,compact))
    # Actual stage snapshot, preserving independent legacy arrays as baseline.
    stagefile=cache/'observations.npz'
    stage=store.load_stage(echo,config)
    stage_record=None
    if stage is not None:
        if stage.get('profiles') is not stage.get('dynamic_spectrum'):
            # Legacy files deserialize equal distinct objects; producer's CPI
            # contract assigns profiles=dynamic. Reuse only after exact equality.
            for name in ('dynamic','dynamic_spectrum'):
                if name in stage and hasattr(stage.get('profiles'),'spectrum'):
                    other=stage[name]
                    if hasattr(other,'spectrum'):
                        np.testing.assert_array_equal(stage['profiles'].spectrum,other.spectrum)
                        stage['profiles']=other;break
        token=SimpleNamespace(_source_identity=before,_processing_store=output/'stage')
        start=time.perf_counter();store.save_stage(token,config,stage);seconds=time.perf_counter()-start
        loaded=store.load_stage(token,config)
        for name in ('features',):
            if name in stage:
                for field in vars(stage[name]):
                    a=getattr(stage[name],field);b=getattr(loaded[name],field)
                    if isinstance(a,np.ndarray):np.testing.assert_array_equal(a,b)
        stage_record=dict(old_bytes=stagefile.stat().st_size,new_bytes=(output/'stage/observations.npz').stat().st_size,
            write_s=seconds,scientific_features_exact=True)
    # Three actual row blocks: stored-member mapping vs existing extracted mmap.
    from inversion.src.npz_mapping import try_map_npz_member
    mapped=try_map_npz_member(source,'iq');extracted=cache/'mapped/iq.npy';mapping=[]
    if mapped is not None and extracted.is_file():
        old=np.load(extracted,mmap_mode='r');n=len(mapped)
        for begin in (0,n//2,n-100):
            a=np.array(mapped[begin:begin+100]);b=np.array(old[begin:begin+100]);np.testing.assert_array_equal(a,b)
            times={'direct':[],'extracted':[]}
            for order in [('direct','extracted'),('extracted','direct')]*3:
                for name in order:
                    start=time.perf_counter();value=np.array((mapped if name=='direct' else old)[begin:begin+100]);times[name].append(time.perf_counter()-start)
            mapping.append(dict(begin=begin,seconds=times,exact=True))
        old._mmap.close()
    if mapped is not None:mapped._mmap.close()
    if store.identity(source)!=before:raise ValueError('Source changed during benchmark')
    result=dict(measured_utc=datetime.now(timezone.utc).isoformat(),source=before,
        scope='Same-session actual first/middle/last CPI; warm ABBA figure construction and isolated-process first read, not OS-cold disk or native browser render',
        cpi=records,stage=stage_record,mapping=mapping)
    (output/'result.json').write_bytes(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
    print(json.dumps(result,ensure_ascii=False),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--output',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--inspection',type=Path)
    args=p.parse_args()
    if args.worker:
        start=time.perf_counter();frame_figure(args.worker);print(json.dumps(dict(figure_seconds=time.perf_counter()-start)))
    elif args.inspection and args.output:inspection(args.inspection,args.output)
    elif args.source and args.output:run(args.source,args.output)
    else:p.error('source and fresh output required')


if __name__=='__main__':main()
