"""Build a public Linux source release from committed bytes at clean HEAD.

Usage: python tools/prepare_cloud_release.py --commit <HEAD-SHA> [--date YYYY-MM-DD]
No network, application import, paid request or Git mutation is performed.
The version is read with ast from the committed hsd_tool/__init__.py blob.
"""
from __future__ import annotations

import argparse
import ast
from datetime import date, datetime, timezone, timedelta
import gzip
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = 'release-manifest.json'
# Keep the original design-review renderings in Git; they are not runtime files
# and are omitted from this text-only Linux source archive by exact name.
EXCLUDED = frozenset({'tests/sample_visual_reference.json',
    'docs/preview/admin-key-ledger-desktop.png', 'docs/preview/admin-key-ledger-narrow.png',
    'docs/preview/admin-key-ledger.html', 'docs/preview/ribbon-model-service.html',
    'docs/preview/ribbon-model-service.png'})
DEMO_SVG_FILES = frozenset('tools/material_demo/assets/' + name + '.svg' for name in
    ('orange-bear', 'mint-cat', 'sunshine', 'flower', 'rocket', 'cherry', 'source-sheet'))
ROOT_FILES = frozenset({'.gitignore', '.gitattributes', 'AGENTS.md', 'README.md', 'CONTRACTS.md',
    'CHANGELOG.md', '使用说明.txt', 'requirements.txt', 'requirements-dev.txt',
    'requirements-cloud.txt', 'build.ps1', 'launch.py', 'pytest.ini', 'HSD图号助手.spec'})
SOURCE_ROOTS = frozenset({'hsd_tool', 'tests', 'tools', 'docs', 'deploy', 'installer'})
SOURCE_SUFFIXES = frozenset({'.py', '.js', '.html', '.css', '.md', '.txt', '.ini', '.ps1',
    '.iss', '.example', '.spec', '.yml', '.yaml', '.sh', '.service', '.timer'})
# No generic JSON rule. Add each new public configuration or synthetic fixture
# only after review; business answer maps are never release fixtures.
JSON_FILES = frozenset({'ribbon_frontend/package.json', 'ribbon_frontend/tsconfig.json'})
FRONTEND_CONFIG_FILES = JSON_FILES | frozenset({'ribbon_frontend/pnpm-lock.yaml',
    'ribbon_frontend/vite.config.ts', 'ribbon_frontend/.gitignore',
    'ribbon_frontend/index.html', 'ribbon_frontend/README.md',
    'ribbon_frontend/tests/api.test.mjs', 'ribbon_frontend/tests/browser-smoke.mjs'})
PRIVATE_NAMES = frozenset({'instance.json', 'access_codes.json', 'material_settings.json',
    'material_volcengine_settings.json', 'ribbon_settings.json', 'ribbon_model_settings.json',
    'ai_settings.json', 'ai_usage.json', 'ai_usage.lock', 'ai_validation.json',
    'ai_validation.secret', 'settings.json', '.env', 'gateway.json', '.admin-password',
    'credential.key', 'admin.json', 'employee.code', 'sample_visual_reference.json',
    'retention-signing.key'})
PRIVATE_DIRS = frozenset({'employee_access', 'material_tasks', 'tmp', '.venv', 'venv', '.git',
    '.pytest_cache', '.pytest_tmp', '__pycache__', '测试样本', '测试输出', '输出结果',
    '自测输出', 'uploads', 'jobs', 'employee_outputs', 'screenshots', '交付', 'cache', '缓存',
    'matching', 'task_records', 'ai_runs', 'ai_first_runs', 'export_records', 'build', 'dist',
    'node_modules', 'data', 'codex-handoff', 'test-results', 'playwright-report',
    'ribbon_layout_examples'})
FORBIDDEN_SUFFIXES = frozenset({'.xlsx', '.xls', '.ai', '.log', '.pyc', '.pyo', '.pem', '.key',
    '.png', '.jpg', '.jpeg', '.webp', '.gif', '.pdf', '.zip', '.gz', '.exe', '.dll', '.pyd',
    '.so', '.whl', '.db', '.sqlite', '.sqlite3', '.docx', '.doc', '.p12', '.pfx', '.csv'})
