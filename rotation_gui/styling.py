"""Application-wide visual theme and native style configuration."""

from __future__ import annotations

from . import storage
from .qt_compat import QStyleFactory, Qt

GUI_STYLE = """
QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 13px; color: #25354a; }
QMainWindow { background: #f3f5f8; }
QFrame#toolbarPanel, QFrame#workPanel {
    background: white; border: 1px solid #dce2eb; border-radius: 10px;
}
QLabel#panelTitle, QLabel#sectionTitle {
    font-size: 17px; font-weight: 650; color: #173652;
}
QLabel#logTitle { font-size: 14px; font-weight: 600; color: #35506c; }
QPushButton#logActionButton { border: none; background: transparent; color: #60738c; padding: 0 6px; }
QPushButton#logActionButton:hover { background: #edf3fa; color: #215b99; }
QLabel#panelHint, QLabel#sectionHint, QLabel#statusText {
    color: #60738c; font-size: 12px;
}
QLabel#fieldLabel { color: #35506c; font-size: 13px; }
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
QFrame#scheduleFeedback { background: #f8fafc; border: 1px solid #dce5ef; border-radius: 6px; }
QLabel#scheduleFeedbackSummary { color: #23415f; font-weight: 600; }
QLabel#scheduleFeedbackSummary[previewState="error"] { color: #a33b3b; }
QLabel#scheduleFeedbackSummary[previewState="ok"] { color: #286447; }
QLabel#scheduleFeedbackSummary[previewState="stale"] { color: #9a6b12; }
QWidget#scheduleTimeline { background: white; border: 1px solid #e1e7ef; border-radius: 4px; }
QLabel#scheduleFeedbackDetail { color: #60738c; font-size: 11px; }
QLabel#rangeGateReadout { color: #60738c; font-size: 12px; background: transparent; border: none; padding: 0; }
QLabel#configPathDisplay { color: #667789; background: #f2f4f7; border: none;
    border-radius: 5px; padding: 0 8px; min-height: 30px; }
QLineEdit, QComboBox { background: white; border: 1px solid #cbd5e1;
    border-radius: 5px; padding: 0 8px; min-height: 30px; selection-background-color: #d9e9fb; }
QLineEdit:focus, QComboBox:focus { border-color: #3979bf; }
QWidget#unitValue[focused="true"] { border-color: #3979bf; }
QLineEdit[inputError="true"], QWidget#unitValue[inputError="true"] {
    border: 2px solid #c94b4b; background: #fff5f5;
}
QWidget#unitValue[inputError="true"] QLineEdit { background: transparent; }
QComboBox { padding-right: 24px; combobox-popup: 0; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #9bafc5;
    selection-background-color: #dbeafb; selection-color: #193b61; outline: 0; }
QWidget#unitValue { background: white; border: 1px solid #cbd5e1; border-radius: 5px; }
QWidget#unitValue QLineEdit { border: none; background: transparent; min-height: 0; }
QWidget#unitValue QLabel#unitSuffix, QWidget#unitValue QComboBox#unitSuffix {
    background: #f0f4f8; color: #526882; border: none; border-left: 1px solid #dce2eb;
    border-radius: 0; min-height: 0; padding: 0 4px; font-size: 12px; }
QWidget#unitValue QComboBox#unitSuffix { padding-right: 12px; }
QWidget#unitValue QComboBox#unitSuffix::drop-down { width: 14px; }
QLabel#componentLabel { color: #60738c; font-size: 12px; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 5px;
    padding: 6px 10px; min-height: 20px; }
QPushButton:hover { background: #edf4fc; border-color: #92b4da; }
QPushButton:disabled { color: #94a3b8; background: #f1f4f8; }
QPushButton#runButton { background: #2868ab; color: white; border-color: #2868ab; font-weight: 600; }
QPushButton#runButton:disabled { background: #a7bfd9; border-color: #a7bfd9; }
QPushButton#previewButton {
    background: #e8edf3; color: #94a3b8; border: 1px solid #cbd5e1; font-weight: 600;
}
QPushButton#previewButton:disabled { background: #eef2f6; color: #b0bac7; border-color: #d8dee7; }
QPushButton#previewButton[previewReady="true"] {
    background: #eff6ff; color: #1d4f91; border: 2px solid #3b82f6;
    font-weight: 700;
}
QPushButton#previewButton[previewReady="true"]:hover {
    background: #dbeafe; border-color: #2563eb;
}
QPushButton[activeStage="true"] { background: #e7f0fb; border-color: #9dbfe5; color: #215b99; font-weight: 600; }
QTextEdit { background: white; border: 1px solid #dce2eb; border-radius: 4px; }
QProgressBar { border: 1px solid #d4dce5; background: #edf1f5; border-radius: 4px;
    text-align: center; min-height: 22px; }
QProgressBar::chunk { background: #39c94c; border-radius: 3px; }
QSplitter::handle { background: #c9d6e3; border: none; }
QSplitter::handle:hover { background: #a9c3e2; }
QSplitter::handle:pressed { background: #3979bf; }
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
