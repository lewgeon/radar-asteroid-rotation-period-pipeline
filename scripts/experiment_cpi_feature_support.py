"""Pair frozen cropped CPI moments with full-support production moments.

This CPU-only diagnostic compares the two representations on identical IQ and
windows. It never uses a known rotation period to select a feature or model.
The original 2026-10-16 measurement used the temporary probe documented in
docs/4.3/vs_4.2/experiments/reports/2026-10-09_SIGNAL_FORMATION_AND_INTEGRATION_COST.md;
this CLI preserves its formulas.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.dataset import load_echo, normalize_inversion_policy
from inversion.src.inversion import (
    _echo_pulse_chunk, _global_delay_grid, multi_harmonic_lomb_scargle,
    prepare_chirp_pulse_profiles,
)
from inversion.src.radar_signal import (
    align_profiles_to_common_delay, centroid_delay_axes,
    chirp_reference_sample_count, range_doppler_cube, range_doppler_features,
)

NAMES = ('total_power', 'doppler_centroid', 'doppler_bandwidth',
         'range_centroid', 'range_energy_width')
ALIASES = dict(total_power='total_power', doppler_centroid_hz='doppler_centroid',
               rms_bandwidth_hz='doppler_bandwidth', range_centroid_s='range_centroid',
               energy_range_width_90_s='range_energy_width')


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def identity(path):
    path = Path(path).resolve()
    stat = path.stat()
    return dict(path=str(path), size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def load_snapshot(path):
    with np.load(path, allow_pickle=False) as data:
        saved = {key: data[key].copy() for key in ('time_elapsed_s', 'run_id',
            'coherence_id', 'effective_sample_count', 'feature_names', 'value')}
        saved['reference_time_utc'] = data['reference_time_utc'].copy()
        metadata = json.loads(str(data['metadata_json'].item()))
    names = [ALIASES.get(str(name), str(name)) for name in saved['feature_names']]
    if set(names) != set(NAMES) or len(names) != len(NAMES):
        raise ValueError('observables 必须包含五项 CPI 特征；逐脉冲结果不适用此实验')
    saved['value'] = saved['value'][:, [names.index(name) for name in NAMES]]
    return saved, metadata


def windows(echo, count, hop):
    valid = np.asarray(echo.valid, bool)
    pulse_valid = valid if valid.ndim == 1 else np.any(valid, axis=1)
    runs = np.asarray(echo.run_id)
    groups = np.asarray(echo.coherence_id)
    output = []
    for run, group in np.unique(np.column_stack((runs, groups)), axis=0):
        selected = np.flatnonzero((runs == run) & (groups == group) & pulse_valid)
        for block in np.split(selected, np.flatnonzero(np.diff(selected) != 1) + 1):
            for start in range(0, len(block) - count + 1, hop):
                first = int(block[start])
                output.append((first, first + count, int(run)))
    return output


def extract(echo, config):
    fast = echo.fast_time_s
    prf = float(echo.metadata.get('prf_hz', 0.))
    if not np.isfinite(prf) or prf <= 0:
        raise ValueError('实验需要正且有限的 prf_hz')
    count = max(2, int(np.ceil(config['cpi_duration_s'] * prf)))
    duration = config.get('cpi_hop_duration_s')
    duration = config['cpi_duration_s'] / 4 if duration is None else duration
    hop = max(1, int(np.ceil(duration * prf)))
    selections = windows(echo, count, hop)
    if not selections:
        raise ValueError('配置无法形成 CPI；请核对保存特征使用的配置，而非更改窗口迎合真值')
    offsets = centroid_delay_axes(np.array([0.]), len(echo.iq),
        row_fast_time_offset_s=echo.row_fast_time_offset_s,
        centroid_fractional_offset_s=echo.centroid_fractional_offset_s)[:, 0]
    grid = _global_delay_grid(fast, offsets)
    step = float(np.median(np.diff(fast)))
    reference = chirp_reference_sample_count(echo.metadata['pulse_width_s'], step)
    full_count = len(fast) + reference - 1
    if count * full_count * 16 * 6 > 512 * 1024 * 1024:
        raise ValueError('单 CPI 工作数组估算超过 512 MiB；本实验不静默缩短 CPI')
    full_fast = fast[0] + (np.arange(full_count) - reference + 1) * step
    energy_grid = _global_delay_grid(full_fast, offsets, preserve_support=True)
    parts = {name: [] for name in ('time_elapsed_s', 'run_id', 'coherence_id',
        'effective_sample_count', 'old_value', 'value', 'range_rms_width_s',
        'doppler_window_rms_hz', 'doppler_nyquist_edge_fraction',
        'doppler_nyquist_edge_half_width_hz')}
    started = time.perf_counter()
    for number, (begin, end, run) in enumerate(selections):
        chunk = _echo_pulse_chunk(echo, begin, end, len(echo.iq))
        native = prepare_chirp_pulse_profiles(chunk, config, pulse_features_only=True)
        cropped = native['full_compressed'][:, reference - 1:reference - 1 + len(fast)]
        axes = centroid_delay_axes(fast, len(chunk.iq),
            row_fast_time_offset_s=chunk.row_fast_time_offset_s,
            centroid_fractional_offset_s=chunk.centroid_fractional_offset_s)
        _, aligned = align_profiles_to_common_delay(cropped, axes, valid=chunk.valid,
            common_grid=grid, method='fourier')
        _, energy = align_profiles_to_common_delay(native['full_compressed'],
            native['full_delay_axes'], preserve_support=True, common_grid=energy_grid,
            method='fourier')
        valid = np.asarray(chunk.valid, bool)
        weight = valid.astype(float) if valid.ndim == 1 else valid.mean(axis=1)
        cube = range_doppler_cube(aligned, native['processing_times'], chunk.coherence_id,
            grid[0], cpi_pulses=count, cpi_hop_pulses=hop, valid=valid,
            run_id=chunk.run_id, effective_pulse_weight=weight,
            energy_iq=energy, energy_delay_axis_s=energy_grid[0],
            doppler_estimator='spectral_moments')
        feature = range_doppler_features(cube)
        new = np.column_stack((feature.total_power, feature.doppler_centroid_hz,
            feature.rms_bandwidth_hz, feature.range_centroid_s, feature.energy_range_width_90_s))
        # Frozen pre-upgrade formulas: power/centroid use the cropped RD view;
        # the 90% width already used full support. All other processing is paired.
        old = new.copy()
        rd = cube.power
        old[:, 0] = rd.sum(axis=(1, 2))
        old[:, 3] = np.sum(rd.sum(axis=2) * cube.delays_s[None, :], axis=1) / np.maximum(old[:, 0], np.finfo(float).tiny)
        variance = np.sum(cube.energy_range_power *
            (cube.energy_delays_s[None, :] - feature.range_centroid_s[:, None]) ** 2,
            axis=1) / np.maximum(feature.total_power, np.finfo(float).tiny)
        rms = np.where(feature.total_power > 0, np.sqrt(np.maximum(variance, 0)), np.nan)
        values = dict(time_elapsed_s=feature.times_s, run_id=np.full(len(new), run),
            coherence_id=feature.coherence_id, effective_sample_count=feature.effective_sample_count,
            old_value=old, value=new, range_rms_width_s=rms,
            doppler_window_rms_hz=feature.doppler_window_rms_hz,
            doppler_nyquist_edge_fraction=feature.doppler_nyquist_edge_fraction,
            doppler_nyquist_edge_half_width_hz=feature.doppler_nyquist_edge_half_width_hz)
        for key, value in values.items():
            parts[key].append(value)
        if number % 25 == 0 or number == len(selections) - 1:
            print(f'CPI {number + 1}/{len(selections)}，已用 {time.perf_counter() - started:.1f} s', flush=True)
        del native, cropped, aligned, energy, cube, feature, rd
    return {key: np.concatenate(value) for key, value in parts.items()}


def finite_range(values):
    finite = np.asarray(values)[np.isfinite(values)]
    return [float(finite.min()), float(finite.max())] if len(finite) else [None, None]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--echo', type=Path, required=True, help='输入 Chirp echo.npz')
    parser.add_argument('--observables', type=Path, required=True, help='升级前的五特征 period_observables.npz')
    parser.add_argument('--config', '--job', dest='config', type=Path,
        help='可选完整作业 JSON 或 inversion JSON；缺省读取 observables 中冻结的 inversion_config')
    parser.add_argument('--output', type=Path, required=True, help='必须尚不存在的输出目录；不覆盖历史证据')
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f'输出目录已存在，拒绝覆盖：{args.output}')
    saved, metadata = load_snapshot(args.observables)
    raw_config = (json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config
                  else metadata['inversion_config'])
    config = normalize_inversion_policy(raw_config.get('inversion', raw_config), 'chirp')
    if config.get('doppler_estimator', 'spectral_moments') != 'spectral_moments':
        parser.error('冻结基线是 FFT 谱矩；本实验要求 doppler_estimator=spectral_moments')
    if config.get('compute_device', 'cpu') != 'cpu':
        parser.error('此配对复现协议限定 CPU；请使用显式 CPU 配置')
    if config.get('los_phase_compensation', False):
        parser.error('本实验的 H1 基线不含视线相位补偿，请提供未补偿配置与对应快照')
    source_before, snapshot_before = identity(args.echo), identity(args.observables)
    code_paths = (Path(__file__), ROOT / 'inversion/src/radar_signal.py',
                  ROOT / 'inversion/src/inversion.py', ROOT / 'inversion/src/compute_backend.py')
    code_before = {str(path.relative_to(ROOT)): digest(path) for path in code_paths}
    summary = dict(measured_utc=datetime.now(timezone.utc).isoformat(),
        source=source_before, source_sha256=digest(args.echo),
        snapshot=snapshot_before, snapshot_sha256=digest(args.observables),
        source_hashes_at_start=code_before, config=config,
        baseline='frozen_cropped_RD_total_and_centroid_full_support_90_percent_width',
        new_branch='production_full_support_range_statistics',
        period_model='shared_intercept_H1_no_truth_selection')
    args.output.mkdir(parents=True, exist_ok=False)
    echo = load_echo(args.echo, mapped_directory=args.output / 'mapped', load_clean=False)
    try:
        started = time.perf_counter()
        result = extract(echo, config)
        summary['extraction_elapsed_s'] = time.perf_counter() - started
    finally:
        echo.close()
    result.update(feature_names=np.array(NAMES), reference_time_utc=saved['reference_time_utc'])
    same_axes = all(np.array_equal(result[key], saved[key]) for key in
                    ('time_elapsed_s', 'run_id', 'coherence_id', 'effective_sample_count'))
    same_shape = result['old_value'].shape == saved['value'].shape
    summary['snapshot_axes_match'] = same_axes
    summary['snapshot_values_match'] = False
    if same_axes and same_shape:
        difference = abs(result['old_value'] - saved['value'])
        maximum = np.max(np.where(np.isfinite(difference), difference, 0.), axis=0)
        summary['snapshot_max_abs_delta'] = dict(zip(NAMES, maximum.tolist()))
        summary['snapshot_values_match'] = bool(np.allclose(
            result['old_value'], saved['value'], rtol=1e-9, atol=1e-14, equal_nan=True))
    nonzero = result['old_value'][:, 0] > 0
    summary['full_vs_cropped_fractional_power_change_minmax'] = finite_range(
        result['value'][nonzero, 0] / result['old_value'][nonzero, 0] - 1)
    summary['full_vs_cropped_centroid_change_s_minmax'] = finite_range(result['value'][:, 3] - result['old_value'][:, 3])
    summary['window_rms_hz_minmax'] = finite_range(result['doppler_window_rms_hz'])
    summary['nyquist_edge_fraction_minmax'] = finite_range(result['doppler_nyquist_edge_fraction'])
    summary['H1_periods'] = {}
    summary['unavailable_searches'] = {}
    def search(values, label):
        try:
            return multi_harmonic_lomb_scargle(result['time_elapsed_s'], values,
                config['period_min_s'], config['period_max_s'], config['period_grid_size'],
                harmonics=1, weights=result['effective_sample_count'], refine_period=True).best_period_s
        except ValueError as error:
            summary['unavailable_searches'][label] = str(error)
            return None
    for column, name in enumerate(NAMES):
        summary['H1_periods'][name] = {branch: search(result[branch][:, column], f'{branch}/{name}')
                                      for branch in ('old_value', 'value')}
    summary['range_rms_H1_period_s'] = search(result['range_rms_width_s'], 'range_rms')
    code_after = {str(path.relative_to(ROOT)): digest(path) for path in code_paths}
    summary['source_hashes_at_end'] = code_after
    summary['inputs_unchanged'] = source_before == identity(args.echo) and snapshot_before == identity(args.observables)
    summary['source_unchanged'] = code_before == code_after
    summary['validation_passed'] = (summary['snapshot_values_match']
        and summary['inputs_unchanged'] and summary['source_unchanged'])
    result['metadata_json'] = np.array(json.dumps(summary, ensure_ascii=False))
    np.savez(args.output / 'feature_pairing.npz', **result)
    (args.output / 'feature_pairing.json').write_text(json.dumps(summary,
        indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))
    if not summary['validation_passed']:
        raise SystemExit('配对检查未通过；已保存诊断产物，请检查快照配置、输入和源码身份。')


if __name__ == '__main__':
    main()
