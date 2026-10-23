"""Rebuild the educational figures for docs/4.3/CHIRP_INVERSION_WALKTHROUGH.md.

Run in the conda pytorch environment. This leaves production code/data untouched.
"""
from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from echo.src.echo import _chirp_motion_terms, _chirp_propagation, _chirp_complex_terms
from inversion.src.inversion import _compensate_raw_centroid_iq, multi_harmonic_lomb_scargle
from inversion.src.radar_signal import matched_filter_chirp, range_features, range_doppler_cube, range_doppler_features
from observation.src.planning import adc_row_sample_counts

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=ROOT / "tmp/chirp_walkthrough")
OUT = parser.parse_args().output
OUT.mkdir(parents=True, exist_ok=True)
C = 299_792_458.0
FC, FS, B, T = 1e9, 20e6, 1e6, 100e-6
FAST = np.arange(2600) / FS
DT = FAST - 10e-6
RHO = C + C / FC * 0.137
V = 3000.0
metrics = {"parameters": {"carrier_hz": FC, "adc_hz": FS, "bandwidth_hz": B, "width_s": T, "common_path_rate_m_s": V}}


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / (name + ".png"), dpi=180)
    fig.savefig(OUT / (name + ".svg"))
    plt.close(fig)


def pulse(reference, motion, rotation=True):
    ctx = SimpleNamespace(output_reference=reference, motion_model=motion,
        scatter_elapsed_s=np.array([0.5]), scatter_rate=np.array([1.0]),
        common_path=np.array([RHO]), path_rate=np.array([V]),
        width=T, slope=B/T, convention="centered", carrier=FC)
    dt = torch.as_tensor(DT, dtype=torch.float64)
    pose, common = _chirp_motion_terms(ctx, 0, dt)
    relative = 30.0 * torch.cos(np.pi * pose) if rotation else torch.zeros_like(dt)
    local, path = _chirp_propagation(dt, relative, common, RHO, ctx)
    return _chirp_complex_terms(local, path, ctx, torch.complex128).numpy()


def compress(samples):
    return matched_filter_chirp(samples[None], FAST, T, B)[0]


# Point target: common motion alone. Call the production compensator.
raw = pulse("raw_baseband", "per_pulse_linear", rotation=False)
ideal = pulse("centroid_compensated", "per_pulse_linear", rotation=False)
echo = SimpleNamespace(fast_time_s=FAST, row_fast_time_offset_s=np.array([-10e-6]),
    common_path_rate_m_s=np.array([V]), tx_range_m=np.array([RHO/2]),
    rx_range_m=np.array([RHO/2]), metadata={"carrier_frequency_hz": FC})
corrected = _compensate_raw_centroid_iq(raw[None], echo, np.ones((1, len(raw)), bool))[0]
rr, rc, ri = [compress(x) for x in (raw, corrected, ideal)]
metrics["point_target"] = {
    "raw_peak_delay_us": float(DT[np.argmax(abs(rr))] * 1e6),
    "corrected_peak_delay_us": float(DT[np.argmax(abs(rc))] * 1e6),
    "ideal_peak_delay_us": float(DT[np.argmax(abs(ri))] * 1e6),
    "raw_peak_relative_to_ideal": float(abs(rr).max()/abs(ri).max()),
    "corrected_peak_relative_to_ideal": float(abs(rc).max()/abs(ri).max()),
    "corrected_relative_l2": float(np.linalg.norm(corrected-ideal)/np.linalg.norm(ideal)),
    "common_doppler_hz": -FC*V/C,
    "approx_delay_bias_us": FC*V/C/(B/T)*1e6,
}
assert abs(metrics["point_target"]["raw_peak_delay_us"]) > 0.5
assert abs(metrics["point_target"]["raw_peak_delay_us"] - metrics["point_target"]["approx_delay_bias_us"]) < 1e6/FS
assert abs(metrics["point_target"]["corrected_peak_delay_us"]) <= 0.05
fig, axes = plt.subplots(3, 1, figsize=(10, 10))
for data, label in [(raw, "Raw"), (corrected, "Geometry compensated"), (ideal, "Ideal centroid reference")]:
    axes[0].plot(DT*1e6, abs(data), label=label)
    inside = (DT >= 10e-6) & (DT <= 90e-6)
    # Difference against the ideal phase, rather than the rapidly varying chirp phase.
    axes[1].plot(DT[inside]*1e6, np.unwrap(np.angle(data[inside]*ideal[inside].conj())), label=label)
