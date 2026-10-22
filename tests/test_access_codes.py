"""Access-code registry tests use synthetic codes and never call a provider."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import stat

import pytest

from hsd_tool import access_codes as module
from hsd_tool.access_codes import AccessCodeStore, AccessCodesConflict


ORIGINAL = "synthetic-original-access"
FIRST = "synthetic-first-access"
SECOND = "synthetic-second-access"
POSIX = pytest.mark.skipif(os.name != "posix", reason="actual Linux openat/private permissions")


@pytest.fixture(autouse=True)
def inexpensive_test_kdf(monkeypatch, request):
    # Exercise the actual KDF separately, not 600k iterations for every malformed
    # input / filesystem test. Production arguments are asserted by the spy test.
    if request.node.name == "test_real_pbkdf2_roundtrip_and_random_salt":
        return
    original = hashlib.pbkdf2_hmac
    monkeypatch.setattr(module.hashlib, "pbkdf2_hmac",
                        lambda name, code, salt, iterations: original(name, code, salt, 5))


def registry(tmp_path, **kwargs):
    return AccessCodeStore(tmp_path / "employee-access", **kwargs)


def add(store, code=FIRST, **extra):
    return store.save({"expected_revision": store.snapshot()["revision"],
                       "add": [{"code": code, **extra}]})


def test_real_pbkdf2_roundtrip_and_random_salt(tmp_path):
    first = registry(tmp_path)
    add(first)
    record = json.loads(first.path.read_text("utf-8"))
    assert record["iterations"] == 600_000
    assert hashlib.pbkdf2_hmac("sha256", FIRST.encode(), bytes.fromhex(record["salt_hex"]),
                               record["iterations"]).hex() == record["codes"][0]["digest_hex"]
    assert AccessCodeStore(first.path.parent).verify(FIRST)
    other = AccessCodeStore(tmp_path / "another-private-store")
    add(other)
    different = json.loads(other.path.read_text("utf-8"))
    assert different["salt_hex"] != record["salt_hex"]
    assert different["codes"][0]["digest_hex"] != record["codes"][0]["digest_hex"]


def test_initial_snapshot_configured_code_and_no_plaintext_or_hash_returned(tmp_path):
    store = registry(tmp_path, min_length=16, bootstrap_code=ORIGINAL)
    assert store.snapshot() == {"revision": 0, "min_length": 16, "max_length": 64,
                                "codes": [{"id": "configured", "label": "原有访问码",
                                           "enabled": True, "source": "configured"}]}
    result = add(store, label="设计部")
    assert result["revision"] == 1
    assert store.verify(ORIGINAL) and store.verify(FIRST)
    assert not store.verify(SECOND)
    assert ORIGINAL not in repr(store) and FIRST not in repr(store)
    stored = store.path.read_text("utf-8")
    public = json.dumps(result)
    for sensitive in (ORIGINAL, FIRST, "digest_hex", "salt_hex"):
        assert sensitive not in public
    assert ORIGINAL not in stored and FIRST not in stored
    assert "configured" not in stored
    record = json.loads(stored)
    assert record["codes"][0]["digest_hex"] not in public


def test_save_enable_disable_delete_immediately_apply_and_survive_reload(tmp_path):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    saved = add(store)["codes"][-1]
    second = AccessCodeStore(store.path.parent, bootstrap_code=ORIGINAL)
    assert second.verify(FIRST)
    result = store.save({"expected_revision": 1, "update": [{"id": saved["id"], "enabled": False}]})
    assert result["revision"] == 2 and not store.verify(FIRST) and not second.verify(FIRST)
    assert store.verify(ORIGINAL)
    assert AccessCodeStore(store.path.parent, bootstrap_code=ORIGINAL).snapshot() == result
    second.save({"expected_revision": 2, "update": [{"id": saved["id"], "enabled": True}]})
    assert store.verify(FIRST)
    result = store.save({"expected_revision": 3, "remove": [saved["id"]]})
    assert result["revision"] == 4 and not second.verify(FIRST)
    assert second.verify(ORIGINAL)


def test_noop_preserves_revision_file_and_snapshot_is_detached(tmp_path):
    store = registry(tmp_path)
    result = add(store)
    before = store.path.read_bytes()
    result["codes"][0]["enabled"] = False
    assert store.verify(FIRST)
    assert store.save({"expected_revision": 1})["revision"] == 1
    assert store.save({"expected_revision": 1, "update": [
        {"id": store.snapshot()["codes"][0]["id"], "enabled": True}]})["revision"] == 1
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("code", [FIRST, ORIGINAL])
def test_duplicate_saved_disabled_or_configured_code_rejects_whole_save(tmp_path, code):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    entry = add(store)["codes"][-1]
    store.save({"expected_revision": 1, "update": [{"id": entry["id"], "enabled": False}]})
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="已存在") as error:
        store.save({"expected_revision": 2, "add": [{"code": SECOND}, {"code": code}]})
    assert code not in str(error.value)
    assert store.path.read_bytes() == before and not store.verify(SECOND)
    assert not store.verify(FIRST) and store.verify(ORIGINAL)


def test_duplicate_within_batch_or_removed_same_save_cannot_evade_duplicate_check(tmp_path):
    store = registry(tmp_path)
    with pytest.raises(ValueError, match="已存在"):
        store.save({"expected_revision": 0, "add": [{"code": FIRST}, {"code": FIRST}]})
    entry = add(store)["codes"][0]
    with pytest.raises(ValueError, match="已存在"):
        store.save({"expected_revision": 1, "remove": [entry["id"]], "add": [{"code": FIRST}]})
    assert store.verify(FIRST)


@pytest.mark.parametrize("operation", [
    {"remove": ["configured"]}, {"update": [{"id": "configured", "enabled": False}]},
    {"update": [{"id": "configured", "enabled": True}]},
])
def test_configured_entry_is_read_only(tmp_path, operation):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="原有访问码"):
        store.save(dict(expected_revision=0, **operation))
    assert store.path.read_bytes() == before and store.verify(ORIGINAL)


@pytest.mark.parametrize("payload", [
    None, [], {}, {"expected_revision": True}, {"expected_revision": -1},
    {"expected_revision": "0"}, {"expected_revision": 0, "unexpected": FIRST},
    {"expected_revision": 0, "add": None}, {"expected_revision": 0, "add": {}},
    {"expected_revision": 0, "add": [None]},
    {"expected_revision": 0, "add": [{"code": FIRST, "enabled": True}]},
    {"expected_revision": 0, "update": [{"id": "id", "enabled": 1}]},
    {"expected_revision": 0, "update": [{"id": "id", "enabled": True, "label": "x"}]},
    {"expected_revision": 0, "remove": [None]},
    {"expected_revision": 0, "remove": ["missing"]},
    {"expected_revision": 0, "remove": ["same", "same"]},
    {"expected_revision": 0, "update": [{"id": "same", "enabled": False}], "remove": ["same"]},
    {"expected_revision": 0, "add": [{"code": FIRST}] * 101},
])
def test_invalid_requests_preserve_all_state_and_hide_input(tmp_path, payload):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    before = store.path.read_bytes()
    with pytest.raises(ValueError) as error:
        store.save(payload)
    assert FIRST not in str(error.value) and ORIGINAL not in str(error.value)
    assert store.path.read_bytes() == before and store.snapshot()["revision"] == 0


@pytest.mark.parametrize("code", [None, True, 42, "", "short", "x" * 65, " space-at-start",
                                  "space-at-end ", "has space in it", "has\nnewline", "has\ttab",
                                  "中文访问码不能使用", "\ud800", "nul\x00inside", "del\x7finside"])
def test_codes_require_instance_minimum_and_exact_visible_ascii(tmp_path, code):
    store = registry(tmp_path, min_length=16)
    with pytest.raises(ValueError) as error:
        add(store, code=code)
    if isinstance(code, str) and len(code) >= 16:
        assert code not in str(error.value)
    assert not store.verify(code) and store.snapshot()["revision"] == 0
    assert store.verify(" " + FIRST) is False
    assert store.verify(FIRST + " ") is False


@pytest.mark.parametrize("label", [None, True, "x" * 41, "line\nbreak", "\ud800", "tab\t", FIRST,
                                   "copy:" + FIRST])
def test_invalid_labels_cannot_leak_code_or_break_json(tmp_path, label):
    store = registry(tmp_path)
    before = store.path.read_bytes()
    with pytest.raises(ValueError) as error:
        add(store, label=label)
    assert FIRST not in str(error.value) and store.path.read_bytes() == before


@pytest.mark.parametrize("minimum", [None, True, 0, 65, "16"])
def test_invalid_instance_minimum_rejected(tmp_path, minimum):
    with pytest.raises(ValueError):
        registry(tmp_path, min_length=minimum)


def test_short_original_code_cannot_weaken_cloud_minimum(tmp_path):
    with pytest.raises(ValueError):
        registry(tmp_path, min_length=16, bootstrap_code="HSD")
    desktop = registry(tmp_path, min_length=1, bootstrap_code="HSD")
    assert desktop.verify("HSD")
    assert add(desktop, code="!")["codes"][-1]["enabled"]
    assert desktop.verify("!")


def test_same_path_instances_serialize_saves_and_reload_conflicts(tmp_path):
    first = registry(tmp_path)
    second = registry(tmp_path)

    def submit(store, code):
        try:
            store.save({"expected_revision": 0, "add": [{"code": code}]})
            return "saved"
        except AccessCodesConflict as error:
            assert error.code == "revision_conflict"
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: submit(*args), ((first, FIRST), (second, SECOND))))
    assert sorted(results) == ["conflict", "saved"]
    assert first.snapshot() == second.snapshot()
    assert first.verify(FIRST) != first.verify(SECOND)
    with pytest.raises(AccessCodesConflict):
        first.save({"expected_revision": 0, "remove": [first.snapshot()["codes"][0]["id"]]})


def test_replace_failure_preserves_file_login_revision_and_cleans_temp(tmp_path, monkeypatch):
    store = registry(tmp_path)
    add(store)
    before = store.path.read_bytes()

    def broken(*args, **kwargs):
        raise OSError(FIRST)

    monkeypatch.setattr(module.os, "replace", broken)
    with pytest.raises(ValueError) as error:
        add(store, code=SECOND)
    assert FIRST not in str(error.value) and str(tmp_path) not in str(error.value)
    assert store.path.read_bytes() == before
    assert store.snapshot()["revision"] == 1 and store.verify(FIRST) and not store.verify(SECOND)
    assert not list(store.path.parent.glob(".access-codes-*.tmp"))


def test_flush_failure_before_replace_preserves_prior_settings(tmp_path, monkeypatch):
    store = registry(tmp_path)
    entry = add(store)["codes"][0]
    before = store.path.read_bytes()

    def broken(descriptor):
        raise OSError(SECOND)

    monkeypatch.setattr(module.os, "fsync", broken)
    with pytest.raises(ValueError) as error:
        store.save({"expected_revision": 1, "update": [{"id": entry["id"], "enabled": False}]})
    assert SECOND not in str(error.value)
    assert store.path.read_bytes() == before and store.verify(FIRST)
    assert store.snapshot()["revision"] == 1
    assert not list(store.path.parent.glob(".access-codes-*.tmp"))


def test_registry_deleted_during_temporary_flush_is_not_silently_recreated(tmp_path, monkeypatch):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    add(store)
    original = module.os.fsync
    removed = False

    def remove_registry(descriptor):
        nonlocal removed
        original(descriptor)
        if not removed:
            removed = True
            store.path.unlink()

    monkeypatch.setattr(module.os, "fsync", remove_registry)
    with pytest.raises(ValueError) as error:
        store.save({"expected_revision": 1, "add": [{"code": SECOND}]})
    assert FIRST not in str(error.value) and SECOND not in str(error.value)
    assert not store.path.exists()
    assert not store.verify(FIRST) and not store.verify(SECOND) and not store.verify(ORIGINAL)
    assert not list(store.path.parent.glob(".access-codes-*.tmp"))


def test_registry_deleted_after_reload_before_write_is_not_silently_recreated(tmp_path, monkeypatch):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    add(store)
    write = store._write

    def remove_before_write(record, **kwargs):
        store.path.unlink()
        return write(record, **kwargs)

    monkeypatch.setattr(store, "_write", remove_before_write)
    with pytest.raises(ValueError):
        store.save({"expected_revision": 1, "add": [{"code": SECOND}]})
    assert not store.path.exists() and not store.verify(ORIGINAL)
    assert not list(store.path.parent.glob(".access-codes-*.tmp"))


@POSIX
def test_directory_flush_failure_after_replace_is_uncertain_and_reloads_disk_truth(tmp_path, monkeypatch):
    store = registry(tmp_path)
    entry = add(store)["codes"][0]
    original = module.os.fsync

    def broken(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError(SECOND)
        return original(descriptor)

    monkeypatch.setattr(module.os, "fsync", broken)
    with pytest.raises(ValueError, match="未能确认") as error:
        store.save({"expected_revision": 1, "update": [{"id": entry["id"], "enabled": False}]})
    assert SECOND not in str(error.value)
    assert "未生效" not in str(error.value)
    # Replacement succeeded, so an error must not restore a previously enabled
    # in-memory code or report the stale revision on the next read.
    assert store.snapshot()["revision"] == 2 and not store.verify(FIRST)
    assert AccessCodeStore(store.path.parent).snapshot() == store.snapshot()


@pytest.mark.parametrize("failure", ["missing", "json", "oversized", "extra", "duplicate_field",
                                     "salt", "iterations", "revision", "same_revision_change",
                                     "entry_hash", "entry_id", "entry_duplicate", "label_surrogate"])
def test_corrupt_or_missing_registry_never_falls_back_to_old_or_original_code(tmp_path, failure):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    add(store)
    record = json.loads(store.path.read_text("utf-8"))
    if failure == "missing":
        store.path.unlink()
    elif failure == "json":
        store.path.write_text(FIRST, encoding="utf-8")
    elif failure == "oversized":
        store.path.write_text("x" * (module.MAX_STORE_BYTES + 1), encoding="utf-8")
    elif failure == "duplicate_field":
        content = store.path.read_text("utf-8").replace('"revision": 1', '"revision": 1, "revision": 1')
        store.path.write_text(content, encoding="utf-8")
    else:
        if failure == "extra":
            record["code"] = FIRST
        elif failure == "salt":
            record["salt_hex"] = "ab" * 32
        elif failure == "iterations":
            record["iterations"] = True
        elif failure == "revision":
            record["revision"] = 0
        elif failure == "same_revision_change":
            record["codes"][0]["enabled"] = False
        elif failure == "entry_hash":
            record["codes"][0]["digest_hex"] = FIRST
        elif failure == "entry_id":
            record["codes"][0]["id"] = "configured"
        elif failure == "entry_duplicate":
            record["codes"].append(record["codes"][0])
        elif failure == "label_surrogate":
            record["codes"][0]["label"] = "\ud800"
        store.path.write_text(json.dumps(record), encoding="utf-8")
    assert not store.verify(FIRST) and not store.verify(ORIGINAL)
    with pytest.raises(ValueError) as error:
        store.snapshot()
    assert FIRST not in str(error.value) and str(tmp_path) not in str(error.value)
    with pytest.raises(ValueError):
        store.save({"expected_revision": 1, "add": [{"code": SECOND}]})
    if failure not in {"missing", "salt", "revision", "same_revision_change"}:
        with pytest.raises(ValueError):
            registry(tmp_path, bootstrap_code=ORIGINAL)


def test_login_one_kdf_for_full_registry_and_constant_number_of_comparisons(tmp_path, monkeypatch):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    store.save({"expected_revision": 0,
                "add": [{"code": f"synthetic-access-number-{number:03d}"} for number in range(100)]})
    derive_calls, compare_calls = [], []
    original_derive, original_compare = module.hashlib.pbkdf2_hmac, module.hmac.compare_digest

    def derive(*args):
        derive_calls.append((args[0], args[3]))
        return original_derive(*args)

    def compare(left, right):
        compare_calls.append((len(left), len(right)))
        return original_compare(left, right)

    monkeypatch.setattr(module.hashlib, "pbkdf2_hmac", derive)
    monkeypatch.setattr(module.hmac, "compare_digest", compare)
    for code in (ORIGINAL, "synthetic-access-number-050", "synthetic-unknown-access"):
        derive_calls.clear()
        compare_calls.clear()
        assert store.verify(code) == (code != "synthetic-unknown-access")
        assert derive_calls == [("sha256", 600_000)]
        assert compare_calls == [(32, 32)] * 101
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="100"):
        add(store, SECOND)
    assert store.path.read_bytes() == before


def test_hardlinked_registry_is_never_read_replaced_or_used_for_login(tmp_path):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    add(store)
    linked = store.path.parent / "linked.json"
    try:
        os.link(store.path, linked)
    except OSError:
        pytest.skip("hardlinks unavailable")
    before = linked.read_bytes()
    with pytest.raises(ValueError):
        registry(tmp_path, bootstrap_code=ORIGINAL)
    assert not store.verify(FIRST) and not store.verify(ORIGINAL)
    with pytest.raises(ValueError):
        add(store, SECOND)
    assert linked.read_bytes() == before and store.path.read_bytes() == before


@POSIX
def test_linux_private_permissions_and_safe_nested_directory_creation(tmp_path):
    store = AccessCodeStore(tmp_path / "new-parent" / "employee-access", bootstrap_code=ORIGINAL)
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    add(store)
    assert AccessCodeStore(store.path.parent, bootstrap_code=ORIGINAL).verify(FIRST)


@POSIX
@pytest.mark.parametrize("unsafe", ["symlink", "ancestor_link", "file_mode", "parent_mode", "foreign_owner"])
def test_linux_unsafe_file_or_parent_fails_closed_without_chmod_or_replacement(tmp_path, unsafe, monkeypatch):
    store = registry(tmp_path, bootstrap_code=ORIGINAL)
    add(store)
    original_path = store.path
    if unsafe == "symlink":
        target = store.path.parent / "actual.json"
        store.path.rename(target)
        store.path.symlink_to(target)
    elif unsafe == "ancestor_link":
        target = tmp_path / "renamed-directory"
        store.path.parent.rename(target)
        original_path.parent.symlink_to(target, target_is_directory=True)
    elif unsafe == "file_mode":
        store.path.chmod(0o644)
    elif unsafe == "parent_mode":
        store.path.parent.chmod(0o755)
    else:
        current = os.geteuid()
        monkeypatch.setattr(module.os, "geteuid", lambda: current + 1)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        registry(tmp_path, bootstrap_code=ORIGINAL)
    assert not store.verify(FIRST) and not store.verify(ORIGINAL)
    with pytest.raises(ValueError):
        store.save({"expected_revision": 1, "add": [{"code": SECOND}]})
    assert store.path.read_bytes() == before


@POSIX
def test_linux_parent_redirect_during_write_cannot_receive_new_settings(tmp_path, monkeypatch):
    store = registry(tmp_path)
    add(store)
    original_path = store.path.parent
    moved = tmp_path / "moved-private"
    replacement = tmp_path / "replacement-private"
    replacement.mkdir(mode=0o700)
    original_fsync = module.os.fsync
    replaced = False

    def replace_parent(descriptor):
        nonlocal replaced
        original_fsync(descriptor)
        if not replaced:
            replaced = True
            original_path.rename(moved)
            original_path.symlink_to(replacement, target_is_directory=True)

    monkeypatch.setattr(module.os, "fsync", replace_parent)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        add(store, SECOND)
    assert (moved / "access_codes.json").read_bytes() == before
    assert not list(replacement.iterdir())
    assert not list(moved.glob(".access-codes-*.tmp"))
