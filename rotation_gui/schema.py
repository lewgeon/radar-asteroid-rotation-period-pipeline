"""Declarative GUI schema: stages, labels, choices, units, and defaults."""

from __future__ import annotations

STAGES = ("observation", "echo", "inversion")

STAGE_LABELS = {
    "observation": "1. 观测解算",
    "echo": "2. 回波仿真",
    "inversion": "3. 周期反演",
}

GROUP_LABELS = {
    "target": "目标参数",
    "transmitter": "发射站",
    "receiver": "接收站",
    "receive": "接收设置",
    "ephemeris": "星历查询",
    "compute": "计算设置",
    "scattering_spot": "散射特性",
    "noise": "噪声",
    "radar": "雷达参数",
    "waveform": "发射时序",
    "campaign": "观测活动",
    "visibility": "可见性约束",
    "radar_system": "雷达体制",
    "receiver_sampling": "接收采样",
    "schedule": "发射计划",
    "radar_parameters": "射频波形",
    "radar_acquire": "雷达体制与接收",
    "sites": "测站",
    "plan": "观测计划",
    "geometry": "几何求解",
    "spectrum": "时频分析",
    "period_search": "周期搜索",
    "echo_options": "回波输出",
    "通用参数": "通用参数",
    "general": "通用参数",
}

STAGE_GROUP_ORDER = {
    "observation": ("通用参数", "target", "transmitter", "receiver", "receive", "ephemeris"),
    "echo": ("通用参数", "compute", "target", "scattering_spot", "radar", "waveform"),
    "inversion": ("通用参数",),
}

CHOICES = {
    "state": ("static", "linear", "geodetic_fixed", "astropy_geodetic", "horizons_vectors"),
    "device": ("auto", "cuda:0", "cpu"),
    "dtype": ("float32", "float64"),
    "type": ("continuous_wave", "chirp_pulse_train"),
    "scattering_model": ("mesh", "point_target"),
    "object_type": ("null", "smallbody"),
    "spin_pole_frame": ("equatorial", "ecliptic"),
    "mode": ("monostatic_switching", "bistatic_continuous"),
    "selection": ("manual", "equal_visible_time", "random_visible_time"),
    "echo_output_reference": ("centroid_compensated", "raw_baseband"),
    "intrapulse_motion_model": ("per_pulse_linear", "frozen"),
    "motion_compensation": ("auto", "none", "centroid_geometry"),
    "period_time_role": ("scatter_centroid", "receive_centroid"),
    "baseband_convention": ("zero_to_bandwidth", "centered"),
}

# Domain-facing enums. Targets never use ground-station geodetic models.
TARGET_STATE_CHOICES = ("static", "linear", "horizons_vectors")
STATION_COORDINATE_CHOICES = ("cartesian", "geodetic")
STATION_TECHNICAL_STATES = ("static", "linear", "geodetic_fixed", "astropy_geodetic")
OBSERVATION_BODY_GROUPS = ("target", "transmitter", "receiver")
STATION_GROUPS = ("transmitter", "receiver")

OPTION_LABELS = {
    "true": "是",
    "false": "否",
    "continuous_wave": "连续波",
    "chirp_pulse_train": "Chirp 脉冲序列",
    "mesh": "三角面元模型",
    "point_target": "单散射点",
    "equatorial": "赤道坐标系",
    "icrs": "赤道坐标系",
    "ecliptic": "黄道坐标系",
    "auto": "自动",
    "range": "范围查询",
    "list": "列表查询",
    "null": "无",
    "smallbody": "小天体",
    "static": "静态位置",
    "linear": "匀速直线",
    "cartesian": "直角坐标",
    "geodetic": "大地坐标",
    "geodetic_fixed": "固定大地坐标",
    "astropy_geodetic": "Astropy 大地坐标",
    "horizons_vectors": "Horizons 星历",
    "monostatic_switching": "单站收发切换",
    "bistatic_continuous": "双站连续",
    "manual": "手动指定",
    "equal_visible_time": "可见时段等间隔",
    "random_visible_time": "可见时段随机",
    "centroid_compensated": "质心补偿基带",
    "raw_baseband": "原始复基带",
    "per_pulse_linear": "脉内一阶运动",
    "frozen": "冻结几何",
    "none": "无",
    "centroid": "质心",
    "centroid_geometry": "质心几何补偿",
    "ephemeris": "星历补偿",
    "scatter_centroid": "散射质心时标",
    "receive_centroid": "接收质心时标",
    "receive": "接收时标",
    "emit": "发射时标",
    "leading_edge": "前沿",
    "zero_to_bandwidth": "零到带宽",
    "centered": "对称基带",
}

