"""Run observation, echo simulation, and rotation-period inversion in sequence."""

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
INVERSION_ENTRY = ROOT / "inversion" / "scripts" / "estimate_period.py"

# Observation owns pulse timing. Echo owns RF waveform details, including type.
# ADC sample rate stays in observation plan / NPZ — not re-injected into echo JSON.
OBSERVATION_TRANSMIT_KEYS = ("prf_hz", "pulse_width_s")
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
    parser.add_argument(
        "--allow-legacy-reuse",
        action="store_true",
        help="Reuse historical artifacts that lack a stage fingerprint after an explicit confirmation.",
    )
    return parser.parse_args()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    """Atomically replace ``path`` so a failed write leaves the previous file."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    handle, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def config_sha256(config):
    encoded = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path):
    """Return a stable digest without loading a potentially large artifact at once."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_stage_artifact(path, stage):
    """Reject missing, empty, or unloadable stage products before recording success."""

    path = Path(path)
    labels = {"observation": "观测产物", "echo": "回波产物"}
    label = labels.get(stage, stage)
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"{label}为空或不存在：{path}")
    if path.suffix.lower() != ".npz":
        return path
    try:
        with np.load(path, allow_pickle=False) as data:
            names = set(data.files)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{label}不是有效的 npz：{path}") from exc
    if stage == "observation" and "elapsed_s" not in names and "valid_plan" not in names:
        raise ValueError(f"{label}缺少 elapsed_s 或 valid_plan：{path}")
    if stage == "echo" and "iq" not in names:
        raise ValueError(f"{label}缺少 iq：{path}")
    return path


def _npz_metadata(data):
    if "metadata_json" not in data.files:
        return {}
    raw = data["metadata_json"]
    if isinstance(raw, np.ndarray):
        raw = raw.item()
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("产物 metadata_json 不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("产物 metadata_json 必须是 JSON 对象")
    return value


def _exact_positive_integer(value, label):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{label} 必须是正整数")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} 必须是正整数") from None
    if not np.isfinite(number) or not number.is_integer() or number <= 0:
        raise ValueError(f"{label} 必须是正整数")
    return int(number)


def validate_observation_echo_contract(observation_path, echo_path):
    """Reject a chirp echo that does not represent the supplied observation plan.

    Old 251-column echoes and current 252-column plans can each be internally
    readable, so validating either file alone is insufficient.  This function
    checks the producer/consumer seam before inversion or GUI preview uses the
    pair.  CW has no pulse/fast-time row grid and is intentionally unaffected.
    """

    observation_path = Path(observation_path)
    echo_path = Path(echo_path)
    with np.load(observation_path, allow_pickle=False) as observation, np.load(
        echo_path, allow_pickle=False
    ) as echo:
        if "iq" not in echo.files:
            raise ValueError(f"回波文件缺少 iq：{echo_path}")
        iq = np.asarray(echo["iq"])
        echo_metadata = _npz_metadata(echo)
        if iq.ndim == 1:
            return {"layout": "cw", "pulse_count": int(iq.shape[0])}
        if iq.ndim != 2:
            raise ValueError(f"回波 iq 维数无效：{iq.ndim}")
        if "valid_plan" not in observation.files:
            raise ValueError("chirp 观测产物缺少 valid_plan，无法核对回波行宽")
        valid_plan = np.asarray(observation["valid_plan"], dtype=bool)
        if valid_plan.ndim != 2:
            raise ValueError("chirp 观测产物 valid_plan 必须是二维数组")

        observation_shape = tuple(map(int, valid_plan.shape))
        echo_shape = tuple(map(int, iq.shape))
        if observation_shape[0] != echo_shape[0]:
            raise ValueError(
                f"观测计划为 {observation_shape[0]} 个脉冲，回波为 {echo_shape[0]} 个脉冲；"
                "产物不是同一份 chirp 计划，请重跑 observation 和 echo"
            )
        if observation_shape[1] != echo_shape[1]:
            raise ValueError(
                f"观测计划为 {observation_shape[1]} 列，回波为 {echo_shape[1]} 列；"
                "检测到不同代次的 chirp 产物，请重跑 echo"
            )

        observation_metadata = _npz_metadata(observation)
        planned_count = observation_metadata.get("fast_sample_count")
        if planned_count is not None:
            planned_count = _exact_positive_integer(
                planned_count, "观测产物 metadata.fast_sample_count"
            )
            if planned_count != observation_shape[1]:
                raise ValueError(
                    "观测产物 metadata.fast_sample_count 与 valid_plan 行宽不一致"
                )
        echoed_count = echo_metadata.get("fast_sample_count")
        if echoed_count is not None:
            echoed_count = _exact_positive_integer(
                echoed_count, "回波 metadata.fast_sample_count"
            )
            if echoed_count != echo_shape[1]:
                raise ValueError("回波 metadata.fast_sample_count 与 iq 行宽不一致")

        if "fast_time_s" in echo.files:
            fast_time_s = np.asarray(echo["fast_time_s"])
            if fast_time_s.ndim != 1:
                raise ValueError("回波 fast_time_s 必须是一维数组")
            if len(fast_time_s) != echo_shape[1]:
                raise ValueError("回波 fast_time_s 长度与 iq 行宽不一致")
        if "row_start_sample" in observation.files and "row_start_sample" in echo.files:
            if not np.array_equal(
                np.asarray(observation["row_start_sample"], dtype=np.int64),
                np.asarray(echo["row_start_sample"], dtype=np.int64),
            ):
                raise ValueError("观测计划与回波的 row_start_sample 不一致")

        source_hash = echo_metadata.get("observation_info_sha256")
        if source_hash is not None:
            actual_hash = file_sha256(observation_path)
            if str(source_hash) != actual_hash:
                raise ValueError(
                    "回波记录的 observation_info_sha256 与当前观测产物不一致；"
                    "请重跑 echo"
                )
        return {
            "layout": "chirp",
            "pulse_count": observation_shape[0],
            "fast_sample_count": observation_shape[1],
        }


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


