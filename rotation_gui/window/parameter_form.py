"""Grouped parameter cards for the single-page pipeline GUI."""

from __future__ import annotations

import copy
import json

from ..qt_compat import (
    EXPANDING,
    FIXED,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
)
from ..schema import (
    CHOICES,
    COMMON_FIELD_ORDER,
    CONTROL_HEIGHT,
    EPHEMERIS_FIELD_DEFAULTS,
    EPHEMERIS_FIELD_ORDER,
    FIELD_LABELS,
    FIELD_UNITS,
    GROUP_LABELS,
    HORIZONS_ID_TYPE_ALIASES,
    OBSERVATION_BODY_GROUPS,
    OPTION_LABELS,
    SCATTERING_SPOT_DEFAULTS,
    STATE_DEFAULTS,
    STATE_FIELDS,
    STATION_COORDINATE_CHOICES,
    STATION_GROUPS,
    STATION_TECHNICAL_STATES,
    TARGET_STATE_CHOICES,
    UNIT_CHOICES,
)
from ..storage import assign_path, format_value, parse_value
from ..widgets import (
    BooleanFieldWidget,
    DirectionBodyWidget,
    NoWheelComboBox,
    ParameterCards,
    SubsectionPanel,
    UnitValueWidget,
    VectorValueWidget,
)

SECTION_META = {
    "observation": ("观测解算", "目标、测站、发射时序、接收采样与 run 计划"),
    "echo": ("回波仿真", "射频波形、自转、散射与回波参考系；发射时序/采样率由观测阶段注入"),
    "inversion": ("周期反演", "时频特征、CPI 与周期搜索范围"),
}

ECHO_FIELD_ORDER = (
    "compute.device",
    "compute.dtype",
    "radar.carrier_frequency_hz",
    "waveform.bandwidth_hz",
    "waveform.amplitude",
    "waveform.baseband_convention",
    "snr_db",
    "seed",
    "echo_output_reference",
    "intrapulse_motion_model",
    "model_path",
    "target.rotation_period_s",
    "target.initial_phase_deg",
    "target.spin_pole_frame",
    "target.spin_pole_icrs_deg",
    "target.spin_pole_ecliptic_deg",
    "scattering_power",
    "scattering_spot.enabled",
    "scattering_spot.direction_body",
    "scattering_spot.radius_deg",
    "scattering_spot.strength",
)

# Echo RF fields that only apply to chirp pulse trains.
ECHO_CHIRP_ONLY_FIELDS = {"waveform.bandwidth_hz", "waveform.baseband_convention"}

OBSERVATION_WAVEFORM_DEFAULTS = {
    "continuous_wave": {
        "prf_hz": 1.0,
        "pulse_width_s": 0.5,
        "pulse_fiducial": "leading_edge",
    },
    "chirp_pulse_train": {
        "prf_hz": 4.0,
        "pulse_width_s": 0.001,
        "pulse_fiducial": "leading_edge",
    },
}

ECHO_WAVEFORM_DEFAULTS = {
    "continuous_wave": {
        "amplitude": 1.0,
    },
    "chirp_pulse_train": {
        "bandwidth_hz": 1.0e5,
        "amplitude": 1.0,
        "baseband_convention": "zero_to_bandwidth",
    },
}

INVERSION_FIELD_ORDER = (
    "stft_window_samples",
    "stft_overlap_fraction",
    "cpi_pulses",
    "cpi_hop_pulses",
    "period_min_s",
    "period_max_s",
    "period_grid_size",
    "period_time_role",
    "motion_compensation",
    "harmonics",
    "cross_run_phase_coherent",
)

CARD_ORDER = {
    "observation": (
        "campaign",
        "target",
        "transmitter",
        "receiver",
        "radar_system",
        "waveform",
        "receiver_sampling",
        "plan",
        "geometry",
    ),
    "echo": ("compute", "radar_parameters", "echo_options", "target", "scattering_spot"),
    "inversion": ("spectrum", "period_search"),
}

_ALL_STATE_FIELD_KEYS = {key for fields in STATE_FIELDS.values() for key in fields} - {"id"}


