import json
import hashlib
import numpy as np
import pytest
import trimesh
from scripts import prepare_ev5_experiments as preparation


def test_mesh_centering_and_volume_scaling_preserve_original_and_rf(tmp_path,monkeypatch):
    monkeypatch.setattr(preparation,'ROOT',tmp_path)
    config=tmp_path/'configs';config.mkdir()
    (config/'seperate_observation_2.json').write_text(json.dumps(dict(observation=dict(target={},schedule={},visibility={},
        receiver_sampling=dict(fast_sample_rate_hz=200e6)))))
    generated=tmp_path/'runs/seperate_observation_2/configs';generated.mkdir(parents=True)
    rf=dict(carrier_frequency_hz=1e9)
    echo=dict(radar=rf,waveform=dict(bandwidth_hz=150e6),target=dict(rotation_period_s=10800.,spin_pole_icrs_deg=[105,-66]))
    (generated/'echo.generated.json').write_text(json.dumps(echo))
    (generated/'inversion.generated.json').write_text(json.dumps(dict(cpi_duration_s=1.)))
    mesh=trimesh.creation.icosphere(subdivisions=1,radius=35.)
    mesh.apply_translation([1,2,3]);source=tmp_path/'original.obj';mesh.export(source)
    original=source.read_bytes()
    actual=preparation.prepare(source,'case')
    path=tmp_path/'assets/case'
    small=trimesh.load(path/'ev5_centered_70m.obj',process=False)
    large=trimesh.load(path/'ev5_centered_400m.obj',process=False)
    assert source.read_bytes()==original
    np.testing.assert_allclose(small.center_mass,0,atol=1e-7)
    np.testing.assert_allclose(large.center_mass,0,atol=1e-7)
    assert abs(small.extents.max()-70)<1e-7
    assert abs((6*large.volume/np.pi)**(1/3)-400)<1e-6
    assert np.max(abs(large.vertices-small.vertices))>100,'scaling fixture must separate models'
    provenance=json.loads((path/'provenance.json').read_text())
    assert provenance['source_sha256']==hashlib.sha256(original).hexdigest()
    assert actual['echo']['radar']==rf
    assert actual['echo']['waveform']['bandwidth_hz']==150e6
    assert actual['observation']['receiver_sampling']['fast_sample_rate_hz']==200e6
    assert actual['echo']['target']['rotation_period_s']==13410
    assert actual['observation']['target']['id']=='341843'
    frozen=(config/'case_400m.json').read_bytes()
    with pytest.raises(FileExistsError):preparation.prepare(source,'case')
    assert (config/'case_400m.json').read_bytes()==frozen
