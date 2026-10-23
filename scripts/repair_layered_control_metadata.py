"""Versioned metadata-only correction, retaining original generation provenance."""
from pathlib import Path
import sys
import argparse
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_optional_period_precision import sha256

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--controls',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    original_manifest=args.controls/'generation.json'
    manifest=json.loads(original_manifest.read_text(encoding='utf-8'))
    for record in manifest['records']:
        mode=record['mode']
        source=args.controls/mode
        destination=args.output/mode
        destination.mkdir()
        old_obs=source/'observation_info.npz'
        old_echo=source/'echo.npz'
        if sha256(old_echo)!=record['echo_sha256'] or sha256(old_obs)!=record['observation_sha256']:
            raise ValueError('Original generation artifact changed')
        with np.load(old_obs) as d:
            payload={k:d[k].copy() for k in d.files}
        changes={'frame':'Inherited ICRS directions; virtual synthetic geometry',
            'time_scale':'UTC reference, inherited scatter elapsed seconds; static-range event reconstruction',
            'solver_version':'layered-control-v1, not an astronomical ephemeris solution'}
        meta=json.loads(str(payload['metadata_json'].item()))
        meta.update(changes)
        for name,value in changes.items():
            payload[name]=np.array(value)
        payload['metadata_json']=np.array(json.dumps(meta))
        new_obs=destination/'observation_info.npz'
        np.savez_compressed(new_obs,**payload)
        with np.load(old_obs) as old,np.load(new_obs) as new:
            for name in old.files:
                if name in set(changes)|{'metadata_json'}:
                    continue
                same=np.array_equal(old[name],new[name],equal_nan=True) if np.issubdtype(old[name].dtype,np.number) else np.array_equal(old[name],new[name])
                if not same:
                    raise ValueError('Numerical observation altered by metadata repair')
        with np.load(old_echo) as d:
            ep={k:d[k].copy() for k in d.files}
        em=json.loads(str(ep['metadata_json'].item()))
        em['original_observation_info_sha256']=em['observation_info_sha256']
        em['original_observation_info_path']=em.get('observation_info_path')
        em['observation_info_path']=str(new_obs.resolve())
        em['observation_info_sha256']=sha256(new_obs)
        em['metadata_only_provenance_repair']=True
        ep['metadata_json']=np.array(json.dumps(em))
        new_echo=destination/'echo.npz'
        np.savez(new_echo,**ep)
        with np.load(old_echo) as old,np.load(new_echo) as new:
            for name in old.files:
                if name!='metadata_json' and not np.array_equal(old[name],new[name]):
                    raise ValueError('Echo array altered by metadata repair')
        config=json.loads((source/'echo_config.json').read_text(encoding='utf-8'))
        config['observation_info_path']=str(new_obs.resolve())
        (destination/'echo_config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        record.update(original_echo_sha256=record['echo_sha256'],original_observation_sha256=record['observation_sha256'],
            echo_sha256=sha256(new_echo),observation_sha256=sha256(new_obs),numerical_arrays_unchanged=True)
    manifest['metadata_repair']={'source':str(original_manifest.resolve()),'source_sha256':sha256(original_manifest),
        'repair_source_sha256':sha256(Path(__file__)),'scope':'Only frame/time_scale/solver labels and provenance; all numerical arrays unchanged'}
    (args.output/'generation.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(args.output)

if __name__=='__main__':
    main()
