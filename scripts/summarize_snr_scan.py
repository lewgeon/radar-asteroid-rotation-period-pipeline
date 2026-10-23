"""Combine disjoint fixed-scene SNR scans and bracket empirical thresholds."""
import argparse,csv,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_receiver_snr import wilson,file_sha256


def summarize(records,truth,clean_period):
    if not np.isfinite(truth) or truth<=0:raise ValueError('invalid truth')
    if not np.isfinite(clean_period) or clean_period<=0:raise ValueError('invalid clean period')
    if not records:raise ValueError('empty records')
    for row in records:
        if not np.isfinite(row['snr_db']):raise ValueError('invalid SNR')
        if row['status'] not in ('selected','unavailable'):raise ValueError('unknown result status')
        if row['status']=='selected' and (not np.isfinite(row['period_s']) or row['period_s']<=0):
            raise ValueError('invalid selected period')
    keys=[(r['trial'],r['snr_db']) for r in records]
    if len(keys)!=len(set(keys)):raise ValueError('duplicate trial/SNR records')
    summary=[]
    for db in sorted({r['snr_db'] for r in records}):
        selected=[r for r in records if r['snr_db']==db]
        errors=[]
        for row in selected:
            value=abs(row['period_s']/truth-1) if row['status']=='selected' else np.inf
            if np.isfinite(value) and not np.isclose(value,row['relative_error'],rtol=1e-12,atol=1e-15):
                raise ValueError('stored relative error disagrees with declared truth')
            errors.append(value)
        errors=np.asarray(errors);finite=errors[np.isfinite(errors)]
        result=dict(snr_db=db,trials=len(errors),failures=int((~np.isfinite(errors)).sum()),
            nonpositive_predictive_score_count=(sum(r['score']<=0 for r in selected if r['status']=='selected')
                if all('score' in r for r in selected if r['status']=='selected') else None),
            relative_error_median=float(np.median(finite)) if len(finite) else None,
            relative_error_rmse=float(np.sqrt(np.mean(finite**2))) if len(finite) else None,
            relative_error_q95=float(np.quantile(finite,.95)) if len(finite) else None,
            max_relative_error=float(finite.max()) if len(finite) else None,success={})
        for tolerance in (.1,.01,.001):
            count=int((errors<=tolerance).sum())
            result['success'][str(tolerance)]=dict(count=count,fraction=count/len(errors),wilson95=wilson(count,len(errors)))
        summary.append(result)
    clean_error=abs(clean_period/truth-1)
    thresholds={}
    for tolerance in (.1,.01,.001):
        good=[r['success'][str(tolerance)]['fraction']>=.95 for r in summary]
        indices=[i for i in range(len(good)) if all(good[i:])]
        index=indices[0] if indices else None
        bracket=None if index is None else [None if index==0 else summary[index-1]['snr_db'],summary[index]['snr_db']]
        status=('noiseless_baseline_fails' if clean_error>tolerance else
            'no_successful_upper_tail_in_scan' if index is None else
            'at_or_below_scan_minimum' if index==0 else 'bracketed_on_scan')
        thresholds[str(tolerance)]=dict(status=status,clean_baseline_passes=clean_error<=tolerance,
            empirical_scan_bracket_db=bracket,minimum_scanned_snr_db=None if index is None else summary[index]['snr_db'],
            criterion='empirical fraction >= .95 at this and every higher scanned point; pointwise Wilson only')
    return dict(truth_repetition_s=truth,clean_period_s=clean_period,clean_relative_error=clean_error,
        summary=summary,thresholds=thresholds,records=records)


