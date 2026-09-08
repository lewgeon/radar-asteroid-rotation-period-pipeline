from __future__ import annotations

from ...qt_compat import (
    EXPANDING, FIXED, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, Qt,
)
from ...schema import (
    CHOICES, CONTROL_HEIGHT, FIELD_LABELS, FIELD_LABELS_EN, FIELD_UNITS,
    STAGE_GROUP_ORDER, STATE_DEFAULTS, STATE_FIELDS, STATION_COORDINATE_CHOICES,
    STATION_GROUPS, TARGET_STATE_CHOICES, UNIT_CHOICES,
)
from ...storage import format_value
from ...widgets import (
    BooleanFieldWidget, DirectionBodyWidget, NoWheelComboBox, ParameterCards,
    SubsectionPanel, UnitValueWidget, VectorValueWidget,
)


class FormRenderingMixin:
    def _render_current_stage(self) -> None:
        self._migrate_config()
        # These controls only exist on the observation page. Their C++ objects
        # are destroyed when the parameter page is rebuilt, so never retain a
        # Python reference across stages.
        self.monostatic_checkbox = None
        self.reuse_observation_checkbox = None
        self.reuse_observation_edit = None
        self.export_observation_btn = None
        self._clear_layout(self.params_layout)
        self.field_widgets.clear()
        self.params_group.setTitle(f"{self._stage_label(self.current_stage)} {self._tr('参数', 'Parameters')}")
        if self.current_stage == "observation":
            self.monostatic_checkbox = QCheckBox(
                self._tr("单基站观测：接收站沿用发射站参数", "Monostatic: receiver uses transmitter parameters")
            )
            self.monostatic_checkbox.setChecked(self.monostatic_observation)
            self.monostatic_checkbox.toggled.connect(self._on_monostatic_toggled)
            self.params_layout.addWidget(self.monostatic_checkbox)
            reuse_row = QHBoxLayout()
            self.reuse_observation_checkbox = QCheckBox(
                self._tr("复用已有视线向量", "Reuse Existing Line-of-Sight Vectors")
            )
            self.reuse_observation_checkbox.setChecked(self.reuse_observation_info)
            self.reuse_observation_checkbox.toggled.connect(self._on_reuse_observation_toggled)
            self.reuse_observation_edit = QLineEdit(self.reuse_observation_path)
            self.reuse_observation_edit.setPlaceholderText(
                self._tr("选择 observation_info.npz", "Select observation_info.npz")
            )
            self.reuse_observation_edit.textChanged.connect(self._on_reuse_observation_path_changed)
            browse_reuse_btn = QPushButton(self._tr("选择", "Browse"))
            browse_reuse_btn.clicked.connect(self._choose_observation_info)
            self.export_observation_btn = QPushButton(self._tr("另存当前向量", "Save Current Vectors As"))
            self.export_observation_btn.clicked.connect(self._export_observation_info)
            reusable = bool(self.latest_observation_path and self.latest_observation_path.exists())
            self.export_observation_btn.setEnabled(reusable)
            reuse_row.addWidget(self.reuse_observation_checkbox)
            reuse_row.addWidget(self.reuse_observation_edit, 1)
            reuse_row.addWidget(browse_reuse_btn)
            reuse_row.addWidget(self.export_observation_btn)
            self.params_layout.addLayout(reuse_row)
            self._on_reuse_observation_toggled(self.reuse_observation_info)
        stage_data = self.config_data.get(self.current_stage, {})
        self._render_stage_group_boxes(self._stage_groups(stage_data))
        self.params_layout.addStretch(1)

    def _render_stage_group_boxes(self, groups) -> None:
        # Presentation groups contain original config paths, never new JSON keys.
        sections = {}
        for group_name, values in groups:
            for relative_path, value in self._ordered_group_fields(values):
                path = relative_path if group_name == "通用参数" else f"{group_name}.{relative_path}"
                section = group_name
                if self.current_stage == "echo":
                    if path == "model_path":
                        section = "target"
                    elif path == "scattering_power":
                        section = "scattering_spot"
                    elif group_name in {"radar", "waveform"} or path in {"snr_db", "seed"}:
                        section = "radar_parameters"
                    elif path == "chunk_size":
                        section = "compute"
                elif self.current_stage == "inversion" and group_name == "通用参数":
                    if path.startswith("stft_"):
                        section = "spectrum"
                    elif path.startswith("period_"):
                        section = "period_search"
                sections.setdefault(section, []).append((path, value))
        if self.current_stage == "echo":
            order = ("compute", "radar_parameters", "target", "scattering_spot")
        elif self.current_stage == "observation":
            order = ("receive", "target", "transmitter", "receiver", "ephemeris", "solver")
        else:
            order = ("spectrum", "period_search")
        names = sorted(sections, key=lambda name: order.index(name) if name in order else len(order))
        if self.current_stage == "echo":
            field_order = (
                "compute.device", "compute.dtype", "chunk_size",
                "radar.carrier_frequency_hz", "waveform.type", "waveform.amplitude",
                "waveform.pulse_width_s", "waveform.bandwidth_hz", "waveform.fast_sample_rate_hz",
                "waveform.receive_window_start_s", "waveform.receive_window_duration_s", "waveform.pri_s",
                "waveform.first_pulse_start_s", "waveform.pulse_count", "waveform.pulse_start_s",
                "snr_db", "seed", "model_path", "target.rotation_period_s",
                "target.initial_phase_deg", "target.spin_pole_frame", "target.spin_pole_icrs_deg",
                "target.spin_pole_ecliptic_deg", "scattering_power", "scattering_spot.enabled",
                "scattering_spot.direction_body", "scattering_spot.radius_deg", "scattering_spot.strength",
            )
            priorities = {path: index for index, path in enumerate(field_order)}
            for fields in sections.values():
                fields.sort(key=lambda item: priorities.get(item[0], len(priorities)))
        cards = [self._create_group_box(name, sections[name]) for name in names if sections[name]]
        if self.current_stage == "observation" and self.monostatic_observation:
            for card in cards:
                if card.property("groupName") == "receiver":
                    card.hide()
        self.parameter_cards = ParameterCards(cards, self.current_stage)
        self.params_layout.addWidget(self.parameter_cards)

    def _create_group_box(self, group_name: str, fields) -> QFrame:
        titles = {
            "radar_parameters": self._tr("雷达参数", "Radar Parameters"),
            "spectrum": self._tr("时频分析", "Time–Frequency Analysis"),
            "period_search": self._tr("周期搜索", "Period Search"),
        }
        title = titles.get(group_name, self._group_label(group_name))
        if self.current_stage == "echo" and group_name == "scattering_spot":
            title = self._tr("散射特性", "Scattering Properties")
        group = QFrame()
        group.setObjectName("parameterCard")
        group.setProperty("groupName", group_name)
        group.setAccessibleName(title)
        outer = QVBoxLayout(group)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(14)
        header = QLabel(title)
        header.setObjectName("cardTitle")
        outer.addWidget(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        self._render_group_fields(grid, group_name, fields)
        outer.addLayout(grid)
        group.setSizePolicy(EXPANDING, FIXED)
        return group

    def _stage_groups(self, stage_data: dict):
        groups = []
        loose = {}
        for key, value in stage_data.items():
            if isinstance(value, dict):
                groups.append((key, value))
            else:
                loose[key] = value
        if loose:
            groups.insert(0, ("通用参数", loose))
        order = STAGE_GROUP_ORDER.get(self.current_stage, ())
        return sorted(groups, key=lambda item: order.index(item[0]) if item[0] in order else len(order))

    def _render_group_fields(self, grid: QGridLayout, group_name: str, fields) -> None:
        row = 0
        label_width = 84 if self.language == "zh" else 120
        field_values = dict(fields)
        spin_values = {path: value for path, value in fields if path.startswith("target.spin_pole_")}
        handled: set[str] = set()
        for full_path, value in fields:
            if full_path in handled:
                continue
            key = full_path.split(".")[-1]
            if full_path == "target.spin_pole_frame":
                coord_path = next(
                    (path for path in ("target.spin_pole_icrs_deg", "target.spin_pole_ecliptic_deg") if path in spin_values),
                    None,
                )
                if coord_path:
                    section = SubsectionPanel(
                        self._tr("自转轴", "Spin Axis"), "target.spin_pole", label_width
                    )
                    frame_widget = self._field_widget(full_path, value)
                    frame_widget.setToolTip(full_path)
                    frame_widget.setAccessibleName(self._display_label(full_path))
                    section.add_field(self._display_label(full_path), frame_widget)

                    coord_widget = self._field_widget(coord_path, spin_values[coord_path])
                    coord_widget.setToolTip(coord_path)
                    coord_widget.setAccessibleName(self._display_label(coord_path))
                    section.add_widget(coord_widget)
                    self.field_widgets[full_path] = frame_widget
                    self.field_widgets[coord_path] = coord_widget
                    handled.update({full_path, coord_path})
                    grid.addWidget(section.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
                    grid.addWidget(section, row, 1)
                    row += 1
                    continue
            label = QLabel(self._display_label(full_path))
            label.setObjectName("fieldLabel")
            label.setProperty("configPath", full_path)
            widget = self._field_widget(full_path, value)
            widget.setToolTip(full_path)
            widget.setAccessibleName(self._display_label(full_path))
            label.setBuddy(widget)
            self.field_widgets[full_path] = widget
            if isinstance(widget, BooleanFieldWidget):
                self._add_boolean_row(grid, row, label, widget, label_width)
                row += 1
            elif isinstance(widget, VectorValueWidget):
                section = SubsectionPanel(self._display_label(full_path), full_path, label_width)
                section.heading.setBuddy(widget)
                section.add_widget(widget)
                label.deleteLater()
                grid.addWidget(section.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
                grid.addWidget(section, row, 1)
                row += 1
            elif key in {"model_path", "observation_info_path", "pulse_start_s", "start_utc"}:
                grid.addWidget(label, row, 0, 1, 2)
                grid.addWidget(widget, row + 1, 0, 1, 2)
                row += 2
            else:
                label.setMinimumWidth(84 if self.language == "zh" else 120)
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1)
                row += 1
                if (
                    key == "state"
                    and self.current_stage == "observation"
                    and group_name in {"transmitter", "receiver"}
                ):
                    row = self._render_station_state_children(
                        grid, row, group_name, str(value), field_values, handled, label_width
                    )
        grid.setColumnStretch(1, 1)

    def _add_boolean_row(
        self,
        grid: QGridLayout,
        row: int,
        label: QLabel,
        widget: BooleanFieldWidget,
        label_width: int,
    ) -> None:
        """Align short booleans with editors; keep long labels intact and inline."""

        label.setBuddy(widget)
        if label.sizeHint().width() <= label_width:
            label.setMinimumWidth(label_width)
            grid.addWidget(label, row, 0)
            grid.addWidget(widget, row, 1)
            return

        inline = QWidget()
        inline_layout = QHBoxLayout(inline)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        inline_layout.setSpacing(8)
        inline_layout.addWidget(label)
        inline_layout.addWidget(widget)
        inline_layout.addStretch(1)
        inline.setFixedHeight(CONTROL_HEIGHT)
        inline.setSizePolicy(EXPANDING, FIXED)
        grid.addWidget(inline, row, 0, 1, 2)

    def _render_station_state_children(
        self,
        grid: QGridLayout,
        row: int,
        group_name: str,
        state: str,
        field_values: dict,
        handled: set[str],
        label_width: int,
    ) -> int:
        for state_fields in STATE_FIELDS.values():
            for child_key in state_fields:
                if child_key not in {"id", "object_type"}:
                    handled.add(f"{group_name}.{child_key}")
        geodetic = state in {"geodetic_fixed", "astropy_geodetic"}
        initial_title = self._tr("初始坐标", "Initial Coordinates")
        if geodetic:
            initial_path = f"{group_name}.initial_geodetic_coordinates"
            initial = SubsectionPanel(initial_title, initial_path, label_width)
            for child_key in ("lon_deg", "lat_deg", "height_m"):
                child_path = f"{group_name}.{child_key}"
                child_widget = self._field_widget(
                    child_path, field_values.get(child_path, STATE_DEFAULTS[child_key])
                )
                child_widget.setToolTip(child_path)
                child_widget.setAccessibleName(self._display_label(child_path))
                initial.add_field(self._display_label(child_path), child_widget)
                self.field_widgets[child_path] = child_widget
                handled.add(child_path)
            grid.addWidget(initial.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(initial, row, 1)
            row += 1
            toggle_path = f"{group_name}.geodetic_time_dependent"
            toggle_value = state == "astropy_geodetic"
            toggle_tooltip = self._tr(
                "开启后按每个事件时刻计算测站在 GCRS 中的位置",
                "Compute the station GCRS position at each event time when enabled",
            )
        else:
            position_key = "position0_m" if state == "linear" else "position_m"
            position_path = f"{group_name}.{position_key}"
            position_widget = self._field_widget(
                position_path, field_values.get(position_path, STATE_DEFAULTS[position_key])
            )
            position_widget.setToolTip(position_path)
            position_widget.setAccessibleName(initial_title)
            initial = SubsectionPanel(initial_title, position_path, label_width)
            initial.heading.setBuddy(position_widget)
            initial.add_widget(position_widget)
            self.field_widgets[position_path] = position_widget
            handled.add(position_path)
            grid.addWidget(initial.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(initial, row, 1)
            row += 1
            toggle_path = f"{group_name}.linear_motion"
            toggle_value = state == "linear"
            toggle_tooltip = self._tr(
                "开启后使用初始坐标和速度进行匀速直线运动",
                "Use the initial coordinates and velocity for uniform linear motion",
            )

        toggle_widget = self._field_widget(toggle_path, toggle_value)
        toggle_widget.setToolTip(toggle_tooltip)
        toggle_widget.setAccessibleName(self._display_label(toggle_path))
        self.field_widgets[toggle_path] = toggle_widget
        toggle_label = QLabel(self._display_label(toggle_path))
        toggle_label.setObjectName("fieldLabel")
        toggle_label.setProperty("configPath", toggle_path)
        self._add_boolean_row(grid, row, toggle_label, toggle_widget, label_width)
        row += 1

        if state == "linear":
            velocity_path = f"{group_name}.velocity_m_s"
            velocity_widget = self._field_widget(
                velocity_path, field_values.get(velocity_path, STATE_DEFAULTS["velocity_m_s"])
            )
            velocity_widget.setToolTip(velocity_path)
            velocity_widget.setAccessibleName(self._display_label(velocity_path))
            velocity = SubsectionPanel(
                self._display_label(velocity_path), velocity_path, label_width
            )
            velocity.heading.setBuddy(velocity_widget)
            velocity.add_widget(velocity_widget)
            self.field_widgets[velocity_path] = velocity_widget
            handled.add(velocity_path)
            grid.addWidget(velocity.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
            grid.addWidget(velocity, row, 1)
            row += 1
        return row

    def _field_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        if isinstance(value, bool):
            checkbox = BooleanFieldWidget(value)
            if full_path == "scattering_spot.enabled":
                checkbox.checkbox.toggled.connect(lambda _checked: self._on_spot_enabled_changed())
            if full_path.endswith(".linear_motion"):
                checkbox.checkbox.toggled.connect(
                    lambda _checked, path=full_path: self._on_station_motion_changed(path)
                )
            return checkbox
        if key in CHOICES:
            combo = NoWheelComboBox()
            choices = self._choices_for_field(full_path)
            current = format_value(value)
            if key == "state" and full_path.split(".", 1)[0] in {"transmitter", "receiver"}:
                if current in {"geodetic_fixed", "astropy_geodetic"}:
                    current = "geodetic"
                elif current in {"static", "linear"}:
                    current = "cartesian"
            for item in choices:
                data = "true" if item is True else "false" if item is False else str(item)
                combo.addItem(self._option_label(data), data)
            existing_data = [combo.itemData(i) for i in range(combo.count())]
            if current == "icrs":
                current = "equatorial"
            if current not in existing_data:
                combo.insertItem(0, self._option_label(current), current)
            index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
            if key == "state":
                combo.currentTextChanged.connect(lambda _text, path=full_path: self._on_state_changed(path))
            if key == "spin_pole_frame":
                combo.currentTextChanged.connect(lambda _text, path=full_path: self._on_spin_pole_frame_changed(path))
            if full_path == "waveform.type":
                combo.currentTextChanged.connect(lambda _text: self._on_waveform_type_changed())
            self._apply_field_width(combo, full_path, value)
            return combo

        custom = self._custom_value_widget(full_path, value)
        if custom is not None:
            self._apply_field_width(custom, full_path, value)
            return custom

        edit = QLineEdit(format_value(value))
        self._apply_field_width(edit, full_path, value)
        unit = FIELD_UNITS.get(key)
        if unit:
            edit.setPlaceholderText(unit)
            edit.setToolTip(f"单位：{unit}；配置字段：{full_path}")
        else:
            edit.setToolTip(f"配置字段：{full_path}")
        return edit

    def _apply_field_width(self, widget: QWidget, full_path: str, value) -> None:
        widget.setSizePolicy(EXPANDING, FIXED)
        if isinstance(widget, (QLineEdit, QComboBox)):
            widget.setMinimumWidth(160)
            widget.setFixedHeight(CONTROL_HEIGHT)
        elif isinstance(widget, UnitValueWidget):
            widget.setMinimumWidth(160)

    def _custom_value_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        unit = FIELD_UNITS.get(key)
        if key == "scattering_power" and isinstance(value, list) and len(value) == 2:
            labels = ("发射照明", "接收散射") if self.language == "zh" else ("Tx", "Rx")
            return VectorValueWidget(value, labels)
        if key == "spin_pole_icrs_deg" and isinstance(value, list):
            labels = ("赤经", "赤纬") if self.language == "zh" else ("RA", "Dec")
            return VectorValueWidget(value, labels, "°")
        if key == "spin_pole_ecliptic_deg" and isinstance(value, list):
            labels = ("黄经", "黄纬") if self.language == "zh" else ("Lon", "Lat")
            return VectorValueWidget(value, labels, "°")
        if key == "direction_body" and isinstance(value, list):
            return DirectionBodyWidget(value, self.language)
        if isinstance(value, list) and len(value) in {2, 3} and all(isinstance(item, (int, float)) for item in value):
            labels = ("x", "y", "z")[: len(value)]
            return VectorValueWidget(value, labels, unit)
        if key in UNIT_CHOICES and isinstance(value, (int, float)):
            return UnitValueWidget(value, UNIT_CHOICES[key], editable_unit=True)
        if unit and (value is None or isinstance(value, (int, float))):
            return UnitValueWidget(value, ((unit, 1.0),), editable_unit=False)
        return None

    def _display_label(self, relative_path: str) -> str:
        if relative_path in {"transmitter.state", "receiver.state"}:
            return self._tr("坐标格式", "Coordinate Format")
        key = relative_path.split(".")[-1]
        labels = FIELD_LABELS if self.language == "zh" else FIELD_LABELS_EN
        return labels.get(key, key)

    def _choices_for_field(self, full_path: str) -> tuple[str, ...]:
        key = full_path.split(".")[-1]
        if key != "state":
            return CHOICES[key]
        group_name = full_path.split(".")[0]
        if self.current_stage == "observation" and group_name == "target":
            return TARGET_STATE_CHOICES
        if self.current_stage == "observation" and group_name in STATION_GROUPS:
            return STATION_COORDINATE_CHOICES
        return CHOICES[key]
