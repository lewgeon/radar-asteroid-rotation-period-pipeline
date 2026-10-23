"""Paired cached-CPI view benchmark; never generate scientific intermediates."""
import argparse,json,sys,time,tracemalloc
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--echo',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'tmp/rd_view_benchmark')
    args=parser.parse_args();source=args.echo.resolve()
    from rotation_gui.window import result_service as service
    from rotation_gui.window.inversion_feature_preview import _load_echo
    core=service._inversion_module()
    from processing_store import stage_key,identity
    from types import SimpleNamespace
    with np.load(source.parent/'processing_cache/observations.npz') as data:
        key=json.loads(data['manifest'].item())['key'];config=key['policy'];windows=data['cpi_windows']
    if key!=stage_key(SimpleNamespace(_source_identity=identity(source)),config):
        raise ValueError('Scientific cache is not current; run inversion before benchmarking')
    indices=np.unique([0,len(windows)//2,len(windows)-1]);records=[]
    from unittest.mock import patch
    def legacy(index):
        echo=_load_echo(source)
        core.prepare_chirp_observations(echo,config)
        return service._cached_scientific_rd(echo,config,-1,int(index))
    with patch.object(core,'prepare_chirp_pulse_profiles',side_effect=AssertionError('Benchmark must not compute FFT')):
        # Initialize Plotly/imports before timing either algorithm.
        service.scientific_rd(source,config,-1,int(indices[0]))
        for index in indices:
            figures=[]
            for method,function in (('previous_full_stage',legacy),('selected_frame',lambda i:service.scientific_rd(source,config,-1,int(i)))):
                tracemalloc.start();begin=time.perf_counter();figure=function(index)
                duration=time.perf_counter()-begin;peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
                figures.append(figure)
                records.append(dict(cpi=int(index),method=method,seconds=duration,peak_mib=peak/2**20))
            for a,b in zip(figures[0].data,figures[1].data):np.testing.assert_array_equal(a.z,b.z)
    from datetime import datetime,timezone
    result=dict(measured_utc=datetime.now(timezone.utc).isoformat(),pairs_per_cpi=1,cpi_samples=len(indices),
        source=key['source'],policy=config,measurement='Warm Plotly construction only; no HTML/browser/cold-stage cost',records=records,max_array_difference=0)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
