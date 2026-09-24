"""Collection path gate: one metre window replaces the chirp time guards."""

from __future__ import annotations

import warnings

from observation.src.config_normalize import normalize_observation_config
from observation.src.light_time import C
from observation.src.planning import stationary_chirp_gate


def _chirp_observation(**sampling):
    return {
        "transmitter": {"state": "static", "position_m": [0.0, 0.0, 0.0]},
        "target": {"state": "static", "position_m": [1.0, 0.0, 0.0], "extent_path_m": 300.0},
        "transmit": {"prf_hz": 2.0, "pulse_width_s": 4.0e-5},
        "radar_system": {
            "mode": "bistatic_continuous",
            "switch_time_s": 0.0,
            "safety_margin_s": 0.0,
        },
        "receiver_sampling": {"fast_sample_rate_hz": 2.0e8, **sampling},
        "schedule": {
            "start_utc": "2026-01-01T00:00:00Z",
            "end_utc": "2026-01-01T00:10:00Z",
            "selection": "manual",
            "runs": [{"tx_start_utc": "2026-01-01T00:00:00Z", "tx_duration_s": 1.0}],
        },
    }


def test_legacy_time_guards_fold_into_the_wider_path_gate():
    config = _chirp_observation(pre_guard_s=0.01, post_guard_s=0.01)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        out = normalize_observation_config(config)
    assert "pre_guard_s" not in out["receiver_sampling"]
    assert "post_guard_s" not in out["receiver_sampling"]
    assert out["target"]["extent_path_m"] == max(300.0, 0.01 * C)
    notes = [str(item.message) for item in caught if str(item.message).startswith("采集路径窗已合并")]
    assert notes
    assert "短" in notes[0]


def test_legacy_time_guards_do_not_shrink_a_wider_path_gate():
    config = _chirp_observation(pre_guard_s=0.0, post_guard_s=1.0e-6)
    config["target"]["extent_path_m"] = 1.0e6
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        out = normalize_observation_config(config)
    assert out["target"]["extent_path_m"] == 1.0e6
    notes = [str(item.message) for item in caught if str(item.message).startswith("采集路径窗已合并")]
    assert notes and "短" in notes[0]


def test_plan_reception_rejects_legacy_time_guards():
    import numpy as np

    from observation.src.light_time import ThreeEventSolution
    from observation.src.planning import build_transmit_schedule, plan_reception

    reference = "2026-01-01T00:00:00Z"
    waveform = {"prf_hz": 2.0, "pulse_width_s": 4.0e-5}
    schedule = build_transmit_schedule(
        reference,
        [{"tx_start_utc": reference, "tx_duration_s": 1.0}],
        waveform,
        "bistatic_continuous",
    )
    emit = schedule.emit_elapsed_s
    count = len(emit)
    los = np.tile([1.0, 0.0, 0.0], (count, 1))
    geometry = ThreeEventSolution(
        receive_elapsed_s=emit + 1.0,
        scatter_elapsed_s=emit + 0.5,
        emit_elapsed_s=emit,
        tx_los_icrs=los,
        rx_los_icrs=los,
        tx_range_m=np.ones(count),
        rx_range_m=np.ones(count),
    )
    try:
        plan_reception(
            schedule,
            geometry,
            waveform,
            {"fast_sample_rate_hz": 1.0e6, "pre_guard_s": 0.0},
            {"mode": "bistatic_continuous"},
        )
    except ValueError as exc:
        assert "extent_path_m" in str(exc)
    else:
        raise AssertionError("plan_reception accepted pre_guard_s")


def test_asymmetric_guards_warn_each_side_separately():
    config = _chirp_observation(pre_guard_s=0.01, post_guard_s=0.001)
    config["target"]["extent_path_m"] = 100.0
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        out = normalize_observation_config(config)
    assert out["target"]["extent_path_m"] == max(100.0, 0.01 * C, 0.001 * C)
    notes = [str(item.message) for item in caught if str(item.message).startswith("采集路径窗已合并")]
    assert len(notes) == 1
    assert "前侧比原先保护时间与路径展宽之和短" in notes[0]
    assert "后侧比原先保护时间与路径展宽之和长" in notes[0]


