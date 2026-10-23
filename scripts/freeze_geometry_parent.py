"""Freeze parent geometry-experiment artifacts before auxiliary experiments."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.experiment_period_harmonics import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', type=Path, required=True)
    args = parser.parse_args()
    out = args.experiment
    dest = out/'parent_artifact_timing_note.json'
    if dest.exists() or (out/'centroid_proxy.json').exists() or (out/'fixed_phase').exists():
        raise ValueError('Freeze must run once, before auxiliary experiments')
    paths = [out/'protocol.json', out/'input_features.npz']
    note = {'created_at': datetime.now().astimezone().isoformat(),
        'scope': 'Parent-artifact hashes frozen before auxiliary proxy/fixed-phase experiments',
        'sha256': {str(p.resolve()): sha256(p) for p in paths}}
    dest.write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Parent artifacts frozen')


if __name__ == '__main__':
    main()
