"""Prepare new EV5 configurations and centered meshes without overwriting inputs.

70 m means the supplied mesh's maximum Cartesian extent. The real-target
400 m case uses volume-equivalent diameter, matching the physical convention.
"""
import argparse,hashlib,json,copy
from pathlib import Path
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parents[1]


def write_new(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)


def prepare(source,tag):
    folder=ROOT/'assets'/tag
    folder.mkdir(parents=True,exist_ok=False)
    mesh=trimesh.load(source,process=False,force='mesh')
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:
        raise ValueError('require a closed, consistently wound mesh with positive volume')
    center=mesh.center_mass.copy();diameter=(6*mesh.volume/np.pi)**(1/3)
    if not np.isclose(mesh.extents.max(),70,rtol=.001):raise ValueError('expected supplied maximum extent 70 m')
    paths={}
    for label,factor in [('70m',1.),('400m',400/diameter)]:
        derived=mesh.copy();derived.vertices=(mesh.vertices-center)*factor
        path=folder/f'ev5_centered_{label}.obj'
        derived.export(path)
        paths[label]=dict(path=str(path),scale=factor,extents_m=derived.extents.tolist(),
            volume_equivalent_diameter_m=float((6*derived.volume/np.pi)**(1/3)),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    observation=json.loads((ROOT/'configs/seperate_observation_2.json').read_text(encoding='utf-8'))['observation']
    echo=json.loads((ROOT/'runs/seperate_observation_2/configs/echo.generated.json').read_text(encoding='utf-8'))
    for key in ('observation_info_path','output_path'):echo.pop(key,None)
    inversion=json.loads((ROOT/'runs/seperate_observation_2/configs/inversion.generated.json').read_text(encoding='utf-8'))
    inversion.pop('output_path',None)
    pair=dict(observation=observation,echo=echo,inversion=inversion)
    pair['echo']['model_path']=paths['70m']['path']
    write_new(ROOT/'configs'/f'{tag}_70m.json',pair)
    actual=copy.deepcopy(pair)
    actual['observation']['target'].update(id='341843',name='2008 EV5',extent_path_m=1000.)
    actual['observation']['schedule'].update(start_utc='2039-12-26T00:00:00Z',end_utc='2039-12-30T00:00:00Z',run_count=100,run_duration_s=2.)
    actual['observation']['visibility'].update(min_tx_elevation_deg=20.,min_rx_elevation_deg=20.)
    actual['echo']['model_path']=paths['400m']['path']
    actual['echo']['target']['rotation_period_s']=3.725*3600
    # Same broad blind search, includes both 3.725h and its half-period.
    actual['inversion'].update(period_min_s=1800.,period_max_s=28800.,period_grid_size=8000)
    write_new(ROOT/'configs'/f'{tag}_400m.json',actual)
    write_new(folder/'provenance.json',dict(source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        center_mass_translation_m=center.tolist(),assumed_density='uniform; translation only; supplied +Z remains spin axis',
        source_maximum_extent_m=float(mesh.extents.max()),source_volume_equivalent_diameter_m=float(diameter),
        vertices=len(mesh.vertices),faces=len(mesh.faces),derived=paths))
    return actual


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh',type=Path,required=True)
    parser.add_argument('--tag',default='ev5_snr_20261016')
    args=parser.parse_args()
    config=prepare(args.mesh,args.tag)
    write_new(ROOT/'tmp'/f'{args.tag}_observation_preview.json',config['observation'])
