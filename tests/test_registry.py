"""Tests for the file-backed Registry."""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402
from prompt_registry.registry import (  # noqa: E402
    PromptVersion, Registry, default_registry_path, now_iso,
)


BUNDLED = default_registry_path()


def test_bundled_registry_lists_three_prompts():
    reg = Registry(BUNDLED)
    assert set(reg.list_prompts()) == {
        "customer_complaint_classifier", "meeting_recap", "policy_summary",
    }


def test_bundled_registration_has_v1_and_v2():
    reg = Registry(BUNDLED)
    r = reg.get("customer_complaint_classifier")
    assert "v1" in r.versions
    assert "v2" in r.versions


def test_bundled_active_is_v1():
    reg = Registry(BUNDLED)
    assert reg.get("customer_complaint_classifier").active_version == "v1"


def test_prompt_version_renders_variables():
    v = PromptVersion(
        name="x", version="v1",
        template="Hello {name}, today is {day}.",
        model="m", params={}, description="", created_at=now_iso(),
    )
    assert v.render(name="world", day="Monday") == "Hello world, today is Monday."


def test_prompt_version_missing_variable_raises():
    v = PromptVersion(
        name="x", version="v1", template="Hello {name}.",
        model="m", params={}, description="", created_at=now_iso(),
    )
    with pytest.raises(KeyError, match="name"):
        v.render()


def test_prompt_version_lists_variables():
    v = PromptVersion(
        name="x", version="v1", template="{a} and {b} but not {a} twice",
        model="m", params={}, description="", created_at=now_iso(),
    )
    assert v.variables() == ["a", "b"]


def test_latest_version_is_highest_numbered():
    reg = Registry(BUNDLED)
    r = reg.get("customer_complaint_classifier")
    assert r.latest_version() == "v2"


# --- Writing behaviour --------------------------------------------------------

def test_add_version_writes_file(tmp_path):
    reg = Registry(tmp_path)
    v = PromptVersion(
        name="my_prompt", version="v1", template="Hi {name}",
        model="m", params={}, description="initial", created_at=now_iso(),
    )
    path = reg.add_version(v)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "my_prompt"


def test_add_version_refuses_to_overwrite(tmp_path):
    reg = Registry(tmp_path)
    v = PromptVersion(
        name="x", version="v1", template="t", model="m", params={},
        description="", created_at=now_iso(),
    )
    reg.add_version(v)
    with pytest.raises(FileExistsError, match="immutable"):
        reg.add_version(v)


def test_set_active_promotes_version(tmp_path):
    reg = Registry(tmp_path)
    reg.add_version(PromptVersion(
        name="x", version="v1", template="t1", model="m", params={},
        description="", created_at=now_iso(),
    ))
    reg.add_version(PromptVersion(
        name="x", version="v2", template="t2", model="m", params={},
        description="", created_at=now_iso(),
    ))
    reg.set_active("x", "v2")
    assert reg.get("x").active_version == "v2"


def test_set_active_refuses_unknown_version(tmp_path):
    reg = Registry(tmp_path)
    reg.add_version(PromptVersion(
        name="x", version="v1", template="t", model="m", params={},
        description="", created_at=now_iso(),
    ))
    with pytest.raises(KeyError, match="v9"):
        reg.set_active("x", "v9")


def test_rollback_reverts_to_previous(tmp_path):
    reg = Registry(tmp_path)
    for v_name in ("v1", "v2", "v3"):
        reg.add_version(PromptVersion(
            name="x", version=v_name, template="t", model="m", params={},
            description="", created_at=now_iso(),
        ))
    reg.set_active("x", "v3")
    new_active = reg.rollback("x")
    assert new_active == "v2"
    assert reg.get("x").active_version == "v2"


def test_rollback_returns_none_when_already_on_v1(tmp_path):
    reg = Registry(tmp_path)
    reg.add_version(PromptVersion(
        name="x", version="v1", template="t", model="m", params={},
        description="", created_at=now_iso(),
    ))
    reg.set_active("x", "v1")
    assert reg.rollback("x") is None
