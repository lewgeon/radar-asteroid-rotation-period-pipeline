"""Independent same-session float32 regeneration for the dtype comparison."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np
import torch
from tqdm import tqdm
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.experiment_half_period_diagnosis import features, search_all
from scripts.experiment_period_harmonics import sha256
from echo.src.echo import generate_echo
from inversion.src.dataset import load_echo

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--job',type=Path,default=Path('runs/paras_for_70m_3h'))
parser.add_argument('--diagnosis-dir',type=Path)
args=parser.parse_args()
root=args.job
out=args.diagnosis_dir or root/'half_period_diagnosis_20261011'
destination=out/'original_float32_repeat.json'
if destination.exists():
    raise ValueError('Repeat result exists; this script refuses to overwrite it')
protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
auxiliary=json.loads((out/'auxiliary_manifest.json').read_text(encoding='utf-8'))
sources={str(Path(__file__).resolve().parents[1]/p):digest for p,digest in protocol['source_sha256'].items()}
for paths in (protocol['input_sha256'],auxiliary['sha256'],sources):
    if not all(sha256(p)==digest for p,digest in paths.items()):
        raise ValueError('Frozen inputs or mesh/module files changed')
cfg=json.loads((root/'configs/echo.generated.json').read_text(encoding='utf-8'))
inv=json.loads((root/'configs/inversion.generated.json').read_text(encoding='utf-8'))
cfg['compute']={'device':'cuda:0' if torch.cuda.is_available() else 'cpu','dtype':'float32'}
cfg.pop('output_path',None)
start=time.perf_counter()
bar=tqdm(total=100,desc='original_float32_repeat',unit='%')
last=[0]
def progress(stage,percent,message):
    if percent>last[0]:
        bar.update(percent-last[0]);last[0]=percent
echo=generate_echo(cfg,progress_callback=progress)
bar.update(100-last[0]);bar.close()
generated_features=features(echo,inv)
original=load_echo(root/'echo/echo.npz')
np.testing.assert_array_equal(echo.scatter_elapsed_s,original.scatter_elapsed_s)
iq_delta=float(np.max(np.abs(echo.iq-original.iq)))
iq_relative=float(np.linalg.norm(echo.iq-original.iq)/np.linalg.norm(original.iq))
with np.load(out/'original_features.npz') as d:
    np.testing.assert_array_equal(d['time'],echo.scatter_elapsed_s)
    original_features=d['value']
np.savez_compressed(out/'original_float32_repeat_features.npz',time=echo.scatter_elapsed_s,value=generated_features)
data={'iq_exact_equal':bool(np.array_equal(echo.iq,original.iq)),
      'iq_max_abs_difference':iq_delta,'iq_relative_l2_difference':iq_relative,
      'feature_max_abs_difference_from_frozen':np.max(np.abs(generated_features-original_features),axis=0).tolist(),
      'echo_metadata':echo.metadata,'source_script_sha256':sha256(__file__),'elapsed_s_before_search':time.perf_counter()-start}
data['estimates']=search_all(echo.scatter_elapsed_s,generated_features,inv,
    cfg['target']['rotation_period_s']/2,'original_float32_repeat')
data['elapsed_s']=time.perf_counter()-start
data['input_hashes_unchanged']=all(sha256(p)==digest for p,digest in protocol['input_sha256'].items())
data['additional_hashes_unchanged']=all(sha256(p)==digest for p,digest in auxiliary['sha256'].items())
data['source_hashes_unchanged']=all(sha256(p)==digest for p,digest in sources.items())
if not data['input_hashes_unchanged'] or not data['additional_hashes_unchanged'] or not data['source_hashes_unchanged']:
    raise RuntimeError('Input or mesh/module hashes changed during repeat')
destination.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(data,flush=True)
