"""Reusable scalar, unit, boolean, vector, and direction editors."""

from __future__ import annotations

import numpy as np

from ..qt_compat import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QSize, QSizePolicy, Qt, QVBoxLayout, QWidget
from ..schema import CONTROL_HEIGHT, EDITABLE_UNIT_WIDTH, FIXED_UNIT_WIDTH
from ..storage import format_value, parse_value

EXPANDING = QSizePolicy.Policy.Expanding
FIXED = QSizePolicy.Policy.Fixed

class NoWheelComboBox(QComboBox):
    """A combo box that ignores mouse-wheel changes to avoid accidental edits."""

    def wheelEvent(self, event) -> None:
        event.ignore()

class UnitValueWidget(QWidget):
    def __init__(self, value, unit_options: tuple[tuple[str, float], ...], editable_unit: bool = False):
        super().__init__()
        self.setObjectName("unitValue")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setSizePolicy(EXPANDING, FIXED)
        self.unit_options = unit_options
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(64)
        self.edit.setFixedHeight(CONTROL_HEIGHT - 2)
        unit_label, multiplier = self._best_unit(float(value) if isinstance(value, (int, float)) else 0.0)
        self.edit.setText(format_value(float(value) / multiplier if isinstance(value, (int, float)) else value))
        layout.addWidget(self.edit, 1)
        if editable_unit and len(unit_options) > 1:
            self.unit_combo = NoWheelComboBox()
            for label, factor in unit_options:
                self.unit_combo.addItem(label, factor)
            self.unit_combo.setCurrentText(unit_label)
            self.unit_combo.setObjectName("unitSuffix")
            self.unit_combo.setFixedSize(EDITABLE_UNIT_WIDTH, CONTROL_HEIGHT - 2)
            self.unit_combo.setToolTip("切换输入单位 / Select input unit")
            layout.addWidget(self.unit_combo)
            self.unit_suffix = self.unit_combo
        else:
            self.unit_combo = None
            unit = QLabel(unit_options[0][0])
            unit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            unit.setObjectName("unitSuffix")
            unit.setFixedSize(FIXED_UNIT_WIDTH, CONTROL_HEIGHT - 2)
            unit.setToolTip("固定单位 / Fixed unit")
            layout.addWidget(unit)
            self.unit_suffix = unit
            unit.setVisible(bool(unit_options[0][0]))
        self.setFocusProxy(self.edit)

    def _best_unit(self, value: float) -> tuple[str, float]:
        abs_value = abs(value)
        for label, multiplier in self.unit_options:
            if multiplier > 1.0 and abs_value >= multiplier:
                return label, multiplier
        return self.unit_options[-1]

    def sizeHint(self):
        return QSize(super().sizeHint().width(), CONTROL_HEIGHT)

    def value(self):
        raw = parse_value(self.edit.text())
        if not isinstance(raw, (int, float)):
            return raw
        multiplier = self.unit_combo.currentData() if self.unit_combo else self.unit_options[0][1]
        return float(raw) * float(multiplier)

class VectorValueWidget(QWidget):
    def __init__(self, value, labels: tuple[str, ...], unit: str | None = None):
        super().__init__()
        values = list(value) if isinstance(value, list) else []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        self.edits: list[QLineEdit] = []
        for index, label_text in enumerate(labels):
            row = QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            label = QLabel(label_text)
            label.setObjectName("componentLabel")
            label.setFixedHeight(22)
            row.addWidget(label)
            value_widget = UnitValueWidget(
                values[index] if index < len(values) else 0.0,
                ((unit, 1.0),) if unit else (("", 1.0),),
                editable_unit=False,
            )
            edit = value_widget.edit
            edit.setAccessibleName(label_text)
            label.setBuddy(edit)
            self.edits.append(edit)
            row.addWidget(value_widget, 1)
            layout.addLayout(row, 1)
        self.setSizePolicy(EXPANDING, FIXED)
        height = len(labels) * (CONTROL_HEIGHT + 26) + (len(labels) - 1) * 14
        self.setFixedHeight(height)

    def value(self):
        return [parse_value(edit.text()) for edit in self.edits]

class BooleanFieldWidget(QWidget):
    """An indicator-only boolean editor aligned with the other field editors."""

    def __init__(self, checked: bool = False):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        layout.addWidget(self.checkbox)
        layout.addStretch(1)

        self.setFocusProxy(self.checkbox)
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setSizePolicy(EXPANDING, FIXED)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)

    def value(self) -> bool:
        return self.isChecked()

    def hasFocus(self) -> bool:
        return self.checkbox.hasFocus()

class DirectionBodyWidget(VectorValueWidget):
    def __init__(self, value, language: str = "zh"):
        vector = np_vector3(value)
        lon_rad = np.arctan2(vector[1], vector[0])
        lat_rad = np.arcsin(np.clip(vector[2] / np.linalg.norm(vector), -1.0, 1.0))
        labels = ("本体系经度", "本体系纬度") if language == "zh" else ("Body longitude", "Body latitude")
        super().__init__([float(np.rad2deg(lon_rad)), float(np.rad2deg(lat_rad))], labels, "°")
        self.lon_edit, self.lat_edit = self.edits

    def value(self):
        lon = np.deg2rad(float(parse_value(self.lon_edit.text())))
        lat = np.deg2rad(float(parse_value(self.lat_edit.text())))
        return [
            float(np.cos(lat) * np.cos(lon)),
            float(np.cos(lat) * np.sin(lon)),
            float(np.sin(lat)),
        ]

def np_vector3(value) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (3,) or not np.isfinite(array).all() or np.linalg.norm(array) == 0.0:
        return np.array([1.0, 0.0, 0.0], dtype=float)
    return array
