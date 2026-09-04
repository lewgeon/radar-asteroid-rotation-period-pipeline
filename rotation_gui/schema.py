"""Declarative GUI schema: stages, labels, choices, units, and defaults."""

from __future__ import annotations

STAGES = ("observation", "echo", "inversion")

STAGE_LABELS = {
    "observation": "1. 观测解算",
    "echo": "2. 回波仿真",
    "inversion": "3. 周期反演",
}

STAGE_LABELS_EN = {
    "observation": "1. Observation",
    "echo": "2. Echo Simulation",
    "inversion": "3. Period Inversion",
}

GROUP_LABELS = {
    "target": "目标参数",
    "transmitter": "发射站",
    "receiver": "接收站",
    "receive": "接收设置",
    "ephemeris": "星历查询",
    "solver": "求解器",
    "compute": "计算设置",
    "scattering_spot": "散射热点",
    "radar": "雷达参数",
    "waveform": "波形参数",
}

GROUP_LABELS_EN = {
    "target": "Target",
    "transmitter": "Transmitter",
    "receiver": "Receiver",
    "receive": "Receive",
    "ephemeris": "Ephemeris",
    "solver": "Solver",
    "compute": "Compute",
    "scattering_spot": "Scattering Spot",
    "radar": "Radar",
    "waveform": "Waveform",
    "通用参数": "General",
}

STAGE_GROUP_ORDER = {
    "observation": ("通用参数", "target", "transmitter", "receiver", "receive", "ephemeris", "solver"),
    "echo": ("通用参数", "compute", "target", "scattering_spot", "radar", "waveform"),
    "inversion": ("通用参数",),
}

CHOICES = {
    "state": ("static", "linear", "geodetic_fixed", "astropy_geodetic", "horizons_vectors"),
    "device": ("auto", "cuda:0", "cpu"),
    "dtype": ("float32", "float64"),
    "type": ("continuous_wave", "chirp_pulse_train"),
    "object_type": ("null", "smallbody"),
    "query_mode": ("auto", "range", "list"),
    "spin_pole_frame": ("equatorial", "ecliptic"),
}

OPTION_LABELS = {
    "zh": {
        "true": "是",
        "false": "否",
        "continuous_wave": "连续波",
        "chirp_pulse_train": "Chirp 脉冲序列",
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
    },
    "en": {
        "true": "Yes",
        "false": "No",
        "continuous_wave": "Continuous Wave",
        "chirp_pulse_train": "Chirp Pulse Train",
        "equatorial": "Equatorial",
        "icrs": "Equatorial",
        "ecliptic": "Ecliptic",
        "auto": "Auto",
        "range": "Range",
        "list": "List",
        "null": "None",
        "smallbody": "Small Body",
        "static": "Static",
        "linear": "Linear",
        "cartesian": "Cartesian",
        "geodetic": "Geodetic",
        "geodetic_fixed": "Geodetic Fixed",
        "astropy_geodetic": "Astropy Geodetic",
        "horizons_vectors": "Horizons Vectors",
    },
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
    "location": "@399",
    "refplane": "earth",
    "padding_s": 7200.0,
    "query_step_s": 60.0,
    "query_mode": "auto",
    "query_chunk_size": 80,
    "min_query_chunk_size": 5,
    "query_retries": 2,
    "cache": True,
}