HORIZONS_ID_TYPE_ALIASES = {
    "": None,
    "none": None,
    "null": None,
    "small body": "smallbody",
    "small_body": "smallbody",
    "small-body": "smallbody",
}

HORIZONS_OBJECT_TYPES = {None, "smallbody"}

STATE_FIELDS = {
    "static": ("position_m",),
    "linear": ("position0_m", "velocity_m_s"),
    "geodetic_fixed": ("lat_deg", "lon_deg", "height_m"),
    "astropy_geodetic": ("lat_deg", "lon_deg", "height_m"),
    "horizons_vectors": ("id", "object_type"),
}

STATE_DEFAULTS = {
    "position_m": [0.0, 0.0, 0.0],
    "position0_m": [0.0, 0.0, 0.0],
    "velocity_m_s": [0.0, 0.0, 0.0],
    "lat_deg": 0.0,
    "lon_deg": 0.0,
    "height_m": 0.0,
    "object_type": None,
}

EPHEMERIS_FIELD_DEFAULTS = {
    "query_step_s": 60.0,
}

EPHEMERIS_FIELD_ORDER = (
    "query_step_s",
)

COMMON_FIELD_ORDER = ("id", "name", "state")

PROGRESS_PREFIX = "__PROGRESS__ "

WARNING_PREFIX = "__WARNING__ "

ERROR_PREFIX = "__ERROR__ "

FIELD_LABELS = {
    "id": "ID",
    "name": "名称",
    "state": "状态",
    "position_m": "位置",
    "position0_m": "初始位置",
    "velocity_m_s": "速度",
    "lat_deg": "纬度",
    "lon_deg": "经度",
    "height_m": "高度",
    "geodetic_time_dependent": "随地球自转更新位置",
    "linear_motion": "进行匀速直线运动",
    "object_type": "目标类型",
    "start_utc": "开始时间",
    "duration_s": "接收时长",
    "sample_rate_hz": "采样率",
    "query_step_s": "星历步长",
    "model_path": "形状模型",
    "scattering_model": "散射模型",
    "seed": "噪声种子",
    "chunk_size": "计算分块",
    "device": "计算设备",
    "dtype": "浮点精度",
    "rotation_period_s": "自转周期",
    "initial_phase_deg": "初始相位",
    "spin_pole_frame": "坐标系",
    "spin_pole_icrs_deg": "α / δ",
    "spin_pole_ecliptic_deg": "λ / β",
    "scattering_power": "散射指数",
    "direction_body": "斑块方向",
    "enabled": "启用散射热点",
    "radius_deg": "斑块半径",
    "strength": "斑块强度",
    "carrier_frequency_hz": "载频",
    "type": "波形类型",
    "amplitude": "幅度",
    "pulse_width_s": "脉冲宽度",
    "bandwidth_hz": "Chirp 带宽",
    "fast_sample_rate_hz": "快时间采样率",
    "noise_enabled": "添加噪声",
    "snr_db": "信噪比",
    "stft_window_samples": "STFT窗长",
    "stft_overlap_fraction": "STFT重叠",
    "period_min_s": "最小周期",
    "period_max_s": "最大周期",
    "period_grid_size": "周期网格数",
    "target_id": "目标 ID",
    "query_start_utc": "查询开始",
    "query_end_utc": "查询结束",
    "start_utc": "窗口开始",
    "end_utc": "窗口结束",
    "min_tx_elevation_deg": "发射最低仰角",
    "min_rx_elevation_deg": "接收最低仰角",
    "sample_step_s": "可见性采样步长",
    "mode": "工作体制",
    "switch_time_s": "收发切换时间",
    "safety_margin_s": "切换安全余量",
    "prf_hz": "脉冲重复频率",
    "baseband_convention": "基带约定",
    "pre_guard_s": "ADC 前置保护",
    "post_guard_s": "ADC 后置保护",
    "extent_path_m": "体尺度路径展宽",
    "amplitude_scale": "点目标幅度",
    "selection": "选时方式",
    "run_count": "Run 数量",
    "run_duration_s": "单次 Run 时长",
    "random_seed": "随机种子",
    "runs": "Run 时刻表",
    "echo_output_reference": "回波参考系",
    "intrapulse_motion_model": "脉内运动模型",
    "motion_compensation": "运动补偿",
    "period_time_role": "周期时标",
    "harmonics": "谐波数",
    "cpi_duration_s": "CPI 时长",
    "cpi_hop_duration_s": "CPI 步进时长",
}