THROUGH_STAGES = ("observation", "echo", "inversion", "full_pipeline")
OBSERVATION_ARTIFACT_CONTRACT_VERSION = 1
ECHO_ARTIFACT_CONTRACT_VERSION = 1
STAGE_MANIFEST_NAME = "stage_manifest.json"


class ReuseDecision:
    def __init__(self, reusable, *, reason="", requires_confirmation=False, mismatched_fields=None):
        self.reusable = bool(reusable)
        self.reason = str(reason)
        self.requires_confirmation = bool(requires_confirmation)
        self.mismatched_fields = list(mismatched_fields or [])


def canonical_pipeline_config(config):
    """Load the sole supported canonical pipeline configuration shape."""

    if not isinstance(config, dict):
        raise ValueError("pipeline 配置必须是 JSON 对象")
    return normalize_config(config)


def canonical_fingerprint(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def observation_dependency_projection(observation_config):
    from observation.src.config_normalize import normalize_observation_config

    projection = _omit_identical_receiver(normalize_observation_config(observation_config))
    projection.pop("output_path", None)
    return {
        "observation": projection,
        "artifact_contract_version": OBSERVATION_ARTIFACT_CONTRACT_VERSION,
    }


def echo_dependency_projection(echo_config, observation_sha256, *, config_path=None):
    from echo.src.config_normalize import normalize_echo_config, resolve_echo_input_paths

    projection = normalize_echo_config(echo_config)
    for key in ("output_path", "observation_info_path"):
        projection.pop(key, None)
    projection, _warnings = resolve_echo_input_paths(projection, config_path=config_path)
    return {
        "echo": projection,
        "observation_info_sha256": observation_sha256,
        "artifact_contract_version": ECHO_ARTIFACT_CONTRACT_VERSION,
    }


def _omit_identical_receiver(observation):
    observation = copy.deepcopy(observation)
    transmitter = observation.get("transmitter")
    receiver = observation.get("receiver")
    if isinstance(transmitter, dict) and isinstance(receiver, dict):
        left = {k: v for k, v in transmitter.items() if k not in {"id", "name", "same_as"}}
        right = {k: v for k, v in receiver.items() if k not in {"id", "name", "same_as"}}
        if left == right:
            observation.pop("receiver", None)
    return observation


def mapping_diff_paths(current, recorded, prefix=""):
    """Return dotted paths whose values differ between two JSON-like mappings."""

    if isinstance(current, dict) and isinstance(recorded, dict):
        paths = []
        for key in sorted(set(current) | set(recorded)):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in current or key not in recorded:
                paths.append(path)
            else:
                paths.extend(mapping_diff_paths(current[key], recorded[key], path))
        return paths
    if current != recorded:
        return [prefix or "."]
    return []


def load_stage_manifest(run_dir):
    path = Path(run_dir) / STAGE_MANIFEST_NAME
    if not path.exists():
        return {}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {}


def write_stage_success(run_dir, stage, *, fingerprint, projection, output_path):
    require_stage_artifact(output_path, stage)
    manifest = load_stage_manifest(run_dir)
    manifest[stage] = {
        "fingerprint": fingerprint,
        "projection": projection,
        "output_sha256": file_sha256(output_path) if Path(output_path).exists() else None,
        "output_path": str(output_path),
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_contract_version": (
            OBSERVATION_ARTIFACT_CONTRACT_VERSION if stage == "observation" else ECHO_ARTIFACT_CONTRACT_VERSION
        ),
    }
    write_json(Path(run_dir) / STAGE_MANIFEST_NAME, manifest)
    return manifest