class ParameterForm(QWidget):
    """Scrollable semantic cards for the full pipeline config."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.field_widgets: dict[str, QWidget] = {}
        self._cards: list[ParameterCards] = []
        self._active_stage = ""
        self._config: dict = {}
        self.monostatic = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas = QWidget()
        self.canvas.setObjectName("parameterCanvas")
        self.canvas_layout = QVBoxLayout(self.canvas)
        self.canvas_layout.setContentsMargins(4, 4, 12, 4)
        self.canvas_layout.setSpacing(18)
        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll)

    def render(
        self,
        config: dict,
        stage: str | None = None,
        *,
        monostatic: bool = False,
        focus_path: str | None = None,
        preserve_scroll: bool = True,
    ) -> None:
        scroll_bar = self.scroll.verticalScrollBar()
        scroll_value = scroll_bar.value() if preserve_scroll else 0
        self._config = config
        self.field_widgets.clear()
        self._cards.clear()
        self.monostatic = bool(monostatic)
        while self.canvas_layout.count():
            item = self.canvas_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        stages = (stage,) if stage else tuple(SECTION_META)
        for name in stages:
            stage_data = config.get(name, {})
            if not isinstance(stage_data, dict):
                continue
            if name == "observation":
                self._normalize_observation_bodies(stage_data)
            elif name == "echo":
                self._normalize_echo_stage(stage_data)
            self.canvas_layout.addWidget(self._build_section(name, stage_data))
        self.canvas_layout.addStretch(1)

        def _restore_view() -> None:
            if focus_path:
                widget = self.field_widgets.get(focus_path)
                if widget is not None:
                    widget.setFocus(Qt.FocusReason.OtherFocusReason)
            if preserve_scroll:
                scroll_bar.setValue(scroll_value)

        QTimer.singleShot(0, _restore_view)

    def collect(self) -> dict:
        # Start from the live model so hidden conditional fields are not wiped.
        config = copy.deepcopy(self._config) if self._config else {}
        geodetic_rotation: dict[str, bool] = {}
        linear_motion: dict[str, bool] = {}
        for path, widget in self.field_widgets.items():
            value = self._widget_value(widget)
            if path.endswith(".geodetic_time_dependent"):
                geodetic_rotation[path.split(".")[1]] = bool(value)
                continue
            if path.endswith(".linear_motion"):
                linear_motion[path.split(".")[1]] = bool(value)
                continue
            assign_path(config, path, value)

        observation = config.get("observation")
        if isinstance(observation, dict):
            for role in STATION_GROUPS:
                group = observation.get(role)
                if not isinstance(group, dict):
                    continue
                if group.get("state") == "geodetic":
                    group["state"] = (
                        "astropy_geodetic"
                        if geodetic_rotation.get(role, True)
                        else "geodetic_fixed"
                    )
                elif group.get("state") == "cartesian":
                    group["state"] = "linear" if linear_motion.get(role, False) else "static"
                observation[role] = self._normalize_state_group(group, role=role)
            target = observation.get("target")
            if isinstance(target, dict):
                observation["target"] = self._normalize_state_group(target, role="target")
        echo = config.get("echo")
        if isinstance(echo, dict):
            self._normalize_echo_stage(echo)
            observation = config.get("observation", {})
            obs_type = None
            if isinstance(observation, dict):
                obs_type = observation.get("waveform", {}).get("type")
            if obs_type:
                echo.setdefault("waveform", {})["type"] = obs_type
        return config

    def collect_stage(self, stage: str) -> dict:
        return self.collect().get(stage, {})

    def _build_section(self, stage: str, stage_data: dict) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._active_stage = stage
        cards = self._create_cards(stage, stage_data)
        if cards:
            canvas = ParameterCards(cards, stage, on_layout_changed=self._relayout)
            self._cards.append(canvas)
            layout.addWidget(canvas)
        return section

    def _relayout(self) -> None:
        self.canvas_layout.activate()
        self.canvas.adjustSize()

    def _create_cards(self, stage: str, stage_data: dict) -> list[QFrame]:
        sections = self._presentation_sections(stage, stage_data)
        order = CARD_ORDER[stage]
        names = sorted(sections, key=lambda name: order.index(name) if name in order else len(order))
        return [self._create_card(stage, name, sections[name]) for name in names if sections[name]]

    def _presentation_sections(self, stage: str, stage_data: dict) -> dict[str, list]:
        sections: dict[str, list] = {}
        loose: dict = {}
        for key, value in stage_data.items():
            if isinstance(value, dict):
                if stage == "observation" and key in OBSERVATION_BODY_GROUPS:
                    sections[key] = self._body_presentation_fields(key, value)
                elif value:
                    for child_key, child_value in value.items():
                        sections.setdefault(key, []).append((f"{key}.{child_key}", child_value))
            else:
                loose[key] = value
        if stage == "echo":
            for path, value in loose.items():
                if path == "model_path":
                    section = "target"
                elif path == "scattering_power":
                    section = "scattering_spot"
                elif path in {"snr_db", "seed"}:
                    section = "radar_parameters"
                else:
                    section = "echo_options"
                sections.setdefault(section, []).append((path, value))
            for group_name in ("radar", "waveform"):
                fields = sections.pop(group_name, [])
                if fields:
                    sections.setdefault("radar_parameters", []).extend(fields)
            sections = self._filter_echo_sections(stage_data, sections)
            priorities = {path: index for index, path in enumerate(ECHO_FIELD_ORDER)}
            for fields in sections.values():
                fields.sort(key=lambda item: priorities.get(item[0], len(priorities)))
        elif stage == "observation":
            merges = {
                "plan": ("visibility", "schedule"),
                "geometry": ("ephemeris", "solver"),
            }
            for target, sources in merges.items():
                merged = []
                for source in sources:
                    merged.extend(sections.pop(source, []))
                if merged:
                    sections[target] = merged
            sections.pop("receive", None)
            if self.monostatic:
                sections.pop("receiver", None)
            if loose:
                for path, value in loose.items():
                    sections.setdefault("campaign", []).append((path, value))
            sections = self._filter_observation_sections(stage_data, sections)
        elif stage == "inversion":
            for path, value in loose.items():
                section = "spectrum" if path.startswith(("stft_", "cpi_")) else "period_search"
                sections.setdefault(section, []).append((path, value))
            priorities = {path: index for index, path in enumerate(INVERSION_FIELD_ORDER)}
            for fields in sections.values():
                fields.sort(key=lambda item: priorities.get(item[0], len(priorities)))
        elif loose:
            for path, value in loose.items():
                sections.setdefault("general", []).append((path, value))
        return sections

    def _body_presentation_fields(self, group_name: str, group: dict) -> list:
        group = self._normalize_state_group(group, role=group_name)
        fields: list[tuple[str, object]] = []
        for key in COMMON_FIELD_ORDER:
            if key == "state":
                if group_name in STATION_GROUPS:
                    technical = str(group.get("state", "static"))
                    if technical in {"geodetic_fixed", "astropy_geodetic"}:
                        fields.append((f"{group_name}.state", "geodetic"))
                    else:
                        fields.append((f"{group_name}.state", "cartesian"))
                else:
                    fields.append((f"{group_name}.state", group.get("state", "static")))
            elif key in group:
                fields.append((f"{group_name}.{key}", group[key]))

        state = str(group.get("state", "static"))
        if group_name in STATION_GROUPS:
            if state in {"geodetic_fixed", "astropy_geodetic"}:
                fields.append((f"{group_name}.initial_geodetic_coordinates", None))
                for child_key in ("lat_deg", "lon_deg", "height_m"):
                    fields.append(
                        (
                            f"{group_name}.{child_key}",
                            group.get(child_key, copy.deepcopy(STATE_DEFAULTS[child_key])),
                        )
                    )
                fields.append((f"{group_name}.geodetic_time_dependent", state == "astropy_geodetic"))
            else:
                position_key = "position0_m" if state == "linear" else "position_m"
                fields.append(
                    (
                        f"{group_name}.{position_key}",
                        group.get(
                            position_key,
                            group.get(
                                "position_m",
                                group.get("position0_m", copy.deepcopy(STATE_DEFAULTS[position_key])),
                            ),
                        ),
                    )
                )
                fields.append((f"{group_name}.linear_motion", state == "linear"))
                if state == "linear":
                    fields.append(
                        (
                            f"{group_name}.velocity_m_s",
                            group.get("velocity_m_s", copy.deepcopy(STATE_DEFAULTS["velocity_m_s"])),
                        )
                    )
        else:
            for child_key in STATE_FIELDS.get(state, ()):
                if child_key == "id":
                    continue
                fields.append(
                    (
                        f"{group_name}.{child_key}",
                        group.get(child_key, copy.deepcopy(STATE_DEFAULTS.get(child_key, ""))),
                    )
                )
        return fields

    def _create_card(self, stage: str, group_name: str, fields: list) -> QFrame:
        title = GROUP_LABELS.get(group_name, group_name)
        card = QFrame()
        card.setObjectName("parameterCard")
        card.setProperty("groupName", group_name)
        card.setAccessibleName(title)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(12)
        header = QLabel(title)
        header.setObjectName("cardTitle")
        outer.addWidget(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        grid.setColumnMinimumWidth(0, 96)
        grid.setColumnStretch(1, 1)
        self._render_fields(grid, stage, group_name, fields)
        outer.addLayout(grid)
        card.setSizePolicy(EXPANDING, FIXED)
        return card

    def _render_fields(self, grid: QGridLayout, stage: str, group_name: str, fields: list) -> None:
        row = 0
        label_width = 108
        previous_root = None
        handled: set[str] = set()
        field_values = {path: value for path, value in fields}
        for relative_path, value in fields:
            if relative_path in handled:
                continue
            absolute = f"{stage}.{relative_path}"
            root = relative_path.split(".", 1)[0]
            if previous_root is not None and root != previous_root and "." in relative_path:
                spacer = QLabel("")
                spacer.setFixedHeight(6)
                grid.addWidget(spacer, row, 0, 1, 2)
                row += 1
            previous_root = root
            key = relative_path.split(".")[-1]

            if stage == "echo" and relative_path == "target.spin_pole_frame":
                coord_path = next(
                    (
                        path
                        for path in ("target.spin_pole_icrs_deg", "target.spin_pole_ecliptic_deg")
                        if path in field_values
                    ),
                    None,
                )
                section = SubsectionPanel("自转轴", f"{stage}.target.spin_pole", label_width)
                frame_widget = self._field_widget(relative_path, value)
                frame_widget.setToolTip(absolute)
                section.add_field(FIELD_LABELS.get("spin_pole_frame", "坐标系"), frame_widget)
                self.field_widgets[absolute] = frame_widget
                handled.add(relative_path)
                if coord_path is not None:
                    coord_absolute = f"{stage}.{coord_path}"
                    coord_widget = self._field_widget(coord_path, field_values[coord_path])
                    coord_widget.setToolTip(coord_absolute)
                    section.add_widget(coord_widget)
                    self.field_widgets[coord_absolute] = coord_widget
                    handled.add(coord_path)
                grid.addWidget(section.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
                grid.addWidget(section, row, 1)
                row += 1
                continue

            if stage == "observation" and group_name in STATION_GROUPS and key == "state":
                text = "坐标格式"
                label = QLabel(text)
                label.setObjectName("fieldLabel")
                label.setMinimumWidth(label_width)
                widget = self._field_widget(relative_path, value)
                widget.setToolTip(absolute)
                self.field_widgets[absolute] = widget
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1)
                handled.add(relative_path)
                row += 1
                row = self._render_station_state_children(
                    grid, stage, group_name, str(value), field_values, handled, label_width, row
                )
                continue

            if relative_path.endswith(".initial_geodetic_coordinates"):
                continue
            if key in {"lat_deg", "lon_deg", "height_m", "geodetic_time_dependent", "linear_motion"}:
                # Station children are rendered with the coordinate-format row.
                if stage == "observation" and group_name in STATION_GROUPS:
                    continue

            text = FIELD_LABELS.get(key, key)
            label = QLabel(text)
            label.setObjectName("fieldLabel")
            label.setMinimumWidth(label_width)
            widget = self._field_widget(relative_path, value)
            widget.setToolTip(absolute)
            self.field_widgets[absolute] = widget
            if isinstance(widget, BooleanFieldWidget):
                if relative_path == "scattering_spot.enabled":
                    widget.checkbox.toggled.connect(lambda _checked: self._on_spot_enabled_changed())
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            elif isinstance(widget, (VectorValueWidget, DirectionBodyWidget)):
                section = SubsectionPanel(text, absolute, label_width)
                section.heading.setBuddy(widget)
                section.add_widget(widget)
                label.deleteLater()
                grid.addWidget(section.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
                grid.addWidget(section, row, 1)
            elif key in {"model_path", "runs", "pulse_start_s"} or key.endswith("_utc"):
                grid.addWidget(label, row, 0, 1, 2)
                grid.addWidget(widget, row + 1, 0, 1, 2)
                row += 1
            else:
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1)
            handled.add(relative_path)
            row += 1

    def _render_station_state_children(
        self,
        grid: QGridLayout,
        stage: str,
        group_name: str,
        presentation_state: str,
        field_values: dict,
        handled: set[str],
        label_width: int,
        row: int,
    ) -> int:
        if presentation_state == "geodetic":
            initial = SubsectionPanel("初始坐标", f"{stage}.{group_name}.initial_geodetic_coordinates", label_width)
            for child_key in ("lat_deg", "lon_deg", "height_m"):
                child_path = f"{group_name}.{child_key}"
                absolute = f"{stage}.{child_path}"
                child_widget = self._field_widget(
                    child_path, field_values.get(child_path, STATE_DEFAULTS[child_key])
                )
                child_widget.setToolTip(absolute)
                initial.add_field(FIELD_LABELS.get(child_key, child_key), child_widget)
                self.field_widgets[absolute] = child_widget
                handled.add(child_path)
            grid.addWidget(initial.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(initial, row, 1)
            row += 1

            toggle_path = f"{group_name}.geodetic_time_dependent"
            absolute = f"{stage}.{toggle_path}"
            toggle_widget = self._field_widget(
                toggle_path, field_values.get(toggle_path, True)
            )
            toggle_widget.setToolTip(absolute)
            if isinstance(toggle_widget, BooleanFieldWidget):
                toggle_widget.checkbox.toggled.connect(
                    lambda _checked, path=absolute: self._on_station_motion_changed(path)
                )
            self.field_widgets[absolute] = toggle_widget
            handled.add(toggle_path)
            label = QLabel(FIELD_LABELS["geodetic_time_dependent"])
            label.setObjectName("fieldLabel")
            label.setMinimumWidth(label_width)
            grid.addWidget(label, row, 0)
            grid.addWidget(toggle_widget, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            row += 1
            return row

        position_key = "position0_m" if field_values.get(f"{group_name}.linear_motion") else "position_m"
        if f"{group_name}.position0_m" in field_values:
            position_key = "position0_m"
        elif f"{group_name}.position_m" in field_values:
            position_key = "position_m"
        position_path = f"{group_name}.{position_key}"
        absolute = f"{stage}.{position_path}"
        position_widget = self._field_widget(
            position_path,
            field_values.get(position_path, copy.deepcopy(STATE_DEFAULTS[position_key])),
        )
        position_widget.setToolTip(absolute)
        initial = SubsectionPanel("初始坐标", absolute, label_width)
        initial.add_widget(position_widget)
        self.field_widgets[absolute] = position_widget
        handled.add(position_path)
        grid.addWidget(initial.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(initial, row, 1)
        row += 1

        toggle_path = f"{group_name}.linear_motion"
        absolute = f"{stage}.{toggle_path}"
        toggle_widget = self._field_widget(
            toggle_path, field_values.get(toggle_path, False)
        )
        toggle_widget.setToolTip(absolute)
        if isinstance(toggle_widget, BooleanFieldWidget):
            toggle_widget.checkbox.toggled.connect(
                lambda _checked, path=absolute: self._on_station_motion_changed(path)
            )
        self.field_widgets[absolute] = toggle_widget
        handled.add(toggle_path)
        label = QLabel(FIELD_LABELS["linear_motion"])
        label.setObjectName("fieldLabel")
        label.setMinimumWidth(label_width)
        grid.addWidget(label, row, 0)
        grid.addWidget(toggle_widget, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        row += 1

        if field_values.get(toggle_path, False):
            velocity_path = f"{group_name}.velocity_m_s"
            absolute = f"{stage}.{velocity_path}"
            velocity_widget = self._field_widget(
                velocity_path,
                field_values.get(velocity_path, copy.deepcopy(STATE_DEFAULTS["velocity_m_s"])),
            )
            velocity_widget.setToolTip(absolute)
            velocity = SubsectionPanel(FIELD_LABELS["velocity_m_s"], absolute, label_width)
            velocity.add_widget(velocity_widget)
            self.field_widgets[absolute] = velocity_widget
            handled.add(velocity_path)
            grid.addWidget(velocity.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(velocity, row, 1)
            row += 1
        return row

    def _field_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        if isinstance(value, bool) or key in {"geodetic_time_dependent", "linear_motion"}:
            return BooleanFieldWidget(bool(value))
        if key in CHOICES or (key == "state"):
            combo = NoWheelComboBox()
            choices = self._choices_for_field(full_path)
            current = format_value(value)
            if key == "spin_pole_frame" and current in {"icrs", "equtorial"}:
                current = "equatorial"
            for item in choices:
                data = "true" if item is True else "false" if item is False else str(item)
                combo.addItem(OPTION_LABELS["zh"].get(data, data), data)
            existing = [combo.itemData(i) for i in range(combo.count())]
            if current not in existing:
                # Preserve unknown values instead of silently rewriting config.
                combo.insertItem(0, OPTION_LABELS["zh"].get(current, current), current)
            index = combo.findData(current)
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
            combo.setFixedHeight(CONTROL_HEIGHT)
            combo.setMinimumWidth(200)
            combo.setSizePolicy(EXPANDING, FIXED)
            if key == "state":
                combo.currentIndexChanged.connect(
                    lambda _index, path=full_path: self._on_state_changed(path)
                )
            if key == "spin_pole_frame":
                combo.currentIndexChanged.connect(
                    lambda _index, path=full_path: self._on_spin_pole_frame_changed(path)
                )
            if full_path == "waveform.type":
                combo.currentIndexChanged.connect(
                    lambda _index: self._on_waveform_type_changed()
                )
            if full_path == "schedule.selection":
                combo.currentIndexChanged.connect(
                    lambda _index: self._on_schedule_selection_changed()
                )
            return combo
        if key == "runs" or (isinstance(value, list) and value and isinstance(value[0], dict)):
            editor = QTextEdit()
            editor.setPlainText(json.dumps(value, ensure_ascii=False, indent=2))
            editor.setFixedHeight(128)
            editor.setMinimumWidth(280)
            editor.setSizePolicy(EXPANDING, FIXED)
            return editor
        custom = self._custom_widget(full_path, value)
        if custom is not None:
            custom.setMinimumWidth(200)
            custom.setSizePolicy(EXPANDING, FIXED)
            return custom
        edit = QLineEdit(format_value(value))
        edit.setFixedHeight(CONTROL_HEIGHT)
        edit.setMinimumWidth(200)
        edit.setSizePolicy(EXPANDING, FIXED)
        unit = FIELD_UNITS.get(key)
        if unit:
            edit.setPlaceholderText(unit)
        return edit

    def _choices_for_field(self, full_path: str) -> tuple:
        key = full_path.split(".")[-1]
        if key != "state":
            return CHOICES[key]
        group_name = full_path.split(".", 1)[0]
        if self._active_stage == "observation" and group_name == "target":
            return TARGET_STATE_CHOICES
        if self._active_stage == "observation" and group_name in STATION_GROUPS:
            return STATION_COORDINATE_CHOICES
        return CHOICES[key]

    def _custom_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        unit = FIELD_UNITS.get(key)
        if key == "scattering_power" and isinstance(value, list) and len(value) == 2:
            return VectorValueWidget(value, ("发射照明", "接收散射"))
        if key == "spin_pole_icrs_deg" and isinstance(value, list):
            return VectorValueWidget(value, ("赤经", "赤纬"), "°")
        if key == "spin_pole_ecliptic_deg" and isinstance(value, list):
            return VectorValueWidget(value, ("黄经", "黄纬"), "°")
        if key == "direction_body" and isinstance(value, list):
            return DirectionBodyWidget(value, "zh")
        if isinstance(value, list) and len(value) in {2, 3} and all(
            isinstance(item, (int, float)) for item in value
        ):
            labels = ("x", "y", "z")[: len(value)]
            return VectorValueWidget(value, labels, unit)
        if key in UNIT_CHOICES and isinstance(value, (int, float)):
            return UnitValueWidget(value, UNIT_CHOICES[key], editable_unit=True)
        if unit and (value is None or isinstance(value, (int, float))):
            return UnitValueWidget(value, ((unit, 1.0),), editable_unit=False)
        return None

    def _widget_value(self, widget):
        if isinstance(widget, BooleanFieldWidget):
            return widget.value()
        if isinstance(widget, (UnitValueWidget, VectorValueWidget, DirectionBodyWidget)):
            return widget.value()
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            if data == "null":
                return None
            if data == "true":
                return True
            if data == "false":
                return False
            return parse_value(str(data))
        if isinstance(widget, QTextEdit):
            return parse_value(widget.toPlainText())
        if isinstance(widget, QLineEdit):
            return parse_value(widget.text())
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        return None

    def _filter_echo_sections(self, stage_data: dict, sections: dict[str, list]) -> dict[str, list]:
        target = stage_data.get("target", {})
        frame = str(target.get("spin_pole_frame", "equatorial")).lower()
        if frame in {"icrs", "equatorial", "equtorial"}:
            hidden_spin = "target.spin_pole_ecliptic_deg"
        else:
            hidden_spin = "target.spin_pole_icrs_deg"
        if "target" in sections:
            sections["target"] = [
                (path, value) for path, value in sections["target"] if path != hidden_spin
            ]

        spot = stage_data.get("scattering_spot", {})
        enabled = spot.get("enabled", True)
        if enabled is False or str(enabled).lower() == "false":
            if "scattering_spot" in sections:
                sections["scattering_spot"] = [
                    (path, value)
                    for path, value in sections["scattering_spot"]
                    if path in {"scattering_spot.enabled", "scattering_power"}
                ]

        # Waveform type is owned by observation; hide the echo mirror.
        waveform_type = self._active_waveform_type(stage_data)
        for group_name, fields in list(sections.items()):
            filtered = []
            for path, value in fields:
                if path == "waveform.type":
                    continue
                if waveform_type == "continuous_wave" and path in ECHO_CHIRP_ONLY_FIELDS:
                    continue
                filtered.append((path, value))
            sections[group_name] = filtered
        return sections

    def _filter_observation_sections(self, stage_data: dict, sections: dict[str, list]) -> dict[str, list]:
        target = stage_data.get("target", {})
        is_horizons = str(target.get("state", "")) == "horizons_vectors"
        geometry = sections.get("geometry", [])
        if geometry:
            if is_horizons:
                sections["geometry"] = geometry
            else:
                sections["geometry"] = [
                    (path, value) for path, value in geometry if not path.startswith("ephemeris.")
                ]
                if not sections["geometry"]:
                    sections.pop("geometry", None)

        schedule = stage_data.get("schedule", {})
        selection = str(schedule.get("selection", "manual"))
        plan = sections.get("plan", [])
        if plan:
            auto_only = {
                "schedule.run_count",
                "schedule.run_duration_s",
                "schedule.random_seed",
            }
            manual_only = {"schedule.runs"}
            if selection == "manual":
                sections["plan"] = [(path, value) for path, value in plan if path not in auto_only]
            else:
                sections["plan"] = [(path, value) for path, value in plan if path not in manual_only]
        return sections

    def _active_waveform_type(self, echo_stage: dict | None = None) -> str:
        observation = self._config.get("observation", {}) if self._config else {}
        obs_type = None
        if isinstance(observation, dict):
            obs_type = observation.get("waveform", {}).get("type")
        if obs_type:
            return str(obs_type)
        if isinstance(echo_stage, dict):
            return str(echo_stage.get("waveform", {}).get("type", "continuous_wave"))
        return "continuous_wave"

    def _normalize_echo_stage(self, echo: dict) -> None:
        target = echo.get("target")
        if isinstance(target, dict):
            frame = str(target.get("spin_pole_frame", "equatorial")).lower()
            if frame in {"icrs", "equtorial"}:
                target["spin_pole_frame"] = "equatorial"
            target.setdefault("spin_pole_frame", "equatorial")
            frame = str(target.get("spin_pole_frame", "equatorial")).lower()
            if frame == "ecliptic":
                target.setdefault(
                    "spin_pole_ecliptic_deg",
                    copy.deepcopy(target.get("spin_pole_icrs_deg", [0.0, 90.0])),
                )
            else:
                target.setdefault(
                    "spin_pole_icrs_deg",
                    copy.deepcopy(target.get("spin_pole_ecliptic_deg", [0.0, 90.0])),
                )
        spot = echo.get("scattering_spot")
        if isinstance(spot, dict):
            spot.setdefault("enabled", True)
            if str(spot.get("enabled", True)).lower() != "false":
                for key, value in SCATTERING_SPOT_DEFAULTS.items():
                    spot.setdefault(key, copy.deepcopy(value))
        waveform = echo.setdefault("waveform", {})
        waveform_type = str(waveform.get("type") or self._active_waveform_type())
        if waveform_type == "lfm_chirp":
            waveform_type = "chirp_pulse_train"
            waveform["type"] = waveform_type
        for key, value in ECHO_WAVEFORM_DEFAULTS.get(waveform_type, {}).items():
            waveform.setdefault(key, copy.deepcopy(value))

    def _normalize_observation_bodies(self, observation: dict) -> None:
        self._migrate_legacy_receive(observation)
        self._normalize_horizons_target(observation)
        target = observation.get("target")
        if isinstance(target, dict):
            observation["target"] = self._normalize_state_group(target, role="target")
            self._ensure_horizons_ephemeris(observation)
        for role in STATION_GROUPS:
            group = observation.get(role)
            if isinstance(group, dict):
                observation[role] = self._normalize_state_group(group, role=role)
        waveform = observation.setdefault("waveform", {})
        if waveform.get("type") == "lfm_chirp":
            waveform["type"] = "chirp_pulse_train"
        waveform_type = str(waveform.get("type", "continuous_wave"))
        for key, value in OBSERVATION_WAVEFORM_DEFAULTS.get(waveform_type, {}).items():
            waveform.setdefault(key, copy.deepcopy(value))

    def _migrate_legacy_receive(self, observation: dict) -> None:
        receive = observation.pop("receive", None)
        if not isinstance(receive, dict):
            return
        campaign = observation.setdefault("campaign", {})
        if receive.get("start_utc") and not campaign.get("query_start_utc"):
            campaign["query_start_utc"] = receive["start_utc"]

    def _normalize_horizons_target(self, observation: dict) -> None:
        target = observation.get("target")
        if not isinstance(target, dict):
            return
        if "horizons_id" in target:
            target.setdefault("id", target["horizons_id"])
            target.pop("horizons_id", None)
        if "id_type" in target:
            target.setdefault("object_type", target["id_type"])
            target.pop("id_type", None)
        value = target.get("object_type")
        if isinstance(value, str):
            normalized = HORIZONS_ID_TYPE_ALIASES.get(value.strip().lower(), value.strip())
            if normalized != value:
                target["object_type"] = normalized

    def _ensure_horizons_ephemeris(self, observation: dict) -> None:
        target = observation.get("target")
        if not isinstance(target, dict) or target.get("state") != "horizons_vectors":
            return
        ephemeris = observation.setdefault("ephemeris", {})
        for key in EPHEMERIS_FIELD_ORDER:
            if key in target:
                ephemeris.setdefault(key, target.pop(key))
        for key, value in EPHEMERIS_FIELD_DEFAULTS.items():
            ephemeris.setdefault(key, copy.deepcopy(value))

    def _normalize_state_group(self, group: dict, *, role: str | None = None) -> dict:
        group = copy.deepcopy(group)
        state = str(group.get("state", "static"))
        if role == "target":
            if state not in TARGET_STATE_CHOICES:
                state = "static"
        elif role in STATION_GROUPS:
            if state == "geodetic":
                state = "astropy_geodetic"
            elif state not in STATION_TECHNICAL_STATES:
                state = "static"
        elif state not in STATE_FIELDS:
            state = "static"
        if state not in STATE_FIELDS:
            state = "static"

        normalized: dict = {}
        for key in COMMON_FIELD_ORDER:
            if key in group:
                normalized[key] = group[key]
        normalized["state"] = state
        for key in STATE_FIELDS[state]:
            normalized[key] = self._state_field_value(key, group)
        for key, value in group.items():
            if key in normalized or key in _ALL_STATE_FIELD_KEYS:
                continue
            if key in {"geodetic_time_dependent", "linear_motion", "initial_geodetic_coordinates"}:
                continue
            normalized[key] = value
        return normalized

    def _state_field_value(self, key: str, group: dict):
        if key in group:
            return group[key]
        if key == "position_m" and "position0_m" in group:
            return group["position0_m"]
        if key == "position0_m" and "position_m" in group:
            return group["position_m"]
        if key == "id" and "name" in group:
            return group["name"]
        return copy.deepcopy(STATE_DEFAULTS.get(key, ""))

    def _sync_into_config(self) -> None:
        if not self._active_stage:
            return
        updated = self.collect()
        if self._active_stage == "observation" and self.monostatic:
            transmitter = updated.get("observation", {}).get("transmitter")
            if isinstance(transmitter, dict):
                updated.setdefault("observation", {})["receiver"] = copy.deepcopy(transmitter)
        # Keep the same dict object so the main window's config_data stays linked.
        self._config.clear()
        self._config.update(updated)

    def _on_state_changed(self, full_path: str) -> None:
        absolute = f"{self._active_stage}.{full_path}"
        self._sync_into_config()
        stage_data = self._config.get(self._active_stage, {})
        group_name = full_path.split(".", 1)[0]
        group = stage_data.get(group_name)
        if isinstance(group, dict):
            role = group_name if group_name in OBSERVATION_BODY_GROUPS else None
            stage_data[group_name] = self._normalize_state_group(group, role=role)
        if self._active_stage == "observation" and group_name == "target":
            self._ensure_horizons_ephemeris(stage_data)
            self._normalize_horizons_target(stage_data)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            focus_path=absolute,
            preserve_scroll=True,
        )

    def _on_station_motion_changed(self, absolute_path: str) -> None:
        self._sync_into_config()
        stage_data = self._config.get(self._active_stage, {})
        group_name = absolute_path.split(".")[1]
        group = stage_data.get(group_name)
        if isinstance(group, dict):
            stage_data[group_name] = self._normalize_state_group(group, role=group_name)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            focus_path=absolute_path,
            preserve_scroll=True,
        )

    def _on_spot_enabled_changed(self) -> None:
        self._sync_into_config()
        echo = self._config.get("echo")
        if isinstance(echo, dict):
            self._normalize_echo_stage(echo)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            focus_path="echo.scattering_spot.enabled",
            preserve_scroll=True,
        )

    def _on_spin_pole_frame_changed(self, full_path: str) -> None:
        absolute = f"{self._active_stage}.{full_path}"
        self._sync_into_config()
        echo = self._config.get("echo")
        if isinstance(echo, dict):
            target = echo.get("target")
            if isinstance(target, dict):
                frame = str(target.get("spin_pole_frame", "equatorial")).lower()
                if frame == "ecliptic":
                    target.setdefault(
                        "spin_pole_ecliptic_deg",
                        copy.deepcopy(target.get("spin_pole_icrs_deg", [0.0, 90.0])),
                    )
                else:
                    target["spin_pole_frame"] = "equatorial"
                    target.setdefault(
                        "spin_pole_icrs_deg",
                        copy.deepcopy(target.get("spin_pole_ecliptic_deg", [0.0, 90.0])),
                    )
            self._normalize_echo_stage(echo)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            focus_path=absolute,
            preserve_scroll=True,
        )

    def _on_waveform_type_changed(self) -> None:
        self._sync_into_config()
        observation = self._config.setdefault("observation", {})
        waveform = observation.setdefault("waveform", {})
        if waveform.get("type") == "lfm_chirp":
            waveform["type"] = "chirp_pulse_train"
        waveform_type = str(waveform.get("type", "continuous_wave"))
        for key, value in OBSERVATION_WAVEFORM_DEFAULTS.get(waveform_type, {}).items():
            waveform.setdefault(key, copy.deepcopy(value))
        echo = self._config.setdefault("echo", {})
        echo_waveform = echo.setdefault("waveform", {})
        echo_waveform["type"] = waveform_type
        for key, value in ECHO_WAVEFORM_DEFAULTS.get(waveform_type, {}).items():
            echo_waveform.setdefault(key, copy.deepcopy(value))
        self._normalize_echo_stage(echo)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            focus_path=f"{self._active_stage}.waveform.type",
            preserve_scroll=True,
        )

    def _on_schedule_selection_changed(self) -> None:
        self._sync_into_config()
        schedule = self._config.setdefault("observation", {}).setdefault("schedule", {})
        selection = str(schedule.get("selection", "manual"))
        if selection == "manual":
            schedule.setdefault("runs", [])
        else:
            schedule.setdefault("run_count", 3)
            schedule.setdefault("run_duration_s", 90.0)
            schedule.setdefault("random_seed", 20260904)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            focus_path="observation.schedule.selection",
            preserve_scroll=True,
        )