FIELD_UNITS = {
    "position_m": "m",
    "position0_m": "m",
    "velocity_m_s": "m/s",
    "lat_deg": "°",
    "lon_deg": "°",
    "height_m": "m",
    "duration_s": "s",
    "sample_rate_hz": "Hz",
    "query_step_s": "s",
    "rotation_period_s": "s",
    "initial_phase_deg": "°",
    "spin_pole_icrs_deg": "°",
    "spin_pole_ecliptic_deg": "°",
    "radius_deg": "°",
    "carrier_frequency_hz": "Hz",
    "pulse_width_s": "s",
    "bandwidth_hz": "Hz",
    "fast_sample_rate_hz": "Hz",
    "snr_db": "dB",
    "period_min_s": "s",
    "period_max_s": "s",
    "switch_time_s": "s",
    "safety_margin_s": "s",
    "prf_hz": "Hz",
    "pre_guard_s": "s",
    "post_guard_s": "s",
    "run_duration_s": "s",
    "cpi_duration_s": "s",
    "cpi_hop_duration_s": "s",
    "min_tx_elevation_deg": "°",
    "min_rx_elevation_deg": "°",
}

UNIT_CHOICES = {
    "duration_s": (("h", 3600.0), ("min", 60.0), ("s", 1.0)),
    "rotation_period_s": (("h", 3600.0), ("s", 1.0)),
    "initial_phase_deg": (("π rad", 180.0), ("°", 1.0)),
    "period_min_s": (("h", 3600.0), ("s", 1.0)),
    "period_max_s": (("h", 3600.0), ("s", 1.0)),
    "carrier_frequency_hz": (("GHz", 1.0e9), ("MHz", 1.0e6), ("Hz", 1.0)),
    "bandwidth_hz": (("MHz", 1.0e6), ("kHz", 1.0e3), ("Hz", 1.0)),
    "sample_rate_hz": (("MHz", 1.0e6), ("kHz", 1.0e3), ("Hz", 1.0)),
    "fast_sample_rate_hz": (("MHz", 1.0e6), ("kHz", 1.0e3), ("Hz", 1.0)),
}

# Numeric editors share one validation path.  Keep this list keyed by the
# serialised field name so presentation code never has to guess from a value's
# current Python type (which may already be an invalid draft string).
NUMERIC_FIELD_KEYS = frozenset(
    set(FIELD_UNITS)
    | {
        "amplitude",
        "amplitude_scale",
        "extent_path_m",
        "seed",
        "chunk_size",
        "facet_chunk_size",
        "fast_sample_chunk_size",
        "frozen_max_carrier_phase_error_rad",
        "frozen_max_range_walk_samples",
        "frozen_max_rotation_error_deg",
        "strength",
        "stft_window_samples",
        "stft_overlap_fraction",
        "period_grid_size",
        "harmonics",
        "run_count",
        "random_seed",
    }
)

INTEGER_FIELD_KEYS = frozenset(
    {
        "seed",
        "chunk_size",
        "facet_chunk_size",
        "fast_sample_chunk_size",
        "stft_window_samples",
        "period_grid_size",
        "harmonics",
        "run_count",
        "random_seed",
    }
)

CONTROL_HEIGHT = 32

EDITABLE_UNIT_WIDTH = 76

FIXED_UNIT_WIDTH = 44

SCATTERING_SPOT_DEFAULTS = {
    "enabled": True,
    "direction_body": [1.0, 0.25, 0.15],
    "radius_deg": 12.0,
    "strength": 8.0,
}

# Used when the session starts as point_target and the user switches to mesh
# without a prior mesh draft to restore.
MESH_ECHO_DEFAULTS = {
    "model_path": "models/ellipsoid.obj",
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
}