def check_reusable_artifact(prepared, *, artifact_stage, allow_legacy=False):
    """Decide whether an upstream artifact can be reused for the current projection.

    Auto-reuse requires a matching fingerprint in ``stage_manifest.json``.
    ``*.generated.json`` is subprocess input only and is never reuse evidence.
    """

    run_dir = Path(prepared["run_dir"])
    if artifact_stage == "observation":
        artifact_path = Path(prepared["observation_output"])
        current_fp = prepared.get("observation_fingerprint")
        label = "观测信息"
    elif artifact_stage == "echo":
        artifact_path = Path(prepared["echo_output_dir"]) / "echo.npz"
        current_fp = prepared.get("echo_fingerprint")
        label = "回波数据"
    else:
        raise ValueError(f"不支持的复用阶段：{artifact_stage}")

    if not artifact_path.exists():
        return ReuseDecision(False, reason=f"找不到{label}：{artifact_path}")
    try:
        require_stage_artifact(artifact_path, artifact_stage)
    except ValueError as exc:
        return ReuseDecision(False, reason=str(exc))

    recorded = load_stage_manifest(run_dir).get(artifact_stage) or {}
    recorded_fp = recorded.get("fingerprint")
    recorded_hash = recorded.get("output_sha256")
    artifact_hash = file_sha256(artifact_path)
    if recorded_fp and not current_fp:
        return ReuseDecision(
            False,
            reason=f"当前配置无法计算{label}指纹，不能与已有产物核对，请补全该阶段参数或重跑上游",
        )
    if recorded_fp and current_fp and recorded_fp == current_fp:
        if not recorded_hash:
            if allow_legacy:
                return ReuseDecision(
                    True,
                    reason=f"按兼容开关复用缺少文件哈希的历史{label}",
                )
            return ReuseDecision(
                False,
                reason=f"{label}阶段记录缺少文件哈希；GUI 需确认，CLI 需 --allow-legacy-reuse",
                requires_confirmation=True,
            )
        if recorded_hash != artifact_hash:
            return ReuseDecision(
                False,
                reason=f"{label}文件哈希与阶段记录不一致，请重跑该阶段",
            )
        return ReuseDecision(True, reason=f"复用已有{label}")
    if recorded_fp and current_fp and recorded_fp != current_fp:
        if artifact_stage == "observation":
            current_proj = observation_dependency_projection(prepared["observation"])
        else:
            current_proj = echo_dependency_projection(
                prepared["echo"],
                file_sha256(prepared["observation_output"])
                if Path(prepared["observation_output"]).exists()
                else None,
                config_path=prepared.get("config_path"),
            )
        mismatched = mapping_diff_paths(recorded.get("projection") or {}, current_proj) or [
            artifact_stage
        ]
        joined = "、".join(mismatched[:12])
        return ReuseDecision(
            False,
            reason=(
                f"当前{label}有效配置与生成该产物时的配置不一致（{joined}），"
                "请重跑上游阶段"
            ),
            mismatched_fields=mismatched,
        )

    if allow_legacy:
        return ReuseDecision(
            True,
            reason=f"按兼容开关复用缺少阶段指纹的历史{label}",
            requires_confirmation=False,
        )
    return ReuseDecision(
        False,
        reason=f"{label}缺少可核对的阶段指纹；GUI 需确认，CLI 需 --allow-legacy-reuse",
        requires_confirmation=True,
    )