for data, label in [(rr, "Raw: no compensation"), (rc, "Raw: geometry compensation"), (ri, "Ideal centroid reference")]:
    axes[2].plot(DT*1e6, abs(data)**2/abs(ri).max()**2, label=label)
axes[0].set(ylabel="Envelope magnitude", title="Point-target example: amplitude alone hides the common phase")
axes[1].set(ylabel="Phase relative to ideal (rad)")
axes[2].set(xlabel="Delay relative to nominal leading edge (us)", ylabel="Compressed power / ideal peak", xlim=(-3, 4))
for ax in axes: ax.legend(); ax.grid(alpha=.25)
save(fig, "01_compensation")

# All four model cells share the same rotating scatterer.
cells = {(ref, mot): pulse(ref, mot) for ref in ("raw_baseband", "centroid_compensated") for mot in ("frozen", "per_pulse_linear")}
pairwise = {}
keys = list(cells)
for n, key in enumerate(keys):
    for other in keys[n+1:]:
        diff = float(np.linalg.norm(cells[key]-cells[other])/np.linalg.norm(cells[other]))
        pairwise["/".join(key)+" vs "+"/".join(other)] = diff
        assert diff > 1e-5, (key, other, diff)
metrics["four_models_relative_l2"] = pairwise
fig, axes = plt.subplots(2, 2, figsize=(11, 7))
for ax, ref in zip(axes, ("raw_baseband", "centroid_compensated")):
    frozen = cells[(ref, "frozen")]
    linear = cells[(ref, "per_pulse_linear")]
    inside = (DT >= 5e-6) & (DT <= 95e-6)
    ax[0].plot(DT[inside]*1e6, np.unwrap(np.angle(linear[inside]*frozen[inside].conj())))
    ax[0].set(title=ref, xlabel="Fast time (us)", ylabel="Linear - frozen phase (rad)")
    for data, name in [(frozen, "Frozen"), (linear, "Per-pulse linear")]:
        comp = compress(data)
        ax[1].plot(DT*1e6, abs(comp)**2/abs(ri).max()**2, label=name)
    ax[1].set(xlim=(-3, 4), xlabel="Delay (us)", ylabel="Compressed power / point ideal peak")
    ax[1].legend()
for ax in axes.flat: ax.grid(alpha=.25)
save(fig, "02_intrapulse")

# Exact same ADC rounding as planning; avoid tie-to-even by choosing non-half values.
dt_ns = 5.0
n_pre, _, _ = adc_row_sample_counts(9e-9, T, 1/(dt_ns*1e-9))
receive_ns = np.array([100., 131.2, 159.1])
adc_on_ns = receive_ns[0] - n_pre*dt_ns
centroid_index = np.rint((receive_ns-adc_on_ns)/dt_ns).astype(int)
row_index = centroid_index - n_pre
row_time_ns = adc_on_ns + row_index*dt_ns
offset_ns = row_time_ns - receive_ns
fraction_ns = receive_ns - (adc_on_ns+centroid_index*dt_ns)
assert np.allclose(offset_ns, -n_pre*dt_ns-fraction_ns)
assert np.ptp(offset_ns) > 1
metrics["adc_example"] = {"n_pre": n_pre, "adc_on_ns": adc_on_ns,
    "receive_ns": receive_ns.tolist(), "centroid_index": centroid_index.tolist(),
    "row_start_index": row_index.tolist(), "row_start_ns": row_time_ns.tolist(),
    "offset_ns": offset_ns.tolist(), "fraction_ns": fraction_ns.tolist()}

# Actual finite complex signal -> compressed rows -> CPI -> moments -> period search.
# The periodic amplitude is imposed, not inferred from an ellipsoid scattering model.
PRF, PERIOD, N = 200., 2., 1600
times = np.arange(N)/PRF
amp = 1.0 + .3*np.cos(2*np.pi*times/PERIOD)
sequence = amp[:, None] * ideal[None, :]
compressed = matched_filter_chirp(sequence, FAST, T, B)
features = range_features(times, DT, compressed, delay_axes_s=DT)
cube = range_doppler_cube(compressed, times, np.zeros(N, int), DT,
    cpi_pulses=64, cpi_hop_pulses=16, run_id=np.zeros(N, int))
