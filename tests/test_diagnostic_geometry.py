import unittest
from types import SimpleNamespace
import numpy as np
from inversion.src.result_views import processing_figure,matrix_figure


class DiagnosticGeometryTests(unittest.TestCase):
    def arrays(self,count=1):
        delays=np.arange(200)*1e-9
        profiles=np.zeros((count,200));profiles[:,30:40]=np.linspace(1,4,10)
        return dict(times_s=np.arange(count,dtype=float)+47091,delays_s=delays,range_time_power=profiles,
            rd_power=np.repeat(profiles[:,:,None],8,axis=2),rd_frequencies_hz=np.tile(np.arange(8)-4,(count,1)),
            rd_times_s=np.arange(count)+47091,cpi_start_pulse=np.arange(count)*25,cpi_end_pulse=np.arange(count)*25+100)

    def test_single_cpi_is_a_profile_not_a_stretched_heatmap(self):
        fig=processing_figure(self.arrays())
        self.assertEqual(fig.data[0].type,'scatter')
        np.testing.assert_allclose(fig.data[0].y,self.arrays()['delays_s']*1e9)
        self.assertEqual(fig.layout.hovermode,'closest')
        self.assertNotIn('诊断帧',fig.layout.xaxis.title.text)

    def test_rd_default_focus_explicitly_applies_to_both_panels(self):
        fig=processing_figure(self.arrays())
        self.assertEqual(list(fig.layout.yaxis.range),list(fig.layout.yaxis2.range))
        self.assertFalse(fig.layout.yaxis.autorange)
        self.assertFalse(fig.layout.yaxis2.autorange)
        self.assertLess(fig.layout.yaxis2.range[1]-fig.layout.yaxis2.range[0],100)

    def test_run_toggle_shares_the_view_control_group(self):
        n=4;echo=SimpleNamespace(iq=np.ones((n,12)),valid=np.ones((n,12),bool),
            fast_time_s=np.arange(12)*1e-9,scatter_elapsed_s=np.arange(n),elapsed_s=np.arange(n),run_id=np.array([0,0,1,1]))
        fig=matrix_figure(echo,echo.iq,'raw',-1,{})
        menus=list(fig.layout.updatemenus)
        toggle=next(m for m in menus if any(b.label=='显示/隐藏Run分隔线' for b in m.buttons))
        self.assertEqual(len(menus),1)
        self.assertEqual(toggle.x,0)
        self.assertEqual(toggle.xanchor,'left')
        self.assertTrue(any(b.label=='信号范围' for b in toggle.buttons))

    def test_multi_frame_still_preserves_actual_frame_columns(self):
        arrays=self.arrays(3);fig=processing_figure(arrays)
        self.assertEqual(fig.data[0].type,'heatmap')
        self.assertEqual(np.asarray(fig.data[0].z).shape,(200,3))
        self.assertEqual(len(np.unique(np.asarray(fig.data[0].customdata))),3)

    def test_single_pulse_fallback_does_not_claim_cpi_or_doppler_sum(self):
        arrays=self.arrays()
        arrays={k:arrays[k] for k in ('times_s','delays_s','range_time_power')}
        fig=processing_figure(arrays)
        self.assertEqual(fig.data[0].type,'scatter')
        self.assertIn('未作慢时间FFT',fig.layout.annotations[0].text)
        self.assertNotIn('所选CPI',fig.layout.xaxis.title.text)
        self.assertNotIn('沿多普勒求和',fig.layout.annotations[0].text)