def prepare_run(config, *, config_path=None, run_dir, through_stage="full_pipeline"):
    """Stage-aware validation, path resolution, and fingerprinting."""

    if through_stage not in THROUGH_STAGES:
        raise ValueError("through_stage 必须是 observation、echo、inversion 或 full_pipeline")
    run_dir = Path(run_dir)
    raw = copy.deepcopy(config)
    if not isinstance(raw, dict):
        raise ValueError("pipeline 配置必须是 JSON 对象")
    required = {"observation", "echo", "inversion"}
    missing = sorted(required - set(raw))
    unknown = sorted(set(raw) - required)
    if unknown:
        raise ValueError("未知 pipeline 顶层字段：" + ", ".join(unknown))
    if missing:
        raise ValueError(f"pipeline 配置缺少顶层段：{', '.join(missing)}")
    for name in required:
        if not isinstance(raw.get(name), dict):
            raise ValueError(f"{name} 配置必须是 JSON 对象")
    _reject_deprecated_pipeline_keys(raw)

    from observation.src.config_normalize import normalize_observation_config
    from echo.src.config_normalize import normalize_echo_config, resolve_echo_input_paths
    from inversion.src.dataset import normalize_inversion_policy

    observation = raw["observation"]
    echo = raw["echo"]
    inversion = raw["inversion"]
    warnings = []

    if through_stage in {"observation", "echo", "full_pipeline"}:
        observation = _omit_identical_receiver(normalize_observation_config(observation))
    elif through_stage == "inversion":
        try:
            observation = _omit_identical_receiver(normalize_observation_config(observation))
        except (TypeError, ValueError):
            pass

    if through_stage in {"echo", "full_pipeline"}:
        _fill_echo_type_from_event_source(observation, echo)
        _pipeline_waveform_type(observation, echo)
        echo = normalize_echo_config(echo)
        combined = normalize_parameter_ownership(
            {"observation": observation, "echo": echo, "inversion": inversion}
        )
        observation = combined["observation"]
        echo = combined["echo"]
        echo["waveform"] = assemble_echo_waveform(
            observation, echo, validate_sample_rate=True
        )
        echo, path_warnings = resolve_echo_input_paths(echo, config_path=config_path)
        warnings.extend(path_warnings)
        _require_complete_chirp_transmit(observation)
    elif through_stage == "observation":
        _fill_echo_type_from_event_source(observation, echo)
        combined = normalize_parameter_ownership(
            {"observation": observation, "echo": echo, "inversion": inversion}
        )
        observation = combined["observation"]
        echo = combined["echo"]
        _require_complete_chirp_transmit(observation)
        echo["waveform"] = assemble_echo_waveform(
            observation, echo, validate_sample_rate=False
        )
    elif through_stage == "inversion":
        try:
            echo = normalize_echo_config(echo)
            echo, path_warnings = resolve_echo_input_paths(echo, config_path=config_path)
            warnings.extend(path_warnings)
        except (TypeError, ValueError):
            pass

    waveform_type = _pipeline_waveform_type(observation, echo)
    layout = "chirp" if waveform_type == "chirp_pulse_train" else "cw"
    inversion = normalize_inversion_policy(inversion, layout)

    observation_output = run_dir / "observation_info.npz"
    echo_output_dir = run_dir / "echo"
    inversion_output_dir = run_dir / "inversion"
    observation_out = copy.deepcopy(observation)
    observation_out["output_path"] = str(observation_output)
    echo_out = copy.deepcopy(echo)
    echo_out["observation_info_path"] = str(observation_output)
    echo_out["output_path"] = str(echo_output_dir)
    inversion_out = copy.deepcopy(inversion)
    inversion_out["output_path"] = str(inversion_output_dir)

    observation_fp = None
    if through_stage in {"observation", "echo", "full_pipeline"}:
        observation_fp = canonical_fingerprint(observation_dependency_projection(observation))
    else:
        try:
            observation_fp = canonical_fingerprint(observation_dependency_projection(observation))
        except (TypeError, ValueError):
            observation_fp = None
    observation_sha = file_sha256(observation_output) if observation_output.exists() else None
    echo_fp = None
    echo_config_path = str(Path(config_path).resolve()) if config_path else None
    if through_stage in {"echo", "full_pipeline"}:
        echo_fp = canonical_fingerprint(
            echo_dependency_projection(echo_out, observation_sha, config_path=echo_config_path)
        )
    elif through_stage == "inversion":
        try:
            echo_fp = canonical_fingerprint(
                echo_dependency_projection(
                    echo_out, observation_sha, config_path=echo_config_path
                )
            )
        except (TypeError, ValueError):
            echo_fp = None

    return {
        "observation": observation_out,
        "echo": echo_out,
        "inversion": inversion_out,
        "observation_output": observation_output,
        "echo_output_dir": echo_output_dir,
        "inversion_output_dir": inversion_output_dir,
        "through_stage": through_stage,
        "warnings": warnings,
        "snapshot": {
            "observation": copy.deepcopy(observation),
            "echo": copy.deepcopy(echo),
            "inversion": copy.deepcopy(inversion),
        },
        "observation_fingerprint": observation_fp,
        "echo_fingerprint": echo_fp,
        "config_path": str(Path(config_path).resolve()) if config_path else None,
        "run_dir": run_dir,
    }


