"""Frozen-input harmonic experiment; never changes production defaults."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import scipy
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.inversion import multi_harmonic_lomb_scargle


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def design_matrix(times, period, harmonics, origin):
    phase = 2*np.pi*(np.asarray(times)-origin)/period
    return np.column_stack([np.ones(len(phase))] +
        [term for h in range(1, harmonics+1) for term in (np.cos(h*phase), np.sin(h*phase))])


def fit_model(times, values, period, harmonics):
    """Fit using training values only; retain training normalization for prediction."""
    times, values = np.asarray(times), np.asarray(values)
    origin = float(times.min())
    mean, scale = float(values.mean()), float(values.std())
    if scale <= 0 or not np.isfinite(scale):
        raise ValueError("实验拟合需要非恒定有限特征")
    x = design_matrix(times, period, harmonics, origin)
    beta, _, rank, _ = np.linalg.lstsq(x, (values-mean)/scale, rcond=None)
    if rank != x.shape[1]:
        raise ValueError("实验周期设计矩阵秩退化")
    return {"origin": origin, "mean": mean, "scale": scale,
            "period_s": float(period), "harmonics": int(harmonics), "beta": beta.tolist()}


def predict(model, times):
    return model["mean"] + model["scale"] * (design_matrix(
        times, model["period_s"], model["harmonics"], model["origin"]) @ model["beta"])


def blocked_folds(run_ids, count=5):
    """Contiguous blocks of chronologically ordered runs, with no split run."""
    ordered_runs = list(dict.fromkeys(np.asarray(run_ids).tolist()))
    for test_runs in np.array_split(ordered_runs, count):
        test = np.isin(run_ids, test_runs)
        train = ~test
        if not train.any() or not test.any():
            raise ValueError("留出块必须同时包含训练和测试观测")
        yield train, test


def blind_fit(times, values, harmonics, config, grid=None):
    estimate = multi_harmonic_lomb_scargle(
        times, values, config["period_min_s"], config["period_max_s"],
        grid or config["period_grid_size"], harmonics=harmonics)
    model = fit_model(times, values, estimate.best_period_s, harmonics)
    amplitudes = np.hypot(np.array(model["beta"])[1::2], np.array(model["beta"])[2::2])
    dominant = int(np.argmax(amplitudes)+1)
    record = {
        "base_period_s": estimate.best_period_s,
        "dominant_harmonic": dominant,
        "dominant_component_period_s": estimate.best_period_s/dominant,
        "harmonic_amplitudes_standardized": amplitudes.tolist(),
        "training_score": estimate.candidates[0].score,
        "candidates": [{"period_s": c.period_s, "score": c.score} for c in estimate.candidates],
        "model": model,
    }
    return record, estimate


def validation_record(times, values, train, test, harmonics, config):
    result, _ = blind_fit(times[train], values[train], harmonics, config)
    error = values[test]-predict(result["model"], times[test])
    baseline_error = values[test]-values[train].mean()
    sse, baseline = float(error@error), float(baseline_error@baseline_error)
    return {**result, "train_count": int(train.sum()), "test_count": int(test.sum()),
            "test_time_span_s": [float(times[test].min()), float(times[test].max())],
            "test_sse": sse, "test_baseline_sse": baseline,
            "test_score": 1-sse/baseline,
            "test_rmse_training_std": float(np.sqrt(np.mean(error**2))/values[train].std())}


def save_figure(fig, output, stem):
    for suffix in ("png", "svg"):
        fig.savefig(output/f"{stem}.{suffix}", dpi=190, bbox_inches="tight")
    plt.close(fig)


def make_figures(output, times, values, names, full, grids, validation, injection, truth_modulation):
    colors = ["#0072B2", "#D55E00", "#009E73"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    for i, name in enumerate(names):
        for h, color in zip((1,2,3), colors):
            p, s = grids[f"{name}:H{h}:G4000"]
            order = np.argsort(p)
            axes[i].plot(p[order], s[order], color=color, label=f"H={h}")
        axes[i].axvline(truth_modulation, color="black", ls="--", lw=1, label="5400 s reference")
        axes[i].axvline(2*truth_modulation, color="gray", ls=":", lw=1)
        axes[i].set(title=name, xlabel="Base period (s)", ylabel="Training regression improvement")
        axes[i].legend(fontsize=8)
    save_figure(fig, output, "periodograms")

    fig, axes = plt.subplots(3, 3, figsize=(13, 9), constrained_layout=True)
    for i, name in enumerate(names):
        standardized = (values[:, i]-values[:, i].mean())/values[:, i].std()
        for j, h in enumerate((1,2,3)):
            rec = full[f"{name}:H{h}:G4000"]
            model = rec["model"]
            phase = ((times-times[0])/rec["base_period_s"]) % 1
            axes[i,j].scatter(phase, standardized, s=3, alpha=.25, color=colors[j], rasterized=True)
            phase_line = np.linspace(0,1,300)
            curve = predict(model, times[0]+phase_line*rec["base_period_s"])
            axes[i,j].plot(phase_line, (curve-values[:,i].mean())/values[:,i].std(), color="black", lw=1.5)
            axes[i,j].set(title=f"{name}, H={h}, base P={rec['base_period_s']:.1f}s",
                          xlabel="Phase of fitted base period", ylabel="Standardized feature")
    save_figure(fig, output, "folded_profiles")

    fig, axes = plt.subplots(1,3,figsize=(14,4), constrained_layout=True)
    for i,name in enumerate(names):
        for h,color in zip((1,2,3),colors):
            records = validation[f"{name}:H{h}"]
            errors = [r["test_rmse_training_std"] for r in records]
            axes[i].scatter(np.full(5,h), errors, color=color, s=28)
            axes[i].plot([h-.2,h+.2],[np.mean(errors)]*2,color=color,lw=2)
        axes[i].set(title=name,xlabel="Harmonic order",ylabel="Held-out RMSE / training std",xticks=[1,2,3])
    save_figure(fig, output, "blocked_validation")

    fig, axes = plt.subplots(2,2,figsize=(11,7), constrained_layout=True)
    for ax, (shape, noise) in zip(axes.ravel(), [(s,n) for s in ("sine","non_sinusoidal") for n in ("white","ar1")]):
        for h,color in zip((1,2,3),colors):
            subset = [r for r in injection if r["shape"]==shape and r["noise"]==noise and r["harmonics"]==h]
            errors = [100*abs(r["dominant_component_period_s"]/truth_modulation-1) for r in subset]
            ax.scatter(np.full(len(errors),h),errors,color=color,s=20,alpha=.6)
        ax.set(title=f"{shape}, {noise} residual",xlabel="Harmonic order",
               ylabel="Dominant-component relative error (%)",xticks=[1,2,3])
    save_figure(fig, output, "injection_recovery")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observables", type=Path, default=ROOT/"runs/paras_for_70m_3h/inversion_batch1_20261011_final/period_observables.npz")
    parser.add_argument("--echo", type=Path, default=ROOT/"runs/paras_for_70m_3h/echo/echo.npz")
    parser.add_argument("--config", type=Path, default=ROOT/"runs/paras_for_70m_3h/configs/inversion.generated.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=12)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("实验输出目录已存在，请指定新目录，避免覆盖")
    if args.repetitions < 2:
        raise ValueError("重复实验至少需要两次")
    started = time.perf_counter()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    # Fixed protocol: this study compares the existing 4000 grid with 8000.
    if config["period_grid_size"] != 4000:
        raise ValueError("本实验协议要求现有配置 period_grid_size=4000")
    with np.load(args.echo) as echo:
        metadata = json.loads(str(echo["metadata_json"].item()))
        if not np.all(echo["valid"]):
            raise ValueError("本实验协议仅接受全有效ADC；缺样需要另行验证权重")
        source_times = echo["scatter_elapsed_s"].copy()
    with np.load(args.observables) as data:
        times, values = data["time_elapsed_s"].copy(), data["value"].copy()
        names = data["feature_names"].tolist()
        run_ids = data["run_id"].copy()
        diag = json.loads(str(data["metadata_json"].item()))["search_diagnostics"]
    if diag["processing_path"] != "pulse_fallback" or diag["aggregation"] != "none":
        raise ValueError("实验必须使用未聚合的完整原生逐脉冲特征")
    if not np.array_equal(times, source_times) or not np.all(np.isfinite(values)):
        raise ValueError("特征时刻必须匹配原始散射时刻，特征必须有限")
    if names != ["total_power", "centroid_delay_s", "energy_width_90_s"]:
        raise ValueError("本实验仅接受三项完整原生逐脉冲特征")
    order = np.argsort(times)
    times, values, run_ids = times[order], values[order], run_ids[order]
    inputs = {str(p):sha256(p) for p in (args.echo,args.observables,args.config)}
    expected_echo = "add62990c10ab7c4d74f5e2e5d50611cd9201d967399b3b2ed26ee195ee6ba3a"
    if inputs[str(args.echo)] != expected_echo:
        raise ValueError("回波与第一批冻结输入不同，本实验协议需重新定义")
    args.output.mkdir(parents=True)
    shutil.copy2(args.observables,args.output/"frozen_observables.npz")
    shutil.copy2(args.config,args.output/"frozen_config.json")
    protocol = {"inputs_sha256":inputs,"sample_count":len(times),"time_span_s":float(np.ptp(times)),
        "harmonics":[1,2,3],"grids":[4000,8000],"blocked_fold_count":5,
        "injection_repetitions":args.repetitions,"injection_noise_std":.2,"ar1_rho":.9,
        "weights":"uniform: source ADC all valid", "selection":"blind best training score; truth evaluation only",
        "truth_modulation_reference_s":float(metadata["truth_period_s"])/2,
        "source_sha256":{str(p.relative_to(ROOT)):sha256(p) for p in
            [Path(__file__),ROOT/"inversion/src/inversion.py",ROOT/"inversion/src/radar_signal.py",ROOT/"inversion/src/dataset.py"]},
        "environment":{"python":sys.version,"numpy":np.__version__,"scipy":scipy.__version__},
        "created_at":datetime.now(timezone(timedelta(hours=8))).isoformat()}
    (args.output/"protocol.json").write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding="utf-8")
    full, grids, validation, stability = {}, {}, {}, {}
    total = 18+45+18+args.repetitions*12
    progress = tqdm(total=total,desc="Harmonic experiment",unit="search")
    for i,name in enumerate(names):
        for h in (1,2,3):
            for grid in (4000,8000):
                key = f"{name}:H{h}:G{grid}"
                rec, est = blind_fit(times,values[:,i],h,config,grid)
                rec["reference_error_s"] = rec["dominant_component_period_s"]-protocol["truth_modulation_reference_s"]
                full[key] = rec
                grids[key] = (est.grid_periods_s, est.grid_scores)
                progress.update()
                print(f"full {key}: base={rec['base_period_s']:.6f}s, dominant={rec['dominant_component_period_s']:.6f}s",flush=True)
            records = []
            for fold,(train,test) in enumerate(blocked_folds(run_ids)):
                records.append({"fold":fold,**validation_record(times,values[:,i],train,test,h,config)})
                progress.update()
            validation[f"{name}:H{h}"] = records
            for label,mask in (("first_half",times <= np.median(times)),("second_half",times > np.median(times))):
                rec,_ = blind_fit(times[mask],values[mask,i],h,config)
                stability[f"{name}:H{h}:{label}"] = rec
                progress.update()
    injection = []
    truth = protocol["truth_modulation_reference_s"]
    phase = 2*np.pi*(times-times[0])/truth
    for shape in ("sine","non_sinusoidal"):
        clean = np.cos(phase)
        if shape == "non_sinusoidal":
            clean = clean+.35*np.cos(2*phase+.3)+.15*np.sin(3*phase-.2)
        for noise_kind in ("white","ar1"):
            for rep in range(args.repetitions):
                rng = np.random.default_rng(20261011+rep)
                noise = rng.normal(size=len(times))
                if noise_kind == "ar1":
                    for k in range(1,len(noise)):
                        noise[k] = .9*noise[k-1]+np.sqrt(1-.9**2)*noise[k]
                injected = clean+.2*noise
                for h in (1,2,3):
                    rec,_ = blind_fit(times,injected,h,config)
                    injection.append({"shape":shape,"noise":noise_kind,"rep":rep,"harmonics":h,
                        "base_period_s":rec["base_period_s"],"dominant_component_period_s":rec["dominant_component_period_s"],
                        "dominant_harmonic":rec["dominant_harmonic"],
                        "base_hit_1pct":abs(rec["base_period_s"]/truth-1) < .01,
                        "dominant_component_hit_1pct":abs(rec["dominant_component_period_s"]/truth-1) < .01})
                    progress.update()
    progress.close()
    aggregates = {}
    for key,records in validation.items():
        aggregates[key] = {"pooled_heldout_score":1-sum(r["test_sse"] for r in records)/sum(r["test_baseline_sse"] for r in records),
            "mean_heldout_rmse_training_std":float(np.mean([r["test_rmse_training_std"] for r in records])),
            "fold_base_periods_s":[r["base_period_s"] for r in records],
            "fold_component_periods_s":[r["dominant_component_period_s"] for r in records]}
    summary = {"protocol":protocol,"full":full,"blocked_validation":validation,
               "validation_aggregates":aggregates,"half_span_stability":stability,"injection":injection}
    summary["input_hashes_unchanged"] = all(sha256(p)==digest for p,digest in inputs.items())
    if not summary["input_hashes_unchanged"]:
        raise RuntimeError("实验期间输入发生变化，结果不可作为冻结对照")
    summary["elapsed_seconds_before_plotting"] = time.perf_counter()-started
    (args.output/"results.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    np.savez_compressed(args.output/"periodograms.npz",**{key.replace(":","_")+suffix:array
        for key,pair in grids.items() for suffix,array in zip(("_periods","_scores"),pair)})
    make_figures(args.output,times,values,names,full,grids,validation,injection,truth)
    print(f"Completed in {time.perf_counter()-started:.2f}s; output={args.output}",flush=True)


if __name__ == "__main__":
    main()
