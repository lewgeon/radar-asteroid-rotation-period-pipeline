"""Freeze mesh and auxiliary module hashes before a half-period experiment."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_period_harmonics import sha256


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,default=ROOT/'runs/paras_for_70m_3h')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:
        data=json.loads(args.output.read_text(encoding='utf-8'))
        if not all(sha256(p)==digest for p,digest in data['sha256'].items()):
            raise ValueError('Additional input hashes changed')
        print('Additional input hashes unchanged')
        return
    if args.output.exists():
        raise ValueError('Manifest exists; choose a new path')
    cfg=json.loads((args.job/'configs/echo.generated.json').read_text(encoding='utf-8'))
    paths=[Path(cfg['model_path'])]+[ROOT/'echo/src'/name for name in
        ['config_normalize.py','geometry.py','dataset.py','light_time.py']]
    data={'created_at':datetime.now().astimezone().isoformat(),
          'scope':'mesh and auxiliary module hashes for controlled echo generation',
          'sha256':{str(p):sha256(p) for p in paths}}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(args.output)


if __name__=='__main__':
    main()
