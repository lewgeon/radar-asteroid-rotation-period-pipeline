import unittest
from unittest import mock
import numpy as np
from tests.test_gui_schema_v4 import _workspace_tmp
from tests import test_inversion_feature_preview as fixtures


class ResultWorkflowTests(unittest.TestCase):
    def test_direct_v1_html_replaces_only_upgrade_script(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('boundary_v1_upgrade') as scratch:
            path=scratch/'old.html'
            payload='<script>const ORIGINAL_PAYLOAD=123;</script>'
            path.write_text('<html><body>'+payload+'<script data-run-boundary-toggle>OLD_SENTINEL</script></body></html>',encoding='utf-8')
            service._views().ensure_responsive_html(path)
            text=path.read_text(encoding='utf-8')
            assert payload in text
            assert 'OLD_SENTINEL' not in text
            self.assertEqual(text.count('<script data-run-boundary-toggle="2">'),1)
            service._views().ensure_responsive_html(path)
            self.assertEqual(path.read_text(encoding='utf-8'),text)
    def test_legacy_toggle_script_executes_and_excludes_named_and_partial_markers(self):
        import json,re,shutil,subprocess
        from rotation_gui.window import result_service as service
        if shutil.which('node') is None:self.skipTest('Node runtime unavailable')
        with _workspace_tmp('boundary_js') as scratch:
            path=scratch/'old.html';path.write_text('<html><body></body></html>',encoding='utf-8')
            service._views().ensure_responsive_html(path)
            script=re.search(r'<script data-run-boundary-toggle="2">(.*?)</script>',path.read_text(encoding='utf-8'),re.S)[1]
            runner=r"""const vm=require('vm'),assert=require('assert');
const legacy={type:'line',xref:'x domain',yref:'y',x0:0,x1:1,y0:39.5,y1:39.5,line:{color:'#96a3b5'}};
const graph={dataset:{},on:(name,fn)=>graph.listener=fn,layout:{title:{text:'原始回波 · 全观测区间'},shapes:[legacy,{...legacy,name:'other-marker'},{...legacy,x0:.1,x1:.3}],updatemenus:[{buttons:[{label:'信号范围'},{label:'完整记录范围'}]},{buttons:[{label:'显示/隐藏Run分隔线'}],x:1,xanchor:'right'}]}};
let calls=0;const context={window:{},document:{querySelectorAll:()=>[graph]},Plotly:{relayout:(p,u)=>{calls++;if(u.updatemenus)p.layout.updatemenus=u.updatemenus;for(const [key,value] of Object.entries(u)){const match=key.match(/^shapes\[(\d+)\]\.visible$/);if(match)p.layout.shapes[+match[1]].visible=value;}}}};
context.window.Plotly=context.Plotly;context.window.addEventListener=()=>{};
vm.runInNewContext(SCRIPT,context);
const menu=graph.layout.updatemenus[0];assert.strictEqual(menu.active,-1);assert.strictEqual(menu.x,0);assert.strictEqual(menu.xanchor,'left');
assert.strictEqual(graph.layout.updatemenus.length,1);const button=menu.buttons[2];
assert.strictEqual(JSON.stringify(button.args[0]),JSON.stringify({'shapes[0].visible':false}));
assert.strictEqual(JSON.stringify(button.args2[0]),JSON.stringify({'shapes[0].visible':true}));
graph.listener({button});assert.strictEqual(graph.layout.shapes[0].visible,false);
graph.listener({button:menu.buttons[0]});graph.listener({button});assert.strictEqual(graph.layout.shapes[0].visible,true);
assert.strictEqual(graph.layout.shapes[1].visible,undefined);assert.strictEqual(graph.layout.shapes[2].visible,undefined);
vm.runInNewContext(SCRIPT,context);assert.strictEqual(calls,3);console.log('Client upgrade and hide-range-show script passed');
""".replace('SCRIPT',json.dumps(script))
            result=subprocess.run([shutil.which('node'),'-e',runner],capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_historical_html_toggle_upgrade_is_idempotent_and_preserves_payload(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('boundary_old_html') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo,_=service.load_run(source,0);echo.run_id=np.repeat([0,1],40)
            figure=service.matrix_figure(echo,echo.iq,'raw',-1,{})
            figure.update_layout(updatemenus=list(figure.layout.updatemenus)[:1])
            figure.layout.shapes[0].name=None
            path=scratch/'old.html';service._views().write_html_atomic(figure,path)
            original=path.read_text(encoding='utf-8').split('</body>')[0]
            service._views().ensure_responsive_html(path)
            text=path.read_text(encoding='utf-8')
            self.assertTrue(text.startswith(original))
            self.assertIn('data-run-boundary-toggle',text)
            assert 'group.active=-1' in text
            self.assertIn('shapes[${i}].visible',text)
            service._views().ensure_responsive_html(path)
            self.assertEqual(path.read_text(encoding='utf-8'),text)
    def test_existing_cpi_view_does_not_reload_whole_scientific_stage(self):
        from rotation_gui.window import result_service as service
        from rotation_gui.window import inversion_feature_preview as preview
        with _workspace_tmp('cpi_fast_hit') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            config=dict(cpi_duration_s=1.6,cpi_hop_duration_s=.4)
            first=service.scientific_rd(source,config,0,0)
            with mock.patch.object(preview,'_load_echo',side_effect=AssertionError('whole echo/stage loaded')):
                second=service.scientific_rd(source,config,0,1)
                automatic=service.scientific_rd(source,config,0,-1)
            self.assertIn('[4,20)',second.layout.title.text)
            np.testing.assert_array_equal(first.data[1].z,automatic.data[1].z)

    def test_run_boundaries_are_toggleable_without_changing_other_shapes(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('boundary_toggle') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo,_=service.load_run(source,0);echo.run_id=np.repeat([0,1],40)
            for kind in ('raw','compression'):
                figure=service.matrix_figure(echo,echo.iq,kind,-1,{})
                figure.add_shape(type='line',x0=0,x1=1,y0=0,y1=1,name='unrelated-marker')
                menu=next(menu for menu in figure.layout.updatemenus
                    if any(button.label=='显示/隐藏Run分隔线' for button in menu.buttons))
                button=next(button for button in menu.buttons if button.label=='显示/隐藏Run分隔线')
                self.assertEqual(menu.active,-1)
                self.assertEqual(button.method,'skip')
                self.assertIn('shapes[0].visible',button.args[0])
                self.assertFalse(button.args[0]['shapes[0].visible'])
                self.assertTrue(button.args2[0]['shapes[0].visible'])
                self.assertNotIn('shapes[1].visible',button.args[0])

    def test_fast_cpi_rejects_wrong_run_and_invalidates_changed_policy(self):
        from rotation_gui.window import result_service as service
        from rotation_gui.window import inversion_feature_preview as preview
        with _workspace_tmp('cpi_fast_guards') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            config=dict(cpi_duration_s=1.6,cpi_hop_duration_s=.4)
            service.scientific_rd(source,config,0,0)
            with self.assertRaisesRegex(ValueError,'重新选择'):
                service.scientific_rd(source,config,99,0)
            with mock.patch.object(preview,'_load_echo',side_effect=AssertionError('cold path')):
                # Estimators change scientific features, not this saved FFT grid.
                reused=service.scientific_rd(source,dict(config,doppler_estimator='narrowband_lag'),0,0)
                self.assertEqual(reused.data[1].z.shape,(len(reused.data[1].y),len(reused.data[1].x)))
                with self.assertRaisesRegex(AssertionError,'cold path'):
                    service.scientific_rd(source,dict(config,cpi_duration_s=.8),0,0)
                source.touch()
                with self.assertRaisesRegex(AssertionError,'cold path'):
                    service.scientific_rd(source,config,0,0)
    def test_first_cpi_request_for_later_run_and_actual_invalid_windows(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('later_run') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            with np.load(source) as data:values={key:data[key] for key in data.files}
            values['run_id']=np.repeat([0,1],40);values['valid'][:3]=False
            np.savez(source,**values)
            config=dict(cpi_duration_s=.8,cpi_hop_duration_s=.4)
            self.assertEqual(service.cpi_catalog(source,config,1)[0][0],-1)
            figure=service.scientific_rd(source,config,1,-1)
            self.assertIn('Run 2',figure.layout.title.text)
            self.assertIn('[40,48)',figure.layout.title.text)
            actual=service.cpi_catalog(source,config,0)
            self.assertIn('[3,11)',actual[0][1])

    def test_fallback_stage_and_source_change_and_corrupt_cache(self):
        from rotation_gui.window.inversion_feature_preview import _load_echo,_inversion_module
        with _workspace_tmp('fallback_cache') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            core=_inversion_module();config=dict(cpi_duration_s=9.)
            echo=_load_echo(source);original=core.prepare_chirp_observations(echo,config)
            with mock.patch.object(core,'prepare_chirp_pulse_profiles',side_effect=AssertionError('duplicate')):
                reused=core.prepare_chirp_observations(echo,config)
                np.testing.assert_array_equal(original['features'].total_power,reused['features'].total_power)
            (echo._processing_store/'observations.npz').write_bytes(b'corrupt')
            with mock.patch.object(core,'prepare_chirp_pulse_profiles',side_effect=AssertionError('recompute')):
                with self.assertRaisesRegex(AssertionError,'recompute'):core.prepare_chirp_observations(echo,config)
            source.touch()
            with self.assertRaisesRegex(ValueError,'重新加载'):
                core.prepare_chirp_observations(echo,config)

    def test_shared_stage_reused_by_search_without_fft_and_config_changes_invalidate(self):
        from rotation_gui.window import result_service as service
        from rotation_gui.window.inversion_feature_preview import _load_echo
        with _workspace_tmp('shared_stage') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo=_load_echo(source);core=service._inversion_module()
            config=dict(cpi_duration_s=1.6,cpi_hop_duration_s=.4,motion_compensation='auto',
                period_min_s=1.,period_max_s=3.,period_grid_size=80)
            # No store: independent current scientific reference.
            del echo._processing_store
            reference=core.estimate_rotation(echo,config)
            echo=_load_echo(source)
            service.scientific_rd(source,config,0,0)
            with mock.patch.object(core,'prepare_chirp_pulse_profiles',side_effect=AssertionError('duplicate FFT')):
                reused=core.estimate_rotation(echo,config)
                edited=core.estimate_rotation(echo,dict(config,period_grid_size=90))
                self.assertEqual(len(edited.periods['total_power'].grid_periods_s),90)
                with self.assertRaisesRegex(AssertionError,'duplicate FFT'):
                    core.estimate_rotation(echo,dict(config,cpi_duration_s=.8))
            for field in reference.features.__dataclass_fields__:
                np.testing.assert_array_equal(getattr(reference.features,field),getattr(reused.features,field))
            for name in reference.periods:
                np.testing.assert_array_equal(reference.periods[name].grid_scores,reused.periods[name].grid_scores)

    def test_campaign_plot_preserves_run_order_and_mean(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('campaign_plot') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            with np.load(source) as data:values={key:data[key] for key in data.files}
            values['run_id']=np.repeat([0,1],40);np.savez(source,**values)
            figure=service.campaign_matrix(source,{},'raw',scratch)
            run_ids=np.asarray(figure.data[0].customdata)[:,0,0]
            self.assertEqual(set(run_ids),{0,1})
            self.assertEqual(len(figure.layout.shapes),1)
            self.assertTrue(np.all(np.diff(run_ids)>=0))

    def test_export_uses_viewport(self):
        from inversion.src.result_views import write_html_atomic,ensure_responsive_html
        import plotly.graph_objects as go
        with _workspace_tmp('responsive') as scratch:
            path=write_html_atomic(go.Figure(go.Scatter(x=[1,2],y=[3,4])),scratch/'figure.html')
            text=path.read_text(encoding='utf-8')
            self.assertIn('height:100vh',text)
            self.assertIn('window.addEventListener',text)
            legacy=scratch/'legacy.html';legacy.write_text('<html><body>old saved plot</body></html>',encoding='utf-8')
            ensure_responsive_html(legacy)
            first=legacy.read_text(encoding='utf-8')
            self.assertIn('data-viewport-layout',first)
            ensure_responsive_html(legacy)
            self.assertEqual(first,legacy.read_text(encoding='utf-8'))
    def test_pulse_reader_does_not_allocate_campaign_arrays(self):
        from rotation_gui.window import inversion_feature_preview as preview
        with _workspace_tmp('mapped_reader') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            original=np.lib.npyio.NpzFile.__getitem__
            def guarded(data,key):
                if key in ('iq','clean_iq','valid'):raise MemoryError('campaign allocation sentinel')
                return original(data,key)
            with mock.patch.object(np.lib.npyio.NpzFile,'__getitem__',guarded):
                echo=preview._load_echo(source)
            self.assertTrue(isinstance(echo.iq.base,np.memmap) or isinstance(echo.iq,np.memmap))

    def test_matrix_fast_time_horizontal_and_synchronised_zoom(self):
        from rotation_gui.window import result_service as service
        with _workspace_tmp('matrix_axes') as scratch:
            source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
            echo,_=service.load_run(source,0)
            figure=service.matrix_figure(echo,echo.iq,'compression',0,{})
            self.assertIn('延迟',figure.layout.xaxis.title.text)
            self.assertEqual(figure.layout.xaxis.matches,'x2')
            self.assertEqual(np.shape(figure.data[0].z)[0],len(echo.iq))
