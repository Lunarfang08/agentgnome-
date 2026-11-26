import copy
import json

import pytest
from agentgenome.genome import Manifest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError


def test_roundtrip_hash(manifest):
    parsed = Manifest.model_validate(manifest)
    assert Manifest.model_validate_json(parsed.canonical()).digest() == parsed.digest()
    reversed_keys = dict(reversed(list(manifest.items())))
    assert Manifest.model_validate(reversed_keys).digest() == parsed.digest()


@pytest.mark.parametrize("path,value", [("unexpected", True), ("kind", "Untrusted")])
def test_strict(manifest, path, value):
    manifest[path] = value
    with pytest.raises(ValidationError):
        Manifest.model_validate(manifest)


def test_protected_mutation(manifest):
    manifest["spec"]["evolution"] = {"mutablePaths": ["sandbox.profile"]}
    with pytest.raises(ValidationError):
        Manifest.model_validate(manifest)


@given(st.integers(min_value=1, max_value=100000))
def test_budget_roundtrip(tokens):
    from pathlib import Path

    manifest = json.loads(Path("examples/genomes/procurement.json").read_text())
    manifest["spec"]["limits"]["maxTotalTokens"] = tokens
    parsed = Manifest.model_validate(copy.deepcopy(manifest))
    assert Manifest.model_validate_json(parsed.canonical()).spec.limits.maxTotalTokens == tokens
