param([int]$Port = 8765)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$root = Split-Path $repo -Parent
$logs = Join-Path $repo '_build\world-region'
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose a port between 1024 and 65535.' }
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Choose another with -Port."
}
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$python = (Get-Command python -ErrorAction Stop).Source
$server = Start-Process -FilePath $python -WindowStyle Hidden -PassThru `
    -ArgumentList @('-m', 'http.server', "$Port", '--protocol', 'HTTP/1.1', '--bind', '127.0.0.1', '--directory', "`"$root`"") `
    -RedirectStandardOutput (Join-Path $logs "server-$Port.stdout.log") `
    -RedirectStandardError (Join-Path $logs "server-$Port.stderr.log")
Write-Output "Local server PID: $($server.Id)"
Write-Output "http://127.0.0.1:$Port/RSDWBaseBuilder/tools/World/preview/index.html"
