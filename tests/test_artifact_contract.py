import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np

import pipeline
from tests.scratch import scratch_directory


ROOT = Path(__file__).resolve().parents[1]


def _write_observation(path: Path, *, pulses=2, width=4, revision=1):
    np.savez(
        path,
        valid_plan=np.ones((pulses, width), dtype=bool),
        row_start_sample=np.arange(pulses, dtype=np.int64),
        metadata_json=json.dumps(
            {
                "data_layout": "pulse_adc_windows",
                "fast_sample_count": width,
                "fast_sample_rate_hz": 10.0,
                "test_revision": revision,
            }
        ),
    )


def _write_echo(path: Path, observation_path: Path, *, pulses=2, width=4):
    np.savez(
        path,
        iq=np.zeros((pulses, width), dtype=np.complex64),
        fast_time_s=np.arange(width, dtype=float) / 10.0,
        row_start_sample=np.arange(pulses, dtype=np.int64),
        metadata_json=json.dumps(
            {
                "data_layout": "pulse_adc_windows",
                "fast_sample_count": width,
                "fast_sample_rate_hz": 10.0,
                "observation_info_sha256": hashlib.sha256(
                    observation_path.read_bytes()
                ).hexdigest(),
            }
        ),
    )


class ArtifactContractTests(unittest.TestCase):
    def test_matching_chirp_pair_is_accepted(self):
        with scratch_directory("artifact_pair_ok") as directory:
            observation = directory / "observation_info.npz"
            echo = directory / "echo.npz"
            _write_observation(observation, width=4)
            _write_echo(echo, observation, width=4)

            result = pipeline.validate_observation_echo_contract(observation, echo)

        self.assertEqual(result["layout"], "chirp")
        self.assertEqual(result["fast_sample_count"], 4)

    def test_stale_chirp_width_is_rejected(self):
        with scratch_directory("artifact_pair_width") as directory:
            observation = directory / "observation_info.npz"
            echo = directory / "echo.npz"
            _write_observation(observation, width=252)
            _write_echo(echo, observation, width=251)
            with self.assertRaisesRegex(ValueError, "观测计划为 252 列，回波为 251 列"):
                pipeline.validate_observation_echo_contract(observation, echo)

    def test_same_shape_but_different_observation_hash_is_rejected(self):
        with scratch_directory("artifact_pair_hash") as directory:
            observation = directory / "observation_info.npz"
            echo = directory / "echo.npz"
            _write_observation(observation, width=4, revision=1)
            _write_echo(echo, observation, width=4)
            _write_observation(observation, width=4, revision=2)
            with self.assertRaisesRegex(ValueError, "observation_info_sha256"):
                pipeline.validate_observation_echo_contract(observation, echo)

    def test_fractional_fast_sample_metadata_is_rejected(self):
        with scratch_directory("artifact_fractional_count") as directory:
            observation = directory / "observation_info.npz"
            echo = directory / "echo.npz"
            _write_observation(observation, width=4)
            _write_echo(echo, observation, width=4)
            with np.load(observation, allow_pickle=False) as data:
                payload = {key: data[key] for key in data.files}
            metadata = json.loads(str(payload["metadata_json"]))
            metadata["fast_sample_count"] = 4.9
            payload["metadata_json"] = json.dumps(metadata)
            np.savez(observation, **payload)

            with self.assertRaisesRegex(ValueError, "fast_sample_count.*整数"):
                pipeline.validate_observation_echo_contract(observation, echo)

    def test_root_cli_stops_before_inversion_for_stale_chirp_pair(self):
        """Dummy unfingerprinted NPZ need --allow-legacy-reuse before the row-width contract runs."""
        with scratch_directory("artifact_pair_cli") as directory:
            run_name = "stale_pair"
            run_directory = directory / run_name
            echo_directory = run_directory / "echo"
            echo_directory.mkdir(parents=True)
            observation = run_directory / "observation_info.npz"
            echo = echo_directory / "echo.npz"
            _write_observation(observation, width=252)
            _write_echo(echo, observation, width=251)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline.py"),
                    "--config",
                    str(ROOT / "configs" / "chirp_point_target_test.json"),
                    "--runs-dir",
                    str(directory),
                    "--run-name",
                    run_name,
                    "--skip-observation",
                    "--skip-echo",
                    "--allow-legacy-reuse",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        combined_output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("上游产物不兼容", combined_output)
        self.assertIn("观测计划为 252 列，回波为 251 列", combined_output)

    def test_root_cli_rejects_unfingerprinted_artifacts_without_legacy_flag(self):
        with scratch_directory("artifact_pair_legacy") as directory:
            run_name = "legacy_pair"
            run_directory = directory / run_name
            echo_directory = run_directory / "echo"
            echo_directory.mkdir(parents=True)
            observation = run_directory / "observation_info.npz"
            echo = echo_directory / "echo.npz"
            _write_observation(observation, width=4)
            _write_echo(echo, observation, width=4)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline.py"),
                    "--config",
                    str(ROOT / "configs" / "chirp_point_target_test.json"),
                    "--runs-dir",
                    str(directory),
                    "--run-name",
                    run_name,
                    "--skip-observation",
                    "--skip-echo",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            combined_output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("无法复用观测产物", combined_output)
            self.assertIn("--allow-legacy-reuse", combined_output)
            self.assertNotIn("[inversion]", combined_output)
            self.assertFalse((run_directory / "configs" / "observation.generated.json").exists())

            prepared = pipeline.prepare_run(
                json.loads((ROOT / "configs" / "chirp_point_target_test.json").read_text(encoding="utf-8")),
                config_path=ROOT / "configs" / "chirp_point_target_test.json",
                run_dir=run_directory,
                through_stage="inversion",
            )
            blocked = pipeline.check_reusable_artifact(prepared, artifact_stage="observation")
            self.assertFalse(blocked.reusable)
            self.assertTrue(blocked.requires_confirmation)
            allowed = pipeline.check_reusable_artifact(
                prepared, artifact_stage="observation", allow_legacy=True
            )
            self.assertTrue(allowed.reusable)

            allowed_run = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline.py"),
                    "--config",
                    str(ROOT / "configs" / "chirp_point_target_test.json"),
                    "--runs-dir",
                    str(directory),
                    "--run-name",
                    run_name,
                    "--skip-observation",
                    "--skip-echo",
                    "--allow-legacy-reuse",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertFalse((run_directory / "configs" / "observation.generated.json").exists())
            self.assertFalse((run_directory / "configs" / "echo.generated.json").exists())
            self.assertTrue((run_directory / "configs" / "inversion.generated.json").exists())

            second = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline.py"),
                    "--config",
                    str(ROOT / "configs" / "chirp_point_target_test.json"),
                    "--runs-dir",
                    str(directory),
                    "--run-name",
                    run_name,
                    "--skip-observation",
                    "--skip-echo",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            second_output = second.stdout + second.stderr
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("无法复用观测产物", second_output)
            self.assertNotIn("[inversion]", second_output)

    def test_root_cli_does_not_reuse_matching_generated_without_fingerprint(self):
        with scratch_directory("artifact_generated_leftover") as directory:
            run_name = "generated_leftover"
            run_directory = directory / run_name
            echo_directory = run_directory / "echo"
            echo_directory.mkdir(parents=True)
            observation = run_directory / "observation_info.npz"
            echo = echo_directory / "echo.npz"
            _write_observation(observation, width=4)
            _write_echo(echo, observation, width=4)

            config_path = ROOT / "configs" / "chirp_point_target_test.json"
            prepared = pipeline.prepare_run(
                json.loads(config_path.read_text(encoding="utf-8")),
                config_path=config_path,
                run_dir=run_directory,
                through_stage="inversion",
            )
            config_dir = run_directory / "configs"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "observation.generated.json").write_text(
                json.dumps(prepared["observation"], ensure_ascii=False), encoding="utf-8"
            )
            (config_dir / "echo.generated.json").write_text(
                json.dumps(prepared["echo"], ensure_ascii=False), encoding="utf-8"
            )

            blocked = pipeline.check_reusable_artifact(prepared, artifact_stage="observation")
            self.assertFalse(blocked.reusable)
            self.assertTrue(blocked.requires_confirmation)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline.py"),
                    "--config",
                    str(config_path),
                    "--runs-dir",
                    str(directory),
                    "--run-name",
                    run_name,
                    "--skip-observation",
                    "--skip-echo",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            combined_output = completed.stdout + completed.stderr
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("无法复用观测产物", combined_output)
            self.assertIn("--allow-legacy-reuse", combined_output)
            self.assertNotIn("[inversion]", combined_output)


if __name__ == "__main__":
    unittest.main()
