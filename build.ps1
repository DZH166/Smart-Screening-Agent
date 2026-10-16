$ErrorActionPreference = 'Stop'
$workspace = $PSScriptRoot
$pythonExe = Join-Path $workspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw '请先建立 .venv，并安装 requirements-dev.txt。'
}
Push-Location -LiteralPath $workspace
try {
    $version = (& $pythonExe -c 'from hsd_tool import __version__; print(__version__)').Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+$') { throw '发布版本号格式不正确。' }
    $distributionRoot = Join-Path $workspace ('dist\v' + $version)
    $buildRoot = Join-Path $workspace ('build\v' + $version)
    New-Item -ItemType Directory -Path $buildRoot -Force | Out-Null
    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed --name 'HSD图号助手' --distpath $distributionRoot --workpath $buildRoot --specpath $buildRoot --add-data (Join-Path $workspace 'hsd_tool/static;hsd_tool/static') --hidden-import tkinter --hidden-import tkinter.filedialog --exclude-module pandas --exclude-module openpyxl --exclude-module pytest --exclude-module scipy --exclude-module matplotlib --collect-all pymupdf launch.py
    if ($LASTEXITCODE -ne 0) { throw '打包失败。' }
    $destination = Join-Path $distributionRoot 'HSD图号助手'
    Copy-Item -LiteralPath (Join-Path $workspace '使用说明.txt') -Destination $destination -Force
    $sourceDestination = Join-Path $destination '源代码'
    New-Item -ItemType Directory -Path $sourceDestination -Force | Out-Null
    foreach ($directory in @('hsd_tool', 'tests', 'tools')) {
        Get-ChildItem -LiteralPath (Join-Path $workspace $directory) -File -Recurse | Where-Object { $_.Extension -in @('.py', '.js', '.css', '.html', '.json') } | ForEach-Object {
            $relative = $_.FullName.Substring($workspace.Length + 1)
            if ($relative -eq 'tests\sample_visual_reference.json') { return }
            $targetFile = Join-Path $sourceDestination $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $targetFile) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $targetFile -Force
        }
    }
    foreach ($file in @('launch.py', 'requirements.txt', 'requirements-dev.txt', 'build.ps1', 'README.md', 'AGENTS.md', 'CONTRACTS.md', 'CHANGELOG.md', '使用说明.txt')) {
        Copy-Item -LiteralPath (Join-Path $workspace $file) -Destination $sourceDestination -Force
    }
    $documentationDestination = Join-Path $sourceDestination 'docs'
    New-Item -ItemType Directory -Path $documentationDestination -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $workspace 'docs') -File -Filter '*.md' | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $documentationDestination -Force
    }
    & $pythonExe tools\collect_licenses.py $destination
    if ($LASTEXITCODE -ne 0) { throw '依赖说明生成失败。' }
    & $pythonExe tools\build_manifest.py $destination
    if ($LASTEXITCODE -ne 0) { throw '构建校验生成失败。' }
    Write-Output ('已生成：' + (Join-Path $destination 'HSD图号助手.exe'))
}
finally {
    Pop-Location
}
