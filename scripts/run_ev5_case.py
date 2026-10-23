"""Launch an isolated EV5 simulation via the existing production pipeline."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def source_hashes():
    files=[ROOT/'pipeline.py',ROOT/'echo/simulate_echo.py',
        ROOT/'observation/solve_observation_info.py',ROOT/'inversion/scripts/estimate_period.py']
    for package in ('observation','echo','inversion'):files.extend((ROOT/package/'src').glob('*.py'))
    return {str(p.relative_to(ROOT)):digest(p) for p in sorted(files)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['70m','400m'],required=True)
    parser.add_argument('--tag',default='ev5_snr_20261016')
    args=parser.parse_args()
    config=ROOT/'configs'/f'{args.tag}_{args.case}.json'
    config_hash=digest(config)
    body=json.loads(config.read_text(encoding='utf-8'))
    model=Path(body['echo']['model_path']);model_hash=digest(model)
    initial_sources=source_hashes()
    name=config.stem
    destination=ROOT/'runs'/name
    destination.mkdir(parents=True,exist_ok=False)
    command=[sys.executable,str(ROOT/'pipeline.py'),'--config',str(config),
        '--runs-dir',str(ROOT/'runs'),'--run-name',name]
    observation_source=None
    if args.case=='70m':
        observation_source=ROOT/'runs/seperate_observation_2/observation_info.npz'
        shutil.copy2(observation_source,destination/'observation_info.npz')
        command.extend(['--skip-observation','--allow-legacy-reuse'])
    cache=ROOT/'tmp/astropy_cache';(cache/'astropy').mkdir(parents=True,exist_ok=True)
    environment=os.environ.copy();environment['XDG_CACHE_HOME']=str(cache)
    environment.update(GIT_CONFIG_COUNT='4',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=str(ROOT),
        GIT_CONFIG_KEY_1='safe.directory',GIT_CONFIG_VALUE_1=str(ROOT/'inversion'),
        GIT_CONFIG_KEY_2='safe.directory',GIT_CONFIG_VALUE_2=str(ROOT/'echo'),
        GIT_CONFIG_KEY_3='safe.directory',GIT_CONFIG_VALUE_3=str(ROOT/'observation'))
    start=time.perf_counter()
    completed=subprocess.run(command,cwd=ROOT,env=environment,check=False)
    final_sources=source_hashes()
    valid=initial_sources==final_sources and config_hash==digest(config) and model_hash==digest(model)
    record=dict(config=str(config),config_sha256=config_hash,model_sha256=model_hash,
        source_hashes_at_start=initial_sources,source_hashes_at_end=final_sources,
        sources_config_and_model_unchanged=valid,
        command=command,seconds=time.perf_counter()-start,exit_code=completed.returncode,
        reused_observation=None if observation_source is None else str(observation_source),
        scope='nominal-parameter simulated echo, not measured asteroid radar data')
    with (destination/'launch_record.json').open('x',encoding='utf-8') as f:
        json.dump(record,f,ensure_ascii=False,indent=2)
    raise SystemExit(completed.returncode if valid else 1)


if __name__=='__main__':main()
