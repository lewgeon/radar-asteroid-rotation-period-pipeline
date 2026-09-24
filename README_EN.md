# Rotation Period Measurement Pipeline

[中文](README.md)

This repository connects three independently runnable modules:

1. `observation/` builds a typed `observation_info.npz` plan with transmit, scatter, receive, geometry, and ADC timing.
2. `echo/` consumes that plan and generates `echo.npz` for either a mesh or an isotropic point target.
3. `inversion/` consumes the echo artifact and estimates rotation-period candidates.

The persisted configuration contract is schema v4. A physical quantity has one owner: observation owns timing and ADC sampling, echo owns RF/scattering choices, and inversion owns period-search policy. Legacy and unknown fields are rejected with their complete paths; no migration layer remains.

```powershell
conda activate pytorch
python pipeline.py --config configs\chirp_point_target_test.json
```

See [the v4 architecture](docs/4.3/ARCHITECTURE_V4.md), [field glossary](docs/4.3/GLOSSARY.md), and [Chinese GUI manual](docs/4.3/GUI_USER_MANUAL.md). Versioned documentation layout: [docs/4.3/README.md](docs/4.3/README.md). The completed 4.2 snapshot is [docs/4.2/README.md](docs/4.2/README.md).
