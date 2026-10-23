import pytest
from scripts.summarize_snr_scan import summarize


def rows(db,errors):
    return [dict(trial=i,snr_db=db,status='selected' if error is not None else 'unavailable',
        period_s=None if error is None else 100*(1+error),relative_error=error) for i,error in enumerate(errors)]


def test_threshold_requires_all_higher_points_and_counts_failures():
    data=rows(-10,[0]*20)+rows(-8,[.2]*2+[0]*18)+rows(-6,[None]+[0]*19)+rows(-4,[0]*20)
    result=summarize(data,100,100)
    for value in result['thresholds'].values():
        assert value['empirical_scan_bracket_db']==[-8,-6]
    assert result['summary'][2]['failures']==1
    assert result['summary'][2]['success']['0.001']['fraction']==.95
    assert result['summary'][1]['success']['0.1']['fraction']==.9


def test_clean_failure_does_not_masquerade_as_noise_limit():
    result=summarize(rows(0,[0]*20),100,102)
    assert result['thresholds']['0.001']['status']=='noiseless_baseline_fails'
    assert result['thresholds']['0.1']['status']=='at_or_below_scan_minimum'
    with pytest.raises(ValueError,match='duplicate'):summarize(rows(0,[0])+rows(0,[0]),100,100)
    with pytest.raises(ValueError,match='disagrees'):summarize(rows(0,[.01]),200,200)
    for invalid in (float('nan'),float('inf'),0,-1):
        with pytest.raises(ValueError,match='clean'):summarize(rows(0,[0]),100,invalid)
    with pytest.raises(ValueError,match='empty'):summarize([],100,100)


def test_combine_checks_grid_truth_config_sources_and_builds_merged_manifest(tmp_path):
    import copy,json
    from scripts.summarize_snr_scan import combine
    iq=tmp_path/'iq';iq.write_bytes(b'fixed input')
    def dataset(db):
        return dict(truth_repetition_s=100,clean_period_s=100,records=rows(db,[0]*20),
            manifest=dict(input=dict(path=str(iq),size_bytes=iq.stat().st_size,mtime_ns=iq.stat().st_mtime_ns),
                snapshot_sha256='snapshot',seed=1,trials=20,snr_db=[db],
                truth_repetition_s=100,config={'h':1},feature_names=['x'],signal_power=1.,power_definition='same',
                source_hashes_at_start={'kernel':'a'},source_hashes_at_end={'kernel':'a'}),
            final_source_hashes={'kernel':'a','scripts/experiment_receiver_snr.py':'old'},scoring_accelerator={'version':1})
    first=tmp_path/'first.json';second=tmp_path/'second.json'
    first.write_text(json.dumps(dataset(-2)))
    second.write_text(json.dumps(dataset(0)))
    result=combine([first,second])
    assert result['manifest']['snr_db']==[-2,0]
    assert len(result['source_manifests'])==2
    for change,match in [('missing','incomplete'),('truth','truth'),('config','config'),('kernel','identity'),('extract','identity')]:
        bad=copy.deepcopy(dataset(0))
        if change=='missing':bad['records'].pop()
        elif change=='truth':bad['manifest']['truth_repetition_s']=101
        elif change=='config':bad['manifest']['config']['h']=2
        elif change=='kernel':bad['final_source_hashes']['kernel']='b'
        else:bad['manifest']['source_hashes_at_start']['kernel']='bad'
        second.write_text(json.dumps(bad))
        with pytest.raises(ValueError,match=match):combine([first,second])
