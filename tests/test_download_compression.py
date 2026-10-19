"""Compression sampling never substitutes for identity or member validation."""
import random
from pathlib import Path
import zipfile
import zlib

import pytest

import hsd_tool.service as service
from test_employee_service import wait_finished
from test_service import prepared


@pytest.mark.parametrize("content,expected", [
    (b"", zipfile.ZIP_STORED), (b"tiny", zipfile.ZIP_STORED),
    (b"vector path 10 20 stroke\n" * 100, zipfile.ZIP_DEFLATED),
    (random.Random(1800).randbytes(512), zipfile.ZIP_STORED),
    (b"same repeated vectors\n" * 50000, zipfile.ZIP_DEFLATED),
    (random.Random(1801).randbytes(1024*1024), zipfile.ZIP_STORED),
], ids=["empty", "small", "small-vector", "small-random", "repeated-vector", "encoded-random"])
def test_member_policy_handles_empty_small_compressible_and_encoded_content(tmp_path, content, expected):
    path = tmp_path / "member.ai"
    path.write_bytes(content)
    assert service._download_compression(path) == expected


def test_large_member_sampling_is_bounded_and_checks_head_middle_tail(tmp_path, monkeypatch):
    path = tmp_path / "large.ai"
    path.write_bytes(random.Random(1802).randbytes(2*1024*1024))
    original = Path.open
    reads = []
    class ReadOnlySample:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def seek(self, position):
            return self.stream.seek(position)
        def read(self, size):
            reads.append((self.stream.tell(), size))
            assert 0 < size <= service.COMPRESSION_SAMPLE_BYTES
            return self.stream.read(size)
    monkeypatch.setattr(Path, "open", lambda current, *args, **kwargs:
        ReadOnlySample(original(current, *args, **kwargs)) if current == path else original(current, *args, **kwargs))
    assert service._download_compression(path) == zipfile.ZIP_STORED
    assert len(reads) == 3
    assert sum(size for _, size in reads) <= service.COMPRESSION_SAMPLE_BUDGET
    assert reads[0][0] == 0 and reads[-1][0] == path.stat().st_size-service.COMPRESSION_SAMPLE_BYTES


@pytest.mark.parametrize("encoded_section", [0, 1, 2])
def test_text_in_other_sections_cannot_hide_an_encoded_section(tmp_path, encoded_section):
    size = 2*1024*1024
    block = service.COMPRESSION_SAMPLE_BYTES
    # General mixed-content control: most bytes are already encoded, with
    # readable/repeated metadata at selected sample positions. No AI syntax,
    # business filenames, or regression sample answers affect the policy.
    content = bytearray(random.Random(1810+encoded_section).randbytes(size))
    text = (b"repeated metadata vector path\n" * (block//29+1))[:block]
    offsets = (0, (size-block)//2, size-block)
    for index, offset in enumerate(offsets):
        if index != encoded_section:
            content[offset:offset+block] = text
    path = tmp_path / "mixed-content.ai"
    path.write_bytes(content)
    combined = b"".join(content[offset:offset+block] for offset in offsets)
    assert len(zlib.compress(combined, 1))*10 <= len(combined)*9
    assert service._download_compression(path) == zipfile.ZIP_STORED


def test_actual_archive_uses_per_member_policy_and_preserves_original_bytes(tmp_path):
    manager, job = prepared(tmp_path, ["", ""])
    job.update(_owner_id="employee", _downloadable=True)
    content = [b"0 0 moveto 100 100 lineto stroke\n" * 20000,
               random.Random(1803).randbytes(256*1024)]
    for file, value in zip(job["files"], content):
        Path(file["source_path"]).write_bytes(value)
        file["source_sha256"] = service.sha256(file["source_path"])
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        path, _ = manager.download_asset("sample")
        prefix = Path(job["output_dir"]).name+"/"
        with zipfile.ZipFile(path) as archive:
            assert len(archive.namelist()) == 3
            assert archive.getinfo(prefix+"已编号AI/HSD0001.ai").compress_type == zipfile.ZIP_DEFLATED
            assert archive.getinfo(prefix+"已编号AI/HSD0002.ai").compress_type == zipfile.ZIP_STORED
            assert archive.read(prefix+"已编号AI/HSD0001.ai") == content[0]
            assert archive.read(prefix+"已编号AI/HSD0002.ai") == content[1]
    finally:
        manager.close()


def test_changed_output_after_sampling_is_rejected_by_full_manifest_hash(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original = service._download_compression
    def changed(path):
        policy = original(path)
        if path.suffix == ".ai":
            path.write_bytes(b"changed after bounded sample")
        return policy
    monkeypatch.setattr(service, "_download_compression", changed)
    try:
        manager.export("sample")
        result = wait_finished(manager)
        assert result["status"] == "ready" and "发生变化" in result["error"]
        assert not result["download_ready"]
        assert not (Path(job["_work_dir"])/"HSD编号结果.zip").exists()
    finally:
        manager.close()


def test_sampling_only_reads_explicit_white_list_members(tmp_path, monkeypatch):
    manager, job = prepared(tmp_path, [""])
    job.update(_owner_id="employee", _downloadable=True)
    original_package, original_policy = manager._package_download, service._download_compression
    sampled = []
    def policy(path):
        sampled.append(path.name)
        return original_policy(path)
    def extra(current, directory):
        (directory / "private.json").write_text('{"must_not_be_sampled":true}')
        (directory / "unplanned.ai").write_bytes(b"not authorized")
        return original_package(current, directory)
    monkeypatch.setattr(service, "_download_compression", policy)
    monkeypatch.setattr(manager, "_package_download", extra)
    try:
        manager.export("sample")
        assert wait_finished(manager)["status"] == "done"
        assert set(sampled) == {"HSD0001.ai", "sample_已编号.xlsx"}
        with zipfile.ZipFile(manager.download_asset("sample")[0]) as archive:
            assert len(archive.namelist()) == 2
    finally:
        manager.close()
