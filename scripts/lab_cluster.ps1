<#
.SYNOPSIS
    Create or remove a throwaway PostgreSQL cluster for this project's tests, benchmarks and demo.

.DESCRIPTION
    create  initdb in -DataDir (builtin C.UTF-8 locale, English server messages, trust
            authentication), start it on -Port listening on localhost only, then run
            olist-dbe bootstrap, init and load against it.
    remove  stop the cluster and delete -DataDir. Only a folder that holds a cluster (PG_VERSION) is
            deleted.

    Trust authentication means no password exists or is needed, and any local user can connect to
    this cluster while it runs. Remove it when you are done. The shared PostgreSQL service is never
    touched: port 5432 is refused.

    The olist-dbe commands read OLIST_DBE_PORT. A script run with -File cannot set it in your
    session, so after `create`, set it yourself as the last line printed says.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\lab_cluster.ps1 create
    powershell -ExecutionPolicy Bypass -File scripts\lab_cluster.ps1 remove
#>
param(
    [Parameter(Position = 0)][ValidateSet('create', 'remove')][string]$Action = 'create',
    [int]$Port = 55433,
    [string]$DataDir = (Join-Path $env:TEMP 'olist-dbe-lab'),
    [string]$PgBin = $(if ($env:OLIST_DBE_PG_BIN) { $env:OLIST_DBE_PG_BIN } else { 'C:\Program Files\PostgreSQL\18\bin' })
)
$ErrorActionPreference = 'Stop'

if ($Port -eq 5432) { throw 'Port 5432 is the shared PostgreSQL service. Choose another port.' }
$repo = Split-Path -Parent $PSScriptRoot
$cli = Join-Path $repo '.venv\Scripts\olist-dbe.exe'
$pgCtl = Join-Path $PgBin 'pg_ctl.exe'

function Invoke-Step([string]$What, [scriptblock]$Command) {
    Write-Host "== $What"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit status $LASTEXITCODE)" }
}

if ($Action -eq 'remove') {
    if (-not (Test-Path (Join-Path $DataDir 'PG_VERSION'))) { throw "$DataDir does not hold a PostgreSQL cluster." }
    & $pgCtl -D $DataDir status *> $null
    if ($LASTEXITCODE -eq 0) { Invoke-Step 'stop the cluster' { & $pgCtl -D $DataDir -m fast -w stop } }
    Remove-Item -Recurse -Force -Confirm:$false $DataDir
    Write-Host "Removed $DataDir."
    return
}

if (Test-Path $DataDir) { throw "$DataDir already exists. Remove it first: scripts\lab_cluster.ps1 remove" }
if (-not (Test-Path $cli)) { throw "$cli not found. Install the package first (README, quick start step 1)." }

Invoke-Step 'initdb' {
    & (Join-Path $PgBin 'initdb.exe') -D $DataDir -U postgres -A trust -E UTF8 `
        --locale-provider=builtin --builtin-locale=C.UTF-8 --lc-messages=C
}
Write-Host "== start on port $Port (localhost only)"
# Started through the shell, so the server inherits none of this script's handles: run with &, it
# would keep this script's output pipe open, and a pipeline reading it would never end.
$log = Join-Path $DataDir 'server.log'
$start = Start-Process -FilePath $pgCtl -WindowStyle Hidden -PassThru -ArgumentList (
    "-D `"$DataDir`" -l `"$log`" -o `"-p $Port -c listen_addresses=localhost`" -w start")
$start.WaitForExit()  # pg_ctl only; Start-Process -Wait would also wait for the server
if ($start.ExitCode -ne 0) { throw "pg_ctl start failed (exit status $($start.ExitCode)); see $log" }
$env:OLIST_DBE_PORT = "$Port"
$env:OLIST_DBE_PG_BIN = $PgBin
Invoke-Step 'bootstrap' { & $cli bootstrap --port $Port --admin-db postgres }
Invoke-Step 'check' { & $cli check }
Invoke-Step 'init' { & $cli init }
Invoke-Step 'load' { & $cli load }

Write-Host ''
Write-Host "Cluster ready in $DataDir. In your PowerShell session, run:"
Write-Host "    `$env:OLIST_DBE_PORT = '$Port'; `$env:OLIST_DBE_PG_BIN = '$PgBin'"
