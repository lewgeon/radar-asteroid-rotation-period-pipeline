import json
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import pipeline
from inversion.src.dataset import normalize_inversion_policy
from observation.src.config_normalize import normalize_observation_config, resolve_stations
from tests.scratch import scratch_directory


def _write_stub_observation(path: Path) -> None:
    np.savez(path, elapsed_s=np.array([0.0]), valid_plan=np.ones((1, 2), dtype=bool))


def _write_stub_echo(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, iq=np.zeros((1, 2), dtype=np.complex64))


class SchemaV4ContractTests(unittest.TestCase):
    def _base(self):
        return {
            "observation": {
                "transmitter": {"state": "static", "position_m": [0, 0, 0]},
                "transmit": {
                    "pulse_width_s": 0.001,
                    "prf_hz": 10.0,
                },
                "receiver_sampling": {
                    "fast_sample_rate_hz": 1e6,
                },
                "radar_system": {
                    "mode": "bistatic_continuous",
                    "switch_time_s": 0.0,
                    "safety_margin_s": 0.0,
                },
                "schedule": {
                    "start_utc": "2026-01-01T00:00:00Z",
                    "end_utc": "2026-01-01T00:10:00Z",
                    "selection": "manual",
                    "runs": [
                        {"tx_start_utc": "2026-01-01T00:00:00Z", "tx_duration_s": 1.0}
                    ],
                },
                "target": {"state": "static", "position_m": [1, 0, 0]},
            },
            "echo": {
                "scattering_model": "mesh",
                "model_path": "models/ellipsoid.obj",
                "compute": {"device": "cpu", "dtype": "float32"},
                "target": {
                    "rotation_period_s": 20.0,
                    "initial_phase_deg": 0.0,
                    "spin_pole_frame": "equatorial",
                    "spin_pole_icrs_deg": [0.0, 90.0],
                },
                "scattering_power": [1.0, 1.0],
                "waveform": {
                    "type": "chirp_pulse_train",
                    "bandwidth_hz": 1e5,
                    "amplitude": 1.0,
                },
                "radar": {"carrier_frequency_hz": 1e9},
                "seed": 1,
            },
            "inversion": {"cpi_duration_s": 1.0},
        }

    def test_chirp_rate_check_can_be_deferred_for_observation_generation(self):
        config = self._base()
        config["observation"]["receiver_sampling"]["fast_sample_rate_hz"] = 5_000.0
        config["echo"]["waveform"]["bandwidth_hz"] = 1_000_000.0
        with self.assertRaisesRegex(ValueError, "fast_sample_rate_hz 大于 bandwidth_hz"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="echo")
        prepared = pipeline.prepare_run(
            config, run_dir=Path("unused_run"), through_stage="observation"
        )
        self.assertEqual(prepared["observation"]["receiver_sampling"]["fast_sample_rate_hz"], 5_000.0)
        self.assertEqual(prepared["echo"]["waveform"]["bandwidth_hz"], 1_000_000.0)
        self.assertNotIn("waveform", prepared["observation"])
        self.assertEqual(prepared["observation"]["transmit"]["prf_hz"], 10.0)

    def test_observation_stage_ignores_incomplete_echo_fields(self):
        config = self._base()
        config["echo"].pop("compute")
        config["echo"].pop("model_path")
        config["echo"]["waveform"]["bandwidth_hz"] = 1_000_000.0
        config["observation"]["receiver_sampling"]["fast_sample_rate_hz"] = 5_000.0
        prepared = pipeline.prepare_run(
            config, run_dir=Path("unused_run"), through_stage="observation"
        )
        self.assertIn("output_path", prepared["observation"])
        with self.assertRaisesRegex(ValueError, r"echo\.(compute|model_path)"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="echo")

    def test_chirp_bandwidth_required_for_echo_but_not_observation(self):
        config = self._base()
        config["echo"]["waveform"].pop("bandwidth_hz")
        prepared = pipeline.prepare_run(
            config, run_dir=Path("unused_run"), through_stage="observation"
        )
        self.assertEqual(prepared["observation"]["transmit"]["prf_hz"], 10.0)
        with self.assertRaisesRegex(ValueError, "echo.waveform.bandwidth_hz"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="echo")
        with self.assertRaisesRegex(ValueError, "echo.waveform.bandwidth_hz"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="full_pipeline")

    def test_incomplete_transmit_fails_prepare_run_but_not_normalize(self):
        config = self._base()
        config["observation"]["transmit"] = {"prf_hz": 10.0}
        normalize_observation_config(config["observation"])
        with self.assertRaisesRegex(ValueError, r"observation\.transmit\.pulse_width_s"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="observation")
        config["observation"]["transmit"] = {}
        normalize_observation_config(config["observation"])
        with self.assertRaisesRegex(ValueError, r"observation\.transmit"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="echo")
        config["observation"].pop("transmit")
        normalize_observation_config(config["observation"])
        with self.assertRaisesRegex(ValueError, r"observation\.transmit"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="full_pipeline")

    def test_inversion_stage_does_not_require_chirp_execution_fields(self):
        config = self._base()
        config["echo"]["waveform"].pop("bandwidth_hz")
        config["observation"]["transmit"] = {"prf_hz": 10.0}
        pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="inversion")

    def test_observation_rejects_legacy_waveform_block(self):
        from observation.src.config_normalize import normalize_observation_config

        config = self._base()["observation"]
        config["waveform"] = {
            "type": "chirp_pulse_train",
            "prf_hz": 10.0,
            "pulse_width_s": 0.001,
        }
        with self.assertRaisesRegex(ValueError, r"observation\.waveform 已废弃"):
            normalize_observation_config(config)

    def test_observation_stage_fills_echo_type_from_event_source(self):
        config = self._base()
        config["echo"]["waveform"].pop("type", None)
        prepared = pipeline.prepare_run(
            config, run_dir=Path("unused_run"), through_stage="observation"
        )
        self.assertNotIn("waveform", prepared["observation"])
        self.assertEqual(prepared["echo"]["waveform"]["type"], "chirp_pulse_train")

    def test_echo_type_must_match_observation_event_source(self):
        config = self._base()
        config["echo"]["waveform"]["type"] = "continuous_wave"
        with self.assertRaisesRegex(ValueError, r"echo\.waveform\.type"):
            pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="echo")

        cw = self._base()
        for key in ("schedule", "radar_system", "receiver_sampling", "transmit"):
            cw["observation"].pop(key, None)
        cw["observation"]["receive"] = {
            "start_utc": "2026-01-01T00:00:00Z",
            "duration_s": 60.0,
            "sample_rate_hz": 16.0,
        }
        cw["echo"]["waveform"] = {"type": "chirp_pulse_train", "amplitude": 1.0}
        with self.assertRaisesRegex(ValueError, r"echo\.waveform\.type"):
            pipeline.prepare_run(cw, run_dir=Path("unused_run"), through_stage="echo")

    def test_prepare_run_does_not_mutate_caller_echo_type(self):
        config = self._base()
        config["echo"]["waveform"].pop("type", None)
        pipeline.prepare_run(config, run_dir=Path("unused_run"), through_stage="observation")
        self.assertNotIn("type", config["echo"]["waveform"])

    def test_cw_observation_rejects_transmit_block(self):
        from observation.src.config_normalize import normalize_observation_config

        config = {
            "transmitter": {"state": "static", "position_m": [0, 0, 0]},
            "target": {"state": "static", "position_m": [1, 0, 0]},
            "receive": {
                "start_utc": "2026-01-01T00:00:00Z",
                "duration_s": 60.0,
                "sample_rate_hz": 16.0,
            },
            "transmit": {"prf_hz": 10.0, "pulse_width_s": 0.001},
        }
        with self.assertRaisesRegex(ValueError, r"observation\.transmit"):
            normalize_observation_config(config)

    def test_missing_transmitter_is_rejected_before_runtime(self):
        from observation.src.config_normalize import normalize_observation_config

        config = self._base()["observation"]
        config.pop("transmitter")
        with self.assertRaisesRegex(ValueError, "observation 配置必须包含 transmitter"):
            normalize_observation_config(config)

    def test_mesh_echo_requires_compute(self):
        from echo.src.config_normalize import normalize_echo_config

        echo = self._base()["echo"]
        echo.pop("compute")
        with self.assertRaisesRegex(ValueError, r"echo\.compute"):
            normalize_echo_config(echo)

    def test_conflicting_duplicate_waveform_values_fail_before_pruning(self):
        config = self._base()
        config["echo"]["waveform"]["pulse_width_s"] = 0.002
        with self.assertRaisesRegex(ValueError, "waveform.pulse_width_s"):
            pipeline.normalize_config(config)

    def test_conflicting_adc_owner_fails_before_pruning(self):
        config = self._base()
        config["echo"]["waveform"]["fast_sample_rate_hz"] = 2e6
        with self.assertRaisesRegex(ValueError, "fast_sample_rate_hz"):
            pipeline.normalize_config(config)

    def test_echo_owned_timing_fields_are_rejected(self):
        config = self._base()
        config["echo"]["waveform"]["pulse_width_s"] = 0.001
        with self.assertRaisesRegex(ValueError, "pulse_width_s"):
            pipeline.normalize_config(config)

        config = self._base()
        config["echo"]["waveform"]["fast_sample_rate_hz"] = 1e6
        with self.assertRaisesRegex(ValueError, "fast_sample_rate_hz"):
            pipeline.normalize_config(config)

    def test_observation_owned_timing_fields_in_echo_are_rejected(self):
        config = self._base()
        config["echo"]["waveform"]["pulse_width_s"] = 0.001
        with self.assertRaisesRegex(ValueError, "pulse_width_s"):
            pipeline.normalize_config(config)

    def test_station_id_and_same_as_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "transmitter.id"):
            resolve_stations(
                {
                    "transmitter": {
                        "id": "site_a",
                        "state": "static",
                        "position_m": [1, 2, 3],
                    },
                    "receiver": {"same_as": "site_a"},
                }
            )

    def test_distinct_stations_are_kept(self):
        tx, rx = resolve_stations(
            {
                "transmitter": {"state": "static", "position_m": [1, 2, 3]},
                "receiver": {"state": "static", "position_m": [4, 5, 6]},
            }
        )
        self.assertEqual(tx["position_m"], [1, 2, 3])
        self.assertEqual(rx["position_m"], [4, 5, 6])

    def test_same_as_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "receiver.same_as"):
            resolve_stations(
                {
                    "transmitter": {"state": "static", "position_m": [1, 2, 3]},
                    "receiver": {"same_as": "site_b"},
                }
            )

    def test_deprecated_path_extent_key_is_rejected(self):
        config = {
            "transmitter": {"state": "static", "position_m": [0, 0, 0]},
            "receiver_sampling": {"max_bistatic_path_offset_m": 10},
            "target": {"state": "static", "position_m": [1, 0, 0]},
        }
        with self.assertRaisesRegex(ValueError, "max_bistatic_path_offset_m"):
            from observation.src.config_normalize import normalize_observation_config
            normalize_observation_config(config)

    def test_custom_cartesian_stations_reject_meaningless_visibility_fields(self):
        from observation.src.config_normalize import normalize_observation_config

        config = self._base()["observation"]
        config["visibility"] = {
            "min_tx_elevation_deg": 20.0,
            "sample_step_s": 30.0,
            "allow_unobservable_for_simulation": True,
        }
        with self.assertRaisesRegex(ValueError, "自定义直角坐标.*visibility"):
            normalize_observation_config(config)

    def test_mixed_horizon_and_cartesian_reject_rx_elevation_field(self):
        from observation.src.config_normalize import normalize_observation_config

        config = self._base()["observation"]
        config["transmitter"] = {
            "state": "astropy_geodetic",
            "lat_deg": 35.0,
            "lon_deg": -116.0,
            "height_m": 0.0,
        }
        config["receiver"] = {"state": "static", "position_m": [6_371_000.0, 0.0, 0.0]}
        config["visibility"] = {
            "sample_step_s": 10.0,
            "min_tx_elevation_deg": 0.0,
            "min_rx_elevation_deg": 20.0,
        }
        with self.assertRaisesRegex(ValueError, "visibility.min_rx_elevation_deg"):
            normalize_observation_config(config)

    def test_mixed_horizon_and_cartesian_keep_tx_visibility_fields(self):
        from observation.src.config_normalize import normalize_observation_config

        config = self._base()["observation"]
        config["transmitter"] = {
            "state": "astropy_geodetic",
            "lat_deg": 35.0,
            "lon_deg": -116.0,
            "height_m": 0.0,
        }
        config["receiver"] = {"state": "static", "position_m": [6_371_000.0, 0.0, 0.0]}
        config["visibility"] = {
            "sample_step_s": 10.0,
            "min_tx_elevation_deg": 5.0,
            "allow_unobservable_for_simulation": True,
        }
        out = normalize_observation_config(config)
        self.assertEqual(out["visibility"]["min_tx_elevation_deg"], 5.0)
        self.assertNotIn("min_rx_elevation_deg", out["visibility"])

    def test_scattering_model_rejects_irrelevant_algorithm_fields(self):
        point = self._base()
        point["echo"].update(
            {
                "scattering_model": "point_target",
                "model_path": "unused.obj",
                "target": {"rotation_period_s": 20.0},
                "scattering_power": [1.0, 1.0],
                "scattering_spot": {"enabled": True},
                "point_target": {"amplitude_scale": 2.0},
            }
        )
        with self.assertRaisesRegex(ValueError, "point_target 不接受"):
            pipeline.normalize_config(point)

        mesh = self._base()
        mesh["echo"].update(
            {
                "scattering_model": "mesh",
                "point_target": {"amplitude_scale": 2.0},
            }
        )
        with self.assertRaisesRegex(ValueError, "echo.point_target"):
            pipeline.normalize_config(mesh)

    def test_chirp_policy_preserves_physical_cpi_durations(self):
        policy = normalize_inversion_policy(
            {"cpi_duration_s": 1.25, "cpi_hop_duration_s": 0.25},
            "chirp",
        )
        self.assertEqual(policy["cpi_duration_s"], 1.25)
        self.assertEqual(policy["cpi_hop_duration_s"], 0.25)

    def test_inversion_policy_rejects_mixed_cpi_duration_and_count(self):
        with self.assertRaisesRegex(ValueError, "cpi_pulses"):
            normalize_inversion_policy(
                {"cpi_duration_s": 4.0, "cpi_pulses": 999}, "chirp"
            )
        with self.assertRaisesRegex(ValueError, "cpi_hop_pulses"):
            normalize_inversion_policy(
                {"cpi_hop_duration_s": 1.0, "cpi_hop_pulses": 777}, "chirp"
            )

    def test_cw_policy_rejects_chirp_only_fields(self):
        config = self._base()
        for key in ("schedule", "radar_system", "receiver_sampling", "transmit"):
            config["observation"].pop(key, None)
        config["observation"]["receive"] = {
            "start_utc": "2026-01-01T00:00:00Z",
            "duration_s": 60.0,
            "sample_rate_hz": 16.0,
        }
        config["echo"]["waveform"] = {"type": "continuous_wave"}
        config["inversion"].update(
            {"cpi_duration_s": 1.0, "motion_compensation": "auto"}
        )
        with self.assertRaisesRegex(ValueError, "cpi_duration_s"):
            pipeline.normalize_config(config)

    def test_canonical_repo_configs_normalize(self):
        from pathlib import Path

        from echo.src.config_normalize import normalize_echo_config
        from observation.src.config_normalize import normalize_observation_config

        root = Path(__file__).resolve().parents[1]
        for name in ("chirp_point_target_test.json", "chirp_mesh_target_test.json", "point_target_debug.json"):
            payload = pipeline.load_json(root / "configs" / name)
            normalized = pipeline.normalize_config(payload)
            self.assertEqual(set(normalized), {"observation", "echo", "inversion"})

        for name in ("example.json", "eros_goldstone_horizons.json"):
            payload = pipeline.load_json(root / "observation" / "configs" / name)
            payload.pop("output_path", None)
            normalize_observation_config(payload)

        echo_payload = pipeline.load_json(root / "echo" / "configs" / "echo.json")
        normalize_echo_config(echo_payload)
        echo_cw = pipeline.load_json(root / "echo" / "configs" / "echo_cw.json")
        normalize_echo_config(echo_cw)

    def test_deprecated_solver_block_is_rejected(self):
        from observation.src.config_normalize import normalize_observation_config

        with self.assertRaisesRegex(ValueError, "solver"):
            normalize_observation_config(
                {
                    "transmitter": {"state": "static", "position_m": [0, 0, 0]},
                    "target": {"state": "static", "position_m": [1, 0, 0]},
                    "solver": {"tolerance_s": 1e-9, "max_iter": 32},
                }
            )

    def test_pipeline_rejects_deprecated_cpi_pulse_counts(self):
        config = self._base()
        config["inversion"]["cpi_pulses"] = 64
        with self.assertRaisesRegex(ValueError, "cpi_pulses"):
            pipeline.normalize_config(config)

    def test_pipeline_rejects_deprecated_observation_keys(self):
        config = self._base()
        config["observation"]["solver"] = {"tolerance_s": 1e-9, "max_iter": 32}
        with self.assertRaisesRegex(ValueError, "solver"):
            pipeline.normalize_config(config)

        config = self._base()
        config["observation"]["campaign"] = {"query_start_utc": "2026-01-01T00:00:00Z"}
        with self.assertRaisesRegex(ValueError, "campaign"):
            pipeline.normalize_config(config)

    def test_pipeline_rejects_unknown_or_wrong_level_fields(self):
        config = self._base()
        config["echo"]["pulse_width_s"] = 0.02
        with self.assertRaisesRegex(ValueError, "echo.pulse_width_s"):
            pipeline.normalize_config(config)

        config = self._base()
        config["echo"]["waveform"]["mystery"] = 1
        with self.assertRaisesRegex(ValueError, "echo.waveform.mystery"):
            pipeline.normalize_config(config)

        config = self._base()
        config["extra_stage"] = {}
        with self.assertRaisesRegex(ValueError, "extra_stage"):
            pipeline.normalize_config(config)

    def test_observation_rejects_unknown_nested_field(self):
        from observation.src.config_normalize import normalize_observation_config

        config = self._base()["observation"]
        config["ephemeris"] = {"query_step_s": 60.0, "mystery": 1}
        with self.assertRaisesRegex(ValueError, "observation.ephemeris.mystery"):
            normalize_observation_config(config)

    def test_inversion_direct_call_rejects_count_aliases(self):
        with self.assertRaisesRegex(ValueError, "cpi_pulses"):
            normalize_inversion_policy({"cpi_pulses": 64}, "chirp")

    def test_pipeline_rejects_mixed_event_sources(self):
        config = self._base()
        config["observation"]["schedule"] = {
            "start_utc": "2026-01-01T00:00:00Z",
            "end_utc": "2026-01-01T00:10:00Z",
            "selection": "manual",
            "runs": [{"tx_start_utc": "2026-01-01T00:00:00Z", "tx_duration_s": 30.0}],
        }
        config["observation"]["radar_system"] = {
            "mode": "monostatic_switching",
            "switch_time_s": 1.0,
            "safety_margin_s": 1.0,
        }
        config["observation"]["receive"] = {
            "start_utc": "2026-01-01T00:00:00Z",
            "duration_s": 60.0,
            "sample_rate_hz": 16.0,
        }
        with self.assertRaisesRegex(ValueError, "不能同时提供"):
            pipeline.normalize_config(config)

    def test_default_cli_config_is_canonical(self):
        normalized = pipeline.normalize_config(pipeline.DEFAULT_CONFIG)
        self.assertEqual(normalized["echo"]["waveform"]["type"], "continuous_wave")
        self.assertIn("receive", normalized["observation"])
        self.assertNotIn("schedule", normalized["observation"])
        self.assertNotIn("waveform", normalized["observation"])
        self.assertNotIn("transmit", normalized["observation"])
        self.assertNotIn("cpi_duration_s", normalized["inversion"])
        with self.assertRaisesRegex(ValueError, "观测解算"):
            pipeline.canonical_pipeline_config(
                {"观测解算": {}, "回波仿真": {}, "周期反演": {}}
            )

    def test_relative_model_path_resolves_against_config_file(self):
        from echo.src.config_normalize import resolve_echo_input_paths

        config_path = Path(__file__).resolve().parents[1] / "configs" / "chirp_mesh_target_test.json"
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        resolved, warnings = resolve_echo_input_paths(payload["echo"], config_path=config_path)
        model = Path(resolved["model_path"])
        self.assertTrue(model.is_file())
        self.assertTrue(model.is_absolute())
        self.assertEqual(warnings, [])

    def test_observation_fingerprint_ignores_echo_edits(self):
        config = self._base()
        run_dir = Path("unused_run")
        first = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
        config["echo"]["radar"]["carrier_frequency_hz"] = 2.0e9
        second = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
        self.assertEqual(first["observation_fingerprint"], second["observation_fingerprint"])
        config["observation"]["transmit"]["prf_hz"] = 11.0
        third = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
        self.assertNotEqual(first["observation_fingerprint"], third["observation_fingerprint"])

    def test_matching_generated_json_is_not_reuse_evidence(self):
        config = self._base()
        with scratch_directory("reuse_generated_leftover") as tmp:
            run_dir = Path(tmp)
            echo_dir = run_dir / "echo"
            echo_dir.mkdir()
            _write_stub_observation(run_dir / "observation_info.npz")
            _write_stub_echo(echo_dir / "echo.npz")
            prepared = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
            config_dir = run_dir / "configs"
            config_dir.mkdir()
            (config_dir / "echo.generated.json").write_text(
                json.dumps(prepared["echo"], ensure_ascii=False), encoding="utf-8"
            )
            (config_dir / "observation.generated.json").write_text(
                json.dumps(prepared["observation"], ensure_ascii=False), encoding="utf-8"
            )
            echo_decision = pipeline.check_reusable_artifact(prepared, artifact_stage="echo")
            self.assertFalse(echo_decision.reusable)
            self.assertTrue(echo_decision.requires_confirmation)
            self.assertNotIn("复用已有回波数据", echo_decision.reason)
            observation_decision = pipeline.check_reusable_artifact(
                prepared, artifact_stage="observation"
            )
            self.assertFalse(observation_decision.reusable)
            self.assertTrue(observation_decision.requires_confirmation)
            allowed = pipeline.check_reusable_artifact(
                prepared, artifact_stage="echo", allow_legacy=True
            )
            self.assertTrue(allowed.reusable)

    def test_recorded_fingerprint_without_current_fingerprint_is_hard_block(self):
        config = self._base()
        with scratch_directory("reuse_current_fp_missing") as tmp:
            run_dir = Path(tmp)
            _write_stub_observation(run_dir / "observation_info.npz")
            _write_stub_echo(run_dir / "echo" / "echo.npz")
            prepared = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
            observation_sha = pipeline.file_sha256(prepared["observation_output"])
            echo_proj = pipeline.echo_dependency_projection(
                prepared["echo"], observation_sha, config_path=None
            )
            pipeline.write_stage_success(
                run_dir,
                "echo",
                fingerprint=prepared["echo_fingerprint"],
                projection=echo_proj,
                output_path=run_dir / "echo" / "echo.npz",
            )
            prepared["echo_fingerprint"] = None
            decision = pipeline.check_reusable_artifact(prepared, artifact_stage="echo")
            self.assertFalse(decision.reusable)
            self.assertFalse(decision.requires_confirmation)
            self.assertIn("无法计算", decision.reason)
            allowed = pipeline.check_reusable_artifact(
                prepared, artifact_stage="echo", allow_legacy=True
            )
            self.assertFalse(allowed.reusable)

    def test_matching_fingerprint_without_output_hash_is_not_silent_reuse(self):
        config = self._base()
        with scratch_directory("reuse_missing_hash") as tmp:
            run_dir = Path(tmp)
            echo = run_dir / "echo" / "echo.npz"
            _write_stub_observation(run_dir / "observation_info.npz")
            _write_stub_echo(echo)
            prepared = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
            pipeline.write_json(
                run_dir / pipeline.STAGE_MANIFEST_NAME,
                {
                    "echo": {
                        "fingerprint": prepared["echo_fingerprint"],
                        "projection": {},
                    }
                },
            )
            decision = pipeline.check_reusable_artifact(prepared, artifact_stage="echo")
            self.assertFalse(decision.reusable)
            self.assertTrue(decision.requires_confirmation)
            self.assertIn("缺少文件哈希", decision.reason)
            allowed = pipeline.check_reusable_artifact(
                prepared, artifact_stage="echo", allow_legacy=True
            )
            self.assertTrue(allowed.reusable)

    def test_inversion_stage_reuses_echo_after_echo_stage_manifest(self):
        config_path = Path(__file__).resolve().parents[1] / "configs" / "chirp_mesh_target_test.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        with scratch_directory("reuse_echo_manifest") as tmp:
            run_dir = Path(tmp)
            (run_dir / "echo").mkdir()
            _write_stub_observation(run_dir / "observation_info.npz")
            _write_stub_echo(run_dir / "echo" / "echo.npz")
            echo_prepared = pipeline.prepare_run(
                config,
                config_path=config_path,
                run_dir=run_dir,
                through_stage="echo",
            )
            observation_sha = pipeline.file_sha256(echo_prepared["observation_output"])
            echo_proj = pipeline.echo_dependency_projection(
                echo_prepared["echo"],
                observation_sha,
                config_path=config_path,
            )
            pipeline.write_stage_success(
                run_dir,
                "echo",
                fingerprint=echo_prepared["echo_fingerprint"],
                projection=echo_proj,
                output_path=run_dir / "echo" / "echo.npz",
            )
            inversion_prepared = pipeline.prepare_run(
                config,
                config_path=config_path,
                run_dir=run_dir,
                through_stage="inversion",
            )
            self.assertEqual(
                echo_prepared["echo_fingerprint"],
                inversion_prepared["echo_fingerprint"],
            )
            self.assertTrue(Path(echo_prepared["echo"]["model_path"]).is_absolute())
            self.assertTrue(Path(inversion_prepared["echo"]["model_path"]).is_absolute())
            decision = pipeline.check_reusable_artifact(
                inversion_prepared, artifact_stage="echo"
            )
            self.assertTrue(decision.reusable, decision.reason)

    def test_missing_echo_fingerprint_does_not_reuse_on_hash_match(self):
        config = self._base()
        with scratch_directory("reuse_missing_fp") as tmp:
            run_dir = Path(tmp)
            echo_dir = run_dir / "echo"
            echo_dir.mkdir()
            echo = echo_dir / "echo.npz"
            _write_stub_observation(run_dir / "observation_info.npz")
            _write_stub_echo(echo)
            prepared = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
            prepared["echo_fingerprint"] = None
            pipeline.write_json(
                run_dir / pipeline.STAGE_MANIFEST_NAME,
                {
                    "echo": {
                        "fingerprint": None,
                        "output_sha256": pipeline.file_sha256(echo),
                    }
                },
            )
            decision = pipeline.check_reusable_artifact(prepared, artifact_stage="echo")
            self.assertFalse(decision.reusable)
            self.assertTrue(decision.requires_confirmation)
            allowed = pipeline.check_reusable_artifact(
                prepared, artifact_stage="echo", allow_legacy=True
            )
            self.assertTrue(allowed.reusable)

    def test_empty_artifact_is_not_recorded_as_success(self):
        with scratch_directory("empty_artifact") as tmp:
            run_dir = Path(tmp)
            empty = run_dir / "observation_info.npz"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "观测产物为空"):
                pipeline.write_stage_success(
                    run_dir,
                    "observation",
                    fingerprint="deadbeef",
                    projection={"observation": {}},
                    output_path=empty,
                )
            self.assertFalse((run_dir / pipeline.STAGE_MANIFEST_NAME).exists())
            config = self._base()
            _write_stub_echo(run_dir / "echo" / "echo.npz")
            prepared = pipeline.prepare_run(config, run_dir=run_dir, through_stage="echo")
            decision = pipeline.check_reusable_artifact(prepared, artifact_stage="observation")
            self.assertFalse(decision.reusable)
            self.assertIn("为空", decision.reason)
            still_blocked = pipeline.check_reusable_artifact(
                prepared, artifact_stage="observation", allow_legacy=True
            )
            self.assertFalse(still_blocked.reusable)
            missing_keys = run_dir / "observation_missing.npz"
            np.savez(missing_keys, junk=np.array([1.0]))
            with self.assertRaisesRegex(ValueError, "elapsed_s 或 valid_plan"):
                pipeline.require_stage_artifact(missing_keys, "observation")
            echo_missing = run_dir / "echo_missing.npz"
            np.savez(echo_missing, junk=np.array([1.0]))
            with self.assertRaisesRegex(ValueError, "缺少 iq"):
                pipeline.require_stage_artifact(echo_missing, "echo")

    def test_identical_receiver_does_not_change_observation_fingerprint(self):
        config = self._base()
        omitted = pipeline.prepare_run(
            config, run_dir=Path("unused_run"), through_stage="echo"
        )
        config["observation"]["receiver"] = dict(config["observation"]["transmitter"])
        config["observation"]["receiver"]["name"] = "copy"
        explicit = pipeline.prepare_run(
            config, run_dir=Path("unused_run"), through_stage="echo"
        )
        self.assertEqual(
            omitted["observation_fingerprint"],
            explicit["observation_fingerprint"],
        )

    def test_atomic_json_keeps_previous_file_if_replace_fails(self):
        with scratch_directory("atomic_json") as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"ok": true}', encoding="utf-8")
            with mock.patch("os.replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    pipeline.write_json(path, {"ok": False})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"ok": True})


if __name__ == "__main__":
    unittest.main()
