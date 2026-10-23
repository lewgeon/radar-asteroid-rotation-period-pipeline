import json
import unittest
import numpy as np
import torch
from echo.src.motion import Spin, spin_axis_from_config
from scripts import experiment_half_period_diagnosis as exp


class HalfPeriodDiagnosisTests(unittest.TestCase):
    def test_half_period_phase_sign_matches_forward_body_rotation(self):
        target={'spin_pole_frame':'equatorial','spin_pole_icrs_deg':[105.,-66.]}
        t=np.array([0.,300.,1000.,17000.,32000.])
        tx=np.column_stack([np.cos(.2+2e-7*t),np.sin(.2+2e-7*t),np.full(len(t),.4)])
        tx=tx/np.linalg.norm(tx,axis=1)[:,None]
        longitude=exp.look_longitude(tx,tx,target)
        spin=Spin(10800.,spin_axis_from_config(target))
        body=spin.rotate_inverse(torch.tensor(2*tx),t).numpy()
        body_phase=2*np.arctan2(body[:,1],body[:,0])
        expected=-2*spin.rate*(t-t[0])+2*longitude
        np.testing.assert_allclose(np.exp(1j*(body_phase-body_phase[0])),
            np.exp(1j*expected),atol=2e-14,rtol=0)

    def test_geometry_phase_correction_recovers_inertial_half_period(self):
        # A moving look longitude causes a known apparent-period displacement.
        t=np.linspace(0,32000,501)
        rate=3e-7
        longitude=rate*t
        y=2+np.cos(2*np.pi*t/5400-2*longitude)
        cfg={'period_min_s':1800,'period_max_s':14400,'period_grid_size':500}
        plain=exp.phase_search(t,y,np.zeros(len(t)),1,cfg)
        corrected=exp.phase_search(t,y,-2*longitude,1,cfg)
        expected=1/(1/5400-rate/np.pi)
        self.assertAlmostEqual(plain['base_period_s'],expected,places=3)
        self.assertGreater(abs(plain['base_period_s']-5400),2)
        self.assertLess(abs(corrected['base_period_s']-5400),1e-3)

    def test_phase_design_matches_independent_trigonometric_values(self):
        t=np.array([4.,11.,17.,34.])
        offset=np.array([0.,.03,.04,.08])
        x=exp.phase_design(t,23.,2,offset)
        phase=2*np.pi*(t-4)/23+offset
        expected=np.array([[1,np.cos(p),np.sin(p),np.cos(2*p),np.sin(2*p)] for p in phase])
        np.testing.assert_allclose(x,expected,rtol=0,atol=1e-15)

    def test_control_changes_only_requested_arrays_and_preserves_input(self):
        base={'elapsed_s':np.array([10.,20.,30.]),'scatter_elapsed_s':np.array([9.,19.,29.]),
            'tx_los_icrs':np.eye(3),'rx_los_icrs':np.eye(3),
            'row_start_sample':np.zeros(3,dtype=int),
            'row_fast_time_offset_s':np.array([-.1,-.12,-.14]),
            'centroid_fractional_offset_s':np.array([.01,.02,.03]),
            'rx_adc_start_elapsed_s':np.array([9.9,19.88,29.86]),
            'rx_adc_stop_elapsed_s':np.array([10.9,20.88,30.86]),
            'metadata_json':np.array(json.dumps({'fast_sample_rate_hz':100.}))}
        copied={k:v.copy() for k,v in base.items()}
        fixed=exp.controlled_observation(base,fixed_los=True)
        np.testing.assert_array_equal(fixed['tx_los_icrs'],np.repeat(base['tx_los_icrs'][:1],3,axis=0))
        for key in base:
            np.testing.assert_array_equal(base[key],copied[key])
            if key not in ['tx_los_icrs','rx_los_icrs']:
                np.testing.assert_array_equal(fixed[key],base[key])
        adc=exp.controlled_observation(fixed,fixed_adc=True)
        np.testing.assert_allclose(adc['row_fast_time_offset_s'],-.1,atol=1e-14)
        np.testing.assert_allclose(adc['rx_adc_stop_elapsed_s']-adc['rx_adc_start_elapsed_s'],1.)
        np.testing.assert_array_equal(adc['scatter_elapsed_s'],base['scatter_elapsed_s'])

    def test_already_fixed_adc_control_is_a_duplicate_not_a_new_branch(self):
        base={'elapsed_s':np.array([10.,20.,30.]),
            'row_start_sample':np.zeros(3,dtype=int),
            'row_fast_time_offset_s':np.full(3,-.125),
            'centroid_fractional_offset_s':np.zeros(3),
            'rx_adc_start_elapsed_s':np.array([9.875,19.875,29.875]),
            'rx_adc_stop_elapsed_s':np.array([10.875,20.875,30.875]),
            'metadata_json':np.array(json.dumps({'fast_sample_rate_hz':100.}))}
        fixed=exp.controlled_observation(base,fixed_adc=True)
        for key in base:
            np.testing.assert_array_equal(fixed[key],base[key])


if __name__=='__main__':
    unittest.main()
