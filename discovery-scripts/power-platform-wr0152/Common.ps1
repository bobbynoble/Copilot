<#
    Shared helpers for the WR-0152 Power Platform discovery scripts.
    Dot-sourced by 01-04 and by Run-AllDiscovery.ps1 - not meant to be run directly.
#>

function New-DiscoveryOutputFolder {
    param([string]$OutputPath = "./output")

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $folder = Join-Path $OutputPath $stamp
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    return $folder
}

function Export-Discovery {
    param(
        [Parameter(Mandatory)] $Data,
        [Parameter(Mandatory)][string]$OutputFolder,
        [Parameter(Mandatory)][string]$Name
    )

    if (-not $Data -or @($Data).Count -eq 0) {
        Write-Warning "No data collected for '$Name' - skipping export."
        return
    }

    $csvPath  = Join-Path $OutputFolder "$Name.csv"
    $jsonPath = Join-Path $OutputFolder "$Name.json"

    $Data | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
    $Data | ConvertTo-Json -Depth 10 | Out-File -FilePath $jsonPath -Encoding UTF8

    Write-Host "  -> $Name : $(@($Data).Count) record(s) written to $csvPath"
}

function Connect-PPAdmin {
    if (-not (Get-Module -ListAvailable -Name Microsoft.PowerApps.Administration.PowerShell)) {
        throw "Module Microsoft.PowerApps.Administration.PowerShell is not installed. Run: Install-Module Microsoft.PowerApps.Administration.PowerShell -Scope CurrentUser"
    }
    Import-Module Microsoft.PowerApps.Administration.PowerShell -ErrorAction Stop

    if (-not $Global:PPDiscoveryConnected) {
        Write-Host "Connecting to Power Platform admin services (interactive sign-in)..."
        Add-PowerAppsAccount | Out-Null
        $Global:PPDiscoveryConnected = $true
    }
}

function Connect-PBIAdmin {
    if (-not (Get-Module -ListAvailable -Name MicrosoftPowerBIMgmt)) {
        throw "Module MicrosoftPowerBIMgmt is not installed. Run: Install-Module MicrosoftPowerBIMgmt -Scope CurrentUser"
    }
    Import-Module MicrosoftPowerBIMgmt -ErrorAction Stop

    if (-not (Get-PowerBIAccessToken -ErrorAction SilentlyContinue)) {
        Write-Host "Connecting to Power BI Service (interactive sign-in)..."
        Connect-PowerBIServiceAccount | Out-Null
    }
}

function Connect-GraphAdmin {
    param([string[]]$Scopes = @("Policy.Read.All"))

    if (-not (Get-Module -ListAvailable -Name Microsoft.Graph.Identity.SignIns)) {
        throw "Module Microsoft.Graph.Identity.SignIns is not installed. Run: Install-Module Microsoft.Graph -Scope CurrentUser"
    }
    Import-Module Microsoft.Graph.Identity.SignIns -ErrorAction Stop

    if (-not (Get-MgContext)) {
        Write-Host "Connecting to Microsoft Graph (interactive sign-in, scopes: $($Scopes -join ', '))..."
        Connect-MgGraph -Scopes $Scopes -NoWelcome | Out-Null
    }
}

# Known first-party Entra ID app IDs for Power Platform workloads.
# Verify these against your tenant's enterprise applications before relying on them -
# Microsoft occasionally adds tenant-specific or sovereign-cloud variants.
$Script:PowerPlatformAppIds = @{
    "PowerApps"      = "475226c6-020e-4fb2-8a90-7a972cbfc1d4"
    "PowerAutomate"  = "7ab7862c-4c57-491e-8a45-d52a7e023983"
    "Dataverse"      = "00000007-0000-0000-c000-000000000000"
}
