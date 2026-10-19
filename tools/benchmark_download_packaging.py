"""Three sequential STORE/DEFLATE1 trials on the same real byte corpus.

Names in the temporary archive are neutral benchmark names, not matches or
numbering decisions. Only packaging and local-loopback transfer are measured;
no provider call or second physical computer is involved.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import statistics
import threading
import time
import urllib.request
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args):
    assert not args.work.exists() or not any(args.work.iterdir())
    args.work.mkdir(parents=True, exist_ok=True)
    corpus = args.work / "corpus"
    corpus.mkdir()
    inputs_before = {path: digest(path) for path in (args.source_zip, args.workbook) if path is not None}
    members = []
    if args.compressible_control_mib:
        assert args.compressible_control_mib > 0
        target = corpus / "BENCH0001.ai"
        line = b"0 0 moveto 100 100 lineto 0.25 0.5 0.75 setrgbcolor stroke\n"
        block = line * 32768
        remaining = args.compressible_control_mib * 1024 * 1024
        with target.open("xb") as stream:
            stream.write(b"%!PS-Adobe-3.0 EPSF-3.0\n%%Title: Synthetic compression control only\n")
            while remaining:
                chunk = block[:min(len(block), remaining)]
                stream.write(chunk)
                remaining -= len(chunk)
        members.append((target, "打包基准/已编号AI/" + target.name))
        archive_ratio = {"ai_expanded_bytes": target.stat().st_size,
                         "ai_existing_compressed_bytes": None, "data_origin": "synthetic_compressible_vector_text"}
    else:
        assert args.source_zip is not None, "Provide --source-zip or --compressible-control-mib"
        with zipfile.ZipFile(args.source_zip) as archive:
            originals = [item for item in archive.infolist() if not item.is_dir() and item.filename.lower().endswith(".ai")]
            for index, item in enumerate(originals, 1):
                target = corpus / f"BENCH{index:04}.ai"
                with archive.open(item) as source, target.open("xb") as destination:
                    shutil.copyfileobj(source, destination, 4*1024*1024)
                members.append((target, "打包基准/已编号AI/"+target.name))
            archive_ratio = {"ai_expanded_bytes": sum(item.file_size for item in originals),
                             "ai_existing_compressed_bytes": sum(item.compress_size for item in originals),
                             "data_origin": "real_ai_workbook_bytes"}
    workbook = corpus / "编号Excel.xlsx"
    shutil.copyfile(args.workbook, workbook)
    assert digest(workbook) == inputs_before[args.workbook]
    members.append((workbook, "打包基准/编号Excel.xlsx"))
    expected = {name: digest(path) for path, name in members}
    target = args.work / "active-result.zip"
    expected_archive = {}
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/result.zip":
                self.send_error(404)
                return
            # Match download_asset's full archive rehash before serving; do not
            # mistake a plain static-file transfer for production readiness.
            if digest(target) != expected_archive.get("sha256"):
                self.send_error(409)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            with target.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile, 4*1024*1024)
        def log_message(self, *args):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    runs = []
    try:
        for repeat in range(1, 4):
            # Alternate the first policy to reduce consistent warm-order bias.
            policies = (("store", zipfile.ZIP_STORED), ("deflate1", zipfile.ZIP_DEFLATED))
            if repeat % 2 == 0:
                policies = policies[::-1]
            for label, method in policies:
                start = time.perf_counter()
                with target.open("wb") as output:
                    with zipfile.ZipFile(output, "w", compression=method,
                            compresslevel=1 if method == zipfile.ZIP_DEFLATED else None) as archive:
                        for path, name in members:
                            current = hashlib.sha256()
                            with path.open("rb") as source, archive.open(name, "w", force_zip64=True) as destination:
                                while chunk := source.read(4*1024*1024):
                                    destination.write(chunk)
                                    current.update(chunk)
                            assert current.hexdigest() == expected[name]
                    output.flush()
                    os.fsync(output.fileno())
                archive_hash = digest(target)
                expected_archive["sha256"] = archive_hash
                packed = time.perf_counter()-start
                transfer_start = time.perf_counter()
                received, received_hash = 0, hashlib.sha256()
                with opener.open(f"http://127.0.0.1:{server.server_port}/result.zip", timeout=120) as response:
                    while chunk := response.read(4*1024*1024):
                        received_hash.update(chunk)
                        received += len(chunk)
                transfer = time.perf_counter()-transfer_start
                assert received == target.stat().st_size and received_hash.hexdigest() == archive_hash
                with zipfile.ZipFile(target) as archive:
                    assert set(archive.namelist()) == set(expected)
                    for item in archive.infolist():
                        with archive.open(item) as stream:
                            assert hashlib.file_digest(stream, "sha256").hexdigest() == expected[item.filename]
                result = {"repeat": repeat, "policy": label, "packaging_seconds": packed,
                    "zip_bytes": received, "loopback_transfer_seconds": transfer,
                    "pack_and_loopback_seconds": packed+transfer, "zip_sha256": archive_hash,
                    "member_integrity_verified": True}
                runs.append(result)
                (args.work / "results-in-progress.json").write_text(json.dumps({
                    "planned_trials": 6, "data_origin": archive_ratio["data_origin"], "runs": runs}, indent=2), "utf-8")
                print(json.dumps(result), flush=True)
        assert all(digest(path) == value for path, value in inputs_before.items())
        report = {"scope": ("Synthetic compressible vector text plus the supplied workbook; no matching/AI accuracy claim. "
                            if args.compressible_control_mib else "Same original AI/XLSX byte corpus with neutral names. ") +
                  "Packaging includes member hashing, ZIP64, fsync and final ZIP hash. HTTP transfer includes the production-equivalent full archive rehash plus client receipt/hash. Loopback is not a second PC or actual LAN timing.",
            "member_count": len(members), "workbook_bytes": workbook.stat().st_size,
            **archive_ratio, "inputs_unchanged": True, "real_api_calls": 0, "runs": runs,
            "medians": {policy: {key: statistics.median(item[key] for item in runs if item["policy"] == policy)
                for key in ("packaging_seconds", "zip_bytes", "loopback_transfer_seconds", "pack_and_loopback_seconds")}
                for policy in ("store", "deflate1")}}
        (args.work / "results.json").write_text(json.dumps(report, indent=2), "utf-8")
        print(json.dumps(report["medians"], indent=2))
    finally:
        server.shutdown()
        server.server_close()
        target.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path)
    parser.add_argument("--compressible-control-mib", type=int, default=0,
                        help="Use clearly labelled synthetic vector text instead of original AI files")
    parser.add_argument("--workbook", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    run(parser.parse_args())
