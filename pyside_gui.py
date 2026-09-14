"""Top-level GUI launcher.

The actual startup logic lives in :func:`rotation_gui.app.main`; this script
only calls it, so ``python pyside_gui.py`` and ``python -m rotation_gui``
behave identically.
"""

from rotation_gui import main

if __name__ == "__main__":
    main()
