"""Independent boundary cases discovered in the second physical audit."""
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from observation.src.light_time import C, StaticState, LinearState, propagate_from_transmit_epochs
from observation.src.campaign_planning import resolve_campaign_run_plan
from observation.src.planning import build_transmit_schedule,plan_reception,select_run_start_offsets,VisibilityWindow
from echo.src.echo import _generate_chirp_echo,generate_echo
from echo.src.mesh import SurfaceMesh
from echo.src.motion import Spin


class PhysicalBoundaryTests(unittest.TestCase):
    def test_campaign_preview_rejects_individually_infeasible_monostatic_run(self):
        config_path = Path(__file__).resolve().parents[1] / "configs" / "chirp_mesh_target_test.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))["observation"]
        # This boundary fixture must not inherit the editable mesh example's RF values.
        config["transmit"].update(prf_hz=2.0, pulse_width_s=4.0e-5)
        config["target"]["extent_path_m"] = 1000.0
        config["schedule"]["run_count"] = 1
        config["schedule"]["run_duration_s"] = 600.0

        preview = resolve_campaign_run_plan(config, allow_infeasible_preview=True)

        self.assertFalse(preview.run_feasible)
        self.assertEqual(preview.max_run_count, 0)
        # 2 Hz and a 40 µs pulse: 240 pulses fit before the ~120 s echo, so the
        # exclusive run length is 240/2 + 40 µs.
        self.assertAlmostEqual(preview.max_run_duration_exclusive_s, 120.00004, places=6)
        self.assertIn("单次 Run", preview.run_feasibility_error)

        with self.assertRaisesRegex(ValueError, "单次 Run.*600"):
            resolve_campaign_run_plan(config)

    def test_each_cpi_uses_its_own_doppler_axis(self):
        from inversion.src.radar_signal import range_doppler_cube,range_doppler_features
        times=np.r_[np.arange(8)*.1,10+np.arange(8)*.2]
        iq=np.exp(2j*np.pi*np.arange(16)/8)[:,None]
        cube=range_doppler_cube(iq,times,np.repeat([0,1],8),[0.],
                               cpi_pulses=8,cpi_hop_pulses=8,window='boxcar')
        features=range_doppler_features(cube)
        np.testing.assert_allclose(features.doppler_centroid_hz,[1.25,.625],atol=1e-10)

    def test_random_selection_is_feasible_for_every_seed(self):
        for seed in range(100):
            starts=select_run_start_offsets([VisibilityWindow(0,100)],10,8,random=True,seed=seed)
            self.assertEqual(len(starts),8)
            self.assertTrue(np.all(np.diff(starts)>=10-1e-10))
            self.assertTrue(starts[0]>=0 and starts[-1]+10<=100)

    def test_exact_fit_window_is_usable(self):
        for random in (False,True):
            np.testing.assert_array_equal(select_run_start_offsets([VisibilityWindow(0,10)],10,1,random=random),[0])

    def test_raw_echo_includes_doppler_stretched_tail(self):
        wave=dict(type='chirp_pulse_train',prf_hz=10,pulse_width_s=.01,bandwidth_hz=1000,
                  fast_sample_rate_hz=1e6,baseband_convention='centered')
        epoch='2026-01-01T00:00:00Z'
        schedule=build_transmit_schedule(epoch,[dict(tx_start_utc=epoch,tx_duration_s=.011)],wave,'monostatic_switching')
        station=StaticState(np.zeros(3))
        target=LinearState(np.array([10*C,0,0]),np.array([30000,0,0]))
        g=propagate_from_transmit_epochs(schedule.emit_elapsed_s,station,station,target)
        p=plan_reception(schedule,g,wave,dict(fast_sample_rate_hz=1e6),
                         dict(mode='monostatic_switching'),target_extent_path_m=300)
        o=SimpleNamespace(reference_time_utc=epoch,tx_icrs=g.tx_los_icrs,rx_icrs=g.rx_los_icrs,
            receive_elapsed_s=g.receive_elapsed_s,scatter_elapsed_s=g.scatter_elapsed_s,
            emit_elapsed_s=g.emit_elapsed_s,tx_range_m=g.tx_range_m,rx_range_m=g.rx_range_m,
            acquisition_id=schedule.run_id,run_id=schedule.run_id,track_id=schedule.track_id,
            coherence_id=schedule.coherence_id,time_axis_role='pulse_centroid_receive',
            common_path_rate_m_s=g.common_path_rate_m_s,scatter_receive_rate=g.scatter_receive_rate,
            metadata=dict(fast_sample_rate_hz=1e6,fast_sample_count=p.fast_sample_count,prf_hz=10.0,
                          pulse_width_s=.01,target_extent_path_m=300),**vars(p))
        mesh=SurfaceMesh.from_tensors([[-1,-1,0],[-1,1,0],[2,0,0]],[[0,1,2]])
        cfg=dict(waveform=wave,radar=dict(carrier_frequency_hz=1e6),scattering_power=[1,1],
            model_path='analytic',observation_info_path='analytic',target=dict(rotation_period_s=300),seed=0,snr_db=None,
            echo_output_reference='raw_baseband')
        echo=_generate_chirp_echo(cfg,mesh,Spin(300,np.array([1.,0,0])),o)
        self.assertEqual(echo.metadata["prf_hz"], 10.0)
        dt=echo.fast_time_s+p.row_fast_time_offset_s[0]
        scale=1-g.common_path_rate_m_s[0]/C
        tail=(dt>.01)&(dt*scale<.01)
        self.assertTrue(np.any(tail))
        self.assertTrue(np.all(abs(echo.clean_iq[0,tail])>.9))
        self.assertTrue(np.all(echo.valid[0,tail]))

    def test_float32_cw_still_runs_through_real_generator(self):
        folder = Path(__file__).resolve().parents[1] / ".tmp_physics_float32_cw"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            model = folder / 'facet.obj'
            geometry = folder / 'geometry.npz'
            model.write_text('v -1 -1 0\nv -1 1 0\nv 2 0 0\nf 1 2 3\n', encoding='utf-8')
            times = np.arange(20) * .01
            los = np.tile([1., 0, 0], (20, 1))
            np.savez(geometry, start_utc='2026-01-01T00:00:00Z', elapsed_s=times,
                     scatter_elapsed_s=times - 1, emit_elapsed_s=times - 2,
                     tx_los_icrs=los, rx_los_icrs=los, tx_range_m=np.full(20, C), rx_range_m=np.full(20, C))
            config = dict(model_path=str(model), observation_info_path=str(geometry), compute=dict(device='cpu', dtype='float32'),
                target=dict(rotation_period_s=300, initial_phase_deg=0, spin_pole_icrs_deg=[0, 0]),
                radar=dict(carrier_frequency_hz=1e6), waveform=dict(type='continuous_wave'),
                scattering_spot=dict(enabled=False), scattering_power=[1, 1], snr_db=None, seed=0)
            result = generate_echo(config)
            self.assertEqual(result.clean_iq.shape, (20,))
            self.assertTrue(np.all(np.isfinite(result.clean_iq)))
            self.assertTrue(np.any(abs(result.clean_iq) > 0))
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__=='__main__': unittest.main()
