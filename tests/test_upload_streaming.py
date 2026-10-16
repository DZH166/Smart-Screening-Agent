"""Generated multipart data exercises streaming, disk failures and private digests."""
import errno
import hashlib
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from hsd_tool.server import EmployeeUploadRequest
from hsd_tool.uploads import DiskBudget, EmployeeUploads, UploadFile, UploadWriteError
from test_employee_api import (employee_app, captured_jobs, login, upload, request,
                               workbook_bytes, zip_bytes, REMOTE, ORIGIN, TOKEN)


def stored_zip(data):
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("pattern.ai", data)
    return output.getvalue()


def test_multipart_writes_once_then_renames_and_never_copies_the_upload_stream(employee_app, captured_jobs, monkeypatch):
    streams = []
    factory = EmployeeUploadRequest._get_file_stream
    def observe(self, *args, **kwargs):
        assert self.max_content_length is None
        result = factory(self, *args, **kwargs)
        assert isinstance(result, UploadFile)
        def no_copy(*args, **kwargs):
            raise AssertionError("Managed multipart stream must be renamed, not read/copied again")
        result.read = no_copy
        streams.append(result)
        return result
    monkeypatch.setattr(EmployeeUploadRequest, "_get_file_stream", observe)
    client = employee_app.test_client();login(client)
    response = upload(client, source=stored_zip(b"generated" * (256 * 1024)))
    assert response.status_code == 200, response.json
    assert len(streams) == 2 and all(stream.closed for stream in streams)
    assert all(not stream.path.exists() for stream in streams)
    directory = Path(captured_jobs[0]["payload"]["source_path"]).parent
    assert {path.name for path in directory.iterdir()} == {".hsd-upload", "workbook.xlsx", "source.zip"}
    assert captured_jobs[0]["input_digests"] == {"workbook": streams[0].hexdigest, "source": streams[1].hexdigest}
    assert employee_app.config["MAX_CONTENT_LENGTH"] == 64 * 1024


def test_disk_free_space_is_rechecked_by_windows_not_each_multipart_chunk(employee_app, captured_jobs, monkeypatch):
    import hsd_tool.uploads as module
    monkeypatch.setattr(module, "DISK_CHECK_INTERVAL", 4 * 1024**2)
    usage = module.shutil.disk_usage
    calls = []
    def observe(path):
        calls.append(path)
        return usage(path)
    monkeypatch.setattr(module.shutil, "disk_usage", observe)
    client = employee_app.test_client();login(client)
    response = upload(client, source=stored_zip(b"s" * (9 * 1024**2)))
    assert response.status_code == 200
    assert 3 <= len(calls) <= 4


