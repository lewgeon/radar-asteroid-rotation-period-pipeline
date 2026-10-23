"""Run the scoped full-grid Monte Carlo scorer with batched peak proposals."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import experiment_receiver_snr as experiment
from scripts.monte_carlo_refinement import BatchedPredictiveSearch


def require_extraction_sources(manifest):
    current=experiment.hashes()
    if manifest['source_hashes_at_start']!=current or manifest['source_hashes_at_end']!=current:
        raise ValueError('extraction/search scientific source identity differs; rebuild extraction with the same sources')


if __name__=='__main__':
    names=['scripts/monte_carlo_refinement.py','scripts/scipy_bounded_batch.py','scripts/search_receiver_snr.py']
    source_start={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    experiment.FixedPredictiveSearch=lambda *args,**kwargs:BatchedPredictiveSearch(*args,device='cuda:0',**kwargs)
    if '--phase' not in sys.argv:sys.argv.extend(['--phase','search'])
    if '--output' in sys.argv and sys.argv[sys.argv.index('--phase')+1]=='search':
        output=Path(sys.argv[sys.argv.index('--output')+1])
        require_extraction_sources(json.loads((output/'extraction.json').read_text(encoding='utf-8')))
    experiment.main()
    output=Path(sys.argv[sys.argv.index('--output')+1])
    path=output/'result.json'
    result=json.loads(path.read_text(encoding='utf-8'))
    source_end={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    if source_start!=source_end:raise AssertionError('accelerator source changed during search')
    result['scoring_accelerator']=dict(scope='batch SciPy bounded Brent state machine for all peaks; final winning bracket uses production SVD/Brent; close scores use full reference',
        source_sha256=source_end)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
