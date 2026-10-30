<#
Adds (or replaces) the dbe_owner entry in the current user's pgpass.conf.

The password is typed at a hidden prompt and written only to that file. It is never echoed,
stored in this repository or passed on a command line.

Usage, from the repository root:
    powershell -ExecutionPolicy Bypass -File scripts\set_pgpass.ps1

Dot-sourcing the script (". scripts\set_pgpass.ps1") only defines Set-PgpassEntry, so the file
handling can be tested without a prompt.
#>
param(
    [string]$HostName = "localhost",
    [int]$Port = 5432,
    [string]$User = "dbe_owner"
)
$ErrorActionPreference = "Stop"

function Set-PgpassEntry {
    param(
        [Parameter(Mandatory)][string]$File,
        [Parameter(Mandatory)][string]$HostName,
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$User,
        [Parameter(Mandatory)][string]$Password
    )
    # pgpass.conf escapes ':' and '\' with a backslash.
    $escaped = $Password.Replace('\', '\\').Replace(':', '\:')
    $prefix = "${HostName}:${Port}:*:${User}:"

    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $File) | Out-Null

    # Keep every other entry. An older line for the same host, port and user is dropped, because
    # libpq uses the first matching line.
    $kept = @()
    if (Test-Path -LiteralPath $File) {
        $kept = @(Get-Content -LiteralPath $File -Encoding UTF8 | Where-Object { -not $_.StartsWith($prefix) })
    }
    $lines = [string[]]($kept + ($prefix + $escaped))

    # UTF-8 without a byte-order mark: Windows PowerShell's -Encoding UTF8 would add one, and it would
    # become part of the first host name so that line would never match.
    [IO.File]::WriteAllLines($File, $lines, (New-Object Text.UTF8Encoding($false)))
}

if ($MyInvocation.InvocationName -eq '.') {
    return
}

$secure = Read-Host "Password for $User" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if ([string]::IsNullOrEmpty($password)) {
    throw "Empty password; nothing written."
}

$file = Join-Path (Join-Path $env:APPDATA "postgresql") "pgpass.conf"
Set-PgpassEntry -File $file -HostName $HostName -Port $Port -User $User -Password $password
Write-Host "Wrote the entry for $User@${HostName}:$Port to $file"
