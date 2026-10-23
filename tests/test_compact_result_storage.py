import json
from types import SimpleNamespace
from unittest import mock
import numpy as np
import pytest
from tests.test_gui_schema_v4 import _workspace_tmp
from inversion.src import processing_store as store, result_views as views
from inversion.src.cpi_display import display_arrays,read_display,frame_header


def test_cpi_full_grid_display_precision_boundary_and_legacy():
    with _workspace_tmp('compact_cpi') as folder:
        axis=np.arange(9.)
        for power in (np.zeros((9,8)),np.ones((9,8)),np.geomspace(np.finfo(float).tiny,np.finfo(float).max/16,72).reshape(9,8)):
            expected=views._db(power);values=display_arrays(power)
            # IEEE single rounding bound, including deeply subnormal displays.
            tolerance=np.maximum(abs(expected)*2**-24,np.finfo(np.float32).tiny)
            assert np.all(abs(values['power_db'].astype(float)-expected)<=tolerance)
            np.testing.assert_array_equal(values['range_power'],power.sum(axis=1))
        with pytest.raises(ValueError,match='溢出'):display_arrays(np.full((2,2),np.finfo(float).max))
        power=np.random.default_rng(77).uniform(size=(9,8));source=folder/'echo.npz';np.savez(source,iq=power)
        echo=SimpleNamespace(_source_identity=store.identity(source),_processing_store=folder/'cache',run_id=np.zeros(8,int))
        cube=SimpleNamespace(power=power[None],delays_s=axis,frame_frequencies_hz=np.arange(8.)[None],times_s=np.array([1.]))
        config={'cpi_duration_s':1.,'doppler_estimator':'spectral_moments'}
        store.save_cpi(echo,config,cube,0,0,8);path=store.cpi_folder(echo,config)/'0.npz'
        oldstamp=path.stat().st_mtime_ns
        with np.load(path) as data:
            assert 'power' not in data.files
            assert data['power_db'].shape==power.shape
        store.save_cpi(echo,dict(config,doppler_estimator='narrowband_lag'),cube,0,0,8)
        assert path.stat().st_mtime_ns==oldstamp
        with np.load(path) as data:corrupt={name:data[name] for name in data.files}
        corrupt['format_version']=np.array(999);np.savez_compressed(path,**corrupt)
        store.save_cpi(echo,config,cube,0,0,8)
        assert read_display(path)['format_version']==2
        displayed=read_display(path)
        np.testing.assert_array_equal(displayed['range_power'],power.sum(axis=1))
        with pytest.raises(ValueError,match='预算'):frame_header(path,1)
        store.save_cpi(echo,dict(config,export_full_cpi_power=True),cube,0,0,8)
        with np.load(path) as data:np.testing.assert_array_equal(data['power'],power)
        legacy=folder/'legacy.npz';np.savez_compressed(legacy,power=power,delays_s=axis,frequencies_hz=np.arange(8.),time_s=1.,begin=0,end=8,run_id=0,key='{}')
        np.testing.assert_array_equal(read_display(legacy)['power_db'],views._db(power))


def test_compact_plot_uses_stored_db_without_inverse_conversion():
    power=np.arange(1.,25).reshape(4,6);db=display_arrays(power)['power_db']
    figure=views.processing_figure(dict(times_s=np.array([1.]),delays_s=np.arange(4.),
        range_time_power=power.sum(axis=1)[None],rd_power_db=db[None],rd_frequencies_hz=np.arange(6.)[None],
        rd_times_s=[1.],cpi_start_pulse=[0],cpi_end_pulse=[6]))
    np.testing.assert_array_equal(figure.data[1].z,db)


def test_inspection_compacts_arrays_and_shared_rows_and_restores_legacy():
    from inversion.src.inspection_store import save_compression_figure,load_compression_figure
    import plotly.graph_objects as go
    with _workspace_tmp('compact_inspection') as folder:
        z=np.arange(12.).reshape(3,4)/7;rows=np.array([[0.,0.,1.],[0.,1.,2.],[1.,2.,3.]])
        figure=go.Figure(go.Heatmap(z=z,customdata=np.broadcast_to(rows[:,None,:],(3,4,3))))
        original=figure.to_json();path=folder/'inspection.npz'
        save_compression_figure(path,figure,{})
        assert json.loads(figure.to_json())==json.loads(original)
        with np.load(path) as data:
            assert data['rows_0'].shape==(3,3)
            assert 'customdata' not in json.loads(data['figure_json'].item())['data'][0]
            restored=load_compression_figure(data)
        np.testing.assert_array_equal(restored.data[0].customdata,figure.data[0].customdata)
        np.testing.assert_array_equal(restored.data[0].z,z.astype(np.float32))
        np.savez(path,figure_json=np.array(original))
        with np.load(path) as data:assert json.loads(load_compression_figure(data).to_json())==json.loads(original)


def test_gui_html_shares_local_library_and_default_export_is_standalone():
    import plotly.graph_objects as go
    with _workspace_tmp('shared_plotly') as folder:
        path=folder/'.gui_state/previews/test/view.html';other=path.with_name('second.html')
        views.write_html_atomic(go.Figure(),path,standalone=False)
        library=list((folder/'.gui_state/previews/_assets').glob('*.js'))
        assert len(library)==1
        stamp=library[0].stat().st_mtime_ns
        views.write_html_atomic(go.Figure(),other,standalone=False)
        assert library[0].stat().st_mtime_ns==stamp
        assert '../_assets/plotly-' in path.read_text(encoding='utf-8')
        exported=folder/'export.html';views.write_html_atomic(go.Figure(),exported)
        assert exported.stat().st_size>path.stat().st_size+1000000


def test_cli_default_and_explicit_scientific_export_have_identical_features():
    import os,sys,subprocess
    from pathlib import Path
    from tests.test_inversion_feature_preview import InversionFeaturePreviewTests
    with _workspace_tmp('compact_cli') as folder:
        source=folder/'experiment/echo/echo.npz';InversionFeaturePreviewTests().write_echo(source)
        config=folder/'config.json';config.write_text(json.dumps(dict(cpi_duration_s=1.6,cpi_hop_duration_s=.4,
            period_min_s=1.,period_max_s=3.,period_grid_size=80)),encoding='utf-8')
        root=Path(__file__).parents[1]
        command=[sys.executable,str(root/'inversion/scripts/estimate_period.py'),'--echo',str(source),'--config',str(config)]
        environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',QT_QPA_PLATFORM='offscreen')
        snapshots=[]
        for name,extra in [('default',[]),('explicit',['--export-full-cpi-power'])]:
            out=folder/name
            done=subprocess.run(command+['--output',str(out)]+extra,env=environment,capture_output=True,text=True,encoding='utf-8',errors='replace')
            assert done.returncode==0,done.stdout[-1000:]+done.stderr[-3000:]
            with np.load(out/'period_observables.npz') as data:snapshots.append(data['value'])
            frames=list((source.parent/'processing_cache/cpi').glob('s*/*.npz'));assert frames
            with np.load(frames[0]) as data:assert ('power' in data.files)==bool(extra)
        np.testing.assert_array_equal(snapshots[0],snapshots[1])
        assert not (source.parent/'processing_cache/mapped/iq.npy').exists()
