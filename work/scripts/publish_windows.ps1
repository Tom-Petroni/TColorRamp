param(
    [string]$NukeVersion = "16.0",
    [string]$SourceDll = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($SourceDll)) {
    $SourceDll = Join-Path $repoRoot "target/release/tcolorramp_nuke.dll"
}

if (-not (Test-Path -LiteralPath $SourceDll)) {
    throw "Source DLL introuvable: $SourceDll"
}

$destDir = Join-Path $repoRoot ("TColorRamp/bin/{0}/windows/x86_64" -f $NukeVersion)
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$destDll = Join-Path $destDir "TColorRamp.dll"
Copy-Item -LiteralPath $SourceDll -Destination $destDll -Force

Write-Output "Published: $destDll"

