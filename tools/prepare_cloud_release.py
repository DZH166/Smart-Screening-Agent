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
# and are omitted from this text-only Linux source archive.
EXCLUDED = frozenset({'tests/sample_visual_reference.json'})
EXCLUDED_DIRECTORIES = frozenset({'docs/preview'})
DEMO_SVG_FILES = frozenset('tools/material_demo/assets/' + name + '.svg' for name in
    ('orange-bear', 'mint-cat', 'sunshine', 'flower', 'rocket', 'cherry', 'source-sheet'))
# Only these public previews made by tools/ribbon_layout_thumbnails.py are
# release assets. Byte pinning prevents a private image renamed to a known mode.
LAYOUT_WEBP_SHA256 = {
    'alternating': '982509e810ef027d7edce8be14e76c5219f956a1801e7945ffc8b724cd7f4339',
    'bordered': '2ca747adeaea9bdac06493c9a18a13e0155bb8b93134e1af0a8cf287be9a60a2',
    'ends': '5439637471b3b3a064d29e328c566ed3615f26df30611af74a5901a4ff9a17df',
    'ends_open': '21c355ac0f45cad3e20f8d941b1de58ba9263f95e2674efc4fb8f0ef95203c95',
    'fullwidth': 'c37858433fcb581adb1c2653efe207fbf83bc6393476654042f6deb6263d04cb',
    'grid': 'b74d6203efd3a3b4ac4c51ac5baf4bf5390c1678b69f9abb2c72e217f9817048',
    'opposed': '7e29814305aeecf8d436e4d2e93189f2f4389ec0f98a0db98b3b98b52fc2b08e',
    'panels': '97856eea16088e9ff12b06ad71732add1313b813867a1eaf46b657d3633b0514',
    'scatter': '74889731b34f5fdf84f8c07fcfb4ac8092a1280e9c7d58825be24b62b12327bc',
    'scene': 'a5f4c3bfe4c15c5af02f475326888aed1566d8d61c104e3368cbfe998cd1c17b',
    'single': '32c3a6eca5118b5844b3df22491cf474a5ac2cf22a321437cf428c2c3d353483',
    'split': 'a9969daf674cf8fc7482659b41aa15f0fc117e281bd0e14f5107d0f0f8f477cf',
    'stacked': 'bf527670d32dc2c8d2cbb5000acb0f198980c7abba8a1d1f2d2c7ee17a8b3252',
    'stagger': '5db5bb26f3fdfa0c42dbb5edcea2ac44eb2117b07dc83caac92304bb6cb0ae6d',
}
# Separate reviewed v3 artwork; old v2 hashes and historical template files stay immutable.
# Generated only from original Pillow drawings by tools/ribbon_layout_thumbnails_v3.py.
LAYOUT_V3_WEBP_SHA256 = {
    'alternating-1': 'c0e0e2999c4e6b0ce9c409c67d7a62d5f26a7a73f244451aa5e188085cdf9d8c',
    'alternating-3': '0ccb3bc2d092e859bf6ac89493546a132baa875d2a5efcf1fe24dd103cd9755d',
    'alternating-6': 'd2bd5dfc6173b867a882a7c1922feeaee5cf81a5eddcf36724801e1de3a99baa',
    'alternating': '0af34f103aefbb767da003eae281a29c8e8c3f09f7975754d9713a6d4dc8d247',
    'bordered-1': '1da068c5514161511f5ae33d217dd38b2c34f47055d927811f5c8317e77efaf4',
    'bordered-3': '585face0d1fc722461d524a3d2f777a9907fa29f2e9ebfa34b1b1f6e26665725',
    'bordered-6': '2cbe442b727c43055b3682685c4c1a7619b242487f55e7785782c75b256f8d21',
    'bordered': '6ded187ce458fe84df09e84ea1e612ca64795ef7814f1afa3a5b895d6a245a24',
    'ends-1': '940e112cba0a678736c76a20e756fd9a07d0c5252da03f65fd8055990a4fe1cf',
    'ends-3': '3d6fc07b705c9874f79332cace112f5fdcdd8a71ca934b01d9a9e7877c1a484c',
    'ends-6': 'f8d7a51d4aee7886df1de1e9c3ab2597a59d3bf87b92e9ce95824c4f036a7755',
    'ends': '2348ac80a8b9441818ad3f65d7b17b9c2a45f9385daced61dc30192aba7343c4',
    'ends_open-1': '6214ced8897438955b5f654e7aef61f9848bcc2272f1209ca75f83e5edb7fe4a',
    'ends_open-3': '7f9eb6dc5ef52d39f0aaa459f589ec7c0e278a5687b5b451d909ec8c4cb3d220',
    'ends_open-6': 'ad56326833fdad73a6b2a39edee6614758f06139d6703b2500a99b35799aba1a',
    'ends_open': '15e274bb15134178006598b4d8dcc94f97d62ffa02ffaed1882ceee90d646c13',
    'fullwidth-1': 'ac243323d0fb3ffa6c1686f2d30e3a65b9217001dc354c5c97fefdc12013cb88',
    'fullwidth-3': 'f919c127ca9bb7dc00c9123b0b0e7b7f5855276605547d2174bb2b5e356dab3e',
    'fullwidth-6': 'c26d95a3514447c5641339f9e606128fc1cdc7a5471e2ccec6d593e1f2670658',
    'fullwidth': '84ed51a98f4b3f3d86bb3542651045e68a3dd9b85b7d1756e254b621e7925ec8',
    'grid-1': 'ea11ec0802d5a0d41147952c9e8ee77896ce0a7920fd43ec47760b36598a86f3',
    'grid-3': '1fadd14642f2a65fef3951d0feb4cbf2ba8d407b2eaccbf95a97c1613f2e6d1a',
    'grid-6': '0b1ea1474326a83b0966aeae25677a6a92d711c82d3b89da0dd019118ea39cf9',
    'grid': '45cdf01f119b0161ca8a137b27568ce76b86ff321cf6992f16e028e9d9e7ff7f',
    'opposed-1': 'c7a1ac7c34d3b83fce792094b8d4cb626c3a82ca5e496f0634f518b818234fff',
    'opposed-3': '61b19049886e2f432b46fd8f972b5e9040cee6cf598cfcb15ddaa378be77e1c2',
    'opposed-6': '50e4576e3443d472f6e8a03762098c076ad81255b58c221e470a65d8f827e087',
    'opposed': '3cf80981858a7c69e80ba4e30511da4f02caa238bbb131f8b37292f199ae0421',
    'panels-1': '730389515f628f2753d7174817b281c012db360557e7dabf83056a8250a0ef34',
    'panels-3': '8a4e03c5074e86b6e0f9cafa8d8b89d58bf21cf691b9866c3ae1f47e41fc09c6',
    'panels-6': '71a2f47a876f020b74f87e608709fbe7c048564964ce063e2f8925211973a77d',
    'panels': '23a491eee21d88ded829807827eaf48b958f8f3617ce875251c9a4ff7b49885f',
    'scatter-1': '6d4c964b6300bc29beee6fe78b297a88bc6926a07b0f307bcd880b3c38513d84',
    'scatter-3': '5c8e16f35e4c1cece7c9d3574d35b4097181a1c1849a8a9a31b2cb3af10aca56',
    'scatter-6': 'd2ad708e234982eec275850d9941297917cf206462fee25089ae7dccf6ac05ef',
    'scatter': '03c5364edf5ec52486cb46e7feb67296fc64f22c7862303cc954649d6e21eb34',
    'scene-1': '061d36c12e1f4d4736314b4780256cbb89e1dca4c37e853b265d938feb8fbfac',
    'scene-3': '40e995e93c7a008e8b018b4c5fb751f1b5f1cad039cc89e9034cd2445bbdaf64',
    'scene-6': '62f072f1a8a848668001aabc2c493c26c2bf3fc04384966c796e006f398efc13',
    'scene': 'fe49919702fd5a38ffa67f86352e905f4cdf726d3ff171fb4f8199677bff6ea1',
    'single-1': 'cf917c476ca44225a7e960ea7078968a92974d53497492985910f5c8911b9c10',
    'single-3': '1eeead4d12899ba113233192d3250db244f47cc07653891cca6751b6e2f965fd',
    'single-6': '217c249416d2fc67f4e87b556c6a878839aa4fbcd8bea332eb4537837df7ef35',
    'single': '60bd4bb94da13495518ff00372054b05385d2deac0a5a92741b04631b2111241',
    'split-1': '7ed632109e63f91b78441590df363d02f33f0ccb4d1de310e6ba3c934afcf7ce',
    'split-3': 'e1f28ed4096bdbcf499de78b3d66d1c7a6015b17b9a27b9947d35ff719ecff48',
    'split-6': '915d8816bac63fb753615639b47708be5ed361d86434346d11d082e2bca10d5e',
    'split': '43aaa7004fbefb1339a50758f2f8d02f4ac213f3cf77a02434c1ff1ff32fc663',
    'stacked-1': '981f33ddb132c2b2b54dac086433ba6e896a74b94ca11e21228e52c5e6042d5f',
    'stacked-3': '5e9ece2b7321e01c9fe2dc4f8ba6e9e37b9ad4385561145acbecc448e33b13c3',
    'stacked-6': '1b79aca00a6f52770c9e408de69522872529ab3b3f52a5090fedaccbacb15545',
    'stacked': '7391253d89bf7bbb209e00da60ad11cb30603fb78f54c6150e673dc6e03071aa',
    'stagger-1': '3c6f32e22aeaaac32e82cc25ab742785528cd8bd865582f23a4a4ad4538e4ff4',
    'stagger-3': 'd9baa3f58b6afe4835a8b0cd6c3c8f2b30e64c4e018cefcab68e9c8d54c4133b',
    'stagger-6': 'a852c8b5062b22474888b4ebd0b0644bea035c41ccb3694f5cf2fbff86472d98',
    'stagger': '32890f98536edf1141873d238e26d35ce1934fd862e1bdc262c5b9ec122708d4',
}
PUBLIC_THUMBNAILS = {
    prefix + mode + '.webp': sha
    for prefix in ('hsd_tool/static/ribbon/layout-v2/', 'ribbon_frontend/public/layout-v2/')
    for mode, sha in LAYOUT_WEBP_SHA256.items()
}
PUBLIC_THUMBNAILS.update({
    prefix + name + '.webp': sha
    for prefix in ('hsd_tool/static/ribbon/layout-v3/', 'ribbon_frontend/public/layout-v3/')
    for name, sha in LAYOUT_V3_WEBP_SHA256.items()
})
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
    'ribbon_frontend/tests/api.test.mjs', 'ribbon_frontend/tests/browser-smoke.mjs',
    'ribbon_frontend/tests/workspace-performance.mjs', 'ribbon_frontend/tests/loop-preview.mjs',
    'ribbon_frontend/tests/refinement-receipt.mjs', 'ribbon_frontend/tests/trial-integration.mjs',
    'ribbon_frontend/tests/workspace-without-refinement.mjs'})
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
    'ribbon_backend/loop_layout_v3.py', 'ribbon_backend/loop_pipeline_v3.py',
    'ribbon_frontend/package.json', 'ribbon_frontend/tsconfig.json', 'ribbon_frontend/pnpm-lock.yaml',
    'ribbon_frontend/vite.config.ts', 'ribbon_frontend/src/embed.tsx',
    'requirements-cloud.txt', 'deploy/cloud.env.example', 'deploy/hsd-agent.service.example',
    'deploy/nginx-hsd.conf.example', 'deploy/hsd-storage.mount.example',
    'deploy/hsd-healthcheck.sh', 'deploy/hsd-healthcheck.service', 'deploy/hsd-healthcheck.timer',
    'deploy/backup.sh', '.gitattributes', 'README.md', 'AGENTS.md', 'CONTRACTS.md',
    'tools/material_demo/index.html', 'tools/material_demo/demo.js', 'tools/material_demo/demo.css'}) | DEMO_SVG_FILES | frozenset(PUBLIC_THUMBNAILS)


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
    if name in PUBLIC_THUMBNAILS:
        return
    require(path.suffix.casefold() not in FORBIDDEN_SUFFIXES, 'Binary or business attachment refused')
    require(path.suffix.casefold() != '.json' or name in JSON_FILES, 'JSON is outside the exact release whitelist')
    ribbon_backend = len(path.parts) == 2 and path.parts[0] == 'ribbon_backend' and path.suffix == '.py'
    ribbon_frontend = len(path.parts) > 2 and path.parts[:2] == ('ribbon_frontend', 'src') and path.suffix in {'.ts', '.tsx', '.css'}
    existing_source = len(path.parts) > 1 and path.parts[0] in SOURCE_ROOTS and path.suffix.casefold() in SOURCE_SUFFIXES
    require(name in ROOT_FILES or name in DEMO_SVG_FILES or name in FRONTEND_CONFIG_FILES
        or ribbon_backend or ribbon_frontend or existing_source, 'Source is outside the closed release whitelist: ' + name)


def scan(name, value):
    public_name(name)
    if name in PUBLIC_THUMBNAILS:
        require(isinstance(value, bytes) and digest(value) == PUBLIC_THUMBNAILS[name],
                'Synthetic thumbnail differs from the reviewed bytes: ' + name)
        return
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
        dependency_binaries_included=False, windows_binary_included=False,
        explicit_exclusions=sorted(EXCLUDED | {directory + '/' for directory in EXCLUDED_DIRECTORIES}))


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
        if name in EXCLUDED or any(name.startswith(directory + '/') for directory in EXCLUDED_DIRECTORIES):
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
