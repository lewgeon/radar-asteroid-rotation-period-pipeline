"""Paired consensus regression study; truth is used only by the fixed scorer."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import experiment_period_uncertainty as controls
from inversion.src import period_uncertainty
from inversion.src.period_consensus import _cross_feature_consensus, CONSENSUS_POLICY

# Frozen pre-fix implementation. SHA256 below identifies the complete pre-fix
# inversion/src/period_consensus.py file (including module docstring/import),
# saved before this repair, not the extracted function text or Git HEAD file:
# 635f4b74b1dbfea25954a495c54331ae2b325d1bcff79058c882e6b879577d35

import numpy as np


def legacy_consensus(feature_summary, relative_tolerance=0.05):
    """Select a period supported by distinct observables, not one tallest peak.

    Multi-harmonic fits naturally admit integer-multiple fundamentals.  Clusters
    are therefore ranked first by independent feature support and then by their
    relative spread.  Half/double aliases appended for reporting are excluded
    from the vote so they cannot count twice for the same measured peak.
    """

    entries = []
    for feature, item in feature_summary.items():
        for rank, candidate in enumerate(item["candidates"][:5]):
            if candidate["source"].endswith((":half", ":double")):
                continue
            entries.append(
                {
                    "feature": feature,
                    "period_s": float(candidate["period_s"]),
                    "score": float(candidate["score"]),
                    "rank": rank,
                }
            )
    clusters = []
    for entry in sorted(entries, key=lambda item: item["period_s"]):
        compatible = [
            cluster for cluster in clusters
            if abs(entry["period_s"] / cluster["center_s"] - 1.0) <= relative_tolerance
        ]
        if compatible:
            cluster = min(
                compatible,
                key=lambda item: abs(np.log(entry["period_s"] / item["center_s"])),
            )
            cluster["entries"].append(entry)
            cluster["center_s"] = float(np.median([x["period_s"] for x in cluster["entries"]]))
        else:
            clusters.append({"center_s": entry["period_s"], "entries": [entry]})
    ranked = []
    for cluster in clusters:
        by_feature = {}
        for entry in cluster["entries"]:
            current = by_feature.get(entry["feature"])
            if current is None or entry["rank"] < current["rank"]:
                by_feature[entry["feature"]] = entry
        evidence = list(by_feature.values())
        center = float(np.median([item["period_s"] for item in evidence]))
        spread = float(
            np.median([abs(item["period_s"] / center - 1.0) for item in evidence])
        )
        ranked.append((len(evidence), spread, center, evidence))
    if not ranked:
        raise ValueError("没有可用于跨特征共识的周期候选")
    support, spread, period_s, evidence = sorted(
        ranked, key=lambda item: (-item[0], item[1], item[2])
    )[0]
    return period_s, support, spread, evidence




def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=200)
    parser.add_argument("--receiver-trials", type=int, default=32)
    args = parser.parse_args()
    if not 0 <= args.receiver_trials <= args.trials or args.trials < 1:
        parser.error("require 0 <= receiver-trials <= trials and trials >= 1")
    args.output.mkdir(parents=True, exist_ok=False)
    results = {}
    for label, function in (("before", legacy_consensus), ("after", _cross_feature_consensus)):
        print(label, flush=True)
        with patch.object(controls, "_cross_feature_consensus", function), patch.object(period_uncertainty, "_cross_feature_consensus", function):
            results[label] = controls.coverage(SimpleNamespace(trials=args.trials, receiver_trials=args.receiver_trials))
        (args.output / (label + ".json")).write_text(json.dumps(results[label], ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    results["policy"] = CONSENSUS_POLICY
    results["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        Path(__file__), ROOT/"scripts/experiment_period_uncertainty.py",
        ROOT/"inversion/src/period_consensus.py", ROOT/"inversion/src/period_uncertainty.py")}
    (args.output / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: results[k]["summary"] for k in ("before", "after")}, indent=2), flush=True)


if __name__ == "__main__":
    main()

