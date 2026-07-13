<#
    WR-0152 Phase 1 Discovery - Section 1: Environments

    Covers:
      - List of all environments (Default, Dev, Test, Prod)
      - Region / data residency
      - Environment type (Production, Sandbox)
      - Environment owners / admins
      - Environment purpose (business system vs end-user vs legacy)  [heuristic - confirm manually]

    Requires: Microsoft.PowerApps.Administration.PowerShell
    Permissions: Power Platform Administrator (or Global Admin) for tenant-wide visibility.
#>

param(
    [string]$OutputFolder = (New-DiscoveryOutputFolder)
)

. "$PSScriptRoot/Common.ps1"
Connect-PPAdmin

function Get-InferredPurpose {
    param($Environment)

    if ($Environment.IsDefault) { return "End-user / Default (unmanaged app & flow creation)" }

    $name = "$($Environment.DisplayName)".ToLower()
    if ($name -match "scribe|d365|dynamics") { return "Business system (confirm: Scribe/D365 integration)" }
    if ($name -match "\bdev\b|\btest\b|\buat\b|\bqa\b|sandbox") { return "Dev/Test - non-production" }
    if ($name -match "\bprod\b|production|live") { return "Production - purpose-built" }

    return "Unclassified - confirm with environment owner"
}

Write-Host "Collecting Power Platform environments..."
$environments = Get-AdminPowerAppEnvironment

$results = foreach ($env in $environments) {
    # Environment admins/owners come from the environment's role assignments, not the
    # environment object itself - a second call is required per environment.
    $admins = Get-AdminPowerAppEnvironmentRoleAssignment -EnvironmentName $env.EnvironmentName -ErrorAction SilentlyContinue |
        Where-Object { $_.RoleType -eq 'System' -and $_.RoleName -in @('Environment Admin', 'System Administrator') } |
        ForEach-Object { $_.PrincipalDisplayName }

    [PSCustomObject]@{
        EnvironmentName   = $env.EnvironmentName
        DisplayName       = $env.DisplayName
        IsDefault         = $env.IsDefault
        EnvironmentType   = $env.EnvironmentType          # Production / Sandbox / Trial / Default / Developer
        Region            = $env.Location                 # data residency
        CreatedTime       = $env.CreatedTime
        CreatedBy         = $env.CreatedBy.displayName
        Admins            = ($admins -join '; ')
        DataverseInstance = $env.Internal.linkedEnvironmentMetadata.instanceUrl
        InferredPurpose   = Get-InferredPurpose -Environment $env
    }
}

Export-Discovery -Data $results -OutputFolder $OutputFolder -Name "01-Environments"

Write-Host "Note: 'InferredPurpose' is a heuristic based on naming and default-environment status." -ForegroundColor Yellow
Write-Host "      Confirm actual business-system / end-user / legacy classification with each environment owner." -ForegroundColor Yellow
