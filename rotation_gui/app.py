"""Application startup."""

from __future__ import annotations

import sys

from .qt_compat import QApplication
from .styling import configure_gui_style
from .window import PipelineWindow

def _prewarm_preview_imports() -> None:
    """提前导入预览绘图依赖，把首次导入耗时挪到启动阶段。

    观测/回波预览在阶段完成时同步调用 matplotlib 和 plotly，若留到那时才首次
    导入，会阻塞主线程造成“闪一下再刷新”。这里提前导入（失败也不致命）。
    """

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: F401
    except Exception:
        pass
    try:
        import plotly.graph_objects as go  # noqa: F401
        from plotly.subplots import make_subplots  # noqa: F401
    except Exception:
        pass

def main() -> None:
    # 注意：不要设置 QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu"——那会关闭
    # GPU 合成，导致 Plotly 的 WebGL 渲染报 “WebGL is not supported”，
    # 观测解算的 3D 预览反而无法显示。这里只保留预导入，缓解阶段完成时的阻塞。
    _prewarm_preview_imports()
    app = QApplication(sys.argv)
    app.setApplicationName("自转周期测量流水线")
    configure_gui_style(app)
    window = PipelineWindow()
    window.show()
    sys.exit(app.exec())
