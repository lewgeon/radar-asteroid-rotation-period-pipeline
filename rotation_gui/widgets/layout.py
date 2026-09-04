"""Responsive card canvas and lightweight subsection containment."""

from __future__ import annotations

from ..qt_compat import QFrame, QGridLayout, QLabel, QSize, QSizePolicy, Qt, QTimer, QVBoxLayout, QWidget

EXPANDING = QSizePolicy.Policy.Expanding
FIXED = QSizePolicy.Policy.Fixed

class ParameterCards(QWidget):
    """Stable semantic lanes, with explicit compact and wide-screen layouts."""

    def __init__(self, cards, stage, on_layout_changed=None):
        super().__init__()
        self.setObjectName("parameterCards")
        self.cards = cards
        self.stage = stage
        self.on_layout_changed = on_layout_changed
        self.layout_mode = "compact"
        self.column_count = 1
        self.gap = 14
        for card in cards:
            card.setParent(self)
            card.ensurePolished()
        self.card_minimum = max([360] + [card.minimumSizeHint().width() for card in cards])
        self.setMinimumWidth(self.card_minimum)
        self.setSizePolicy(EXPANDING, FIXED)
        QTimer.singleShot(0, self.reflow)

    def sizeHint(self):
        return QSize(self.card_minimum, self.minimumHeight())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        lanes_by_stage = {
            "observation": (("target", "transmitter", "receiver"), ("receive", "ephemeris", "solver")),
            "echo": (("compute", "radar_parameters"), ("target", "scattering_spot")),
            "inversion": (("spectrum",), ("period_search",)),
        }
        lanes = lanes_by_stage[self.stage]
        if self.width() < self.card_minimum * 2 + self.gap:
            lanes = (tuple(name for lane in lanes for name in lane),)
        self.layout_mode = "standard" if len(lanes) > 1 else "narrow"
        self.column_count = len(lanes)
        lane_map = {name: column for column, lane in enumerate(lanes) for name in lane}
        cards_by_name = {
            card.property("groupName"): card for card in self.cards if not card.isHidden()
        }
        order = [name for lane in lanes for name in lane if name in cards_by_name]
        order.extend(name for name in cards_by_name if name not in lane_map)
        available = min(self.width() - self.gap * (self.column_count - 1), self.column_count * 620)
        heights = [0] * self.column_count
        for name in order:
            card = cards_by_name[name]
            column = lane_map.get(name, self.column_count - 1)
            left = column * available // self.column_count + column * self.gap
            right = (column + 1) * available // self.column_count + column * self.gap
            card.layout().itemAt(1).layout().invalidate()
            card.layout().invalidate()
            height = max(card.sizeHint().height(), card.minimumSizeHint().height())
            card.setGeometry(left, heights[column], right - left, height)
            heights[column] += height + self.gap
        self.setFixedHeight(max(0, max(heights) - self.gap))
        if self.on_layout_changed:
            self.on_layout_changed()

class SubsectionPanel(QFrame):
    def __init__(self, title: str, config_path: str | None = None, label_width: int = 84):
        super().__init__()
        self.setObjectName("subsectionRail")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.heading = QLabel(title)
        self.heading.setObjectName("fieldLabel")
        self.heading.setProperty("configPath", config_path)
        self.heading.setMinimumWidth(label_width)
        self.heading.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(14, 0, 0, 0)
        self.content_layout.setSpacing(14)

    def add_field(self, label: str, widget: QWidget) -> None:
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        field_label = QLabel(label)
        field_label.setObjectName("componentLabel")
        field_label.setBuddy(widget)
        layout.addWidget(field_label)
        layout.addWidget(widget)
        self.content_layout.addWidget(field)

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)