def _reject_deprecated_pipeline_keys(config):
    """Reject deprecated keys at the strict pipeline boundary.

    Deprecated keys fail here with a clear message instead of silently passing
    through to subprocesses. Observation's normalizer applies the same policy.
    """

    observation = config.get("observation") or {}
    inversion = config.get("inversion") or {}

    if "schema_version" in config:
        raise ValueError("schema_version 已废弃；项目不再使用版本号字段")
    if "campaign" in observation:
        raise ValueError("observation.campaign 已废弃；观测窗口请写到 schedule.start_utc / schedule.end_utc")
    if "solver" in observation:
        raise ValueError("observation.solver 已废弃；光行时收敛策略由实现内部常量决定")

    from observation.src.config_normalize import OBSERVATION_WAVEFORM_DEPRECATED

    if "waveform" in observation:
        raise ValueError(OBSERVATION_WAVEFORM_DEPRECATED)

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
        raise ValueError("receive.acquisitions 已废弃；脉冲序列请使用 schedule + transmit + radar_system + receiver_sampling")

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
    # Identical TX/RX geometry → monostatic omit receiver.  Observation
    # normalize fills a copy of the transmitter; this restores the omit form.
    config["observation"] = config.get("observation") or {}
    echo = config.setdefault("echo", {})
    inversion = config.setdefault("inversion", {})

    config["echo"] = echo
    config["inversion"] = inversion

    # Validate at the interfaces owned by each submodule.  The pipeline does
    # not maintain a second, drifting copy of their field lists.
    from observation.src.config_normalize import normalize_observation_config
    from echo.src.config_normalize import normalize_echo_config
    from inversion.src.dataset import normalize_inversion_policy

    config["observation"] = _omit_identical_receiver(
        normalize_observation_config(config["observation"])
    )
    _fill_echo_type_from_event_source(config["observation"], echo)
    _pipeline_waveform_type(config["observation"], echo)
    config["echo"] = normalize_echo_config(config["echo"])
    config = normalize_parameter_ownership(config)
    waveform_type = _pipeline_waveform_type(config["observation"], config["echo"])
    layout = "chirp" if waveform_type == "chirp_pulse_train" else "cw"
    config["inversion"] = normalize_inversion_policy(config["inversion"], layout)
    return config


def _require_complete_chirp_transmit(observation):
    """Reject a Chirp execution config that is missing pulse timing fields."""

    from observation.src.config_normalize import observation_event_source

    event = observation_event_source(observation)
    if event != "chirp_pulse_train":
        return
    transmit = observation.get("transmit")
    if not isinstance(transmit, dict) or "prf_hz" not in transmit or "pulse_width_s" not in transmit:
        raise ValueError(
            "Chirp 脉冲序列需要 observation.transmit.prf_hz 与 observation.transmit.pulse_width_s"
        )