rd = range_doppler_features(cube)
estimate = multi_harmonic_lomb_scargle(times, features.total_power, 1., 3., 600, harmonics=2)
assert abs(estimate.best_period_s-PERIOD) < .002
metrics["teaching_sequence"] = {"period_s": PERIOD, "prf_hz": PRF, "pulses": N,
    "estimated_period_s": estimate.best_period_s, "range_centroid_s": float(features.centroid_delay_s[0]),
    "range_width_s": float(features.energy_width_90_s[0]), "cpi_doppler_centroid_hz": float(rd.doppler_centroid_hz[0]),
    "cpi_rms_bandwidth_hz": float(rd.rms_bandwidth_hz[0])}
first = abs(compressed[0])**2
indices = np.argsort(first)[-5:][::-1]
metrics["first_profile_top5"] = [{"delay_us": float(DT[i]*1e6), "power": float(first[i])} for i in indices]
frame_power = cube.power[0]
fd = cube.frame_frequencies_hz[0]
marginal = frame_power.sum(axis=0)
idx = np.argsort(marginal)[-5:][::-1]
metrics["first_cpi_top5"] = [{"frequency_hz": float(fd[i]), "power": float(marginal[i])} for i in idx]
rng = np.random.default_rng(20261009)
noise = (rng.normal(size=sequence.shape)+1j*rng.normal(size=sequence.shape))
noise *= np.sqrt(np.mean(abs(sequence)**2)/2) # 0 dB over the full saved row.
noisy_compressed = matched_filter_chirp(sequence+noise, FAST, T, B)
noisy_f = range_features(times, DT, noisy_compressed, delay_axes_s=DT)
noisy_cube = range_doppler_cube(noisy_compressed, times, np.zeros(N, int), DT,
    cpi_pulses=64, cpi_hop_pulses=16, run_id=np.zeros(N, int))
noisy_rd = range_doppler_features(noisy_cube)
metrics["noise_0db_full_row"] = {"seed": 20261009,
    "clean_median_range_width_us": float(np.median(features.energy_width_90_s)*1e6),
    "noisy_median_range_width_us": float(np.median(noisy_f.energy_width_90_s)*1e6),
    "clean_median_doppler_width_hz": float(np.median(rd.rms_bandwidth_hz)),
    "noisy_median_doppler_width_hz": float(np.median(noisy_rd.rms_bandwidth_hz))}
# Check estimability without assuming a monotonic noise-induced width bias.
assert np.all(np.isfinite(features.energy_width_90_s))
assert np.all(np.isfinite(noisy_f.energy_width_90_s))
assert metrics["noise_0db_full_row"]["noisy_median_doppler_width_hz"] > metrics["noise_0db_full_row"]["clean_median_doppler_width_hz"]
fig, axes = plt.subplots(2, 2, figsize=(11, 7))
axes[0,0].plot(DT*1e6, abs(compressed[0])**2, label="Clean")
axes[0,0].plot(DT*1e6, abs(noisy_compressed[0])**2, alpha=.6, label="Noisy")
axes[0,0].set(xlim=(-5, 8), xlabel="Delay (us)", ylabel="Compressed power", title="First pulse")
axes[0,1].plot(times, features.total_power/features.total_power.mean())
axes[0,1].set(xlabel="Time (s)", ylabel="Normalized total power", title="Known 2 s amplitude modulation")
for rd_item, cube_item, label in [(rd,cube,"Clean"),(noisy_rd,noisy_cube,"Noisy")]:
    marginal = cube_item.power[0].sum(axis=0)
    axes[1,0].plot(cube_item.frame_frequencies_hz[0], marginal/marginal.max(), label=label)
axes[1,0].set(xlabel="Frequency (Hz)", ylabel="Normalized Doppler power", title="First 64-pulse CPI")
axes[1,1].plot(times, features.energy_width_90_s*1e6, label="Clean")
axes[1,1].plot(times, noisy_f.energy_width_90_s*1e6, alpha=.5, label="Noisy")
axes[1,1].set(xlabel="Time (s)", ylabel="Central 90% energy width (us)", title="Energy width with noise")
for ax in axes.flat: ax.grid(alpha=.25)
for ax in (axes[0,0],axes[1,0],axes[1,1]): ax.legend()
save(fig, "03_features_noise")
metrics["definitions"] = {"total_power": "unnormalized sum after processing, not joules",
    "period_example": "known amplitude modulation, one group, H=2; not mesh physics validation"}
(OUT/"metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(metrics, ensure_ascii=False, indent=2))
