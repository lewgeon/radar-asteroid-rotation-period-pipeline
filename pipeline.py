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


FRIENDLY_CONFIG_MARKERS = {
    "GUI配置版本",
    "GUI Config Version",
    "说明",
    "Description",
}

FRIENDLY_KEY_ALIASES = {
    "观测解算": "observation",
    "Observation": "observation",
    "回波仿真": "echo",
    "Echo Simulation": "echo",
    "周期反演": "inversion",
    "Rotation Inversion": "inversion",
    "目标参数": "target",
    "Target": "target",
    "发射站": "transmitter",
    "Transmitter": "transmitter",
    "接收站": "receiver",
    "Receiver": "receiver",
    "接收设置": "receive",
    "Receive": "receive",
    "求解器": "solver",
    "Solver": "solver",
    "计算设置": "compute",
    "Compute": "compute",
    "雷达参数": "radar",
    "Radar": "radar",
    "波形参数": "waveform",
    "Waveform": "waveform",
    "散射热点": "scattering_spot",
    "Scattering Spot": "scattering_spot",
    "ID": "id",
    "名称": "name",
    "Name": "name",
    "状态": "state",
    "State": "state",
    "目标类型": "object_type",
    "Object Type": "object_type",
    "初始位置": "position0_m",
    "Initial Position": "position0_m",
    "速度": "velocity_m_s",
    "Velocity": "velocity_m_s",
    "位置": "position_m",
    "Position": "position_m",
    "纬度": "lat_deg",
    "Latitude": "lat_deg",
    "经度": "lon_deg",
    "Longitude": "lon_deg",
    "高度": "height_m",
    "Height": "height_m",
    "开始时间": "start_utc",
    "Start Time": "start_utc",
    "接收时长": "duration_s",
    "Duration": "duration_s",
    "采样率": "sample_rate_hz",
    "Sample Rate": "sample_rate_hz",
    "收敛阈值": "tolerance_s",
    "Tolerance": "tolerance_s",
    "最大迭代": "max_iter",
    "Max Iterations": "max_iter",
    "参考中心": "location",
    "Reference Center": "location",
    "参考平面": "refplane",
    "Reference Plane": "refplane",
    "星历余量": "padding_s",
    "Padding": "padding_s",
    "星历步长": "query_step_s",
    "Query Step": "query_step_s",
    "查询分块": "query_chunk_size",
    "Query Chunk Size": "query_chunk_size",
    "查询模式": "query_mode",
    "Query Mode": "query_mode",
    "查询重试": "query_retries",
    "Query Retries": "query_retries",
    "最小重试分块": "min_query_chunk_size",
    "Min Query Chunk Size": "min_query_chunk_size",
    "使用缓存": "cache",
    "Use Cache": "cache",
    "模型路径": "model_path",
    "Model Path": "model_path",
    "随机种子": "seed",
    "Seed": "seed",
    "计算设备": "device",
    "Device": "device",
    "数值精度": "dtype",
    "DType": "dtype",
    "自转周期": "rotation_period_s",
    "Rotation Period": "rotation_period_s",
    "初始相位": "initial_phase_deg",
    "Initial Phase": "initial_phase_deg",
    "自转轴坐标系": "spin_pole_frame",
    "Spin Pole Frame": "spin_pole_frame",
    "自转轴赤道坐标": "spin_pole_icrs_deg",
    "Spin Pole Equatorial": "spin_pole_icrs_deg",
    "自转轴黄道坐标": "spin_pole_ecliptic_deg",
    "Spin Pole Ecliptic": "spin_pole_ecliptic_deg",
    "散射指数": "scattering_power",
    "Scattering Power": "scattering_power",
    "发射照明方向": "incident",
    "Incident Direction": "incident",
    "散射方向": "scattered",
    "Scattered Direction": "scattered",
    "启用": "enabled",
    "Enabled": "enabled",
    "斑块方向": "direction_body",
    "Spot Direction": "direction_body",
    "角半径": "radius_deg",
    "Radius": "radius_deg",
    "增强倍数": "strength",
    "Strength": "strength",
    "载频": "carrier_frequency_hz",
    "Carrier Frequency": "carrier_frequency_hz",
    "波形类型": "type",
    "Waveform Type": "type",
    "幅度": "amplitude",
    "Amplitude": "amplitude",
    "脉冲宽度": "pulse_width_s",
    "Pulse Width": "pulse_width_s",
    "Chirp带宽": "bandwidth_hz",
    "Chirp Bandwidth": "bandwidth_hz",
    "脉冲重复间隔": "pri_s",
    "Pulse Repetition Interval": "pri_s",
    "首脉冲起点": "first_pulse_start_s",
    "First Pulse Start": "first_pulse_start_s",
    "信噪比": "snr_db",
    "SNR": "snr_db",
    "STFT窗长": "stft_window_samples",
    "STFT Window": "stft_window_samples",
    "STFT重叠率": "stft_overlap_fraction",
    "STFT Overlap": "stft_overlap_fraction",
    "周期下限": "period_min_s",
    "Period Min": "period_min_s",
    "周期上限": "period_max_s",
    "Period Max": "period_max_s",
    "周期网格数": "period_grid_size",
    "Period Grid Size": "period_grid_size",
}