def test_point_target_debug_row_is_shorter_without_the_old_millisecond_guards():
    import json
    from pathlib import Path

    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "configs" / "point_target_debug.json").read_text(
            encoding="utf-8"
        )
    )["observation"]
    sampling = payload["receiver_sampling"]
    assert "pre_guard_s" not in sampling and "post_guard_s" not in sampling
    extent = float(payload["target"]["extent_path_m"])
    pulse = float(payload["transmit"]["pulse_width_s"])
    sample_rate = float(sampling["fast_sample_rate_hz"])
    assert extent == 3000.0
    _gate_s, _n_pre, _n_after, fast_count = stationary_chirp_gate(extent, pulse, sample_rate)
    import math

    old_before_s = 0.001 + extent / C
    old_after_s = 0.001 + pulse + extent / C
    old_fast = (
        math.ceil(old_before_s * sample_rate)
        + math.ceil(old_after_s * sample_rate + 0.5)
        + 1
    )
    assert fast_count < old_fast


def test_simple_chirp_plan_matches_stationary_gate():
    import sys
    from pathlib import Path

    echo_root = Path(__file__).resolve().parents[1] / "echo"
    if str(echo_root) not in sys.path:
        sys.path.insert(0, str(echo_root))
    from scripts.make_simple_chirp_plan import make_simple_chirp_plan

    payload = make_simple_chirp_plan(
        start_utc="2026-01-01T00:00:00Z",
        num_pulses=4,
        prf_hz=4.0,
        pulse_width_s=4.0e-5,
        fast_sample_rate_hz=2.0e8,
        target_range_m=C,
        target_extent_m=1000.0,
    )
    _gate_s, _n_pre, _n_after, fast_count = stationary_chirp_gate(1000.0, 4.0e-5, 2.0e8)
    assert payload["row_valid"].shape[1] == fast_count


def test_folded_post_guard_is_not_added_twice_into_schedule_reserve():
    from observation.src.campaign_planning import resolve_campaign_run_plan

    station_x = 6_371_000.0
    target_x = station_x + 10.0 * C
    config = {
        "schedule": {
            "start_utc": "2026-01-01T00:00:00Z",
            "end_utc": "2026-01-01T00:00:25Z",
            "selection": "equal_visible_time",
            "run_duration_s": 1.0,
            "run_count": 1,
        },
        "transmitter": {"state": "static", "position_m": [station_x, 0.0, 0.0]},
        "receiver": {"state": "static", "position_m": [station_x, 0.0, 0.0]},
        "target": {"state": "static", "position_m": [target_x, 0.0, 0.0], "extent_path_m": 0.0},
        "radar_system": {
            "mode": "monostatic_switching",
            "switch_time_s": 0.1,
            "safety_margin_s": 0.1,
        },
        "transmit": {"pulse_width_s": 0.01, "prf_hz": 2.0},
        "receiver_sampling": {"fast_sample_rate_hz": 1000.0, "post_guard_s": 0.01},
    }
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always", UserWarning)
        preview = resolve_campaign_run_plan(config, allow_infeasible_preview=True)
    # D + round trip + switch + safety + folded gate + pulse.
    # Adding the old post_guard a second time would make this 21.23 s.
    assert preview.occupied_duration_s == 1.0 + 20.0 + 0.1 + 0.1 + 0.01 + 0.01


def test_negative_legacy_guard_is_rejected():
    config = _chirp_observation(pre_guard_s=-0.1, post_guard_s=0.0)
    try:
        normalize_observation_config(config)
    except ValueError as exc:
        assert "pre_guard_s" in str(exc)
    else:
        raise AssertionError("negative pre_guard_s was accepted")


def test_one_kilometre_gate_at_200_megahertz_is_9337_samples():
    """Hand count for the mesh example: 1 km, 40 µs, 200 MHz, stretch 1.

    T_gate = 1000/c = 3.33564095 µs, so T_gate * f_s + 0.5 = 667.628 and n_pre = 668.
    The trailing side is 40 µs + T_gate, times f_s, plus half a sample: 8667.628,
    which ceilings to 8668. The row is 668 + 8668 + 1 = 9337.
    """

    gate_s, n_pre, n_after, fast_count = stationary_chirp_gate(1000.0, 4.0e-5, 2.0e8)
    assert n_pre == 668
    assert n_after == 8668
    assert fast_count == 9337
    assert gate_s == 1000.0 / C
    assert 0.9 < C / (2.0 * 150.0e6) < 1.1
