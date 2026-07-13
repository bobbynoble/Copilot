<#
    WR-0152 Phase 1 Discovery - Section 3: Asset Discovery (Power Apps & Power Automate)

    Covers:
      - Number of apps (canvas vs model-driven), business-critical vs personal productivity (heuristic),
        apps linked to enterprise systems, orphaned apps
      - Number of flows, flow types (scheduled/trigger-based/business process), failed/inactive flows,
        premium connector usage
      - Cross-workload dependencies: apps using flows, flows using Power BI/APIs, Dataverse dependencies

    Requires: Microsoft.PowerApps.Administration.PowerShell
    Permissions: Power Platform Administrator (or Global Admin) for tenant-wide visibility.

    Known limitation: Get-AdminPowerApp reliably enumerates CANVAS apps. Model-driven apps live in
    Dataverse (table `appmodule`) and are not fully surfaced by this cmdlet - see the
    Get-ModelDrivenAppsForEnvironment function below, which queries Dataverse directly for
    environments that have a Dataverse instance. This requires the caller to have (or acquire) a
    Dataverse-scoped token; if that fails for an environment it is skipped with a warning rather
    than guessed at.
#>

param(
    [string]$OutputFolder = (New-DiscoveryOutputFolder)
)

. "$PSScriptRoot/Common.ps1"
Connect-PPAdmin

Write-Host "Collecting connector tier information (for premium connector detection)..."
$connectors = Get-AdminPowerAppConnector
$premiumConnectorNames = $connectors | Where-Object { $_.Tier -eq 'Premium' } | Select-Object -ExpandProperty Name

function Get-ConnectionReferenceNames {
    param($AppOrFlow)
    # connectionReferences is a dictionary keyed by connector logical name (e.g. shared_sql, shared_powerbi)
    $refs = $AppOrFlow.Internal.properties.connectionReferences
    if (-not $refs) { return @() }
    return $refs.PSObject.Properties | ForEach-Object { $_.Value.apiId -replace '^.*/', '' }
}

function Get-ModelDrivenAppsForEnvironment {
    param($Environment)

    $instanceUrl = $Environment.Internal.linkedEnvironmentMetadata.instanceUrl
    if (-not $instanceUrl) { return @() }

    if (-not (Get-Module -ListAvailable -Name Az.Accounts)) {
        Write-Warning "Az.Accounts module not installed - skipping model-driven app enumeration for '$($Environment.DisplayName)'. Install-Module Az.Accounts, or query the 'appmodule' table manually via pac cli / Dataverse Web API for this environment."
        return @()
    }
    Import-Module Az.Accounts -ErrorAction SilentlyContinue

    try {
        if (-not (Get-AzContext)) { Connect-AzAccount | Out-Null }
        $token = (Get-AzAccessToken -ResourceUrl $instanceUrl -ErrorAction Stop).Token
    } catch {
        Write-Warning "Could not acquire a Dataverse token for '$($Environment.DisplayName)' - skipping model-driven app enumeration. Query the 'appmodule' table manually via pac cli or Dataverse Web API for this environment."
        return @()
    }

    $uri = "$instanceUrl/api/data/v9.2/appmodules?`$select=name,uniquename,createdon,modifiedon,_createdby_value"
    $resp = Invoke-RestMethod -Uri $uri -Headers @{ Authorization = "Bearer $token" } -Method Get
    return $resp.value
}

$environments = Get-AdminPowerAppEnvironment
$appResults = @()
$flowResults = @()

