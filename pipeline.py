"""Run observation, echo simulation, and rotation-period inversion in sequence."""

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


DEFAULT_CONFIG = {
    "observation": {
        "target": {
            "id": "linear-test-target",
            "name": "linear-test-target",
            "state": "linear",
            "position0_m": [299_792_458.0, 0.0, 0.0],
            "velocity_m_s": [0.0, 120.0, 0.0],
        },
        "transmitter": {
            "name": "static-origin-transmitter",
            "state": "static",
            "position_m": [0.0, 0.0, 0.0],
        },
        "receiver": {
            "name": "static-origin-receiver",
            "state": "static",
            "position_m": [0.0, 0.0, 0.0],
        },
        "receive": {
            "start_utc": "2026-01-01T00:00:00.000",
            "duration_s": 60.0,
            "sample_rate_hz": 16.0,
        },
        "solver": {
            "tolerance_s": 1e-9,
            "max_iter": 32,
        },
    },
    "echo": {
        "model_path": "models/ellipsoid.obj",
        "seed": 20250729,
        "compute": {
            "device": "auto",
            "dtype": "float32",
        },
        "target": {
            "rotation_period_s": 20.0,
            "initial_phase_deg": 17.0,
            "spin_pole_frame": "equatorial",
            "spin_pole_icrs_deg": [105.0, -66.0],
        },
        "scattering_power": [1.0, 1.0],
        "scattering_spot": {
            "enabled": True,
            "direction_body": [1.0, 0.25, 0.15],
            "radius_deg": 28.0,
            "strength": 5.0,
        },
        "radar": {
            "carrier_frequency_hz": 1_000_000.0,
        },
        "waveform": {
            "type": "continuous_wave",
            "amplitude": 1.0,
        },
        "snr_db": 20.0,
    },
    "inversion": {
        "stft_window_samples": 256,
        "stft_overlap_fraction": 0.75,
        "period_min_s": 8.0,
        "period_max_s": 40.0,
        "period_grid_size": 4000,
    },
}


def parse_args():
    parser = argparse.ArgumentParser(description="Run the full radar rotation-period pipeline.")
    parser.add_argument("--config", default=None, help="Experiment JSON config. Uses a built-in example if omitted.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used for child modules.")
    parser.add_argument("--runs-dir", default="runs", help="Directory that stores experiment runs.")
    parser.add_argument("--run-name", default=None, help="Run directory name. Defaults to the config file stem.")
    parser.add_argument("--skip-observation", action="store_true", help="Reuse the run's existing observation_info.npz.")
    parser.add_argument("--skip-echo", action="store_true", help="Reuse the run's existing echo/echo.npz.")
    return parser.parse_args()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def abs_path(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def run_directory(args):
    if args.run_name:
        name = args.run_name
    elif args.config:
        name = Path(args.config).stem
    else:
        name = "default"
    return abs_path(args.runs_dir) / name


def require_sections(config):
    required = ["observation", "echo", "inversion"]
    missing = [name for name in required if name not in config]
    if missing:
        raise SystemExit(f"流水线配置缺少顶层字段：{missing}")


def run_step(name, command, cwd, env=None):
    print(f"\n[{name}] {' '.join(map(str, command))}", flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{name} 失败，退出码 {completed.returncode}")


def child_env(extra_paths=None):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if extra_paths:
        env["PYTHONPATH"] = os.pathsep.join(extra_paths + [env.get("PYTHONPATH", "")])
    return env


def prepared_configs(config, run_dir):
    observation_output = run_dir / "observation_info.npz"
    echo_output_dir = run_dir / "echo"
    inversion_output_dir = run_dir / "inversion"

    observation_config = copy.deepcopy(config["observation"])
    observation_config["output_path"] = str(observation_output)

    echo_config = copy.deepcopy(config["echo"])
    echo_config["observation_info_path"] = str(observation_output)

    inversion_config = copy.deepcopy(config["inversion"])

    return {
        "observation": observation_config,
        "echo": echo_config,
        "inversion": inversion_config,
        "observation_output": observation_output,
        "echo_output_dir": echo_output_dir,
        "inversion_output_dir": inversion_output_dir,
    }


def main():
    args = parse_args()
    config = load_json(args.config) if args.config else copy.deepcopy(DEFAULT_CONFIG)
    require_sections(config)

    run_dir = run_directory(args)
    config_dir = run_dir / "configs"
    prepared = prepared_configs(config, run_dir)
    write_json(config_dir / "experiment.json", config)
    write_json(config_dir / "observation.generated.json", prepared["observation"])
    write_json(config_dir / "echo.generated.json", prepared["echo"])
    write_json(config_dir / "inversion.generated.json", prepared["inversion"])

    if not args.skip_observation:
        run_step(
            "observation",
            [
                args.python,
                "solve_observation_info.py",
                "--config",
                str(config_dir / "observation.generated.json"),
                "--output",
                str(prepared["observation_output"]),
            ],
            ROOT / "observation",
            env=child_env(),
        )

    if not args.skip_echo:
        run_step(
            "echo",
            [
                args.python,
                "simulate_echo.py",
                "--config",
                str(config_dir / "echo.generated.json"),
                "--output",
                str(prepared["echo_output_dir"]),
            ],
            ROOT / "echo",
            env=child_env(),
        )

    inversion_src = str(ROOT / "inversion" / "src")
    run_step(
        "inversion",
        [
            args.python,
            "scripts/estimate_period.py",
            "--echo",
            str(prepared["echo_output_dir"] / "echo.npz"),
            "--config",
            str(config_dir / "inversion.generated.json"),
            "--output",
            str(prepared["inversion_output_dir"]),
        ],
        ROOT / "inversion",
        env=child_env([inversion_src]),
    )

    print("\n完成。")
    print(f"实验目录: {run_dir}")
    print(f"观测信息: {prepared['observation_output']}")
    print(f"回波数据: {prepared['echo_output_dir'] / 'echo.npz'}")
    print(f"反演结果: {prepared['inversion_output_dir'] / 'summary.json'}")


if __name__ == "__main__":
    main()
