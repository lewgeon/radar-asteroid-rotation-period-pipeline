"""Distinguishable optional period-search branches and configuration contracts."""
import itertools
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from inversion.src import inversion as core
from inversion.src.dataset import normalize_inversion_policy, load_echo
from inversion.src.period_enhancements import effective_look_phase, method_options
from inversion.tests.test_chirp_contracts import chirp_echo, ChirpInversionTests


def test_all_eight_branches_match_independent_weighted_regression():
    t = np.linspace(0, 43, 100) + .07*np.sin(np.arange(100))
    offset = -.09*t - .12*np.sin(t/9)
    phase = 2*np.pi*t/7.23 + offset
    y = 3 + np.cos(phase+.31) + .42*np.sin(2*phase-.6)
    w = np.linspace(.4, 1.7, len(t))
    periods = []
    grid_curves = {}
    for comp, h, refine in itertools.product((False, True), (1, 2), (False, True)):
        e = core.multi_harmonic_lomb_scargle(t, y, 6, 9, 600, harmonics=h,
            weights=w, phase_offset=offset if comp else None, refine_period=refine)
        baseline = np.sum(w*(y-np.average(y, weights=w))**2)
        expected = []
        for p in e.grid_periods_s:
            a = 2*np.pi*t/p + (offset if comp else 0)
            x = np.column_stack([np.ones(len(t))] +
                [f(n*a) for n in range(1, h+1) for f in (np.cos, np.sin)])
            beta = np.linalg.lstsq(x*np.sqrt(w[:, None]), y*np.sqrt(w), rcond=None)[0]
            expected.append(1-np.sum(w*(y-x@beta)**2)/baseline)
        np.testing.assert_allclose(e.grid_scores, expected, atol=3e-14)
        grid_curves[comp, h] = e.grid_scores
        periods.append(e.best_period_s)
        if not refine:
            assert e.best_period_s in e.grid_periods_s
        if comp and h == 2 and refine:
            assert abs(e.best_period_s-7.23) < 1e-4
    # Guard the fixture: phase/H/refinement interventions really differ.
    assert len(np.unique(np.round(periods, 7))) == 8
    assert np.max(abs(grid_curves[False, 1]-grid_curves[True, 1])) > .1
    assert np.max(abs(grid_curves[True, 1]-grid_curves[True, 2])) > .05


def test_geometry_sort_wrap_multiplier_and_explicit_axis():
    t = np.array([3., 0., 2., 1.])
    a = np.pi-.2 + .15*t
    v = np.column_stack([np.cos(a), np.sin(a), np.zeros(4)])
    echo = SimpleNamespace(scatter_elapsed_s=t, tx_los_icrs=v, rx_los_icrs=v)
    cfg = dict(spin_axis_ra_deg=0, spin_axis_dec_deg=90, phase_period_convention="half_rotation")
    q = np.array([.5, 1.5, 2.5])
    np.testing.assert_allclose(effective_look_phase(echo, q, cfg), -.3*q, atol=1e-14)
    cfg["phase_period_convention"] = "full_rotation"
    np.testing.assert_allclose(effective_look_phase(echo, q, cfg), -.15*q, atol=1e-14)
    with pytest.raises(ValueError, match="禁止外推"):
        effective_look_phase(echo, [4], cfg)
    echo.rx_los_icrs = -v
    with pytest.raises(ValueError, match="经度未定义"):
        effective_look_phase(echo, q, cfg)


def test_explicit_refinement_keeps_boundary_candidates_and_cannot_reduce_score():
    t = np.linspace(0, 43, 100)
    y = np.cos(2*np.pi*t/20)
    grid = core.multi_harmonic_lomb_scargle(t, y, 6, 9, 80, refine_period=False)
    refined = core.multi_harmonic_lomb_scargle(t, y, 6, 9, 80, refine_period=True)
    legacy = core.multi_harmonic_lomb_scargle(t, y, 6, 9, 80)
    assert grid.best_period_s == refined.best_period_s == 9
    assert refined.candidates[0].score >= grid.candidates[0].score
    assert legacy.search_diagnostics["candidate_policy"] == "legacy_interior_peaks"
    assert abs(legacy.best_period_s-7.7863838) < 1e-6
    assert abs(legacy.best_period_s-grid.best_period_s) > 1


@pytest.mark.parametrize("update", [dict(los_phase_compensation="false"),
    dict(compare_methods=1), dict(refine_period=None), dict(multi_harmonic_enabled=0),
    dict(los_phase_compensation=True), dict(compare_methods=True, harmonics=1),
    dict(los_phase_compensation=True, spin_axis_ra_deg=True, spin_axis_dec_deg=0),
    dict(los_phase_compensation=True, spin_axis_ra_deg=0, spin_axis_dec_deg=91),
    dict(los_phase_compensation=True, spin_axis_ra_deg=0, spin_axis_dec_deg=0,
         phase_period_convention="guess"),
    dict(los_phase_compensation=True, spin_axis_ra_deg=0, spin_axis_dec_deg=0,
         period_time_role="receive_centroid")])
