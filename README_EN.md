# Asteroid Radar Rotation Period Measurement

[中文](README.md)


**Version 4.3 is closed for this round**; further algorithm development and remaining work are assigned to [4.4](docs/4.4/README.md). The pipeline connects observation geometry and light-time solving, echo simulation, period estimation, and GUI result inspection. Ellipsoid controls, an EV5 mesh control, and a nominal-parameter EV5 simulation have been completed. Measured-radar validation, accuracy across scenes, and calibration of final-period uncertainty remain open.

Version 4.4 adds explicit positive predictive skill energy and known-pole spherical response selectors while retaining the previous default. See [precision options](docs/4.4/PERIOD_PRECISION_OPTIONS.md) (Chinese) for configuration, automatic model orders, rejection conditions and validation scope. These options do not supply calibrated total-error intervals or guarantee improvement at low SNR.


## Where to start

| Purpose | Read |
| --- | --- |
| Compare optical and radar period accuracy within the same window | **[Standalone benchmark and modification plan](docs/4.4/vs_4.3/plans/OPTICAL_RADAR_BENCHMARK_PLAN.md)** (Chinese): shared OBJ scene, convexinv/ADAM adapters, strong baselines, short-window hypothesis and acceptance gates; not yet implemented |
| Read the integrated stage report with figures | **[Stage experiment report](docs/4.4/vs_4.3/experiments/reports/2026-10-24_STAGE_EXPERIMENT_REPORT.md)**, in Chinese |
| Current capabilities, results and limitations | **[4.3 project status overview](docs/4.3/PROJECT_OVERVIEW.md)** (Chinese) |
| Find the right document | [Documentation guide](docs/4.3/README.md) |
| Run the GUI and inspect results | [GUI manual](docs/4.3/GUI_USER_MANUAL.md) |
| Understand the signal chain and estimator | [Chirp walkthrough](docs/4.3/CHIRP_INVERSION_WALKTHROUGH.md), [algorithm](docs/4.3/INVERSION_ALGORITHM.md) |
| Verify results and reproduce experiments | [Evidence by stage](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/README.md#reports), [experiment protocol](EXPERIMENTS.md) |
| Find remaining work | [Current open issues](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues) |
| Check the completed EV5 precision integration contract | [A/B integration handoff](docs/4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md) (Chinese), retained as a historical contract |

The overview distinguishes the ellipsoid's 5400 s repetition period from the EV5 controls' full spin periods. The 70 m mesh control is a negative result; the 400 m nominal EV5 simulation meets the 1% target under its stated assumptions but does not establish sustained 0.1% accuracy. Neither is measured radar data. Use the linked evidence for exact values, configurations and noise thresholds.

## Quick start

Clone with `git clone --recurse-submodules https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline.git`, or run `git submodule update --init --recursive` in an existing clone. Root Git archives and GitHub source ZIPs omit the three submodules and are not complete installation bundles. The included default configuration is a startup/interface fixture, not a rotation-accuracy experiment.

Tests, research scripts and internal evidence remain in Git but are excluded from source archives. Their links in public manuals point to the repository's `chirp-pulse` branch; use a full clone for offline evidence. Online references become available when the corresponding candidate changes are committed and published.

```powershell
conda activate pytorch
python pipeline.py --config configs/chirp_point_target_test.json
python pyside_gui.py
```

The point-target configuration is a development fixture. EV5 research configurations depend on their specific local mesh and observing plan; portable scientific examples still need separate preparation. The [Chinese README](README.md#快速运行) explains stage reuse and output directories.

Three modules can run independently: `observation/` produces `observation_info.npz`, `echo/` produces `echo.npz`, and `inversion/` produces period results. The schema-v4 contract assigns each physical quantity one owner: observation owns timing and ADC sampling, echo owns RF and scattering, and inversion owns search policy. Unknown or inapplicable fields are rejected; the documented legacy receiver-guard conversion is an explicit compatibility exception. See [architecture](docs/4.3/ARCHITECTURE_V4.md) and [field glossary](docs/4.3/GLOSSARY.md).

Chirp searches retain native feature times and use a shared intercept across Runs. The default `predictive_joint` method fits a common candidate period across channels and selects by whole-Run held-out predictive scores; these scores are not probabilities. Coherent processing respects Run/coherence boundaries, and scalar calibration across Runs is assumed. CPU is the default, with optional CUDA processing and period-search kernels. Conditional uncertainty diagnostics do not certify the final period's total error.

Versioned history starts at the [4.2→4.3 evidence index](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/README.md); the [4.2 snapshot](docs/4.2/README.md) remains frozen.