SECRET_PATTERNS = {
    'api_key_literal': re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}\b'),
    'github_token_literal': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b'),
    'private_key_block': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}
# Frozen hashes of previously reviewed, deliberately fake test literals. This
# does NOT grandfather arbitrary values from a commit, parent, or baseline.
# Scope each exception to its reviewed test/verification path; never print values.
REVIEWED_FIXTURES = {
    'tools/admin_fixture_server.py': {'a568ac799e35dad8e14d38391d358855cd3e3ea1d3ae7955e0e9b98e62ff5873',
        '7497ca9862d245508f5726813751287400e4df74aa7bf4dd45d864d66316a2ae'},
    'tools/verify_admin_portable.py': {'b76d751618635f8878883a8cc9f8362f4e36d4050527de20dc84ee9df00f10a1'},
    'tests/test_admin_ui.js': {'8431fa6c2025c92d3eb12b384b0090c997688cde38bc0c76194e1b591900a081'},
    'tests/test_ai_client.py': {'1f1e0043f0b262f8b76452997564e281ade43da2695d8840cd0ba1f15510e38d'},
    'tests/test_ai_gateway_dispatch.py': {'35b56caca503d60d882a3a7cc99b5b0dc6c7355146b96fefa61ba0c1ac222010'},
    'tests/test_ai_gateway_settings.py': {'ef3df72099fc9dcf4f17583b2ee3090ab38841f6648ac0171a8c7cf7e82be08f'},
    'tests/test_ai_key_pool.py': {'43629d25643589594ac15114aa4effe7e8997e4d26af92383da6aa41ee07d5dc',
        '18a5a1281cd227a07dabcd716f52e53bca4192613129445ccb0c385997f5de6f',
        '7053c498221e132a104ab363cea2d8a011163a25bf15714d6b75bc7dda4278a3',
        '757dabded446beab2329af960817fee0e2c2865167320584528f9bf8a83450c5'},
    'tests/test_ai_parallel.py': {'a961af858845e97a5ee3bd1e8f7c81ea431c52115b5cfe29f433114326eed5d3',
        'e826acb6a31654a72e22e77202e0c330ba3e5a9397f4f1f105d0678079f899bd'},
    'tests/test_ai_settings.py': {'65309474574bf81c0a7d13fd4dfded98cf6512a5007ea123a41fd6e0ea759ac5',
        '011c54cb8dec6da17277e05443a60688891829942d3f1e2cca9e9c2a502a842a',
        'dfa9ff0f19ae110a26f2d5bc40ec3e6746cf73d365f2da8c9b64c079550c11c1',
        '09d5d8603961adb4717e7731c3dcf59ac217a42d4e6e1b323c2a165583a8fd3b',
        '4d0e3d12195927d9f04c45c5daf8b9e4cf7978be158f98a9d6811cc87e5fc819',
        '95de922a6298deeaa0b44826140a52341f295d14e73cdd85cdd328b5799c658e',
        '525cc025470867c7afb5387df20a7c72b0af72128bdae9797fa6151e5e792ae1',
        '440205769c0e1cd232b1427812a7e3f2a441034078cc6ecfb0be66f2067cdfba'},
    'tests/test_gateway.py': {'4c1702fe752a271203d8c6d9df8e8fa803bd8eafbf0d039d0c2b2c9af9d50a6e'},
    'tests/test_ribbon_settings.py': {'0456c431284bf80b6668586fb5a89c513e74d0572ca6bb1aa2451a600b4a958e'},
}
REQUIRED_FILES = frozenset({'hsd_tool/__init__.py', 'hsd_tool/cloud_server.py',
    'hsd_tool/cloud_gunicorn.py', 'hsd_tool/cloud_retention.py', 'hsd_tool/cloud_admin.py',
    'hsd_tool/credential_store.py', 'hsd_tool/material_ark.py', 'hsd_tool/material_service.py',
    'hsd_tool/material_quality.py', 'hsd_tool/material_design.py', 'hsd_tool/material_settings.py',
    'hsd_tool/material_providers.py', 'hsd_tool/material_demo.py', 'hsd_tool/access_codes.py',
    'hsd_tool/static/material.js', 'hsd_tool/static/material.css', 'hsd_tool/static/admin-workspace.js',
    'hsd_tool/static/access-codes.html', 'hsd_tool/static/access-codes.js', 'hsd_tool/static/access-codes.css',
    'hsd_tool/static/material-settings.html', 'hsd_tool/static/material-settings.js',
    'hsd_tool/ribbon_gateway.py', 'hsd_tool/ribbon_settings.py', 'hsd_tool/ribbon_examples.py',
    'hsd_tool/static/ribbon-loader.js',
    'hsd_tool/static/ribbon-settings.js', 'hsd_tool/static/ribbon/ribbon.js',
    'ribbon_backend/app.py', 'ribbon_backend/service.py', 'ribbon_backend/retention.py',
    'ribbon_backend/providers.py', 'ribbon_backend/config.py', 'ribbon_backend/imaging.py',
    'ribbon_frontend/package.json', 'ribbon_frontend/tsconfig.json', 'ribbon_frontend/pnpm-lock.yaml',
    'ribbon_frontend/vite.config.ts', 'ribbon_frontend/src/embed.tsx',
    'requirements-cloud.txt', 'deploy/cloud.env.example', 'deploy/hsd-agent.service.example',
    'deploy/nginx-hsd.conf.example', 'deploy/hsd-storage.mount.example',
    'deploy/hsd-healthcheck.sh', 'deploy/hsd-healthcheck.service', 'deploy/hsd-healthcheck.timer',
    'deploy/backup.sh', '.gitattributes', 'README.md', 'AGENTS.md', 'CONTRACTS.md',
    'tools/material_demo/index.html', 'tools/material_demo/demo.js', 'tools/material_demo/demo.css'}) | DEMO_SVG_FILES


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def public_name(name):
    path = PurePosixPath(name)
    require(name == path.as_posix() and not path.is_absolute() and '..' not in path.parts
        and '\\' not in name and ':' not in name and all(p not in {'', '.'} for p in path.parts), 'Unsafe source path')
    require(not any(ord(c) < 32 or ord(c) == 127 for c in name), 'Control character in source path')
    require(not {p.casefold() for p in path.parts} & PRIVATE_DIRS, 'Private source directory refused')
    require(path.name.casefold() not in PRIVATE_NAMES and not path.name.casefold().startswith(
        ('.env', 'ai_observations_', '.ai-settings-', '.ai-usage-', '.material-settings-', '.ribbon-settings-')),
        'Private or runtime source filename refused')
    require(path.suffix.casefold() not in FORBIDDEN_SUFFIXES, 'Binary or business attachment refused')
    require(path.suffix.casefold() != '.json' or name in JSON_FILES, 'JSON is outside the exact release whitelist')
    ribbon_backend = len(path.parts) == 2 and path.parts[0] == 'ribbon_backend' and path.suffix == '.py'
    ribbon_frontend = len(path.parts) > 2 and path.parts[:2] == ('ribbon_frontend', 'src') and path.suffix in {'.ts', '.tsx', '.css'}
    existing_source = len(path.parts) > 1 and path.parts[0] in SOURCE_ROOTS and path.suffix.casefold() in SOURCE_SUFFIXES
    require(name in ROOT_FILES or name in DEMO_SVG_FILES or name in FRONTEND_CONFIG_FILES
        or ribbon_backend or ribbon_frontend or existing_source, 'Source is outside the closed release whitelist: ' + name)


