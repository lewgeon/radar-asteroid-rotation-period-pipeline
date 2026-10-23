import unittest
import numpy as np
from unittest import mock
from types import SimpleNamespace
from tests.test_gui_schema_v4 import _workspace_tmp
from rotation_gui.qt_compat import QApplication
from rotation_gui import storage
from rotation_gui.window.main import PipelineWindow


class ResultDiagnosticsTests(unittest.TestCase):
    def test_popup_escape_outside_click_and_buttons_stay_inside(self):
        from rotation_gui.qt_compat import Qt,QPushButton
        try:
            from PySide6.QtTest import QTest
        except ImportError:
            from PyQt6.QtTest import QTest
        app=QApplication.instance() or QApplication([])
        with _workspace_tmp('popup_events') as scratch,mock.patch.object(storage,'STATE_PATH',scratch/'session.json'):
            window=PipelineWindow();window.show();app.processEvents()
            window._open_result_dialog();app.processEvents()
            popup=window._result_popup
            rects=[b.geometry() for b in popup.findChildren(QPushButton)]
            self.assertEqual(len(rects),8)
            self.assertTrue(all(popup.rect().contains(rect) for rect in rects))
            self.assertTrue(all(not a.intersects(b) for i,a in enumerate(rects) for b in rects[i+1:]))
            QTest.keyClick(popup,Qt.Key.Key_Escape);app.processEvents()
            self.assertFalse(popup.isVisible())
            window._open_result_dialog();app.processEvents()
            combo=window.result_run_combo
            combo.clear()
            for run in range(100):combo.addItem(f'Run {run}',run)
            combo.showPopup();app.processEvents()
            view=combo.view();index=combo.model().index(99,0)
            view.scrollTo(index);app.processEvents()
            point=view.visualRect(index).center()
            QTest.mouseClick(view.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
            self.assertEqual(combo.currentData(),99)
            self.assertTrue(window._result_popup.isVisible())
            QTest.mouseClick(window,Qt.MouseButton.LeftButton,pos=window.rect().topLeft());app.processEvents()
            self.assertFalse(window._result_popup.isVisible())
            from rotation_gui.window.main import ResultPopup
            from rotation_gui.qt_compat import QComboBox,QVBoxLayout
            small=ResultPopup(window);layout=QVBoxLayout(small);combo=QComboBox(small)
            layout.addWidget(combo);combo.addItems([str(i) for i in range(100)])
            small.move(200,200);small.show();app.processEvents();combo.showPopup();app.processEvents()
            view=combo.view();index=combo.model().index(8,0);view.scrollTo(index);app.processEvents()
            point=view.visualRect(index).center()
            self.assertFalse(small.rect().contains(small.mapFromGlobal(view.viewport().mapToGlobal(point))))
            QTest.mouseClick(view.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents()
            self.assertEqual(combo.currentIndex(),8)
            self.assertTrue(small.isVisible())
            small.hide()
            window.close()

    def test_repeated_dialog_close_does_not_accumulate_children(self):
        from rotation_gui.qt_compat import QFrame,QEvent
        app=QApplication.instance() or QApplication([])
        with _workspace_tmp('diagnostic_lifetime') as scratch,mock.patch.object(storage,'STATE_PATH',scratch/'session.json'):
            window=PipelineWindow()
            for _ in range(3):
                window._open_result_dialog()
                app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                app.processEvents()
                self.assertEqual(sum(d.objectName()=='resultPopup' for d in window.findChildren(QFrame)),1)
                window._result_popup.hide()
            window.close()

    def test_rd_roi_buttons_and_zero_power(self):
        from inversion.src.result_views import processing_figure
        arrays=dict(times_s=np.array([0.,10000.]),delays_s=np.arange(20)*1e-9,
            range_time_power=np.ones((2,20)),rd_power=np.ones((2,20,3)),
            rd_frequencies_hz=np.array([[-1,0,1],[-2,0,2]]),rd_times_s=[0,10000],
            cpi_start_pulse=[0,100],cpi_end_pulse=[100,200])
        fig=processing_figure(arrays)
        self.assertEqual(fig.layout.yaxis.range,fig.layout.yaxis2.range)
        buttons=fig.layout.updatemenus[0].buttons
        self.assertIn('yaxis2.range',buttons[0].args[0])
        self.assertTrue(buttons[1].args[0]['yaxis2.autorange'])
        arrays['range_time_power']*=0;arrays['rd_power']*=0
        zero=processing_figure(arrays)
        self.assertTrue(np.all(np.isfinite(np.asarray(zero.data[0].z))))
    def test_processing_uses_frame_index_and_focuses_signal_without_dropping_data(self):
        from inversion.src.result_views import processing_figure
        delays=np.arange(100)*1e-9
        power=np.zeros((4,100));power[:,20:24]=1
        fig=processing_figure(dict(times_s=np.array([0.,1.,10000.,10001.]),delays_s=delays,range_time_power=power))
        np.testing.assert_array_equal(fig.data[0].x,np.arange(4))
        self.assertEqual(np.shape(fig.data[0].z),(100,4))
        self.assertLess(fig.layout.yaxis.range[1]-fig.layout.yaxis.range[0],20.)
        np.testing.assert_array_equal(np.asarray(fig.data[0].customdata)[0],[0.,1.,10000.,10001.])

    def test_pulse_lines_never_bridge_runs(self):
        from rotation_gui.window import inversion_feature_preview as p
        f=SimpleNamespace(times_s=np.array([0.,1.,100.,101.]), total_power=np.ones(4),
            centroid_delay_s=np.ones(4),energy_width_90_s=np.ones(4))
        with mock.patch.object(p,'_pulse_features',return_value=(f,'scatter_elapsed_s',np.array([0,0,1,1]))):
            fig=p.build_inversion_feature_figure(None,{})
        self.assertTrue(all(t.mode=='lines+markers' and not t.connectgaps for t in fig.data))
        for trace in fig.data:
            self.assertTrue(np.isnan(np.asarray(trace.x)[2]))

    def test_result_control_is_a_panel_and_does_not_duplicate_features(self):
        QApplication.instance() or QApplication([])
        with _workspace_tmp('diagnostic_panel') as scratch, mock.patch.object(storage,'STATE_PATH',scratch/'session.json'):
            window=PipelineWindow()
            self.assertIsNone(window.result_btn.menu())
            panel=window._build_result_dialog()
            from rotation_gui.qt_compat import QPushButton
            labels=[b.text() for b in panel.findChildren(QPushButton)]
            self.assertEqual(set(labels), {'原始回波','脉冲压缩','实际反演特征','逐脉冲检查','距离—多普勒','周期搜索','融合诊断','误差诊断'})
            self.assertEqual(len(labels),8)
            self.assertFalse(any('关闭' in label for label in labels))
            panel.close();window.close()
