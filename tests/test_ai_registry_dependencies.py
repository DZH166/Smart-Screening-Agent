"""Qualification binds every production matcher and review implementation."""
import types
import pytest

from hsd_tool.ai_registry import IMPLEMENTATION_MODULES, ValidationRegistry


@pytest.mark.parametrize("module", ["matching_verification", "archive_io", "ai_first"])
def test_changed_matching_helper_invalidates_previously_signed_qualification(tmp_path, monkeypatch, module):
    import hsd_tool.ai_policy as policy
    import hsd_tool.ai_registry as registry
    from hsd_tool.ai_policy import POLICY_VERSION, PROMPT_VERSION

    revisions = {"hsd_tool." + name: "REVISION = 1" for name in IMPLEMENTATION_MODULES}

    class Loader:
        def get_code(self, fullname):
            return compile(revisions[fullname], "frozen/" + fullname, "exec")

    monkeypatch.setattr(registry.importlib.util, "find_spec",
                        lambda fullname: types.SimpleNamespace(loader=Loader()))
    monkeypatch.setattr(policy, "build_validation_record", lambda *_: {
        "model": "test-only", "policy_version": POLICY_VERSION,
        "prompt_version": PROMPT_VERSION, "categories": ["texture_review"],
        "approved_origins": ["independent_manual"],
        "implementation_sha256": ValidationRegistry._implementation(),
    })
    store = ValidationRegistry(tmp_path)
    assert store.activate({}, {})["qualified"]
    revisions["hsd_tool." + module] = "REVISION = 2"
    assert store.load() == {}
    assert not store.snapshot()["qualified"]