def test_no_physical_space_fails_clearly_and_cleans_staged_files(employee_app, captured_jobs, monkeypatch):
    import hsd_tool.uploads as module
    monkeypatch.setattr(module.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    client = employee_app.test_client();login(client)
    response = upload(client)
    assert response.status_code == 400 and "磁盘空间不足" in response.json["error"]
    assert captured_jobs == []
    assert not list(employee_app.config["HSD_UPLOADS"].input_root.iterdir())


def test_os_disk_full_during_write_fails_without_returning_a_digest(employee_app, captured_jobs, monkeypatch):
    received = []
    original = EmployeeUploads.open_stream
    class FullDisk:
        def __init__(self, stream): self.stream = stream
        def write(self, data): raise OSError(errno.ENOSPC, "simulated physical disk full")
        def __getattr__(self, name): return getattr(self.stream, name)
    def fail(self, directory, budget):
        stream = original(self, directory, budget)
        stream._file = FullDisk(stream._file)
        received.append(stream)
        return stream
    monkeypatch.setattr(EmployeeUploads, "open_stream", fail)
    client = employee_app.test_client();login(client)
    response = upload(client)
    assert response.status_code == 400 and "磁盘空间不足" in response.json["error"]
    assert captured_jobs == [] and received
    assert all(stream.bytes_written == 0 and stream.hexdigest == hashlib.sha256(b"").hexdigest() for stream in received)
    assert all(stream.closed for stream in received)
    assert not list(employee_app.config["HSD_UPLOADS"].input_root.iterdir())


def test_short_write_hashes_only_successfully_written_bytes(tmp_path):
    stream = UploadFile(tmp_path / "partial", DiskBudget(tmp_path))
    actual = stream._file
    class ShortWrite:
        def write(self, data):
            actual.write(data[:3]);return 3
        def __getattr__(self, name):return getattr(actual, name)
    stream._file = ShortWrite()
    with pytest.raises(UploadWriteError, match="未完整写入"):
        stream.write(b"abcdef")
    stream.close()
    assert stream.bytes_written == 3 and stream.hexdigest == hashlib.sha256(b"abc").hexdigest()
    assert (tmp_path / "partial").read_bytes() == b"abc"


def test_direct_filestorage_fallback_streams_in_chunks_and_computes_private_digests(tmp_path):
    import hsd_tool.uploads as module
    class ChunkOnly(BytesIO):
        def read(self, size=-1):
            assert 0 < size <= module.COPY_BUFFER_BYTES
            return super().read(size)
    workbook, source = workbook_bytes(), stored_zip(b"generated" * 300000)
    files = MultiDict({"workbook": FileStorage(ChunkOnly(workbook), filename="generated.xlsx"),
                       "source": FileStorage(ChunkOnly(source), filename="generated.zip")})
    directory, payload, names = EmployeeUploads(tmp_path).receive(files, MultiDict({"start_number": "1"}))
    assert names["_input_digests"] == {"workbook": hashlib.sha256(workbook).hexdigest(), "source": hashlib.sha256(source).hexdigest()}
    assert Path(payload["source_path"]).read_bytes() == source
    assert directory.is_dir()


def test_valid_workbook_above_previous_100_mib_is_received_without_a_byte_cap(employee_app, captured_jobs, tmp_path):
    large = tmp_path / "large.xlsx"
    large.write_bytes(workbook_bytes())
    block = b"synthetic-padding" * (1024 * 1024 // len(b"synthetic-padding"))
    with zipfile.ZipFile(large, "a", zipfile.ZIP_STORED) as archive:
        with archive.open("unused-padding.bin", "w", force_zip64=True) as stream:
            for _ in range(102): stream.write(block)
    assert large.stat().st_size > 100 * 1024**2
    client = employee_app.test_client();login(client)
    with large.open("rb") as input_stream:
        response = request(client, "/api/jobs/upload", method="POST", data={"workbook": (input_stream, "large.xlsx"),
            "source": (BytesIO(zip_bytes({"pattern.ai": b"synthetic"})), "source.zip"), "start_number": "1"}, content_type="multipart/form-data")
    assert response.status_code == 200, response.json
    copied = Path(captured_jobs[0]["payload"]["workbook_path"])
    assert copied.stat().st_size == large.stat().st_size
    with large.open("rb") as stream: expected = hashlib.file_digest(stream, "sha256").hexdigest()
    assert captured_jobs[0]["input_digests"]["workbook"] == expected


def test_compressible_ai_is_not_rejected_as_a_hidden_upload_size_limit(employee_app, captured_jobs):
    client = employee_app.test_client();login(client)
    source = zip_bytes({"pattern.ai": b"x" * (8 * 1024**2)})
    with zipfile.ZipFile(BytesIO(source)) as archive:
        info = archive.getinfo("pattern.ai")
        assert info.file_size > max(1, info.compress_size) * 1000
    assert upload(client, source=source).status_code == 200


def test_declared_large_request_is_parsed_instead_of_rejected_by_previous_two_gib_cap(employee_app, captured_jobs):
    client = employee_app.test_client();login(client)
    boundary = "synthetic-large-declaration"
    data = f'--{boundary}\r\nContent-Disposition: form-data; name="start_number"\r\n\r\n1\r\n'.encode()
    response = client.open('/api/jobs/upload', method='POST', base_url=ORIGIN,
        headers={'Origin':ORIGIN,'X-HSD-Token':TOKEN,'Content-Type':f'multipart/form-data; boundary={boundary}'},
        environ_overrides={'REMOTE_ADDR':REMOTE,'wsgi.input':BytesIO(data),'CONTENT_LENGTH':str(3 * 1024**3)})
    assert response.status_code == 400  # Actual short body, not a successful 3 GiB transfer.
    assert captured_jobs == []
    assert not list(employee_app.config['HSD_UPLOADS'].input_root.iterdir())