def test_invalid_config_is_rejected(update):
    with pytest.raises(ValueError):
        normalize_inversion_policy({"cpi_duration_s": 1, **update}, "chirp")


def test_disabled_children_do_not_affect_results_and_legacy_options():
    cfg = {"cpi_duration_s": 1, "multi_harmonic_enabled": False,
           "harmonics": 3, "los_phase_compensation": False,
           "spin_axis_ra_deg": None, "spin_axis_dec_deg": None}
    cfg = normalize_inversion_policy(cfg, "chirp")
    assert method_options(cfg) == dict(los_phase_compensation=False, harmonics=1, refine_period=True)
    assert method_options({"harmonics": 3})["harmonics"] == 3
    assert method_options({"multi_harmonic_enabled": False, "harmonics": None})["harmonics"] == 1
    assert method_options({"multi_harmonic_enabled": False, "harmonics": "draft"})["harmonics"] == 1
    with pytest.raises(ValueError, match="不接受"):
        normalize_inversion_policy({"refine_period": False}, "cw")


@pytest.mark.parametrize("cpi", [.8, 20])
def test_real_cpi_and_pulse_routing_comparison(cpi):
    echo = chirp_echo("centroid_compensated")
    t = echo.scatter_elapsed_s
    v = np.column_stack([np.cos(.06*t), np.sin(.06*t), np.zeros(len(t))])
    echo.tx_los_icrs = v
    echo.rx_los_icrs = v.copy()
    echo.run_id = np.repeat(np.arange(10), 8) if cpi < 1 else np.arange(80)
    echo.coherence_id = echo.run_id.copy()
    cfg = {**ChirpInversionTests.config, "cpi_duration_s": cpi, "cpi_hop_duration_s": cpi,
           "harmonics": 2, "multi_harmonic_enabled": False, "compare_methods": True,
           "spin_axis_ra_deg": 0, "spin_axis_dec_deg": 90}
    # CPI needs enough frames for H2: shorten the blocks for 20 frames.
    if cpi < 1:
        cfg["cpi_duration_s"] = .4
        cfg["cpi_hop_duration_s"] = .4
    with patch.object(core, "multi_harmonic_lomb_scargle", wraps=core.multi_harmonic_lomb_scargle) as search:
        result = core.estimate_rotation(echo, cfg)
    assert result.search_diagnostics["processing_path"] == ("cpi" if cpi < 1 else "pulse_fallback")
    assert len(result.method_comparisons) == 8
    assert any(call.kwargs["phase_offset"] is not None for call in search.call_args_list)
    assert any(call.kwargs["refine_period"] is False for call in search.call_args_list)
    for record in result.method_comparisons.values():
        assert record["features"]["total_power"]["status"] == "searched"


def test_frozen_legacy_and_phase_correction_golden():
    from pathlib import Path
    path = Path("runs/paras_for_70m_3h/echo/echo.npz")
    if not path.exists():
        pytest.skip("optional frozen experiment input unavailable")
    echo = load_echo(path)
    f = core.chirp_pulse_range_features(echo, {"motion_compensation": "auto"})[0]
    baseline = core.multi_harmonic_lomb_scargle(f.times_s, f.centroid_delay_s, 1800, 14400, 4000)
    assert abs(baseline.best_period_s-5404.493479588764) < 1e-8
    cfg = dict(spin_axis_ra_deg=105, spin_axis_dec_deg=-66)
    offset = effective_look_phase(echo, f.times_s, cfg)
    corrected = core.multi_harmonic_lomb_scargle(f.times_s, f.centroid_delay_s, 1800, 14400, 4000,
                                               phase_offset=offset)
    assert abs(corrected.best_period_s-5401.5967670188475) < 1e-6


def test_comparison_report_replaces_stale_results_when_disabled(tmp_path):
    import json
    from inversion.src.method_report import write_method_comparison
    records = {"one": {"options": {"los_phase_compensation": True, "harmonics": 2, "refine_period": False},
               "features": {"power<": {"status": "searched", "best_period_s": 7.23, "score": .9}}}}
    write_method_comparison(tmp_path, records)
    assert json.loads((tmp_path/"method_comparison.json").read_text(encoding="utf-8"))["enabled"]
    assert "power&lt;" in (tmp_path/"method_comparison.html").read_text(encoding="utf-8")
    write_method_comparison(tmp_path, {})
    result = json.loads((tmp_path/"method_comparison.json").read_text(encoding="utf-8"))
    assert result["methods"] == {} and not result["enabled"]
    assert "7.23" not in (tmp_path/"method_comparison.html").read_text(encoding="utf-8")
