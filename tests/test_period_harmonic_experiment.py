"""Independent checks of the experiment's predictions and leakage controls."""
import unittest
import numpy as np

from scripts import experiment_period_harmonics as exp


class HarmonicExperimentTests(unittest.TestCase):
    def test_prediction_matches_raw_independent_least_squares(self):
        t = np.array([0., .5, 1., 2., 3., 5., 7., 9., 12., 16., 21., 27.])
        y = 3+np.cos(2*np.pi*t/7)+.4*np.sin(4*np.pi*t/7)
        test_t = np.array([.7, 4., 17.])
        columns = lambda x: np.column_stack([np.ones(len(x)),np.cos(2*np.pi*x/7),
            np.sin(2*np.pi*x/7),np.cos(4*np.pi*x/7),np.sin(4*np.pi*x/7)])
        beta = np.linalg.lstsq(columns(t), y, rcond=None)[0]
        model = exp.fit_model(t,y,7.,2)
        np.testing.assert_allclose(exp.predict(model,test_t),columns(test_t)@beta,atol=1e-12)

    def test_blocked_folds_never_split_runs_or_reuse_test_samples(self):
        groups = np.repeat([17,4,21,1,50,9,7,5,44,2],3)
        coverage = np.zeros(len(groups),dtype=int)
        for train,test in exp.blocked_folds(groups):
            self.assertFalse(np.any(train & test))
            self.assertFalse(set(groups[train]) & set(groups[test]))
            indexes = np.flatnonzero(test)
            self.assertTrue(np.all(np.diff(indexes)==1))
            coverage += test
        np.testing.assert_array_equal(coverage,1)

    def test_heldout_values_cannot_change_training_search_or_model(self):
        t = np.linspace(0.,120.,100)
        y = 3+np.cos(2*np.pi*t/23.)
        train,test = next(exp.blocked_folds(np.arange(len(t))))
        config = {"period_min_s":15.,"period_max_s":35.,"period_grid_size":60}
        first = exp.validation_record(t,y,train,test,1,config)
        modified = y.copy()
        modified[test] += 100*np.sin(t[test])
        second = exp.validation_record(t,modified,train,test,1,config)
        self.assertEqual(first["base_period_s"],second["base_period_s"])
        self.assertEqual(first["model"],second["model"])
        self.assertGreater(second["test_sse"],first["test_sse"]+100)

    def test_fixture_distinguishes_all_three_harmonic_orders(self):
        t = np.linspace(0.,210.,211)
        y = np.cos(2*np.pi*t/30)+.35*np.sin(4*np.pi*t/30)+.15*np.cos(6*np.pi*t/30)
        errors = []
        for h in (1,2,3):
            fit = exp.predict(exp.fit_model(t,y,30.,h),t)
            errors.append(float(np.mean((y-fit)**2)))
        self.assertGreater(errors[0]-errors[1],.05)
        self.assertGreater(errors[1]-errors[2],.01)
        self.assertLess(errors[2],1e-25)


if __name__ == "__main__":
    unittest.main()
