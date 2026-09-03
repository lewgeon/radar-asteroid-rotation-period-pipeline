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

Use the multi-acquisition configuration for chirp pulses:

```powershell
python pipeline.py --config configs\chirp_smoke.json
```

This mode no longer applies one sample rate to the whole campaign.
`receive.acquisitions` defines each short coherent acquisition by start time,
pulse count, and PRF, while `waveform.fast_sample_rate_hz` applies only inside
the fast-time receive window. IQ is stored as `[pulse, fast_time]`, with no
samples allocated in acquisition gaps. Inversion range-compresses each pulse,
extracts power/range features, and applies Lomb–Scargle at the true, potentially
irregular pulse epochs. Phase is never stitched across different `coherence_id`
groups. See [Three-time-axis architecture](docs/three_time_axis_architecture.md).

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

The PySide6 parameter editor uses content-height cards in stable semantic lanes.
In observation windows, target/transmitter/receiver stay on the left and
receive/ephemeris/solver stay on the right. Monostatic mode only hides the receiver.
Maximized windows keep the same two module lanes. Preview now lives in a closable
right sidebar that opens after a completed stage; the lower area contains only logs.
Echo uses compute/radar on the left and target/scattering on the right. Value and compact
unit controls share a consistent appearance. Peer field labels use the same font,
while spin axis, position, velocity, and scattering direction use one subtle vertical-rail pattern for child fields.
Scrollbars and checkmarks have stronger contrast. Dropdown lists open below the
control (above only when screen space requires it), using native Windows effects
where supported. Radar frequency, waveform, SNR, and noise seed share a card, while
inversion settings are split into time–frequency analysis and period search.
These are presentation-only groups: JSON paths remain unchanged. Drag the splitter
between parameters and logs/previews to adjust the available space.

Observation results are saved as `runs/<run-name>/observation_info.npz`. The GUI can
validate and reuse an existing file to skip repeated geometry solving, or export the
current vectors elsewhere. Duration accepts h/min/s, and initial phase accepts degrees
or π rad; saved JSON still uses the original standard units.

Run the GUI layout and interaction regressions without changing saved GUI settings:

```powershell
conda activate pytorch
python tests/test_gui_layout.py
```

Screenshots and test artifacts are written to `tmp/`. Set
`$env:GUI_SMOKE_PIPELINE='1'` before the command to also run the real short pipeline
smoke test. This is functional validation, not scientific reproduction. The legacy
Tkinter interface is unchanged by this layout update.

The GUI uses the same config-preparation rules as `pipeline.py`: before running,
it writes `experiment.json`, `observation.generated.json`, `echo.generated.json`,
and `inversion.generated.json` under `runs/<run-name>/configs/`, then runs one
stage at a time. If a stage fails, check the GUI log for the parameter source and
generated config paths.

Outputs are written under `runs/<run-name>/` by default. For `configs\pipeline_example.json`, the default run directory is `runs/pipeline_example/`.

The example config is intentionally short for a fast end-to-end smoke run. For a scientific run, copy `configs/pipeline_example.json` and adjust the observation duration, echo waveform, and inversion search range.
