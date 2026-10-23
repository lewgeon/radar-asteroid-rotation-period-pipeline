"""Local artifact reuse must not scan signal content or materialize big arrays."""
import copy
import hashlib
import json
import os
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import pipeline
from tests.scratch import scratch_directory
from tests.test_artifact_contract import _write_observation, _write_echo


class ArtifactIdentityTests(unittest.TestCase):
    def fixture(self, directory):
        config = copy.deepcopy(pipeline.DEFAULT_CONFIG)
        observation = directory / 'observation_info.npz'
        echo = directory / 'echo/echo.npz'
        echo.parent.mkdir()
        _write_observation(observation)
        _write_echo(echo, observation)
        prepared = pipeline.prepare_run(config, run_dir=directory, through_stage='echo')
        projection = pipeline.echo_dependency_projection(prepared['echo'], pipeline.artifact_identity(observation))
        pipeline.write_stage_success(directory, 'echo', fingerprint=prepared['echo_fingerprint'],
                                     projection=projection, output_path=echo)
        return config, observation, echo, prepared

    def test_prepare_reuse_write_and_contract_never_hash_files(self):
        with scratch_directory('identity_no_hash') as directory:
            with patch.object(pipeline, 'file_sha256', side_effect=AssertionError('content scan')):
                config, observation, echo, prepared = self.fixture(directory)
                self.assertTrue(pipeline.check_reusable_artifact(prepared, artifact_stage='echo').reusable)
                original = np.lib.npyio.NpzFile.__getitem__
                def guarded(data, key):
                    if key in ('iq', 'valid_plan'):
                        raise AssertionError('signal array materialized')
                    return original(data, key)
                with patch.object(np.lib.npyio.NpzFile, '__getitem__', guarded):
                    pipeline.validate_observation_echo_contract(observation, echo)

    def test_identity_and_parameter_changes_invalidate_reuse(self):
        with scratch_directory('identity_change') as directory:
            config, observation, echo, prepared = self.fixture(directory)
            self.assertTrue(pipeline.check_reusable_artifact(prepared, artifact_stage='echo').reusable)
            previous = echo.stat()
            os.utime(echo, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1000000))
            self.assertFalse(pipeline.check_reusable_artifact(prepared, artifact_stage='echo').reusable)
            os.utime(echo, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            # Inversion policy does not change the producer's echo parameters.
            config['inversion']['period_grid_size'] += 1
            fresh = pipeline.prepare_run(config, run_dir=directory, through_stage='inversion')
            self.assertTrue(pipeline.check_reusable_artifact(fresh, artifact_stage='echo').reusable)
            config['echo']['seed'] += 1
            fresh = pipeline.prepare_run(config, run_dir=directory, through_stage='echo')
            self.assertFalse(pipeline.check_reusable_artifact(fresh, artifact_stage='echo').reusable)

    def test_v42_echo_metadata_works_with_root_identity_manifest_without_hashing(self):
        """4.2 producer metadata and root reuse bookkeeping are independent."""
        with scratch_directory('identity_v42_producer') as directory:
            config, observation, echo, prepared = self.fixture(directory)
            with np.load(echo, allow_pickle=False) as stored:
                payload = {key: stored[key] for key in stored.files}
            metadata = json.loads(str(payload['metadata_json']))
            metadata.pop('observation_info_identity')
            metadata['artifact_contract_version'] = 1
            metadata['observation_info_sha256'] = hashlib.sha256(observation.read_bytes()).hexdigest()
            self.assertNotIn('observation_info_identity', metadata)
            self.assertEqual(len(metadata['observation_info_sha256']), 64)
            payload['metadata_json'] = json.dumps(metadata)
            np.savez(echo, **payload)
            with patch.object(pipeline, 'file_sha256', side_effect=AssertionError('content scan')):
                self.assertEqual(pipeline.validate_observation_echo_contract(observation, echo)['layout'], 'chirp')
                pipeline.write_stage_success(directory, 'echo', fingerprint=prepared['echo_fingerprint'],
                    projection=pipeline.echo_dependency_projection(prepared['echo'], pipeline.artifact_identity(observation)),
                    output_path=echo)
                self.assertTrue(pipeline.check_reusable_artifact(prepared, artifact_stage='echo').reusable)
                original = observation.stat()
                os.utime(observation, ns=(original.st_atime_ns, original.st_mtime_ns + 1000000))
                refreshed = pipeline.prepare_run(config, run_dir=directory, through_stage='echo')
                self.assertFalse(pipeline.check_reusable_artifact(refreshed, artifact_stage='echo').reusable)
                os.utime(observation, ns=(original.st_atime_ns, original.st_mtime_ns))
                config['echo']['seed'] += 1
                changed = pipeline.prepare_run(config, run_dir=directory, through_stage='echo')
                self.assertFalse(pipeline.check_reusable_artifact(changed, artifact_stage='echo').reusable)

    def test_legacy_hash_is_not_validated_but_saved_parameters_are(self):
        with scratch_directory('identity_legacy') as directory:
            config, observation, echo, prepared = self.fixture(directory)
            projection = pipeline.echo_dependency_projection(prepared['echo'], None)
            projection.pop('observation_info_identity')
            projection['observation_info_sha256'] = 'ignored old digest'
            pipeline.write_json(directory / pipeline.STAGE_MANIFEST_NAME,
                                {'echo': {'fingerprint': 'old', 'projection': projection,
                                          'output_sha256': 'ignored old digest'}})
            self.assertTrue(pipeline.check_reusable_artifact(prepared, artifact_stage='echo').reusable)
            config['echo']['seed'] += 1
            fresh = pipeline.prepare_run(config, run_dir=directory, through_stage='echo')
            self.assertFalse(pipeline.check_reusable_artifact(fresh, artifact_stage='echo').reusable)

    def test_upstream_success_invalidates_downstream_records(self):
        with scratch_directory('identity_upstream') as directory:
            config, observation, echo, prepared = self.fixture(directory)
            pipeline.write_json(directory / pipeline.STAGE_MANIFEST_NAME,
                                {'echo': {'fingerprint': 'old'}, 'inversion': {'fingerprint': 'old'}})
            manifest = pipeline.write_stage_success(directory, 'observation',
                fingerprint=prepared['observation_fingerprint'],
                projection=pipeline.observation_dependency_projection(prepared['observation']),
                output_path=observation)
            self.assertEqual(manifest['echo']['invalidated_by'], 'observation')
            self.assertEqual(manifest['inversion']['invalidated_by'], 'observation')
            self.assertFalse(pipeline.check_reusable_artifact(prepared, artifact_stage='echo',
                                                             allow_legacy=True).reusable)

    def test_old_echo_cannot_bind_to_new_upstream_record(self):
        with scratch_directory('identity_legacy_upstream') as directory:
            config, observation, echo, prepared = self.fixture(directory)
            old = pipeline.echo_dependency_projection(prepared['echo'], None)
            old.pop('observation_info_identity')
            old['observation_info_sha256'] = 'ignored'
            recorded = {'fingerprint': 'old', 'projection': old, 'created_utc': '2026-10-12T01:00:00Z'}
            pipeline.write_json(directory / pipeline.STAGE_MANIFEST_NAME,
                {'observation': {'fingerprint': prepared['observation_fingerprint'],
                                 'created_utc': '2026-10-12T02:00:00Z'}})
            self.assertFalse(pipeline.stage_record_matches(prepared, 'echo', recorded))

    def test_gui_does_not_reclassify_invalidated_echo_as_untracked(self):
        from rotation_gui import storage
        from rotation_gui.qt_compat import QApplication
        from rotation_gui.window.main import PipelineWindow
        app = QApplication.instance() or QApplication([])
        with scratch_directory('identity_gui_stale') as directory:
            config, observation, echo, prepared = self.fixture(directory)
            pipeline.write_stage_success(directory, 'observation',
                fingerprint=prepared['observation_fingerprint'],
                projection=pipeline.observation_dependency_projection(prepared['observation']),
                output_path=observation)
            def session(window):
                window._startup_notes = []
                return directory / 'config.json', config, {'run_name': directory.name,
                                                            'runs_dir': str(directory.parent)}
            with patch.object(PipelineWindow, '_load_initial_session', session), \
                 patch.object(storage, 'STATE_PATH', directory / 'session.json'), \
                 patch.object(pipeline, 'file_sha256', side_effect=AssertionError('content scan')):
                window = PipelineWindow()
                try:
                    app.processEvents()
                    window._refresh_saved_run_status(overwrite_errors=True)
                    self.assertEqual(window.stage_status['echo'], window.STALE_STATUS)
                    window._select_stage('inversion')
                    self.assertEqual(window.stage_status['echo'], window.STALE_STATUS)
                finally:
                    window.close()
                    window.deleteLater()
                    app.processEvents()
