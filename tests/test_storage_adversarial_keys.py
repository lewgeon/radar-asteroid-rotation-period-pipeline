"""Adversarial cache metadata cases: invalid products must be cache misses."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from inversion.src import processing_store as store
from tests.test_gui_schema_v4 import _workspace_tmp


@pytest.mark.parametrize('key', [None, [], {'version': 3, 'policy': None},
    {'version': 3, 'policy': {'compute_execution': None}}])
def test_malformed_cpi_key_is_a_cache_miss(key):
    echo = SimpleNamespace(_source_identity={})
    assert not store.cpi_key_matches(key, echo, {})


def test_malformed_stage_description_is_a_cache_miss():
    with _workspace_tmp('adversarial_stage_manifest') as folder:
        source = folder / 'echo.npz'
        np.savez(source, iq=np.ones(3))
        echo = SimpleNamespace(_source_identity=store.identity(source), _processing_store=folder)
        manifest = dict(key=store.stage_key(echo, {}), description={'features': []})
        np.savez_compressed(folder / 'observations.npz', manifest=np.array(json.dumps(manifest)))
        assert store.load_stage(echo, {}) is None
