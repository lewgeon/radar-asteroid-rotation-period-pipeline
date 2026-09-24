"""Grouped parameter cards for the single-page pipeline GUI."""

from __future__ import annotations

import copy
import json
import math

from ..qt_compat import (
    QColor,
    EXPANDING,
    FIXED,
    QBrush,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFont,
    QPainter,
    QPen,
    QPointF,
    QPolygonF,
    QRectF,
    QPushButton,
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
    FIELD_LABELS,
    FIELD_TOOLTIPS,
    FIELD_UNITS,
    GROUP_LABELS,
    HORIZONS_ID_TYPE_ALIASES,
    INTEGER_FIELD_KEYS,
    MESH_ECHO_DEFAULTS,
    NUMERIC_FIELD_KEYS,
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
    NumericLineEdit,
    ParameterCards,
    SubsectionPanel,
    UnitValueWidget,
    VectorValueWidget,
)
from ..widgets.inputs import NumericInputError

SECTION_META = {
    "observation": ("观测解算", "目标、测站、发射时序、接收采样与 run 计划"),
    "echo": ("回波仿真", "射频波形、自转、散射与回波参考系；发射时序/采样率读取观测计划"),
    "inversion": ("周期反演", "时频特征、CPI 与周期搜索范围"),
}

ECHO_FIELD_ORDER = (
    "point_target.amplitude_scale",
    "compute.device",
    "compute.dtype",
    "radar.carrier_frequency_hz",
    "waveform.bandwidth_hz",
    "waveform.amplitude",
    "waveform.baseband_convention",
    "noise_enabled",
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

OBSERVATION_TRANSMIT_DEFAULTS = {
    "prf_hz": 4.0,
    "pulse_width_s": 0.001,
}

WAVEFORM_TYPES = ("continuous_wave", "chirp_pulse_train")

ECHO_WAVEFORM_DEFAULTS = {
    "continuous_wave": {
        "amplitude": 1.0,
    },
    "chirp_pulse_train": {
        "bandwidth_hz": 1.0e5,
        "amplitude": 1.0,
        "baseband_convention": "centered",
    },
}

INVERSION_FIELD_ORDER = (
    "stft_window_samples",
    "stft_overlap_fraction",
    "cpi_duration_s",
    "cpi_hop_duration_s",
    "period_min_s",
    "period_max_s",
    "period_grid_size",
    "period_time_role",
    "motion_compensation",
    "harmonics",
)
INVERSION_CW_ONLY = {"stft_window_samples", "stft_overlap_fraction"}
INVERSION_CHIRP_ONLY = {
    "cpi_duration_s",
    "cpi_hop_duration_s",
    "motion_compensation",
    "period_time_role",
    "harmonics",
}
ECHO_MESH_ONLY = ("model_path", "target", "scattering_power", "scattering_spot")

CARD_ORDER = {
    "observation": (
        "campaign",
        "target",
        "transmitter",
        "receiver",
        "radar_system",
        "transmit",
        "receive",
        "receiver_sampling",
        "plan",
        "geometry",
    ),
    "echo": (
        "compute",
        "radar_parameters",
        "noise",
        "echo_options",
        "target",
        "scattering_spot",
    ),
    "inversion": ("spectrum", "period_search"),
}

_ALL_STATE_FIELD_KEYS = {key for fields in STATE_FIELDS.values() for key in fields} - {"id"}


def _reject_observation_waveform(observation) -> None:
    if isinstance(observation, dict) and "waveform" in observation:
        from observation.src.config_normalize import OBSERVATION_WAVEFORM_DEPRECATED

        raise ValueError(OBSERVATION_WAVEFORM_DEPRECATED)


class ScheduleTimelineWidget(QWidget):
    """Three-track campaign preview drawn at native widget resolution."""

    _COLORS = {
        "axis": QColor("#7b8794"),
        "empty": QColor("#e6ebf0"),
        "visible": QColor("#3f9a69"),
        "hidden": QColor("#cf6767"),
        "unknown": QColor("#aeb7c2"),
        "run": QColor("#2f67a2"),
        "reserve": QColor("#b9d3ed"),
        "adc": QColor("#8060a8"),
        "text": QColor("#526273"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._payload: dict = {}
        self.setObjectName("scheduleTimeline")
        self.setMinimumHeight(112)
        self.setSizePolicy(EXPANDING, FIXED)

    def clear(self) -> None:
        self._payload = {}
        self.update()

    def set_plan(self, payload: dict) -> None:
        self._payload = copy.deepcopy(payload)
        self.update()

    @staticmethod
    def _intervals(payload: dict, key: str) -> list[tuple[float, float]]:
        result = []
        for item in payload.get(key) or []:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                result.append((float(item[0]), float(item[1])))
        return result

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(QFont("Microsoft YaHei", 9))
        duration = float(self._payload.get("campaign_duration_s") or 0.0)
        left = 66.0
        right = max(left + 10.0, float(self.width()) - 18.0)
        axis_right = right - 7.0
        width = axis_right - left
        rows = (("可见性", 24.0), ("Run", 57.0), ("ADC 估计", 90.0))

        painter.setPen(self._COLORS["text"])
        for label, y in rows:
            painter.drawText(QRectF(7.0, y - 10.0, 56.0, 20.0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), label)
            painter.setPen(QPen(self._COLORS["empty"], 2.0))
            painter.drawLine(QPointF(left, y), QPointF(axis_right, y))
            painter.setPen(self._COLORS["text"])
        if duration <= 0.0:
            painter.end()
            return

        def x_at(value: float) -> float:
            return left + width * min(1.0, max(0.0, value / duration))

        def fill_intervals(intervals, y, color, height=10.0, minimum_width=0.0):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            for start, stop in intervals:
                x0 = x_at(start)
                x1 = x_at(stop)
                if stop > start and x1 - x0 < minimum_width:
                    x1 = min(axis_right, x0 + minimum_width)
                if x1 > x0:
                    painter.drawRoundedRect(QRectF(x0, y - height / 2.0, x1 - x0, height), 1.5, 1.5)

        visibility_y = rows[0][1]
        visibility_applicable = bool(self._payload.get("visibility_applicable", True))
        if visibility_applicable and not bool(self._payload.get("visibility_computed", True)):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._COLORS["unknown"], Qt.BrushStyle.BDiagPattern))
            painter.drawRect(QRectF(left, visibility_y - 5.0, width, 10.0))
        else:
            fill_intervals([(0.0, duration)], visibility_y, self._COLORS["hidden"])
            fill_intervals(
                self._intervals(self._payload, "visibility_windows_elapsed_s"),
                visibility_y,
                self._COLORS["visible"],
            )

        selected = self._intervals(self._payload, "run_intervals_elapsed_s")
        reservations = self._intervals(self._payload, "reservation_intervals_elapsed_s")
        run_y = rows[1][1]
        painter.setPen(Qt.PenStyle.NoPen)
        for tx, reserve in zip(selected, reservations):
            x0 = x_at(reserve[0])
            tx_end = x_at(tx[1])
            reserve_end = x_at(reserve[1])
            # Keep both layers legible when their true widths are below one display pixel.
            reserve_end = min(axis_right, max(reserve_end, tx_end + 4.0, x0 + 8.0))
            painter.setBrush(QBrush(self._COLORS["reserve"]))
            painter.drawRoundedRect(QRectF(x0, run_y - 7.0, max(0.0, reserve_end - x0), 14.0), 1.5, 1.5)
            tx_start = x_at(tx[0])
            tx_end = min(axis_right, max(tx_end, tx_start + 4.0))
            painter.setBrush(QBrush(self._COLORS["run"]))
            painter.drawRoundedRect(QRectF(tx_start, run_y - 5.0, max(0.0, tx_end - tx_start), 10.0), 1.5, 1.5)

        fill_intervals(
            self._intervals(self._payload, "adc_preview_intervals_elapsed_s"),
            rows[2][1],
            self._COLORS["adc"],
            height=8.0,
            minimum_width=2.0,
        )

        painter.setPen(QPen(self._COLORS["axis"], 1.0))
        painter.drawLine(QPointF(left, 10.0), QPointF(left, 101.0))
        painter.drawText(QPointF(left - 5.0, 108.0), "T₀")
        painter.drawText(QPointF(axis_right - 13.0, 108.0), "T₁")
        arrow = QPolygonF(
            [
                QPointF(axis_right, visibility_y - 4.0),
                QPointF(right, visibility_y),
                QPointF(axis_right, visibility_y + 4.0),
            ]
        )
        painter.setBrush(QBrush(self._COLORS["axis"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(arrow)
        painter.end()


class ScheduleFeedbackWidget(QFrame):
    """Compact capacity and timeline preview for automatic Run selection."""

    def __init__(self, refresh_callback, parent=None):
        super().__init__(parent)
        self.setObjectName("scheduleFeedback")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(7)
        header = QHBoxLayout()
        self.summary = QLabel("正在计算观测计划…")
        self.summary.setObjectName("scheduleFeedbackSummary")
        self.summary.setWordWrap(True)
        self.refresh_button = QPushButton("刷新预览")
        self.refresh_button.setFixedHeight(28)
        self.refresh_button.clicked.connect(refresh_callback)
        header.addWidget(self.summary, 1)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)
        self.timeline = ScheduleTimelineWidget()
        layout.addWidget(self.timeline)
        self.detail = QLabel("绿色/红色：可见/不可见　深蓝：发射 Run　浅蓝：调度预留　紫色：ADC 估计窗")
        self.detail.setObjectName("scheduleFeedbackDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

    def show_stale(self, message="参数已更新，请刷新预览") -> None:
        self.summary.setText(message)
        self._set_state("stale")

    def show_pending(self, message="参数已更新，请刷新预览") -> None:
        self.show_stale(message)

    def show_error(self, message: str) -> None:
        self.summary.setText(f"无法生成预览：{message}")
        self._set_state("error")
        self.timeline.clear()

    def show_plan(self, payload: dict, requested_count: int) -> None:
        maximum = payload.get("max_run_count")
        occupied = payload.get("occupied_duration_s")
        if maximum is None:
            self.summary.setText("手动选时不计算自动 Run 数量上限")
            self._set_state("neutral")
        elif not bool(payload.get("run_feasible", True)):
            self.summary.setText(
                (payload.get("run_feasibility_error") or "单次 Run 不可行")
                + "；因此当前 Run 数量上限为 0"
            )
            self._set_state("error")
        else:
            state = "可行" if requested_count <= maximum else "超出上限"
            capacity_label = (
                f"近似可排列最多 {maximum} 次 Run"
                if bool(payload.get("capacity_is_approximate"))
                else f"正式计划最多 {maximum} 次 Run"
            )
            extra = f"；每次调度占用 {occupied:.6g} s" if occupied is not None else ""
            official_note = (
                "；该上限来自近似传播时延，不表示正式计划已通过光行时解算"
                if bool(payload.get("capacity_is_approximate")) and requested_count <= maximum
                else ""
            )
            self.summary.setText(
                f"{capacity_label}；当前设置 {requested_count} 次（{state}）{extra}{official_note}"
            )
            self._set_state("ok" if requested_count <= maximum else "error")
        self.timeline.set_plan(payload)
        if not bool(payload.get("visibility_applicable", True)):
            visibility_note = "自定义直角坐标：不应用地平可见性约束"
        elif not bool(payload.get("visibility_computed", True)):
            visibility_note = "灰色斜纹：当前坐标无法计算几何可见性"
            if bool(payload.get("allow_unobservable", False)):
                visibility_note += "，已按“包含非可见时段”忽略该约束"
        else:
            visibility_note = "绿色/红色：可见/不可见"
        feasibility_note = (
            "　当前轨道仅显示请求的假设布局，不表示可执行。"
            if not bool(payload.get("run_feasible", True))
            else ""
        )
        self.detail.setText(
            visibility_note
            + "　深蓝：发射 Run　浅蓝：调度预留尾部（过短时放大到 4 px）　紫色：近似 ADC 窗"
            + feasibility_note
        )

    def _set_state(self, state: str) -> None:
        self.summary.setProperty("previewState", state)
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)


def _format_gate_delay(gate_s: float) -> str:
    if gate_s <= 0.0:
        return "0 s"
    if gate_s >= 1.0:
        return f"{gate_s:.3f} s"
    if gate_s >= 1e-3:
        return f"{gate_s * 1e3:.3f} ms"
    if gate_s >= 1e-6:
        return f"{gate_s * 1e6:.3f} µs"
    return f"{gate_s * 1e9:.3f} ns"


def _format_range_resolution(range_m: float) -> str:
    if range_m >= 1000.0:
        return f"{range_m / 1000.0:.3g} km"
    return f"{range_m:.3g} m"


def _widget_finite(widget) -> float | None:
    if not isinstance(widget, UnitValueWidget):
        return None
    try:
        value = float(widget.value())
    except (NumericInputError, TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def _range_gate_readout_text(widgets: dict, config: dict) -> str:
    """Read-only stationary conversion shown under the collection path gate."""

    from observation.src.light_time import C
    from observation.src.planning import stationary_chirp_gate

    extent = _widget_finite(widgets.get("observation.target.extent_path_m"))
    pulse = _widget_finite(widgets.get("observation.transmit.pulse_width_s"))
    sample_rate = _widget_finite(widgets.get("observation.receiver_sampling.fast_sample_rate_hz"))
    if (
        extent is None
        or pulse is None
        or sample_rate is None
        or extent < 0.0
        or pulse <= 0.0
        or sample_rate <= 0.0
    ):
        return "采集路径窗、脉宽或采样率还不能换算。"
    gate_s, n_pre, _n_after, fast_count = stationary_chirp_gate(extent, pulse, sample_rate)
    text = (
        f"静止时标：门时延 {_format_gate_delay(gate_s)}（{n_pre} 点），整行 {fast_count} 点"
    )
    waveform = ((config or {}).get("echo") or {}).get("waveform") or {}
    bandwidth = waveform.get("bandwidth_hz")
    try:
        bandwidth_hz = float(bandwidth)
    except (TypeError, ValueError):
        bandwidth_hz = float("nan")
    if math.isfinite(bandwidth_hz) and bandwidth_hz > 0.0:
        text += f"，压缩后距离分辨 {_format_range_resolution(C / (2.0 * bandwidth_hz))}"
    return text


class ParameterForm(QWidget):
    """Scrollable semantic cards for the full pipeline config."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.field_widgets: dict[str, QWidget] = {}
        self._cards: list[ParameterCards] = []
        self._active_stage = ""
        self._config: dict = {}
        self._mesh_echo_draft: dict | None = None
        self._noise_draft: dict | None = None
        self._schedule_draft: dict = {}
        self.schedule_feedback: ScheduleFeedbackWidget | None = None
        self.range_gate_readout: QLabel | None = None
        self._schedule_preview_dirty = True
        self._scroll_floor = 0
        self.monostatic = False
        self.point_target = False
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
        point_target: bool = False,
        focus_path: str | None = None,
        preserve_scroll: bool = True,
        retain_scroll_extent: bool = False,
    ) -> None:
        scroll_bar = self.scroll.verticalScrollBar()
        scroll_value = scroll_bar.value() if preserve_scroll else 0
        previous_extent = max(self.canvas.height(), scroll_bar.maximum() + self.scroll.viewport().height()) if retain_scroll_extent else 0
        self._scroll_floor = previous_extent
        self.canvas.setMinimumHeight(previous_extent)
        self._config = config
        self.field_widgets.clear()
        self._cards.clear()
        self.schedule_feedback = None
        self.range_gate_readout = None
        self.monostatic = bool(monostatic)
        self.point_target = bool(point_target)
        while self.canvas_layout.count():
            item = self.canvas_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Hide while still parented. setParent(None) would promote a
                # visible widget into a brief top-level window.
                widget.hide()
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
            self.canvas_layout.activate()
            self._apply_canvas_height()
            if focus_path:
                widget = self.field_widgets.get(focus_path)
                if widget is not None:
                    widget.setFocus(Qt.FocusReason.OtherFocusReason)
            if preserve_scroll:
                scroll_bar.setValue(scroll_value)

        QTimer.singleShot(0, _restore_view)
        if stage == "observation":
            QTimer.singleShot(0, self._connect_schedule_feedback_updates)
            QTimer.singleShot(0, self._connect_range_gate_readout)

    def collect(self, *, strip: bool = True) -> dict:
        # Start from the live model so hidden conditional fields are not wiped.
        config = copy.deepcopy(self._config) if self._config else {}
        geodetic_rotation: dict[str, bool] = {}
        linear_motion: dict[str, bool] = {}
        random_selection = None
        noise_enabled = None
        for path, widget in self.field_widgets.items():
            value = self._widget_value(widget)
            if path.endswith(".geodetic_time_dependent"):
                geodetic_rotation[path.split(".")[1]] = bool(value)
                continue
            if path.endswith(".linear_motion"):
                linear_motion[path.split(".")[1]] = bool(value)
                continue
            if path == "observation.schedule.random_selection":
                random_selection = bool(value)
                continue
            if path == "echo.noise_enabled":
                # Presentation-only toggle; maps to snr_db null vs numeric.
                noise_enabled = bool(value)
                continue
            assign_path(config, path, value)

        observation = config.get("observation")
        _reject_observation_waveform(observation)
        if isinstance(observation, dict):
            schedule = observation.get("schedule")
            if isinstance(schedule, dict) and schedule.get("selection") != "manual" and random_selection is not None:
                schedule["selection"] = "random_visible_time" if random_selection else "equal_visible_time"
            if isinstance(schedule, dict) and schedule.get("selection") == "manual":
                visibility = observation.get("visibility")
                if isinstance(visibility, dict):
                    visibility.pop("allow_unobservable_for_simulation", None)
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
            self._normalize_visibility_for_stations(observation)
            target = observation.get("target")
            if isinstance(target, dict):
                if target.get("state") == "static" and "target" in linear_motion:
                    target["state"] = "linear" if linear_motion["target"] else "static"
                observation["target"] = self._normalize_state_group(target, role="target")
        echo = config.get("echo")
        if isinstance(echo, dict):
            if noise_enabled is not None:
                self._apply_noise_enabled(echo, noise_enabled)
            self._normalize_echo_stage(echo)
        if strip:
            self._strip_inapplicable_fields(config)
        return config

    @staticmethod
    def _station_uses_local_horizon(station) -> bool:
        if not isinstance(station, dict):
            return False
        return str(station.get("state", "static")).lower() not in {"static", "linear"}

    @classmethod
    def _normalize_visibility_for_stations(cls, observation: dict) -> None:
        transmitter = observation.get("transmitter") or {}
        receiver = observation.get("receiver") or transmitter
        tx_horizon = cls._station_uses_local_horizon(transmitter)
        rx_horizon = cls._station_uses_local_horizon(receiver)
        if not (tx_horizon or rx_horizon):
            observation.pop("visibility", None)
            return
        visibility = observation.setdefault("visibility", {})
        visibility.setdefault("sample_step_s", 30.0)
        visibility.setdefault("allow_unobservable_for_simulation", False)
        if tx_horizon:
            visibility.setdefault("min_tx_elevation_deg", 0.0)
        else:
            visibility.pop("min_tx_elevation_deg", None)
        if rx_horizon:
            visibility.setdefault("min_rx_elevation_deg", 0.0)
        else:
            visibility.pop("min_rx_elevation_deg", None)

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

    def _content_bottom(self) -> int:
        margin_bottom = self.canvas_layout.contentsMargins().bottom()
        needed = margin_bottom
        for cards in self._cards:
            if cards.isHidden():
                continue
            needed = max(
                needed,
                cards.mapTo(self.canvas, cards.rect().bottomRight()).y() + margin_bottom,
            )
        return needed

    def _apply_canvas_height(self) -> None:
        """Size the scroll canvas to the cards, and allow that height to shrink.

        sizeHint includes the previous minimumHeight, so using it as the next
        minimum locks the tall single-column measurement from startup.
        """

        needed = max(self._content_bottom(), getattr(self, "_scroll_floor", 0))
        if self.canvas.minimumHeight() != needed:
            self.canvas.setMinimumHeight(needed)
        viewport_h = self.scroll.viewport().height()
        target = max(needed, viewport_h)
        if self.canvas.height() != target:
            self.canvas.resize(self.canvas.width(), target)

    def _relayout(self) -> None:
        for canvas in self._cards:
            if not getattr(canvas, "_reflowing", False):
                canvas.reflow()
        self.canvas_layout.activate()
        self._apply_canvas_height()

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
                if path == "scattering_model":
                    continue
                if path == "model_path":
                    section = "target"
                elif path == "scattering_power":
                    section = "scattering_spot"
                elif path in {"noise_enabled", "snr_db", "seed"}:
                    section = "noise"
                else:
                    section = "echo_options"
                sections.setdefault(section, []).append((path, value))
            if "point_target" in sections:
                sections.setdefault("target", []).extend(sections.pop("point_target"))
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
                "geometry": ("ephemeris",),
            }
            for target, sources in merges.items():
                merged = []
                for source in sources:
                    merged.extend(sections.pop(source, []))
                if merged:
                    sections[target] = merged
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
            waveform_type = self._active_waveform_type()
            cw_only = INVERSION_CW_ONLY
            chirp_only = INVERSION_CHIRP_ONLY
            for section_name, fields in list(sections.items()):
                filtered = []
                for path, value in fields:
                    if waveform_type == "continuous_wave" and path in chirp_only:
                        continue
                    if waveform_type == "chirp_pulse_train" and path in cw_only:
                        continue
                    filtered.append((path, value))
                if filtered:
                    sections[section_name] = filtered
                else:
                    sections.pop(section_name, None)
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
                    state = str(group.get("state", "static"))
                    fields.append((f"{group_name}.state", "static" if state == "linear" else state))
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
        elif group_name == "target" and state in {"static", "linear"}:
            position_key = "position0_m" if state == "linear" else "position_m"
            fields.append((f"{group_name}.{position_key}", self._state_field_value(position_key, group)))
            fields.append((f"{group_name}.linear_motion", state == "linear"))
            if state == "linear":
                fields.append((f"{group_name}.velocity_m_s", self._state_field_value("velocity_m_s", group)))
        else:
            for child_key in STATE_FIELDS.get(state, ()):
                if child_key == "object_type":
                    continue
                fields.append(
                    (
                        f"{group_name}.{child_key}",
                        group.get(child_key, copy.deepcopy(STATE_DEFAULTS.get(child_key, ""))),
                    )
                )
            # target.extent_path_m is the chirp collection path gate. It is
            # presented on the receiver_sampling card, not on the target body card.
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
        header.setSizePolicy(EXPANDING, FIXED)
        outer.addWidget(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        grid.setColumnMinimumWidth(0, 96)
        grid.setColumnStretch(1, 1)
        self._render_fields(grid, stage, group_name, fields)
        outer.addLayout(grid)
        if stage == "observation" and group_name == "plan":
            self.schedule_feedback = ScheduleFeedbackWidget(
                self._refresh_schedule_feedback, card
            )
            outer.addWidget(self.schedule_feedback)
        if stage == "observation" and group_name == "receiver_sampling":
            readout = QLabel()
            readout.setObjectName("rangeGateReadout")
            readout.setWordWrap(True)
            readout.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            readout.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            outer.addWidget(readout)
            self.range_gate_readout = readout
        card.setSizePolicy(EXPANDING, FIXED)
        return card

    def _connect_schedule_feedback_updates(self) -> None:
        feedback = self.schedule_feedback
        if feedback is None:
            return
        for widget in self.field_widgets.values():
            if isinstance(widget, UnitValueWidget):
                widget.edit.editingFinished.connect(self._mark_schedule_feedback_stale)
                if widget.unit_combo is not None:
                    widget.unit_combo.currentIndexChanged.connect(self._mark_schedule_feedback_stale)
            elif isinstance(widget, VectorValueWidget):
                for edit in widget.edits:
                    edit.editingFinished.connect(self._mark_schedule_feedback_stale)
            elif isinstance(widget, QLineEdit):
                widget.editingFinished.connect(self._mark_schedule_feedback_stale)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._mark_schedule_feedback_stale)
            elif isinstance(widget, BooleanFieldWidget):
                widget.checkbox.toggled.connect(self._mark_schedule_feedback_stale)
        self._schedule_preview_dirty = True
        feedback.show_stale("请点击「刷新预览」生成观测计划")

    def _connect_range_gate_readout(self) -> None:
        if self.range_gate_readout is None:
            return
        for path in (
            "observation.target.extent_path_m",
            "observation.receiver_sampling.fast_sample_rate_hz",
            "observation.transmit.pulse_width_s",
        ):
            widget = self.field_widgets.get(path)
            if isinstance(widget, UnitValueWidget):
                widget.edit.textChanged.connect(self._refresh_range_gate_readout)
                widget.edit.editingFinished.connect(self._refresh_range_gate_readout)
                if widget.unit_combo is not None:
                    widget.unit_combo.currentIndexChanged.connect(self._refresh_range_gate_readout)
        self._refresh_range_gate_readout()

    def _refresh_range_gate_readout(self, *_args) -> None:
        label = self.range_gate_readout
        if label is None:
            return
        label.setText(_range_gate_readout_text(self.field_widgets, self._config))
        self._relayout()

    def _mark_schedule_feedback_stale(self, *_args) -> None:
        feedback = self.schedule_feedback
        if feedback is None or self._active_stage != "observation":
            return
        if self._schedule_preview_dirty:
            return
        self._schedule_preview_dirty = True
        feedback.show_stale("参数已更新，请刷新预览")

    def _refresh_schedule_feedback(self, *_args, **_kwargs) -> None:
        feedback = self.schedule_feedback
        if feedback is None or self._active_stage != "observation":
            return
        try:
            config = self.collect(strip=False)
            observation = config.get("observation", {})
            schedule = observation.get("schedule", {})
            if schedule.get("selection") == "manual":
                feedback.show_plan({}, 0)
                self._schedule_preview_dirty = False
                self._relayout()
                return
            from observation.src.campaign_planning import resolve_campaign_run_plan

            plan = resolve_campaign_run_plan(
                observation, allow_infeasible_preview=True
            )
            feedback.show_plan(
                plan.json_payload(observation.get("transmitter")),
                int(schedule.get("run_count", 0)),
            )
            self._schedule_preview_dirty = False
            self._relayout()
        except Exception as exc:
            feedback.show_error(str(exc))
            self._schedule_preview_dirty = False
            self._relayout()

    def _render_fields(self, grid: QGridLayout, stage: str, group_name: str, fields: list) -> None:
        row = 0
        label_width = 108
        handled: set[str] = set()
        field_values = {path: value for path, value in fields}
        for relative_path, value in fields:
            if relative_path in handled:
                continue
            absolute = f"{stage}.{relative_path}"
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

            if stage == "observation" and group_name == "target" and key == "state":
                label = QLabel("位置来源")
                label.setObjectName("fieldLabel")
                label.setMinimumWidth(label_width)
                widget = self._field_widget(relative_path, value)
                widget.setToolTip(absolute)
                self.field_widgets[absolute] = widget
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1)
                handled.add(relative_path)
                row += 1
                if value == "static":
                    row = self._render_station_state_children(
                        grid, stage, group_name, "cartesian", field_values, handled, label_width, row
                    )
                continue

            if relative_path.endswith(".initial_geodetic_coordinates"):
                continue
            if key in {"lat_deg", "lon_deg", "height_m", "geodetic_time_dependent", "linear_motion"}:
                # Station children are rendered with the coordinate-format row.
                if stage == "observation" and group_name in STATION_GROUPS:
                    continue

            text = FIELD_LABELS.get(key, key)
            if group_name == "plan" and relative_path == "schedule.start_utc":
                text = "发射选时范围开始"
            elif group_name == "plan" and relative_path == "schedule.end_utc":
                text = "发射选时范围结束"
            label = QLabel(text)
            label.setObjectName("fieldLabel")
            label.setMinimumWidth(label_width)
            widget = self._field_widget(relative_path, value)
            tooltip = self._field_tooltip(key, absolute)
            widget.setToolTip(tooltip)
            label.setToolTip(tooltip)
            self.field_widgets[absolute] = widget
            if isinstance(widget, BooleanFieldWidget):
                if relative_path == "scattering_spot.enabled":
                    widget.checkbox.toggled.connect(lambda _checked: self._on_spot_enabled_changed())
                if relative_path == "noise_enabled":
                    widget.checkbox.toggled.connect(lambda _checked: self._on_noise_enabled_changed())
                if group_name == "plan" and key in {"allow_unobservable_for_simulation", "random_selection"}:
                    widget.checkbox.setText(text)
                    label.deleteLater()
                    grid.addWidget(widget, row, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
                else:
                    grid.addWidget(label, row, 0)
                    grid.addWidget(widget, row, 1, alignment=Qt.AlignmentFlag.AlignLeft)
            elif isinstance(widget, (VectorValueWidget, DirectionBodyWidget)):
                section = SubsectionPanel(text, absolute, label_width)
                section.heading.setBuddy(widget)
                section.add_widget(widget)
                label.deleteLater()
                grid.addWidget(section.heading, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
                grid.addWidget(section, row, 1)
            elif key in {"model_path", "runs"} or (key.endswith("_utc") and group_name != "plan"):
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
            toggle_widget.checkbox.setText(FIELD_LABELS["geodetic_time_dependent"])
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
        toggle_widget.checkbox.setText(FIELD_LABELS["linear_motion"])
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

    def _field_tooltip(self, key: str, absolute: str) -> str:
        hint = FIELD_TOOLTIPS.get(key)
        if hint:
            return f"{hint}\n配置字段：{absolute}"
        return absolute

    def _field_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        if isinstance(value, bool) or key in {"geodetic_time_dependent", "linear_motion"}:
            widget = BooleanFieldWidget(bool(value))
            if full_path == "schedule.random_selection":
                widget.checkbox.toggled.connect(lambda _checked: self._on_schedule_selection_changed(focus_path="observation.schedule.random_selection"))
            return widget
        if key in CHOICES or (key == "state"):
            combo = NoWheelComboBox()
            choices = self._choices_for_field(full_path)
            current = format_value(value)
            if full_path == "schedule.selection" and current != "manual":
                current = "automatic"
            for item in choices:
                data = "true" if item is True else "false" if item is False else str(item)
                label = "手动坐标" if full_path == "target.state" and data == "static" else OPTION_LABELS.get(data, data)
                combo.addItem(label, data)
            existing = [combo.itemData(i) for i in range(combo.count())]
            if current not in existing:
                # Preserve unknown values instead of silently rewriting config.
                combo.insertItem(0, OPTION_LABELS.get(current, current), current)
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
            if full_path == "scattering_model":
                combo.currentIndexChanged.connect(
                    lambda _index: self._on_scattering_model_changed()
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
        if key in NUMERIC_FIELD_KEYS:
            edit = NumericLineEdit(
                value,
                label=f"{self._active_stage}.{full_path}",
                integer=key in INTEGER_FIELD_KEYS,
            )
        else:
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
        if full_path == "schedule.selection":
            return ("manual", "automatic")
        if key != "state":
            return CHOICES[key]
        group_name = full_path.split(".", 1)[0]
        if self._active_stage == "observation" and group_name == "target":
            return ("static", "horizons_vectors")
        if self._active_stage == "observation" and group_name in STATION_GROUPS:
            return STATION_COORDINATE_CHOICES
        return CHOICES[key]

    def _custom_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        unit = FIELD_UNITS.get(key)
        if key == "scattering_power" and isinstance(value, list) and len(value) == 2:
            return VectorValueWidget(value, ("发射照明", "接收散射"), label=full_path)
        if key == "spin_pole_icrs_deg" and isinstance(value, list):
            return VectorValueWidget(value, ("赤经", "赤纬"), "°", label=full_path)
        if key == "spin_pole_ecliptic_deg" and isinstance(value, list):
            return VectorValueWidget(value, ("黄经", "黄纬"), "°", label=full_path)
        if key == "direction_body" and isinstance(value, list):
            return DirectionBodyWidget(value, "zh")
        if isinstance(value, list) and len(value) in {2, 3} and all(
            isinstance(item, (int, float)) for item in value
        ):
            labels = ("x", "y", "z")[: len(value)]
            return VectorValueWidget(value, labels, unit, label=full_path)
        if key in UNIT_CHOICES and isinstance(value, (int, float)):
            return UnitValueWidget(value, UNIT_CHOICES[key], editable_unit=True, label=full_path)
        if unit and (value is None or isinstance(value, (int, float))):
            return UnitValueWidget(value, ((unit, 1.0),), editable_unit=False, label=full_path)
        return None

    def _widget_value(self, widget):
        if isinstance(widget, BooleanFieldWidget):
            return widget.value()
        if isinstance(widget, (UnitValueWidget, VectorValueWidget, DirectionBodyWidget)):
            return widget.value()
        if isinstance(widget, NumericLineEdit):
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
        hidden_spin = (
            "target.spin_pole_icrs_deg" if frame == "ecliptic" else "target.spin_pole_ecliptic_deg"
        )
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

        noise_enabled = stage_data.get("snr_db") is not None
        noise_fields = [
            (path, value)
            for path, value in sections.get("noise", [])
            if path != "noise_enabled" and not (path == "snr_db" and value is None)
        ]
        if not noise_enabled:
            noise_fields = [
                (path, value) for path, value in noise_fields if path not in {"snr_db", "seed"}
            ]
        noise_fields.insert(0, ("noise_enabled", noise_enabled))
        sections["noise"] = noise_fields
        # Keep SNR/seed out of the RF card so spacing there stays unchanged.
        if "radar_parameters" in sections:
            sections["radar_parameters"] = [
                (path, value)
                for path, value in sections["radar_parameters"]
                if path not in {"noise_enabled", "snr_db", "seed"}
            ]
            if not sections["radar_parameters"]:
                sections.pop("radar_parameters", None)

        # Waveform type lives on the global combo as echo.waveform.type.
        waveform_type = self._active_waveform_type(stage_data)
        scattering_model = str(stage_data.get("scattering_model", "mesh")).lower()
        if self.point_target:
            scattering_model = "point_target"
        for group_name, fields in list(sections.items()):
            filtered = []
            for path, value in fields:
                if path == "waveform.type":
                    continue
                if waveform_type == "continuous_wave" and path in ECHO_CHIRP_ONLY_FIELDS:
                    continue
                if scattering_model == "point_target":
                    if path in {
                        "model_path",
                        "scattering_power",
                        "scattering_spot.enabled",
                        "scattering_spot.direction_body",
                        "scattering_spot.radius_deg",
                        "scattering_spot.strength",
                        "target.rotation_period_s",
                        "target.initial_phase_deg",
                        "target.spin_pole_frame",
                        "target.spin_pole_icrs_deg",
                        "target.spin_pole_ecliptic_deg",
                    }:
                        continue
                elif path.startswith("point_target."):
                    continue
                filtered.append((path, value))
            sections[group_name] = filtered
            if not filtered:
                sections.pop(group_name, None)
        return sections

    def _filter_observation_sections(self, stage_data: dict, sections: dict[str, list]) -> dict[str, list]:
        if "schedule" in stage_data:
            waveform_type = "chirp_pulse_train"
        elif "receive" in stage_data:
            waveform_type = "continuous_wave"
        else:
            waveform_type = self._active_waveform_type()
        if waveform_type == "continuous_wave":
            for name in ("radar_system", "receiver_sampling", "plan", "transmit"):
                sections.pop(name, None)
        else:
            sections.pop("receive", None)
            # The chirp collection path gate stays under target in JSON and is
            # shown on this card next to the fast-time sample rate.
            target_group = stage_data.get("target") or {}
            extent = target_group.get("extent_path_m", 0.0)
            sampling_fields = sections.setdefault("receiver_sampling", [])
            if not any(path == "target.extent_path_m" for path, _ in sampling_fields):
                sampling_fields.append(("target.extent_path_m", extent))

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

        # Drop decorative / legacy campaign identity fields.
        campaign_fields = sections.get("campaign", [])
        if campaign_fields:
            drop = {
                "campaign.id",
                "campaign.target_id",
                "campaign.target_name",
                "campaign.target_object_type",
                "campaign.query_start_utc",
                "campaign.query_end_utc",
            }
            kept = [(path, value) for path, value in campaign_fields if path not in drop]
            if kept:
                sections["campaign"] = kept
            else:
                sections.pop("campaign", None)

        schedule = stage_data.get("schedule", {})
        selection = str(schedule.get("selection", "manual"))
        plan = sections.get("plan", [])
        if plan:
            transmitter = stage_data.get("transmitter") or {}
            receiver = stage_data.get("receiver") or transmitter
            tx_horizon = self._station_uses_local_horizon(transmitter)
            rx_horizon = self._station_uses_local_horizon(receiver)
            visibility_applicable = tx_horizon or rx_horizon
            seed_value = next((value for path, value in plan if path == "schedule.random_seed"), 20260904)
            plan = [
                (path, value)
                for path, value in plan
                if path not in {"visibility.allow_unobservable_for_simulation", "schedule.random_seed"}
            ]
            if not visibility_applicable:
                plan = [(path, value) for path, value in plan if not path.startswith("visibility.")]
            else:
                if not tx_horizon:
                    plan = [(path, value) for path, value in plan if path != "visibility.min_tx_elevation_deg"]
                if not rx_horizon:
                    plan = [(path, value) for path, value in plan if path != "visibility.min_rx_elevation_deg"]
            if selection != "manual":
                if visibility_applicable:
                    plan.append(
                        (
                            "visibility.allow_unobservable_for_simulation",
                            bool(
                                (stage_data.get("visibility") or {}).get(
                                    "allow_unobservable_for_simulation", False
                                )
                            ),
                        )
                    )
                plan.append(("schedule.random_selection", selection == "random_visible_time"))
                if selection == "random_visible_time":
                    plan.append(("schedule.random_seed", seed_value))
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

        # Hide station IDs; target ID only for Horizons.
        for group_name in ("transmitter", "receiver", "target"):
            fields = sections.get(group_name)
            if not fields:
                continue
            filtered = []
            for path, value in fields:
                if path.endswith(".id"):
                    if group_name == "target" and is_horizons:
                        filtered.append((path, value))
                    continue
                filtered.append((path, value))
            sections[group_name] = filtered

        return sections

    def _active_waveform_type(self, echo_stage: dict | None = None) -> str:
        echo = echo_stage if isinstance(echo_stage, dict) else None
        if echo is None and self._config:
            echo = self._config.get("echo")
        if isinstance(echo, dict):
            echo_type = (echo.get("waveform") or {}).get("type")
            if echo_type:
                if echo_type == "lfm_chirp":
                    raise ValueError("echo.waveform.type=lfm_chirp 已废弃；请使用 chirp_pulse_train")
                return str(echo_type)
        observation = self._config.get("observation", {}) if self._config else {}
        if isinstance(observation, dict):
            if "schedule" in observation:
                return "chirp_pulse_train"
            if "receive" in observation:
                return "continuous_wave"
        return "continuous_wave"

    def _strip_inapplicable_fields(self, config: dict) -> None:
        observation = config.get("observation")
        echo = config.get("echo")
        inversion = config.get("inversion")
        _reject_observation_waveform(observation)
        waveform_type = "continuous_wave"
        echo_type = None
        if isinstance(echo, dict):
            echo_type = (echo.get("waveform") or {}).get("type")
            if echo_type:
                waveform_type = str(echo_type)
        if echo_type is None and isinstance(observation, dict):
            if "schedule" in observation:
                waveform_type = "chirp_pulse_train"
            elif "receive" in observation:
                waveform_type = "continuous_wave"
        if waveform_type == "lfm_chirp":
            raise ValueError("echo.waveform.type=lfm_chirp 已废弃；请使用 chirp_pulse_train")
        if isinstance(observation, dict):
            if waveform_type == "continuous_wave":
                for key in ("schedule", "radar_system", "receiver_sampling", "transmit"):
                    observation.pop(key, None)
            elif waveform_type == "chirp_pulse_train":
                observation.pop("receive", None)
                schedule = observation.get("schedule")
                if isinstance(schedule, dict):
                    selection = str(schedule.get("selection", "manual"))
                    if selection == "manual":
                        for key in ("run_count", "run_duration_s", "random_seed"):
                            schedule.pop(key, None)
                    else:
                        schedule.pop("runs", None)
                        if selection != "random_visible_time":
                            schedule.pop("random_seed", None)
        if isinstance(echo, dict):
            echo.pop("noise_enabled", None)
            model = str(echo.get("scattering_model", "mesh")).lower()
            if model == "point_target":
                for key in ECHO_MESH_ONLY:
                    echo.pop(key, None)
            else:
                echo.pop("point_target", None)
            echo_waveform = echo.get("waveform")
            if isinstance(echo_waveform, dict) and waveform_type == "continuous_wave":
                for key in ("bandwidth_hz", "baseband_convention"):
                    echo_waveform.pop(key, None)
        if isinstance(inversion, dict):
            drop = INVERSION_CHIRP_ONLY if waveform_type == "continuous_wave" else INVERSION_CW_ONLY
            if waveform_type in {"continuous_wave", "chirp_pulse_train"}:
                for key in drop:
                    inversion.pop(key, None)

    def _apply_waveform_event_source(self, observation: dict, waveform_type: str) -> None:
        _reject_observation_waveform(observation)
        if waveform_type == "continuous_wave":
            schedule = observation.get("schedule") or {}
            receive = dict(observation.get("receive") or {})
            receive.setdefault(
                "start_utc",
                schedule.get("start_utc") or "2026-01-01T00:00:00Z",
            )
            receive.setdefault("duration_s", 60.0)
            receive.setdefault("sample_rate_hz", 16.0)
            observation["receive"] = receive
            for key in ("schedule", "radar_system", "receiver_sampling", "transmit"):
                observation.pop(key, None)
            return
        receive = observation.get("receive") or {}
        schedule = dict(observation.get("schedule") or {})
        start = receive.get("start_utc") or schedule.get("start_utc") or "2026-01-01T00:00:00Z"
        schedule.setdefault("start_utc", start)
        schedule.setdefault("end_utc", schedule.get("start_utc"))
        schedule.setdefault("selection", "manual")
        duration = float(receive.get("duration_s") or 30.0)
        schedule.setdefault(
            "runs",
            [{"tx_start_utc": schedule["start_utc"], "tx_duration_s": duration}],
        )
        observation["schedule"] = schedule
        observation.pop("receive", None)
        observation.setdefault(
            "radar_system",
            {"mode": "monostatic_switching", "switch_time_s": 1.0, "safety_margin_s": 1.0},
        )
        observation.setdefault(
            "receiver_sampling",
            {"fast_sample_rate_hz": 250000.0},
        )
        transmit = observation.setdefault("transmit", {})
        for key, value in OBSERVATION_TRANSMIT_DEFAULTS.items():
            transmit.setdefault(key, copy.deepcopy(value))

    def _normalize_echo_stage(self, echo: dict) -> None:
        target = echo.get("target")
        if isinstance(target, dict):
            frame = str(target.get("spin_pole_frame", "equatorial")).lower()
            if frame in {"icrs", "equtorial"}:
                raise ValueError(
                    "echo.target.spin_pole_frame 已废弃值 "
                    f"{frame!r}；请使用 equatorial 或 ecliptic"
                )
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
            raise ValueError("echo.waveform.type=lfm_chirp 已废弃；请使用 chirp_pulse_train")
        for key, value in ECHO_WAVEFORM_DEFAULTS.get(waveform_type, {}).items():
            waveform.setdefault(key, copy.deepcopy(value))

    def _normalize_observation_bodies(self, observation: dict) -> None:
        self._normalize_horizons_target(observation)
        target = observation.get("target")
        if isinstance(target, dict):
            observation["target"] = self._normalize_state_group(target, role="target")
            self._ensure_horizons_ephemeris(observation)
        for role in STATION_GROUPS:
            group = observation.get(role)
            if isinstance(group, dict):
                observation[role] = self._normalize_state_group(group, role=role)
        _reject_observation_waveform(observation)
        if "schedule" in observation:
            transmit = observation.setdefault("transmit", {})
            for key, value in OBSERVATION_TRANSMIT_DEFAULTS.items():
                transmit.setdefault(key, copy.deepcopy(value))
        else:
            observation.pop("transmit", None)

    def _normalize_horizons_target(self, observation: dict) -> None:
        target = observation.get("target")
        if not isinstance(target, dict):
            return
        value = target.get("object_type")
        if isinstance(value, str):
            normalized = HORIZONS_ID_TYPE_ALIASES.get(value.strip().lower(), value.strip())
            if normalized != value:
                target["object_type"] = normalized

    def _ensure_horizons_ephemeris(self, observation: dict) -> None:
        target = observation.get("target")
        if not isinstance(target, dict) or target.get("state") != "horizons_vectors":
            observation.pop("ephemeris", None)
            return
        ephemeris = observation.setdefault("ephemeris", {})
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
            if key == "id" and state != "horizons_vectors":
                continue
            if key in group:
                normalized[key] = group[key]
        normalized["state"] = state
        for key in STATE_FIELDS[state]:
            normalized[key] = self._state_field_value(key, group)
        for key, value in group.items():
            if key in normalized or key in _ALL_STATE_FIELD_KEYS:
                continue
            if key == "id" and state != "horizons_vectors":
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
        return copy.deepcopy(STATE_DEFAULTS.get(key, ""))

    def _sync_into_config(self) -> None:
        if not self._active_stage:
            return
        updated = self.collect()
        if self._active_stage == "observation" and self.monostatic:
            updated.setdefault("observation", {}).pop("receiver", None)
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
            point_target=self.point_target,
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
            point_target=self.point_target,
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
            point_target=self.point_target,
            focus_path="echo.scattering_spot.enabled",
            preserve_scroll=True,
        )

    def _on_noise_enabled_changed(self) -> None:
        # Match scattering-model toggles: commit without stripping unrelated stages.
        updated = self.collect(strip=False)
        self._config.clear()
        self._config.update(updated)
        echo = self._config.get("echo")
        if isinstance(echo, dict):
            self._normalize_echo_stage(echo)
            echo.pop("noise_enabled", None)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            point_target=self.point_target,
            focus_path="echo.noise_enabled",
            preserve_scroll=True,
        )

    def _apply_noise_enabled(self, echo: dict, enabled: bool) -> None:
        """Map the presentation checkbox onto snr_db without inventing a new schema key."""
        if enabled:
            if echo.get("snr_db") is None:
                draft = self._noise_draft or {}
                restored = draft.get("snr_db")
                echo["snr_db"] = 20.0 if restored is None else restored
                if "seed" in draft and draft["seed"] is not None:
                    echo["seed"] = draft["seed"]
            echo.setdefault("seed", 20250729)
            return
        if echo.get("snr_db") is not None or "seed" in echo:
            self._noise_draft = {
                "snr_db": echo.get("snr_db"),
                "seed": echo.get("seed"),
            }
        echo["snr_db"] = None

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
            point_target=self.point_target,
            focus_path=absolute,
            preserve_scroll=True,
        )

    def set_waveform_type(self, waveform_type: str) -> None:
        """Apply the global waveform choice and rebuild the active stage."""
        if waveform_type not in WAVEFORM_TYPES:
            raise ValueError(f"不支持的波形类型：{waveform_type}")
        updated = self.collect(strip=False)
        updated.setdefault("echo", {}).setdefault("waveform", {})["type"] = waveform_type
        self._commit_waveform_type(updated, waveform_type)

    def _commit_waveform_type(self, updated: dict, waveform_type: str) -> None:
        if self._active_stage == "observation" and self.monostatic:
            updated.setdefault("observation", {}).pop("receiver", None)
        self._config.clear()
        self._config.update(updated)
        observation = self._config.setdefault("observation", {})
        _reject_observation_waveform(observation)
        self._apply_waveform_event_source(observation, waveform_type)
        echo = self._config.setdefault("echo", {})
        echo_waveform = echo.setdefault("waveform", {})
        echo_waveform["type"] = waveform_type
        if waveform_type == "continuous_wave":
            for key in ("bandwidth_hz", "baseband_convention"):
                echo_waveform.pop(key, None)
        for key, value in ECHO_WAVEFORM_DEFAULTS.get(waveform_type, {}).items():
            echo_waveform.setdefault(key, copy.deepcopy(value))
        inversion = self._config.setdefault("inversion", {})
        if waveform_type == "continuous_wave":
            for key in INVERSION_CHIRP_ONLY:
                inversion.pop(key, None)
            inversion.setdefault("stft_window_samples", 256)
            inversion.setdefault("stft_overlap_fraction", 0.75)
        else:
            for key in INVERSION_CW_ONLY:
                inversion.pop(key, None)
            inversion.setdefault("cpi_duration_s", 16.0)
            inversion.setdefault("motion_compensation", "auto")
            inversion.setdefault("period_time_role", "scatter_centroid")
        self._normalize_echo_stage(echo)
        self._strip_inapplicable_fields(self._config)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            point_target=self.point_target,
            preserve_scroll=True,
        )

    def _capture_schedule_draft(self) -> None:
        schedule = (self._config.get("observation") or {}).get("schedule") or {}
        for key in ("runs", "run_count", "run_duration_s", "random_seed"):
            if key in schedule:
                self._schedule_draft[key] = copy.deepcopy(schedule[key])
        seed_widget = self.field_widgets.get("observation.schedule.random_seed")
        if seed_widget is not None:
            self._schedule_draft["random_seed"] = self._widget_value(seed_widget)
        count_widget = self.field_widgets.get("observation.schedule.run_count")
        if count_widget is not None:
            self._schedule_draft["run_count"] = self._widget_value(count_widget)
        duration_widget = self.field_widgets.get("observation.schedule.run_duration_s")
        if duration_widget is not None:
            self._schedule_draft["run_duration_s"] = self._widget_value(duration_widget)

    def _on_schedule_selection_changed(self, *, focus_path: str | None = "observation.schedule.selection") -> None:
        self._capture_schedule_draft()
        self._sync_into_config()
        schedule = self._config.setdefault("observation", {}).setdefault("schedule", {})
        selection = str(schedule.get("selection", "manual"))
        if selection == "manual":
            if self._schedule_draft.get("runs"):
                schedule["runs"] = copy.deepcopy(self._schedule_draft["runs"])
            else:
                start = schedule.get("start_utc") or "2026-01-01T00:00:00Z"
                duration = float(self._schedule_draft.get("run_duration_s") or 30.0)
                schedule.setdefault(
                    "runs",
                    [{"tx_start_utc": start, "tx_duration_s": duration}],
                )
            for key in ("run_count", "run_duration_s", "random_seed"):
                schedule.pop(key, None)
        else:
            if selection == "automatic":
                schedule["selection"] = "equal_visible_time"
                selection = "equal_visible_time"
            schedule.pop("runs", None)
            schedule.setdefault("run_count", self._schedule_draft.get("run_count", 3))
            schedule.setdefault(
                "run_duration_s", self._schedule_draft.get("run_duration_s", 90.0)
            )
            if selection == "random_visible_time":
                schedule.setdefault(
                    "random_seed", self._schedule_draft.get("random_seed", 20260904)
                )
            else:
                schedule.pop("random_seed", None)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            point_target=self.point_target,
            focus_path=focus_path,
            preserve_scroll=True,
            retain_scroll_extent=True,
        )

    def _on_scattering_model_changed(self) -> None:
        updated = self.collect(strip=False)
        model = str((updated.get("echo") or {}).get("scattering_model", "mesh")).lower()
        self._apply_scattering_model(updated, model)

    def set_scattering_model(self, model: str) -> None:
        """Apply a scattering-model choice from the echo form."""
        if model not in {"mesh", "point_target"}:
            raise ValueError("散射模型必须是 mesh 或 point_target")
        updated = self.collect(strip=False)
        self._apply_scattering_model(updated, model)

    def _apply_scattering_model(self, updated: dict, model: str) -> None:
        if model not in {"mesh", "point_target"}:
            raise ValueError("散射模型必须是 mesh 或 point_target")
        self._config.clear()
        self._config.update(updated)
        echo = self._config.setdefault("echo", {})
        echo["scattering_model"] = model
        self.point_target = model == "point_target"
        if self.point_target:
            self._mesh_echo_draft = {
                key: copy.deepcopy(echo[key])
                for key in ECHO_MESH_ONLY
                if key in echo
            }
            echo.setdefault("point_target", {"amplitude_scale": 1.0})
            if isinstance(echo["point_target"], dict):
                echo["point_target"].setdefault("amplitude_scale", 1.0)
            for key in ECHO_MESH_ONLY:
                echo.pop(key, None)
        else:
            echo.pop("point_target", None)
            if self._mesh_echo_draft:
                for key, value in self._mesh_echo_draft.items():
                    echo.setdefault(key, copy.deepcopy(value))
            for key, value in MESH_ECHO_DEFAULTS.items():
                echo.setdefault(key, copy.deepcopy(value))
        self._strip_inapplicable_fields(self._config)
        self.render(
            self._config,
            self._active_stage,
            monostatic=self.monostatic,
            point_target=self.point_target,
            preserve_scroll=True,
        )