def combine(paths):
    datasets=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
    if not datasets:raise ValueError('no sources')
    base=datasets[0]
    records=[]
    source_changes={}
    for data in datasets:
        manifest=data['manifest']
        expected={(trial,float(db)) for db in manifest['snr_db'] for trial in range(manifest['trials'])}
        actual=[(r['trial'],r['snr_db']) for r in data['records']]
        if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('incomplete declared trial/SNR grid')
        if manifest['truth_repetition_s']!=data['truth_repetition_s']:raise ValueError('result truth differs from extraction')
        if data['truth_repetition_s']!=base['truth_repetition_s']:raise ValueError('different declared truths')
        if data['manifest']['input']!=base['manifest']['input']:raise ValueError('different IQ identities')
        if data['manifest']['snapshot_sha256']!=base['manifest']['snapshot_sha256']:raise ValueError('different snapshots')
        if data['manifest']['seed']!=base['manifest']['seed']:raise ValueError('different seeds')
        for key,default in [('noise_engine','numpy'),('noise_seed_mapping',None)]:
            if manifest.get(key,default)!=base['manifest'].get(key,default):raise ValueError(f'different {key}')
        if manifest.get('noise_engine','numpy')=='torch':
            for key in ('actual_device','noise_torch_version','noise_numpy_version'):
                if manifest[key]!=base['manifest'][key]:raise ValueError(f'different Torch noise identity {key}')
        for key in ('trials','config','feature_names','signal_power','power_definition'):
            if data['manifest'][key]!=base['manifest'][key]:raise ValueError(f'different {key}')
        if data.get('scoring_accelerator')!=base.get('scoring_accelerator'):raise ValueError('different search accelerator identity')
        hashes=data['final_source_hashes'];reference=base['final_source_hashes']
        if hashes.keys()!=reference.keys():raise ValueError('different scientific source lists')
        for name,digest in hashes.items():
            if name!='scripts/experiment_receiver_snr.py':
                start=manifest['source_hashes_at_start'].get(name)
                end=manifest['source_hashes_at_end'].get(name)
                if start!=end or end!=digest:raise ValueError(f'extraction/search scientific identity changed: {name}')
            if digest!=reference[name]:
                # The driver adds SNR/identity guards and production fallback;
                # receiver kernels and scorer must retain baseline identities.
                if name!='scripts/experiment_receiver_snr.py':raise ValueError(f'different scientific source {name}')
                source_changes.setdefault(name,set()).update([digest,reference[name]])
        if abs(data['clean_period_s']-base['clean_period_s'])>1e-4:raise ValueError('different clean estimates')
        records.extend(data['records'])
    result=summarize(records,base['truth_repetition_s'],base['clean_period_s'])
    result['manifest']={key:base['manifest'][key] for key in ('input','snapshot_sha256','seed','trials',
        'config','feature_names','power_definition','signal_power','truth_repetition_s')}
    result['manifest']['snr_db']=[row['snr_db'] for row in result['summary']]
    for key in ('noise_engine','noise_seed_mapping','noise_torch_version','noise_numpy_version','actual_device','phase_compensation'):
        if key in base['manifest']:result['manifest'][key]=base['manifest'][key]
    iq=Path(base['manifest']['input']['path'])
    identity=iq.stat()
    expected_identity=base['manifest']['input']
    if (identity.st_size,identity.st_mtime_ns)!=(expected_identity['size_bytes'],expected_identity['mtime_ns']):
        raise ValueError('current IQ identity differs from scan input')
    content_hash=file_sha256(iq)
    for data in datasets:
        if data['manifest'].get('input_sha256',content_hash)!=content_hash:raise ValueError('IQ content hash mismatch')
    result['manifest']['input_sha256']=content_hash
    result['input_content_verified_utc']=datetime.now(timezone.utc).isoformat()
    result['source_manifests']=[data['manifest'] for data in datasets]
    result['explicit_cli_source_differences']={key:sorted(value) for key,value in source_changes.items()}
    result['sources']=[dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=combine(args.input)
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    with (args.output/'trials.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['trial','snr_db','status','period_s','relative_error']
        writer=csv.DictWriter(f,fields,extrasaction='ignore');writer.writeheader();writer.writerows(result['records'])
    print(json.dumps(result['thresholds'],indent=2))