def scan(name, value):
    public_name(name)
    require(isinstance(value, bytes) and b'\0' not in value, 'Non-text source refused: ' + name)
    try:
        value.decode('utf-8-sig')
    except UnicodeError:
        raise RuntimeError('Non-UTF-8 source refused: ' + name) from None
    require(not re.search(rb'(?m)^(?:<{7}|>{7}) ', value), 'Merge conflict in public source')
    path = PurePosixPath(name)
    if path.suffix in {'.sh', '.service', '.timer', '.example'} or name == '.gitattributes':
        require(b'\r' not in value, 'Linux deployment source must be committed with LF: ' + name)
    if name in DEMO_SVG_FILES:
        import xml.etree.ElementTree as ET
        try:
            ET.fromstring(value)
        except ET.ParseError:
            raise RuntimeError('Invalid synthetic SVG') from None
        require(b'<script' not in value.lower() and b'href=' not in value.lower(), 'External or scripted demo SVG refused')
    for label, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(value):
            synthetic = label == 'api_key_literal' and name.startswith('tests/') and b'synthetic' in match.group(0).lower()
            reviewed = label == 'api_key_literal' and digest(match.group(0)) in REVIEWED_FIXTURES.get(name, set())
            require(synthetic or reviewed, 'Unexpected ' + label + ' in ' + name + '; value intentionally omitted')