EPHEMERIS_FIELD_ORDER = (
    "location",
    "refplane",
    "padding_s",
    "query_step_s",
    "query_mode",
    "query_chunk_size",
    "min_query_chunk_size",
    "query_retries",
    "cache",
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
    "acquisitions": "相干采集计划",
    "tolerance_s": "收敛阈值",
    "max_iter": "最大迭代次数",
    "location": "参考中心",
    "refplane": "参考平面",
    "padding_s": "星历余量",
    "query_step_s": "星历步长",
    "query_mode": "查询模式",
    "query_chunk_size": "查询分块",
    "min_query_chunk_size": "最小重试分块",
    "query_retries": "最大重试次数",
    "cache": "使用缓存",
    "model_path": "形状模型",
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
    "receive_window_start_s": "接收窗起点",
    "receive_window_duration_s": "接收窗时长",
    "pri_s": "脉冲重复间隔",
    "first_pulse_start_s": "首脉冲起点",
    "pulse_count": "脉冲数量",
    "pulse_start_s": "脉冲起点序列",
    "snr_db": "信噪比",
    "stft_window_samples": "STFT窗长",
    "stft_overlap_fraction": "STFT重叠",
    "period_min_s": "最小周期",
    "period_max_s": "最大周期",
    "period_grid_size": "周期网格数",
}

FIELD_LABELS_EN = {
    "id": "ID",
    "name": "Name",
    "state": "State",
    "position_m": "Position",
    "position0_m": "Initial Position",
    "velocity_m_s": "Velocity",
    "lat_deg": "Latitude",
    "lon_deg": "Longitude",
    "height_m": "Height",
    "geodetic_time_dependent": "Update Position with Earth Rotation",
    "linear_motion": "Use Uniform Linear Motion",
    "object_type": "Object Type",
    "start_utc": "Start UTC",
    "duration_s": "Duration",
    "sample_rate_hz": "Sample Rate",
    "acquisitions": "Coherent Acquisition Schedule",
    "tolerance_s": "Tolerance",
    "max_iter": "Maximum Iterations",
    "location": "Center",
    "refplane": "Reference Plane",
    "padding_s": "Padding",
    "query_step_s": "Query Step",
    "query_mode": "Query Mode",
    "query_chunk_size": "Query Chunk",
    "min_query_chunk_size": "Min Retry Chunk",
    "query_retries": "Maximum Retries",
    "cache": "Use Cache",
    "model_path": "Shape Model",
    "seed": "Noise Seed",
    "chunk_size": "Chunk Size",
    "device": "Device",
    "dtype": "Float Type",
    "rotation_period_s": "Rotation Period",
    "initial_phase_deg": "Initial Phase",
    "spin_pole_frame": "Frame",
    "spin_pole_icrs_deg": "α / δ",
    "spin_pole_ecliptic_deg": "λ / β",
    "scattering_power": "Scattering Power",
    "direction_body": "Spot Direction",
    "enabled": "Enable Scattering Spot",
    "radius_deg": "Spot Radius",
    "strength": "Spot Strength",
    "carrier_frequency_hz": "Carrier Frequency",
    "type": "Waveform",
    "amplitude": "Amplitude",
    "pulse_width_s": "Pulse Width",
    "bandwidth_hz": "Chirp Bandwidth",
    "fast_sample_rate_hz": "Fast-time Sample Rate",
    "receive_window_start_s": "Receive Window Start",
    "receive_window_duration_s": "Receive Window Duration",
    "pri_s": "PRI",
    "first_pulse_start_s": "First Pulse Start",
    "pulse_count": "Pulse Count",
    "pulse_start_s": "Pulse Starts",
    "snr_db": "SNR",
    "stft_window_samples": "STFT Window",
    "stft_overlap_fraction": "STFT Overlap",
    "period_min_s": "Min Period",
    "period_max_s": "Max Period",
    "period_grid_size": "Period Grid Size",
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
    "tolerance_s": "s",
    "padding_s": "s",
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
    "receive_window_start_s": "s",
    "receive_window_duration_s": "s",
    "pri_s": "s",
    "first_pulse_start_s": "s",
    "snr_db": "dB",
    "period_min_s": "s",
    "period_max_s": "s",
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

CONTROL_HEIGHT = 32

EDITABLE_UNIT_WIDTH = 76

FIXED_UNIT_WIDTH = 44

SCATTERING_SPOT_DEFAULTS = {
    "enabled": True,
    "direction_body": [1.0, 0.25, 0.15],
    "radius_deg": 12.0,
    "strength": 8.0,
}
