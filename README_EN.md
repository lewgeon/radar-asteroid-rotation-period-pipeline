# Rotation-Period Measurement Pipeline

[中文](README.md)

The project is split into three independent submodules:

1. `observation/` solves line-of-sight vectors and three-event light-time geometry, then writes `observation_info.npz`.
2. `echo/` reads `observation_info.npz` plus shape/radar settings, then writes `echo.npz`.
3. `inversion/` reads `echo.npz` and estimates rotation-period candidates.

The top-level `pipeline.py` connects the three modules through files. It accepts both the legacy three-section configuration and the schema-v3 campaign configuration. Intermediate paths are generated and injected by the pipeline.

## Quick Start

For detailed GUI usage, see [GUI User Manual](docs/GUI_USER_MANUAL.md).

```powershell
conda activate pytorch
python pipeline.py --config configs\pipeline_example.json
```

Use the transmit-driven schema-v3 campaign for chirp pulses:

```powershell
python pipeline.py --config configs\campaign_v3_example.json
```

`schedule.runs[].tx_start_utc` defines physical transmit starts. PRF belongs to
the waveform, while `receiver.fast_sample_rate_hz` belongs to the ADC. Every
pulse is propagated forward through transmit–centroid-scatter–receive geometry.
Each saved IQ row remains an integer slice of one uniform ADC grid per run.
Inversion performs pulse compression, sliding CPIs within coherence groups,
range-Doppler feature extraction, and a multi-harmonic period search with
per-run baselines. Candidates from independent observables are clustered into
a cross-feature consensus result. Phase is never stitched across different
`coherence_id` groups. See [schema-v3 architecture](docs/ARCHITECTURE_V3.md). The old
`receive.acquisitions` route is retained for compatibility only.

The receiver has one continuous ADC clock, at `fast_sample_rate_hz`, throughout
each run's receive interval. “Fast time” and “slow time” are processing
coordinates; PRF is not a second receive sampling rate. To avoid storing empty
inter-pulse spans, the simulator evaluates each required global integer ADC
index once, including noise, and then gathers those indices into rows using
`row_start_sample`. Repeated indices are identical in every row. If echoes from
adjacent pulses overlap, all contributing pulses are summed and the dataset is
flagged with a warning.

Schema v3 supports two echo references. The default `centroid_compensated`
output is intended for rotation-inversion development and removes ideal
centroid translation. `raw_baseband` preserves common delay and carrier
Doppler for pre-deployment realism tests. Both use per-pulse three-event
ephemeris anchors and default `per_pulse_linear` intrapulse motion. The
traditional `frozen` stop-and-go mode is available only behind error checks.

You can also launch the first-pass desktop GUI and run the pipeline step by step:

```powershell
conda activate pytorch
python pyside_gui.py
```

The package entry point is equivalent:

```powershell
python -m rotation_gui
```

GUI implementation is now organized by responsibility under `rotation_gui/`;
the top-level `pyside_gui.py` remains a compatibility launcher. See the
[GUI architecture guide](docs/GUI_ARCHITECTURE.md) for module ownership,
dependency direction, and extension points.

The GUI now loads the schema-v3 chirp example from `configs/campaign_v3_example.json`;
legacy configs can still be opened explicitly. The Run Schedule card is visible at
the top of the observation page and can compute visibility, select transmit runs,
populate their UTC rows, and preview the visibility timeline. The "执行下一步"
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
Schema-v3 observation windows place the Run Schedule and live timeline across the top,
with visibility, radar mode, transmit waveform, and receive ADC controls grouped by ownership.
Legacy layouts remain supported.
Maximized windows keep the same two module lanes. Preview now lives in a closable
right sidebar that opens after a completed stage; the lower area contains only logs.
Schema v3 has one editable acquisition source: the Observation page. Echo shows a
read-only acquisition summary and generates its execution snapshot from Observation
immediately before running; it only edits compute, noise, target, and scattering settings.
Legacy three-section configs retain their radar editor. Value and compact
unit controls share a consistent appearance. Peer field labels use the same font,
while spin axis, position, velocity, and scattering direction use one subtle vertical-rail pattern for child fields.
Scrollbars and checkmarks have stronger contrast. Dropdown lists open below the
control (above only when screen space requires it), using native Windows effects
where supported. SNR and noise seed share a simulation card, while
schema-v3 inversion settings are split into chirp signal processing and period
search; CW-only STFT fields are hidden for chirp campaigns.
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
