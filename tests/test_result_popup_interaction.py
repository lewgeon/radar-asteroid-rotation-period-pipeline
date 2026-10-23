import threading
import sys
from pathlib import Path
import pytest
from unittest import mock

from PySide6.QtTest import QTest
from rotation_gui.qt_compat import QApplication, Qt
from rotation_gui import storage
from rotation_gui.window.main import PipelineWindow
from rotation_gui.window import result_service
from tests.test_gui_schema_v4 import _workspace_tmp
from tests import test_inversion_feature_preview as fixtures


@pytest.fixture(autouse=True)
def no_swallowed_qt_slot_exception(monkeypatch):
    errors=[]
    monkeypatch.setattr(sys,'excepthook',lambda *error:errors.append(error))
    yield
    assert not errors,errors


def pump(app):
    for _ in range(15):app.processEvents()


def test_button_second_click_closes_instead_of_recreating():
    app=QApplication.instance() or QApplication([])
    with _workspace_tmp('popup_toggle') as scratch, mock.patch.object(storage,'STATE_PATH',scratch/'state.json'):
        window=PipelineWindow()
        window.show()
        pump(app)
        try:
            window.result_btn.click()
            pump(app)
            popup=window._result_popup
            assert popup.isVisible()
            window.result_btn.click()
            pump(app)
            assert not window._result_popup.isVisible()
            window.result_btn.click()
            pump(app)
            assert window._result_popup.isVisible()
            QTest.mouseClick(window.result_btn,Qt.MouseButton.LeftButton)
            pump(app)
            assert not window._result_popup.isVisible()
        finally:
            window.close()
            pump(app)


def test_menu_status_io_never_runs_on_gui_thread():
    app=QApplication.instance() or QApplication([])
    with _workspace_tmp('popup_background') as scratch, mock.patch.object(storage,'STATE_PATH',scratch/'state.json'):
        source=scratch/'experiment/echo/echo.npz'
        source.parent.mkdir(parents=True)
        fixtures.InversionFeaturePreviewTests().write_echo(source)
        fixtures.write_completed_fixture(source,config={'cpi_duration_s':1.},with_inspections=True)
        window=PipelineWindow()
        window.runs_dir_edit.setText(str(scratch))
        window.run_name_edit.setText('experiment')
        window.show()
        pump(app)
        main_thread=threading.get_ident()
        original=result_service.run_catalog
        calls=[]
        def catalog(*args):
            calls.append(threading.get_ident())
            assert threading.get_ident()!=main_thread, 'result catalog blocks GUI thread'
            return original(*args)
        try:
            with mock.patch.object(result_service,'run_catalog',side_effect=catalog):
                window.result_btn.click()
                assert window._result_popup.isVisible()
                for _ in range(100):
                    QTest.qWait(10)
                    if calls and window.result_run_combo.currentData() is not None:break
                assert calls and main_thread not in calls
                assert window.result_run_combo.count()>0
        finally:
            window.close()
            pump(app)


def test_popup_paints_and_closes_while_background_status_is_blocked():
    app=QApplication.instance() or QApplication([])
    from PySide6.QtCore import QTimer
    gate=threading.Event()
    entered=threading.Event()
    with _workspace_tmp('popup_pending') as scratch, mock.patch.object(storage,'STATE_PATH',scratch/'state.json'):
        window=PipelineWindow();window.show();pump(app)
        main_thread=threading.get_ident()
        original_is_file=Path.is_file
        def stat(path):
            if path.name=='echo.npz' and threading.get_ident()==main_thread:
                raise AssertionError('echo status stat ran on GUI thread')
            return original_is_file(path)
        def blocked(*_):
            entered.set();gate.wait(5)
            return dict(chirp=False,runs=[],cpis=[],available={},context=None,
                        error='无有效回波',run_id=None,cpi_index=None,source_exists=False)
        try:
            with mock.patch.object(result_service,'result_menu_snapshot',side_effect=blocked), mock.patch.object(Path,'is_file',stat):
                beats=[]
                QTimer.singleShot(0,lambda:beats.append(True))
                window.result_btn.click();pump(app)
                assert window._result_popup.isVisible() and beats
                assert entered.wait(.2)
                QTest.keyClick(window._result_popup,Qt.Key.Key_Escape)
                pump(app)
                assert not window._result_popup.isVisible()
                window.result_btn.click();pump(app)
                assert window._result_popup.isVisible()
                # Outside click must still dismiss while the first worker runs.
                QTest.mouseClick(window.run_name_edit,Qt.MouseButton.LeftButton)
                pump(app)
                assert not window._result_popup.isVisible()
                window.result_btn.click();pump(app)
                assert window._result_popup.isVisible()
                window.close();pump(app)
                assert not window._result_popup.isVisible()
        finally:
            gate.set()
            window.close()
            pump(app)
