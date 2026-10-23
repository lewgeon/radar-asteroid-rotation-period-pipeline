"""Run an astronomy CLI with a workspace-local Astropy/Astroquery cache."""
import runpy,sys
from pathlib import Path
from astropy.config.paths import set_temp_cache

if __name__=='__main__':
    if len(sys.argv)<3 or sys.argv[1] not in ('--module','--script'):
        raise SystemExit('usage: python scripts/run_local_astropy.py --module PACKAGE.MODULE | --script PATH [args]')
    mode,target=sys.argv[1:3];sys.argv=[target,*sys.argv[3:]]
    root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root))
    cache=root/'tmp/astropy_cache';cache.mkdir(parents=True,exist_ok=True)
    with set_temp_cache(cache,delete=False):
        if mode=='--module':runpy.run_module(target,run_name='__main__')
        else:
            path=Path(target).resolve();sys.path.insert(0,str(path.parent))
            runpy.run_path(str(path),run_name='__main__')
