# Rotation-Period Measurement Pipeline

[中文](README.md)

The project is split into three independent submodules:

1. `observation/` solves line-of-sight vectors and three-event light-time geometry, then writes `observation_info.npz`.
2. `echo/` reads `observation_info.npz` plus shape/radar settings, then writes `echo.npz`.
3. `inversion/` reads `echo.npz` and estimates rotation-period candidates.

The top-level `pipeline.py` connects the three modules through files. The modules do not import each other's business logic. The experiment config contains only three business sections: `observation`, `echo`, and `inversion`. Intermediate paths are generated and injected by the pipeline.

## Quick Start

For detailed GUI usage, see [GUI User Manual](docs/GUI_USER_MANUAL.md).

```powershell
conda activate pytorch
python pipeline.py --config configs\pipeline_example.json
```

You can also launch the first-pass desktop GUI and run the pipeline step by step:

```powershell
conda activate pytorch
python pyside_gui.py
```

The GUI loads initial values from `configs/pipeline_example.json`. The "执行下一步"
button runs `observation`, `echo`, and `inversion` one stage at a time. Edited
parameters are saved under `.gui_state/pipeline_gui_state.json` and reused the
next time the GUI opens. Recent execution history is shown in the left panel.
While a stage is running, the bottom of the window shows a rough percentage and
the current sub-step reported by the child module.
Use "中止" to abort the current stage. The PySide6 GUI embeds Plotly previews in
the result panel when Qt WebEngine is available, with static images and external
browser opening kept as fallback.
The older Tkinter entry point remains available as `python gui_app.py` for fallback.

The GUI uses the same config-preparation rules as `pipeline.py`: before running,
it writes `experiment.json`, `observation.generated.json`, `echo.generated.json`,
and `inversion.generated.json` under `runs/<run-name>/configs/`, then runs one
stage at a time. If a stage fails, check the GUI log for the parameter source and
generated config paths.

Outputs are written under `runs/<run-name>/` by default. For `configs\pipeline_example.json`, the default run directory is `runs/pipeline_example/`.

The example config is intentionally short for a fast end-to-end smoke run. For a scientific run, copy `configs/pipeline_example.json` and adjust the observation duration, echo waveform, and inversion search range.
