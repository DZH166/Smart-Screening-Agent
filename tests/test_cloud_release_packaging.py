"""Synthetic packaging checks: no Git changes, credentials or business inputs."""
from datetime import date
from io import BytesIO
import json
from pathlib import Path
import tarfile

import pytest

from tools import prepare_cloud_release as release


@pytest.mark.parametrize('name', [
    '.gitattributes', 'README.md', 'hsd_tool/server.py', 'hsd_tool/static/material.js',
    'hsd_tool/static/ribbon/ribbon.js', 'ribbon_backend/providers.py',
    'ribbon_frontend/src/App.tsx', 'ribbon_frontend/src/api.ts', 'ribbon_frontend/src/styles.css',
    'hsd_tool/ribbon_examples.py', 'ribbon_frontend/src/LayoutExamples.tsx',
    'ribbon_frontend/package.json', 'ribbon_frontend/tsconfig.json', 'ribbon_frontend/vite.config.ts',
    'ribbon_frontend/pnpm-lock.yaml', 'ribbon_frontend/.gitignore', 'ribbon_frontend/index.html',
    'ribbon_frontend/tests/api.test.mjs', 'deploy/backup.sh', 'deploy/hsd-healthcheck.service',
    'deploy/hsd-healthcheck.timer', 'deploy/hsd-agent.service.example', 'docs/ribbon-providers.md',
    'tests/ribbon/test_workflow.py', 'tools/material_demo/assets/flower.svg'])
def test_closed_allowlist_keeps_required_public_sources(name):
    release.public_name(name)


@pytest.mark.parametrize('name', [
    'hsd_tool/static/ribbon_layout_examples/HSD31620.jpg',
    'hsd_tool/ribbon_layout_examples/provenance.md',
    'ribbon_layout_examples/catalog.txt',
])
def test_company_reference_files_never_enter_public_release(name):
    with pytest.raises(RuntimeError):
        release.public_name(name)


@pytest.mark.parametrize('name', [
    '../README.md', '/README.md', 'C:/README.md', 'hsd_tool\\server.py', 'hsd_tool/../README.md',
    'hsd_tool//server.py', 'hsd_tool/server.py\x00', 'hsd_tool/server.py\n',
    'tests/sample_visual_reference.json', 'tests/sample_visual_reference.JSON',
    'tests/arbitrary.json', 'hsd_tool/static/ribbon/config.json', 'ribbon_backend/config.json',
    'ribbon_frontend/new-package.json', 'ribbon_frontend/src/unknown.json',
    'ribbon_frontend/node_modules/react/index.js', 'ribbon_frontend/dist/bundle.js',
    'ribbon_frontend/test-results/page.html', 'ribbon_backend/data/private.py',
    'hsd_tool/cache/images.py', 'docs/codex-handoff/PRODUCT_SPEC.md',
    'hsd_tool/.env', 'hsd_tool/ribbon_model_settings.json', 'hsd_tool/credential.key',
    'docs/reference.png', 'docs/original.docx', 'tools/archive.zip', 'tests/session.db',
    'hsd_tool/static/ribbon/runtime.log', 'ribbon_frontend/assets/reference.svg',
    'tools/material_demo/assets/unknown.svg', 'unknown/public.py'])
def test_private_binary_unknown_configuration_and_unsafe_names_refused(name):
    with pytest.raises(RuntimeError):
        release.public_name(name)


@pytest.mark.parametrize('value', [b'\xff\xfeinvalid', b'print(1)\0binary', b'<<<<<<< unresolved\n'])
def test_binary_or_conflicted_bytes_cannot_hide_in_py(value):
    with pytest.raises(RuntimeError):
        release.scan('hsd_tool/module.py', value)


@pytest.mark.parametrize('name', ['deploy/test.sh', 'deploy/test.service',
    'deploy/test.timer', 'deploy/test.service.example', '.gitattributes'])
def test_linux_source_requires_committed_lf_without_rewriting(name):
    release.scan(name, b'# synthetic\n')
    with pytest.raises(RuntimeError, match='LF'):
        release.scan(name, b'# synthetic\r\n')


def test_secret_pattern_failure_does_not_print_the_value():
    secret = b'sk-' + b'Q9' * 24
    with pytest.raises(RuntimeError) as error:
        release.scan('hsd_tool/module.py', b'TOKEN = "' + secret + b'"\n')
    assert secret.decode() not in str(error.value)
    with pytest.raises(RuntimeError):
        release.scan('tests/test_new.py', b'TOKEN = "' + secret + b'"\n')
    dummy = b'sk-' + b'synthetic-dummy-never-real'
    release.scan('tests/test_new.py', b'TOKEN = "' + dummy + b'"\n')
    with pytest.raises(RuntimeError):
        release.scan('hsd_tool/module.py', b'TOKEN = "' + dummy + b'"\n')


