"""Small public interface for the rotation-period measurement GUI."""

from .app import main
from .styling import configure_gui_style
from .window import PipelineWindow

__all__ = ["PipelineWindow", "configure_gui_style", "main"]
