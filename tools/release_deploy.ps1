# Release with an explicit integrity check.
#
# 2026-11-06: a failed scp let the server deploy a stale /tmp archive and the
# site briefly ran an older version. This script refuses to deploy unless the
# archive on the server is byte-identical to the one just built here, and it
# re-reads X-HSD-Build afterwards.
param(
    [string]$Remote = "hsd-server",
    [switch]$SkipBusyCheck
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$head = (git rev-parse HEAD).Trim()
$short = $head.Substring(0, 8)
Write-Host "release commit: $head"

if (-not $SkipBusyCheck) {
    $busy = (ssh $Remote "bash /tmp/check_busy.sh 2>/dev/null").Trim()
    Write-Host $busy
    if ($busy -notmatch "busy jobs: 0") { throw "远端仍有任务，先确认再发布：$busy" }
}

git archive --format=tar.gz -o tmp/release.tgz HEAD
if ($LASTEXITCODE -ne 0) { throw "git archive failed" }
$head | Set-Content -NoNewline tmp\release-sha

scp -q tmp/release.tgz tmp/release-sha "${Remote}:/tmp/"
if ($LASTEXITCODE -ne 0) { throw "scp failed — refuse to deploy a possibly stale archive" }

$local = (Get-FileHash tmp\release.tgz -Algorithm SHA256).Hash.ToLower()
$remoteHash = (ssh $Remote "sha256sum /tmp/release.tgz | cut -d' ' -f1").Trim()
Write-Host "local  sha256: $local"
Write-Host "remote sha256: $remoteHash"
if ($local -ne $remoteHash) { throw "archive mismatch: refusing to deploy" }

$remoteSha = (ssh $Remote "cat /tmp/release-sha").Trim()
if ($remoteSha -ne $head) { throw "release-sha mismatch: $remoteSha vs $head" }

# Rapid repeated releases can trip systemd's start limit, leaving the unit
# failed even though the code is fine. Clear the limit first, and recover once
# if the restart inside deploy.sh still ends up rate-limited.
ssh $Remote "systemctl reset-failed hsd-agent.service 2>/dev/null; true"
ssh $Remote "bash /tmp/deploy.sh"
if ($LASTEXITCODE -ne 0) {
    $state = (ssh $Remote "systemctl is-active hsd-agent.service").Trim()
    if ($state -ne "active") {
        Write-Warning "deploy.sh exited non-zero and the unit is '$state'; retrying with reset-failed"
        ssh $Remote "systemctl reset-failed hsd-agent.service; systemctl start hsd-agent.service"
        Start-Sleep -Seconds 4
        $state = (ssh $Remote "systemctl is-active hsd-agent.service").Trim()
        if ($state -ne "active") { throw "service did not recover after deploy: $state" }
    }
}

$build = (ssh $Remote "curl -sk -H 'Host: 39.106.45.116:8443' -D - -o /dev/null https://127.0.0.1:8443/healthz | grep -i x-hsd-build").Trim()
$current = (ssh $Remote "readlink -f /opt/hsd-agent/current").Trim()
$health = (ssh $Remote "curl -sk -H 'Host: 39.106.45.116:8443' https://127.0.0.1:8443/healthz").Trim()
Write-Host "current: $current"
Write-Host "build:   $build"
Write-Host "health:  $health"
if ($build -notmatch [regex]::Escape($short)) { throw "deployed build does not contain $short — investigate before announcing" }
if ($health -ne "ok") { throw "health check did not return ok" }
Write-Host "release $short is live and verified."