foreach ($env in $environments) {
    Write-Host "Scanning environment: $($env.DisplayName)..."

    $apps = Get-AdminPowerApp -EnvironmentName $env.EnvironmentName -ErrorAction SilentlyContinue
    foreach ($app in $apps) {
        $connRefs = Get-ConnectionReferenceNames -AppOrFlow $app
        $usesDataverse = $connRefs -contains 'shared_commondataserviceforapps'
        $usesFlow      = $connRefs -contains 'shared_flow' -or $connRefs -contains 'shared_logicflows'
        $usesPowerBI   = $connRefs -contains 'shared_powerbi'

        $appResults += [PSCustomObject]@{
            EnvironmentName       = $env.DisplayName
            AppName               = $app.AppName
            DisplayName           = $app.DisplayName
            AppType               = 'Canvas'   # see script header re: model-driven limitation
            Owner                 = $app.Owner.displayName
            CreatedTime           = $app.CreatedTime
            LastModifiedTime      = $app.LastModifiedTime
            IsOrphaned            = [string]::IsNullOrEmpty($app.Owner.displayName)
            ConnectionReferences  = ($connRefs -join '; ')
            UsesPremiumConnector  = [bool]($connRefs | Where-Object { $_ -in $premiumConnectorNames })
            LinkedToDataverse     = $usesDataverse
            CallsFlow             = $usesFlow
            UsesPowerBI           = $usesPowerBI
        }
    }

    $modelDrivenApps = Get-ModelDrivenAppsForEnvironment -Environment $env
    foreach ($mda in $modelDrivenApps) {
        $appResults += [PSCustomObject]@{
            EnvironmentName       = $env.DisplayName
            AppName               = $mda.uniquename
            DisplayName           = $mda.name
            AppType               = 'Model-driven'
            Owner                 = $mda.'_createdby_value'
            CreatedTime           = $mda.createdon
            LastModifiedTime      = $mda.modifiedon
            IsOrphaned            = $false
            ConnectionReferences  = $null
            UsesPremiumConnector  = $null
            LinkedToDataverse     = $true
            CallsFlow             = $null
            UsesPowerBI           = $null
        }
    }

    $flows = Get-AdminFlow -EnvironmentName $env.EnvironmentName -ErrorAction SilentlyContinue
    foreach ($flow in $flows) {
        $connRefs = Get-ConnectionReferenceNames -AppOrFlow $flow
        $trigger = $flow.Internal.properties.definitionSummary.triggers | Select-Object -First 1
        $triggerType = switch -Regex ("$($trigger.type)") {
            'Recurrence'          { 'Scheduled'; break }
            'Request|ApiConnectionWebhook|OpenApiConnectionWebhook' { 'Trigger-based (event/webhook)'; break }
            'Manual'              { 'Manual/Business process'; break }
            default               { "Trigger-based ($($trigger.type))" }
        }

        $flowResults += [PSCustomObject]@{
            EnvironmentName       = $env.DisplayName
            FlowName              = $flow.FlowName
            DisplayName           = $flow.DisplayName
            State                 = $flow.Enabled
            IsInactiveOrFailed    = ($flow.Enabled -ne $true)
            TriggerType           = $triggerType
            IsCloudFlow           = $true    # desktop flows require Get-AdminPowerAppEnvironment + separate RPA license reporting; not exposed by Get-AdminFlow
            CreatedTime           = $flow.CreatedTime
            LastModifiedTime      = $flow.LastModifiedTime
            Owner                 = $flow.CreatedBy.displayName
            ConnectionReferences  = ($connRefs -join '; ')
            UsesPremiumConnector  = [bool]($connRefs | Where-Object { $_ -in $premiumConnectorNames })
            UsesPowerBIOrApi      = [bool]($connRefs | Where-Object { $_ -in @('shared_powerbi', 'shared_webcontents', 'shared_http') })
            UsesDataverse         = [bool]($connRefs -contains 'shared_commondataserviceforapps')
        }
    }
}

Export-Discovery -Data $appResults -OutputFolder $OutputFolder -Name "03-PowerApps"
Export-Discovery -Data $flowResults -OutputFolder $OutputFolder -Name "03-PowerAutomate-CloudFlows"

Write-Host "Note: desktop flows (RPA) are not returned by Get-AdminFlow - pull those from the Power Automate admin center > Desktop flows report." -ForegroundColor Yellow
Write-Host "Note: 'business-critical vs personal productivity' is not inferable from metadata alone - cross-reference LinkedToDataverse/CallsFlow/UsesPowerBI with business owner interviews." -ForegroundColor Yellow