def test_only_reviewed_demo_svg_names_and_safe_svg_content():
    path = 'tools/material_demo/assets/flower.svg'
    release.scan(path, b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>')
    for value in (b'<svg><script>1</script></svg>', b'<svg><use href="https://invalid"/></svg>', b'<broken>'):
        with pytest.raises(RuntimeError):
            release.scan(path, value)


def files():
    return {'hsd_tool/__init__.py': ('100644', b'__version__ = "9.8.7"\n'),
            'README.md': ('100644', b'Synthetic public source\n'),
            'deploy/check.sh': ('100755', b'#!/bin/sh\nexit 0\n')}


def test_archive_is_reproducible_with_exact_modes_and_manifest_hashes():
    sources = files()
    manifest = release.create_manifest(sources, 'a' * 40, date(2026, 10, 28))
    encoded = release.json_bytes(manifest)
    packed = release.build_archive(sources, encoded, 100000)
    assert packed == release.build_archive(sources, encoded, 100000)
    assert release.verify_archive(packed, manifest['source_files'], encoded) == 4
    assert manifest['version'] == '9.8.7' and manifest['tag'] == 'v9.8.7'
    assert manifest['explicit_exclusions'] == sorted([
        'tests/sample_visual_reference.json',
        'docs/preview/admin-key-ledger-desktop.png',
        'docs/preview/admin-key-ledger-narrow.png',
        'docs/preview/admin-key-ledger.html',
        'docs/preview/ribbon-model-service.html',
        'docs/preview/ribbon-model-service.png',
    ])
    with tarfile.open(fileobj=BytesIO(packed), mode='r:gz') as archive:
        assert archive.getmember('deploy/check.sh').mode == 0o755
        assert archive.extractfile('README.md').read() == sources['README.md'][1]
        stored = json.load(archive.extractfile(release.MANIFEST_NAME))
        assert stored['source_files']['README.md'] == release.digest(sources['README.md'][1])
    altered = dict(manifest['source_files'], **{'README.md': '0' * 64})
    with pytest.raises(RuntimeError):
        release.verify_archive(packed, altered, encoded)


def test_archive_cannot_include_symlink_mode_or_business_answer_map():
    for name, mode in [('README.md', '120000'), ('tests/sample_visual_reference.json', '100644')]:
        with pytest.raises(RuntimeError):
            release.build_archive({name: (mode, b'data')}, b'{}', 100000)


def test_verify_archive_rejects_unknown_file_and_links():
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        info = tarfile.TarInfo('../outside')
        info.type = tarfile.SYMTYPE
        info.linkname = '/private'
        archive.addfile(info)
    with pytest.raises(RuntimeError):
        release.verify_archive(buffer.getvalue(), {}, b'{}')


@pytest.mark.parametrize('value', [b'__version__="../escape"', b'__version__=False',
    b'__version__="1.2.3"\n__version__="1.2.4"', b'__version__=call()'])
def test_version_is_literal_and_cannot_control_destination(value):
    with pytest.raises((RuntimeError, ValueError)):
        release.committed_version(value)


def test_clean_head_rejects_any_uncommitted_or_untracked_public_change(monkeypatch,tmp_path):
    monkeypatch.setattr(release, 'git', lambda *args, **kw: b'?? new-file.py\0')
    with pytest.raises(RuntimeError, match='Commit public'):
        release.clean_head(tmp_path)


def test_assemble_writes_only_versioned_artifacts_and_exact_checksum(monkeypatch,tmp_path):
    commit='a'*40
    monkeypatch.setattr(release,'clean_head',lambda repo:commit)
    monkeypatch.setattr(release,'committed_files',lambda repo,revision:files())
    monkeypatch.setattr(release,'git',lambda *args,**kw:b'1700000000\n')
    result=release.assemble(tmp_path,commit,date(2026,10,28))
    output=tmp_path/'交付'/'v9.8.7'
    assert {p.name for p in output.iterdir()} == {
        'HSD-Image-Numbering-Cloud-v9.8.7.tar.gz','release-manifest.json','SHA256.txt'}
    checks=(output/'SHA256.txt').read_text().splitlines()
    for row in checks:
        digest,name=row.split('  ',1)
        assert digest==release.digest((output/name).read_bytes())
    assert result['git_blob_bytes_verified'] and result['archive_entries_verified']
    assert release.assemble(tmp_path,commit,date(2026,10,28))==result
    assert all(Path(a['path']).is_relative_to(output) for a in result['artifacts'])
    with pytest.raises(RuntimeError,match='full current clean HEAD'):
        release.assemble(tmp_path,'b'*40)


def test_destination_never_escapes_or_overwrites_different_existing_bytes(tmp_path):
    with pytest.raises(RuntimeError):
        release.safe_destination(tmp_path,tmp_path.parent/'outside')
    target=tmp_path/'out.txt'
    release.write_exact(tmp_path,target,b'first')
    release.write_exact(tmp_path,target,b'first')
    with pytest.raises(RuntimeError,match='refusing overwrite'):
        release.write_exact(tmp_path,target,b'second')
    assert target.read_bytes()==b'first'


def test_git_blob_bytes_are_used_instead_of_worktree(tmp_path,monkeypatch):
    identity='b'*40
    (tmp_path/'README.md').write_bytes(b'private uncommitted local value')
    blob=b'committed public bytes\n'
    def fake_git(repo,*args,data=None):
        if args[0]=='ls-tree':
            return ('100644 blob '+identity+'\tREADME.md\0').encode()
        assert args==('cat-file','--batch') and data==(identity+'\n').encode()
        return (identity+' blob '+str(len(blob))+'\n').encode()+blob+b'\n'
    monkeypatch.setattr(release,'git',fake_git)
    monkeypatch.setattr(release,'REQUIRED_FILES',{'README.md'})
    assert release.committed_files(tmp_path,'a'*40)=={'README.md':('100644',blob)}


@pytest.mark.parametrize('entry',[b'120000 blob ',b'160000 commit '])
def test_git_links_and_submodules_rejected_before_blob_loading(tmp_path,monkeypatch,entry):
    def fake_git(repo,*args,**kwargs):
        assert args[0]=='ls-tree'
        return entry+b'b'*40+b'\tREADME.md\0'
    monkeypatch.setattr(release,'git',fake_git)
    with pytest.raises(RuntimeError,match='linked Git source'):
        release.committed_files(tmp_path,'a'*40)
