import sys
from types import SimpleNamespace
import numpy as np
import pytest
from scripts import experiment_receiver_snr as experiment


@pytest.mark.parametrize('flags',[
    ['--snr-min','nan'],['--snr-step','0'],['--snr-min','10','--snr-max','2'],
    ['--snr-min','-10000','--snr-max','30','--snr-step','.001'],
    ['--snr-points','0','0'],['--snr-points','1','0'],['--snr-points','nan'],
    ['--snr-points','-25','--snr-step','2'],['--snr-points','-301'],
])
def test_invalid_snr_grid_rejected_before_io(monkeypatch,flags):
    monkeypatch.setattr(sys,'argv',['experiment','--phase','extract','--output','unused',*flags])
    monkeypatch.setattr(experiment,'extract',lambda _:pytest.fail('must reject before IO'))
    with pytest.raises(SystemExit):experiment.main()


def test_negative_snr_scan_keeps_old_defaults_and_explicit_grid(monkeypatch):
    captured=[]
    monkeypatch.setattr(experiment,'extract',captured.append)
    for flags in ([],['--snr-min','-60','--snr-max','4','--snr-step','2']):
        monkeypatch.setattr(sys,'argv',['experiment','--phase','extract','--output','unused',*flags])
        experiment.main()
    grids=[np.arange(a.snr_min,a.snr_max+a.snr_step*.25,a.snr_step) for a in captured]
    np.testing.assert_array_equal(grids[0],np.arange(5.,31.))
    np.testing.assert_array_equal(grids[1],np.arange(-60.,5.,2.))
    assert len(grids[0])!=len(grids[1])


def test_nondivisible_snr_range_does_not_exceed_upper_bound():
    actual=experiment.snr_values(0,.5,.6)
    np.testing.assert_array_equal(actual,[0.])
    np.testing.assert_array_equal(experiment.snr_values(5,30,1),np.arange(5.,31.))


def test_explicit_boundary_points_reach_extractor_unchanged(monkeypatch):
    captured=[]
    monkeypatch.setattr(experiment,'extract',captured.append)
    monkeypatch.setattr(sys,'argv',['experiment','--phase','extract','--output','unused',
        '--snr-points','-25','-23','-15'])
    experiment.main()
    assert captured[0].snr_points==[-25.,-23.,-15.]


def test_search_truth_is_bound_to_extraction_manifest():
    assert experiment.bound_truth(None,{'truth_repetition_s':13410})==13410
    assert experiment.bound_truth(13410,{'truth_repetition_s':13410})==13410
    with pytest.raises(ValueError,match='truth'):experiment.bound_truth(5400,{'truth_repetition_s':13410})


def test_snapshot_scientific_names_are_not_confused_with_display_labels():
    names=['total_power','doppler_centroid_hz','rms_bandwidth_hz','range_centroid_s','energy_range_width_90_s']
    experiment.validate_snapshot_names(names)
    with pytest.raises(ValueError,match='column order'):experiment.validate_snapshot_names(names[::-1])


def test_known_pole_los_protocol_accepts_geometry_and_rejects_missing_or_invalid_pole():
    valid=dict(los_phase_compensation=True,spin_axis_ra_deg=105.,spin_axis_dec_deg=-66.,phase_period_convention='full_rotation')
    experiment.validate_protocol(valid)
    for update in ({'spin_axis_ra_deg':None},{'spin_axis_dec_deg':91.},{'spin_axis_ra_deg':True},{'phase_period_convention':'unknown'}):
        with pytest.raises(ValueError):experiment.validate_protocol(dict(valid,**update))
    with pytest.raises(ValueError):experiment.validate_protocol({'los_phase_compensation':True})


def test_search_entry_requires_identical_extraction_sources_including_driver(monkeypatch):
    from scripts.search_receiver_snr import require_extraction_sources
    current={'kernel':'a','scripts/experiment_receiver_snr.py':'driver-a'}
    monkeypatch.setattr(experiment,'hashes',lambda:current)
    require_extraction_sources(dict(source_hashes_at_start=current,source_hashes_at_end=current))
    for key in current:
        changed=dict(current,**{key:'changed'})
        with pytest.raises(ValueError,match='identity'):
            require_extraction_sources(dict(source_hashes_at_start=changed,source_hashes_at_end=changed))


def test_unsupported_accelerator_uses_actual_production_channel_filter():
    class Scorer:
        def select(self,values,return_grid=False):raise ValueError('constant feature')
        def production(self,values):
            return dict(period_s=10.,score=-.1,status='weak',candidates=[],warnings=['weak'],
                diagnostics=dict(excluded_channels={'x':'constant_feature'}))
    actual=experiment.selected_with_fallback(Scorer(),np.zeros((20,5)))
    assert actual['period_s']==10.
    assert actual['production_status']=='weak'
    assert actual['search_route']=='production_fallback'
    assert 'status' not in actual,'MC availability must not collide with production quality status'
