"""Run observation, echo simulation, and rotation-period inversion in sequence."""

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent

# Observation owns transmit timing. Echo owns RF waveform details.
# ADC sample rate stays in observation plan / NPZ — not re-injected into echo JSON.
OBSERVATION_WAVEFORM_KEYS = ("type", "prf_hz", "pulse_width_s")
ECHO_WAVEFORM_KEYS = ("type", "bandwidth_hz", "amplitude", "baseband_convention")


DEFAULT_CONFIG = {
    "observation": {
        "target": {
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
        "receive": {
            "start_utc": "2026-01-01T00:00:00.000",
            "duration_s": 60.0,
            "sample_rate_hz": 16.0,
        },
        "waveform": {"type": "continuous_wave"},
    },
    "echo": {
        "scattering_model": "mesh",
        "model_path": "models/ellipsoid.obj",
        "seed": 20250729,
        "echo_output_reference": "raw_baseband",
        "intrapulse_motion_model": "per_pulse_linear",
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


def config_sha256(config):
    encoded = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(config):
    return {
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "config_sha256": config_sha256(config),
        "python_version": sys.version,
        "pipeline_version": "0.4.0-transmit-driven",
    }


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
    """Validate the pipeline object. ``canonical_pipeline_config`` already
    requires the three stage sections, so this is a named alias for callers.
    """

    canonical_pipeline_config(config)


def canonical_pipeline_config(config):
    """Load the sole supported canonical pipeline configuration shape."""

    if not isinstance(config, dict):
        raise ValueError("pipeline 配置必须是 JSON 对象")
    return normalize_config(config)


def _reject_deprecated_pipeline_keys(config):
    """Reject v3/deprecated keys at the strict pipeline boundary.

    The pipeline is the authoritative schema-v4 entry; deprecated keys must
    fail here with a clear message instead of silently passing through to the
    subprocess.  Observation's own normalizer applies the same policy as
    defence-in-depth.
    """

    observation = config.get("observation") or {}
    inversion = config.get("inversion") or {}

    if "schema_version" in config:
        raise ValueError("schema_version 已废弃；项目不再使用版本号字段")
    if "campaign" in observation:
        raise ValueError("observation.campaign 已废弃；观测窗口请写到 schedule.start_utc / schedule.end_utc")
    if "solver" in observation:
        raise ValueError("observation.solver 已废弃；光行时收敛策略由实现内部常量决定")

    waveform = observation.get("waveform") or {}
    if isinstance(waveform, dict):
        if waveform.get("type") == "lfm_chirp":
            raise ValueError("waveform.type=lfm_chirp 已废弃；请使用 chirp_pulse_train")
        if "pulse_fiducial" in waveform:
            raise ValueError("waveform.pulse_fiducial 已废弃；调度固定为脉冲前沿")

    visibility = observation.get("visibility") or {}
    if isinstance(visibility, dict) and "ephemeris_step_s" in visibility:
        raise ValueError("visibility.ephemeris_step_s 已废弃；请使用 visibility.sample_step_s")

    schedule = observation.get("schedule") or {}
    if isinstance(schedule, dict) and "reference_time_utc" in schedule:
        raise ValueError("schedule.reference_time_utc 已废弃；请使用 schedule.start_utc")

    sampling = observation.get("receiver_sampling") or {}
    if isinstance(sampling, dict):
        if "fs_hz" in sampling:
            raise ValueError("receiver_sampling.fs_hz 已废弃；请使用 receiver_sampling.fast_sample_rate_hz")
        if "max_bistatic_path_offset_m" in sampling:
            raise ValueError("receiver_sampling.max_bistatic_path_offset_m 已废弃；请使用 target.extent_path_m")

    target = observation.get("target") or {}
    if (
        isinstance(target, dict)
        and str(target.get("state", "static")).lower() in {"static", "linear"}
        and "id" in target
    ):
        raise ValueError("target.id 仅 Horizons 目标需要；static/linear 目标不要提供 id")

    for role in ("transmitter", "receiver"):
        station = observation.get(role)
        if isinstance(station, dict):
            for key in ("id", "same_as"):
                if key in station:
                    raise ValueError(f"{role}.{key} 已废弃；单站请省略 receiver，双站请提供完整站状态")

    receive = observation.get("receive") or {}
    if isinstance(receive, dict) and "acquisitions" in receive:
        raise ValueError("receive.acquisitions 已废弃；脉冲序列请使用 schedule + waveform + radar_system + receiver_sampling")

    ephemeris = observation.get("ephemeris") or {}
    if isinstance(ephemeris, dict):
        for key in ("padding_s", "query_mode", "query_chunk_size", "min_query_chunk_size", "query_retries", "cache"):
            if key in ephemeris:
                raise ValueError(f"ephemeris.{key} 已废弃；Horizons 传输/重试策略由环境默认决定")

    if "cpi_pulses" in inversion:
        raise ValueError("inversion.cpi_pulses 已废弃；请使用 inversion.cpi_duration_s")
    if "cpi_hop_pulses" in inversion:
        raise ValueError("inversion.cpi_hop_pulses 已废弃；请使用 inversion.cpi_hop_duration_s")
    if "cross_run_phase_coherent" in inversion:
        raise ValueError("inversion.cross_run_phase_coherent 已废弃；该字段从未实现")


def normalize_config(config):
    """Normalize a schema-v4 stage config into clean observation/echo/inversion."""

    config = copy.deepcopy(config)
    if not isinstance(config, dict):
        raise ValueError("pipeline 配置必须是 JSON 对象")
    required = {"observation", "echo", "inversion"}
    missing = sorted(required - set(config))
    unknown = sorted(set(config) - required)
    if unknown:
        raise ValueError(
            "未知 pipeline 顶层字段：" + ", ".join(unknown)
        )
    if missing:
        raise ValueError(f"pipeline 配置缺少顶层段：{', '.join(missing)}")
    _reject_deprecated_pipeline_keys(config)
    observation = config.setdefault("observation", {})
    echo = config.setdefault("echo", {})
    inversion = config.setdefault("inversion", {})

    waveform_type = str(
        (observation.get("waveform") or {}).get("type")
        or (echo.get("waveform") or {}).get("type")
        or "continuous_wave"
    )

    # Identical TX/RX geometry → monostatic omit receiver.
    transmitter = observation.get("transmitter")
    receiver = observation.get("receiver")
    if isinstance(transmitter, dict) and isinstance(receiver, dict):
        left = {k: v for k, v in transmitter.items() if k not in {"id", "name", "same_as"}}
        right = {k: v for k, v in receiver.items() if k not in {"id", "name", "same_as"}}
        if left == right:
            observation.pop("receiver", None)

    config["observation"] = observation
    config["echo"] = echo
    config["inversion"] = inversion

    # Validate at the interfaces owned by each submodule.  The pipeline does
    # not maintain a second, drifting copy of their field lists.
    from observation.src.config_normalize import validate_observation_config
    from echo.src.config_normalize import normalize_echo_config
    from inversion.src.dataset import normalize_inversion_policy

    validate_observation_config(config["observation"])
    config["echo"] = normalize_echo_config(config["echo"])
    config = normalize_parameter_ownership(config)
    layout = "chirp" if waveform_type == "chirp_pulse_train" else "cw"
    config["inversion"] = normalize_inversion_policy(config["inversion"], layout)
    return config


def normalize_parameter_ownership(config):
    """Reject fields placed in the wrong stage (strict v4 ownership).

    ``type`` is the sole shared waveform discriminator and may appear on either
    side.  Every other editable field has exactly one owner, so writing it on
    the wrong side is an error rather than something to silently migrate.
    """

    config = copy.deepcopy(config)
    observation = config.setdefault("observation", {})
    echo = config.setdefault("echo", {})
    obs_waveform = dict(observation.get("waveform", {}))
    echo_waveform = dict(echo.get("waveform", {}))
    echo_radar = dict(echo.get("radar", {}))

    # type is shared; require consistency when present on both sides.
    if "type" in obs_waveform and "type" in echo_waveform:
        if obs_waveform["type"] != echo_waveform["type"]:
            raise ValueError(
                f"waveform.type 在 observation 与 echo 中不一致："
                f"{obs_waveform['type']!r} 与 {echo_waveform['type']!r}"
            )
    for key in ("prf_hz", "pulse_width_s"):
        if key in echo_waveform:
            raise ValueError(f"waveform.{key} 应由 observation.waveform 持有，请从 echo.waveform 移除")
    if "fast_sample_rate_hz" in echo_waveform:
        raise ValueError(
            "waveform.fast_sample_rate_hz 应由 observation.receiver_sampling 持有，"
            "请从 echo.waveform 移除"
        )
    for key in ("bandwidth_hz", "amplitude", "baseband_convention"):
        if key in obs_waveform:
            raise ValueError(f"waveform.{key} 应由 echo.waveform 持有，请从 observation.waveform 移除")
    if "carrier_frequency_hz" in obs_waveform:
        raise ValueError("carrier_frequency_hz 应由 echo.radar 持有，请从 observation.waveform 移除")

    # type may live on either side; mirror it so both stages agree.
    if "type" in obs_waveform:
        echo_waveform["type"] = obs_waveform["type"]
    elif "type" in echo_waveform:
        obs_waveform["type"] = echo_waveform["type"]

    observation["waveform"] = {
        key: obs_waveform[key] for key in OBSERVATION_WAVEFORM_KEYS if key in obs_waveform
    }
    echo["waveform"] = {
        key: echo_waveform[key] for key in ECHO_WAVEFORM_KEYS if key in echo_waveform
    }
    if echo_radar:
        echo["radar"] = echo_radar
    config["observation"] = observation
    config["echo"] = echo
    return config


def assemble_echo_waveform(observation_config, echo_config):
    """Validate the RF waveform against the observation-owned ADC rate."""

    observation_waveform = observation_config.get("waveform", {})
    receiver_sampling = observation_config.get("receiver_sampling", {})
    echo_waveform = copy.deepcopy(echo_config.get("waveform", {}))
    if "type" not in echo_waveform and "type" in observation_waveform:
        echo_waveform["type"] = observation_waveform["type"]
    bandwidth = echo_waveform.get("bandwidth_hz")
    sample_rate = receiver_sampling.get("fast_sample_rate_hz")
    if bandwidth is not None and sample_rate is not None and float(sample_rate) <= abs(float(bandwidth)):
        raise ValueError(
            "复基带 chirp 要求 receiver_sampling.fast_sample_rate_hz 大于 bandwidth_hz"
        )
    return echo_waveform


def run_step(name, command, cwd, env=None):
    print(f"\n[{name}] {' '.join(map(str, command))}", flush=True)
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"{name} 失败，退出码 {completed.returncode}")


def child_env(extra_paths=None):
    """Build a child process env without inheriting a polluted PYTHONPATH.

    Putting ``inversion/src`` on ``PYTHONPATH`` used to shadow the stdlib
    ``signal`` module and break torch imports in the echo stage. Children only
    get explicitly requested paths plus any unrelated inherited entries.
    """

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    inversion_src = (ROOT / "inversion" / "src").resolve()
    inherited = []
    for entry in env.get("PYTHONPATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            if Path(entry).resolve() == inversion_src:
                continue
        except OSError:
            pass
        inherited.append(entry)
    paths = [str(Path(path)) for path in (extra_paths or [])] + inherited
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def prepared_configs(config, run_dir):
    config = canonical_pipeline_config(config)
    observation_output = run_dir / "observation_info.npz"
    echo_output_dir = run_dir / "echo"
    inversion_output_dir = run_dir / "inversion"

    observation_config = copy.deepcopy(config["observation"])
    observation_config["output_path"] = str(observation_output)

    echo_config = copy.deepcopy(config["echo"])
    echo_config["observation_info_path"] = str(observation_output)
    echo_config["output_path"] = str(echo_output_dir)
    if "waveform" in observation_config or "waveform" in echo_config:
        echo_config["waveform"] = assemble_echo_waveform(observation_config, echo_config)

    inversion_config = copy.deepcopy(config["inversion"])
    inversion_config["output_path"] = str(inversion_output_dir)

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
    config = canonical_pipeline_config(
        load_json(args.config) if args.config else copy.deepcopy(DEFAULT_CONFIG)
    )

    run_dir = run_directory(args)
    config_dir = run_dir / "configs"
    prepared = prepared_configs(config, run_dir)
    write_json(config_dir / "experiment.json", config)
    write_json(config_dir / "observation.generated.json", prepared["observation"])
    write_json(config_dir / "echo.generated.json", prepared["echo"])
    write_json(config_dir / "inversion.generated.json", prepared["inversion"])
    write_json(run_dir / "manifest.json", build_manifest(config))

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
