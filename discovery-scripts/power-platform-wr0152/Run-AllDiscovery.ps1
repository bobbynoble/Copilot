<#
    Runs all four WR-0152 Phase 1 discovery scripts in sequence and writes output to a single
    timestamped folder.

    Usage:
        ./Run-AllDiscovery.ps1
        ./Run-AllDiscovery.ps1 -OutputPath "C:\Discovery\WR-0152"
#>

param(
    [string]$OutputPath = "./output"
)

. "$PSScriptRoot/Common.ps1"

$outputFolder = New-DiscoveryOutputFolder -OutputPath $OutputPath
Write-Host "Discovery output folder: $outputFolder"
Write-Host ""

$scripts = @(
    "01-Environments.ps1",
    "02-PowerBI.ps1",
    "03-Assets.ps1",
    "04-AccessSecurity.ps1"
)

foreach ($script in $scripts) {
    Write-Host "=== Running $script ===" -ForegroundColor Cyan
    try {
        & "$PSScriptRoot/$script" -OutputFolder $outputFolder
    } catch {
        Write-Error "Error running $script : $($_.Exception.Message)"
    }
    Write-Host ""
}

Write-Host "Discovery complete. Results in: $outputFolder" -ForegroundColor Green
