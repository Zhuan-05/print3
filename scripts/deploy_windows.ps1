param([string]$Mode = '')
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
if ($Mode -notin @('', 'reconfigure')) { throw 'Usage: deploy_print3d.bat [reconfigure]' }
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
$distros = @()
if ($wsl) {
    $distros = @(& wsl.exe --list --quiet 2>$null | ForEach-Object { ($_ -replace "`0", '').Trim() } | Where-Object { $_ })
}
$distro = $distros | Where-Object { $_ -eq 'Ubuntu-24.04' } | Select-Object -First 1
if (-not $distro) { $distro = $distros | Where-Object { $_ -match '^Ubuntu' } | Select-Object -First 1 }
if (-not $distro) {
    Write-Host 'WSL Ubuntu 24.04 is required. Windows will request administrator permission to install it.'
    $install = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -ArgumentList @('-NoProfile', '-Command', 'wsl.exe --install -d Ubuntu-24.04 --no-launch; exit $LASTEXITCODE')
    Write-Host 'If Windows requests a restart, restart now. Open Ubuntu-24.04, create your Linux username/password, then double-click deploy_print3d.bat again.'
    exit 1
}
Write-Host "Using $distro. If prompted, complete Ubuntu username/password setup."
& wsl.exe --distribution $distro --cd $projectPath --exec bash ./scripts/deploy.sh $Mode
exit $LASTEXITCODE
