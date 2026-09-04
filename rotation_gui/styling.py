"""Application-wide visual theme and native style configuration."""

from __future__ import annotations

from . import storage
from .qt_compat import QStyleFactory, Qt

GUI_STYLE = """
QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 13px; color: #25354a; }
QMainWindow { background: #f3f5f8; }
QGroupBox { border: 1px solid #dce2eb; border-radius: 8px;
    margin-top: 12px; padding-top: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QScrollArea { border: none; background: transparent; }
QWidget#parameterCanvas, QWidget#parameterCards { background: #f3f5f8; }
QFrame#parameterCard { background: white; border: 1px solid #dce2eb; border-radius: 8px; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; color: #193b61;
    background: #eff5fc; border: none; border-left: 3px solid #3979bf;
    border-radius: 3px; padding: 4px 9px; }
QLabel#subsectionTitle { font-size: 13px; font-weight: 400; color: #25354a; }
QFrame#subsectionRail { background: transparent; border: none;
    border-left: 2px solid #d4dfeb; border-radius: 0; }
QLineEdit, QComboBox { background: white; border: 1px solid #cbd5e1;
    border-radius: 5px; padding: 0 8px; min-height: 30px; selection-background-color: #d9e9fb; }
QLineEdit:focus, QComboBox:focus { border-color: #3979bf; }
QComboBox { padding-right: 24px; combobox-popup: 0; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #9bafc5;
    selection-background-color: #dbeafb; selection-color: #193b61; outline: 0; }
QWidget#unitValue { background: white; border: 1px solid #cbd5e1; border-radius: 5px; }
QWidget#unitValue QLineEdit { border: none; background: transparent; min-height: 0; }
QWidget#unitValue QLineEdit:focus { background: #edf5ff; }
QWidget#unitValue QLabel#unitSuffix, QWidget#unitValue QComboBox#unitSuffix {
    background: #f0f4f8; color: #526882; border: none; border-left: 1px solid #dce2eb;
    border-radius: 0; min-height: 0; padding: 0 6px; font-size: 12px; }
QWidget#unitValue QComboBox#unitSuffix { padding-right: 16px; }
QWidget#unitValue QComboBox#unitSuffix::drop-down { width: 16px; }
QLabel#componentLabel { color: #60738c; font-size: 12px; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 5px;
    padding: 6px 10px; min-height: 20px; }
QPushButton:hover { background: #edf4fc; border-color: #92b4da; }
QPushButton:disabled { color: #94a3b8; background: #f1f4f8; }
QPushButton#runButton { background: #2868ab; color: white; border-color: #2868ab; font-weight: 600; }
QPushButton#runButton:disabled { background: #a7bfd9; border-color: #a7bfd9; }
QPushButton[activeStage="true"] { background: #e7f0fb; border-color: #9dbfe5; color: #215b99; font-weight: 600; }
QTableWidget, QTextEdit { background: white; border: 1px solid #dce2eb; border-radius: 4px; }
QHeaderView::section { background: #edf2f8; border: none; padding: 5px; }
QProgressBar { border: 1px solid #dce2eb; background: white; border-radius: 4px;
    text-align: center; min-height: 22px; }
QProgressBar::chunk { background: #b3d2f1; border-radius: 3px; }
QSplitter::handle { background: #c9d6e3; border: none; }
QSplitter::handle:hover { background: #a9c3e2; }
QSplitter::handle:pressed { background: #3979bf; }
QFrame#resultSidebar { background: white; border: 1px solid #dce2eb; border-radius: 8px; }
QLabel#resultSidebarTitle { font-size: 16px; font-weight: 600; color: #193b61;
    background: #eff5fc; border: none; border-left: 3px solid #3979bf;
    border-radius: 3px; padding: 4px 9px; }
QToolButton#previewToggle { background: white; border: 1px solid #cbd5e1; border-radius: 6px;
    color: #35506c; font-size: 15px; padding: 0; }
QToolButton#previewToggle:hover { background: #edf4fc; border-color: #92b4da; }
QToolButton#previewToggle:checked { background: #e7f0fb; border-color: #3979bf; color: #215b99; }
QTabWidget::pane { border: 1px solid #dce2eb; border-radius: 5px; top: -1px; }
QTabBar::tab { background: #edf2f8; border: 1px solid #dce2eb; padding: 6px 10px;
    border-top-left-radius: 5px; border-top-right-radius: 5px; margin-right: 2px; }
QTabBar::tab:selected { background: white; color: #215b99; border-bottom-color: white; }
QScrollBar:vertical { background: #e8edf3; width: 12px; margin: 0; border-radius: 6px; }
QScrollBar:horizontal { background: #e8edf3; height: 12px; margin: 0; border-radius: 6px; }
QScrollBar::handle:vertical { background: #71859d; min-height: 32px; border: 2px solid #e8edf3; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #71859d; min-width: 32px; border: 2px solid #e8edf3; border-radius: 6px; }
QScrollBar::handle:hover { background: #486785; }
QScrollBar::handle:pressed { background: #28598a; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 4px; }
QCheckBox::indicator:unchecked { background: white; border: 2px solid #71859d; }
QCheckBox::indicator:unchecked:hover { border-color: #2868ab; background: #edf5ff; }
QCheckBox::indicator:checked { background: #2868ab; border: 2px solid #2868ab; }
QCheckBox::indicator:checked:hover { background: #1e558e; border-color: #1e558e; }
"""
GUI_STYLE += (
    'QComboBox::down-arrow { image: url("'
    + (storage.ROOT / "assets/gui/chevron-down.svg").as_posix()
    + '"); width: 10px; height: 6px; }'
)
GUI_STYLE += (
    'QCheckBox::indicator:checked { image: url("'
    + (storage.ROOT / "assets/gui/check.svg").as_posix()
    + '"); }'
)

def configure_gui_style(app):
    """Use native Windows combo transitions, retaining Fusion as a fallback."""
    styles = {name.lower(): name for name in QStyleFactory.keys()}
    app.setStyle(next((styles[name] for name in ("windowsvista", "windows11", "windows") if name in styles), "Fusion"))
    app.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, True)