def committed_version(value):
    module = ast.parse(value.decode('utf-8-sig'))
    versions = [ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)]
    require(len(versions) == 1 and isinstance(versions[0], str) and re.fullmatch(
        r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?', versions[0]), 'Committed version is invalid')
    return versions[0]


def create_manifest(files, commit, release_date):
    require(re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', commit), 'Full commit ID required')
    version = committed_version(files['hsd_tool/__init__.py'][1])
    hashes = {name: digest(value) for name, (_, value) in sorted(files.items())}
    return dict(schema=1, version=version, tag='v' + version, commit=commit,
        release_date=release_date.isoformat(), timezone='Asia/Shanghai', artifact_type='linux-cloud-source',
        source_files=hashes, source_file_count=len(hashes), archive_file_count=len(hashes)+1,
        business_data_included=False, credentials_included=False, runtime_logs_cache_results_included=False,
        dependency_binaries_included=False, windows_binary_included=False, explicit_exclusions=sorted(EXCLUDED))


def build_archive(files, manifest_bytes, epoch):
    """Pure deterministic archive assembly, also used by synthetic tests."""
    for name, (mode, value) in files.items():
        require(mode in {'100644', '100755'}, 'Symlink/submodule source refused')
        scan(name, value)
    output = BytesIO()
    with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=epoch, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as archive:
            members = {name: (int(mode, 8) & 0o777, value) for name, (mode, value) in files.items()}
            members[MANIFEST_NAME] = (0o644, manifest_bytes)
            for name, (mode, value) in sorted(members.items()):
                info = tarfile.TarInfo(name)
                info.size, info.mtime, info.mode = len(value), epoch, mode
                info.uid = info.gid = 0
                info.uname = info.gname = ''
                archive.addfile(info, BytesIO(value))
    return output.getvalue()


def verify_archive(value, source_hashes, manifest_bytes):
    expected, observed = set(source_hashes) | {MANIFEST_NAME}, set()
    with tarfile.open(fileobj=BytesIO(value), mode='r:gz') as archive:
        for entry in archive:
            require(entry.name in expected and entry.name not in observed and entry.isfile(), 'Unexpected archive entry')
            require(not entry.issym() and not entry.islnk() and not entry.isdev(), 'Archive link/device refused')
            if entry.name != MANIFEST_NAME:
                public_name(entry.name)
            stream = archive.extractfile(entry)
            require(stream is not None, 'Unreadable archive member')
            expected_hash = digest(manifest_bytes) if entry.name == MANIFEST_NAME else source_hashes[entry.name]
            require(digest(stream.read()) == expected_hash, 'Archive member differs from committed Git blob')
            observed.add(entry.name)
    require(observed == expected, 'Archive file set differs from manifest')
    return len(observed)


def git(repo, *args, data=None):
    result = subprocess.run(['git', '--no-optional-locks', *args], cwd=repo, input=data,
        capture_output=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0'))
    require(result.returncode == 0, 'Read-only Git command failed; output intentionally omitted')
    return result.stdout


def clean_head(repo):
    require(not git(repo, 'status', '--porcelain=v1', '-z', '--untracked-files=normal'),
        'Commit public changes and resolve untracked files before assembly')
    return git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()


def committed_files(repo, commit):
    selected = {}
    for record in git(repo, 'ls-tree', '-r', '-z', '--full-tree', commit).split(b'\0'):
        if not record:
            continue
        attributes, encoded_name = record.split(b'\t', 1)
        mode, kind, identity = attributes.decode('ascii').split()
        name = encoded_name.decode('utf-8')
        if name in EXCLUDED:
            continue
        public_name(name)
        require(name not in selected and mode in {'100644', '100755'} and kind == 'blob', 'Duplicate or linked Git source refused')
        selected[name] = mode, identity
    require(REQUIRED_FILES <= set(selected), 'Required cloud source/build output is missing from Git HEAD')
    identities = sorted({identity for mode, identity in selected.values()})
    result = BytesIO(git(repo, 'cat-file', '--batch', data=('\n'.join(identities)+'\n').encode('ascii')))
    blobs = {}
    for expected in identities:
        fields = result.readline().decode('ascii').strip().split()
        require(len(fields) == 3 and fields[0] == expected and fields[1] == 'blob', 'Unexpected Git object type')
        size = int(fields[2])
        value = result.read(size)
        require(len(value) == size and result.read(1) == b'\n', 'Truncated Git blob')
        blobs[expected] = value
    require(result.read() == b'', 'Unexpected trailing Git blob data')
    return {name: (mode, blobs[identity]) for name, (mode, identity) in selected.items()}


def safe_destination(repo, path):
    repo, path = Path(repo).absolute(), Path(path).absolute()
    require(path.is_relative_to(repo) and '..' not in path.parts, 'Output must remain in this workspace')
    for part in (path, *path.parents):
        require(not part.is_symlink() and not (hasattr(part, 'is_junction') and part.is_junction()), 'Linked output destination refused')
        if part == repo:
            break


def write_exact(repo, path, value):
    safe_destination(repo, path)
    if path.exists():
        require(path.is_file() and path.read_bytes() == value, 'Existing artifact differs; refusing overwrite')
        return
    temporary = path.parent / ('.sourcepack-' + secrets.token_hex(12) + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        # Linking publishes a complete file atomically and, unlike POSIX
        # rename, refuses a destination created by another writer meanwhile.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def assemble(repo, expected_commit, release_date=None):
    repo = Path(repo).absolute()
    commit = clean_head(repo)
    require(re.fullmatch(r'[0-9a-f]{40}(?:[0-9a-f]{24})?', expected_commit) and expected_commit == commit,
        'Requested commit must be the full current clean HEAD ID')
    files = committed_files(repo, commit)
    epoch = int(git(repo, 'show', '-s', '--format=%ct', commit).strip())
    release_date = release_date or datetime.fromtimestamp(epoch, timezone(timedelta(hours=8))).date()
    manifest = create_manifest(files, commit, release_date)
    manifest_bytes = json_bytes(manifest)
    packed = build_archive(files, manifest_bytes, epoch)
    count = verify_archive(packed, manifest['source_files'], manifest_bytes)
    require(clean_head(repo) == commit, 'Git HEAD/worktree changed during assembly')
    output = repo / '交付' / manifest['tag']
    safe_destination(repo, output)
    output.mkdir(parents=True, exist_ok=True)
    archive_name = 'HSD-Image-Numbering-Cloud-' + manifest['tag'] + '.tar.gz'
    checksum = (digest(packed) + '  ' + archive_name + '\n' + digest(manifest_bytes) + '  ' + MANIFEST_NAME + '\n').encode('ascii')
    artifacts = []
    for name, value in ((archive_name, packed), (MANIFEST_NAME, manifest_bytes), ('SHA256.txt', checksum)):
        path = output / name
        write_exact(repo, path, value)
        require(path.read_bytes() == value, 'Written artifact verification failed')
        artifacts.append(dict(name=name, path=str(path), bytes=len(value), sha256=digest(value)))
    require(clean_head(repo) == commit, 'Git HEAD/worktree changed before delivery receipt')
    return dict(version=manifest['version'], tag=manifest['tag'], commit=commit,
        date=release_date.isoformat(), artifacts=artifacts, source_file_count=len(files),
        archive_file_count=count, manifest_sha256=digest(manifest_bytes),
        git_blob_bytes_verified=True, archive_entries_verified=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True, help='Full SHA of current clean HEAD')
    parser.add_argument('--date', type=date.fromisoformat, help='Release date; defaults to commit date in Asia/Shanghai')
    args = parser.parse_args()
    print(json.dumps(assemble(ROOT, args.commit, args.date), ensure_ascii=True))


if __name__ == '__main__':
    main()
