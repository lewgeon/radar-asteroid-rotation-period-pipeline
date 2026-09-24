"""Responsive card canvas and lightweight subsection containment."""

from __future__ import annotations

from ..qt_compat import QFrame, QLabel, QSize, QSizePolicy, Qt, QTimer, QVBoxLayout, QWidget

EXPANDING = QSizePolicy.Policy.Expanding
FIXED = QSizePolicy.Policy.Fixed


def _apply_wrap_heights(widget: QWidget) -> None:
    """Pin wrapping labels to their height-for-width so layouts cannot ignore wrap."""

    for label in widget.findChildren(QLabel):
        if label.isHidden() or not label.wordWrap():
            continue
        label.setMinimumHeight(0)
        available = max(1, label.width())
        needed = label.heightForWidth(available) if label.hasHeightForWidth() else label.sizeHint().height()
        label.setMinimumHeight(max(1, needed))


def _height_for_width(widget: QWidget, width: int) -> int:
    """Measure wrapping content at the column width without compressing the layout."""

    width = max(1, int(width))
    # A tall canvas lets wrapping labels take their column width first. Do not
    # read child geometries after that resize: expanding labels would fill the
    # extra space and the measured card would stay thousands of pixels tall.
    widget.resize(width, max(widget.height(), 4096))
    layout = widget.layout()
    if layout is None:
        return max(widget.sizeHint().height(), widget.minimumSizeHint().height()) + 2
    layout.invalidate()
    layout.activate()
    _apply_wrap_heights(widget)
    layout.invalidate()
    measured = max(
        layout.sizeHint().height(),
        layout.minimumSize().height(),
        widget.minimumSizeHint().height(),
    )
    # QSS draws the 1 px card border inside the widget rectangle.
    return measured + 2


_WRAPPING_CARD_GROUPS = frozenset({"plan", "receiver_sampling"})


LANES_BY_STAGE = {
    "observation": (
        ("target", "transmitter", "receiver"),
        ("transmit", "receive", "radar_system", "receiver_sampling", "plan", "geometry"),
    ),
    "echo": (
        ("compute", "radar_parameters", "noise", "echo_options"),
        ("target", "scattering_spot"),
    ),
    "inversion": (
        ("spectrum",),
        ("period_search",),
    ),
}


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
        self._reflowing = False
        for card in cards:
            card.setParent(self)
            card.ensurePolished()
        self.card_minimum = max([360] + [card.minimumSizeHint().width() for card in cards] or [360])
        self.setMinimumWidth(self.card_minimum)
        self.setSizePolicy(EXPANDING, FIXED)
        QTimer.singleShot(0, self.reflow)

    def sizeHint(self):
        # Keep the width already allocated by the scroll area. Reporting only
        # card_minimum lets a focus/layout pass shrink the canvas to one column.
        width = self.card_minimum
        if self.width() > width:
            width = self.width()
        return QSize(width, max(1, self.minimumHeight()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._reflowing:
            self.reflow()

    def reflow(self):
        if self._reflowing or self.width() <= 0:
            return
        self._reflowing = True
        used_width = self.width()
        try:
            lanes = LANES_BY_STAGE.get(self.stage, (("general",),))
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
            available = min(
                max(self.width() - self.gap * (self.column_count - 1), self.card_minimum),
                self.column_count * 620,
            )
            heights = [0] * self.column_count
            for name in order:
                card = cards_by_name[name]
                column = lane_map.get(name, self.column_count - 1)
                left = column * available // self.column_count + column * self.gap
                right = (column + 1) * available // self.column_count + column * self.gap
                if card.layout() is not None and card.layout().count() > 1:
                    item = card.layout().itemAt(1)
                    if item is not None and item.layout() is not None:
                        item.layout().invalidate()
                    card.layout().invalidate()
                width = max(1, right - left)
                height = max(card.sizeHint().height(), card.minimumSizeHint().height())
                if card.property("groupName") in _WRAPPING_CARD_GROUPS:
                    height = max(height, _height_for_width(card, width))
                card.setGeometry(left, heights[column], width, height)
                heights[column] += height + self.gap
            target_height = max(0, max(heights or [0]) - self.gap)
            if self.minimumHeight() != target_height or self.maximumHeight() != target_height:
                self.setFixedHeight(target_height)
            if self.on_layout_changed:
                self.on_layout_changed()
        finally:
            self._reflowing = False
        # A layout pass can change our width while _reflowing swallows resizeEvent.
        if abs(self.width() - used_width) > 1:
            QTimer.singleShot(0, self.reflow)

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
