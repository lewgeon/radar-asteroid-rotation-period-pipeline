"""Legacy-compatible launcher for the modular :mod:`rotation_gui` package."""

import numpy as np

from rotation_gui import PipelineWindow, configure_gui_style, main
from rotation_gui import qt_compat, storage
from rotation_gui.qt_compat import *
from rotation_gui.schema import *
from rotation_gui.storage import DEFAULT_CONFIG_PATH, HISTORY_PATH, PREVIEW_DIR, ROOT, STATE_DIR, STATE_PATH
from rotation_gui.styling import GUI_STYLE
from rotation_gui.widgets import *


if __name__ == "__main__":
    main()
