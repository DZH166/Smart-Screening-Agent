$ErrorActionPreference = 'Stop'
$workspace = $PSScriptRoot
$pythonExe = Join-Path $workspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw '请先建立 .venv，并安装 requirements-dev.txt。'
}
Push-Location -LiteralPath $workspace
try {
    & $pythonExe -m PyInstaller --noconfirm --clean --onedir --windowed --name 'HSD图号助手' --add-data 'hsd_tool/static;hsd_tool/static' --hidden-import tkinter --hidden-import tkinter.filedialog --exclude-module pandas --exclude-module openpyxl --exclude-module pytest --exclude-module scipy --exclude-module matplotlib --collect-all pymupdf launch.py
    if ($LASTEXITCODE -ne 0) { throw '打包失败。' }
    $destination = Join-Path $workspace 'dist\HSD图号助手'
    Copy-Item -LiteralPath (Join-Path $workspace '使用说明.txt') -Destination $destination -Force
    $sourceDestination = Join-Path $destination '源代码'
    New-Item -ItemType Directory -Path $sourceDestination -Force | Out-Null
    $packageDestination = Join-Path $sourceDestination 'hsd_tool'
    New-Item -ItemType Directory -Path $packageDestination -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $workspace 'hsd_tool') -File -Filter '*.py' | Copy-Item -Destination $packageDestination -Force
    Copy-Item -LiteralPath (Join-Path $workspace 'hsd_tool\static') -Destination $packageDestination -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $workspace 'tests') -Destination $sourceDestination -Recurse -Force
    $toolsDestination = Join-Path $sourceDestination 'tools'
    New-Item -ItemType Directory -Path $toolsDestination -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $workspace 'tools\collect_licenses.py') -Destination $toolsDestination -Force
    foreach ($file in @('launch.py', 'requirements.txt', 'requirements-dev.txt', 'build.ps1', 'README.md', '使用说明.txt')) {
        Copy-Item -LiteralPath (Join-Path $workspace $file) -Destination $sourceDestination -Force
    }
    & $pythonExe tools\collect_licenses.py $destination
    if ($LASTEXITCODE -ne 0) { throw '依赖说明生成失败。' }
    Write-Output ('已生成：' + (Join-Path $destination 'HSD图号助手.exe'))
}
finally {
    Pop-Location
}
