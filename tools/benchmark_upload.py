"""Sequential real HTTP multipart ingestion timings; matching is deliberately stubbed.

Measures reception, server streaming SHA, validation and task admission only.
Loopback transfer is not a second employee computer or whole-batch measurement.
Explicit original XLSX/ZIP inputs and all private generated copies stay local.
"""
import argparse
import hashlib
import http.client
import http.cookiejar
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
import uuid


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def worker(args):
    sys.path.insert(0, str(args.package_root.resolve()))
    os.environ.pop('DEEPSEEK_API_KEY', None)
    from werkzeug.serving import make_server, WSGIRequestHandler
    from hsd_tool.server import create_app
    from hsd_tool.lan import LanAccess
    import hsd_tool.server as server_module
    import hsd_tool.service as service_module
    import hsd_tool.uploads as uploads_module
    modules = (server_module, service_module, uploads_module)
    assert all(Path(module.__file__).resolve().is_relative_to(args.package_root.resolve()) for module in modules)
    implementation = {module.__name__: digest(Path(module.__file__)) for module in modules}
    inputs, outputs = args.out / 'host_inputs', args.out / 'host_outputs'
    inputs.mkdir(parents=True)
    outputs.mkdir()
    # The real server binds loopback only. The artificial LAN identity enables
    # the actual upload route without opening any LAN or firewall access.
    app = create_app(args.out / 'state', settings_dir=args.out / 'isolated-settings',
                     lan=LanAccess('10.254.254.1/24', inputs, outputs))
    manager = app.config['HSD_MANAGER']
    def admitted(identifier):
        with manager.lock:
            manager.jobs[identifier]['status'] = 'ready'
    manager._process = admitted
    class Quiet(WSGIRequestHandler):
        def log_request(self, *values, **options):
            pass
    server = make_server('127.0.0.1', 0, app, threaded=True, request_handler=Quiet)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))
    before = {'workbook': digest(args.workbook), 'source': digest(args.source)}
    try:
        with opener.open(base, timeout=20) as response:
            html = response.read().decode('utf-8')
        token = json.loads(re.search(r'window\.HSD_TOKEN\s*=\s*("[^"\r\n]*")', html).group(1))
        boundary = 'hsd-upload-bench-' + uuid.uuid4().hex
        fields = []
        for name, path in (('workbook', args.workbook), ('source', args.source)):
            header = (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                      f'filename="{name}{path.suffix}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
            fields.append((header, path))
        start_field = f'--{boundary}\r\nContent-Disposition: form-data; name="start_number"\r\n\r\n7\r\n'.encode()
        ending = f'--{boundary}--\r\n'.encode()
        length = len(start_field) + len(ending) + sum(len(header) + path.stat().st_size + 2 for header, path in fields)
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=300)
        started = time.perf_counter()
        try:
            connection.putrequest('POST', '/api/jobs/upload')
            headers = {'Origin': base, 'X-HSD-Token': token,
                       'Content-Type': 'multipart/form-data; boundary=' + boundary,
                       'Content-Length': str(length),
                       'Cookie': '; '.join(cookie.name + '=' + cookie.value for cookie in cookies)}
            for name, value in headers.items():
                connection.putheader(name, value)
            connection.endheaders()
            sent = 0
            for header, path in fields:
                connection.send(header)
                sent += len(header)
                with path.open('rb') as stream:
                    while block := stream.read(4 * 1024 * 1024):
                        connection.send(block)
                        sent += len(block)
                connection.send(b'\r\n')
                sent += 2
            connection.send(start_field + ending)
            sent += len(start_field) + len(ending)
            response = connection.getresponse()
            body = json.loads(response.read())
            assert response.status == 200, body.get('error', response.status)
            elapsed = time.perf_counter() - started
            assert sent == length
            job = manager.jobs[body['id']]
            assert job['_upload_digests'] == before
            assert digest(Path(job['_workbook_path'])) == before['workbook']
            assert digest(Path(job['_source_path'])) == before['source']
            print(json.dumps({'seconds': elapsed, 'multipart_bytes': sent,
                              'server_input_digests_verified': True, 'real_api_calls': 0,
                              'input_sha256': before, 'implementation_sha256': implementation,
                              'harness_sha256': digest(Path(__file__))}), flush=True)
        finally:
            connection.close()
        assert before == {'workbook': digest(args.workbook), 'source': digest(args.source)}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        manager.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--package-root', type=Path)
    parser.add_argument('--workbook', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    assert args.baseline_root
    args.out.mkdir(parents=True, exist_ok=False)
    current = Path(__file__).resolve().parents[1]
    runs = []
    for iteration in range(3):
        for label, package in (('baseline', args.baseline_root), ('current', current)):
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker',
                '--package-root', str(package.resolve()), '--workbook', str(args.workbook.resolve()),
                '--source', str(args.source.resolve()), '--out', str(args.out / f'{label}-{iteration}')],
                check=False, capture_output=True, text=True, encoding='utf-8')
            raw = args.out / f'{label}-{iteration}-process.json'
            raw.write_text(json.dumps({'returncode': result.returncode, 'stdout': result.stdout,
                                     'stderr': result.stderr}, ensure_ascii=False, indent=2), 'utf-8')
            value = json.loads(result.stdout) if result.returncode == 0 else {'failed': True, 'returncode': result.returncode}
            runs.append(dict(value, implementation=label, iteration=iteration))
            (args.out / 'runs.json').write_text(json.dumps(runs, ensure_ascii=False, indent=2), 'utf-8')
    report = {'scope': 'Real HTTP loopback upload ingestion only; actual matcher replaced by admission marker; no provider calls or whole-batch speed claim',
              'runs': runs, 'medians_seconds': {label: (statistics.median(item['seconds'] for item in runs if item['implementation'] == label)
                  if sum(item['implementation'] == label and not item.get('failed') for item in runs) == 3 else None)
                  for label in ('baseline', 'current')}}
    (args.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report['medians_seconds']))
    assert len(runs) == 6 and not any(item.get('failed') for item in runs), 'Failed runs retained; do not claim completed benchmark'


if __name__ == '__main__':
    main()
