"""Exercise Plotly's actual HTML buttons in a browser engine."""
import os,time,json,threading,functools
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS','--disable-gpu --no-sandbox')
import pytest
from tests.test_gui_schema_v4 import _workspace_tmp
from tests import test_inversion_feature_preview as fixtures


@pytest.mark.skipif(os.environ.get('RUN_WEBENGINE_TESTS')!='1',reason='Optional browser-engine test; enable only with a working Qt WebEngine runtime')
def test_run_separator_html_real_clicks_preserve_zoom_and_other_shapes():
    widgets=pytest.importorskip('PySide6.QtWebEngineWidgets')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QUrl
    from rotation_gui.window import result_service as service
    import numpy as np
    app=QApplication.instance() or QApplication([])
    def wait(predicate,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if predicate():return
            time.sleep(.01)
        raise AssertionError('Browser did not reach expected state')
    with _workspace_tmp('boundary_browser') as scratch:
        source=scratch/'echo.npz';fixtures.InversionFeaturePreviewTests().write_echo(source)
        echo,_=service.load_run(source,0);echo.run_id=np.repeat([0,1],40)
        figure=service.matrix_figure(echo,echo.iq,'compression',-1,{})
        figure.add_shape(type='line',x0=0,x1=1,y0=0,y1=1,name='unrelated-marker')
        service._views().write_html_atomic(figure,scratch/'new.html')
        # Historical HTML: same numeric data, no toggle or tagged shapes.
        historical=figure.to_dict();historical['layout']['updatemenus']=historical['layout']['updatemenus'][:1]
        historical['layout']['shapes'][0].pop('name')
        import plotly.graph_objects as go
        service._views().write_html_atomic(go.Figure(historical),scratch/'old.html')
        service._views().ensure_responsive_html(scratch/'old.html')
        unchanged=(scratch/'old.html').read_bytes();service._views().ensure_responsive_html(scratch/'old.html')
        assert (scratch/'old.html').read_bytes()==unchanged
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(scratch)))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        view=widgets.QWebEngineView();view.resize(1100,750);view.show()
        def javascript(code):
            output=[];view.page().runJavaScript(code,lambda value:output.append(value));wait(lambda:bool(output))
            return output[0]
        try:
            for name in ('new','old'):
                loaded=[];view.loadFinished.connect(loaded.append)
                view.load(QUrl(f'http://127.0.0.1:{server.server_port}/{name}.html'))
                wait(lambda:bool(loaded));assert loaded[-1]
                wait(lambda:javascript("!!document.querySelector('.plotly-graph-div')?.layout?.shapes?.length"))
                javascript("Plotly.relayout(document.querySelector('.plotly-graph-div'),{'xaxis.range':[0,50],'xaxis2.range':[0,50]});'ok'")
                def state():
                    return json.loads(javascript("JSON.stringify((()=>{let p=document.querySelector('.plotly-graph-div');return {shapes:p.layout.shapes.map(s=>s.visible!==false),zoom:p.layout.xaxis.range,zoom2:p.layout.xaxis2.range};})())"))
                before=state();assert before['shapes']==[True,True]
                click="[...document.querySelectorAll('.updatemenu-button')].find(b=>b.textContent.includes('显示/隐藏Run分隔线')).dispatchEvent(new MouseEvent('click',{bubbles:true}));'clicked'"
                javascript(click);wait(lambda:not state()['shapes'][0])
                hidden=state();assert hidden['shapes']==[False,True]
                assert hidden['zoom']==before['zoom'] and hidden['zoom2']==before['zoom2']
                view.grab().save(str(scratch/f'{name}_hidden.png'))
                javascript(click);wait(lambda:state()['shapes'][0]);assert state()==before
                view.grab().save(str(scratch/f'{name}_shown.png'))
                view.loadFinished.disconnect(loaded.append)
        finally:
            view.close();view.deleteLater();app.processEvents();server.shutdown();server.server_close();thread.join(timeout=2)