def _echo_waveform_type(echo):
    value = (echo.get("waveform") or {}).get("type") if isinstance(echo, dict) else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fill_echo_type_from_event_source(observation, echo):
    from observation.src.config_normalize import observation_event_source

    event = observation_event_source(observation)
    waveform = echo.setdefault("waveform", {})
    if event and not _echo_waveform_type({"waveform": waveform}):
        waveform["type"] = event


def _pipeline_waveform_type(observation, echo):
    from observation.src.config_normalize import observation_event_source

    echo_type = _echo_waveform_type(echo)
    event = observation_event_source(observation)
    if echo_type == "lfm_chirp":
        raise ValueError("echo.waveform.type=lfm_chirp 已废弃；请使用 chirp_pulse_train")
    if echo_type and event and echo_type != event:
        source = (
            "schedule（Chirp 脉冲序列）"
            if event == "chirp_pulse_train"
            else "receive（连续波）"
        )
        raise ValueError(
            f"echo.waveform.type={echo_type!r} 与观测事件源不一致：{source}"
        )
    return str(echo_type or event or "continuous_wave")


def normalize_parameter_ownership(config):
    """Reject fields placed in the wrong stage (strict v4 ownership).

    RF ``type`` belongs to ``echo.waveform``. Pulse PRF/width belong to
    ``observation.transmit``. Every other editable field has exactly one owner,
    so writing it on the wrong side is an error rather than something to
    silently migrate.
    """

    config = copy.deepcopy(config)
    observation = config.setdefault("observation", {})
    echo = config.setdefault("echo", {})
    obs_transmit = dict(observation.get("transmit", {}))
    echo_waveform = dict(echo.get("waveform", {}))
    echo_radar = dict(echo.get("radar", {}))

    if "waveform" in observation:
        from observation.src.config_normalize import OBSERVATION_WAVEFORM_DEPRECATED

        raise ValueError(OBSERVATION_WAVEFORM_DEPRECATED)
    if "type" in obs_transmit:
        raise ValueError("波形类型请写 echo.waveform.type，不要写 observation.transmit.type")
    for key in ("prf_hz", "pulse_width_s"):
        if key in echo_waveform:
            raise ValueError(
                f"waveform.{key} 应由 observation.transmit 持有，请从 echo.waveform 移除"
            )
    if "fast_sample_rate_hz" in echo_waveform:
        raise ValueError(
            "waveform.fast_sample_rate_hz 应由 observation.receiver_sampling 持有，"
            "请从 echo.waveform 移除"
        )
    for key in ("bandwidth_hz", "amplitude", "baseband_convention"):
        if key in obs_transmit:
            raise ValueError(
                f"{key} 应由 echo.waveform 持有，请从 observation.transmit 移除"
            )
    if "carrier_frequency_hz" in obs_transmit:
        raise ValueError("carrier_frequency_hz 应由 echo.radar 持有，请从 observation.transmit 移除")

    _pipeline_waveform_type(observation, echo)

    if obs_transmit:
        observation["transmit"] = {
            key: obs_transmit[key] for key in OBSERVATION_TRANSMIT_KEYS if key in obs_transmit
        }
    else:
        observation.pop("transmit", None)
    echo["waveform"] = {
        key: echo_waveform[key] for key in ECHO_WAVEFORM_KEYS if key in echo_waveform
    }
    if echo_radar:
        echo["radar"] = echo_radar
    config["observation"] = observation
    config["echo"] = echo
    return config


def assemble_echo_waveform(observation_config, echo_config, *, validate_sample_rate=True):
    """Validate the RF waveform against the observation-owned ADC rate."""

    echo_waveform = copy.deepcopy(echo_config.get("waveform", {}))
    if "type" not in echo_waveform:
        from observation.src.config_normalize import observation_event_source

        event = observation_event_source(observation_config)
        if event:
            echo_waveform["type"] = event
    _pipeline_waveform_type(observation_config, {"waveform": echo_waveform})
    bandwidth = echo_waveform.get("bandwidth_hz")
    sample_rate = (observation_config.get("receiver_sampling") or {}).get("fast_sample_rate_hz")
    if validate_sample_rate and bandwidth is not None and sample_rate is not None and float(sample_rate) <= abs(float(bandwidth)):
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