CANONICAL_TO_FRIENDLY_ZH = {
    "observation": "观测解算",
    "echo": "回波仿真",
    "inversion": "周期反演",
    "target": "目标参数",
    "transmitter": "发射站",
    "receiver": "接收站",
    "receive": "接收设置",
    "solver": "求解器",
    "compute": "计算设置",
    "radar": "雷达参数",
    "waveform": "波形参数",
    "scattering_spot": "散射热点",
    "id": "ID",
    "name": "名称",
    "state": "状态",
    "object_type": "目标类型",
    "position0_m": "初始位置",
    "velocity_m_s": "速度",
    "position_m": "位置",
    "lat_deg": "纬度",
    "lon_deg": "经度",
    "height_m": "高度",
    "start_utc": "开始时间",
    "duration_s": "接收时长",
    "sample_rate_hz": "采样率",
    "tolerance_s": "收敛阈值",
    "max_iter": "最大迭代",
    "location": "参考中心",
    "refplane": "参考平面",
    "padding_s": "星历余量",
    "query_step_s": "星历步长",
    "query_chunk_size": "查询分块",
    "query_mode": "查询模式",
    "query_retries": "查询重试",
    "min_query_chunk_size": "最小重试分块",
    "cache": "使用缓存",
    "model_path": "模型路径",
    "seed": "随机种子",
    "device": "计算设备",
    "dtype": "数值精度",
    "rotation_period_s": "自转周期",
    "initial_phase_deg": "初始相位",
    "spin_pole_frame": "自转轴坐标系",
    "spin_pole_icrs_deg": "自转轴赤道坐标",
    "spin_pole_ecliptic_deg": "自转轴黄道坐标",
    "scattering_power": "散射指数",
    "incident": "发射照明方向",
    "scattered": "散射方向",
    "enabled": "启用",
    "direction_body": "斑块方向",
    "radius_deg": "角半径",
    "strength": "增强倍数",
    "carrier_frequency_hz": "载频",
    "type": "波形类型",
    "amplitude": "幅度",
    "pulse_width_s": "脉冲宽度",
    "bandwidth_hz": "Chirp带宽",
    "pri_s": "脉冲重复间隔",
    "first_pulse_start_s": "首脉冲起点",
    "snr_db": "信噪比",
    "stft_window_samples": "STFT窗长",
    "stft_overlap_fraction": "STFT重叠率",
    "period_min_s": "周期下限",
    "period_max_s": "周期上限",
    "period_grid_size": "周期网格数",
}

CANONICAL_TO_FRIENDLY_EN = {
    value: key for key, value in FRIENDLY_KEY_ALIASES.items() if key and key[0].isascii() and " " in key
}
CANONICAL_TO_FRIENDLY_EN.update(
    {
        "observation": "Observation",
        "echo": "Echo Simulation",
        "inversion": "Rotation Inversion",
        "id": "ID",
        "snr_db": "SNR",
        "dtype": "DType",
    }
)


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
    config = pipeline_config_from_any(config)
    required = ["observation", "echo", "inversion"]
    missing = [name for name in required if name not in config]
    if missing:
        raise SystemExit(f"流水线配置缺少顶层字段：{missing}")


def pipeline_config_from_any(config):
    """Accept either canonical pipeline JSON or GUI-friendly JSON labels."""

    if isinstance(config, list):
        return [pipeline_config_from_any(item) for item in config]
    if not isinstance(config, dict):
        return config
    converted = {}
    for key, value in config.items():
        if key in FRIENDLY_CONFIG_MARKERS:
            continue
        canonical_key = FRIENDLY_KEY_ALIASES.get(key, key)
        converted[canonical_key] = pipeline_config_from_any(value)
    _collapse_scattering_power(converted)
    return converted


def _collapse_scattering_power(config):
    value = config.get("scattering_power")
    if isinstance(value, dict):
        incident = value.get("incident", value.get("发射照明方向", value.get("Incident Direction", 1.0)))
        scattered = value.get("scattered", value.get("散射方向", value.get("Scattered Direction", 1.0)))
        config["scattering_power"] = [incident, scattered]


def gui_config_from_pipeline_config(config, language="zh"):
    """Export a researcher-facing JSON using GUI labels while keeping values exact."""

    labels = CANONICAL_TO_FRIENDLY_ZH if language == "zh" else CANONICAL_TO_FRIENDLY_EN
    payload = {"GUI配置版本" if language == "zh" else "GUI Config Version": 1}
    for key, value in config.items():
        payload[labels.get(key, key)] = _friendly_value(value, labels)
    return payload


def _friendly_value(value, labels):
    if isinstance(value, list):
        return [_friendly_value(item, labels) for item in value]
    if not isinstance(value, dict):
        return value
    converted = {}
    for key, item in value.items():
        if key == "scattering_power" and isinstance(item, list) and len(item) == 2:
            converted[labels.get(key, key)] = {
                labels.get("incident", "incident"): item[0],
                labels.get("scattered", "scattered"): item[1],
            }
        else:
            converted[labels.get(key, key)] = _friendly_value(item, labels)
    return converted


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
    config = pipeline_config_from_any(config)
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
    config = pipeline_config_from_any(load_json(args.config)) if args.config else copy.deepcopy(DEFAULT_CONFIG)
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