def prepared_configs(config, run_dir, *, validate_echo_waveform=True):
    through_stage = "echo" if validate_echo_waveform else "observation"
    prepared = prepare_run(config, run_dir=run_dir, through_stage=through_stage)
    return {
        "observation": prepared["observation"],
        "echo": prepared["echo"],
        "inversion": prepared["inversion"],
        "observation_output": prepared["observation_output"],
        "echo_output_dir": prepared["echo_output_dir"],
        "inversion_output_dir": prepared["inversion_output_dir"],
    }


def main():
    args = parse_args()
    config_path = Path(args.config).resolve() if args.config else None
    config = canonical_pipeline_config(
        load_json(args.config) if args.config else copy.deepcopy(DEFAULT_CONFIG)
    )

    run_dir = run_directory(args)
    config_dir = run_dir / "configs"
    if args.skip_observation and args.skip_echo:
        through_stage = "inversion"
    elif args.skip_observation:
        through_stage = "echo"
    else:
        through_stage = "full_pipeline"
    prepared = prepare_run(
        config,
        config_path=config_path,
        run_dir=run_dir,
        through_stage=through_stage,
    )

    if args.skip_observation:
        decision = check_reusable_artifact(
            prepared, artifact_stage="observation", allow_legacy=args.allow_legacy_reuse
        )
        if not decision.reusable:
            raise SystemExit(f"无法复用观测产物：{decision.reason}")
        print(decision.reason, flush=True)
    if args.skip_echo:
        decision = check_reusable_artifact(
            prepared, artifact_stage="echo", allow_legacy=args.allow_legacy_reuse
        )
        if not decision.reusable:
            raise SystemExit(f"无法复用回波产物：{decision.reason}")
        print(decision.reason, flush=True)

    if not args.skip_observation:
        write_json(config_dir / "observation.generated.json", prepared["observation"])
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
        try:
            require_stage_artifact(prepared["observation_output"], "observation")
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        write_stage_success(
            run_dir,
            "observation",
            fingerprint=prepared["observation_fingerprint"],
            projection=observation_dependency_projection(prepared["observation"]),
            output_path=prepared["observation_output"],
        )

    if not args.skip_echo:
        write_json(config_dir / "echo.generated.json", prepared["echo"])
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
        echo_npz = Path(prepared["echo_output_dir"]) / "echo.npz"
        try:
            require_stage_artifact(echo_npz, "echo")
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        observation_sha = file_sha256(prepared["observation_output"])
        echo_proj = echo_dependency_projection(
            prepared["echo"],
            observation_sha,
            config_path=prepared.get("config_path"),
        )
        write_stage_success(
            run_dir,
            "echo",
            fingerprint=canonical_fingerprint(echo_proj),
            projection=echo_proj,
            output_path=echo_npz,
        )

    observation_artifact = Path(prepared["observation_output"])
    echo_artifact = Path(prepared["echo_output_dir"]) / "echo.npz"
    if observation_artifact.exists() and echo_artifact.exists():
        try:
            validate_observation_echo_contract(observation_artifact, echo_artifact)
        except ValueError as exc:
            raise SystemExit(f"上游产物不兼容：{exc}") from exc

    inversion_src = str(ROOT / "inversion" / "src")
    if not INVERSION_ENTRY.is_file():
        raise SystemExit(f"找不到反演入口：{INVERSION_ENTRY}")
    write_json(config_dir / "inversion.generated.json", prepared["inversion"])
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
    summary = Path(prepared["inversion_output_dir"]) / "summary.json"
    if not summary.exists():
        raise SystemExit("inversion 退出码为 0 但未生成 summary.json")
    write_json(run_dir / "manifest.json", build_manifest(prepared["snapshot"]))

    print("\n完成。")
    print(f"实验目录: {run_dir}")
    print(f"观测信息: {prepared['observation_output']}")
    print(f"回波数据: {prepared['echo_output_dir'] / 'echo.npz'}")
    print(f"反演结果: {prepared['inversion_output_dir'] / 'summary.json'}")


if __name__ == "__main__":
    main()
